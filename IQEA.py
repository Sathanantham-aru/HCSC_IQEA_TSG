import streamlit as st
import sys
import os

from utilities import auth

st.set_page_config(page_title="IQEA Platform", layout="wide", initial_sidebar_state="expanded")

# Gate the ENTIRE app here, before the sidebar/styling/routing below render.
# require_login() calls st.stop() itself when nobody is authenticated, so
# nothing past this line ever executes for a logged-out visitor.
auth.require_login()
st.markdown("""
<style>

/* =========================================================
   HIDE STREAMLIT CHROME
   ========================================================= */

[data-testid="stSidebarNav"]            { display: none !important; }
[data-testid="stHeader"]                { display: none !important; }
[data-testid="stToolbar"]               { display: none !important; }
[data-testid="stDecoration"]            { display: none !important; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="collapsedControl"]        { display: none !important; }
[data-testid="stSidebarResizeHandle"]   { display: none !important; }
[data-testid="stDeployButton"]          { display: none !important; }

#MainMenu {
    display: none !important;
}

footer {
    display: none !important;
}


/* =========================================================
   APP BACKGROUND
   ========================================================= */

[data-testid="stAppViewContainer"] {
    background-color: #F0F2F6;
    font-family: 'Segoe UI', sans-serif;
}


/* =========================================================
   SIDEBAR - SOLID ORANGE
   ========================================================= */

/*
   IMPORTANT:
   The sidebar itself and all internal scroll containers
   must have the same orange background.
*/

section[data-testid="stSidebar"] {
    width: 300px !important;
    min-width: 300px !important;
    max-width: 300px !important;

    background: #F47B20 !important;

    padding: 0 !important;
    margin: 0 !important;
}

section[data-testid="stSidebar"] > div {
    width: 300px !important;

    background: #F47B20 !important;

    padding: 0 !important;
    margin: 0 !important;
}

section[data-testid="stSidebar"]
[data-testid="stSidebarContent"] {
    background: #F47B20 !important;

    padding: 0 12px 20px 12px !important;
}

section[data-testid="stSidebar"]
[data-testid="stScrollable"] {
    background: #F47B20 !important;
}


/*
   Do not allow nested Streamlit containers to create
   a white background while scrolling.
*/

section[data-testid="stSidebar"]
[data-testid="stVerticalBlock"] {
    background: transparent !important;
}


/* =========================================================
   SIDEBAR LOGO AREA
   ========================================================= */

.iqea-sidebar-logo {
    width: 100%;

    box-sizing: border-box;

    background: #FFFFFF;

    border-radius: 0 0 8px 8px;

    padding: 14px 10px;

    text-align: center;

    margin: 0;
}

.iqea-sidebar-logo img {
    width: 155px;

    max-width: 100%;

    height: auto;

    display: block;

    margin: 0 auto;
}


/* =========================================================
   SIDEBAR TITLE
   ========================================================= */

section[data-testid="stSidebar"] h3 {
    color: #FFFFFF !important;

    font-size: 19px !important;

    font-weight: 800 !important;

    text-align: center !important;

    letter-spacing: 0.3px !important;

    margin-top: 6px !important;

    margin-bottom: 8px !important;
}


/* =========================================================
   SIDEBAR DIVIDER
   ========================================================= */

.sidebar-divider {
    border: 0 !important;

    border-top: 1px solid rgba(255,255,255,0.45) !important;

    margin: 8px 0 14px 0 !important;
}


/* =========================================================
   SIDEBAR RADIO NAVIGATION
   ========================================================= */

section[data-testid="stSidebar"] .stRadio {
    width: 100% !important;

    margin: 0 !important;

    padding: 0 !important;
}

section[data-testid="stSidebar"] .stRadio > div {
    width: 100% !important;

    gap: 0 !important;
}


/* Individual navigation item */

section[data-testid="stSidebar"]
.stRadio
div[role="radiogroup"]
label {

    display: flex !important;

    flex-direction: row !important;

    align-items: center !important;

    width: 100% !important;

    box-sizing: border-box !important;

    min-height: 43px !important;

    padding: 9px 12px !important;

    margin: 0 0 7px 0 !important;

    gap: 10px !important;

    border-radius: 8px !important;

    border-left: 4px solid transparent !important;

    background: transparent !important;

    cursor: pointer !important;

    transition:
        background-color 0.15s ease,
        border-color 0.15s ease !important;
}


/* Radio circle */

section[data-testid="stSidebar"]
.stRadio
div[role="radiogroup"]
label
div:first-child {

    margin-top: 0 !important;

    margin-bottom: 0 !important;

    align-self: center !important;

    flex-shrink: 0 !important;
}


/* Navigation text */

section[data-testid="stSidebar"]
.stRadio
div[role="radiogroup"]
label p {

    margin: 0 !important;

    padding: 0 !important;

    color: #FFFFFF !important;

    font-size: 16px !important;

    font-weight: 700 !important;

    line-height: 1.2 !important;

    white-space: nowrap !important;

    align-self: center !important;
}


/* =========================================================
   NAVIGATION HOVER
   ========================================================= */

section[data-testid="stSidebar"]
.stRadio
div[role="radiogroup"]
label:hover {

    background-color: rgba(255,255,255,0.16) !important;

    border-left-color: rgba(255,255,255,0.70) !important;
}


/* =========================================================
   SELECTED NAVIGATION
   ========================================================= */

section[data-testid="stSidebar"]
.stRadio
div[role="radiogroup"]
label:has(input:checked) {

    background-color: #FFFFFF !important;

    border-left: 4px solid #E8650A !important;

    border-radius: 8px !important;
}


/* Selected navigation text */

section[data-testid="stSidebar"]
.stRadio
div[role="radiogroup"]
label:has(input:checked) p {

    color: #E8650A !important;

    font-weight: 800 !important;
}


/* =========================================================
   USER INFORMATION
   ========================================================= */

section[data-testid="stSidebar"]
[data-testid="stCaptionContainer"] {

    padding: 4px 2px !important;

    margin: 4px 0 8px 0 !important;
}

section[data-testid="stSidebar"]
[data-testid="stCaptionContainer"] p {

    color: #FFFFFF !important;

    font-size: 13px !important;

    font-weight: 600 !important;

    margin: 0 !important;
}


/* =========================================================
   LOGOUT BUTTON
   ========================================================= */

section[data-testid="stSidebar"] .stButton {
    width: 100% !important;

    margin: 0 !important;
}

section[data-testid="stSidebar"] .stButton > button {

    width: 100% !important;

    min-height: 43px !important;

    box-sizing: border-box !important;

    background-color: transparent !important;

    color: #FFFFFF !important;

    border: 1px solid rgba(255,255,255,0.45) !important;

    border-radius: 8px !important;

    font-size: 15px !important;

    font-weight: 700 !important;

    text-align: left !important;

    padding: 9px 12px !important;

    box-shadow: none !important;
}


/* Logout hover */

section[data-testid="stSidebar"]
.stButton > button:hover {

    background-color: rgba(255,255,255,0.16) !important;

    border-color: rgba(255,255,255,0.75) !important;

    color: #FFFFFF !important;
}


/* Logout focus */

section[data-testid="stSidebar"]
.stButton > button:focus {

    background-color: rgba(255,255,255,0.20) !important;

    border-color: rgba(255,255,255,0.75) !important;

    color: #FFFFFF !important;

    box-shadow: none !important;
}


/* =========================================================
   MAIN PAGE LAYOUT
   ========================================================= */

.block-container {
    padding: 0rem 2rem 2rem 2rem !important;

    max-width: 100% !important;
}

[data-testid="stMainBlockContainer"] {
    max-width: 100% !important;
}

[data-testid="column"] {
    width: 100% !important;

    min-width: 0 !important;

    flex: 1 1 0% !important;
}


/* =========================================================
   TEXT INPUTS & TEXT AREAS
   ========================================================= */

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {

    background-color: #FFFFFF !important;

    border: 2px solid #C8CDD6 !important;

    border-radius: 8px !important;

    color: #1B2A4A !important;

    font-size: 15px !important;

    padding: 8px 12px !important;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {

    border: 2px solid #F47B20 !important;

    outline: none !important;

    box-shadow:
        0 0 0 3px rgba(244,123,32,0.15) !important;
}

[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {

    color: #A0A8B4 !important;

    font-weight: 400 !important;
}


/* =========================================================
   SELECTBOX & MULTISELECT
   ========================================================= */

[data-testid="stSelectbox"] > div > div,
[data-testid="stMultiSelect"] > div > div {

    background-color: #FFFFFF !important;

    border: 2px solid #C8CDD6 !important;

    border-radius: 8px !important;
}

[data-testid="stSelectbox"] > div > div:focus-within,
[data-testid="stMultiSelect"] > div > div:focus-within {

    border: 2px solid #F47B20 !important;

    box-shadow:
        0 0 0 3px rgba(244,123,32,0.15) !important;
}

[data-testid="stSelectbox"] span,
[data-testid="stMultiSelect"] span {

    color: #1B2A4A !important;

    font-weight: 500 !important;
}


/* =========================================================
   MULTISELECT CHIPS
   ========================================================= */

[data-testid="stMultiSelect"]
[data-baseweb="tag"] {

    background-color: #F47B20 !important;

    border: 1px solid #E8650A !important;

    border-radius: 6px !important;
}

[data-testid="stMultiSelect"]
[data-baseweb="tag"],
[data-testid="stMultiSelect"]
[data-baseweb="tag"] span,
[data-testid="stMultiSelect"]
[data-baseweb="tag"] div {

    color: #FFFFFF !important;

    font-weight: 600 !important;
}


/* Chip remove icon */

[data-testid="stMultiSelect"]
[data-baseweb="tag"] svg {

    fill: #FFFFFF !important;

    color: #FFFFFF !important;
}

[data-testid="stMultiSelect"]
[data-baseweb="tag"]
span[role="presentation"]:hover {

    background-color: rgba(0,0,0,0.18) !important;

    border-radius: 4px !important;
}


/* =========================================================
   DROPDOWN MENU
   ========================================================= */

[data-baseweb="popover"] ul {

    background-color: #FFFFFF !important;

    border: 1px solid #C8CDD6 !important;

    border-radius: 8px !important;
}

[data-baseweb="popover"] li {

    color: #1B2A4A !important;

    font-size: 15px !important;
}

[data-baseweb="popover"] li:hover {

    background-color: #FFF0E6 !important;

    color: #F47B20 !important;
}


/* =========================================================
   HOME PAGE STYLES
   ========================================================= */

.feature-card {

    background: white;

    border-radius: 14px;

    border-top: 5px solid #F47B20;

    padding: 28px 24px;

    box-shadow: 0 4px 16px rgba(0,0,0,0.08);

    height: 100%;
}

.feature-card-title {

    font-size: 22px;

    font-weight: 800;

    color: #F47B20;

    margin-bottom: 16px;

    display: flex;

    align-items: center;

    gap: 8px;
}

.feature-card li {

    font-size: 15px;

    line-height: 1.9;

    color: #2C2C2C;

    margin-bottom: 2px;
}

.feature-card ul {

    padding-left: 18px;

    margin: 0;
}

.feature-card li::marker {

    color: #F47B20;
}

</style>
""", unsafe_allow_html=True)
# st.markdown("""
# <style>

