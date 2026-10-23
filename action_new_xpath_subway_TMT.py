import os
import io
import base64
import threading
from PIL import Image
import pandas as pd
import streamlit as st

# Internal utilities and configurations
import utilities.Utilities_Xpath as utils
import utilities.utils_action as action_utils
import utilities.db_utils.handler as db_handler
import utilities.TMT_Connection.Test_management_tool_utils as tmt_utils
import utilities.ocr as ocr
import utilities.screenshot_view as screenshot_view
from utilities.artifact_export import render_artifact_export
from utilities.live_view import auto_open_live_browser, mark_opened, render_live_browser_panel
from utilities.identity import current_user
from utilities.capabilities import desktop_unavailable_reason, is_desktop_recording_available, load_desktop_modules
from utilities.browser_factory import get_driver, is_azure, normalize_url, quit_driver, safe_maximize, wait_until_page_ready, diagnose_browser_session, get_browser_session_info
from selenium.webdriver.support.wait import WebDriverWait
from config.env_loader import load_dotenv
from config.settings_reader import get_source, get_model, get_xpath_key

load_dotenv()

# Settings
source = get_source()
model_type = get_model()
xpath_tag_keys = get_xpath_key()

# Directory Setup
current_path = os.getcwd()
input_folder = os.path.join(current_path, "Input")
output_folder = os.path.join(current_path, "output")
Action_collection = os.path.join(output_folder, "Action_collection")
Action_collection_desktop = os.path.join(Action_collection, "Action_collection_desktop")
Page_collection = os.path.join(output_folder, "page_file_generator")
Test_case_collection = os.path.join(output_folder, "Test_Cases_collection")
Test_file_generator = os.path.join(output_folder, "test_file_generator")
feature_file_collection = os.path.join(output_folder, "Feature_file_generator")
test_data_folder = os.path.join(output_folder, "Test_data_generator")
page_screenshot_folder = os.path.join(Action_collection, "Sauce_demo")

for path in [Page_collection, Test_case_collection, Action_collection, feature_file_collection,
             test_data_folder, Action_collection_desktop, page_screenshot_folder, Test_file_generator]:
    os.makedirs(path, exist_ok=True)

st.set_page_config(
    page_title="TigerQE AI iQEA",
    page_icon="🤖",
    layout="centered"
)

# Essential Session State Initializations
state_defaults = {
    "page_url": None,
    "selected_images": [],
    "show_popup": False,
    "show_form": False,
    "stop_monitor": {"stop": False},
    "monitor_thread": None,
    "driver": None,
    "recording_started": False,
    "actions": [],
    "workflow_text": [],
    "testcase_response": [],
    "all_testcases": [],
    "save_testcases": False,
    "injected_windows": {},
    "last_urls": {},
    "current_window_ref": {"handle": None},
    "recorded_script": None,
    "recorded_script_language": "Python-Selenium",
    "rb_actions_snapshot": [],
    "tmt_tool": "None",
    "tmt_connected": False,
    "tmt_existing_tcs": [],
    "tmt_selected_plan_id": None,
    "tmt_selected_suite_id": None,
    "tmt_plans": [],
    "tmt_suites": [],
    "gap_analysis_result": None,
    "tmt_jira_project_key": "",
    "tmt_fetch_type": "Test Cases",
    "tmt_gap_approved": False,
    "tmt_replacement_responses": "",
    "tmt_deletion_notice": [],
    "tmt_gen_inputs": {},
    "document_source_selector": "Files",
    "azure_workitem_id": "",
    "jira_workitem_id": "",
    "excel_path": "",
    "recorder": None,
    "rb_language": "Python-Selenium",
    "iqea_active_tool": "recorder"
}

for key, default in state_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.title(" 🤖 TigerQE AI Platform - iQEA (Intelligent QE Assistant)")

# Browser Handling Logic
page_url = st.text_input("Enter the URL of the page:")
st.session_state.page_url = page_url


