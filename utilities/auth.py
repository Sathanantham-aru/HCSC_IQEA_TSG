"""
Login for IQEA: who is allowed in, and who they are once they're in.

Before this module, `utilities.identity` could only ever be TOLD who was
using the app — nothing actually asked. `get_update_user()` returned the
database role name, so every artifact in a shared deployment claimed the same
author (see identity.py). This module is what finally supplies a real answer:
a `users` table, a login form gating the whole app, and one call into
`identity.set_current_user()` once someone proves who they are.

Deliberately NOT built here: password reset flows, SSO, MFA. This is an
internal tool for a handful of testers; bcrypt + a login form covers it, and
Easy Auth / Entra can replace this later without touching anything downstream
— identity.py's resolution order already prefers whatever set_current_user()
was given, so swapping the source of that call is the only change it would
take.

First-run bootstrap: if the `users` table is empty, the login screen becomes
a "create the first admin" form instead. Without this, a fresh install has an
admin-gated "create user" page and zero users who can reach it — nobody could
ever log in.
"""
import base64
import os

from sympy import python
import bcrypt
import streamlit as st

from utilities import identity
from utilities.db_utils.models import User
from utilities.db_utils.session import session_scope

_SESSION_KEY = "iqea_auth_user"   # {"username", "display_name", "role"}


# ── Password hashing ─────────────────────────────────────────────────────────

def _hash_password(plain):
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain, hashed):
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/legacy hash — fail closed rather than raising past login.
        return False


# ── Data access ──────────────────────────────────────────────────────────────

def user_count():
    with session_scope() as s:
        return s.query(User).count()


def get_user(username):
    """Return the User row for `username`, or None. Read-only."""
    with session_scope() as s:
        return s.query(User).filter(User.username == username).first()


