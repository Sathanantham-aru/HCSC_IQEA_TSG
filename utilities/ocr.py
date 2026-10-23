"""
Central OCR entry point.

`pytesseract` is only a thin wrapper — it shells out to a `tesseract` BINARY. On
a workstation that binary is installed and on PATH; in a container it exists only
if the image installed it, and on Azure App Service code deploys it never exists
at all. A bare `pytesseract.image_to_string(...)` therefore raises
TesseractNotFoundError and takes the whole feature down.

This module:
  * points pytesseract at the configured binary ([OCR] tesseract_cmd), once
  * degrades to "" instead of raising when the binary is absent
  * lets the vision-LLM path be preferred via [OCR] prefer_vision_ocr

IQEA already has a vision-LLM OCR replacement (see the wireframe extraction in
utilities/Utilities_Xpath.py). It is more accurate than tesseract on screenshots
and wireframes and needs no OS dependency, so it is the better default in Azure.
"""

from config.settings_reader import get_tesseract_cmd, prefer_vision_ocr

_configured = False
_available = None

try:
    import pytesseract
    _IMPORTED = True
except Exception:
    _IMPORTED = False


def _configure():
    """Point pytesseract at the configured binary. Idempotent."""
    global _configured
    if _configured or not _IMPORTED:
        return
    cmd = get_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    _configured = True


def is_available():
    """
    True only when pytesseract AND the tesseract binary are both usable.

    Probed once — `get_tesseract_version()` actually executes the binary, so it
    catches "installed but broken" as well as "not installed".
    """
    global _available
    if _available is None:
        if not _IMPORTED:
            _available = False
        else:
            _configure()
            try:
                pytesseract.get_tesseract_version()
                _available = True
            except Exception:
                _available = False
    return _available


def use_vision_ocr():
    """True when the vision-LLM path should be preferred over tesseract."""
    return prefer_vision_ocr() or not is_available()


def image_to_string(image, default=""):
    """
    OCR an image, returning `default` rather than raising when OCR is
    unavailable. Drop-in replacement for `pytesseract.image_to_string`.
    """
    if not is_available():
        return default
    try:
        return pytesseract.image_to_string(image)
    except Exception as exc:
        print("[ocr] extraction failed (%s: %s)" % (type(exc).__name__, exc))
        return default


def status():
    """One-line summary for a startup log or diagnostics panel."""
    return ("ocr: pytesseract=%s binary=%s cmd=%r prefer_vision=%s"
            % (_IMPORTED, is_available(), get_tesseract_cmd() or "<PATH>",
               prefer_vision_ocr()))
