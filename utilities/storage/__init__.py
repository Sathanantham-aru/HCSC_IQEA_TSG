"""
IQEA artifact storage.

One interface over the two places IQEA keeps what it produces — the output/
folders and the application MySQL database — so that call sites describe what
they are saving rather than branching on settings.ini.

    from utilities.storage import get_store, get_xpath_store, kinds

    store = get_store()
    store.save(kinds.TEST_CASE, "Add to Cart", dataframe, created_by=user)
    names = store.list(kinds.TEST_CASE)
    text  = store.get_text(kinds.ACTION, "login.txt")

`kinds` is the registry of what can be stored; see kinds.py for the list.
"""

from utilities.storage import kinds
from utilities.storage.base import (ArtifactStore, ArtifactRef, XPathStore,
                                    to_bytes)
from utilities.storage.factory import (get_store, get_xpath_store,
                                       is_database_backed, reset)

__all__ = [
    "kinds",
    "ArtifactStore", "ArtifactRef", "XPathStore", "to_bytes",
    "get_store", "get_xpath_store", "is_database_backed", "reset",
]
