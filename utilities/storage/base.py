"""
The storage interface every IQEA call site talks to.

Today each place that produces an artifact carries its own `if source == "file"
/ elif source == "database"` pair — roughly sixty of them across
action_new_xpath_subway_TMT.py and Utilities_Xpath.py, each one an independent
chance for the two branches to drift apart. They already have: the recorder
skips its cleanup on the database branch, the desktop recorder and test data
generator have no database branch at all, and the combined test case sheet
returned an unbound variable.

A call site should say what it is saving, not where it goes:

    store = get_store()
    store.save(kinds.TEST_CASE, name, dataframe)

and the store resolves `source` once, at startup.
"""

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from utilities.storage import kinds


@dataclass
class ArtifactRef:
    """What a store hands back about one stored artifact. Deliberately the same
    shape from FileStore and DbStore so the UI never branches on which is live."""
    kind: str
    name: str
    ext: str = ""
    version: int = 1
    is_latest: bool = True
    size_bytes: int = 0
    created_by: Optional[str] = None
    created_on: Optional[datetime] = None
    meta: dict = field(default_factory=dict)
    # Set by FileStore only; the database has no path.
    path: Optional[str] = None
    # Set by DbStore only.
    artifact_id: Optional[int] = None
    run_id: Optional[int] = None

    @property
    def label(self):
        return f"{self.name} (v{self.version})" if self.version > 1 else self.name


def to_bytes(data: Any, ext: str = "") -> bytes:
    """
    Normalise whatever a call site produced into bytes.

    Call sites variously hand over bytes, a string, the recorder's list of action
    lines, or a pandas DataFrame. Centralising the conversion is what stops the
    class of bug where a helper assumed one of those — save_testcases_to_db
    called .to_excel() on its argument, so the two call sites that passed CSV
    text raised AttributeError into an except block that printed and moved on.
    """
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)

    if isinstance(data, str):
        return data.encode("utf-8")

    if isinstance(data, (list, tuple)):
        return "\n".join(str(line) for line in data).encode("utf-8")

    # Imported lazily: pandas is heavy and most saves are not frames.
    try:
        import pandas as pd
    except ImportError:
        pd = None

    if pd is not None and isinstance(data, pd.DataFrame):
        if ext == ".csv":
            return data.to_csv(index=False).encode("utf-8")
        buffer = io.BytesIO()
        data.to_excel(buffer, index=False)
        buffer.seek(0)
        return buffer.read()

    if data is None:
        raise ValueError("Cannot store None as an artifact")

    return str(data).encode("utf-8")


class ArtifactStore(ABC):
    """Save and read the files IQEA produces, without the caller knowing where
    they live."""

    @abstractmethod
    def save(self, kind, name, data, *, ext=None, meta=None, run_id=None,
             created_by=None) -> ArtifactRef:
        """Store `data` under (kind, name). Returns a ref to what was written."""

    @abstractmethod
    def read(self, kind, name, *, version=None):
        """
        (bytes, ArtifactRef) for a stored artifact, or None.

        The single lookup primitive: get() and get_text() are built on it so
        that the extension used to interpret the bytes is the one the artifact
        was actually stored with. Resolving that separately is what broke
        reading anything saved with a non-default extension — the reader
        appended the kind's default instead and looked for a name that was
        never written.

        Implementations must accept `name` with or without its extension.
        """

    @abstractmethod
    def list(self, kind) -> list:
        """Names of the current version of every artifact of `kind`."""

    @abstractmethod
    def refs(self, kind) -> list:
        """As list(), but full ArtifactRefs — for a UI that shows dates, sizes
        and version numbers."""

    @abstractmethod
    def versions(self, kind, name) -> list:
        """Every stored version of one name, newest first."""

    @abstractmethod
    def delete(self, kind, name, *, version=None) -> bool:
        """Remove one version, or every version when `version` is None."""

    # ── Shared conveniences, all built on read() ────────────────────────────

    def get(self, kind, name, *, version=None) -> Optional[bytes]:
        """Raw bytes of the latest version, or of `version` when given.
        None when there is nothing stored under that name."""
        found = self.read(kind, name, version=version)
        return found[0] if found else None

    def resolve(self, kind, name, *, version=None) -> Optional[ArtifactRef]:
        """What is actually stored under this name — real name, extension,
        version — or None."""
        found = self.read(kind, name, version=version)
        return found[1] if found else None

    def get_text(self, kind, name, *, version=None, errors="ignore"):
        """Text of an artifact. Excel is rendered as a readable table, because
        most text callers are assembling an LLM prompt."""
        found = self.read(kind, name, version=version)
        if not found:
            return None

        raw, ref = found
        if (ref.ext or "").lower() in (".xlsx", ".xls"):
            try:
                import pandas as pd
                return pd.read_excel(io.BytesIO(raw)).to_string(index=False)
            except Exception as exc:
                print(f"❌ Could not read workbook '{ref.name}': {exc}")
                return None

        return raw.decode("utf-8", errors=errors)

    def exists(self, kind, name) -> bool:
        return self.read(kind, name) is not None

    def get_many_text(self, kind, names, *, separator=True):
        """Concatenate several artifacts into one prompt-ready blob.

        Returns (text, missing_names) so the caller can tell the user which
        selections produced nothing rather than silently sending a short prompt.
        """
        chunks, missing = [], []
        for name in names:
            content = self.get_text(kind, name)
            if content:
                chunks.append(f"\n### {name} ###\n{content}\n"
                              if separator else content)
            else:
                missing.append(name)
        return "".join(chunks), missing


class XPathStore(ABC):
    """Locators are kept apart from ArtifactStore because they are queried by
    page rather than fetched whole: page file generation asks for the rows of
    one page, not for a workbook it then has to filter."""

    @abstractmethod
    def add(self, page_name, rows, *, created_by=None, source_url=None) -> int:
        """Upsert locator rows for a page. `rows` are dicts carrying at least
        an 'XPath'; 'Element' and 'Type' are used when present. Returns the
        number written."""

    @abstractmethod
    def get(self, page_name=None):
        """A DataFrame of locators — one page's, or all of them. Columns match
        what the page file prompt expects: Element, XPath, Page Name."""

    @abstractmethod
    def pages(self) -> list:
        """Distinct page names that have locators."""

    @abstractmethod
    def delete_page(self, page_name) -> int:
        """Remove a page's locators. Returns how many went."""