def _render_login_branding():
    """Render IQEA logo and contact information on the login page."""

    logo_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "utilities",
        "IQEA.ai_logo.png"
    )

    # Hide Streamlit chrome and position the logo.
    st.markdown(
        """
        <style>

        /* ================================
           HIDE STREAMLIT CHROME
           ================================ */

        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        #MainMenu,
        footer {
            display: none !important;
        }

        /* ================================
           PAGE
           ================================ */

        [data-testid="stAppViewContainer"] {
            background-color: #F0F2F6 !important;
        }

        .block-container {
            padding-top: 0 !important;
            padding-bottom: 100px !important;
        }

        /* ================================
           LOGO
           ================================ */

        .iqea-login-logo {
            position: fixed;
            top: 20px;
            left: 28px;
            z-index: 9999;
        }

        .iqea-login-logo img {
            width: 145px;
            height: auto;
            display: block;
        }

        /* ================================
           LOGIN FORM
           ================================ */

        div[data-testid="stForm"] {
            width: 400px !important;
            max-width: calc(100vw - 40px) !important;
            margin: 170px auto 0 auto !important;

            background-color: #FFFFFF !important;
            border-radius: 14px !important;

            padding: 28px 32px 30px 32px !important;

            border-top: 5px solid #F47B20 !important;

            box-shadow:
                0 5px 20px rgba(0, 0, 0, 0.10) !important;
        }

        /* ================================
           LOGIN TITLE
           ================================ */

        .iqea-login-title {
            text-align: center;
            color: #1B2A4A;
            font-size: 25px;
            font-weight: 800;
            margin-bottom: 5px;
        }

        .iqea-login-subtitle {
            text-align: center;
            color: #707070;
            font-size: 13px;
            margin-bottom: 20px;
        }

        /* ================================
           INPUTS
           ================================ */

        div[data-testid="stTextInput"] {
            margin-bottom: 8px !important;
        }

        div[data-testid="stTextInput"] label {
            color: #1B2A4A !important;
            font-size: 14px !important;
            font-weight: 600 !important;
        }

        div[data-testid="stTextInput"] input {
            height: 42px !important;
            background-color: #FFFFFF !important;
            border: 1px solid #C8CDD6 !important;
            border-radius: 7px !important;
            color: #1B2A4A !important;
            font-size: 14px !important;
        }

        div[data-testid="stTextInput"] input:focus {
            border: 2px solid #F47B20 !important;
            box-shadow: 0 0 0 2px rgba(244, 123, 32, 0.12) !important;
        }

        /* ================================
           LOGIN BUTTON
           ================================ */

        div[data-testid="stFormSubmitButton"] button {
            height: 42px !important;
            background-color: #F47B20 !important;
            border: 1px solid #E8650A !important;
            border-radius: 7px !important;
            color: #FFFFFF !important;
            font-size: 15px !important;
            font-weight: 700 !important;
            margin-top: 8px !important;
        }

        div[data-testid="stFormSubmitButton"] button:hover {
            background-color: #E8650A !important;
        }

        /* ================================
           CONTACT
           ================================ */

        .iqea-contact {
            position: fixed;
            bottom: 18px;
            left: 0;
            right: 0;
            width: 100%;
            text-align: center;
            color: #666666;
            font-size: 13px;
            z-index: 9998;
        }

        .iqea-contact a {
            color: #E8650A;
            text-decoration: none;
            font-weight: 700;
        }

        .iqea-contact a:hover {
            color: #F47B20;
            text-decoration: underline;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # Logo
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_base64 = base64.b64encode(f.read()).decode("utf-8")

        st.markdown(
            f"""
            <div class="iqea-login-logo">
                <img src="data:image/png;base64,{logo_base64}">
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Contact section
    st.markdown(
        """
        <p class="iqea-contact">
            <a href="http://localhost:8512/#contact-us">
                Contact Us
            </a>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            Reach us at
            <a href="mailto:sahil.gupta@tigeranalytics.com">
                QE Core Team
            </a>
        </p>
        """,
        unsafe_allow_html=True,
    )



def list_users():
    with session_scope() as s:
        rows = (s.query(User).order_by(User.username).all())
        # Detach plain values — the session that produced these rows is about
        # to close, and callers (the admin table) only need the display data.
        return [
            {"username": u.username, "display_name": u.display_name,
             "role": u.role, "is_active": u.is_active,
             "created_on": u.created_on, "last_login": u.last_login}
            for u in rows
        ]


def create_user(username, password, display_name=None, role="tester",
                created_by=None):
    """
    Create a login account. Raises ValueError on a duplicate username rather
    than letting a raw IntegrityError surface — the admin form turns this into
    a plain message instead of a stack trace.
    """
    username = (username or "").strip()
    if not username:
        raise ValueError("Username cannot be empty.")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    with session_scope() as s:
        if s.query(User).filter(User.username == username).first():
            raise ValueError(f"'{username}' already exists.")
        user = User(
            username=username,
            password_hash=_hash_password(password),
            display_name=(display_name or username).strip(),
            role=role,
            is_active=True,
            created_by=created_by,
        )
        s.add(user)
        s.flush()   # populate user.id before the session closes
        return user.username


def set_user_active(username, is_active):
    with session_scope() as s:
        user = s.query(User).filter(User.username == username).first()
        if user:
            user.is_active = is_active


def authenticate(username, password):
    """
    Check credentials. Returns the user dict on success, None on failure —
    a bad username and a bad password look identical to the caller, which is
    deliberate: telling an attacker "that username doesn't exist" is a free
    account-enumeration oracle for no real benefit to a genuine typo.
    """
    username = (username or "").strip()
    if not username or not password:
        return None

    with session_scope() as s:
        from datetime import datetime
        user = s.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            return None
        if not _verify_password(password, user.password_hash):
            return None
        user.last_login = datetime.utcnow()
        return {"username": user.username, "display_name": user.display_name,
                "role": user.role}


# ── Session state ────────────────────────────────────────────────────────────

def current_auth_user():
    """The logged-in user's record for this session, or None."""
    return st.session_state.get(_SESSION_KEY)


def is_admin():
    user = current_auth_user()
    return bool(user and user.get("role") == "admin")


def _log_in(user_record):
    st.session_state[_SESSION_KEY] = user_record
    # From this point on, every save in the app stamps this username instead
    # of the database role name — the whole point of this module.
    identity.set_current_user(user_record["username"])


def logout():
    st.session_state.pop(_SESSION_KEY, None)
    # Close this thread's DB session and release any open browser so a
    # forgotten "Open Browser" doesn't keep a Grid slot pinned after logout.
    try:
        from utilities.browser_factory import quit_driver
        quit_driver(st.session_state.get("driver"))
    except Exception:
        pass
    st.session_state.pop("driver", None)
    st.session_state.pop("novnc_url", None)


# ── UI ────────────────────────────────────────────────────────────────────────

def _render_first_admin_setup():
    st.title("👋 Welcome to IQEA")
    st.caption("No accounts exist yet — set up the first admin account to get started.")
    with st.form("first_admin_form"):
        username = st.text_input("Admin username")
        display_name = st.text_input("Display name (optional)")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create admin account", type="primary")

    if submitted:
        if password != confirm:
            st.error("⚠️ Passwords do not match.")
            return
        try:
            create_user(username, password, display_name, role="admin",
                        created_by=username)
            st.success(f"✅ Admin account '{username}' created. Please log in below.")
            st.rerun()
        except ValueError as exc:
            st.error(f"⚠️ {exc}")



def _render_login_form():
    _render_login_branding()

    with st.form("login_form"):

        st.markdown(
            """
            <div class="iqea-login-title">
                🔐 IQEA Login
            </div>

            <div class="iqea-login-subtitle">
                Sign in to access the IQEA Platform
            </div>
            """,
            unsafe_allow_html=True,
        )

        username = st.text_input(
            "Username",
            placeholder="Enter your username"
        )

        password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter your password"
        )

        submitted = st.form_submit_button(
            "Log in",
            type="primary",
            use_container_width=True
        )

    if submitted:
        user_record = authenticate(username, password)

        if user_record:
            _log_in(user_record)
            st.rerun()
        else:
            st.error("⚠️ Incorrect username or password.")


