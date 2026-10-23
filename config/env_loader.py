"""
Execution-aware replacement for `dotenv.load_dotenv`.

Call sites import `load_dotenv` from here instead of from `dotenv` directly:

    from config.env_loader import load_dotenv
    load_dotenv()                 # unchanged locally, no-op under azure

Why this exists
---------------
Locally, secrets and endpoints come from a `.env` file at the repo root. In
Azure they come from App Service application settings, which land in
`os.environ` before Python starts — so there is nothing to load.

The reason this matters beyond tidiness: several call sites use
`load_dotenv(override=True)` (see utilities/Utilities_Xpath.py), and
`override=True` makes the FILE win over the real environment. If a `.env` ever
reaches the container image, it would silently overwrite the Azure App Service
settings — the portal would show the right values while the app used stale
local ones. Short-circuiting under azure removes that failure mode entirely.

`.dockerignore` excludes `.env*` from the image as a second line of defence;
this shim is the first.

The signature is fully pass-through, so existing calls keep working unchanged:
`load_dotenv()`, `load_dotenv(override=True)` and
`load_dotenv("/explicit/path/.env")` all behave as they do today when
execution_type=local.
"""

from dotenv import load_dotenv as _dotenv_load_dotenv

from config.settings_reader import is_azure

# Log the skip once rather than on every one of the ~26 call sites.
_skip_logged = False


def load_dotenv(*args, **kwargs):
    """
    Load the local `.env` when execution_type=local; do nothing under azure.

    Returns whatever python-dotenv returns locally (True/False), and False when
    skipped, matching python-dotenv's "nothing was loaded" result.
    """
    global _skip_logged

    if is_azure():
        if not _skip_logged:
            print("[env] execution_type=azure -> skipping .env; "
                  "using process environment (Azure App Service settings)")
            _skip_logged = True
        return False

    return _dotenv_load_dotenv(*args, **kwargs)
