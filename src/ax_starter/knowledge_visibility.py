# pyright: reportAny=false
# SQLite rows are parsed into frozen contracts before leaving this module.
import sqlite3

from ax_starter.common import Operation, Principal, Purpose
from ax_starter.data_contracts import DataContract, DataContractRegistry
from ax_starter.knowledge_binding import binding_is_current
from ax_starter.knowledge_contracts import (
    KnowledgeDocumentMeta,
    KnowledgeMutationReceipt,
    KnowledgeSourceHead,
)
from ax_starter.knowledge_store import StoredDocument, document_record
from ax_starter.policy import visible
from ax_starter.retrieval import content_hash


def document_metas(
    conn: sqlite3.Connection,
    actor: Principal,
    registry: DataContractRegistry,
) -> tuple[KnowledgeDocumentMeta, ...]:
    rows = conn.execute(
        "SELECT document_id FROM knowledge_documents WHERE tenant = ? ORDER BY document_id",
        (actor.tenant,),
    ).fetchall()
    contracts = _manageable_contracts(actor, registry)
    records = (document_record(conn, str(row[0])) for row in rows)
    return tuple(
        record.meta
        for record in records
        if record is not None and _metadata_visible(record, actor, registry, contracts)
    )


def source_heads(
    conn: sqlite3.Connection,
    actor: Principal,
    registry: DataContractRegistry,
) -> tuple[KnowledgeSourceHead, ...]:
    allowed = {
        contract.collection_source.identifier for contract in _manageable_contracts(actor, registry)
    }
    rows = conn.execute(
        """SELECT source_identifier, revision, state_hash FROM knowledge_source_state
        WHERE tenant = ? ORDER BY source_identifier""",
        (actor.tenant,),
    ).fetchall()
    return tuple(
        KnowledgeSourceHead(
            source_identifier=str(row[0]), revision=int(row[1]), state_hash=str(row[2])
        )
        for row in rows
        if str(row[0]) in allowed
    )


def management_access_visible(record: StoredDocument, actor: Principal) -> bool:
    access = record.access_snapshot
    return (
        access is not None
        and actor.tenant == access.tenant
        and bool(actor.groups & access.groups)
        and actor.clearance >= access.sensitivity
    )


def record_matches_contract(
    record: StoredDocument,
    contract: DataContract,
    *,
    exact_binding: bool,
) -> bool:
    meta = record.meta
    if (
        meta.tenant != contract.tenant
        or meta.source_identifier != contract.collection_source.identifier
        or meta.contract_id != contract.id
    ):
        return False
    return not exact_binding or (
        meta.contract_version == contract.version
        and meta.contract_sha256 == content_hash(contract.model_dump_json())
    )


def project_receipt(
    conn: sqlite3.Connection,
    receipt: KnowledgeMutationReceipt,
    actor: Principal,
    contract: DataContract,
) -> KnowledgeMutationReceipt:
    documents = tuple(
        meta for meta in receipt.documents if _receipt_meta_visible(conn, meta, actor, contract)
    )
    return receipt.model_copy(update={"documents": documents})


def _manageable_contracts(
    actor: Principal, registry: DataContractRegistry
) -> tuple[DataContract, ...]:
    return tuple(
        contract
        for contract in registry.contracts
        if contract.tenant == actor.tenant
        and Operation.MANAGE_KNOWLEDGE in actor.operations
        and visible(actor, contract.access, Purpose.AUDIT)
    )


def _metadata_visible(
    record: StoredDocument,
    actor: Principal,
    registry: DataContractRegistry,
    contracts: tuple[DataContract, ...],
) -> bool:
    if (
        record.access_snapshot is None
        or not binding_is_current(record.meta, registry)
        or not visible(actor, record.access_snapshot, Purpose.AUDIT)
    ):
        return False
    if record.meta.contract_id is None:
        return True
    return any(contract.id == record.meta.contract_id for contract in contracts)


def _receipt_meta_visible(
    conn: sqlite3.Connection,
    meta: KnowledgeDocumentMeta,
    actor: Principal,
    contract: DataContract,
) -> bool:
    record = document_record(conn, meta.document_id)
    return (
        record is not None
        and record_matches_contract(record, contract, exact_binding=True)
        and record.access_snapshot is not None
        and visible(actor, record.access_snapshot, Purpose.AUDIT)
    )
