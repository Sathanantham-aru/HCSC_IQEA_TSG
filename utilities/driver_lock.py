"""
Per-driver serialisation for the recorder's background threads.

A Selenium WebDriver is NOT thread-safe, and the recorder runs four monitor
threads plus the Streamlit thread against a single driver. The dangerous pattern
is `driver.switch_to.window(...)` — it mutates state shared by every caller, so
while thread 1 is switching windows to inject JS, thread 2 can read
`driver.current_url` and get the *other* window's URL, and `get_recorded_actions`
can read localStorage from the wrong window entirely.

Locally each WebDriver command is ~1-5 ms, so the race window is tiny and it
mostly gets away with it. Against a Selenium Grid over HTTP each command is
~20-100 ms, widening that window by roughly 20x — and with many people
recording at once the Grid is under load, widening it further. This is the
change most likely to decide whether recording is reliable in Azure.

The lock is PER DRIVER, not global: every user has their own browser, so one
person's recording never blocks another's.

Usage — wrap the critical section, never the sleep:

    from utilities.driver_lock import driver_guard

    while not stop_flag["stop"]:
        with driver_guard(driver):
            ...                      # every driver.* call for this iteration
        time.sleep(0.5)              # OUTSIDE the guard
"""

import threading
from contextlib import contextmanager

# driver key -> RLock. Re-entrant so nested guards in the same thread are safe.
_locks = {}
_registry_lock = threading.Lock()


def _key(driver):
    """
    Stable identity for a driver. session_id survives attribute access on a live
    session; id() is the fallback for a driver whose session already ended.
    """
    try:
        session_id = getattr(driver, "session_id", None)
        if session_id:
            return session_id
    except Exception:
        pass
    return id(driver)


def get_lock(driver):
    """Return (creating if needed) the RLock guarding this driver."""
    key = _key(driver)
    with _registry_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _locks[key] = lock
        return lock


@contextmanager
def driver_guard(driver, timeout=30):
    """
    Serialise access to `driver` for the duration of the block.

    `timeout` stops a wedged thread from deadlocking the recorder forever: if the
    lock cannot be taken in time the block still runs, because a slightly racy
    read is better than a recorder that hangs and loses the whole session. The
    skip is logged so it is visible rather than silent.
    """
    if driver is None:
        yield driver
        return

    lock = get_lock(driver)
    acquired = lock.acquire(timeout=timeout)
    if not acquired:
        print("[driver_lock] WARNING: could not acquire driver lock in %ss — "
              "proceeding unguarded (a monitor thread may be stuck)" % timeout)
    try:
        yield driver
    finally:
        if acquired:
            lock.release()


def release_driver(driver):
    """Drop the lock entry for a finished driver so the registry cannot grow
    without bound across many sessions."""
    key = _key(driver)
    with _registry_lock:
        _locks.pop(key, None)


def active_lock_count():
    """Diagnostics: how many drivers currently have locks registered."""
    with _registry_lock:
        return len(_locks)
