"""
Filesystem-backed ArtifactStore — what runs when settings.ini has source=file.

Deliberately keeps the semantics the app has today: saving a name that already
exists overwrites it, so a local run behaves exactly as it did before the store
existed and nobody's output folders change shape. Version history is a database
feature; here versions() reports the single file on disk.
"""

import os
import shutil
from datetime import datetime

import pandas as pd

from utilities.storage import kinds
from utilities.storage.base import ArtifactStore, ArtifactRef, XPathStore, to_bytes

# Resolved from this file rather than os.getcwd(): identical when the app is
# launched from the repo root the way run_ai.bat does it, but it does not break
# if something changes the working directory mid-run.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_OUTPUT_ROOT = os.environ.get("IQEA_OUTPUT_ROOT") or os.path.join(_REPO_ROOT,
                                                                 "output")

# Where the locator workbook lives — unchanged from Utilities_Xpath.xpath_file.
_XPATH_FILE = os.path.join(_OUTPUT_ROOT, "xpath_generator", "xpath_details.xlsx")

_XPATH_COLUMNS = ["Element", "XPath", "Page Name", "Type", "Source URL"]


def _safe(name):
    """Strip what Windows will not accept in a filename. The app already does
    this inline in several places with slightly different character sets."""
    cleaned = "".join(c for c in name if c.isalnum() or c in "._- ()[]").strip()
    return cleaned or "unnamed"


class FileStore(ArtifactStore):

    def folder_for(self, kind):
        spec = kinds.get_spec(kind)
        path = os.path.join(_OUTPUT_ROOT, spec.folder)
        os.makedirs(path, exist_ok=True)
        return path

    def path_for(self, kind, name):
        """Where a save of this name goes."""
        name, _ = kinds.split_name(kind, name)
        return os.path.join(self.folder_for(kind), _safe(name))

    def resolve_path(self, kind, name):
        """Where an existing artifact of this name actually is, or None.

        Separate from path_for because a caller may ask by bare name for
        something stored with a non-default extension — resolve_candidates
        handles that, path_for only knows the default.
        """
        folder = self.folder_for(kind)
        candidates, stem = kinds.resolve_candidates(kind, name)

        for candidate in candidates:
            path = os.path.join(folder, _safe(candidate))
            if os.path.isfile(path):
                return path

        if stem:
            prefix = _safe(stem) + "."
            matches = [entry for entry in os.listdir(folder)
                       if entry.startswith(prefix)
                       and os.path.isfile(os.path.join(folder, entry))]
            if matches:
                # Newest, to match the database store's is_latest semantics.
                matches.sort(key=lambda e: os.path.getmtime(
                    os.path.join(folder, e)), reverse=True)
                return os.path.join(folder, matches[0])
        return None

    # ── ArtifactStore ───────────────────────────────────────────────────────

    def save(self, kind, name, data, *, ext=None, meta=None, run_id=None,
             created_by=None):
        name, resolved_ext = kinds.split_name(kind, name)
        if ext:
            resolved_ext = ext if ext.startswith(".") else f".{ext}"
            name = f"{os.path.splitext(name)[0]}{resolved_ext}"

        payload = to_bytes(data, resolved_ext)
        path = os.path.join(self.folder_for(kind), _safe(name))

        with open(path, "wb") as handle:
            handle.write(payload)

        return ArtifactRef(
            kind=kind, name=_safe(name), ext=resolved_ext, version=1,
            is_latest=True, size_bytes=len(payload), created_by=created_by,
            created_on=datetime.fromtimestamp(os.path.getmtime(path)),
            meta=meta or {}, path=path,
        )

    def read(self, kind, name, *, version=None):
        path = self.resolve_path(kind, name)
        if not path:
            return None

        with open(path, "rb") as handle:
            payload = handle.read()

        stat = os.stat(path)
        return payload, ArtifactRef(
            kind=kind, name=os.path.basename(path),
            ext=os.path.splitext(path)[1].lower(), size_bytes=stat.st_size,
            created_on=datetime.fromtimestamp(stat.st_mtime), path=path,
        )

    def list(self, kind):
        folder = self.folder_for(kind)
        return sorted(
            entry for entry in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, entry))
            and not entry.startswith("~$")  # Excel lock files
        )

    def refs(self, kind):
        folder = self.folder_for(kind)
        out = []
        for name in self.list(kind):
            path = os.path.join(folder, name)
            stat = os.stat(path)
            out.append(ArtifactRef(
                kind=kind, name=name, ext=os.path.splitext(name)[1].lower(),
                size_bytes=stat.st_size,
                created_on=datetime.fromtimestamp(stat.st_mtime), path=path,
            ))
        return sorted(out, key=lambda ref: ref.created_on, reverse=True)

    def versions(self, kind, name):
        """One entry at most — overwriting is how file mode has always worked."""
        found = self.read(kind, name)
        return [found[1]] if found else []

    def delete(self, kind, name, *, version=None):
        path = self.resolve_path(kind, name)
        if not path:
            return False
        os.remove(path)
        return True

    # ── Extras the DB store cannot offer ────────────────────────────────────

    def export_to_dir(self, kind, names, target_dir):
        """Copy selected artifacts into a scratch directory — used by the GitHub
        push, which needs real files on disk."""
        os.makedirs(target_dir, exist_ok=True)
        copied = []
        for name in names:
            source = self.resolve_path(kind, name)
            if source:
                shutil.copy2(source, os.path.join(target_dir,
                                                  os.path.basename(source)))
                copied.append(name)
        return copied


class FileXPathStore(XPathStore):
    """The existing xpath_details.xlsx, behind the XPathStore interface.

    Read / concat / dedupe / rewrite on every add, exactly as
    adding_selected_xapth_excel does it today. Two people generating locators at
    once still clobber each other here — that is the reason the database
    implementation stores rows instead.
    """

    def _read(self):
        if not os.path.exists(_XPATH_FILE):
            return pd.DataFrame(columns=_XPATH_COLUMNS)
        try:
            return pd.read_excel(_XPATH_FILE, engine="openpyxl")
        except Exception as exc:
            print(f"❌ Could not read {_XPATH_FILE}: {exc}")
            return pd.DataFrame(columns=_XPATH_COLUMNS)

    def add(self, page_name, rows, *, created_by=None, source_url=None):
        if not rows:
            return 0

        incoming = pd.DataFrame(rows)
        incoming["Page Name"] = page_name
        if source_url and "Source URL" not in incoming.columns:
            incoming["Source URL"] = source_url

        combined = pd.concat([self._read(), incoming], ignore_index=True)
        combined = combined.drop_duplicates(subset=["XPath", "Page Name"],
                                            keep="last")

        os.makedirs(os.path.dirname(_XPATH_FILE), exist_ok=True)
        combined.to_excel(_XPATH_FILE, index=False, engine="openpyxl")
        return len(incoming)

    def get(self, page_name=None):
        df = self._read()
        if page_name and "Page Name" in df.columns:
            df = df[df["Page Name"] == page_name]
        return df

    def pages(self):
        df = self._read()
        if "Page Name" not in df.columns:
            return []
        return sorted(df["Page Name"].dropna().unique().tolist())

    def delete_page(self, page_name):
        df = self._read()
        if "Page Name" not in df.columns:
            return 0
        keep = df[df["Page Name"] != page_name]
        removed = len(df) - len(keep)
        if removed:
            keep.to_excel(_XPATH_FILE, index=False, engine="openpyxl")
        return removed
