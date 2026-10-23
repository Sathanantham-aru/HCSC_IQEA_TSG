"""
Screenshot gallery reads, cached, for source=database.

WHY THIS EXISTS
---------------
The gallery called handler.get_all_screenshots() on every Streamlit re-run, and
so did test-case generation. That function pulled EVERY row with its full PNG
blob (and, until this change, ran the query twice and print()ed the rows, so
__repr__ walked every blob). Against Azure MySQL that is the entire screenshot
table crossing the network up to four times per click.

That is the direct cause of "selecting an image takes a long time in Azure", and
the likely cause of the broken thumbnails too: st.image() with a PIL object
makes Streamlit mint a /media/<hash> URL that the browser fetches in a SECOND
request. While a slow re-run is still re-downloading blobs, those pending media
fetches can race the media manager and 404 — which the browser draws as a broken
image. Some images survive, some do not, which is exactly the "most broken, a
few fine" pattern.

The fix is to stop re-fetching:
  * labels come from get_screenshot_index() — ids and names, NO blobs
  * bytes are fetched one at a time and cached per id
  * st.image() gets raw PNG BYTES, not a PIL object, so the media URL is a
    stable content hash rather than something re-minted each run
"""

import streamlit as st

import utilities.db_utils.handler as db_handler


@st.cache_data(show_spinner=False, ttl=20)
def screenshot_index():
    """
    [{id, page_name, label}] with no image bytes.

    Short TTL rather than permanent: recording adds screenshots while the page
    is open, so the list must refresh — just not on every re-run.
    """
    try:
        rows = db_handler.get_screenshot_index() or []
    except Exception as exc:
        print("[screenshots] index query failed: %s" % exc)
        return []
    return [{"id": r["id"],
             "page_name": r["page_name"],
             # Label format is unchanged, so existing selections keep working.
             "label": "%s_%s" % (r["page_name"], r["id"])}
            for r in rows]


@st.cache_data(show_spinner=False, max_entries=512)
def screenshot_bytes(screenshot_id):
    """PNG bytes for one screenshot, fetched once and cached."""
    try:
        return db_handler.get_screenshot_data(screenshot_id)
    except Exception as exc:
        print("[screenshots] blob %s unavailable: %s" % (screenshot_id, exc))
        return None


def label_to_id(label):
    """Resolve a gallery label back to its screenshot id."""
    for row in screenshot_index():
        if row["label"] == label:
            return row["id"]
    return None


def bytes_for_label(label):
    """PNG bytes for a gallery label, or None."""
    sid = label_to_id(label)
    return screenshot_bytes(sid) if sid is not None else None


@st.cache_data(show_spinner=False, max_entries=512)
def thumbnail_data_uri(screenshot_id, max_width=100):
    """
    A small JPEG thumbnail as a `data:` URI, cached per (id, width).

    Two problems with handing full-size bytes to st.image(width=100):

    1. st.image does not embed the image. It registers it with Streamlit's
       MediaFileManager and emits /media/<hash>, which the browser fetches as a
       SECOND request. Streamlit garbage-collects media that the current run no
       longer references, so requests still in flight from the previous run get
       a 404 and the browser draws its broken-image glyph. That is why some
       thumbnails broke, why the URL worked when opened directly, and why a
       page refresh fixed them.
    2. It shipped the entire full-resolution screenshot and let the browser
       scale it down — hundreds of KB to paint 100 pixels.

    A data: URI solves both. There is no second request to lose, nothing for the
    media manager to collect, and a real 100px thumbnail is a few KB.
    """
    import base64
    import io as _io

    raw = screenshot_bytes(screenshot_id)
    if not raw:
        return None
    try:
        from PIL import Image
        img = Image.open(_io.BytesIO(raw))
        img.load()                     # decode now; the BytesIO goes away below
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")   # JPEG cannot store alpha
        ratio = img.height / img.width if img.width else 1
        img = img.resize((max_width, max(1, int(max_width * ratio))))
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=70, optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return "data:image/jpeg;base64," + encoded
    except Exception as exc:
        print("[screenshots] thumbnail %s failed: %s" % (screenshot_id, exc))
        return None


def render_thumbnail(label, max_width=100):
    """
    Draw an inline thumbnail that cannot 404. Returns True if it rendered.

    Inline because the media endpoint races Streamlit's own cleanup on re-run —
    see thumbnail_data_uri.
    """
    sid = label_to_id(label)
    uri = thumbnail_data_uri(sid, max_width) if sid is not None else None
    if not uri:
        st.warning("🖼️ `%s` unavailable" % label)
        return False
    st.markdown(
        '<img src="%s" width="%d" style="border-radius:4px;display:block;" '
        'alt="%s" />' % (uri, max_width, label),
        unsafe_allow_html=True,
    )
    return True


def render_label(label, caption=None, width=None, use_container_width=False):
    """
    Draw one screenshot by label. Returns True if it rendered.

    Passes bytes rather than a PIL image so Streamlit's media URL is a stable
    content hash. On failure it says what is missing instead of leaving a broken
    image icon, which gave no hint that the blob was the problem.
    """
    data = bytes_for_label(label)
    if not data:
        st.warning("🖼️ `%s` could not be loaded from the database." % label)
        return False
    if width:
        st.image(data, caption=caption, width=width)
    else:
        st.image(data, caption=caption, use_container_width=use_container_width)
    return True


def clear_cache():
    """Drop cached index and blobs — call after saving new screenshots."""
    screenshot_index.clear()
    screenshot_bytes.clear()
