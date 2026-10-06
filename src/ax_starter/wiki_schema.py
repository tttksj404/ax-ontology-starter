# pyright: reportAny=false
# SQLite rows remain inside this persistence boundary.
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from ax_starter.action_contracts import AuditEvent
from ax_starter.common import AXError
from ax_starter.retrieval import content_hash

WIKI_SCHEMA_VERSION: Final = "1"


@dataclass(frozen=True, slots=True)
class _InvalidationContext:
    conn: sqlite3.Connection
    tenant: str
    actor: str
    occurred_at: datetime


def migrate_wiki(conn: sqlite3.Connection) -> None:
    """Create the isolated wiki-derived-data schema without touching raw knowledge."""
    _ = conn.execute(
        "CREATE TABLE IF NOT EXISTS wiki_meta (id TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    row = conn.execute("SELECT value FROM wiki_meta WHERE id = 'schema_version'").fetchone()
    if row is not None and str(row[0]) != WIKI_SCHEMA_VERSION:
        raise AXError("wiki_schema_migration_required")
    for statement in _TABLES:
        _ = conn.execute(statement)
    _ = conn.execute(
        "INSERT OR REPLACE INTO wiki_meta (id, value) VALUES ('schema_version', ?)",
        (WIKI_SCHEMA_VERSION,),
    )


def invalidate_wiki_sources(  # noqa: PLR0913 - hook keeps backward-compatible audit keywords.
    conn: sqlite3.Connection,
    tenant: str,
    changed_doc_ids: tuple[str, ...],
    tombstoned_doc_ids: tuple[str, ...],
    *,
    actor: str = "system",
    now: datetime | None = None,
) -> None:
    """Invalidate dependent drafts/pages inside the caller's knowledge transaction."""
    if not _table_exists(conn, "wiki_page_sources"):
        return
    changed = tuple(sorted(set(changed_doc_ids) | set(tombstoned_doc_ids)))
    tombstoned = tuple(sorted(set(tombstoned_doc_ids)))
    context = _InvalidationContext(
        conn=conn,
        tenant=tenant,
        actor=actor,
        occurred_at=now or datetime.now(UTC),
    )
    if changed:
        _mark_dependent_state(context, changed, "stale")
    if tombstoned:
        _scrub_dependent_data(context, tombstoned)


def _mark_dependent_state(
    context: _InvalidationContext, document_ids: tuple[str, ...], state: str
) -> None:
    for document_id in document_ids:
        heads = context.conn.execute(
            """SELECT DISTINCT sources.page_id FROM wiki_page_sources AS sources
            JOIN wiki_page_heads AS heads
              ON heads.tenant = sources.tenant AND heads.page_id = sources.page_id
             AND heads.revision = sources.revision
            WHERE sources.tenant = ? AND sources.document_id = ?""",
            (context.tenant, document_id),
        ).fetchall()
        drafts = context.conn.execute(
            """SELECT DISTINCT draft_id FROM wiki_draft_sources
            WHERE tenant = ? AND document_id = ?""",
            (context.tenant, document_id),
        ).fetchall()
        for row in heads:
            page_id = str(row[0])
            _ = context.conn.execute(
                """UPDATE wiki_page_heads SET state = ?
                WHERE tenant = ? AND page_id = ? AND state != 'scrubbed'""",
                (state, context.tenant, page_id),
            )
            _audit(context, "wiki.source_invalidated", page_id, document_id)
        for row in drafts:
            draft_id = str(row[0])
            _ = context.conn.execute(
                """UPDATE wiki_drafts SET state = ?
                WHERE tenant = ? AND draft_id = ? AND state != 'scrubbed'""",
                (state, context.tenant, draft_id),
            )
            _audit(context, "wiki.draft_source_invalidated", draft_id, document_id)


def _scrub_dependent_data(context: _InvalidationContext, document_ids: tuple[str, ...]) -> None:
    for document_id in document_ids:
        pages = context.conn.execute(
            """SELECT DISTINCT page_id, revision FROM wiki_page_sources
            WHERE tenant = ? AND document_id = ?""",
            (context.tenant, document_id),
        ).fetchall()
        drafts = context.conn.execute(
            """SELECT DISTINCT draft_id FROM wiki_draft_sources
            WHERE tenant = ? AND document_id = ?""",
            (context.tenant, document_id),
        ).fetchall()
        for row in pages:
            page_id = str(row[0])
            revision = int(row[1])
            _ = context.conn.execute(
                """UPDATE wiki_page_heads SET state = 'scrubbed'
                WHERE tenant = ? AND page_id = ? AND revision = ?""",
                (context.tenant, page_id, revision),
            )
            _ = context.conn.execute(
                """UPDATE wiki_page_versions SET data = NULL
                WHERE tenant = ? AND page_id = ? AND revision = ?""",
                (context.tenant, page_id, revision),
            )
            _ = context.conn.execute(
                """DELETE FROM wiki_links
                WHERE tenant = ? AND page_id = ? AND revision = ?""",
                (context.tenant, page_id, revision),
            )
            _audit(context, "wiki.source_scrubbed", page_id, document_id)
        for row in drafts:
            draft_id = str(row[0])
            _ = context.conn.execute(
                """UPDATE wiki_drafts SET state = 'scrubbed', data = NULL
                WHERE tenant = ? AND draft_id = ?""",
                (context.tenant, draft_id),
            )
            _audit(context, "wiki.draft_source_scrubbed", draft_id, document_id)


def _audit(context: _InvalidationContext, event: str, reference: str, payload_hash: str) -> None:
    digest = content_hash(payload_hash)
    _ = context.conn.execute(
        """INSERT INTO wiki_audit (tenant, event, reference, payload_hash, occurred_at)
        VALUES (?, ?, ?, ?, ?)""",
        (context.tenant, event, reference, digest, context.occurred_at.isoformat()),
    )
    if _table_exists(context.conn, "audit"):
        audit = AuditEvent(
            tenant=context.tenant,
            actor=context.actor,
            event=event,
            reference=reference,
            payload_hash=digest,
            occurred_at=context.occurred_at,
        )
        row = context.conn.execute(
            "SELECT hash FROM audit WHERE tenant = ? ORDER BY seq DESC LIMIT 1",
            (context.tenant,),
        ).fetchone()
        previous = str(row[0]) if row else "GENESIS"
        data = audit.model_dump_json()
        chain_hash = content_hash(previous + "\n" + data)
        _ = context.conn.execute(
            "INSERT INTO audit (tenant, data, previous, hash) VALUES (?, ?, ?, ?)",
            (context.tenant, data, previous, chain_hash),
        )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


_TABLES: Final = (
    """CREATE TABLE IF NOT EXISTS wiki_drafts (
    tenant TEXT NOT NULL, draft_id TEXT NOT NULL, page_id TEXT NOT NULL,
    proposer TEXT NOT NULL, request_key TEXT NOT NULL, request_sha256 TEXT NOT NULL,
    payload_hash TEXT NOT NULL, state TEXT NOT NULL, data TEXT, created_at TEXT NOT NULL,
    reviewer TEXT, reviewer_person_id TEXT, published_revision INTEGER,
    PRIMARY KEY (tenant, draft_id), UNIQUE (tenant, proposer, request_key))""",
    """CREATE TABLE IF NOT EXISTS wiki_draft_sources (
    tenant TEXT NOT NULL, draft_id TEXT NOT NULL, document_id TEXT NOT NULL,
    PRIMARY KEY (tenant, draft_id, document_id),
    FOREIGN KEY (tenant, draft_id) REFERENCES wiki_drafts (tenant, draft_id))""",
    """CREATE TABLE IF NOT EXISTS wiki_page_heads (
    tenant TEXT NOT NULL, page_id TEXT NOT NULL, revision INTEGER NOT NULL,
    version_id TEXT NOT NULL, page_hash TEXT NOT NULL, state TEXT NOT NULL,
    PRIMARY KEY (tenant, page_id))""",
    """CREATE TABLE IF NOT EXISTS wiki_page_versions (
    tenant TEXT NOT NULL, page_id TEXT NOT NULL, revision INTEGER NOT NULL,
    version_id TEXT NOT NULL, page_hash TEXT NOT NULL, data TEXT,
    PRIMARY KEY (tenant, page_id, revision), UNIQUE (tenant, version_id))""",
    """CREATE TABLE IF NOT EXISTS wiki_page_sources (
    tenant TEXT NOT NULL, page_id TEXT NOT NULL, revision INTEGER NOT NULL,
    document_id TEXT NOT NULL, document_sha256 TEXT NOT NULL,
    content_sha256 TEXT NOT NULL, access_sha256 TEXT NOT NULL,
    PRIMARY KEY (tenant, page_id, revision, document_id))""",
    """CREATE TABLE IF NOT EXISTS wiki_links (
    tenant TEXT NOT NULL, page_id TEXT NOT NULL, revision INTEGER NOT NULL,
    target_page_id TEXT NOT NULL,
    PRIMARY KEY (tenant, page_id, revision, target_page_id))""",
    """CREATE TABLE IF NOT EXISTS wiki_audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL, event TEXT NOT NULL,
    reference TEXT NOT NULL, payload_hash TEXT NOT NULL, occurred_at TEXT NOT NULL)""",
)
