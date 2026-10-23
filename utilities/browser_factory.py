"""
IQEA browser factory
====================

Single place where IQEA creates Selenium Chrome sessions.

Supported modes
---------------
LOCAL
    Chrome runs on the developer machine using webdriver.Chrome().

AZURE / REMOTE
    Chrome runs through Selenium Grid. The IQEA container connects to the
    Selenium Hub and Grid assigns each WebDriver session to a free Chrome node.

Important concurrency rule
--------------------------
Do NOT publish port 4444 from chrome-node containers. Port 4444 belongs to the
Selenium Hub only. Chrome nodes communicate with the Hub over the Compose
network.

This module is intentionally safe to IMPORT even when Selenium is not installed
in the current Python environment. Local execution still requires Selenium to
be installed. Azure containers must contain Selenium because they create remote
WebDriver sessions.
"""

import logging
import os
import threading
import time
import uuid

# other existing imports...


logger = logging.getLogger(__name__)



try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    webdriver = None
    Options = None
    SELENIUM_AVAILABLE = False

from config.settings_reader import (
    get_novnc_path,
    get_selenium_remote_url,
    get_window_size,
    is_azure,
    get_novnc_password,
)

logger = logging.getLogger(__name__)


# ============================================================================
# ORIGINAL PROFILE FLAGS
# ============================================================================

_RECORDER_ARGS = [
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--remote-allow-origins=*",
    "--disable-dev-shm-usage",
]

_LOCATOR_ARGS = [
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--remote-allow-origins=*",
    "--disable-dev-shm-usage",
]

