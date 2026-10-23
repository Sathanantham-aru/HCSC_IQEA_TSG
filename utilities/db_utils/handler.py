from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from io import BytesIO
import csv
import zipfile
from utilities.db_utils.models import *
from config.settings_reader import get_db_url
import os
import io
import pandas as pd
import streamlit as st
import tempfile
from datetime import datetime
from urllib.parse import urlparse
import re
from sqlalchemy.exc import SQLAlchemyError

# Use the shared engine/session from db_utils.session rather than building a
# second one here.
#
# The old `session = Session()` was ONE Session object shared by the whole
# process. Streamlit serves every user from that process and the recorder runs
# four monitor threads, so a single failed flush anywhere left the session in a
# "needs rollback" state for EVERYONE until a restart — which is the
# PendingRollbackError seen in Azure ("transaction has been rolled back due to a
# previous exception during flush"). Azure MySQL also closes idle connections,
# and this engine had no pre-ping to recover from that.
#
# ScopedSession is a proxy: every existing session.query(...) / session.add(...)
# call here keeps working unchanged, but each thread gets its own Session, and
# the shared engine adds pool_pre_ping and pool_recycle.
from utilities.db_utils.session import ScopedSession, get_engine

engine = get_engine()
Session = ScopedSession
session = ScopedSession


def _commit():
    """
    Commit, rolling back on failure.

    Without the rollback a failed flush poisons this thread's session, and every
    later write raises PendingRollbackError instead of the real error — so the
    cause gets hidden behind a misleading message. Of the nine commit sites here
    only two had any rollback handling.
    """
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

def bulk_add_prompts(prompt_data_list, created_by):
    """
    prompt_data_list: List of dicts with keys - prompt_name, prompt_text, description (optional)
    """
    added = []
    skipped = []

    for data in prompt_data_list:
        prompt_name = data.get("prompt_name")
        existing = session.query(Prompt).filter_by(prompt_name=prompt_name).first()

        if existing:
            skipped.append(prompt_name)
            continue

        new_prompt = Prompt(
            prompt_name=prompt_name,
            prompt_text=data.get("prompt_text"),
            description=data.get("description"),
            created_by=created_by,
            updated_by=created_by,
            created_on=datetime.utcnow(),
            updated_on=datetime.utcnow()
        )
        session.add(new_prompt)
        added.append(prompt_name)

    _commit()
    print(f"✅ Added prompts: {added}")
    if skipped:
        print(f"⚠️ Skipped existing prompts: {skipped}")

def add_prompt(prompt_name, prompt_text, created_by, description=None):
    existing = session.query(Prompt).filter_by(prompt_name=prompt_name).first()
    if existing:
        print(f"⚠️ Prompt '{prompt_name}' already exists.")
        return

    new_prompt = Prompt(
        prompt_name=prompt_name,
        prompt_text=prompt_text,
        description=description,
        created_by=created_by,
        updated_by=created_by,
        created_on=datetime.utcnow(),
        updated_on=datetime.utcnow()
    )
    session.add(new_prompt)
    _commit()
    print(f"✅ Prompt '{prompt_name}' added.")

def get_prompt_by_name(prompt_name):
    prompt = session.query(Prompt).filter_by(prompt_name=prompt_name).first()
    if prompt:
        return prompt.prompt_text
    else:
        print(f"⚠️ Prompt '{prompt_name}' not found.")
        return None
    
def save_action_to_db(action_name, content, created_by):
    if isinstance(content, list):
        content = "\n".join(content)

    file_binary = content.encode("utf-8")
    full_name = f"{action_name}.txt"

    # Same name, same owner as an existing row -> overwrite that row instead
    # of appending a new one. Resaving your OWN "login_flow" a second time is
    # a normal edit, not a collision — this is what makes it safe for two
    # DIFFERENT owners to each have their own "login_flow" (see
    # get_all_action_names/get_action_content_by_name's owner filter) without
    # either one's row count growing without bound every time they iterate.
    existing = (session.query(Action)
               .filter_by(action_name=full_name, created_by=created_by)
               .order_by(Action.id.desc())
               .first())
    if existing:
        existing.file_data = file_binary
        _commit()
        return existing.id

    action = Action(
        action_name=full_name,
        file_data=file_binary,
        created_by=created_by
    )

    session.add(action)
    _commit()
    return action.id

