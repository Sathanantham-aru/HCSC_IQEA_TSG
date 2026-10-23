"""
Database-backed ArtifactStore — what runs when settings.ini has source=database.

Unlike FileStore, saving the same name twice keeps both: the new row becomes
version N+1 and takes the is_latest flag, the old row keeps its bytes. That is
the fix for the behaviour that prompted this work — the old tables also kept
every save, but with no version column and no ORDER BY on the lookups, asking
for a name returned whichever row the planner happened to produce first, which
in practice was the oldest.
"""

import hashlib

import pandas as pd
from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert as mysql_insert

from utilities.db_utils.models import IqeaArtifact, IqeaRun, IqeaXPath
from utilities.db_utils.session import session_scope, get_session
from utilities.storage import kinds
from utilities.storage.base import ArtifactStore, ArtifactRef, XPathStore, to_bytes

_XPATH_COLUMNS = ["Element", "XPath", "Page Name", "Type", "Source URL"]


def _to_ref(row):
    return ArtifactRef(
        kind=row.kind, name=row.name, ext=row.ext or "", version=row.version,
        is_latest=row.is_latest, size_bytes=row.size_bytes or 0,
        created_by=row.created_by, created_on=row.created_on,
        meta=row.meta or {}, artifact_id=row.id, run_id=row.run_id,
    )


class DbStore(ArtifactStore):

    # ── Runs ────────────────────────────────────────────────────────────────

    def start_run(self, run_type, run_name=None, created_by=None, meta=None):
        """Open a run so everything produced by one session can be grouped.
        Optional — artifacts save fine with run_id left None."""
        with session_scope() as session:
            run = IqeaRun(run_type=run_type, run_name=run_name,
                          created_by=created_by, meta=meta, status="running")
            session.add(run)
            session.flush()
            return run.id

    def finish_run(self, run_id, status="completed"):
        if not run_id:
            return
        with session_scope() as session:
            run = session.get(IqeaRun, run_id)
            if run:
                run.status = status
                run.finished_on = func.now()

    # ── ArtifactStore ───────────────────────────────────────────────────────

    def save(self, kind, name, data, *, ext=None, meta=None, run_id=None,
             created_by=None):
        kinds.get_spec(kind)  # reject unknown kinds before writing
        name, resolved_ext = kinds.split_name(kind, name)
        if ext:
            resolved_ext = ext if ext.startswith(".") else f".{ext}"
            name = f"{name.rsplit('.', 1)[0]}{resolved_ext}" if "." in name \
                else f"{name}{resolved_ext}"

        payload = to_bytes(data, resolved_ext)

        with session_scope() as session:
            # Version numbers are per (kind, name); COALESCE covers the first save.
            current_max = session.query(
                func.coalesce(func.max(IqeaArtifact.version), 0)
            ).filter(
                IqeaArtifact.kind == kind, IqeaArtifact.name == name
            ).scalar()

            # Demote the previous latest in the same transaction as the insert,
            # so a crash between the two cannot leave two rows flagged latest.
            session.query(IqeaArtifact).filter(
                IqeaArtifact.kind == kind,
                IqeaArtifact.name == name,
                IqeaArtifact.is_latest.is_(True),
            ).update({"is_latest": False}, synchronize_session=False)

            row = IqeaArtifact(
                run_id=run_id, kind=kind, name=name, ext=resolved_ext,
                version=current_max + 1, is_latest=True,
                mime=kinds.mime_for(resolved_ext), size_bytes=len(payload),
                file_data=payload, meta=meta, created_by=created_by,
            )
            session.add(row)
            session.flush()
            return _to_ref(row)

    def _find(self, kind, name, version=None):
        """The row for a caller-supplied name, or None. Shared by read() and
        versions() so both accept a name with or without its extension."""
        session = get_session()
        base_query = session.query(IqeaArtifact).filter(
            IqeaArtifact.kind == kind)
        base_query = (base_query.filter(IqeaArtifact.version == version)
                      if version
                      else base_query.filter(IqeaArtifact.is_latest.is_(True)))

        candidates, stem = kinds.resolve_candidates(kind, name)
        for candidate in candidates:
            row = base_query.filter(IqeaArtifact.name == candidate).first()
            if row:
                return row

        if stem:
            # LIKE, so escape what LIKE treats as wildcards in the stem.
            escaped = stem.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            return (base_query
                    .filter(IqeaArtifact.name.like(f"{escaped}.%", escape="\\"))
                    .order_by(IqeaArtifact.created_on.desc())
                    .first())
        return None

    def read(self, kind, name, *, version=None):
        row = self._find(kind, name, version)
        if not row or row.file_data is None:
            return None
        return row.file_data, _to_ref(row)

    def list(self, kind):
        session = get_session()
        rows = session.query(IqeaArtifact.name).filter(
            IqeaArtifact.kind == kind,
            IqeaArtifact.is_latest.is_(True),
        ).order_by(IqeaArtifact.name).all()
        return [row[0] for row in rows]

    def refs(self, kind):
        session = get_session()
        rows = session.query(IqeaArtifact).filter(
            IqeaArtifact.kind == kind,
            IqeaArtifact.is_latest.is_(True),
        ).order_by(IqeaArtifact.created_on.desc()).all()
        return [_to_ref(row) for row in rows]

    def versions(self, kind, name):
        # Resolve the caller's name to the stored one first, so "login" and
        # "login.py" list the same history.
        current = self._find(kind, name)
        if not current:
            return []
        session = get_session()
        rows = session.query(IqeaArtifact).filter(
            IqeaArtifact.kind == kind, IqeaArtifact.name == current.name,
        ).order_by(IqeaArtifact.version.desc()).all()
        return [_to_ref(row) for row in rows]

    def refs_for_run(self, run_id):
        session = get_session()
        rows = session.query(IqeaArtifact).filter(
            IqeaArtifact.run_id == run_id
        ).order_by(IqeaArtifact.created_on).all()
        return [_to_ref(row) for row in rows]

    def delete(self, kind, name, *, version=None):
        current = self._find(kind, name) or self._find(kind, name, version)
        if not current:
            return False
        name = current.name

        with session_scope() as session:
            query = session.query(IqeaArtifact).filter(
                IqeaArtifact.kind == kind, IqeaArtifact.name == name)
            if version:
                query = query.filter(IqeaArtifact.version == version)

            removed = query.delete(synchronize_session=False)
            if not removed:
                return False

            # Deleting the current version would otherwise leave the name with
            # history but nothing flagged latest, making get() return None while
            # versions() still lists rows. Promote the newest survivor.
            still_latest = session.query(IqeaArtifact).filter(
                IqeaArtifact.kind == kind, IqeaArtifact.name == name,
                IqeaArtifact.is_latest.is_(True),
            ).count()
            if not still_latest:
                newest = session.query(IqeaArtifact).filter(
                    IqeaArtifact.kind == kind, IqeaArtifact.name == name,
                ).order_by(IqeaArtifact.version.desc()).first()
                if newest:
                    newest.is_latest = True
            return True


