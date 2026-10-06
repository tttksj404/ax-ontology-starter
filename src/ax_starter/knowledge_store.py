# pyright: reportAny=false
# sqlite3 rows are parsed into frozen contracts before leaving this module.
import sqlite3
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from ax_starter.common import Access, AXError
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.evidence_policy import raw_source_allowed
from ax_starter.knowledge_binding import binding_is_current
from ax_starter.knowledge_contracts import (
    DocumentLifecycle,
    KnowledgeDocumentMeta,
    KnowledgeMutationReceipt,
)
from ax_starter.knowledge_schema import document_state_hash
from ax_starter.ontology import Document
from ax_starter.retrieval import content_hash


@dataclass(frozen=True, slots=True)
class StateHead:
    revision: int
    state_hash: str


@dataclass(frozen=True, slots=True)
class StoredDocument:
    meta: KnowledgeDocumentMeta
    document: Document | None
    access_snapshot: Access | None


@dataclass(frozen=True, slots=True)
class StoredBatch:
    payload_sha256: str
    receipt: KnowledgeMutationReceipt


BatchKind = Literal["apply", "import"]


def access_hash(access: Access) -> str:
    return content_hash(access.model_dump_json())


def active_documents(
    conn: sqlite3.Connection, registry: DataContractRegistry | None
) -> tuple[Document, ...]:
    rows = conn.execute(
        """SELECT document_id FROM knowledge_documents
        WHERE lifecycle = 'active' ORDER BY document_id"""
    ).fetchall()
    records = (document_record(conn, str(row[0])) for row in rows)
    return tuple(
        record.document
        for record in records
        if record is not None
        and record.document is not None
        and binding_is_current(record.meta, registry)
        and raw_source_allowed(record.meta, record.document, registry)
    )


def tenant_head(conn: sqlite3.Connection, tenant: str) -> StateHead:
    row = conn.execute(
        "SELECT revision, state_hash FROM knowledge_tenant_state WHERE tenant = ?", (tenant,)
    ).fetchone()
    if row is None:
        _ = conn.execute(
            "INSERT INTO knowledge_tenant_state VALUES (?, 0, ?)",
            (tenant, content_hash("")),
        )
        return StateHead(revision=0, state_hash=content_hash(""))
    return StateHead(revision=int(row[0]), state_hash=str(row[1]))


def source_head(conn: sqlite3.Connection, tenant: str, source_identifier: str) -> StateHead:
    row = conn.execute(
        """SELECT revision, state_hash FROM knowledge_source_state
        WHERE tenant = ? AND source_identifier = ?""",
        (tenant, source_identifier),
    ).fetchone()
    if row is None:
        genesis = content_hash("GENESIS")
        _ = conn.execute(
            """INSERT INTO knowledge_source_state
            (tenant, source_identifier, revision, state_hash) VALUES (?, ?, 0, ?)""",
            (tenant, source_identifier, genesis),
        )
        return StateHead(revision=0, state_hash=genesis)
    return StateHead(revision=int(row[0]), state_hash=str(row[1]))


def stored_batch(
    conn: sqlite3.Connection,
    tenant: str,
    contract_id: str,
    request_kind: BatchKind,
    request_key: str,
) -> StoredBatch | None:
    row = conn.execute(
        """SELECT payload_sha256, receipt_json FROM knowledge_batches
        WHERE tenant = ? AND contract_id = ? AND request_kind = ? AND request_key = ?""",
        (tenant, contract_id, request_kind, request_key),
    ).fetchone()
    if row is None:
        return None
    return StoredBatch(
        payload_sha256=str(row[0]),
        receipt=KnowledgeMutationReceipt.model_validate_json(str(row[1])),
    )