def save_testfile_to_db(test_name, content, created_by, language):
    if language in ["Java-Selenium", "Java-Playwright"]:
        language = "java"
    elif language in ["Python-Selenium", "Python-Playwright"]:
        language = "python"
    ext = "java" if language == "java" else "py"
    file_name = f"{test_name}.{ext}"

    if isinstance(content, list):
        content = "\n".join(content)

    file_binary = content.encode("utf-8")

    # See save_action_to_db for why this is an overwrite-in-place rather than
    # a blind append.
    existing = (session.query(Testfile)
               .filter_by(testfile_name=file_name, created_by=created_by)
               .order_by(Testfile.id.desc())
               .first())
    if existing:
        existing.file_data = file_binary
        _commit()
        st.write("✅ Test file script updated in DB")
        return existing.id

    testfile = Testfile(
        testfile_name=file_name,
        file_data=file_binary,
        created_by=created_by
    )

    session.add(testfile)
    _commit()
    st.write("✅ Test file script generated and saved in DB")
    return testfile.id

def save_pagefile_to_db(page_name, content, created_by, language):
    if language in ["Java-Selenium", "Java-Playwright"]:
        file_extension = "java"
    elif language in ["Python-Selenium", "Python-Playwright"]:
        file_extension = "python"
    ext = "java" if language == "java" else "py"
    file_name = f"{page_name}.{ext}"

    if isinstance(content, list):
        content = "\n".join(content)

    file_binary = content.encode("utf-8")

    # See save_action_to_db for why this is an overwrite-in-place rather than
    # a blind append.
    existing = (session.query(Pagefile)
               .filter_by(pagefile_name=file_name, created_by=created_by)
               .order_by(Pagefile.id.desc())
               .first())
    if existing:
        existing.file_data = file_binary
        _commit()
        return existing.id

    pagefile = Pagefile(
        pagefile_name=file_name,
        file_data=file_binary,
        created_by=created_by
    )

    session.add(pagefile)
    _commit()
    return pagefile.id


def save_featurefile_to_db(page_name, content, created_by):
    file_name = f"{page_name}.feature"

    if isinstance(content, list):
        content = "\n".join(content)

    file_binary = content.encode("utf-8")

    # See save_action_to_db for why this is an overwrite-in-place rather than
    # a blind append.
    existing = (session.query(Fetaurefile)
               .filter_by(featurefile_name=file_name, created_by=created_by)
               .order_by(Fetaurefile.id.desc())
               .first())
    if existing:
        existing.file_data = file_binary
        _commit()
        return existing.id

    featurefile = Fetaurefile(
        featurefile_name=file_name,
        file_data=file_binary,
        created_by=created_by
    )

    session.add(featurefile)
    _commit()
    return featurefile.id


def save_testcases_to_db(testcase_name, dataframe: pd.DataFrame, created_by):
    try:
        # Some callers hand over CSV text rather than a frame; parse it back so
        # what lands in the column is always a real workbook, instead of raising
        # AttributeError into a caller that swallows it.
        if not isinstance(dataframe, pd.DataFrame):
            dataframe = pd.read_csv(io.StringIO(str(dataframe)))

        # The artifacts download names the ZIP entry after this column, so keep
        # the extension on it.
        if not testcase_name.lower().endswith(".xlsx"):
            testcase_name = f"{testcase_name}.xlsx"

        # Convert DataFrame to real Excel binary
        buffer = io.BytesIO()
        dataframe.to_excel(buffer, index=False)
        buffer.seek(0)
        file_binary = buffer.read()

        # See save_action_to_db for why this is an overwrite-in-place rather
        # than a blind append.
        existing = (session.query(Testcasefile)
                   .filter_by(testcase_name=testcase_name, created_by=created_by)
                   .order_by(Testcasefile.id.desc())
                   .first())
        if existing:
            existing.file_data = file_binary
            _commit()
            return existing.id

        testcase = Testcasefile(
            testcase_name=testcase_name,
            file_data=file_binary,
            created_by=created_by
        )

        session.add(testcase)
        _commit()
        return testcase.id

    except SQLAlchemyError as e:
        session.rollback()
        print(f"❌ Database error: {e}")
        raise

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise

def save_testcases_to_db_old(testcase_name, content, created_by):
    try:
        # Case 1: content is a list of dictionaries (structured like a CSV)
        if isinstance(content, list) and content and isinstance(content[0], dict):
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=content[0].keys())
            writer.writeheader()
            writer.writerows(content)
            file_binary = buffer.getvalue().encode("utf-8")

        # Case 2: fallback for plain text or other formats
        else:
            file_binary = str(content).encode("utf-8")

        # Create the database object
        testcase = Testcasefile(
            testcase_name=testcase_name,
            file_data=file_binary,
            created_by=created_by
        )

        session.add(testcase)
        _commit()
        return testcase.id

    except SQLAlchemyError as e:
        session.rollback()
        print(f"❌ Database error: {e}")
        raise

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise
def get_action_file_by_name(action_name):
    # Exact name, newest row — see the note in get_action_content_by_name.
    action = (session.query(Action)
              .filter(Action.action_name == action_name)
              .order_by(Action.id.desc())
              .first())
    if action:
        # Save the binary file data as a temp file
        temp_file_path = f"temp_files/{action_name}"  # store in a temp folder
        os.makedirs("temp_files", exist_ok=True)  # ensure the folder exists

        with open(temp_file_path, "wb") as f:
            f.write(action.file_data)

        return temp_file_path
    else:
        raise FileNotFoundError(f"No file found in DB with name: {action_name}")

def _distinct_names(model, name_col, owner_col=None, owner=None):
    """
    Saving the same name twice appends a row rather than replacing one, so these
    pickers used to list one entry per save. Collapse to distinct names — the
    lookups above resolve each to its newest row.

    `owner` scopes this to one person's rows. Without it, two testers who both
    saved a workflow called "login_flow" see ONE "login_flow" in the list
    between them — a name collision hides one of the two, and whichever the
    lookup below picks as newest silently wins for both of them. Passing
    `owner=current_user()` (every call site in the app now does) makes each
    tester see only their own names, so "login_flow" and someone else's
    "login_flow" are two separate, independently reachable entries rather than
    one that shadows the other.
    """
    query = session.query(name_col).distinct()
    if owner and owner_col is not None:
        query = query.filter(owner_col == owner)
    return [row[0] for row in query.order_by(name_col).all()]

def get_all_screenshot_names():
    return _distinct_names(Screenshot, Screenshot.page_name)
def get_all_action_names(owner=None):
    return _distinct_names(Action, Action.action_name, Action.created_by, owner)
def get_all_pagefile_names(owner=None):
    return _distinct_names(Pagefile, Pagefile.pagefile_name, Pagefile.created_by, owner)
def get_all_testfile_names(owner=None):
    return _distinct_names(Testfile, Testfile.testfile_name, Testfile.created_by, owner)
def get_all_testcasefile_names(owner=None):
    return _distinct_names(Testcasefile, Testcasefile.testcase_name, Testcasefile.created_by, owner)


