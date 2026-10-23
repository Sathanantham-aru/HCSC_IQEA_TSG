"""
The one place that says which file backs which prompt type.

This mapping used to live only inside Utilities_Xpath.load_prompt_from_file, as
a 39-branch if/elif chain that ran only on the `source == "file"` path. The
database path looked the name up in the `prompts` table instead, and nothing
kept the two in step. They drifted badly:

  * 31 of the 39 types had no row in `prompts` at all, so database mode got
    None back and fed it to .format() — the generation silently ran on a broken
    prompt rather than failing loudly.
  * 7 of the 8 that did exist were months stale. "Web" was 242 characters in
    the database against 1941 on disk.

With the mapping here, both the file loader and utilities/db_utils/sync_prompts
read the same list, so a prompt added to the app cannot be missing from the
sync, and `python -m utilities.db_utils.sync_prompts --check` will say so.

The files stay the source of truth. They are reviewed in pull requests, they
diff, and `git blame` explains them — none of which is true of a TEXT column.
The database copy exists so a deployment can read prompts without shipping the
Input/ tree, and it is refreshed from the files, never edited in place.
"""

import os

# Folder shorthands, relative to the repo root.
_INPUT = "Input"
_PAGE = os.path.join(_INPUT, "Page_file_prompts")
_TEST = os.path.join(_INPUT, "Test_file_prompts")
_VALIDATE = os.path.join(_INPUT, "Script_validation")
_CASES = os.path.join(_INPUT, "Test_cases_prompts")

# prompt_type -> path, relative to the repo root.
PROMPT_FILES = {
    "Web": os.path.join(_INPUT, "web_prompt.txt"),

    # Page file generation, per language/library.
    "Java-Selenium": os.path.join(_PAGE, "java_selenium_page_prompt.txt"),
    "Java-Playwright": os.path.join(_PAGE, "java_playwright_page_prompt.txt"),
    "Python-Selenium": os.path.join(_PAGE, "python_selenium_page_prompt.txt"),
    # Note the .text extension — that is how the file is actually named on disk.
    "Python-Playwright": os.path.join(_PAGE, "python_playwright_page_prompt.text"),

    # Test file generation, per language/library.
    "Test-Java-Selenium": os.path.join(_TEST, "java_selenium_test_prompt.txt"),
    "Test-Java-Playwright": os.path.join(_TEST, "java_playwright_test_prompt.txt"),
    "Test-Python-Selenium": os.path.join(_TEST, "python_selenium_test_prompt.txt"),
    "Test-Python-Playwright": os.path.join(_TEST, "python_playwright_test_prompt.txt"),
    "Test-Desktop & Web[python-Selenium]": os.path.join(_TEST, "Desktop_Web_python_Selenium.txt"),
    "Test-UTAM-JavaScript": os.path.join(_TEST, "UTAM-JavaScript.txt"),

    # Generated-script validation.
    "Test-validate-Java-Selenium": os.path.join(_VALIDATE, "java_selenium_validation.txt"),
    "Test-validate-Java-Playwright": os.path.join(_VALIDATE, "java_playwright_validation.txt"),
    "Test-validate-Python-Selenium": os.path.join(_VALIDATE, "python_selenium_validation.txt"),
    "Test-validate-Python-Playwright": os.path.join(_VALIDATE, "python_playwright_validation.txt"),
    "Script_validation_common": os.path.join(_VALIDATE, "Script_validation_common.txt"),

    # Test data.
    "test_data": os.path.join(_INPUT, "test_data_generator_promt.txt"),

    # Locators / page objects.
    "PowerBi": os.path.join(_INPUT, "powerBi_prompt.txt"),
    "Page_File": os.path.join(_INPUT, "Page_file_prompt.txt"),
    "Page_File_Action": os.path.join(_INPUT, "Page_file_prompt_with_action_v2.txt"),
    "Test_File_Action": os.path.join(_INPUT, "test_script_prompt_v2.txt"),

    # Test case generation.
    "Test_case_generation": os.path.join(_INPUT, "testcase_generation_final_prompt.txt"),
    "Test_case_generation_gemini": os.path.join(_INPUT, "testcase_generation_final_prompt_gemini.txt"),
    "Test_case_generation_document": os.path.join(_INPUT, "Testcase_generate_prompt_with_document.txt"),
    "Test_case_generation_document_gemini": os.path.join(_INPUT, "Testcase_generate_prompt_with_document_gemini.txt"),
    "Test_case_generation_pbi": os.path.join(_INPUT, "Testcase_generate_prompt_powerbi.txt"),

    # BDD.
    "Feature_file": os.path.join(_INPUT, "featurefile_prompt.txt"),

    # Accuracy / regeneration.
    "Test_case_accuracy": os.path.join(_INPUT, "Testcase_Accuracy_matrix1.txt"),
    "Test_case_regeneration_accuracy": os.path.join(_INPUT, "Testcase_regeneration_accuracy.txt"),
    "Test_case_regeneration_accuracy_doc": os.path.join(_INPUT, "Testcase_regeneration_accuracy_doc.txt"),
    "Test_case_regeneration_requirement_split": os.path.join(_INPUT, "testcase_requirement_split_prompt.txt"),

    # Coverage planning.
    "Testcase_coverage_plan_recorded_details_flow": os.path.join(_INPUT, "testcase_coverage_plan_recorded_details_flow.txt"),
    "Testcase_coverage_plan_document_flow": os.path.join(_INPUT, "testcase_coverage_plan_document_flow.txt"),
    "Test_scenarios_finder": os.path.join(_INPUT, "Test_scenarios_finder.txt"),

    # Added May 2026.
    "testcase_workflow_segmenter": os.path.join(_CASES, "testcase_workflow_segmenter.txt"),
    "testcase_gap_analysis": os.path.join(_CASES, "testcase_gap_analysis.txt"),
    "script_from_recording": os.path.join(_CASES, "script_from_recording_prompt.txt"),
}

# Declared by the old if/elif chain but never requested by any caller, and the
# files they name do not exist. Listed rather than silently dropped so that a
# search for the name lands here instead of on "why is this missing".
ORPHANED = {
    "featureaction": os.path.join(_INPUT, "featureaction_prompt.txt"),
    "Test_case_generation_withaction": os.path.join(_INPUT, "Testcase_generate_prompt_with_action.txt"),
}

# Resolved against this file's location, not os.getcwd(), which the recorder
# threads and the `python -m` entry points do not all agree on.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def prompt_path(prompt_type):
    """Absolute path to the file backing `prompt_type`, or None if unknown."""
    relative = PROMPT_FILES.get(prompt_type) or ORPHANED.get(prompt_type)
    return os.path.join(_REPO_ROOT, relative) if relative else None


def read_prompt_file(prompt_type):
    """The prompt text from disk. Raises if the type or the file is unknown —
    a missing prompt must not degrade into an empty string that gets sent to
    the model as if it were an instruction."""
    path = prompt_path(prompt_type)
    if path is None:
        raise ValueError(f"Invalid prompt type: {prompt_type}")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found at: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def all_prompt_types():
    return list(PROMPT_FILES)


def missing_files():
    """(prompt_type, path) for every registered prompt whose file is absent."""
    return [(t, prompt_path(t)) for t in PROMPT_FILES
            if not os.path.exists(prompt_path(t))]