def clear_browser_session_state():
    driver = st.session_state.get("driver")
    if driver:
        quit_driver(driver)
    st.session_state.driver = None
    st.session_state.novnc_url = None
    st.session_state.browser_session_id = None
    st.session_state.browser_node = None


if st.button("Open Browser"):
    if page_url:
        st.session_state.page_url = normalize_url(page_url)
        if not st.session_state.page_url:
            st.warning("⚠️ Please enter a valid URL.")
        else:
            quit_driver(st.session_state.get("driver"))
            st.session_state.driver = None
            st.session_state.novnc_url = None

            if is_azure():
                with st.spinner("Launching an isolated browser session..."):
                    try:
                        driver = get_driver("recorder")
                        st.session_state.driver = driver
                        browser_info = get_browser_session_info(driver)
                        st.session_state.browser_session_id = browser_info["session_id"]
                        st.session_state.browser_node = browser_info["node"]
                        st.session_state.novnc_url = get_novnc_url(driver)
                    except Exception:
                        st.session_state.driver = None
                        st.error("❌ Unable to create the browser session. Please try again.")
                        st.stop()
            else:
                with st.spinner("Launching browser..."):
                    try:
                        st.session_state.driver = get_driver("recorder")
                    except Exception:
                        st.session_state.driver = None
                        st.error("❌ Unable to create the browser session. Please try again.")
                        st.stop()

            mark_opened("iqea")
            st.session_state.driver.get(st.session_state.page_url)
            safe_maximize(st.session_state.driver)
            WebDriverWait(st.session_state.driver, 30).until(utils.is_page_loaded)

            if is_azure():
                browser_info = get_browser_session_info(st.session_state.driver)
                st.info(f"Browser session: `{browser_info['session_id']}`")
                with st.expander("Browser Session Diagnostics"):
                    st.json(diagnose_browser_session(st.session_state.driver))

            with st.spinner("Waiting for the page to render in the live view..."):
                painted, detail = wait_until_page_ready(st.session_state.driver, timeout=45)

            if painted:
                if is_azure():
                    auto_open_live_browser(st.session_state.driver, key="iqea")
                    st.success(f"✅ Browser opened in a **new tab** — showing {detail}.")
                else:
                    st.success(f"✅ Browser opened and ready — showing {detail}")
            else:
                st.warning(f"⚠️ Browser opened but the page has not finished rendering ({detail}).")
    else:
        st.warning("⚠️ Please enter a URL before opening the browser.")

# Live Browser Panel for Remote/Azure Sessions
render_live_browser_panel(
    st.session_state.get("driver"),
    key="iqea",
    title="🖥️ Live browser — interact here to record",
    caption="This is the browser running in Azure. Click and type inside the live browser to record actions.",
    on_close=clear_browser_session_state,
)

render_artifact_export(key="iqea")

# Tool Rail Workspace
from contextlib import contextmanager

@contextmanager
def _workspace(title):
    with st.container(border=True):
        yield

st.markdown("""
<style>
.stButton>button[kind="primary"]{background:#F47B20;border-color:#F47B20;}
.stButton>button{font-weight:600;}
.iqea-phase{
    color:#E8650A !important;
    font-weight:800; font-size:15px; letter-spacing:.6px; text-transform:uppercase;
    text-align:center; padding:2px 0 8px 0; margin:0 0 12px 0; border-bottom:2px solid #F47B20;
}
.iqea-rail [data-testid="stVerticalBlockBorderWrapper"]{
    background:#ffffff; border:1px solid #E3E6EC !important; border-radius:12px;
    box-shadow:0 3px 10px rgba(0,0,0,.05); min-height:170px;
}
</style>
""", unsafe_allow_html=True)

_IQEA_PHASES = [
    ("🎬 Capture", [("recorder", "🔴 Recorder")]),
    ("📝 Author", [("testcases", "🧮 Test Cases")]),
]

