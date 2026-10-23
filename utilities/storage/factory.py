"""
Resolves settings.ini's `source` once, so call sites never have to.

Every `if source == "file" / elif source == "database"` pair in the app is a
place the two branches can drift, and several already have. Import the store
instead:

    from utilities.storage import get_store, kinds

    store = get_store()
    store.save(kinds.ACTION, page_name, workflow_text, created_by=user())
"""

import threading

from config.settings_reader import get_source

_lock = threading.Lock()
_store = None
_xpath_store = None


def _build():
    """Instantiate the pair for the configured source.

    DbStore is imported here rather than at module scope so a source=file run
    never constructs the engine — a local user with no MySQL server should not
    need one to open the app.
    """
    source = (get_source() or "file").strip().lower()

    if source == "database":
        from utilities.storage.db_store import DbStore, DbXPathStore
        return DbStore(), DbXPathStore()

    from utilities.storage.file_store import FileStore, FileXPathStore
    return FileStore(), FileXPathStore()


def _ensure():
    global _store, _xpath_store
    if _store is None:
        with _lock:
            if _store is None:
                _store, _xpath_store = _build()
    return _store, _xpath_store


def get_store():
    """The ArtifactStore for this run."""
    return _ensure()[0]


def get_xpath_store():
    """The XPathStore for this run."""
    return _ensure()[1]


def is_database_backed():
    """True when artifacts are going to MySQL. Use only for things that are
    genuinely database-only — version history, run grouping — not to pick a
    save path; that is what the store is for.

    Reads the setting rather than isinstance-ing the store, so asking the
    question does not import DbStore and build an engine on a file-mode run.
    """
    return (get_source() or "file").strip().lower() == "database"


def reset():
    """Drop the cached stores so the next call re-reads settings.ini. For tests
    and for the settings screen, not for normal request flow."""
    global _store, _xpath_store
    with _lock:
        _store = None
        _xpath_store = None
