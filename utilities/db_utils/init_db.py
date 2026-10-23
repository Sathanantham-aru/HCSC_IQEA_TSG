# init_db.py
#
# Prepares the IQEA application database for whichever environment
# EXECUTION/execution_type selects. Run on every launch by run_ai.bat when
# source=database; safe to repeat.
#
# Unlike the PostgreSQL version this replaces, it creates the DATABASE as well
# as the tables. Postgres was started by pg_ctl against an existing data
# directory, so the database was always already there; a fresh MySQL server has
# no 'iqea' schema at all and create_all alone would fail to connect.
import os
import sys
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent.parent)

from config.settings_reader import get_db_config

# Import all models to register them with Base
import utilities.db_utils.models  # noqa: F401


def init_db():
    """Create the database if missing, then any missing tables."""
    from utilities.db_utils.bootstrap_db import create_database, create_tables

    cfg = get_db_config()
    print(f"Target: {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}")

    url = create_database()
    create_tables(url)
    print("✅ Database and tables ready!")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    print("Initializing database...")
    init_db()

    # No prompt loading here any more. Prompts are read from the files in
    # Input/ in every mode (see utilities/prompt_registry.py), so there is
    # nothing to seed and nothing that can go stale.
    #
    # This step used to load utilities/db_utils/prompt_list.py — a hardcoded
    # copy of 11 prompts from July 2025 — via bulk_add_prompts, which SKIPS
    # prompts that already exist. A database seeded once was therefore never
    # updated, and database mode served those July prompts indefinitely.
    print("Prompts are read from Input/ — nothing to seed.")