# /* ===== HIDE STREAMLIT CHROME ===== */
# [data-testid="stSidebarNav"]            { display: none !important; }
# [data-testid="stHeader"]                { display: none !important; }
# [data-testid="stToolbar"]               { display: none !important; }
# [data-testid="stDecoration"]            { display: none !important; }
# [data-testid="stSidebarCollapseButton"] { display: none !important; }
# [data-testid="collapsedControl"]        { display: none !important; }
# [data-testid="stSidebarResizeHandle"]   { display: none !important; }
# #MainMenu                               { display: none !important; }
# footer                                  { display: none !important; }

# /* ===== APP BACKGROUND ===== */
# [data-testid="stAppViewContainer"] {
#     background-color: #F0F2F6;
#     font-family: 'Segoe UI', sans-serif;
# }

# # /* ===== SIDEBAR BASE ===== */
# # [data-testid="stSidebar"] {
# #     background: linear-gradient(180deg, #E8650A 0%, #F47B20 60%, #F99245 100%);
# #     padding-top: 0px;
# # }

# # /* All sidebar text → white */
# # [data-testid="stSidebar"] * {
# #     color: white !important;
# #     font-weight: 700 !important;
# # }
# /* ===== SIDEBAR BASE ===== */
# [data-testid="stSidebar"] {
#     /* REMOVE the old gradient here — it's now handled inline above */
#     padding-top: 0px;
# }