def get_action_content_by_name(action_name: str, type: str, owner: str = None) -> str:
    """
    Fetches the content of the action file from the database by action_name.
    Supports .txt, .py, .java (as text), and .xlsx (as parsed table).

    `owner` matters as soon as two people can save the same name. Without it,
    "newest row wins" means whoever saved last — anyone, not just you — is
    the version every caller gets back, including the ORIGINAL owner opening
    what they think is their own file. Pass `owner=current_user()` (every
    call site in the app now does) to resolve within that person's own rows
    only.
    """
    # Exact name match, newest row first. The old `.ilike("%name%")` + `.first()`
    # matched any file whose name merely CONTAINED the requested one, and with no
    # ORDER BY it returned whichever row the planner produced — in practice the
    # lowest id, i.e. the very first version ever saved rather than the current one.
    model_map = {
        "page":     (Pagefile,     Pagefile.pagefile_name,   Pagefile.created_by),
        "testcase": (Testcasefile, Testcasefile.testcase_name, Testcasefile.created_by),
        "test":     (Testfile,     Testfile.testfile_name,   Testfile.created_by),
        "action":   (Action,       Action.action_name,       Action.created_by),
    }

    if type not in model_map:
        # Returning a string here made every caller's `if content:` succeed and
        # write the error text out as if it were the file.
        return None

    model, name_col, owner_col = model_map[type]
    query = session.query(model).filter(name_col == action_name)
    if owner:
        query = query.filter(owner_col == owner)
    action = query.order_by(model.id.desc()).first()

    if not action or not action.file_data:
        return None

    # Determine file extension
    _, ext = os.path.splitext(action_name.lower())

    try:
        if ext == ".xlsx":
            # Read Excel binary using pandas
            excel_buffer = io.BytesIO(action.file_data)
            df = pd.read_excel(excel_buffer)
            return df.to_string(index=False)

        # Everything else is text. Callers feed this straight into an LLM prompt
        # or write it out as a .py to execute, so an "[Unsupported file type]"
        # marker for an unrecognised (or absent) extension was worse than useless
        # — rows saved before the extension fix have no suffix at all.
        return action.file_data.decode("utf-8", errors="ignore")

    except Exception as e:
        print(f"❌ Could not read '{action_name}' ({type}): {e}")
        return None
    

def prepare_selected_files_for_github(selected_file_names, owner=None):
    """
    1. Takes list of selected file names from UI (either .java or .py)
    2. Creates physical files in a temp directory using DB content
    3. Returns temp folder path containing those files for pushing to GitHub
    4. You are expected to delete temp folder after GitHub push

    `owner` scopes both lookups the same way get_action_content_by_name does
    — without it, pushing a name you share with another tester can push
    THEIR file to your repo path.
    """
     # Create a temporary directory
    temp_dir = tempfile.mkdtemp(prefix="push_github_")

    for file_name in selected_file_names:
        file_ext = os.path.splitext(file_name)[1].lower()

        # Determine model type based on file name or extension
        file_record = None
        if file_ext == ".py" or file_ext == ".java":
            # Newest row wins — an unordered .first() pushed the oldest version
            # of the file to GitHub.
            page_query = session.query(Pagefile).filter_by(pagefile_name=file_name)
            test_query = session.query(Testfile).filter_by(testfile_name=file_name)
            if owner:
                page_query = page_query.filter_by(created_by=owner)
                test_query = test_query.filter_by(created_by=owner)
            file_record = (
                page_query.order_by(Pagefile.id.desc()).first()
                or test_query.order_by(Testfile.id.desc()).first()
            )

        if not file_record:
            st.warning(f"⚠️ No record found for file: {file_name}")
            continue

        # Write binary content to actual file
        temp_file_path = os.path.join(temp_dir, file_name)
        with open(temp_file_path, "wb") as f:
            f.write(file_record.file_data)

        st.success(f"✅ Prepared {file_name} for GitHub upload")

    return temp_dir  # You'll use this path to push to GitHub

def get_screenshots_from_db(page_name: str = None):
    query = session.query(Screenshot)
    if page_name:
        query = query.filter(Screenshot.page_name == page_name)
    return query.order_by(Screenshot.created_on.desc()).all()

def get_all_screenshots():
    """
    Every screenshot row, image bytes included.

    Prefer get_screenshot_index() + get_screenshot_data() for anything that
    renders a gallery — this pulls every PNG in the table.

    It used to run the identical query TWICE and print() the result, which
    called __repr__ on rows holding full PNG blobs. Against Azure MySQL that was
    four whole-table blob transfers per Streamlit re-run (this is called from
    two places), which is why selecting an image took seconds.
    """
    return session.query(Screenshot).order_by(Screenshot.created_on.desc()).all()


