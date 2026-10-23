import os
import re
import time
import json
import random
import string
import tempfile
from io import BytesIO, StringIO
import pandas as pd
import openai
from config.env_loader import load_dotenv
from config.settings_reader import get_source, get_model, debug_logs_enabled, get_recorder_poll_secs
import utilities.utils_action as action_utils
import utilities.db_utils.handler as db_handler
from utilities.driver_lock import driver_guard
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
from selenium.webdriver.support.wait import WebDriverWait
import streamlit as st

# Environment & Configurations
source = get_source()
model_type = get_model()

load_dotenv(override=True)
current_path = os.getcwd()
output_folder = os.path.join(current_path, "output")
xpath_generator_folder = os.path.join(output_folder, "xpath_generator")
Page_file_generator = os.path.join(output_folder, "page_file_generator")
Test_file_generator = os.path.join(output_folder, "test_file_generator")
xpath_file = os.path.join(xpath_generator_folder, "xpath_details.xlsx")

os.makedirs(xpath_generator_folder, exist_ok=True)
os.makedirs(Page_file_generator, exist_ok=True)
os.makedirs(Test_file_generator, exist_ok=True)

os.environ["OPENAI_API_KEY"] = os.getenv("AZURE_OPENAI_API_KEY", "")
os.environ["OPENAI_API_BASE"] = os.getenv("AZURE_OPENAI_ENDPOINT", "")

client = openai.OpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    base_url=os.getenv("AZURE_OPENAI_ENDPOINT")
)

if not os.path.exists(xpath_file):
    with pd.ExcelWriter(xpath_file) as writer:
        pd.DataFrame().to_excel(writer, index=False)


# ── Progress Reporting Helpers ────────────────────────────────────────────────
def progress_start(label):
    try:
        return {"bar": st.progress(0.0), "status": st.empty(), "label": label}
    except Exception:
        return None


def progress_tick(handle, done, total, noun="chunk"):
    if not handle:
        return
    try:
        fraction = (done / total) if total else 1.0
        handle["bar"].progress(min(1.0, max(0.0, fraction)))
        handle["status"].caption(f"{handle['label']} — {noun} {done} of {total}")
    except Exception:
        pass


def progress_end(handle, message=None):
    if not handle:
        return
    try:
        handle["bar"].progress(1.0)
        handle["bar"].empty()
        if message:
            handle["status"].caption(message)
        else:
            handle["status"].empty()
    except Exception:
        pass


# ── Utility Helpers ───────────────────────────────────────────────────────────
def _dbg(*args):
    if debug_logs_enabled():
        print(*args)


def _interruptible_sleep(stop_flag, seconds=None):
    if seconds is None:
        seconds = get_recorder_poll_secs()
    slept = 0.0
    while slept < seconds:
        if stop_flag["stop"]:
            return
        time.sleep(0.5)
        slept += 0.5


def load_prompt_from_file(prompt_type):
    from utilities import prompt_registry
    return prompt_registry.read_prompt_file(prompt_type)


