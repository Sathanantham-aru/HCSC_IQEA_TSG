"""
Database session management for the IQEA application store.

handler.py builds one module-level `Session()` at import and every function
reuses it. That works for a single user on a laptop and fails in two ways once
the app is shared: SQLAlchemy Sessions are not thread-safe (the recorder runs
four monitor threads against the same driver and the same handler), and once any
statement errors the Session stays in a failed transaction until something calls
rollback — so one user's bad write turns into every user's "current transaction
is aborted" until the container restarts.

What this module provides instead:

  session_scope()   context manager: commits on success, rolls back on error,
                    always closes. Use it for anything that writes.
  get_session()     the thread-local Session, for read-only call sites that are
                    not ready to be restructured yet.

Both share one engine, so the connection pool is still shared process-wide.
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from config.settings_reader import get_db_url

# pool_pre_ping costs one cheap round trip per checkout and buys immunity to the
# connection drops you otherwise only find out about through a failed save:
# Azure MySQL closes idle connections (wait_timeout), and Streamlit sessions sit
# idle for long stretches while someone records a workflow.
#
# READ COMMITTED is load-bearing, not a preference. InnoDB defaults to
# REPEATABLE READ, under which a transaction keeps the snapshot it had at its
# first read for its whole life. Writes go through session_scope() — a separate,
# short transaction — while reads come from the long-lived scoped session below,
# which in a Streamlit run is never explicitly committed. On REPEATABLE READ
# that reader would never observe anything saved after its first query: the file
# is written, the commit succeeds, and the picker still does not list it.
# PostgreSQL defaults to READ COMMITTED, which is the behaviour all of this code
# was written against, so this restores it rather than introducing anything new.
_engine = create_engine(
    get_db_url(),
    pool_pre_ping=True,
    pool_recycle=1800,
    isolation_level="READ COMMITTED",
    future=True,
)

# scoped_session hands each thread its own Session, so the recorder threads stop
# sharing one with the main Streamlit thread.
SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
ScopedSession = scoped_session(SessionFactory)


def get_engine():
    return _engine


def get_session():
    """The calling thread's Session. Prefer session_scope() for writes."""
    return ScopedSession()


@contextmanager
def session_scope():
    """
    Transactional scope around a series of operations.

        with session_scope() as s:
            s.add(row)

    Commits on clean exit, rolls back on any exception, and always returns the
    connection to the pool.
    """
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def remove_session():
    """Drop this thread's scoped Session. Call at the end of a worker thread so
    its connection goes back to the pool rather than being held until the thread
    object is collected."""
    ScopedSession.remove()
