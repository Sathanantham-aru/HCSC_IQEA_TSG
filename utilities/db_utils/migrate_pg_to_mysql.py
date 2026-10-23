"""
One-time copy of the IQEA application data from PostgreSQL into MySQL.

    python -m utilities.db_utils.migrate_pg_to_mysql --env local --dry-run
    python -m utilities.db_utils.migrate_pg_to_mysql --env local
    python -m utilities.db_utils.migrate_pg_to_mysql --env azure
    python -m utilities.db_utils.migrate_pg_to_mysql --env both --verify

Reads the old server described by [DATABASE_postgres_legacy] in settings.ini and
writes the MySQL database for the chosen environment. Nothing is written back to
PostgreSQL, so the old server stays intact as a fallback until this has been
checked.

Idempotent: primary keys are carried across unchanged and rows whose id is
already present are skipped. Carrying the ids matters — iqea_artifacts.run_id
points at iqea_runs.id, and renumbering would break that link.

Rows are sent in batches sized by their byte count rather than by row count,
because a screenshot is ~400KB and Azure MySQL rejects any packet over 16MB.
"""

import argparse
import hashlib
import os
import sys

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text

# Parents before children, so a foreign key never points at a row that has not
# arrived yet.
_TABLE_ORDER = [
    "prompts",
    "actions", "pagefile", "testcase", "testfile", "featurefile", "screenshot",
    "iqea_runs",        # before iqea_artifacts: artifacts reference runs
    "iqea_artifacts",
    "iqea_xpaths",
]

# Azure caps max_allowed_packet at 16MB. Stay well under it — the limit applies
# to the whole statement, not one row.
_BATCH_BYTES = 4 * 1024 * 1024
_BATCH_ROWS = 200


def _legacy_url():
    """PostgreSQL URL from [DATABASE_postgres_legacy]."""
    from urllib.parse import quote_plus
    from config.settings_reader import config

    section = "DATABASE_postgres_legacy"
    if not config.has_section(section):
        raise RuntimeError(
            f"settings.ini has no [{section}] section — nothing to migrate from."
        )

    def get(option, default=""):
        return config.get(section, option, fallback=default).strip()

    return (f"postgresql+psycopg2://{quote_plus(get('DB_USER', 'postgres'))}:"
            f"{quote_plus(get('DB_PASSWORD'))}@{get('DB_HOST', 'localhost')}:"
            f"{get('DB_PORT', '5432')}/{get('DB_NAME')}")


def _target_url(env):
    if env:
        os.environ["IQEA_EXECUTION_TYPE"] = env
    from config.settings_reader import get_db_url
    return get_db_url()


def _row_bytes(row):
    """Rough serialised size of a row, for batching."""
    total = 0
    for value in row.values():
        if isinstance(value, (bytes, bytearray)):
            total += len(value)
        elif value is not None:
            total += len(str(value))
    return total + 64  # per-row statement overhead


def _adapt(table_name, row, target_columns):
    """
    Reshape a PostgreSQL row for the MySQL table.

    Two things differ. Columns the target does not have are dropped (the source
    may predate a change). And iqea_xpaths.xpath_hash exists only on MySQL,
    where it carries the unique constraint that (page_name, xpath) cannot —
    MySQL will not index an unbounded column — so it is computed here.
    """
    adapted = {k: v for k, v in row.items() if k in target_columns}

    if table_name == "iqea_xpaths" and "xpath_hash" in target_columns:
        if not adapted.get("xpath_hash"):
            xpath = adapted.get("xpath") or ""
            adapted["xpath_hash"] = hashlib.sha256(
                xpath.encode("utf-8")).hexdigest()

    # PostgreSQL booleans arrive as bool; MySQL TINYINT(1) takes them directly.
    return adapted


def _existing_ids(conn, table):
    return {row[0] for row in conn.execute(select(table.c.id))}


