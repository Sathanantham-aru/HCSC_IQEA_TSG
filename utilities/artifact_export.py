"""
Download IQEA's generated artifacts as a zip.

The workaround for ephemeral container storage. On Azure App Service everything
the app writes under output/ is discarded on restart, redeploy or scale-in, so a
recording session's action files, screenshots, page files and test files are
lost without warning. The durable fix is an Azure Files mount at /app/output;
until that exists, this lets a user pull their work out of the container before
it disappears.

Renders nothing locally, where the files already live on the user's own disk.
"""

import io
import os
import zipfile

import streamlit as st

from config.settings_reader import is_azure

# label -> path relative to the working directory (which is the repo root)
_SETS = [
    ("Action files",       os.path.join("output", "Action_collection")),
    ("Test files",         os.path.join("output", "test_file_generator")),
    ("Xpath details",      os.path.join("output", "xpath_generator")),
    ("Test cases",         os.path.join("output", "Test_Cases_collection")),
    ("Page files",         os.path.join("output", "page_file_generator")),
    ("Self-healing",       os.path.join("Self_healing_web_application", "output")),
    ("Generated features", "generated_features"),
]

# Skip the bulky intermediates - a zip a browser has to download should stay
# small enough to actually finish.
_SKIP_EXT = (".zip", ".pyc")
_MAX_BYTES = 200 * 1024 * 1024


def _collect(root):
    """(arcname, fullpath) for every file under root."""
    items = []
    if not os.path.isdir(root):
        return items
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if name.lower().endswith(_SKIP_EXT):
                continue
            full = os.path.join(dirpath, name)
            items.append((os.path.relpath(full, os.getcwd()), full))
    return items


def build_zip(selected_labels):
    """Zip the chosen artifact sets. Returns (bytes, file_count, skipped)."""
    wanted = [p for label, p in _SETS if label in selected_labels]
    buf = io.BytesIO()
    count = 0
    skipped = []
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root in wanted:
            for arcname, full in _collect(root):
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if total + size > _MAX_BYTES:
                    skipped.append(arcname)
                    continue
                try:
                    zf.write(full, arcname)
                    total += size
                    count += 1
                except OSError:
                    skipped.append(arcname)
    return buf.getvalue(), count, skipped


def render_artifact_export(key="iqea", force=False):
    """
    Show the export control. Azure-only unless `force` is set.

    Returns True if rendered.
    """
    if not (is_azure() or force):
        return False

    with st.expander("⬇️ Download artifacts (recommended before you finish)",
                     expanded=False):
        st.caption(
            "Container storage is **temporary** — files written here are lost "
            "when the app restarts or redeploys. Download anything you want to "
            "keep. This goes away once persistent storage is mounted."
        )

        available = []
        for label, path in _SETS:
            n = len(_collect(path))
            if n:
                available.append(label)
                st.write("• **%s** — %d file(s)" % (label, n))

        if not available:
            st.info("Nothing generated yet in this container.")
            return True

        chosen = st.multiselect("Include", available, default=available,
                                key="export_sets_%s" % key)
        if st.button("📦 Build zip", key="export_build_%s" % key):
            data, count, skipped = build_zip(chosen)
            if not count:
                st.warning("No files matched the selection.")
            else:
                st.session_state["_export_zip_%s" % key] = data
                st.success("Packed %d file(s), %.1f MB."
                           % (count, len(data) / 1e6))
                if skipped:
                    st.warning("%d file(s) skipped (size cap)." % len(skipped))

        data = st.session_state.get("_export_zip_%s" % key)
        if data:
            st.download_button("⬇️ Download iqea_artifacts.zip", data=data,
                               file_name="iqea_artifacts.zip",
                               mime="application/zip",
                               key="export_dl_%s" % key)
    return True