# /* Keep all sidebar text white EXCEPT the title zone */
# [data-testid="stSidebar"] * {
#     color: white !important;
#     font-weight: 700 !important;
# }

# /* Override: title text must be black (white zone) */
# [data-testid="stSidebar"] h3 {
#     color: #000000 !important;;
# }
# /* ===== SIDEBAR SECTION HEADER ===== */
# [data-testid="stSidebar"] h3 {
#     font-size: 22px !important;
#     font-weight: 800 !important;
#     color: #000000 !important;;
#     text-align: center !important;
#     letter-spacing: 0.5px !important;
# }

# /* ===== NAV RADIO LABELS ===== */
# [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label {
#     display: flex !important;
#     flex-direction: row !important;
#     align-items: center !important;
#     gap: 12px !important;
#     padding: 14px 18px !important;
#     border-radius: 10px !important;
#     margin-bottom: 8px !important;
#     cursor: pointer !important;
#     border-left: 4px solid transparent !important;
#     transition: background 0.2s !important;
# }

# [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label div:first-child {
#     margin-top: 0 !important;
#     margin-bottom: 0 !important;
#     align-self: center !important;
#     flex-shrink: 0 !important;
# }

# [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label p {
#     margin: 0 !important;
#     padding: 0 !important;
#     font-size: 20px !important;
#     font-weight: 700 !important;
#     color: white !important;
#     line-height: 1.2 !important;
#     align-self: center !important;
# }

