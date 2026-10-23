"""
Create the IQEA MySQL database and its tables.

    python -m utilities.db_utils.bootstrap_db                 # this environment
    python -m utilities.db_utils.bootstrap_db --env local
    python -m utilities.db_utils.bootstrap_db --env azure
    python -m utilities.db_utils.bootstrap_db --env both
    python -m utilities.db_utils.bootstrap_db --env both --inspect

Safe to re-run: the database is created only if absent, and create_all only adds
tables that are missing. It never drops or alters anything, so it will not
reconcile a table whose columns have since changed — use --inspect to see what
is actually there.

`--env` overrides EXECUTION/execution_type for this process only, so both
servers can be set up from one workstation without editing settings.ini.
"""

import argparse
import os
import sys

from sqlalchemy import create_engine, inspect, text


def _configure_env(env):
    """Point config.settings_reader at one environment's [DATABASE_*] section.

    get_execution_type() reads IQEA_EXECUTION_TYPE on every call and it wins
    over settings.ini, so setting it here redirects every later lookup without
    touching the file.
    """
    if env:
        os.environ["IQEA_EXECUTION_TYPE"] = env


def create_database(env=None):
    """CREATE DATABASE if it does not exist, then return its URL."""
    _configure_env(env)
    # Imported after the env var is set so the section resolves correctly.
    from config.settings_reader import get_db_config, get_db_url

    cfg = get_db_config()
    name = cfg["database"]

    # Connect to the server rather than the database — the database is what we
    # are about to create.
    server = create_engine(get_db_url(include_database=False),
                           isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        existing = [row[0] for row in conn.execute(text("SHOW DATABASES"))]
        if name in existing:
            print(f"   database '{name}' already exists")
        else:
            # utf8mb4 throughout: test case titles and recorded page text carry
            # non-ASCII, and MySQL's older 'utf8' is a 3-byte subset that cannot
            # represent everything utf-8 can.
            conn.execute(text(
                f"CREATE DATABASE `{name}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            print(f"   created database '{name}' (utf8mb4)")
    server.dispose()

    return get_db_url()


def create_tables(url):
    from utilities.db_utils.base import Base
    import utilities.db_utils.models  # noqa: F401 — registers every model

    engine = create_engine(url)
    before = set(inspect(engine).get_table_names())
    Base.metadata.create_all(engine)
    after = set(inspect(engine).get_table_names())

    added = sorted(after - before)
    if added:
        print(f"   created tables: {', '.join(added)}")
    else:
        print(f"   all {len(after)} tables already present")
    engine.dispose()
    return sorted(after)


def inspect_schema(url):
    """Print the column types actually in the database.

    Worth looking at at least once: a BLOB where a LONGBLOB was intended holds
    64KB and truncates the rest silently, and the screenshots in this store
    reach 396KB.
    """
    engine = create_engine(url)
    inspector = inspect(engine)
    for table in sorted(inspector.get_table_names()):
        print(f"\n   {table}")
        for col in inspector.get_columns(table):
            print(f"      {col['name']:<16} {str(col['type'])}")
    engine.dispose()


def bootstrap(env=None, show_schema=False):
    label = env or "current settings.ini"
    print(f"\n=== {label} ===")
    url = create_database(env)
    # Report where we landed without printing the password.
    from config.settings_reader import get_db_config
    cfg = get_db_config()
    print(f"   target: {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}")
    tables = create_tables(url)
    if show_schema:
        inspect_schema(url)
    return tables


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=["local", "azure", "both"],
                        help="which environment to set up (default: whatever "
                             "settings.ini currently selects)")
    parser.add_argument("--inspect", action="store_true",
                        help="print resulting column types")
    args = parser.parse_args()

    try:
        if args.env == "both":
            for one in ("local", "azure"):
                bootstrap(one, args.inspect)
        else:
            bootstrap(args.env, args.inspect)
        print("\nDone.")
    except Exception as exc:
        print(f"\n❌ Bootstrap failed: {type(exc).__name__}: {exc}")
        sys.exit(1)