st.markdown("##### 🧰 Select Agent")
st.markdown("<div class='iqea-rail'>", unsafe_allow_html=True)
_rail_cols = st.columns(len(_IQEA_PHASES))
for _col, (_phase, _tools) in zip(_rail_cols, _IQEA_PHASES):
    with _col:
        with st.container(border=True):
            st.markdown(f"<div class='iqea-phase'>{_phase}</div>", unsafe_allow_html=True)
            for _tid, _label in _tools:
                if st.button(
                    _label,
                    key=f"iqea_nav_{_tid}",
                    use_container_width=True,
                    type="primary" if st.session_state.iqea_active_tool == _tid else "secondary",
                ):
                    st.session_state.iqea_active_tool = _tid
                    st.rerun()
st.markdown("</div>", unsafe_allow_html=True)

_tool = st.session_state.iqea_active_tool

if source == "database":
    st.session_state.setdefault("iqea_show_all_owners", False)
    st.session_state.iqea_show_all_owners = st.checkbox(
        "👥 Show recordings and files saved by all users (not just mine)",
        value=st.session_state.iqea_show_all_owners
    )

def _scoped_owner():
    return None if st.session_state.get("iqea_show_all_owners") else current_user()

st.divider()

# ==========================================
# TOOL 1: RECORDER
# ==========================================
if _tool == "recorder":
    with _workspace("🔴 User Workflow Recorder"):
        option = 'Web' if not is_desktop_recording_available() else st.radio("Choose where to record:", ('Web', 'Desktop'))

        if option == 'Web':
            st.subheader("Record User Actions & Capture Screenshots of User Navigation")
            st.session_state.workflow_text = []

            if not st.session_state.recording_started and st.button("🎥 Start Recording"):
                if st.session_state.driver:
                    st.session_state.injected_windows = {}
                    st.session_state.last_urls = {}
                    st.session_state.current_window_ref = {"handle": None}
                    st.session_state.stop_monitor = {"stop": False}
                    st.session_state.actions = []
                    st.session_state.workflow_text = []
                    st.session_state.recorded_script = None
                    st.session_state.rb_actions_snapshot = []

                    handle = st.session_state.driver.current_window_handle
                    st.session_state.driver.execute_script(action_utils.injection_script_agentflow())

                    _inj_ok, _inj_detail = action_utils.verify_injection(st.session_state.driver)
                    if not _inj_ok:
                        st.error(f"❌ Recording could NOT be attached to the page ({_inj_detail}). Please refresh and try again.")
                        st.stop()

                    st.session_state.injected_windows[handle] = True

                    t1 = threading.Thread(
                        target=utils.thread_new_window_checker,
                        args=(st.session_state.driver, st.session_state.injected_windows,
                              st.session_state.last_urls, st.session_state.stop_monitor,
                              page_screenshot_folder, st.session_state.current_window_ref),
                        daemon=True
                    )
                    t2 = threading.Thread(
                        target=utils.thread_focus_and_url_monitor,
                        args=(st.session_state.driver, st.session_state.injected_windows,
                              st.session_state.last_urls, st.session_state.stop_monitor,
                              page_screenshot_folder, st.session_state.current_window_ref),
                        daemon=True
                    )
                    t3 = threading.Thread(
                        target=utils.thread_focus_screenshot,
                        args=(st.session_state.driver, st.session_state.stop_monitor, page_screenshot_folder, source),
                        daemon=True
                    )
                    t4 = threading.Thread(
                        target=utils.thread_reinject_action_check,
                        args=(st.session_state.driver, st.session_state.stop_monitor,
                              st.session_state.last_urls, st.session_state.current_window_ref, st.session_state.injected_windows),
                        daemon=True
                    )

                    t1.start(); t2.start(); t3.start(); t4.start()
                    st.session_state.monitor_threads = [t1, t2, t3, t4]
                    st.session_state.recording_started = True
                    st.success("🔴 Recording started successfully!")

            if st.session_state.recording_started and st.button("🛑 Stop Recording"):
                st.session_state.actions = action_utils.get_recorded_actions(st.session_state.driver)
                st.session_state.rb_actions_snapshot = list(st.session_state.actions)
                st.session_state.recording_started = False
                st.session_state.stop_monitor["stop"] = True

                for t in st.session_state.get("monitor_threads", []):
                    if t and t.is_alive():
                        t.join(timeout=2)

                st.session_state.monitor_threads = []
                if st.session_state.actions:
                    st.success(f"Recording stopped — {len(st.session_state.actions)} action(s) captured.")
                else:
                    st.error("⚠️ Recording stopped but no actions were captured.")

            if st.session_state.actions:
                st.session_state.workflow_text = []
                page_name = st.text_input("Enter Page Name for Saving the Workflow:")
                if st.button("💾 Save Workflow"):
                    if not page_name:
                        st.warning("⚠ Please enter a name for the workflow.")
                    else:
                        st.session_state.workflow_text = action_utils.generate_workflow_manual(st.session_state.actions)
                        workflow_saved = False

                        if source == "database":
                            action_id = db_handler.save_action_to_db(page_name, st.session_state.workflow_text, current_user())
                            st.success(f"✅ Action saved to database (ID: {action_id})")
                            st.download_button("⬇ Download Workflow", data="\n".join(st.session_state.workflow_text), file_name=f"{page_name}_actions.txt")
                            workflow_saved = True
                        elif source == "file":
                            filename = os.path.join(Action_collection, f"{page_name}_actions.txt")
                            cleaned = [s.replace("\u200b", "").replace("\xa0", " ").strip() for s in st.session_state.workflow_text]
                            with open(filename, "w", encoding="utf-8") as f:
                                f.write("\n".join(cleaned))
                            st.success(f"✅ Workflow saved: {filename}")
                            st.download_button("⬇ Download Workflow", data="\n".join(st.session_state.workflow_text), file_name=f"{page_name}_actions.txt")
                            workflow_saved = True

                        if workflow_saved:
                            clear_actions = """(function() {
                                window.__recordedActions = [];
                                localStorage.removeItem("recordedActions");
                            })();"""
                            st.session_state.driver.execute_script(clear_actions)
                            st.session_state.actions.clear()
                            st.session_state.workflow_text.clear()

        if option == 'Desktop':
            st.subheader("Record User Actions & Capture Screenshots of Desktop App")
            st.session_state.setdefault("desktop_recording_started", False)

            application_path = st.text_input("Enter full path to application (.exe):")

            if application_path and not st.session_state.desktop_recording_started:
                if st.button("🎥 Launch and Start Recording"):
                    with st.spinner("Launching application..."):
                        try:
                            _ok, _why, DesktopSession, DesktopRecorder = load_desktop_modules()
                            if not _ok:
                                raise RuntimeError(_why)

                            session = DesktopSession(application_path)
                            session.start(timeout=15)
                            recorder = DesktopRecorder()
                            recorder.start()

                            st.session_state.recorder = recorder
                            st.session_state.desktop_recording_started = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to launch application: {e}")

            if st.session_state.desktop_recording_started:
                st.info("🔴 Recording in progress... Interact with the application, then click Stop.")
                if st.button("🛑 Stop Recording"):
                    st.session_state.recorder.stop()
                    st.session_state.desktop_recording_started = False
                    st.success(f"✅ Recording stopped. {len(st.session_state.recorder.get_actions())} action(s) captured.")
                    st.rerun()

            if not st.session_state.desktop_recording_started and st.session_state.recorder and st.session_state.recorder.get_actions():
                workflow_name = st.text_input("Enter name for saving the desktop workflow:")
                if workflow_name and st.button("💾 Save Desktop Workflow"):
                    workflow_text = st.session_state.recorder.save(workflow_name)
                    filename = os.path.join(Action_collection_desktop, f"{workflow_name}_desktop_actions.txt")
                    cleaned = [s.replace("\u200b", "").replace("\xa0", " ").strip() for s in workflow_text]
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write("\n".join(cleaned))
                    st.success(f"✅ Desktop workflow saved: {filename}")
                    st.session_state.recorder = None

        # Quick Script Generator
        if st.session_state.rb_actions_snapshot:
            with st.expander("⚡ Quick Script Generator (Record & Playback)", expanded=False):
                st.session_state.rb_language = st.selectbox(
                    "Select target language / framework",
                    ["Python-Selenium", "Python-Playwright", "Java-Selenium", "Java-Playwright"],
                    key="rb_language_select"
                )
                rb_script_name = st.text_input("Script file name (without extension):", key="rb_script_name")

                if st.button("⚡ Generate Script from Recording", key="rb_generate_btn"):
                    with st.spinner("Generating script from recorded actions..."):
                        actions_formatted = action_utils.format_actions_for_script_generation(st.session_state.rb_actions_snapshot)
                        script = utils.generate_script_from_recorded_actions(actions_formatted, st.session_state.rb_language)
                        if script:
                            st.session_state.recorded_script = script
                            st.success("✅ Script generated from recording.")
                        else:
                            st.error("Failed to generate script.")

                if st.session_state.recorded_script:
                    st.code(st.session_state.recorded_script, language="python" if "python" in st.session_state.rb_language.lower() else "java")
                    if st.button("💾 Save Script", key="rb_save_btn"):
                        if rb_script_name:
                            utils.create_test_file(Test_file_generator, rb_script_name, st.session_state.rb_language, st.session_state.recorded_script)
                            st.success(f"✅ Script saved: {rb_script_name}")