class DbXPathStore(XPathStore):
    """Locators as rows in iqea_xpaths.

    The point of not storing the workbook as a blob: page file generation asks
    for one page's locators, and two people can add locators at the same time
    without the second overwriting the first — which is exactly what the shared
    xpath_details.xlsx does today.
    """

    def add(self, page_name, rows, *, created_by=None, source_url=None):
        if not rows:
            return 0

        payload = []
        for row in rows:
            xpath = (row.get("XPath") or row.get("xpath") or "").strip()
            if not xpath:
                continue
            payload.append({
                "page_name": page_name,
                "element": row.get("Element") or row.get("element"),
                "xpath": xpath,
                # The unique key is (page_name, xpath_hash) rather than
                # (page_name, xpath): MySQL cannot put an unbounded column in a
                # constraint, and capping XPath length to fit would be a real
                # limitation. See the note on IqeaXPath.
                "xpath_hash": hashlib.sha256(xpath.encode("utf-8")).hexdigest(),
                "xpath_type": row.get("Type") or row.get("xpath_type"),
                "source_url": row.get("Source URL") or source_url,
                "is_active": True,
                "created_by": created_by,
            })

        if not payload:
            return 0

        with session_scope() as session:
            # Re-adding a locator already on the page refreshes it rather than
            # failing the unique constraint — the UI lets you re-collect a page.
            # Re-collecting also revives a previously soft-deleted locator, which
            # is why is_active is forced back on.
            statement = mysql_insert(IqeaXPath).values(payload)
            statement = statement.on_duplicate_key_update(
                element=statement.inserted.element,
                xpath_type=statement.inserted.xpath_type,
                source_url=statement.inserted.source_url,
                is_active=True,
            )
            session.execute(statement)

        return len(payload)

    def get(self, page_name=None):
        session = get_session()
        query = session.query(IqeaXPath).filter(IqeaXPath.is_active.is_(True))
        if page_name:
            query = query.filter(IqeaXPath.page_name == page_name)

        rows = query.order_by(IqeaXPath.page_name, IqeaXPath.id).all()
        if not rows:
            return pd.DataFrame(columns=_XPATH_COLUMNS)

        # Column names match what the page file prompt and the file-mode
        # workbook both use, so downstream code does not care which store ran.
        return pd.DataFrame([{
            "Element": row.element,
            "XPath": row.xpath,
            "Page Name": row.page_name,
            "Type": row.xpath_type,
            "Source URL": row.source_url,
        } for row in rows])

    def pages(self):
        session = get_session()
        rows = session.query(IqeaXPath.page_name).filter(
            IqeaXPath.is_active.is_(True)
        ).distinct().order_by(IqeaXPath.page_name).all()
        return [row[0] for row in rows]

    def delete_page(self, page_name):
        with session_scope() as session:
            # Soft delete — keeps the record that the locator once existed.
            return session.query(IqeaXPath).filter(
                IqeaXPath.page_name == page_name,
                IqeaXPath.is_active.is_(True),
            ).update({"is_active": False}, synchronize_session=False)