def get_screenshot_index():
    """
    (id, page_name, url, created_on) for every screenshot — WITHOUT the image
    bytes.

    This is what a gallery needs to build its labels. Fetching the blobs to
    render 100px thumbnails is what made the page slow; bytes are pulled one at
    a time, on demand, by get_screenshot_data().
    """
    rows = (session.query(Screenshot.id, Screenshot.page_name, Screenshot.url,
                          Screenshot.created_on)
            .order_by(Screenshot.created_on.desc())
            .all())
    return [{"id": r[0], "page_name": r[1], "url": r[2], "created_on": r[3]}
            for r in rows]


def get_screenshot_data(screenshot_id):
    """Image bytes for one screenshot, or None if the row is gone."""
    row = (session.query(Screenshot.image_data)
           .filter(Screenshot.id == screenshot_id)
           .first())
    return row[0] if row else None

def take_screenshot_db(driver,created_by="system"):
    url = driver.current_url
    parsed_url = urlparse(url)
    # `path.strip("/") or None` handed re.sub None for any root URL, which raised
    # TypeError inside the recorder's screenshot thread — so the landing page of
    # every site was the one page that never got captured. Fall back to the host,
    # and to "home" if even that is empty.
    raw_name = parsed_url.path.strip("/") or parsed_url.netloc or "home"
    page_name = re.sub(r'[\\/*?:"<>|]', "_", raw_name)

    screenshot_bytes = driver.get_screenshot_as_png()

    screenshot_record = Screenshot(
        page_name=page_name,
        url=url,
        image_data=screenshot_bytes,
        created_by=created_by
    )
    session.add(screenshot_record)
    _commit()

    return f"DB_Record_ID: {screenshot_record.id}"

def download_files_from_database(file_names: list, file_type: str, owner: str = None) -> bytes:
    """
    Given a list of filenames and file type, fetch content from DB and return zipped bytes.

    `owner` matters even though the picker that produced `file_names` is
    already scoped to one owner (see get_all_*_names): the NAME travels here,
    not the row. Without re-applying the same owner filter at the fetch, a
    name shared with another tester (now a normal, expected thing — see
    _distinct_names) resolves to whichever of the two rows has the higher id,
    which is not necessarily the one the current user picked from their own
    list. Pass owner=current_user() (the call site does) to fetch YOUR row.
    """
    zip_buffer = BytesIO()
    missing = []
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for name in file_names:
            content = get_file_content_by_type(name, file_type, owner=owner)
            if content:
                zipf.writestr(name, content)
            else:
                missing.append(name)

    # Say so rather than handing back a ZIP that is quietly short a few files.
    if missing:
        st.warning("⚠️ No stored content for: " + ", ".join(missing))

    zip_buffer.seek(0)
    return zip_buffer.read()

def get_file_content_by_type(name: str, file_type: str, owner: str = None):
    return get_file_content_by_name(name, file_type, owner=owner)

def get_file_content_by_name(action_name: str, type: str, owner: str = None):
    """
    Fetches the stored bytes for a file, for zipping into an artifacts download.

    Returns the raw stored bytes for every type. The previous version dispatched
    on the file extension and only handled .txt/.py/.java/.xlsx/images, so a name
    saved without an extension (test case sheets were saved as bare
    "All_Test_Cases") fell to an "[Unsupported file type: ]" branch whose error
    STRING was then written into the ZIP in place of the workbook. It also
    base64'd images into a data: URI, which is not what belongs in a ZIP entry.

    `owner` scopes the lookup the same way get_action_content_by_name does —
    see that function's docstring for why this is not optional once two
    people can save the same name.
    """
    model_map = {
        "Page_file": (Pagefile, Pagefile.pagefile_name, Pagefile.created_by),
        "Testcase_file": (Testcasefile, Testcasefile.testcase_name, Testcasefile.created_by),
        "Test_file": (Testfile, Testfile.testfile_name, Testfile.created_by),
        "Recorded_Action_file": (Action, Action.action_name, Action.created_by),
    }

    if type not in model_map:
        return None

    model, name_col, owner_col = model_map[type]
    # Exact name, newest row — see the note in get_action_content_by_name.
    query = session.query(model).filter(name_col == action_name)
    if owner:
        query = query.filter(owner_col == owner)
    action = query.order_by(model.id.desc()).first()

    if not action or not getattr(action, "file_data", None):
        return None

    return action.file_data