def require_login():
    """
    The app-wide gate. Call this first, before anything else renders.

    Returns the logged-in user's record. Calls st.stop() itself when nobody
    is logged in yet, so callers never need their own early-return check.
    """
    user_record = current_auth_user()
    if user_record:
        return user_record

    if user_count() == 0:
        _render_first_admin_setup()
    else:
        _render_login_form()
    st.stop()


# def render_sidebar_identity():
#     """Small who-am-I block + logout button, meant for the sidebar."""
#     user_record = current_auth_user()
#     if not user_record:
#         return
#     label = user_record.get("display_name") or user_record["username"]
#     role = user_record.get("role", "tester")
#     st.caption(f"👤 {label} ({role})")
#     if st.button("Log out", key="_auth_logout_btn"):
#         logout()
#         st.rerun()
# def render_sidebar_identity():
    """Render logged-in user information and logout button."""

    user_record = current_auth_user()

    if not user_record:
        return

    label = user_record.get("display_name") or user_record["username"]
    role = user_record.get("role", "tester")

    st.markdown(
        f"""
        <div class="iqea-user-info">
            <div class="iqea-user-name">👤 {label}</div>
            <div class="iqea-user-role">{role.title()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Normal Streamlit button — same style as other sidebar buttons
    if st.button(
        "🚪 Log out",
        key="_auth_logout_btn",
        use_container_width=True,
    ):
        logout()
        st.rerun()
def render_sidebar_identity():
    """Render logged-in user information and logout button."""

    user_record = current_auth_user()

    if not user_record:
        return

    label = user_record.get("display_name") or user_record["username"]
    role = user_record.get("role", "tester")

    st.caption(f"👤 {label} • {role.title()}")

    if st.button(
        "🚪 Log out",
        key="_auth_logout_btn",
        use_container_width=True
    ):
        logout()
        st.rerun()
def render_manage_users_page():
    """Admin-only page: list accounts, create new ones, deactivate old ones."""
    if not is_admin():
        st.warning("⚠️ Only admins can manage users.")
        return

    st.subheader("👥 Manage users")

    with st.expander("➕ Create a new account", expanded=False):
        with st.form("create_user_form"):
            new_username = st.text_input("Username")
            new_display = st.text_input("Display name (optional)")
            new_role = st.selectbox("Role", ["tester", "admin"])
            new_password = st.text_input("Temporary password", type="password")
            created = st.form_submit_button("Create account", type="primary")

        if created:
            try:
                created_by = current_auth_user()["username"]
                create_user(new_username, new_password, new_display,
                            new_role, created_by=created_by)
                st.success(f"✅ Account '{new_username}' created.")
                st.rerun()
            except ValueError as exc:
                st.error(f"⚠️ {exc}")

    st.markdown("#### Existing accounts")
    for u in list_users():
        cols = st.columns([3, 2, 2, 2, 2])
        cols[0].write(f"**{u['username']}**" + (f" — {u['display_name']}"
                                                  if u["display_name"] else ""))
        cols[1].write(u["role"])
        cols[2].write("🟢 active" if u["is_active"] else "⚪ disabled")
        cols[3].write(u["last_login"].strftime("%Y-%m-%d %H:%M")
                      if u["last_login"] else "never logged in")
        # Never let an admin lock themselves out.
        if u["username"] != current_auth_user()["username"]:
            toggle_label = "Disable" if u["is_active"] else "Enable"
            if cols[4].button(toggle_label, key=f"_toggle_{u['username']}"):
                set_user_active(u["username"], not u["is_active"])
                st.rerun()