# /* ===== SELECTED NAV ITEM ===== */
# [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) {
#     background-color: white !important;
#     border-left: 4px solid #E8650A !important;
#     border-radius: 10px !important;
# }

# [data-testid="stSidebar"] .stRadio div[role="radiogroup"] label:has(input:checked) p {
#     color: #E8650A !important;
#     font-weight: 800 !important;
#     font-size: 20px !important;
# }

# /* ===== LAYOUT ===== */
# .block-container {
#     padding: 0rem 2rem 2rem 2rem !important;
#     max-width: 100% !important;
# }

# [data-testid="stMainBlockContainer"] {
#     max-width: 100% !important;
# }

# [data-testid="column"] {
#     width: 100% !important;
#     min-width: 0 !important;
#     flex: 1 1 0% !important;
# }

# /* ===== TEXT INPUTS & TEXT AREAS ===== */
# [data-testid="stTextInput"] input,
# [data-testid="stTextArea"] textarea {
#     background-color: #ffffff !important;
#     border: 2px solid #C8CDD6 !important;
#     border-radius: 8px !important;
#     color: #1B2A4A !important;
#     font-size: 15px !important;
#     padding: 8px 12px !important;
# }

# [data-testid="stTextInput"] input:focus,
# [data-testid="stTextArea"] textarea:focus {
#     border: 2px solid #F47B20 !important;
#     outline: none !important;
#     box-shadow: 0 0 0 3px rgba(244, 123, 32, 0.15) !important;
# }

# [data-testid="stTextInput"] input::placeholder,
# [data-testid="stTextArea"] textarea::placeholder {
#     color: #A0A8B4 !important;
#     font-weight: 400 !important;
# }

# /* ===== SELECTBOX & MULTISELECT ===== */
# [data-testid="stSelectbox"] > div > div,
# [data-testid="stMultiSelect"] > div > div {
#     background-color: #ffffff !important;
#     border: 2px solid #C8CDD6 !important;
#     border-radius: 8px !important;
# }

