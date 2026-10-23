"""
Who to record as `created_by` on stored artifacts.

Fourteen call sites still pass the literal "sathanantham", and before this
module existed get_update_user() returned the database role name, so every row
claimed the same author. That is harmless on one laptop and wrong the moment
the Azure deployment has more than one person using it.

utilities.auth now supplies a real identity: its login form calls
set_current_user() once someone authenticates against the `users` table, so
the fallbacks below only apply to threads and scripts that run outside a
login (the recorder's monitor threads, one-off CLI scripts).

Resolution order:
  1. whatever set_current_user() was last given for this Streamlit session
     (this is where utilities.auth's login feeds in)
  2. the IQEA_USER environment variable (per-container, useful in Azure)
  3. DB_UPDATE_USER from the active [DATABASE_*] section of settings.ini
  4. DB_USER from that same section
"""

import os
import threading

from config.settings_reader import get_db_config, get_update_user

_SESSION_KEY = "iqea_current_user"

# Fallback for threads and scripts with no Streamlit session (the recorder
# monitor threads save screenshots from outside the script run).
#
# threading.local(), NOT a bare module global. A real login means this
# process now serves several DIFFERENT people at once, each with their own
# recorder threads — a plain global would let tester B's set_current_user()
# call overwrite the value tester A's monitor thread reads next, stamping
# A's screenshots as B. A thread-local avoids that cross-contamination, at
# the cost that a freshly spawned recorder thread starts with none set (falls
# through to the env/DB fallbacks below) until something calls
# set_current_user() again from inside that thread. Passing the username into
# the thread at creation time would recover full attribution there too; that
# is recorder-side work, not this module's.
_local = threading.local()


def _has_script_run_context():
    """Whether we are inside a Streamlit script run.

    Touching st.session_state without one logs a "missing ScriptRunContext"
    warning per access. The recorder saves screenshots from worker threads, so
    without this check every screenshot would put two warnings in the log — the
    kind of per-poll noise settings.ini's debug_logs comment exists to avoid.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        # suppress_warning, because asking the question is not itself a mistake
        # — outside a script run the answer is simply "no".
        return get_script_run_ctx(suppress_warning=True) is not None
    except TypeError:
        # Older Streamlit without the keyword.
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def _from_streamlit():
    if not _has_script_run_context():
        return None
    try:
        import streamlit as st
        return st.session_state.get(_SESSION_KEY)
    except Exception:
        return None


def set_current_user(username):
    """Record who is driving this session/thread. Safe to call before auth
    exists — the sidebar or a login screen can set it, and everything else
    picks it up."""
    username = (username or "").strip()
    if not username:
        return

    _local.process_user = username
    if _has_script_run_context():
        try:
            import streamlit as st
            st.session_state[_SESSION_KEY] = username
        except Exception:
            pass


def current_user():
    """The name to stamp on anything saved now. Never returns empty."""
    for candidate in (
        _from_streamlit(),
        getattr(_local, "process_user", None),
        os.environ.get("IQEA_USER"),
        # Resolved against whichever [DATABASE_*] section this environment uses.
        get_update_user(),
        get_db_config()["user"],
    ):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return "unknown"