# ==========================================
# TOOL 2: TEST CASES
# ==========================================
if _tool == "testcases":
    with _workspace("🧮 E2E Scenario Based Test Case Generator"):
        st.title("E2E Scenario Based Test Case Generation")
        option = st.radio("Choose your Flow with:", ('Documents', 'Recorded_Details'))

        if option == 'Recorded_Details':
            if source == "file":
                st.markdown("**Select Images (Mandatory)**", unsafe_allow_html=True)
                image_files = [f for f in os.listdir(page_screenshot_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
                cols = st.columns(5)
                for idx, image_file in enumerate(image_files):
                    with cols[idx % 5]:
                        st.image(os.path.join(page_screenshot_folder, image_file), width=100)
                        if image_file not in st.session_state.selected_images:
                            if st.button(f"{image_file}", key=f"{image_file}"):
                                st.session_state.selected_images.append(image_file)
                        else:
                            if st.button(f"Deselect {image_file}", key=f"deselect_{image_file}"):
                                st.session_state.selected_images.remove(image_file)

            elif source == "database":
                st.markdown("**Select Images from database (Mandatory)**", unsafe_allow_html=True)
                screenshots = screenshot_view.screenshot_index()
                if screenshots:
                    cols = st.columns(5)
                    for idx, shot in enumerate(screenshots):
                        with cols[idx % 5]:
                            label = shot["label"]
                            screenshot_view.render_thumbnail(label, max_width=100)
                            if label not in st.session_state.selected_images:
                                if st.button(f"{label}", key=f"{label}"):
                                    st.session_state.selected_images.append(label)
                            else:
                                if st.button(f"Deselect {label}", key=f"deselect_{label}"):
                                    st.session_state.selected_images.remove(label)

            if st.button("Clear All Selection"):
                st.session_state.selected_images = []

            prompt = st.text_area("Enter the test requirements", "", key="user_requirements_textarea")
            
            Action_data = ""
            if source == "file":
                Action_data = utils.select_and_read_text_files(Action_collection)
            elif source == "database":
                all_files = db_handler.get_all_action_names(owner=_scoped_owner())
                selected_files = st.multiselect("Select saved action files from database", all_files)
                if selected_files:
                    Action_data = "\n".join([f"\n### {f} ###\n{db_handler.get_action_content_by_name(f, 'action', owner=_scoped_owner())}" for f in selected_files])

        elif option == 'Documents':
            source_type = st.selectbox("Select Source Type", options=["Files", "Azure Board", "Jira"], index=0)
            
            if source_type == "Files":
                uploaded_file = st.file_uploader("Upload a document", type=['pdf', 'docx', 'xlsx', 'txt'], key="uploaded_file_uploader")
            elif source_type == "Azure Board":
                workitem = st.text_input("Azure Work Item ID", value=st.session_state.azure_workitem_id, key="azure_workitem_text")
                st.session_state.azure_workitem_id = workitem.strip()
            elif source_type == "Jira":
                jira_id = st.text_input("Jira Issue ID", value=st.session_state.jira_workitem_id, key="jira_workitem_text")
                st.session_state.jira_workitem_id = jira_id.strip()

        # TMT Integration Section
        with st.expander("🔗 Test Management Integration (Optional)", expanded=False):
            tmt_tool = st.radio("Select Test Management Tool", options=["None", "Azure Test Plans", "Jira"], horizontal=True, key="tmt_tool_radio")
            st.session_state.tmt_tool = tmt_tool

            if tmt_tool == "Azure Test Plans":
                if st.button("Directly Fetch Test Cases"):
                    try:
                        tcs = tmt_utils.get_all_testcases_direct()
                        st.session_state.tmt_existing_tcs = tcs
                        st.session_state.tmt_connected = True
                        st.success(f"✅ Fetched {len(tcs)} test case(s).")
                    except Exception as e:
                        st.error(f"❌ Fetch failed: {e}")

        if st.button("Generate Functional Test Cases"):
            st.session_state.testcase_response = []
            st.session_state.save_testcases = False

            if option == 'Recorded_Details' and st.session_state.selected_images and prompt:
                navigation = ', '.join(st.session_state.selected_images)
                image_data = ""

                for image_name in st.session_state.selected_images:
                    if source == "file":
                        image_path = os.path.join(page_screenshot_folder, image_name)
                        if os.path.exists(image_path):
                            image = Image.open(image_path)
                            image_data += f"\nImage: {image_name}\nExtracted Text: {ocr.image_to_string(image)}\n"
                    elif source == "database":
                        raw = screenshot_view.bytes_for_label(image_name)
                        if raw:
                            image = Image.open(io.BytesIO(raw))
                            image_data += f"\nImage: {image_name}\nExtracted Text: {ocr.image_to_string(image)}\n"

                image_prompt = f"Summarize context concisely: {image_data}"
                image_data_processed = utils.get_queries_from_ai_updated(image_prompt) or image_data

                if st.session_state.tmt_existing_tcs:
                    gap_result = utils.analyze_testcase_gaps(st.session_state.tmt_existing_tcs, Action_data, image_data_processed, prompt)
                    st.session_state.gap_analysis_result = gap_result
                else:
                    constructedprompt = utils.generate_pom_from_excel_testcases("Test_case_generation", navigation, image_data_processed, Action_data, prompt)
                    st.session_state.testcase_response = utils.generate_testcases_with_dynamic_stop(constructedprompt, 15, 5)
                    utils.parse_and_display_testcases_categorywise(st.session_state.testcase_response)

        if st.session_state.testcase_response:
            st.session_state.save_testcases = True

        if st.session_state.save_testcases and st.button("💾 Save test cases"):
            utils.covert_response_to_testcases_single_file(st.session_state.testcase_response, Test_case_collection)
            st.session_state.excel_path = utils.covert_response_to_testcases_single_sheet(st.session_state.testcase_response, Test_case_collection)
            st.success("✅ Test cases saved successfully!")

st.divider()
st.markdown("### Contact Us\n- Reach us at [QE Core Team](mailto:sahil.gupta@tigeranalytics.com)")