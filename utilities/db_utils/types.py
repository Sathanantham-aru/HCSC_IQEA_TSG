"""
Column types that behave the same on MySQL and PostgreSQL.

The models were written against PostgreSQL, where `Text` and `LargeBinary` are
unbounded and `JSONB` exists. None of that survives a move to MySQL unchanged:

  LargeBinary  MySQL renders it as BLOB, which truncates at 64KB. The screenshots
               already in the store reach 396KB, so every one of them would be
               silently cut in half. LONGBLOB (4GB) is the only safe mapping.

  Text         MySQL's TEXT is also 64KB, and — more importantly — MySQL cannot
               put a TEXT column in an index or a unique constraint without a
               prefix length. `iqea_artifacts.name` sits inside a UNIQUE
               (kind, name, version), so it has to become a bounded VARCHAR.

  JSONB        PostgreSQL-only. MySQL 5.7.8+ has JSON, and SQLAlchemy's generic
               JSON maps to the right one on each.

Sizing note: InnoDB caps an index key at 3072 bytes and utf8mb4 charges 4 bytes
per character, so everything that participates in an index is kept at or under
255 characters (1020 bytes). The longest name in the existing data is 58.
"""

from sqlalchemy import JSON, LargeBinary, String, Text
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT


def blob():
    """Binary payload of any size — artifact bytes, screenshots."""
    return LargeBinary().with_variant(LONGBLOB(), "mysql")


def long_text():
    """Unbounded text — prompt bodies, XPath expressions, URLs.
    Never usable in an index; use name() for anything indexed."""
    return Text().with_variant(LONGTEXT(), "mysql")


def json_type():
    """Schemaless per-row extras. JSON on MySQL, JSON on PostgreSQL."""
    return JSON()


def name():
    """An indexable identifier: file names, page names, users.

    255 chars is the conventional ceiling for an indexed utf8mb4 VARCHAR —
    1020 bytes, comfortably inside InnoDB's 3072-byte key limit even when two
    of them are combined in one constraint.
    """
    return String(255)


def url():
    """A URL. Not indexed, so it can be long — the longest stored is 685."""
    return String(2048)


# SHA-256 hex digest. Used where the natural unique key is a value too long to
# index directly, which on MySQL means any XPath expression.
def digest():
    return String(64)
