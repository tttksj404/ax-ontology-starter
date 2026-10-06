# pyright: reportAny=false
# sqlite3 rows are used only to seed and hash the versioned schema.
from __future__ import annotations

from typing import TYPE_CHECKING, Final

from pydantic import ValidationError

if TYPE_CHECKING:
    import sqlite3
    from datetime import datetime

    from ax_starter.ontology import DomainPack

from ax_starter.action_contracts import AuditEvent
from ax_starter.common import AXError
from ax_starter.knowledge_contracts import KnowledgeMutationReceipt
from ax_starter.ontology import Document
from ax_starter.retrieval import content_hash

SCHEMA_VERSION: Final = "4"


def migrate_knowledge(conn: sqlite3.Connection, template: DomainPack) -> None:
    row = conn.execute("SELECT value FROM meta WHERE id = 'schema_version'").fetchone()
    version = None if row is None else str(row[0])
    if version not in (None, "2", "3", SCHEMA_VERSION):
        raise AXError("knowledge_schema_migration_required")
    if version == "2":
        _migrate_v2(conn)
    _create_tables(conn)
    _add_column(conn, "knowledge_documents", "access_json", "TEXT")
    _seed_documents(conn, template)
    _backfill_access_snapshots(conn)
    _seed_accepted_versions(conn)
    _seed_state_heads(conn, template)
    _ = conn.execute(
        "INSERT OR REPLACE INTO meta (id, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )


def document_state_hash(conn: sqlite3.Connection, tenant: str) -> str:
    rows = conn.execute(
        """SELECT document_id, source_version, lifecycle, content_sha256,
        access_sha256, revision, contract_id, contract_version, contract_sha256
        FROM knowledge_documents WHERE tenant = ? ORDER BY document_id""",
        (tenant,),
    ).fetchall()
    canonical = "\n".join("|".join(str(value) for value in row) for row in rows)
    return content_hash(canonical)


def _create_tables(conn: sqlite3.Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS knowledge_documents (
        document_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, source_identifier TEXT NOT NULL,
        source_version TEXT NOT NULL, lifecycle TEXT NOT NULL, document_json TEXT,
        content_sha256 TEXT NOT NULL, access_sha256 TEXT NOT NULL, revision INTEGER NOT NULL,
        contract_id TEXT, contract_version TEXT, contract_sha256 TEXT, access_json TEXT)""",
        """CREATE TABLE IF NOT EXISTS knowledge_batches (
        tenant TEXT NOT NULL, contract_id TEXT NOT NULL, request_kind TEXT NOT NULL,
        request_key TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL,
        PRIMARY KEY (tenant, contract_id, request_kind, request_key))""",
        """CREATE TABLE IF NOT EXISTS knowledge_tenant_state (
        tenant TEXT PRIMARY KEY, revision INTEGER NOT NULL, state_hash TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS knowledge_source_state (
        tenant TEXT NOT NULL, source_identifier TEXT NOT NULL,
        revision INTEGER NOT NULL, state_hash TEXT NOT NULL, last_observed_at TEXT,
        PRIMARY KEY (tenant, source_identifier))""",
        """CREATE TABLE IF NOT EXISTS knowledge_accepted_versions (
        tenant TEXT NOT NULL, source_identifier TEXT NOT NULL, document_id TEXT NOT NULL,
        source_version TEXT NOT NULL,
        PRIMARY KEY (tenant, source_identifier, document_id, source_version))""",
    )
    for statement in statements:
        _ = conn.execute(statement)


def _seed_documents(conn: sqlite3.Connection, template: DomainPack) -> None:
    for document in template.documents:
        _ = conn.execute(
            """INSERT OR IGNORE INTO knowledge_documents
            (document_id, tenant, source_identifier, source_version, lifecycle, document_json,
            content_sha256, access_sha256, revision, access_json)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, 0, ?)""",
            (
                document.id,
                document.access.tenant,
                f"bootstrap.{document.id}",
                document.source_version,
                document.model_dump_json(),
                content_hash(document.text),
                content_hash(document.access.model_dump_json()),
                document.access.model_dump_json(),
            ),
        )


def _backfill_access_snapshots(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """SELECT document_id, document_json, access_sha256 FROM knowledge_documents
        WHERE access_json IS NULL AND document_json IS NOT NULL"""
    ).fetchall()
    for row in rows:
        try:
            document = Document.model_validate_json(str(row[1]))
        except ValidationError:
            continue
        if content_hash(document.access.model_dump_json()) != str(row[2]):
            continue
        _ = conn.execute(
            "UPDATE knowledge_documents SET access_json = ? WHERE document_id = ?",
            (document.access.model_dump_json(), str(row[0])),
        )


def _seed_state_heads(conn: sqlite3.Connection, template: DomainPack) -> None:
    tenants = {entity.access.tenant for entity in template.objects}
    tenants.update(document.access.tenant for document in template.documents)
    for tenant in sorted(tenants):
        _ = conn.execute(
            "INSERT OR IGNORE INTO knowledge_tenant_state VALUES (?, 0, ?)",
            (tenant, document_state_hash(conn, tenant)),
        )
    rows = conn.execute(
        "SELECT DISTINCT tenant, source_identifier FROM knowledge_documents"
    ).fetchall()
    for tenant, source_identifier in rows:
        _ = conn.execute(
            """INSERT OR IGNORE INTO knowledge_source_state
            (tenant, source_identifier, revision, state_hash) VALUES (?, ?, 0, ?)""",
            (str(tenant), str(source_identifier), content_hash("GENESIS")),
        )


def _migrate_v2(conn: sqlite3.Connection) -> None:
    _add_column(conn, "knowledge_documents", "contract_id", "TEXT")
    _add_column(conn, "knowledge_documents", "contract_version", "TEXT")
    _add_column(conn, "knowledge_documents", "contract_sha256", "TEXT")
    _add_column(conn, "knowledge_source_state", "last_observed_at", "TEXT")
    batch_columns = _columns(conn, "knowledge_batches")
    if "request_kind" not in batch_columns:
        _ = conn.execute("ALTER TABLE knowledge_batches RENAME TO knowledge_batches_v2")
        _ = conn.execute(
            """CREATE TABLE knowledge_batches (
            tenant TEXT NOT NULL, contract_id TEXT NOT NULL, request_kind TEXT NOT NULL,
            request_key TEXT NOT NULL, payload_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL,
            PRIMARY KEY (tenant, contract_id, request_kind, request_key))"""
        )
        _ = conn.execute(
            """INSERT INTO knowledge_batches
            SELECT tenant, contract_id, 'apply', request_key, payload_sha256, receipt_json
            FROM knowledge_batches_v2"""
        )
        _ = conn.execute("DROP TABLE knowledge_batches_v2")
    _seed_v2_watermarks(conn)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, column: str, kind: str) -> None:
    if column not in _columns(conn, table):
        _ = conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")


def _seed_accepted_versions(conn: sqlite3.Connection) -> None:
    _ = conn.execute(
        """INSERT OR IGNORE INTO knowledge_accepted_versions
        SELECT tenant, source_identifier, document_id, source_version FROM knowledge_documents"""
    )
    rows = conn.execute("SELECT receipt_json FROM knowledge_batches").fetchall()
    for row in rows:
        receipt = KnowledgeMutationReceipt.model_validate_json(str(row[0]))
        _ = conn.executemany(
            """INSERT OR IGNORE INTO knowledge_accepted_versions
            VALUES (?, ?, ?, ?)""",
            [
                (item.tenant, item.source_identifier, item.document_id, item.source_version)
                for item in receipt.documents
            ],
        )


def _seed_v2_watermarks(conn: sqlite3.Connection) -> None:
    audit_times: dict[tuple[str, str], datetime] = {}
    for row in conn.execute("SELECT tenant, data FROM audit").fetchall():
        event = AuditEvent.model_validate_json(str(row[1]))
        if event.event != "knowledge.batch_applied":
            continue
        key = (str(row[0]), event.reference)
        previous = audit_times.get(key)
        if previous is None or event.occurred_at > previous:
            audit_times[key] = event.occurred_at
    source_times: dict[tuple[str, str], datetime] = {}
    rows = conn.execute(
        """SELECT tenant, contract_id, request_key, receipt_json
        FROM knowledge_batches"""
    ).fetchall()
    for row in rows:
        tenant, contract_id, request_key = str(row[0]), str(row[1]), str(row[2])
        references = (
            f"{contract_id}:{request_key}",
            f"apply:{contract_id}:{request_key}",
            f"import:{contract_id}:{request_key}",
        )
        observed = max(
            (
                audit_times[(tenant, reference)]
                for reference in references
                if (tenant, reference) in audit_times
            ),
            default=None,
        )
        if observed is None:
            continue
        receipt = KnowledgeMutationReceipt.model_validate_json(str(row[3]))
        for source_identifier in {item.source_identifier for item in receipt.documents}:
            key = (tenant, source_identifier)
            previous = source_times.get(key)
            if previous is None or observed > previous:
                source_times[key] = observed
    for (tenant, source_identifier), observed in source_times.items():
        _ = conn.execute(
            """UPDATE knowledge_source_state SET last_observed_at = ?
            WHERE tenant = ? AND source_identifier = ? AND last_observed_at IS NULL""",
            (observed.isoformat(), tenant, source_identifier),
        )
    _ = conn.execute(
        """UPDATE knowledge_source_state
        SET last_observed_at = strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
        WHERE last_observed_at IS NULL AND EXISTS (
            SELECT 1 FROM knowledge_documents AS document
            WHERE document.tenant = knowledge_source_state.tenant
            AND document.source_identifier = knowledge_source_state.source_identifier
            AND document.source_identifier != 'bootstrap.' || document.document_id)"""
    )
