import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Never

from ax_starter.common import AXError, Principal, Purpose, Sensitivity
from ax_starter.knowledge_contracts import KnowledgeDocumentMeta
from ax_starter.knowledge_store import document_record
from ax_starter.ontology import Document, DomainPack
from ax_starter.policy import visible
from ax_starter.retrieval import Answer, Citation, content_hash
from ax_starter.store import Store
from ax_starter.wiki_contracts import WikiSourceBinding


@dataclass(frozen=True, slots=True)
class SourcePolicyContext:
    conn: sqlite3.Connection
    store: Store
    template: DomainPack
    actor: Principal
    purpose: Purpose
    query_sensitivity: Sensitivity
    now: datetime


def build_source_bindings(
    context: SourcePolicyContext,
    answer: Answer,
) -> tuple[tuple[WikiSourceBinding, ...], Sensitivity]:
    pack = context.store.current_pack(context.conn, context.template)
    documents = {document.id: document for document in pack.documents}
    entities = {entity.id: entity for entity in pack.objects}
    bindings: list[WikiSourceBinding] = []
    labels = [context.query_sensitivity, answer.sensitivity]
    for citation in answer.citations:
        document = documents.get(citation.document_id)
        if document is None or document.valid_until <= context.now:
            raise AXError("wiki_source_stale", 409)
        if not visible(context.actor, document.access, context.purpose):
            raise AXError("access_denied", 403)
        scoped = tuple(entities.get(object_id) for object_id in document.object_ids)
        if any(entity is None for entity in scoped) or any(
            not visible(context.actor, entity.access, context.purpose)
            for entity in scoped
            if entity is not None
        ):
            raise AXError("access_denied", 403)
        record = document_record(context.conn, document.id)
        if record is None or record.document is None or record.access_snapshot is None:
            raise AXError("wiki_source_stale", 409)
        _require_citation_matches_document(citation, document)
        labels.append(document.access.sensitivity)
        labels.extend(entity.access.sensitivity for entity in scoped if entity is not None)
        bindings.append(
            WikiSourceBinding(
                document_id=document.id,
                document_sha256=content_hash(document.model_dump_json()),
                content_sha256=content_hash(document.text),
                access_sha256=content_hash(document.access.model_dump_json()),
                source_identifier=record.meta.source_identifier,
                source_version=document.source_version,
                object_ids=document.object_ids,
                access_snapshot=document.access,
                valid_until=document.valid_until,
                contract_id=record.meta.contract_id,
                contract_version=record.meta.contract_version,
                contract_sha256=record.meta.contract_sha256,
            )
        )
    if not bindings:
        raise AXError("wiki_source_required", 422)
    return tuple(bindings), max(labels)


def require_sources_current(
    context: SourcePolicyContext,
    bindings: tuple[WikiSourceBinding, ...],
    *,
    read_projection: bool,
) -> Sensitivity:
    pack = context.store.current_pack(context.conn, context.template)
    documents = {document.id: document for document in pack.documents}
    entities = {entity.id: entity for entity in pack.objects}
    labels = [context.query_sensitivity]
    for binding in bindings:
        document = documents.get(binding.document_id)
        if document is None:
            _source_failure(read_projection)
        record = document_record(context.conn, binding.document_id)
        if record is None or not _record_binding_matches(binding, record.meta):
            _source_failure(read_projection)
        if not _binding_matches(binding, document) or document.valid_until <= context.now:
            _source_failure(read_projection)
        if not visible(context.actor, binding.access_snapshot, context.purpose):
            _source_failure(read_projection)
        if not visible(context.actor, document.access, context.purpose):
            _source_failure(read_projection)
        labels.append(document.access.sensitivity)
        for object_id in binding.object_ids:
            entity = entities.get(object_id)
            if entity is None or not visible(context.actor, entity.access, context.purpose):
                _source_failure(read_projection)
            labels.append(entity.access.sensitivity)
    return max(labels)


def require_sources_access(
    context: SourcePolicyContext,
    bindings: tuple[WikiSourceBinding, ...],
) -> Sensitivity:
    """Authorize a historical head without treating expected source drift as disclosure."""
    pack = context.store.current_pack(context.conn, context.template)
    entities = {entity.id: entity for entity in pack.objects}
    labels = [context.query_sensitivity]
    for binding in bindings:
        record = document_record(context.conn, binding.document_id)
        if (
            record is None
            or record.document is None
            or record.access_snapshot is None
            or record.meta.tenant != context.actor.tenant
        ):
            _source_failure(read_projection=True)
        document = record.document
        if not visible(context.actor, binding.access_snapshot, context.purpose):
            _source_failure(read_projection=True)
        if not visible(context.actor, document.access, context.purpose):
            _source_failure(read_projection=True)
        labels.append(document.access.sensitivity)
        for object_id in set(binding.object_ids) | set(document.object_ids):
            entity = entities.get(object_id)
            if entity is None or not visible(context.actor, entity.access, context.purpose):
                _source_failure(read_projection=True)
            labels.append(entity.access.sensitivity)
    return max(labels)


def _binding_matches(binding: WikiSourceBinding, document: Document) -> bool:
    return (
        binding.document_id == document.id
        and binding.document_sha256 == content_hash(document.model_dump_json())
        and binding.content_sha256 == content_hash(document.text)
        and binding.access_sha256 == content_hash(document.access.model_dump_json())
        and binding.source_version == document.source_version
        and binding.object_ids == document.object_ids
        and binding.access_snapshot == document.access
        and binding.valid_until == document.valid_until
    )


def _record_binding_matches(binding: WikiSourceBinding, meta: KnowledgeDocumentMeta) -> bool:
    return (
        binding.source_identifier == meta.source_identifier
        and binding.contract_id == meta.contract_id
        and binding.contract_version == meta.contract_version
        and binding.contract_sha256 == meta.contract_sha256
    )


def _require_citation_matches_document(citation: Citation, document: Document) -> None:
    if (
        citation.title != document.title
        or citation.source_uri != document.source_uri
        or citation.source_version != document.source_version
        or citation.content_sha256 != content_hash(document.text)
        or citation.access_sha256 != content_hash(document.access.model_dump_json())
        or citation.object_ids != document.object_ids
        or citation.quote != document.text
        or citation.sensitivity != document.access.sensitivity
    ):
        raise AXError("wiki_source_integrity_failure")


def _source_failure(read_projection: bool) -> Never:
    if read_projection:
        raise AXError("wiki_page_not_found", 404)
    raise AXError("wiki_source_stale", 409)