# [data-testid="stSelectbox"] > div > div:focus-within,
# [data-testid="stMultiSelect"] > div > div:focus-within {
#     border: 2px solid #F47B20 !important;
#     box-shadow: 0 0 0 3px rgba(244, 123, 32, 0.15) !important;
# }

# [data-testid="stSelectbox"] span,
# [data-testid="stMultiSelect"] span {
#     color: #1B2A4A !important;
#     font-weight: 500 !important;
# }

# /* Selected multiselect chips — Streamlit's default is a washed-out purple that
#    reads as "disabled"; use the platform orange so the picked values stand out. */
# [data-testid="stMultiSelect"] [data-baseweb="tag"] {
#     background-color: #F47B20 !important;
#     border: 1px solid #E8650A !important;
#     border-radius: 6px !important;
# }

# [data-testid="stMultiSelect"] [data-baseweb="tag"],
# [data-testid="stMultiSelect"] [data-baseweb="tag"] span,
# [data-testid="stMultiSelect"] [data-baseweb="tag"] div {
#     color: #ffffff !important;
#     font-weight: 600 !important;
# }

# /* the chip's "×" remove icon */
# [data-testid="stMultiSelect"] [data-baseweb="tag"] svg {
#     fill: #ffffff !important;
#     color: #ffffff !important;
# }

# [data-testid="stMultiSelect"] [data-baseweb="tag"] span[role="presentation"]:hover {
#     background-color: rgba(0, 0, 0, 0.18) !important;
#     border-radius: 4px !important;
# }

# /* dropdown menu list */
# [data-baseweb="popover"] ul {
#     background-color: #ffffff !important;
#     border: 1px solid #C8CDD6 !important;
#     border-radius: 8px !important;
# }

# [data-baseweb="popover"] li {
#     color: #1B2A4A !important;
#     font-size: 15px !important;
# }

# [data-baseweb="popover"] li:hover {
#     background-color: #FFF0E6 !important;
#     color: #F47B20 !important;
# }

# /* ===== HOME PAGE STYLES ===== */
# .feature-card {
#     background: white;
#     border-radius: 14px;
#     border-top: 5px solid #F47B20;
#     padding: 28px 24px;
#     box-shadow: 0 4px 16px rgba(0,0,0,0.08);
#     height: 100%;
# }
# .feature-card-title {
#     font-size: 22px;
#     font-weight: 800;
#     color: #F47B20;
#     margin-bottom: 16px;
#     display: flex;
#     align-items: center;
#     gap: 8px;
# }
# .feature-card li {
#     font-size: 15px;
#     line-height: 1.9;
#     color: #2C2C2C;
#     margin-bottom: 2px;
# }
# .feature-card ul {
#     padding-left: 18px;
#     margin: 0;
# }
# .feature-card li::marker {
#     color: #F47B20;
# }

# </style>
# """, unsafe_allow_html=True)

# ==============================
# BASE PATH
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_page(file_path):
    """Run a page file in-place without changing the process CWD."""
    page_dir = os.path.dirname(file_path)
    if page_dir not in sys.path:
        sys.path.insert(0, page_dir)
    # NOTE: We deliberately do NOT evict cached submodules from sys.modules here.
    # An earlier version evicted every module whose __file__ lived under the
    # project root to hot-reload edits to utils/*.py without a restart. That was
    # harmful:
    #   * The virtualenv (.venv) sits inside the project root, so it also evicted
    #     Streamlit's own modules -> re-import mid-run with fresh ContextVars ->
    #     "FragmentThreadState not initialized" and pages failing to load.
    #   * Even limited to the app's own modules, it forced heavy re-imports of
    #     desktop.recorder etc. (native keyboard/mouse hooks, pywinauto) on every
    #     navigation, which intermittently hung or crashed the server.
    # Modules are now imported once and cached. If you edit utils/*.py during
    # development, restart the Streamlit server to pick up the changes.
    with open(file_path, "r", encoding="utf-8") as f:
        exec(f.read(), {"__file__": file_path})