_SELF_HEALING_ARGS = [
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

_XPATH_PAGE_ARGS = [
    "--remote-debugging-port=9222",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

_PBI_ARGS = [
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-extensions",
]

PROFILES = {
    "recorder": _RECORDER_ARGS,
    "locator": _LOCATOR_ARGS,
    "self_healing": _SELF_HEALING_ARGS,
    "xpath_page": _XPATH_PAGE_ARGS,
    "pbi": _PBI_ARGS,
}


# ============================================================================
# AZURE CHROME FLAGS
# ============================================================================

# Fixed remote-debugging port causes concurrent Chrome instances to collide.
_AZURE_DROP_PREFIXES = (
    "--remote-debugging-port",
)

_AZURE_REQUIRED = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _require_selenium():
    """Raise a useful error only when Selenium is actually needed."""
    if not SELENIUM_AVAILABLE:
        raise RuntimeError(
            "Selenium is not installed in this Python environment.\n"
            "For local development install it with:\n"
            "    python -m pip install selenium webdriver-manager\n"
            "\n"
            "The browser_factory module itself can still be imported without "
            "Selenium; only browser creation requires the package."
        )


def _capability(capabilities, *names):
    """Return the first non-empty capability value."""
    for name in names:
        value = capabilities.get(name)
        if value:
            return value
    return None


# ============================================================================
# CHROME OPTIONS
# ============================================================================

def build_options(profile="recorder", headless=False):
    """
    Build ChromeOptions for local or Azure execution.

    LOCAL:
        Preserves the original profile flags.

    AZURE:
        Removes fixed remote-debugging-port=9222 and adds container-safe flags,
        a unique user-data directory and an explicit window size.

    Azure Chrome is deliberately NOT headless because noVNC needs a visible
    browser/X display.
    """
    _require_selenium()

    if profile not in PROFILES:
        raise ValueError(
            "Unknown browser profile %r. Known: %s"
            % (profile, ", ".join(sorted(PROFILES)))
        )

    options = Options()
    args = list(PROFILES[profile])

    if is_azure():
        # Remove fixed debugging port so multiple Chrome nodes/sessions can run.
        args = [
            arg
            for arg in args
            if not arg.startswith(_AZURE_DROP_PREFIXES)
        ]

        for required in _AZURE_REQUIRED:
            if required not in args:
                args.append(required)

        width, height = get_window_size()
        args.append("--window-size=%d,%d" % (width, height))

        # Every Selenium session gets its own Chrome profile.
        args.append(
            "--user-data-dir=/tmp/iqea-chrome-%s" % uuid.uuid4().hex
        )

        # Do NOT add --headless here.
        # The browser must be visible through Xvfb/noVNC.

    elif headless:
        args.insert(0, "--headless=new")

    for arg in args:
        options.add_argument(arg)

    if profile == "pbi":
        options.add_experimental_option(
            "excludeSwitches",
            ["enable-automation"],
        )
        options.add_experimental_option(
            "useAutomationExtension",
            False,
        )

    return options


# ============================================================================
# SESSION INFORMATION
# ============================================================================

def get_browser_session_info(driver):
    """
    Return safe information about the current Selenium session.

    Works for both local Chrome and Selenium Grid.
    """
    empty = {
        "session_id": None,
        "browser_name": None,
        "browser_version": None,
        "platform": None,
        "node": None,
        "vnc_endpoint": None,
        "current_url": None,
        "title": None,
    }

    if driver is None:
        return empty

    try:
        capabilities = getattr(driver, "capabilities", {}) or {}

        info = dict(empty)
        info["session_id"] = getattr(driver, "session_id", None)
        info["browser_name"] = capabilities.get("browserName")
        info["browser_version"] = capabilities.get("browserVersion")
        info["platform"] = (
            capabilities.get("platformName")
            or capabilities.get("platform")
        )

        info["node"] = _capability(
            capabilities,
            "se:node",
            "se:nodeId",
            "se:cdp",
        )

        info["vnc_endpoint"] = _capability(
            capabilities,
            "se:vnc",
            "se:vncLocalAddress",
        )

        try:
            info["current_url"] = driver.current_url
        except Exception:
            pass

        try:
            info["title"] = driver.title
        except Exception:
            pass

        return info

    except Exception as exc:
        return {
            **empty,
            "session_id": getattr(driver, "session_id", None),
            "error": "%s: %s" % (type(exc).__name__, exc),
        }


def diagnose_browser_session(driver):
    """
    Return diagnostic information used by the IQEA recorder.

    Unlike get_browser_session_info(), this explicitly includes an `ok` flag
    and an `error` field.
    """
    result = {
        "ok": False,
        "session_id": None,
        "browser_name": None,
        "browser_version": None,
        "platform": None,
        "node": None,
        "vnc_endpoint": None,
        "current_url": None,
        "title": None,
        "error": None,
    }

    if driver is None:
        result["error"] = "Driver is None"
        return result

    try:
        info = get_browser_session_info(driver)

        for key in result:
            if key in info:
                result[key] = info[key]

        result["ok"] = bool(result["session_id"])

        if not result["ok"] and not result["error"]:
            result["error"] = "Selenium session_id is missing"

        return result

    except Exception as exc:
        result["error"] = "%s: %s" % (
            type(exc).__name__,
            str(exc),
        )
        return result


# ============================================================================
# DRIVER CREATION
# ============================================================================

def get_driver(profile="recorder", url=None, headless=False):
    """
    Create a Chrome driver.

    LOCAL:
        webdriver.Chrome()

    AZURE:
        webdriver.Remote() -> Selenium Hub -> one available Chrome node.

    Each Azure session receives a unique Chrome profile. Selenium Grid performs
    the actual session-to-node routing.
    """
    _require_selenium()

    options = build_options(profile, headless=headless)
    
    if is_azure():

        target = get_selenium_remote_url()

        ok, detail = check_grid_reachable(target)

        if not ok:
            raise RuntimeError(
                _grid_unreachable_message(target, detail)
            )
        # logger.
        #     info(
        #         "AZURE GRID SESSION REQUEST - remote_url=%s"
        #     ,
        #         target
        #     ,
        #     )

        #     logger.
        #     info(
        #         "AZURE GRID SESSION CAPABILITIES - %s"
        #     ,
        #         options.
        #     capabilities,
        #     )
        # driver = webdriver.Remote(
        #     command_executor=target,
        #     options=options,
        # )
        logger.info("=== AZURE DRIVER CREATION START ===")
        logger.info("Remote URL: %s", target)
        logger.info("Browser profile: %s", profile)
        logger.info("Capabilities BEFORE Remote: %s", options.capabilities)

        print("=== AZURE DRIVER CREATION START ===")
        print("Remote URL: %s", target)
        print("Browser profile: %s", profile)
        print("Capabilities BEFORE Remote: %s", options.capabilities)
        request_start = time.monotonic()
        try:
            logger.info("Calling webdriver.Remote()...")

            driver = webdriver.Remote(
                command_executor=target,
                options=options,
            )
            elapsed = time.monotonic() - request_start
            logger.info("webdriver.Remote() RETURNED SUCCESSFULLY")
            logger.info("Session ID: %s", driver.session_id)
            logger.info("Returned capabilities: %s", driver.capabilities)
            print("webdriver.Remote() RETURNED SUCCESSFULLY")
            print("Session ID: %s", driver.session_id)
            print("Returned capabilities: %s", driver.capabilities)

        except Exception as e:
            elapsed = time.monotonic() - request_start
            logger.exception("webdriver.Remote() FAILED - elapsed:%.2f remote=%s exception=%s", elapsed, target, e)
            print("webdriver.Remote() FAILED - elapsed:%.2f remote=%s exception=%s", elapsed, target, e)
            raise
        

        start_keepalive(driver)

    else:
        driver = _local_driver(profile, options)

    if url:
        normalized = normalize_url(url)
        if normalized:
            driver.get(normalized)

    return driver


def _local_driver(profile, options):
    """
    Create a local Chrome driver.

    PBI keeps webdriver-manager compatibility with the old implementation.
    Other profiles use Selenium Manager through webdriver.Chrome().
    """
    _require_selenium()

    if profile == "pbi":
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            return webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options,
            )
        except ImportError as exc:
            raise RuntimeError(
                "PBI local browser requires webdriver-manager. "
                "Install with: python -m pip install webdriver-manager"
            ) from exc

    return webdriver.Chrome(options=options)


# ============================================================================
# SELENIUM GRID HEALTH
# ============================================================================

def check_grid_reachable(url=None, timeout=5):
    """
    Check whether Selenium Grid responds.

    Returns:
        (True, detail)
        (False, detail)

    `ready=False` alone is NOT treated as an infrastructure failure. A Grid
    can report ready=False while all slots are temporarily occupied.
    """
    import json
    import urllib.error
    import urllib.request

    target = url or get_selenium_remote_url()

    base = target.rstrip("/")

    # Remove common WebDriver suffixes.
    for suffix in ("/wd/hub", "/wd/hub/"):
        if base.endswith(suffix.rstrip("/")):
            base = base[: -len(suffix.rstrip("/"))]

    status_url = base + "/status"

    try:
        with urllib.request.urlopen(status_url, timeout=timeout) as resp:
            body = json.loads(
                resp.read().decode("utf-8", "replace")
            )

        value = body.get("value", {})
        ready = value.get("ready")
        nodes = value.get("nodes") or []

        slots = 0
        free_slots = 0

        for node in nodes:
            node_slots = node.get("slots") or []
            slots += len(node_slots)

            for slot in node_slots:
                stereotype = slot.get("stereotype") or {}
                session = slot.get("session")
                if session is None:
                    free_slots += 1

        detail = (
            "ready=%s nodes=%d slots=%d free_slots=%d — %s"
            % (
                ready,
                len(nodes),
                slots,
                free_slots,
                value.get("message", "").strip() or "ok",
            )
        )

        # Reachability only requires the Hub to respond.
        usable = bool(nodes) and slots > 0

        return usable, detail

    except urllib.error.HTTPError as exc:
        return False, "HTTP %s from %s" % (
            exc.code,
            status_url,
        )

    except Exception as exc:
        return False, "%s: %s" % (
            type(exc).__name__,
            exc,
        )


def wait_for_free_slot(timeout=60, poll=2.0):
    """
    Wait for a free Selenium Grid slot.

    Returns:
        (True, detail) when a free slot is detected.
        (False, detail) after timeout.

    This is advisory. Selenium Grid can still queue a session request after
    this function returns False.
    """
    import json
    import urllib.request

    target = get_selenium_remote_url()
    base = target.rstrip("/")

    for suffix in ("/wd/hub", "/wd/hub/"):
        if base.endswith(suffix.rstrip("/")):
            base = base[: -len(suffix.rstrip("/"))]

    status_url = base + "/status"

    deadline = time.time() + timeout
    detail = "not checked"

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(status_url, timeout=5) as resp:
                value = json.loads(
                    resp.read().decode("utf-8", "replace")
                ).get("value", {})

            nodes = value.get("nodes") or []
            total_slots = 0
            free_slots = 0

            for node in nodes:
                slots = node.get("slots") or []
                total_slots += len(slots)

                for slot in slots:
                    if slot.get("session") is None:
                        free_slots += 1

            if free_slots > 0:
                return True, (
                    "free_slots=%d total_slots=%d"
                    % (free_slots, total_slots)
                )

            detail = (
                "no free slot: nodes=%d total_slots=%d"
                % (len(nodes), total_slots)
            )

        except Exception as exc:
            detail = "%s: %s" % (
                type(exc).__name__,
                exc,
            )

        time.sleep(poll)

    return False, detail


# ============================================================================
# NO-VNC
# ============================================================================

def check_novnc_reachable(timeout=5):
    """
    Advisory check for the local nginx /vnc/ route.

    It specifically detects the common failure where Streamlit receives the
    /vnc/ request instead of nginx serving noVNC.
    """
    import urllib.request

    notes = []

    path = get_novnc_path()

    if not path.endswith("/"):
        path += "/"

    proxied_url = (
        "http://127.0.0.1:8000%s"
        "vnc.html"
    ) % path

    misrouted = False

    try:
        with urllib.request.urlopen(
            proxied_url,
            timeout=timeout,
        ) as resp:
            body = resp.read(8192).decode(
                "utf-8",
                "replace",
            )

            status = resp.status

        if (
            "stAppViewContainer" in body
            or "streamlit" in body.lower()
        ):
            misrouted = True
            notes.append(
                "proxied %s returned Streamlit instead of noVNC"
                % proxied_url
            )
        else:
            notes.append(
                "proxied %s -> HTTP %s"
                % (proxied_url, status)
            )

    except Exception as exc:
        notes.append(
            "proxied %s -> %s: %s "
            "(advisory only)"
            % (
                proxied_url,
                type(exc).__name__,
                exc,
            )
        )

    return (
        not misrouted,
        " | ".join(notes),
    )


def get_novnc_url(driver):
    """
    Build a session-specific noVNC URL.

    Example:

        /vnc/vnc.html?autoconnect=1&resize=scale&
        path=session/<SESSION_ID>/se/vnc

    The WebSocket path is resolved through the IQEA nginx/Hub route, so the
    actual Chrome node does not need to be publicly exposed.

    LOCAL:
        Returns an empty string because the browser is already on the local
        machine.

    AZURE:
        Returns the IQEA-origin noVNC URL.
    """
    if driver is None:
        return ""

    if not is_azure():
        return ""

    try:
        session_id = getattr(driver, "session_id", None)

        if not session_id:
            return ""

        base = get_novnc_path()

        if not base.endswith("/"):
            base += "/"

        capabilities = getattr(
            driver,
            "capabilities",
            {},
        ) or {}

        vnc_endpoint = _capability(
            capabilities,
            "se:vnc",
            "se:vncLocalAddress",
        )

        vnc_path = None

        if vnc_endpoint:
            try:
                from urllib.parse import urlparse

                parsed = urlparse(vnc_endpoint)
                path = parsed.path or ""

                if "/session/" in path:
                    vnc_path = path.lstrip("/")

            except Exception:
                vnc_path = None

        # Selenium Grid versions that do not advertise se:vnc use the
        # standard Grid session VNC route.
        if not vnc_path:
            vnc_path = (
                "session/%s/se/vnc"
                % session_id
            )

        from urllib.parse import quote

        url = (
            base
            + "vnc.html"
            + "?autoconnect=1"
            + "&resize=scale"
            + "&reconnect=1"
            + "&path="
            + quote(vnc_path, safe="/")
        )

        password = get_novnc_password()

        if password:
            url += "&password=" + quote(
                password,
                safe="",
            )

        return url

    except Exception:
        logger.exception(
            "Failed to construct noVNC URL"
        )
        return ""


# ============================================================================
# PAGE / WINDOW HELPERS
# ============================================================================

def wait_until_page_ready(
    driver,
    expected_url=None,
    timeout=45,
):
    """
    Wait until the browser has navigated and the document is complete.

    A screenshot is requested to force a paint before returning.
    """
    from utilities.driver_lock import driver_guard

    if driver is None:
        return False, "driver is None"

    deadline = time.time() + timeout
    detail = "timed out"

    while time.time() < deadline:
        try:
            with driver_guard(driver, timeout=15):
                state = driver.execute_script(
                    "return document.readyState;"
                )
                current = driver.current_url or ""

            navigated = bool(current) and not current.startswith(
                (
                    "about:",
                    "data:",
                    "chrome://",
                )
            )

            expected_ok = True

            if expected_url:
                expected = normalize_url(expected_url)

                if expected:
                    expected_ok = (
                        current == expected
                        or current.startswith(expected)
                        or expected in current
                    )

            if (
                state == "complete"
                and navigated
                and expected_ok
            ):
                try:
                    with driver_guard(driver, timeout=15):
                        driver.get_screenshot_as_png()
                except Exception:
                    pass

                return True, current

            detail = (
                "readyState=%s url=%s expected_ok=%s"
                % (
                    state,
                    current or "(none)",
                    expected_ok,
                )
            )

        except Exception as exc:
            detail = "%s: %s" % (
                type(exc).__name__,
                str(exc).splitlines()[0],
            )

        time.sleep(1)

    return False, detail


def safe_maximize(driver):
    """
    Try to maximise the browser without allowing window-manager errors to
    break the recording workflow.
    """
    if driver is None:
        return False

    try:
        driver.maximize_window()
        return True

    except Exception as exc:
        logger.warning(
            "Browser maximize skipped: %s",
            str(exc).splitlines()[0],
        )
        return False


def normalize_url(url):
    """
    Convert user input into an absolute URL.
    """
    clean = (
        (url or "")
        .strip()
        .strip('"')
        .strip("'")
    )

    if not clean:
        return ""

    if not clean.startswith(
        (
            "http://",
            "https://",
            "file://",
            "about:",
            "data:",
        )
    ):
        clean = "https://" + clean

    return clean


# ============================================================================
# GRID ERROR MESSAGE
# ============================================================================

def _grid_unreachable_message(
    target,
    detail,
):
    """
    Produce an actionable Selenium Grid connectivity error.
    """
    host = (
        target
        .split("//")[-1]
        .split("/")[0]
    )

    loopback = host.startswith(
        (
            "127.0.0.1",
            "localhost",
            "[::1]",
        )
    )

    lines = [
        "Selenium Grid is not reachable at %s" % target,
        "  probe: %s" % detail,
        "",
    ]

    if loopback:
        lines += [
            "SELENIUM_REMOTE_URL points to loopback (%s)." % host,
            "",
            "In Docker/Podman Compose, 127.0.0.1 means the IQEA",
            "container itself, NOT the Selenium Hub container.",
            "",
            "Use the Compose service name instead:",
            "  SELENIUM_REMOTE_URL=http://chrome:4444",
            "",
            "If the Hub service is named selenium-hub:",
            "  SELENIUM_REMOTE_URL=http://selenium-hub:4444",
            "",
            "Only the Selenium Hub should publish host port 4444.",
            "Do NOT publish 4444 from chrome-node replicas.",
        ]

    else:
        lines += [
            "Check that the Grid container is running.",
            "Check that '%s' resolves from the IQEA container." % host,
            "Check that the Hub port is 4444.",
            "Check that IQEA and the Hub share the same network.",
            "",
            "From inside IQEA run:",
            "  curl -sS http://%s/status" % host,
        ]

    lines += [
        "",
        "For local Chrome use:",
        "  execution_type=local",
        "",
        "For Azure/remote Selenium use:",
        "  execution_type=azure",
        "  SELENIUM_REMOTE_URL=<hub-address>",
    ]

    return "\n".join(lines)


# ============================================================================
# KEEPALIVE
# ============================================================================

_keepalive_flags = {}
_keepalive_lock = threading.Lock()


def start_keepalive(
    driver,
    interval=60,
):
    """
    Keep an Azure Selenium session alive while the user interacts directly
    with Chrome through noVNC.
    """
    if driver is None or not is_azure():
        return False

    session_id = getattr(
        driver,
        "session_id",
        None,
    )

    if not session_id:
        return False

    with _keepalive_lock:
        if session_id in _keepalive_flags:
            return False

        flag = {"stop": False}
        _keepalive_flags[session_id] = flag

    def _ping():
        try:
            from utilities.driver_lock import driver_guard
        except Exception:
            driver_guard = None

        while not flag["stop"]:
            slept = 0.0

            while slept < interval:
                if flag["stop"]:
                    return

                time.sleep(1.0)
                slept += 1.0

            try:
                if driver_guard:
                    with driver_guard(
                        driver,
                        timeout=10,
                    ):
                        _ = driver.title
                else:
                    _ = driver.title

            except Exception:
                break

        with _keepalive_lock:
            _keepalive_flags.pop(
                session_id,
                None,
            )

    thread = threading.Thread(
        target=_ping,
        daemon=True,
        name="iqea-keepalive-%s"
        % session_id[:8],
    )

    thread.start()

    return True


def stop_keepalive(driver):
    """
    Stop the keepalive thread for a driver.
    """
    if driver is None:
        return

    session_id = getattr(
        driver,
        "session_id",
        None,
    )

    if not session_id:
        return

    with _keepalive_lock:
        flag = _keepalive_flags.get(session_id)

    if flag:
        flag["stop"] = True


def keepalive_count():
    """
    Return the number of currently active keepalive sessions.
    """
    with _keepalive_lock:
        return len(_keepalive_flags)


# ============================================================================
# DRIVER CLEANUP
# ============================================================================

def quit_driver(driver):
    """
    Safely close a local or remote browser session.
    """
    if driver is None:
        return

    try:
        stop_keepalive(driver)
    except Exception:
        pass

    try:
        driver.quit()
    except Exception:
        logger.exception(
            "Failed to quit browser"
        )


# ============================================================================
# LOCAL PROFILE PARITY TEST
# ============================================================================

def test_browser_factory_parity():
    """
    Verify that local profile arguments have not accidentally changed.

    Run:

        python -c "from utilities.browser_factory import \
test_browser_factory_parity as t; t()"
    """
    from config.settings_reader import get_execution_type

    execution_type = get_execution_type()

    assert execution_type == "local", (
        "parity check must run with execution_type=local "
        "(got %r)"
        % execution_type
    )

    expected = {
        "recorder": _RECORDER_ARGS,
        "locator": _LOCATOR_ARGS,
        "self_healing": _SELF_HEALING_ARGS,
        "xpath_page": _XPATH_PAGE_ARGS,
        "pbi": _PBI_ARGS,
    }

    for profile, wanted in expected.items():
        got = build_options(profile).arguments

        assert got == wanted, (
            "profile %r drifted from original flags:\n"
            "  expected: %s\n"
            "  actual:   %s"
            % (
                profile,
                wanted,
                got,
            )
        )

    print(
        "browser_factory parity OK — "
        "all %d profiles match their original flags"
        % len(expected)
    )


# ============================================================================
# DIAGNOSTICS
# ============================================================================

def diagnose():
    """
    Run browser/Grid diagnostics.

    Recommended inside the IQEA container:

        python -m utilities.browser_factory
    """
    from config.settings_reader import get_execution_type

    print("IQEA browser diagnostics")
    print("-" * 60)

    execution_type = get_execution_type()

    print(
        "  execution_type      : %s"
        % execution_type
    )

    print(
        "  IQEA_EXECUTION_TYPE : %r"
        % os.environ.get(
            "IQEA_EXECUTION_TYPE"
        )
    )

    print(
        "  Selenium installed  : %s"
        % SELENIUM_AVAILABLE
    )

    if not is_azure():
        print()
        print(
            "  mode                : LOCAL"
        )
        print(
            "  Chrome               : local webdriver.Chrome()"
        )
        print(
            "  Grid                 : not used"
        )

        if not SELENIUM_AVAILABLE:
            print()
            print(
                "Install local dependencies:"
            )
            print(
                "  python -m pip install selenium webdriver-manager"
            )

            return 1

        return 0

    target = get_selenium_remote_url()

    print()
    print(
        "  mode                : AZURE / REMOTE"
    )
    print(
        "  SELENIUM_REMOTE_URL : %s"
        % target
    )
    print(
        "  GRID_UPSTREAM        : %s"
        % os.environ.get(
            "GRID_UPSTREAM",
            "<unset>",
        )
    )
    print(
        "  noVNC path           : %s"
        % get_novnc_path()
    )

    print()

    ok, detail = check_grid_reachable(
        target
    )

    print(
        "  GRID REACHABLE       : %s"
        % ("YES" if ok else "NO")
    )
    print(
        "  %s"
        % detail
    )

    if not ok:
        print()
        print(
            _grid_unreachable_message(
                target,
                detail,
            )
        )

        return 1

    print()

    vok, vdetail = check_novnc_reachable()

    print(
        "  noVNC route          : %s"
        % (
            "OK"
            if vok
            else "MISROUTED"
        )
    )

    print(
        "  %s"
        % vdetail
    )

    return 0


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    raise SystemExit(diagnose())
