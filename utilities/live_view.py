"""
The "Live browser" control, shared by every page that drives a browser.

Locally the Chrome window is on the user's own screen, so this renders nothing.
Under execution_type=azure the browser lives on a virtual display inside the
Chrome container, and the only way a person can see or click it is noVNC.

WHY A NEW TAB RATHER THAN AN EMBEDDED FRAME
-------------------------------------------
Streamlit re-runs the whole script on every interaction, and re-running
re-creates the component tree. An `st.components.v1.iframe` is therefore torn
down and rebuilt on EVERY button click, checkbox, or text entry — and each
rebuild drops the noVNC WebSocket and reconnects it.

That is not cosmetic. It caused a chain of failures:
  * the view disconnected repeatedly while the user worked
  * clicks made during a reconnect never reached Chrome, so the recorder
    captured nothing, so `st.session_state.actions` stayed empty, so the
    "Save Workflow" name box (gated on that list) never appeared
  * the frame re-expanded on every rerun
  * the browser was stuck at whatever height the frame was given

Opening noVNC in its own tab fixes all of it at once: Streamlit reruns cannot
touch another tab, so the connection persists until the user closes it, and the
browser gets a full window it can maximise. The embedded frame is kept as an
opt-in for anyone who wants it side by side and accepts the reconnects.
"""

import streamlit as st

from utilities.browser_factory import (check_novnc_reachable, get_novnc_url,
                                       quit_driver)


def mark_opened(key):
    """
    Note that the browser was just opened, so the panel expands on this run
    only. Call right after creating the driver.
    """
    st.session_state["_lv_opened_%s" % key] = True


def auto_open_live_browser(driver, key="iqea"):
    """
    Open the live browser in a new tab automatically, once per session.

    Returns True if the attempt was made (azure), False if not applicable.

    Two things make this best-effort rather than guaranteed:

    1. Browsers block `window.open` that is not inside a user-gesture handler.
       Clicking "Open Browser" IS a gesture, but Streamlit answers it with a
       server round-trip and re-render, so by the time this script runs the
       gesture context is gone. Chrome usually treats that as a popup and
       blocks it unless the user has allowed popups for the site.
    2. The script runs inside Streamlit's sandboxed component frame, which must
       permit popups for the call to succeed at all.

    So the manual button stays as the reliable path, and this only saves a
    click when the browser cooperates. `sessionStorage` is keyed on the
    WebDriver session id, so a Streamlit re-run cannot spam a new tab on every
    interaction — it opens once per browser session and no more.
    """
    import json

    url = get_novnc_url(driver)
    if not url:
        return False
    token = getattr(driver, "session_id", None) or "unknown"

    html = """
<div id="iqea-popup-blocked-%(key)s"
     style="display:none;font:600 13px system-ui,sans-serif;color:#8a4b00;
            background:#fff4e5;border:1px solid #ffb066;border-radius:8px;
            padding:10px 12px;">
  Your browser blocked the new tab. Use the
  <b>Open live browser in a new tab</b> button below, or allow pop-ups for
  this site to have it open automatically.
</div>
<script>
(function () {
  var key = 'iqea_live_opened_' + %(token)s;
  var warn = function () {
    var el = document.getElementById('iqea-popup-blocked-%(key)s');
    if (el) { el.style.display = 'block'; }
  };
  try {
    // Open once per WebDriver session, no matter how often Streamlit re-runs.
    if (window.sessionStorage && sessionStorage.getItem(key)) { return; }
    var w = window.open(%(url)s, '_blank');
    if (w && !w.closed) {
      try { w.opener = null; } catch (e) {}
      if (window.sessionStorage) { sessionStorage.setItem(key, '1'); }
    } else {
      warn();
    }
  } catch (e) {
    warn();
  }
})();
</script>
""" % {"url": json.dumps(url), "token": json.dumps(token), "key": key}

    st.components.v1.html(html, height=64)
    return True


def _session_alive(driver):
    """
    Is the WebDriver session still usable?

    A dead session is the likely cause of the panel showing a stale screen or
    the Grid's own page instead of the report: the display still exists, but
    nothing is driving Chrome any more.
    """
    if driver is None:
        return False, "no browser session"
    try:
        _ = driver.current_url
        return True, driver.current_url
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__,
                                  str(exc).splitlines()[0])


def render_live_browser_panel(driver, key, title="🖥️ Live browser",
                              caption=None, height=760, expanded=None,
                              on_close=None):
    """
    Render the live browser controls for `driver`.

    Returns True if rendered (azure), False if not needed (local).
    """
    url = get_novnc_url(driver)
    if not url:
        return False           # local: the real window is already on screen

    # Expanded only on the run where the browser was opened (issue 1a).
    opened_flag = "_lv_opened_%s" % key
    if expanded is None:
        expanded = bool(st.session_state.pop(opened_flag, False))

    alive, where = _session_alive(driver)

    with st.expander(title, expanded=expanded):
        if not alive:
            st.warning(
                "⚠️ The browser session has ended (%s). The live view may show "
                "a stale screen or the Selenium start page. Click **Open "
                "Browser** again to start a fresh session." % where
            )

        st.markdown(
            '<a href="%s" target="_blank" rel="noopener" '
            'style="display:inline-block;padding:10px 18px;background:#F47B20;'
            'color:#fff;font-weight:700;border-radius:8px;'
            'text-decoration:none;">🖥️ Open live browser in a new tab ↗</a>'
            % url,
            unsafe_allow_html=True,
        )
        st.caption(
            caption or
            "Opens the real browser in its own tab. **Keep that tab open** and "
            "arrange it beside IQEA — the connection stays up while you work, "
            "and you can maximise it. Do your clicking and typing there; every "
            "action is captured exactly as it would be locally."
        )
        if alive:
            st.caption("Currently showing: `%s`" % where)

        # Opt-in embedded view. Warned about, because Streamlit reruns will
        # drop and re-establish the connection.
        if st.checkbox("Also show it embedded here (reconnects on every click)",
                       key="embed_%s" % key):
            st.info(
                "The embedded frame reconnects whenever Streamlit re-runs — "
                "which is every button click. Use the new tab while recording; "
                "this is only for a quick look."
            )
            frame_h = st.select_slider(
                "Frame height", options=[480, 620, 760, 900, 1080],
                value=height, key="embed_h_%s" % key)
            st.components.v1.iframe(url, height=frame_h, scrolling=True)

        with st.expander("Live view diagnostics", expanded=False):
            ok, detail = st.session_state.setdefault(
                "_novnc_probe_%s" % key, check_novnc_reachable())
            if not ok:
                st.error(
                    "`/vnc/` is returning the IQEA app instead of noVNC — the "
                    "view will show IQEA inside itself. Check that "
                    "`/usr/share/novnc/` exists in the image and "
                    "`WEBSITES_PORT=8000`."
                )
            st.code(detail, language="text")
            st.caption("If the tab opens but stays on 'connecting', the Chrome "
                       "container is not serving noVNC — check SE_START_VNC=true. "
                       "If it asks for a password, set [BROWSER] novnc_password "
                       "to match the sidecar's SE_VNC_PASSWORD.")

    if st.button("🧹 Close browser", key="close_browser_%s" % key):
        quit_driver(driver)
        st.session_state.pop("_novnc_probe_%s" % key, None)
        st.session_state.pop(opened_flag, None)
        if on_close:
            on_close()
        st.success("Browser released. You can close the live browser tab.")
        st.rerun()

    return True


def clear_probe(key):
    """Forget a cached probe result so the next open re-checks."""
    st.session_state.pop("_novnc_probe_%s" % key, None)
