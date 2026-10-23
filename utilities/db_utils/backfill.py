"""
Copy the legacy per-type tables into iqea_artifacts.

    python -m utilities.db_utils.backfill --dry-run
    python -m utilities.db_utils.backfill

Additive and idempotent: it creates the new tables if they are missing, never
writes to or drops the old ones, and records each source row's id in the new
row's meta so a second run skips what it already moved. The old tables stay in
place — handler.py keeps reading them — until the migrated data has been
checked in the UI.

Version numbers come from insertion order. The legacy tables kept every save as
a separate row with no way to tell which was current, so for each name the rows
are ordered by id and numbered 1..N, with the highest flagged is_latest. That
turns the duplicate rows that were causing stale reads into real history.
"""

import argparse
import sys
from collections import defaultdict

from sqlalchemy import create_engine

from config.settings_reader import get_db_url
from utilities.db_utils.base import Base
from utilities.db_utils.models import (Action, Pagefile, Testcasefile, Testfile,
                                       Fetaurefile, Screenshot, IqeaArtifact)
from utilities.db_utils.session import session_scope
from utilities.storage import kinds

# (legacy model, name column, data column, target kind, legacy table label)
_MIGRATIONS = [
    (Action,       "action_name",    "file_data",  kinds.ACTION,       "actions"),
    (Pagefile,     "pagefile_name",  "file_data",  kinds.PAGE_FILE,    "pagefile"),
    (Testfile,     "testfile_name",  "file_data",  kinds.TEST_FILE,    "testfile"),
    (Testcasefile, "testcase_name",  "file_data",  kinds.TEST_CASE,    "testcase"),
    (Fetaurefile,  "featurefile_name", "file_data", kinds.FEATURE_FILE, "featurefile"),
    (Screenshot,   None,             "image_data", kinds.SCREENSHOT,   "screenshot"),
]


def create_new_tables():
    """Create iqea_runs / iqea_artifacts / iqea_xpaths if absent. create_all
    only adds what is missing, so the legacy tables are untouched."""
    engine = create_engine(get_db_url())
    Base.metadata.create_all(engine)
    print("✅ New tables present (iqea_runs, iqea_artifacts, iqea_xpaths)")


def _legacy_name(row, name_field, kind):
    """The name to store the migrated row under."""
    if name_field:
        return getattr(row, name_field)
    # Screenshots had no filename — the picker built one from page name and id,
    # so keep that shape and give it the extension the download needs.
    return f"{row.page_name}_{row.id}.png"


def _already_migrated(session, kind):
    """Legacy ids of rows this kind has already taken, so a rerun is a no-op."""
    done = set()
    rows = session.query(IqeaArtifact.meta).filter(
        IqeaArtifact.kind == kind).all()
    for (meta,) in rows:
        if meta and meta.get("legacy_id") is not None:
            done.add((meta.get("legacy_table"), meta["legacy_id"]))
    return done


def backfill(dry_run=False):
    totals = defaultdict(int)

    with session_scope() as session:
        for model, name_field, data_field, kind, table_label in _MIGRATIONS:
            rows = session.query(model).order_by(model.id).all()
            if not rows:
                print(f"—  {table_label}: empty")
                continue

            done = _already_migrated(session, kind)

            # Group by name first so version numbers run 1..N per name rather
            # than per table.
            by_name = defaultdict(list)
            for row in rows:
                by_name[_legacy_name(row, name_field, kind)].append(row)

            migrated = skipped = 0
            for raw_name, group in by_name.items():
                name, ext = kinds.split_name(kind, raw_name or "unnamed")
                total = len(group)

                for index, row in enumerate(group, start=1):
                    if (table_label, row.id) in done:
                        skipped += 1
                        continue

                    payload = getattr(row, data_field)
                    if not payload:
                        skipped += 1
                        continue

                    meta = {"legacy_table": table_label, "legacy_id": row.id}
                    if kind == kinds.SCREENSHOT:
                        meta["url"] = row.url
                        meta["page_name"] = row.page_name

                    if not dry_run:
                        session.add(IqeaArtifact(
                            kind=kind, name=name, ext=ext,
                            version=index, is_latest=(index == total),
                            mime=kinds.mime_for(ext), size_bytes=len(payload),
                            file_data=payload, meta=meta,
                            created_by=getattr(row, "created_by", None),
                            created_on=getattr(row, "created_on", None),
                        ))
                    migrated += 1

            totals[kind] += migrated
            print(f"{'DRY ' if dry_run else ''}✅ {table_label:<12} → "
                  f"{kind:<14} {migrated:>4} migrated, {skipped:>4} skipped "
                  f"({len(by_name)} distinct names)")

        if dry_run:
            session.rollback()

    print("\n" + ("Nothing written (dry run)." if dry_run else
                  f"Done. {sum(totals.values())} artifacts written."))
    return dict(totals)


def verify():
    """Row counts old vs new, so the migration can be eyeballed before the old
    tables are trusted less."""
    with session_scope() as session:
        print(f"{'legacy table':<14} {'legacy rows':>12} {'new rows':>10}")
        print("-" * 38)
        for model, _, _, kind, table_label in _MIGRATIONS:
            legacy = session.query(model).count()
            new = session.query(IqeaArtifact).filter(
                IqeaArtifact.kind == kind).count()
            flag = "" if legacy == new else "   ⚠️ differs"
            print(f"{table_label:<14} {legacy:>12} {new:>10}{flag}")


if __name__ == "__main__":
    # A Windows console defaults to cp1252, which cannot encode the status
    # glyphs below — without this the script dies in print() after having
    # already done the work, which reads as a failure when it was a success.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would move without writing")
    parser.add_argument("--verify", action="store_true",
                        help="compare legacy and migrated row counts")
    args = parser.parse_args()

    try:
        create_new_tables()
        if args.verify:
            verify()
        else:
            backfill(dry_run=args.dry_run)
            if not args.dry_run:
                print()
                verify()
    except Exception as exc:
        print(f"❌ Backfill failed: {exc}")
        sys.exit(1)
