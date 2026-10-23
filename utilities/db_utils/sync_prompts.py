"""
Push the prompt files in Input/ into the `prompts` table.

    python -m utilities.db_utils.sync_prompts --check          # report drift only
    python -m utilities.db_utils.sync_prompts                  # this environment
    python -m utilities.db_utils.sync_prompts --env both       # local and azure

NOT PART OF THE APPLICATION'S READ PATH.

The app reads prompts from the files in every mode — see
utilities/prompt_registry.py and Utilities_Xpath.load_prompt_from_file. Nothing
reads the `prompts` table any more, so nothing needs this script to have been
run. It is kept for two narrow uses: populating the table for something outside
this app that wants to read prompts from SQL, and putting the table back into a
known state if anyone reinstates the database path.

Background, because the table is still populated and looks authoritative:
database mode used to read it, and it had not been refreshed since July 2025.
Only 8 of 37 prompt types had a row at all; the rest returned None straight into
.format(). `bulk_add_prompts` could never have fixed that — it SKIPS prompts
that already exist, so it could seed a database but never update one. The stale
"Test_case_generation" asked the model for a six-column table with no Category
column, and the parser discards rows that are not seven wide, which is how the
category summary came out as two boxes holding one test case instead of twenty.
"""

import argparse
import os
import sys
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from utilities import prompt_registry


@contextmanager
def _session_for(env):
    """A session bound to `env`'s database, built fresh for this call.

    Deliberately NOT utilities.db_utils.session: that module creates its engine
    at import time from whatever settings were live then, and caches it in
    sys.modules. A loop over --env both therefore kept writing to the first
    environment — the azure pass reported "37 unchanged" while azure still held
    the 11 stale rows, because it had just re-read local. Building the engine
    per target is what makes --env both actually target two servers.
    """
    if env:
        os.environ["IQEA_EXECUTION_TYPE"] = env

    # Imported here so the env var above is in place before the section is read.
    import importlib
    import config.settings_reader as settings_reader
    importlib.reload(settings_reader)

    engine = create_engine(settings_reader.get_db_url(), pool_pre_ping=True,
                           isolation_level="READ COMMITTED", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session, settings_reader.get_db_config()
    finally:
        session.close()
        engine.dispose()


def _rows_by_name(session, Prompt):
    """Existing prompts keyed by lowercase name.

    Keyed case-insensitively on purpose: MySQL's utf8mb4_unicode_ci collation
    already treats 'Page_file' and 'Page_File' as the same key, and the table
    has rows in the old casing ('Page_file', 'Page_file_action',
    'Test_file_action') from before those types were renamed. Matching the same
    way the database does means those are updated and renamed rather than
    colliding with the unique index on insert.
    """
    return {row.prompt_name.lower(): row for row in session.query(Prompt).all()}


def sync(env=None, dry_run=False, check_only=False):
    from utilities.db_utils.models import Prompt
    from utilities.identity import current_user

    missing = prompt_registry.missing_files()
    if missing:
        print("⚠️ Registered prompts with no file on disk (skipped):")
        for prompt_type, path in missing:
            print(f"     {prompt_type} -> {path}")

    added, updated, unchanged, renamed = [], [], [], []
    user = current_user()

    with _session_for(env) as (session, cfg):
        # Printed from the connection that is about to be written to, not from
        # the config that was read earlier, so the target is never in doubt.
        print(f"\n=== {env or 'current'} -> "
              f"{session.get_bind().url.host}/{session.get_bind().url.database} ===")

        existing = _rows_by_name(session, Prompt)

        for prompt_type in prompt_registry.all_prompt_types():
            try:
                text = prompt_registry.read_prompt_file(prompt_type)
            except FileNotFoundError:
                continue

            # Recorded so the table says where its content came from.
            description = os.path.relpath(
                prompt_registry.prompt_path(prompt_type),
                os.path.dirname(os.path.dirname(
                    os.path.abspath(prompt_registry.__file__))))

            row = existing.get(prompt_type.lower())

            if row is None:
                added.append(prompt_type)
                if not (dry_run or check_only):
                    session.add(Prompt(
                        prompt_name=prompt_type, prompt_text=text,
                        description=description,
                        created_by=user, updated_by=user))
                continue

            was_renamed = row.prompt_name != prompt_type
            if was_renamed:
                renamed.append(f"{row.prompt_name} -> {prompt_type}")

            if (row.prompt_text or "").strip() == text.strip() and not was_renamed:
                unchanged.append(prompt_type)
                continue

            if not was_renamed:
                updated.append(prompt_type)

            if not (dry_run or check_only):
                # Normalise the stored name to the registry's casing so the two
                # agree even on a case-sensitive database.
                row.prompt_name = prompt_type
                row.prompt_text = text
                row.description = description
                row.updated_by = user

        if check_only or dry_run:
            session.rollback()
        else:
            session.commit()

    verb = "would add" if (dry_run or check_only) else "added"
    print(f"   {verb:10} {len(added):3}  {', '.join(added[:4])}"
          f"{' ...' if len(added) > 4 else ''}")
    verb = "would update" if (dry_run or check_only) else "updated"
    print(f"   {verb:10} {len(updated):3}  {', '.join(updated[:4])}"
          f"{' ...' if len(updated) > 4 else ''}")
    print(f"   unchanged  {len(unchanged):3}")
    if renamed:
        print(f"   renamed    {len(renamed):3}  {', '.join(renamed)}")

    drift = len(added) + len(updated) + len(renamed)
    if check_only:
        print("   ✅ database matches the prompt files" if not drift
              else f"   ⚠️ {drift} prompt(s) differ — run without --check to sync")
    return drift


def verify(env=None):
    """Read every prompt back the way database mode will, and compare it to the
    file. Catches a name that synced but cannot be looked up again."""
    from utilities.db_utils.models import Prompt

    missing, mismatched = [], []

    with _session_for(env) as (session, cfg):
        print(f"\n=== verify {env or 'current'} -> "
              f"{session.get_bind().url.database} ===")

        # Same lookup handler.get_prompt_by_name performs, but on this
        # environment's connection rather than the import-time cached one.
        for prompt_type in prompt_registry.all_prompt_types():
            row = session.query(Prompt).filter_by(prompt_name=prompt_type).first()
            if not row or not row.prompt_text:
                missing.append(prompt_type)
            elif (row.prompt_text.strip()
                    != prompt_registry.read_prompt_file(prompt_type).strip()):
                mismatched.append(prompt_type)

    total = len(prompt_registry.all_prompt_types())
    print(f"   {total - len(missing) - len(mismatched)}/{total} resolve and match "
          f"the file")
    if missing:
        print(f"   ❌ not found in database: {missing}")
    if mismatched:
        print(f"   ❌ content differs: {mismatched}")
    return not (missing or mismatched)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=["local", "azure", "both"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="report drift and exit non-zero; writes nothing")
    args = parser.parse_args()

    targets = ["local", "azure"] if args.env == "both" else [args.env]

    drift_found = 0
    ok = True
    for target in targets:
        drift_found += sync(target, args.dry_run, args.check)
        if not (args.check or args.dry_run):
            ok = verify(target) and ok

    if args.check:
        sys.exit(1 if drift_found else 0)
    sys.exit(0 if ok else 1)
