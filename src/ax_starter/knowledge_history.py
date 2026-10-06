# pyright: reportAny=false
import sqlite3
from datetime import datetime

from ax_starter.knowledge_contracts import KnowledgeDocumentMeta


def source_watermark(
    conn: sqlite3.Connection, tenant: str, source_identifier: str
) -> datetime | None:
    row = conn.execute(
        """SELECT last_observed_at FROM knowledge_source_state
        WHERE tenant = ? AND source_identifier = ?""",
        (tenant, source_identifier),
    ).fetchone()
    return None if row is None or row[0] is None else datetime.fromisoformat(str(row[0]))


def save_source_watermark(
    conn: sqlite3.Connection, tenant: str, source_identifier: str, observed_at: datetime
) -> None:
    _ = conn.execute(
        """UPDATE knowledge_source_state SET last_observed_at = ?
        WHERE tenant = ? AND source_identifier = ?""",
        (observed_at.isoformat(), tenant, source_identifier),
    )


def source_version_accepted(
    conn: sqlite3.Connection,
    tenant: str,
    source_identifier: str,
    document_id: str,
    source_version: str,
) -> bool:
    row = conn.execute(
        """SELECT 1 FROM knowledge_accepted_versions
        WHERE tenant = ? AND source_identifier = ? AND document_id = ? AND source_version = ?""",
        (tenant, source_identifier, document_id, source_version),
    ).fetchone()
    return row is not None


def save_accepted_version(conn: sqlite3.Connection, meta: KnowledgeDocumentMeta) -> None:
    _ = conn.execute(
        """INSERT INTO knowledge_accepted_versions VALUES (?, ?, ?, ?)""",
        (meta.tenant, meta.source_identifier, meta.document_id, meta.source_version),
    )