def document_record(conn: sqlite3.Connection, document_id: str) -> StoredDocument | None:
    row = conn.execute(
        """SELECT tenant, source_identifier, source_version, lifecycle, document_json,
        content_sha256, access_sha256, revision, contract_id, contract_version,
        contract_sha256, access_json FROM knowledge_documents
        WHERE document_id = ?""",
        (document_id,),
    ).fetchone()
    if row is None:
        return None
    meta = KnowledgeDocumentMeta(
        document_id=document_id,
        tenant=str(row[0]),
        source_identifier=str(row[1]),
        source_version=str(row[2]),
        contract_id=None if row[8] is None else str(row[8]),
        contract_version=None if row[9] is None else str(row[9]),
        contract_sha256=None if row[10] is None else str(row[10]),
        lifecycle=DocumentLifecycle(str(row[3])),
        content_sha256=str(row[5]),
        access_sha256=str(row[6]),
        revision=int(row[7]),
    )
    try:
        document = None if row[4] is None else Document.model_validate_json(str(row[4]))
        access_snapshot = None if row[11] is None else Access.model_validate_json(str(row[11]))
    except ValidationError as exc:
        raise AXError("knowledge_integrity_failure") from exc
    if access_snapshot is not None and (
        access_snapshot.tenant != meta.tenant or access_hash(access_snapshot) != meta.access_sha256
    ):
        raise AXError("knowledge_integrity_failure")
    if document is not None and (
        document.id != meta.document_id
        or document.source_version != meta.source_version
        or document.access.tenant != meta.tenant
        or content_hash(document.text) != meta.content_sha256
        or access_hash(document.access) != meta.access_sha256
        or (access_snapshot is not None and document.access != access_snapshot)
    ):
        raise AXError("knowledge_integrity_failure")
    return StoredDocument(meta=meta, document=document, access_snapshot=access_snapshot)


def save_document(conn: sqlite3.Connection, stored: StoredDocument) -> None:
    document_json = None if stored.document is None else stored.document.model_dump_json()
    access_json = (
        None if stored.access_snapshot is None else stored.access_snapshot.model_dump_json()
    )
    _ = conn.execute(
        """INSERT INTO knowledge_documents
        (document_id, tenant, source_identifier, source_version, lifecycle, document_json,
        content_sha256, access_sha256, revision, contract_id, contract_version, contract_sha256,
        access_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET tenant = excluded.tenant,
        source_identifier = excluded.source_identifier, source_version = excluded.source_version,
        lifecycle = excluded.lifecycle, document_json = excluded.document_json,
        content_sha256 = excluded.content_sha256, access_sha256 = excluded.access_sha256,
        revision = excluded.revision, contract_id = excluded.contract_id,
        contract_version = excluded.contract_version, contract_sha256 = excluded.contract_sha256,
        access_json = excluded.access_json""",
        (
            stored.meta.document_id,
            stored.meta.tenant,
            stored.meta.source_identifier,
            stored.meta.source_version,
            stored.meta.lifecycle.value,
            document_json,
            stored.meta.content_sha256,
            stored.meta.access_sha256,
            stored.meta.revision,
            stored.meta.contract_id,
            stored.meta.contract_version,
            stored.meta.contract_sha256,
            access_json,
        ),
    )


def advance_state(
    conn: sqlite3.Connection,
    tenant: str,
    source_identifier: str,
    payload_sha256: str,
) -> tuple[StateHead, StateHead]:
    current_tenant = tenant_head(conn, tenant)
    current_source = source_head(conn, tenant, source_identifier)
    source = StateHead(
        revision=current_source.revision + 1,
        state_hash=content_hash(current_source.state_hash + "\n" + payload_sha256),
    )
    _ = conn.execute(
        """UPDATE knowledge_source_state SET revision = ?, state_hash = ?
        WHERE tenant = ? AND source_identifier = ?""",
        (source.revision, source.state_hash, tenant, source_identifier),
    )
    tenant_state = StateHead(
        revision=current_tenant.revision + 1,
        state_hash=document_state_hash(conn, tenant),
    )
    _ = conn.execute(
        "UPDATE knowledge_tenant_state SET revision = ?, state_hash = ? WHERE tenant = ?",
        (tenant_state.revision, tenant_state.state_hash, tenant),
    )
    return tenant_state, source


def save_batch(
    conn: sqlite3.Connection,
    receipt: KnowledgeMutationReceipt,
    request_kind: BatchKind,
) -> None:
    _ = conn.execute(
        """INSERT INTO knowledge_batches
        (tenant, contract_id, request_kind, request_key, payload_sha256, receipt_json)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (
            receipt.tenant,
            receipt.contract_id,
            request_kind,
            receipt.request_key,
            receipt.payload_sha256,
            receipt.model_dump_json(),
        ),
    )
