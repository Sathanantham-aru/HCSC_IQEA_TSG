from sqlalchemy import (Column, Integer, String, DateTime, func,
                        Boolean, ForeignKey, Index, UniqueConstraint)
from datetime import datetime
from utilities.db_utils.base import Base  # Shared Base
from utilities.db_utils import types

# Every column type below comes from utilities/db_utils/types.py rather than
# straight from sqlalchemy. See that module for why: on MySQL a plain
# LargeBinary is capped at 64KB and a Text column cannot be indexed at all.


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    prompt_name = Column(String(255), nullable=False, unique=True)
    prompt_text = Column(types.long_text(), nullable=False)  # Supports long prompt text
    description = Column(types.long_text(), nullable=True)   # Optional: describe prompt purpose

    created_on = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)

    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(100), nullable=True)

    def __repr__(self):
        return f"<Prompt(name='{self.prompt_name}', created_by='{self.created_by}')>"


class User(Base):
    """Login account. Authenticates the person; everything they save still
    gets stamped with `username` as a plain string via utilities.identity —
    every other table's created_by column is already a VARCHAR, and rewiring
    all of them to a numeric FK for a handful of internal testers is not worth
    the churn. This table exists to answer "who is this", not to relabel
    ownership everywhere else."""
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    username = Column(types.name(), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(150), nullable=True)
    role = Column(String(32), nullable=False, default="tester")  # tester | admin
    is_active = Column(Boolean, nullable=False, default=True)
    created_on = Column(DateTime, server_default=func.now())
    created_by = Column(types.name(), nullable=True)  # who created this account
    last_login = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User(username='{self.username}', role='{self.role}')>"


# ── Legacy per-type tables ───────────────────────────────────────────────────
# Superseded by iqea_artifacts, still read by handler.py until the UI is moved
# over. The name columns are VARCHAR rather than TEXT so MySQL can index them —
# every lookup in handler.py filters on them by equality.

# Every UniqueConstraint below is (name, created_by) — same name, DIFFERENT
# owner is allowed and expected (two testers can each have a "login_flow");
# same name, SAME owner is the case that used to append a shadow row that no
# lookup could ever tell apart from the first. handler.py's save_*_to_db
# functions now update that row in place instead of inserting a duplicate,
# which is what makes this constraint safe to add — see save_action_to_db.

class Action(Base):
    __tablename__ = 'actions'
    __table_args__ = (
        UniqueConstraint("action_name", "created_by", name="uq_action_name_owner"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True)
    action_name = Column(types.name(), nullable=False, index=True)  # this is the file name
    file_data = Column(types.blob(), nullable=False)
    created_by = Column(types.name(), nullable=False)
    created_on = Column(DateTime, server_default=func.now())

class Pagefile(Base):
    __tablename__ = 'pagefile'
    __table_args__ = (
        UniqueConstraint("pagefile_name", "created_by", name="uq_pagefile_name_owner"),
        {"extend_existing": True},
    )
    id = Column(Integer, primary_key=True)
    pagefile_name = Column(types.name(), nullable=False, index=True)  # this is the file name
    file_data = Column(types.blob(), nullable=False)
    created_by = Column(types.name(), nullable=False)
    created_on = Column(DateTime, server_default=func.now())

class Testcasefile(Base):
    __tablename__ = 'testcase'
    __table_args__ = (
        UniqueConstraint("testcase_name", "created_by", name="uq_testcase_name_owner"),
        {"extend_existing": True},
    )
    id = Column(Integer, primary_key=True)
    testcase_name = Column(types.name(), nullable=False, index=True)  # this is the file name
    file_data = Column(types.blob(), nullable=False)
    created_by = Column(types.name(), nullable=False)
    created_on = Column(DateTime, server_default=func.now())

class Testfile(Base):
    __tablename__ = 'testfile'
    __table_args__ = (
        UniqueConstraint("testfile_name", "created_by", name="uq_testfile_name_owner"),
        {"extend_existing": True},
    )
    id = Column(Integer, primary_key=True)
    testfile_name = Column(types.name(), nullable=False, index=True)  # this is the file name
    file_data = Column(types.blob(), nullable=False)
    created_by = Column(types.name(), nullable=False)
    created_on = Column(DateTime, server_default=func.now())

class Fetaurefile(Base):
    __tablename__ = 'featurefile'
    __table_args__ = (
        UniqueConstraint("featurefile_name", "created_by", name="uq_featurefile_name_owner"),
        {"extend_existing": True},
    )
    id = Column(Integer, primary_key=True)
    featurefile_name = Column(types.name(), nullable=False, index=True)  # this is the file name
    file_data = Column(types.blob(), nullable=False)
    created_by = Column(types.name(), nullable=False)
    created_on = Column(DateTime, server_default=func.now())

class Screenshot(Base):
    __tablename__ = 'screenshot'
    __table_args__ = {"extend_existing": True}
    id = Column(Integer, primary_key=True)
    page_name = Column(types.name(), nullable=False, index=True)
    url = Column(types.url(), nullable=False)
    image_data = Column(types.blob(), nullable=False)
    created_on = Column(DateTime, server_default=func.now())
    created_by = Column(types.name(), nullable=False)  # optional


# ─────────────────────────────────────────────────────────────────────────────
# IQEA artifact store
#
# The seven tables above each hold one artifact type in the same four columns,
# with no version column and no link between artifacts produced by the same
# session. The three tables below replace them:
#
#   iqea_runs      groups everything one recording / generation produced
#   iqea_artifacts one versioned row per stored file, of any kind
#   iqea_xpaths    locators as queryable rows rather than an .xlsx blob
#
# The old tables stay until the backfill in utilities/db_utils/backfill.py has
# been run and verified; handler.py keeps serving them meanwhile.
# ─────────────────────────────────────────────────────────────────────────────

class IqeaRun(Base):
    """One user-visible unit of work: a recording session, a test case
    generation, a script run. Nullable everywhere it can be — artifacts saved
    outside any run keep working with run_id NULL."""
    __tablename__ = "iqea_runs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    run_name = Column(types.name(), nullable=True)
    # record | testcase | pom | script | testdata | execute
    run_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="running")
    started_on = Column(DateTime, server_default=func.now())
    finished_on = Column(DateTime, nullable=True)
    created_by = Column(types.name(), nullable=True)
    meta = Column(types.json_type(), nullable=True)

    def __repr__(self):
        return f"<IqeaRun(id={self.id}, type='{self.run_type}', name='{self.run_name}')>"


