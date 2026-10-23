"""
Runtime capability detection for IQEA.

A feature is available only where the platform can actually support it. Rather
than scattering `if sys.platform == "win32"` / `if is_azure()` checks through
the UI, every feature asks here, and the UI renders a single consistent reason
when something is off.

Desktop (WinAppDriver) recording is the important one: its modules import
`win32gui`, `pywinauto`, `mouse` and `keyboard` at module scope. On Linux that
raises ImportError, so the import MUST stay behind `load_desktop_modules()` —
importing it eagerly takes the whole Streamlit app down, not just the feature.
"""

import shutil
import sys

from config.settings_reader import get_execution_type, get_tesseract_cmd, is_azure

# Cache the desktop import attempt: (ok: bool, reason: str, session_cls, recorder_cls)
_desktop_probe = None


# ── Desktop (WinAppDriver) recording ─────────────────────────────────────────

def is_desktop_recording_available():
    """True only when desktop recording can actually run here."""
    return load_desktop_modules()[0]


def desktop_unavailable_reason():
    """Human-readable reason for the UI, or '' when available."""
    ok, reason, _, _ = load_desktop_modules()
    return "" if ok else reason


def load_desktop_modules():
    """
    Lazily import the desktop recorder/session classes.

    Returns (ok, reason, DesktopSession, DesktopRecorder). On failure the two
    classes are None and `reason` explains why. Result is cached, so the
    expensive/failing import is attempted at most once per process.
    """
    global _desktop_probe
    if _desktop_probe is not None:
        return _desktop_probe

    if is_azure():
        _desktop_probe = (
            False,
            "Desktop recording is available in local execution only. This "
            "instance runs in Azure (execution_type=azure), where there is no "
            "Windows desktop to record.",
            None, None,
        )
        return _desktop_probe

    if sys.platform != "win32":
        _desktop_probe = (
            False,
            "Desktop recording requires Windows (pywinauto / WinAppDriver). "
            "Current platform: %s." % sys.platform,
            None, None,
        )
        return _desktop_probe

    try:
        from desktop.session import DesktopSession
        from desktop.recorder import DesktopRecorder
        _desktop_probe = (True, "", DesktopSession, DesktopRecorder)
    except Exception as exc:
        # Windows but the deps are missing/broken — degrade, do not crash.
        _desktop_probe = (
            False,
            "Desktop recording dependencies could not be loaded (%s: %s). "
            "Install the Windows extras from requirements.txt."
            % (type(exc).__name__, exc),
            None, None,
        )
    return _desktop_probe


# ── Browser ──────────────────────────────────────────────────────────────────

def is_remote_browser():
    """True when Chrome runs in a separate container driven over WebDriver."""
    return is_azure()


# ── OCR ──────────────────────────────────────────────────────────────────────

def is_tesseract_available():
    """True only if the tesseract BINARY is resolvable (pytesseract shells out)."""
    configured = get_tesseract_cmd()
    if configured:
        return bool(shutil.which(configured)) or _is_file(configured)
    return bool(shutil.which("tesseract"))


def _is_file(path):
    import os
    return os.path.isfile(path)


# ── Summary (handy for a diagnostics panel / startup log) ────────────────────

def capability_summary():
    return {
        "execution_type": get_execution_type(),
        "platform": sys.platform,
        "desktop_recording": is_desktop_recording_available(),
        "remote_browser": is_remote_browser(),
        "tesseract": is_tesseract_available(),
    }
