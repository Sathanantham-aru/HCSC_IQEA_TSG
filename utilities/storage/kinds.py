"""
The registry of artifact kinds IQEA stores.

One entry per kind of thing the app produces. `folder` is where FileStore puts
it — these are the paths the app already uses, so switching a call site to the
store does not move anyone's files. `default_ext` is applied when a caller
saves a name without one, which is how test case sheets ended up in the database
as bare "All_Test_Cases" and came back out of the artifacts download as an error
string instead of a workbook.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class KindSpec:
    key: str
    folder: str          # relative to the output/ directory
    default_ext: str
    binary: bool
    label: str           # what the Artifacts UI calls it


# Kind keys — import these rather than typing the strings at call sites, so a
# typo is an AttributeError here instead of a silently empty list in the UI.
ACTION            = "action"
ACTION_DESKTOP    = "action_desktop"
SCREENSHOT        = "screenshot"
SCREENSHOT_UPLOAD = "screenshot_upload"
PAGE_FILE         = "page_file"
TEST_FILE         = "test_file"
TEST_CASE         = "test_case"
TEST_CASE_ALL     = "test_case_all"
TEST_DATA         = "test_data"
FEATURE_FILE      = "feature_file"
INPUT_DOC         = "input_doc"
EXEC_REPORT       = "exec_report"


KINDS = {spec.key: spec for spec in [
    KindSpec(ACTION, "Action_collection", ".txt", False,
             "Recorded Action (Web)"),
    KindSpec(ACTION_DESKTOP, os.path.join("Action_collection",
                                          "Action_collection_desktop"),
             ".txt", False, "Recorded Action (Desktop)"),

    # The recorder's existing screenshot folder. The name is a leftover from the
    # first demo site; kept so current local runs keep finding their images.
    KindSpec(SCREENSHOT, os.path.join("Action_collection", "Sauce_demo"),
             ".png", True, "Screenshot (Recorded)"),
    KindSpec(SCREENSHOT_UPLOAD, "Uploaded_screenshots", ".png", True,
             "Screenshot (Uploaded)"),

    KindSpec(PAGE_FILE, "page_file_generator", ".py", False, "Page File"),
    KindSpec(TEST_FILE, "test_file_generator", ".py", False, "Test File"),

    # Both test case kinds share one folder because that is where the app writes
    # them today — individual sheets and the combined workbook sit side by side.
    # They stay separate kinds so the database can tell them apart.
    KindSpec(TEST_CASE, "Test_Cases_collection", ".xlsx", True, "Test Case"),
    KindSpec(TEST_CASE_ALL, "Test_Cases_collection", ".xlsx", True,
             "Test Cases (Combined)"),

    KindSpec(TEST_DATA, "Test_data_generator", ".xlsx", True, "Test Data"),
    KindSpec(FEATURE_FILE, "Feature_file_generator", ".feature", False,
             "BDD Feature File"),
    KindSpec(INPUT_DOC, "Input_documents", "", True, "Uploaded Document"),
    KindSpec(EXEC_REPORT, "Execution_reports", ".html", True,
             "Execution Report"),
]}


_MIME_BY_EXT = {
    ".txt": "text/plain",
    ".py": "text/x-python",
    ".java": "text/x-java-source",
    ".js": "text/javascript",
    ".feature": "text/plain",
    ".json": "application/json",
    ".csv": "text/csv",
    ".html": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def get_spec(kind):
    """The KindSpec for `kind`. Raises rather than guessing, so an unregistered
    kind surfaces at the call site instead of as an empty picker."""
    try:
        return KINDS[kind]
    except KeyError:
        raise ValueError(
            f"Unknown artifact kind '{kind}'. "
            f"Known kinds: {', '.join(sorted(KINDS))}"
        ) from None


def split_name(kind, name):
    """
    Normalise a caller-supplied name into (name_with_ext, ext).

    Callers pass names inconsistently — "login", "login.py", "Add to Cart.xlsx" —
    so every store applies this before touching disk or the database, and the
    stored name always carries its extension.
    """
    spec = get_spec(kind)
    base, ext = os.path.splitext(name)
    if not ext:
        ext = spec.default_ext
        name = f"{base}{ext}"
    return name, ext.lower()


def resolve_candidates(kind, name):
    """
    The names to try, in order, when a caller asks for `name`.

    Callers are inconsistent about extensions — a picker hands back the stored
    "login.py" while generation code asks for a bare "login" — and a kind's
    default extension is only a default: a test case saved as .csv still lives
    under the test_case kind. So a bare name resolves to the default extension
    first, then the bare name itself, and finally any extension on that stem.

    Returns (exact_names, stem_or_None). A stem means "fall back to a prefix
    match on <stem>.*" when none of the exact names hit.
    """
    base, ext = os.path.splitext(name)
    if ext:
        return [name], None

    spec = get_spec(kind)
    candidates = [f"{base}{spec.default_ext}"] if spec.default_ext else []
    candidates.append(base)
    return candidates, base


def mime_for(ext):
    return _MIME_BY_EXT.get((ext or "").lower(), "application/octet-stream")


def all_kinds():
    """Kind keys in a stable order, for building UI selectors."""
    return list(KINDS)