# ==============================
# SIDEBAR
# ==============================
# with st.sidebar:
#     img_base64 = __import__('base64').b64encode(
#         open("utilities/IQEA.ai_logo.png", "rb").read()
#     ).decode()

#     st.markdown(f"""
#     <style>
#     [data-testid="stSidebar"] > div:first-child,
#     [data-testid="stSidebarContent"],
#     section[data-testid="stSidebar"] > div,
#     [data-testid="stSidebar"] div:first-child {{
#         padding-top: 0 !important;
#         margin-top: 0 !important;
#     }}
#     </style>
#     <div style="background-color:white; padding:16px 12px 10px 12px; text-align:center;
#                 border-bottom: 3px solid rgba(255,255,255,0.4);">
#         <img src="data:image/png;base64,{img_base64}"
#              style="width:155px; display:block; margin:0 auto;" />
#     </div>
#     """, unsafe_allow_html=True)

#     st.markdown("<br>", unsafe_allow_html=True)
#     st.markdown("### QE Agentic E2E Solutions")
#     st.markdown("<hr style='border:1px solid rgba(255,255,255,0.4); margin:8px 0 16px 0;'>",
#                 unsafe_allow_html=True)

#     page = st.radio(
#         "Go to",
#         ["🏠  Home", "🧠  IQEA", "🔁  Self Healing", "🔗  API Validator"],
#         index=0,
#         label_visibility="collapsed"
#     )
# Replace the existing sidebar logo + markdown block with this:

# with st.sidebar:
#     img_base64 = __import__('base64').b64encode(
#         open("utilities/IQEA.ai_logo.png", "rb").read()
#     ).decode()

#     st.markdown(f"""
#     <style>
#     /* Remove all top padding from sidebar */
#     [data-testid="stSidebar"] > div:first-child,
#     [data-testid="stSidebarContent"],
#     section[data-testid="stSidebar"] > div,
#     [data-testid="stSidebar"] div:first-child {{
#         padding-top: 0 !important;
#         margin-top: 0 !important;
#     }}

#     /* Override sidebar gradient — start white, transition to orange */
#     [data-testid="stSidebar"] {{
#         background: linear-gradient(
#             180deg,
#             #FFFFFF 0%,
#             #FFFFFF 46%,    /* ← increase this until divider is in white zone */
#             #E8650A 46%,    /* ← match this to the same value */
#             #F47B20 60%,
#             #F99245 100%
#         ) !important;
#     }}

#     /* Title text in the white zone must be black */
#     # [data-testid="stSidebar"] h3 {{
#     #     color: #1B2A4A !important;
#     #     font-size: 20px !important;
#     #     font-weight: 800 !important;
#     #     text-align: center !important;
#     #     letter-spacing: 0.5px !important;
#     # }}

#     # /* Divider line below title — dark instead of white */
#     # .sidebar-divider {{
#     #     border: 1px solid #D0D0D0;
#     #     margin: 8px 0 16px 0;
#     # }}
#     [data-testid="stSidebar"] h3 {{
#         color: #000000 !important;;
#         font-size: 20px !important;
#         font-weight: 800 !important;
#         text-align: center !important;
#     }}

#     /* Divider line — dark grey to match white background */
#     .sidebar-divider {{
#         border: 1px solid #D0D0D0 !important;
#         margin: 8px 0 16px 0;
#     }}

#     /* Prevent the global white override from recoloring the title */
#     [data-testid="stSidebar"] h3 {{
#         color: #000000 !important;
#     }}            
#     </style>

#     <div style="
#         background-color: white;
#         padding: 20px 12px 16px 12px;
#         text-align: center;
#     ">
#         <img src="data:image/png;base64,{img_base64}"
#             style="width: 155px; display: block; margin: 0 auto;" />
#     </div>
#     """, unsafe_allow_html=True)

#     st.markdown("<br>", unsafe_allow_html=True)
#     st.markdown("### QE Agentic E2E Solutions")
#     st.markdown("<hr class='sidebar-divider'>", unsafe_allow_html=True)