class IqeaArtifact(Base):
    """One stored file. `name` is the logical identity (stable across saves);
    `version` counts up per (kind, name) and `is_latest` flags the current one,
    so a lookup by name no longer depends on row order."""
    __tablename__ = "iqea_artifacts"
    __table_args__ = (
        UniqueConstraint("kind", "name", "version", name="uq_iqea_artifact_version"),
        # The two access patterns: resolve one name to its current row, and list
        # the current rows of a kind for a picker.
        Index("ix_iqea_artifact_lookup", "kind", "name", "is_latest"),
        Index("ix_iqea_artifact_kind_latest", "kind", "is_latest"),
        Index("ix_iqea_artifact_run", "run_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("iqea_runs.id", ondelete="SET NULL"),
                    nullable=True)

    # See utilities/storage/kinds.py for the registry of valid values.
    kind = Column(String(32), nullable=False)
    # VARCHAR, not TEXT: this column is inside a unique constraint and two
    # indexes, and MySQL cannot index TEXT without a prefix length.
    name = Column(types.name(), nullable=False)
    # Stored separately so a download never has to parse it back out of `name`.
    ext = Column(String(16), nullable=True)

    version = Column(Integer, nullable=False, default=1)
    is_latest = Column(Boolean, nullable=False, default=True)

    mime = Column(String(128), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    file_data = Column(types.blob(), nullable=False)

    # Per-kind extras that would otherwise each need their own table: a
    # screenshot's url and page, a test file's language, a test case's category.
    meta = Column(types.json_type(), nullable=True)

    created_by = Column(types.name(), nullable=True)
    created_on = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return (f"<IqeaArtifact(kind='{self.kind}', name='{self.name}', "
                f"v{self.version}{'*' if self.is_latest else ''})>")


class IqeaXPath(Base):
    """A locator row. Structured rather than an .xlsx blob because page file
    generation selects by page_name — as a blob that stays a read / concat /
    dedupe / rewrite cycle over a file two users can clobber."""
    __tablename__ = "iqea_xpaths"
    __table_args__ = (
        # Keyed on a hash of the expression rather than the expression itself.
        # An XPath has no useful length limit, and MySQL will not accept an
        # unbounded column in a unique constraint — (page_name, xpath) would cap
        # the expression at roughly 500 characters to stay inside InnoDB's
        # 3072-byte key limit. The hash keeps the guarantee without the cap.
        UniqueConstraint("page_name", "xpath_hash", name="uq_iqea_xpath_page"),
        Index("ix_iqea_xpath_page", "page_name", "is_active"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True)
    page_name = Column(types.name(), nullable=False)
    element = Column(types.long_text(), nullable=True)
    xpath = Column(types.long_text(), nullable=False)
    # SHA-256 of `xpath`, maintained by DbXPathStore on write.
    xpath_hash = Column(types.digest(), nullable=False)
    xpath_type = Column(String(32), nullable=True)
    source_url = Column(types.url(), nullable=True)

    # Soft delete: a locator that stops matching should drop out of generation
    # without losing the record that it once existed.
    is_active = Column(Boolean, nullable=False, default=True)

    created_by = Column(types.name(), nullable=True)
    created_on = Column(DateTime, server_default=func.now())
    updated_on = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<IqeaXPath(page='{self.page_name}', xpath='{self.xpath[:40]}')>"