def generate_random_prefix(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def is_page_loaded(driver):
    return driver.execute_script("return document.readyState")


def create_test_file(Test_file_location, file_name: str, file_extension: str, response):
    if file_extension in ["Java-Selenium", "Java-Playwright"]:
        file_extension = "java"
    elif file_extension in ["Python-Selenium", "Python-Playwright", "Desktop & Web[python-Selenium]"]:
        file_extension = "python"
    
    if not file_extension.startswith("."):
        if file_extension == "java":
            file_extension = f".{file_extension}"
        elif file_extension == "python":
            file_extension = ".py"
        else:
            file_extension = f".{file_extension}"

    full_file_path = os.path.join(Test_file_location, f"{file_name}{file_extension}")
    with open(full_file_path, "w", encoding="utf-8") as file:
        file.write(response)

    st.write(f"✅ Test file script generated: {full_file_path}")


# ── LLM Invocation Utilities ──────────────────────────────────────────────────
def get_queries_from_ai_updated(formatted_summary):
    load_dotenv(override=True)
    local_client = openai.OpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        base_url=os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    model = "gpt-5-mini"
    try:
        response = local_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": formatted_summary}],
            max_completion_tokens=25000,
            timeout=600
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return None


# ── Background Thread Monitors ────────────────────────────────────────────────
def thread_new_window_checker(driver, injected_windows, last_urls, stop_flag, screenshot_folder, current_window_ref):
    print("Thread 1 started: new window checker")
    while not stop_flag["stop"]:
        try:
            with driver_guard(driver):
                handles = driver.window_handles
                for handle in handles:
                    if handle not in injected_windows:
                        driver.switch_to.window(handle)
                        driver.execute_script(action_utils.injection_script_agentflow())
                        injected_windows[handle] = True
                        last_urls[handle] = driver.current_url
                        current_window_ref["handle"] = handle
                        
                        if source == "file":
                            filepath = action_utils.take_screenshot(driver, screenshot_folder)
                        elif source == "database":
                            filepath = db_handler.take_screenshot_db(driver, "sathanantham")
                        else:
                            filepath = None
                        print(f"📸 Screenshot taken for: {last_urls} => {filepath}")
        except Exception as e:
            print("New window monitor error:", e)
            if stop_flag["stop"]:
                break

        _interruptible_sleep(stop_flag)


def thread_focus_and_url_monitor(driver, injected_windows, last_urls, stop_flag, screenshot_folder, current_window_ref):
    print("Thread 2 started: focus and URL monitor")
    while not stop_flag["stop"]:
        try:
            with driver_guard(driver):
                current_handle = driver.current_window_handle
                current_window_ref["handle"] = current_handle
                current_url = driver.current_url

                if last_urls.get(current_handle) != current_url:
                    driver.execute_script(action_utils.injection_script_agentflow())
                    last_urls[current_handle] = current_url
                    print(f"🔄 URL changed in window {current_handle}, JS reinjected ({current_url})")

        except Exception as e:
            print("Focus/URL monitor error:", e)
            if stop_flag["stop"]:
                break

        _interruptible_sleep(stop_flag)


UI_CHANGE_PROBE_JS = """
return (function () {
    var w = window;
    if (!w.__iqeaShotProbe) {
        var s = { interactions: 0, lastTs: 0 };
        w.__iqeaShotProbe = s;
        var bump = function () { s.interactions++; s.lastTs = Date.now(); };
        document.addEventListener('click',  bump, true);
        document.addEventListener('change', bump, true);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === 'Escape') bump();
        }, true);
    }
    var st = w.__iqeaShotProbe;
    return {
        interactions: st.interactions,
        idle_ms: st.lastTs ? (Date.now() - st.lastTs) : -1,
        count: document.getElementsByTagName('*').length,
        url: location.href,
        ready: document.readyState
    };
})();
"""


def thread_focus_screenshot(driver, stop_flag, screenshot_folder, source="file",
                            settle_ms=800, poll_seconds=0.5, min_delta=1,
                            max_tracked_pages=200):
    print("📸 Screenshot thread started")
    pages = {}
    last_url = None

    def _probe():
        try:
            return driver.execute_script(UI_CHANGE_PROBE_JS)
        except Exception:
            return None

    def _wait_ready():
        for _ in range(50):
            if stop_flag["stop"]:
                return
            try:
                if driver.execute_script("return document.readyState") == "complete":
                    return
            except Exception:
                return
            time.sleep(0.1)

    def _capture(reason, url):
        if stop_flag["stop"]:
            return None
        if source == "file":
            filepath = action_utils.take_screenshot_unique(driver, screenshot_folder)
        elif source == "database":
            filepath = db_handler.take_screenshot_db(driver, "sathanantham")
        else:
            filepath = None
        print(f"📸 Screenshot [{reason}] {url} => {filepath}")
        return filepath

    def _baseline(url, fallback_count, fallback_interactions):
        state = _probe()
        pages.pop(url, None)
        pages[url] = {
            "count": int(state["count"]) if state else fallback_count,
            "interactions": int(state["interactions"]) if state else fallback_interactions,
        }
        while len(pages) > max_tracked_pages:
            pages.pop(next(iter(pages)), None)

    while not stop_flag["stop"]:
        try:
            state = _probe()
            if state:
                url = state["url"]
                count = int(state["count"])
                interactions = int(state["interactions"])
                idle_ms = state["idle_ms"]
                prev = pages.get(url)

                if url != last_url or prev is None:
                    last_url = url
                    _wait_ready()
                    _capture("new-page", url)
                    _baseline(url, count, interactions)
                elif interactions < prev["interactions"]:
                    _wait_ready()
                    _capture("reload", url)
                    _baseline(url, count, interactions)
                elif interactions > prev["interactions"]:
                    if idle_ms >= settle_ms:
                        if abs(count - prev["count"]) >= min_delta:
                            _wait_ready()
                            _capture("ui-change", url)
                            _baseline(url, count, interactions)
                        else:
                            prev["interactions"] = interactions
                            prev["count"] = count

        except Exception as e:
            print("❌ Screenshot thread error:", e)
            if stop_flag["stop"]:
                break

        slept = 0.0
        while slept < poll_seconds and not stop_flag["stop"]:
            time.sleep(0.1)
            slept += 0.1


def thread_reinject_action_check(driver, stop_flag, last_urls=None, current_window_ref=None,
                                 injected_windows=None, idle_timeout=5):
    print("Thread 3 started (idle reinject checker)")
    while not stop_flag["stop"]:
        try:
            result = driver.execute_script("""
                const actions = JSON.parse(localStorage.getItem('recordedActions') || '[]');
                const lastReinject = localStorage.getItem('lastReinjectTime');
                let lastActionTs = null;

                if (actions.length > 0) {
                    lastActionTs = actions[actions.length - 1].timestamp || null;
                }

                return {
                    lastAction: lastActionTs,
                    lastReinject: lastReinject
                };
            """)

            last_action = result.get("lastAction")
            last_reinject = result.get("lastReinject")

            last_action_ts = None
            if last_action:
                if isinstance(last_action, (int, float)):
                    last_action_ts = float(last_action) / 1000.0
                elif isinstance(last_action, str):
                    try:
                        dt = datetime.fromisoformat(last_action.replace("Z", "+00:00"))
                        last_action_ts = dt.timestamp()
                    except Exception:
                        pass

            last_reinject_ts = None
            if last_reinject:
                try:
                    last_reinject_ts = float(last_reinject)
                except Exception:
                    pass

            if last_action_ts:
                now_ts = time.time()
                if not last_reinject_ts or last_action_ts > last_reinject_ts:
                    diff = now_ts - last_action_ts
                    if diff >= idle_timeout:
                        if injected_windows is not None:
                            injected_windows.clear()

                        driver.execute_script("""
                            localStorage.setItem('lastReinjectTime', Date.now() / 1000);
                        """)
                        time.sleep(1)

        except Exception as e:
            print("Idle reinject monitor error:", e)
            if stop_flag["stop"]:
                break

        _interruptible_sleep(stop_flag)


# ── Test Case Generation & Parsing ────────────────────────────────────────────
def generate_pom_from_excel_testcases(prompt_type, navigation, image_data, action_data=None, requirements=""):
    prompt_template = load_prompt_from_file(prompt_type)
    action_section = f"- User Interaction Elements (Action Data): {action_data}" if action_data else ""
    final_prompt = prompt_template.format(
        navigation=navigation,
        image_data_processed=image_data,
        action_data_processed=action_section,
        requirements=requirements
    )
    return final_prompt


def parse_testcases_from_markdown(md_text):
    rows = []
    malformed = []
    if isinstance(md_text, list):
        md_text = "\n".join(str(item) for item in md_text)
    if not md_text:
        return rows
    md_text = md_text.strip()

    for line in md_text.splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        if re.match(r'^\|\s*[-:]+\s*\|', line):
            continue
        if not line.endswith("|"):
            line = line + "|"
        parts = re.split(r'\s*\|\s*', line)
        parts = [p.strip() for p in parts[1:-1]]

        if parts and parts[0].lower() == "test case name":
            continue
        if not parts or all(not p or re.match(r'^[-:]+$', p) for p in parts):
            continue

        if len(parts) == 7:
            name, step, description, expected, status, type_, category = parts
        elif len(parts) == 6:
            name, step, description, expected, status, type_ = parts
            category = ""
        else:
            malformed.append(line)
            continue

        rows.append({
            "name": name,
            "step_number": step,
            "description": description,
            "expected": expected,
            "status": status,
            "type": type_,
            "category": category,
        })

    seen_tc_names = set()
    for row in rows:
        name = row["name"].strip()
        if not name:
            continue
        if name in seen_tc_names:
            row["name"] = ""
        else:
            seen_tc_names.add(name)

    return rows


def parse_and_display_testcases_categorywise(md_text):
    from collections import defaultdict
    rows = parse_testcases_from_markdown(md_text)

    category_to_cases = defaultdict(list)
    for row in rows:
        name = row["name"].strip()
        if not name:
            continue
        category = row["category"].strip().lower() if row["category"].strip() else "others"
        if name not in category_to_cases[category]:
            category_to_cases[category].append(name)

    category_counts = {cat: len(names) for cat, names in category_to_cases.items()}
    category_counts["total"] = sum(category_counts.values())

    color_map = {
        "positive": "#27ae60",
        "negative": "#e74c3c",
        "workflow": "#2980b9",
        "ui": "#f1c40f",
        "edge case": "#8e44ad",
        "others": "#95a5a6",
        "total": "#7f8c8d"
    }

    st.markdown("""
        <style>
            .testcase-container { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
            .testcase-box {
                width: 150px; height: 70px; border-radius: 10px; color: white;
                padding: 6px; text-align: center; position: relative;
                box-shadow: 1px 2px 6px rgba(0,0,0,0.15); font-family: 'Segoe UI', sans-serif;
            }
            .testcase-title { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
            .testcase-count { font-size: 20px; font-weight: 700; margin: 0; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("### 🧾 Category-wise Test Case Summary")
    boxes = []
    for cat, count in category_counts.items():
        color = color_map.get(cat, "#34495e")
        box_html = (
            f"<div class='testcase-box' style='background-color:{color};'>"
            f"<div class='testcase-title'>{cat.capitalize()}</div>"
            f"<div class='testcase-count'>{count}</div>"
            f"</div>"
        )
        boxes.append(box_html)

    st.markdown("<div class='testcase-container'>" + "".join(boxes) + "</div>", unsafe_allow_html=True)
    st.write(" ")
    return category_counts


def generate_testcases_with_dynamic_stop(constructed_prompt, max_testcases, min_new_threshold, max_attempts=50):
    all_testcases = []
    seen_steps = set()
    all_raw_responses = ""
    llm_coverage_summary = ""
    attempt = 0

    while attempt < max_attempts:
        if llm_coverage_summary:
            exclusion_text = (
                f"Previously covered scenarios:\n{llm_coverage_summary}\n\n"
                f"Generate ONLY test cases for NEW scenarios NOT already covered above. "
                f"Continue numbering from TC{len(all_testcases) + 1:02d}."
            )
            prompt = constructed_prompt + "\n\n" + exclusion_text
        else:
            prompt = constructed_prompt

        try:
            response = get_queries_from_ai_updated(prompt)
            if not response:
                attempt += 1
                continue
            all_raw_responses += "\n" + response

            if "## Coverage Summary" in response:
                summary_parts = response.split("## Coverage Summary", 1)
                llm_coverage_summary = summary_parts[1].strip()
                table_response = summary_parts[0]
            else:
                table_response = response

            new_cases = parse_testcases_from_markdown(table_response)
            new_added = 0
            for case in new_cases:
                key = case["name"].strip().lower()
                if key not in seen_steps:
                    seen_steps.add(key)
                    all_testcases.append(case)
                    new_added += 1

            if new_added < min_new_threshold or len(all_testcases) >= max_testcases:
                break
        except Exception as e:
            print(f"⚠️ Exception during AI call: {e}")
            attempt += 1
            continue

        attempt += 1

    return all_raw_responses


def analyze_testcase_gaps(existing_tcs, action_data, image_data, requirements):
    if existing_tcs:
        existing_summary_lines = [f"ID: {tc.get('id','') } | Title: {tc.get('title','')}" for tc in existing_tcs]
        existing_summary = "\n".join(existing_summary_lines)
    else:
        existing_summary = "No existing test cases provided."

    if isinstance(action_data, dict):
        action_str = "\n".join(f"{k}:\n{v}" for k, v in action_data.items())
    else:
        action_str = action_data or ""

    prompt_template = load_prompt_from_file("testcase_gap_analysis")
    final_prompt = prompt_template.format(
        existing_tcs=existing_summary,
        action_data=action_str,
        image_data=image_data or "",
        requirements=requirements or ""
    )

    response = get_queries_from_ai_updated(final_prompt)
    if not response:
        return {"new": [], "update": [], "skip": []}

    clean = response.strip()
    if clean.startswith("```"):
        clean = "\n".join(line for line in clean.splitlines() if not line.strip().startswith("```")).strip()

    try:
        result = json.loads(clean)
        result.setdefault("new", [])
        result.setdefault("update", [])
        result.setdefault("skip", [])
        return result
    except Exception as e:
        print(f"⚠️ Failed to parse gap analysis JSON: {e}")
        return {"new": [], "update": [], "skip": []}


def generate_targeted_testcases(scenarios, action_data, image_data, requirements):
    if not scenarios:
        return ""

    if isinstance(action_data, dict):
        action_str = "\n".join(f"{k}:\n{v}" for k, v in action_data.items())
    else:
        action_str = action_data or ""

    scenario_list = "\n".join(f"{i+1}. {s}" for i, s in enumerate(scenarios))
    n = len(scenarios)

    prompt = (
        f"You are an expert QA test case generator.\n\n"
        f"Generate exactly {n} test case(s) — one for each scenario listed below.\n\n"
        f"Scenarios to generate:\n{scenario_list}\n\n"
        f"Recorded Actions:\n{action_str}\n\n"
        f"UI Screenshot Context:\n{image_data or ''}\n\n"
        f"Requirements:\n{requirements or ''}\n\n"
        f"Output a single Markdown table with header:\n"
        f"| Test Case Name | Step Number | Test Step Description | Test Step Expected Result | Status | Type | Category |\n"
    )

    return get_queries_from_ai_updated(prompt) or ""


def generate_replacement_testcase(title, reason, action_data, image_data, requirements):
    if isinstance(action_data, dict):
        action_str = "\n".join(f"{k}:\n{v}" for k, v in action_data.items())
    else:
        action_str = action_data or ""

    prompt = (
        f"An existing test case needs to be replaced because it is outdated.\n\n"
        f"Existing Test Case Title: {title}\n"
        f"Reason for replacement: {reason}\n\n"
        f"Recorded Actions:\n{action_str}\n\n"
        f"UI Screenshot Context:\n{image_data or ''}\n\n"
        f"Requirements:\n{requirements or ''}\n\n"
        f"Generate exactly ONE replacement test case in Markdown table format."
    )

    return get_queries_from_ai_updated(prompt) or ""


def generate_script_from_recorded_actions(actions_formatted, language):
    prompt_template = load_prompt_from_file("script_from_recording")
    final_prompt = prompt_template.format(
        language=language,
        recorded_actions=actions_formatted
    )
    response = get_queries_from_ai_updated(final_prompt)
    if response:
        lines = response.splitlines()
        cleaned = [l for l in lines if not l.strip().startswith("```")]
        response = "\n".join(cleaned).strip()

    return response or ""


# ── File Export Handlers ───────────────────────────────────────────────────────
def clean_table_lines(raw_markdown):
    cleaned_lines = []
    for line in raw_markdown.strip().splitlines():
        line = line.strip()
        if "|" in line and not set(line).issubset(set("|- ")) and line.count("|") >= 3:
            cleaned_lines.append(line.strip("|").strip())
    return cleaned_lines


def covert_response_to_testcases_single_file(markdown_text, test_collection):
    if source == "file" and not os.path.exists(test_collection):
        os.makedirs(test_collection)

    if isinstance(markdown_text, list):
        markdown_text = "\n".join(str(line) for line in markdown_text)
    elif not isinstance(markdown_text, str):
        markdown_text = str(markdown_text)

    if markdown_text.startswith("```"):
        markdown_text = "\n".join(
            line for line in markdown_text.splitlines() if not line.strip().startswith("```")
        )

    table_lines = clean_table_lines(markdown_text)

    if len(table_lines) >= 2 and "Test Case Name" in table_lines[0]:
        table_text = "\n".join(table_lines)
        try:
            df = pd.read_csv(StringIO(table_text), sep='|', engine='python', on_bad_lines='skip')
            df = df.dropna(axis=1, how='all')
            df.columns = [re.sub(r'\*+', '', col.strip()) for col in df.columns]
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

            df['Test Case Name'] = df['Test Case Name'].replace('', pd.NA).ffill()

            for test_case, group in df.groupby('Test Case Name'):
                file_name = f"{test_case.strip()[:50]}.xlsx"
                safe_file_name = "".join(c for c in file_name if c.isalnum() or c in "._- ()").rstrip()

                if source == "file":
                    path = os.path.join(test_collection, safe_file_name)
                    group.to_excel(path, index=False)
                elif source == "database":
                    db_handler.save_testcases_to_db(safe_file_name, group, "sathanantham")

            st.write("\n✅ Individual test cases are successfully saved.")
            return
        except Exception as e:
            print(f"❌ Failed to parse single-table format: {e}")


def covert_response_to_testcases_single_sheet(markdown_text, test_collection, output_file="IQEA_testcases_" + generate_random_prefix() + ".xlsx"):
    if isinstance(markdown_text, list):
        markdown_text = "\n".join(str(line) for line in markdown_text)
    elif not isinstance(markdown_text, str):
        markdown_text = str(markdown_text)

    if markdown_text.startswith("```"):
        markdown_text = "\n".join(
            line for line in markdown_text.splitlines() if not line.strip().startswith("```")
        )

    rows = parse_testcases_from_markdown(markdown_text)
    if not rows:
        return None

    final_df = pd.DataFrame(rows, columns=["name", "step_number", "description", "expected", "status", "type", "category"])
    final_df.columns = ["Test Case Name", "Step Number", "Test Step Description", "Test Step Expected Result", "Status", "Type", "Category"]

    excel_path = None
    if source == "file":
        if not os.path.exists(test_collection):
            os.makedirs(test_collection)

        excel_path = os.path.join(test_collection, output_file)
        final_df.to_excel(excel_path, index=False, sheet_name="All_Test_Cases")
        st.write(f"✅ Saved all test cases in single sheet: {excel_path}")

    elif source == "database":
        from config.settings_reader import get_update_user
        db_handler.save_testcases_to_db(output_file, final_df, get_update_user())
        excel_path = os.path.join(tempfile.gettempdir(), output_file)
        final_df.to_excel(excel_path, index=False, sheet_name="All_Test_Cases")
        st.write("✅ Saved all test cases in single sheet to DB")

    return excel_path


def select_and_read_text_files(folder_path):
    txt_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]
    if not txt_files:
        st.warning("No .txt files found in the folder.")
        return {}

    selected_files = st.multiselect("Select relevant file(s)", txt_files)
    file_contents = {}
    for file_name in selected_files:
        full_path = os.path.join(folder_path, file_name)
        with open(full_path, 'r', encoding='utf-8') as f:
            file_contents[file_name] = f.read()

    return file_contents