#     nav_options = ["🏠  Home", "💬  Chat Agent", "🧠  IQEA", "🔁  Self Healing",
#                    "🔗  API Validator", "📊  PBI Validator"]
#     if auth.is_admin():
#         nav_options.append("👥  Manage Users")

#     page = st.radio(
#         "Go to",
#         nav_options,
#         index=0,
#         label_visibility="collapsed"
#     )

#     st.markdown("<hr class='sidebar-divider'>", unsafe_allow_html=True)
#     auth.render_sidebar_identity()
with st.sidebar:

    # =========================================================
    # SIDEBAR LOGO
    # =========================================================

    img_base64 = __import__("base64").b64encode(
        open("utilities/IQEA.ai_logo.png", "rb").read()
    ).decode()

    st.markdown(
        f"""
        <div class="iqea-sidebar-logo">
            <img
                src="data:image/png;base64,{img_base64}"
                alt="IQEA"
            />
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Small spacing between logo and navigation
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # =========================================================
    # SIDEBAR TITLE
    # =========================================================

    st.markdown("### QE Agentic E2E Solutions")

    st.markdown(
        "<hr class='sidebar-divider'>",
        unsafe_allow_html=True
    )

    # =========================================================
    # NAVIGATION
    # =========================================================

    nav_options = [
        "🏠  Home",
        "💬  Chat Agent",
        "🧠  IQEA",
    ]

    if auth.is_admin():
        nav_options.append("👥  Manage Users")

    page = st.radio(
        "Go to",
        nav_options,
        index=0,
        label_visibility="collapsed",
    )

    # =========================================================
    # USER / LOGOUT
    # =========================================================

    st.markdown(
        "<hr class='sidebar-divider'>",
        unsafe_allow_html=True
    )

    auth.render_sidebar_identity()
# ==============================
# PAGE ROUTING
# ==============================
if page == "🏠  Home":
    st.markdown("""
    <div style="padding: 28px 0 24px 0;">
        <div style="font-size:34px; font-weight:900; color:#1B2A4A; margin-bottom:8px;">
            🤖 TigerQE AI Platform — iQEA (Intelligent QE Assistant)
        </div>
        <div style="font-size:17px; color:#666; font-weight:500;">
            AI-powered end-to-end test automation — from recording to execution, all in one place.
        </div>
        <hr style="border:2px solid #F47B20; width:80px; margin:16px 0 0 0;">
    </div>
    """, unsafe_allow_html=True)

    # col1, col2, col3 = st.columns(3, gap="large")
    # with col1:
    
    st.markdown("""
    <div class="feature-card">
        <div class="feature-card-title">Key Features</div>
        <div class="feature-table-wrap">
        <table class="feature-table">
            <thead>
                <tr>
                    <th class="col-num">#</th>
                    <th class="col-feat">Feature</th>
                    <th class="col-desc">What it does</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="col-num">1</td>
                    <td class="col-feat"><span class="feat-icon">🎯</span><strong>Test Generation from User Journey</strong></td>
                    <td class="col-desc">Auto-generate test cases by recording real user workflows on web &amp; desktop, no scripting needed</td>
                </tr>
                <tr>
                    <td class="col-num">2</td>
                    <td class="col-feat"><span class="feat-icon">🔗</span><strong>Seamless Integration</strong></td>
                    <td class="col-desc">Native sync with test management tools (Jira, Azure Boards) and source code version controllers (Git)</td>
                </tr>
                <tr>
                    <td class="col-num">3</td>
                    <td class="col-feat"><span class="feat-icon">🔧</span><strong>Low-Effort Test Maintenance (Self-Healing)</strong></td>
                    <td class="col-desc">AI automatically detects and repairs broken locators and test steps after UI changes</td>
                </tr>
                <tr>
                    <td class="col-num">4</td>
                    <td class="col-feat"><span class="feat-icon">🤖</span><strong>AI-Augmented XPath &amp; Automation</strong></td>
                    <td class="col-desc">Intelligent locator generation and maintenance with full Page Object Model support</td>
                </tr>
                <tr>
                    <td class="col-num">5</td>
                    <td class="col-feat"><span class="feat-icon">⚡</span><strong>2× Faster QE Cycle</strong></td>
                    <td class="col-desc">Dramatically reduce time-to-test with one-click script generation in Java or Python</td>
                </tr>
                <tr>
                    <td class="col-num">6</td>
                    <td class="col-feat"><span class="feat-icon">🛠️</span><strong>Quick Customization</strong></td>
                    <td class="col-desc">Flexible templates and configurations adapt to your team's standards and tech stack instantly</td>
                </tr>
                <tr>
                    <td class="col-num">7</td>
                    <td class="col-feat"><span class="feat-icon">📋</span><strong>Regulatory Compliance &amp; Adherence Reporting</strong></td>
                    <td class="col-desc">Built-in compliance-ready reports for standards like GDPR, HIPAA &amp; ISO</td>
                </tr>
                <tr>
                    <td class="col-num">8</td>
                    <td class="col-feat"><span class="feat-icon">🔍</span><strong>Smarter Regression — Scan &amp; Fix Changes</strong></td>
                    <td class="col-desc">Automatically identifies impacted test cases when code changes and flags fixes needed</td>
                </tr>
                <tr>
                    <td class="col-num">9</td>
                    <td class="col-feat"><span class="feat-icon">🚀</span><strong>Faster Regression with AIR</strong></td>
                    <td class="col-desc">Artificial Impact Reviewer prioritizes and runs only the tests affected by recent changes</td>
                </tr>
                <tr>
                    <td class="col-num">10</td>
                    <td class="col-feat"><span class="feat-icon">📊</span><strong>Built-in Performance Benchmarking</strong></td>
                    <td class="col-desc">Measure and track response times across all endpoints without leaving the platform</td>
                </tr>
                <tr>
                    <td class="col-num">11</td>
                    <td class="col-feat"><span class="feat-icon">📄</span><strong>Seamless Swagger Integration</strong></td>
                    <td class="col-desc">Auto-generate API test cases directly from Swagger/OpenAPI specs with zero manual effort</td>
                </tr>
            </tbody>
        </table>
        </div>
    </div>
    <style>
    .feature-card {
        background: #ffffff;
        border: 2px solid #FF6B00;
        border-radius: 12px;
        padding: 24px 28px;
        height: 100%;
        box-shadow: 0 4px 20px rgba(255, 107, 0, 0.15);
    }
    .feature-card-title {
        font-size: 1.4rem;
        font-weight: 700;
        color: #FF6B00;
        margin-bottom: 14px;
        letter-spacing: 0.5px;
    }
    /* narrow screens scroll the table instead of squashing the description */
    .feature-table-wrap {
        overflow-x: auto;
    }
    .feature-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95rem;
        min-width: 640px;
    }
    .feature-table thead th {
        background: #FF6B00;
        color: #ffffff;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        font-size: 0.78rem;
        text-align: left;
        padding: 10px 14px;
        border: 1px solid #FF6B00;
    }
    .feature-table td {
        padding: 11px 14px;
        border: 1px solid #F3D6C0;
        vertical-align: top;
        color: #1B2A4A;
        line-height: 1.5;
    }
    .feature-table tbody tr:nth-child(even) td {
        background: #FFF7F1;
    }
    .feature-table tbody tr:hover td {
        background: #FFEBDD;
    }
    .feature-table .col-num {
        width: 48px;
        text-align: center;
        font-weight: 700;
        color: #FF6B00;
    }
    .feature-table .col-feat {
        width: 32%;
        white-space: normal;
    }
    .feature-table .col-feat strong {
        color: #FF6B00;
    }
    .feat-icon {
        font-size: 1rem;
        margin-right: 8px;
    }
    </style>
    """, unsafe_allow_html=True)
    

elif page == "💬  Chat Agent":
    run_page(os.path.join(BASE_DIR, "chat_agent.py"))

elif page == "🧠  IQEA":
    run_page(os.path.join(BASE_DIR, "action_new_xpath_subway_TMT.py"))

elif page == "👥  Manage Users":
    auth.render_manage_users_page()