def migrate_table(source_conn, target_engine, table_name, source_meta,
                  dry_run=False):
    if table_name not in source_meta.tables:
        return 0, 0, "not in source"

    source_table = source_meta.tables[table_name]

    target_meta = MetaData()
    try:
        target_table = Table(table_name, target_meta, autoload_with=target_engine)
    except Exception:
        return 0, 0, "not in target"

    target_columns = set(target_table.c.keys())

    rows = [dict(r._mapping) for r in
            source_conn.execute(select(source_table).order_by(source_table.c.id))]
    if not rows:
        return 0, 0, "source empty"

    with target_engine.begin() as target_conn:
        already = _existing_ids(target_conn, target_table)
        pending = [_adapt(table_name, r, target_columns)
                   for r in rows if r["id"] not in already]
        skipped = len(rows) - len(pending)

        if dry_run or not pending:
            return len(pending), skipped, ""

        batch, batch_bytes = [], 0
        for row in pending:
            size = _row_bytes(row)
            # Flush before adding a row that would push the statement over the
            # packet limit, and before the row-count cap.
            if batch and (batch_bytes + size > _BATCH_BYTES
                          or len(batch) >= _BATCH_ROWS):
                target_conn.execute(target_table.insert(), batch)
                batch, batch_bytes = [], 0
            batch.append(row)
            batch_bytes += size

        if batch:
            target_conn.execute(target_table.insert(), batch)

        # Explicit ids were inserted, so the counter still points at 1 and the
        # next app-generated insert would collide. Move it past the highest id.
        highest = target_conn.execute(
            select(func.max(target_table.c.id))).scalar()
        if highest:
            target_conn.execute(
                text(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = {highest + 1}"))

    return len(pending), skipped, ""


def migrate(env, dry_run=False):
    source_engine = create_engine(_legacy_url())
    target_engine = create_engine(_target_url(env))

    from config.settings_reader import get_db_config
    cfg = get_db_config()
    print(f"\n=== {env or 'current'} -> "
          f"{cfg['user']}@{cfg['host']}/{cfg['database']} ===")

    source_meta = MetaData()
    available = set(inspect(source_engine).get_table_names())
    source_meta.reflect(bind=source_engine,
                        only=[t for t in _TABLE_ORDER if t in available])

    total_copied = 0
    with source_engine.connect() as source_conn:
        for table_name in _TABLE_ORDER:
            copied, skipped, note = migrate_table(
                source_conn, target_engine, table_name, source_meta, dry_run)
            total_copied += copied
            suffix = f"  ({note})" if note else ""
            print(f"{'DRY ' if dry_run else ''}{table_name:<16} "
                  f"copied {copied:>5}, skipped {skipped:>5}{suffix}")

    source_engine.dispose()
    target_engine.dispose()
    print(f"{'Would copy' if dry_run else 'Copied'} {total_copied} rows.")
    return total_copied


def verify(env):
    """Row counts and a blob checksum, source against target.

    The checksum matters more than the counts: MySQL's plain BLOB silently
    truncates at 64KB, so a screenshot can migrate as a row that is present,
    counted, and corrupt.
    """
    source_engine = create_engine(_legacy_url())
    target_engine = create_engine(_target_url(env))

    from config.settings_reader import get_db_config
    cfg = get_db_config()
    print(f"\n=== verify {env or 'current'} -> {cfg['database']} ===")
    print(f"{'table':<16}{'postgres':>10}{'mysql':>10}   status")
    print("-" * 48)

    blob_columns = {"actions": "file_data", "pagefile": "file_data",
                    "testcase": "file_data", "testfile": "file_data",
                    "featurefile": "file_data", "screenshot": "image_data",
                    "iqea_artifacts": "file_data"}

    ok = True
    with source_engine.connect() as sc, target_engine.connect() as tc:
        source_tables = set(inspect(source_engine).get_table_names())
        target_tables = set(inspect(target_engine).get_table_names())

        for table_name in _TABLE_ORDER:
            if table_name not in source_tables or table_name not in target_tables:
                continue
            src = sc.execute(text(f"SELECT count(*) FROM {table_name}")).scalar()
            tgt = tc.execute(text(f"SELECT count(*) FROM `{table_name}`")).scalar()

            status = "ok" if src == tgt else "COUNT MISMATCH"
            if src != tgt:
                ok = False

            column = blob_columns.get(table_name)
            if column and src and src == tgt:
                src_bytes = sc.execute(text(
                    f"SELECT coalesce(sum(length({column})),0) FROM {table_name}")).scalar()
                tgt_bytes = tc.execute(text(
                    f"SELECT coalesce(sum(length(`{column}`)),0) FROM `{table_name}`")).scalar()
                if int(src_bytes) != int(tgt_bytes):
                    status = (f"BYTES DIFFER src={src_bytes} tgt={tgt_bytes}")
                    ok = False
                else:
                    status = f"ok, {int(src_bytes):,} bytes match"

            print(f"{table_name:<16}{src:>10}{tgt:>10}   {status}")

    source_engine.dispose()
    target_engine.dispose()
    print("\nAll tables match." if ok else "\n⚠️ Differences above.")
    return ok


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=["local", "azure", "both"],
                        default="local")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", action="store_true",
                        help="compare counts and blob sizes, copying nothing")
    args = parser.parse_args()

    targets = ["local", "azure"] if args.env == "both" else [args.env]

    try:
        for target in targets:
            if args.verify:
                verify(target)
            else:
                migrate(target, args.dry_run)
                if not args.dry_run:
                    verify(target)
    except Exception as exc:
        print(f"\n❌ Migration failed: {type(exc).__name__}: {exc}")
        sys.exit(1)
