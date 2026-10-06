import sqlite3
from dataclasses import dataclass
from typing import assert_never

from ax_starter.common import Access, AXError, Principal
from ax_starter.data_contracts import DataContract, validate_document
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    DocumentLifecycle,
    KnowledgeDocumentMeta,
    KnowledgeMutation,
    RetireDocument,
    TombstoneDocument,
    UpsertDocument,
)
from ax_starter.knowledge_history import save_accepted_version, source_version_accepted
from ax_starter.knowledge_store import (
    StoredDocument,
    access_hash,
    document_record,
    save_document,
)
from ax_starter.knowledge_visibility import management_access_visible, record_matches_contract
from ax_starter.ontology import Document, DomainPack
from ax_starter.retrieval import content_hash


@dataclass(frozen=True, slots=True)
class MutationContext:
    conn: sqlite3.Connection
    template: DomainPack
    contract: DataContract
    actor: Principal


def apply_mutation(context: MutationContext, mutation: KnowledgeMutation) -> StoredDocument:
    match mutation:
        case UpsertDocument():
            return _upsert(context, mutation)
        case RetireDocument(document_id=document_id):
            stored = _owned_document(context, document_id)
            if stored.meta.lifecycle is DocumentLifecycle.TOMBSTONE:
                raise AXError("document_tombstoned")
            changed = StoredDocument(
                meta=stored.meta.model_copy(
                    update={
                        "lifecycle": DocumentLifecycle.RETIRED,
                        "revision": stored.meta.revision + 1,
                    }
                ),
                document=stored.document,
                access_snapshot=stored.access_snapshot,
            )
        case TombstoneDocument(document_id=document_id):
            stored = _owned_document(context, document_id, exact_binding=False)
            if stored.meta.lifecycle is DocumentLifecycle.TOMBSTONE:
                raise AXError("document_tombstoned")
            changed = StoredDocument(
                meta=stored.meta.model_copy(
                    update={
                        "lifecycle": DocumentLifecycle.TOMBSTONE,
                        "revision": stored.meta.revision + 1,
                        "contract_version": context.contract.version,
                        "contract_sha256": content_hash(context.contract.model_dump_json()),
                    }
                ),
                document=None,
                access_snapshot=stored.access_snapshot,
            )
        case ChangeDocumentAccess(document_id=document_id, access=access):
            stored = _owned_document(context, document_id)
            if stored.document is None:
                raise AXError("document_tombstoned")
            _require_allowed_access(context.contract, access)
            document = stored.document.model_copy(update={"access": access})
            changed = StoredDocument(
                meta=stored.meta.model_copy(
                    update={
                        "access_sha256": access_hash(access),
                        "revision": stored.meta.revision + 1,
                    }
                ),
                document=document,
                access_snapshot=access,
            )
        case unreachable:
            assert_never(unreachable)
    save_document(context.conn, changed)
    return changed


def _upsert(context: MutationContext, mutation: UpsertDocument) -> StoredDocument:
    _require_document_namespace(context.contract, mutation.candidate.document_id)
    existing = document_record(context.conn, mutation.candidate.document_id)
    if existing is not None and (
        not record_matches_contract(existing, context.contract, exact_binding=False)
        or not management_access_visible(existing, context.actor)
    ):
        raise AXError("document_not_found", 404)
    validation = validate_document(context.contract, mutation.candidate)
    if not mutation.candidate.access.groups or not validation.accepted:
        raise AXError("data_contract_violation", 422)
    if existing is not None and existing.meta.lifecycle is DocumentLifecycle.TOMBSTONE:
        raise AXError("tombstone_recreation_forbidden")
    if source_version_accepted(
        context.conn,
        context.contract.tenant,
        context.contract.collection_source.identifier,
        mutation.candidate.document_id,
        mutation.candidate.source_version,
    ):
        raise AXError("source_version_reuse")
    try:
        text = mutation.candidate.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AXError("document_content_not_utf8", 422) from exc
    document = Document(
        id=mutation.candidate.document_id,
        object_ids=mutation.candidate.object_scope,
        title=mutation.title,
        text=text,
        source_uri=mutation.candidate.origin.uri,
        source_version=mutation.candidate.source_version,
        access=mutation.candidate.access,
        valid_until=mutation.valid_until,
    )
    stored = StoredDocument(
        meta=KnowledgeDocumentMeta(
            document_id=document.id,
            tenant=document.access.tenant,
            source_identifier=mutation.candidate.origin.identifier,
            source_version=document.source_version,
            contract_id=context.contract.id,
            contract_version=context.contract.version,
            contract_sha256=content_hash(context.contract.model_dump_json()),
            lifecycle=DocumentLifecycle.ACTIVE,
            content_sha256=validation.computed_sha256,
            access_sha256=access_hash(document.access),
            revision=1 if existing is None else existing.meta.revision + 1,
        ),
        document=document,
        access_snapshot=document.access,
    )
    save_document(context.conn, stored)
    save_accepted_version(context.conn, stored.meta)
    return stored


def _owned_document(
    context: MutationContext,
    document_id: str,
    *,
    exact_binding: bool = True,
) -> StoredDocument:
    stored = document_record(context.conn, document_id)
    if stored is None or not (
        record_matches_contract(stored, context.contract, exact_binding=exact_binding)
        and management_access_visible(stored, context.actor)
    ):
        raise AXError("document_not_found", 404)
    return stored


def _require_allowed_access(contract: DataContract, access: Access) -> None:
    if (
        access.tenant != contract.tenant
        or not access.groups
        or access.sensitivity < contract.effective_minimum_sensitivity
        or access.sensitivity > contract.access.sensitivity
        or not access.groups <= contract.access.groups
        or not access.purposes <= contract.access.purposes
    ):
        raise AXError("data_contract_violation", 422)


def _require_document_namespace(contract: DataContract, document_id: str) -> None:
    prefix, separator, suffix = document_id.rpartition(".")
    if separator != "." or prefix != contract.tenant or not suffix or "." in suffix:
        raise AXError("data_contract_violation", 422)
