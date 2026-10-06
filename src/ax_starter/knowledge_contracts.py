from enum import StrEnum
from typing import Annotated, Literal, Self, assert_never

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import Access, Contract, Identifier
from ax_starter.data_contracts import DocumentCandidate


class DocumentLifecycle(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    TOMBSTONE = "tombstone"


class UpsertDocument(Contract):
    operation: Literal["upsert"] = "upsert"
    candidate: DocumentCandidate
    title: str = Field(min_length=1, max_length=200)
    valid_until: AwareDatetime


class RetireDocument(Contract):
    operation: Literal["retire"] = "retire"
    document_id: Identifier


class TombstoneDocument(Contract):
    operation: Literal["tombstone"] = "tombstone"
    document_id: Identifier


class ChangeDocumentAccess(Contract):
    operation: Literal["change_acl"] = "change_acl"
    document_id: Identifier
    access: Access


KnowledgeMutation = Annotated[
    UpsertDocument | RetireDocument | TombstoneDocument | ChangeDocumentAccess,
    Field(discriminator="operation"),
]


class KnowledgeMutationBatch(Contract):
    contract_id: Identifier
    request_key: Identifier
    expected_tenant_revision: int = Field(ge=0)
    expected_source_revision: int = Field(ge=0)
    mutations: tuple[KnowledgeMutation, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def document_ids_must_be_unique(self) -> Self:
        document_ids = tuple(_mutation_document_id(item) for item in self.mutations)
        if len(document_ids) != len(set(document_ids)):
            raise PydanticCustomError("duplicate_document_mutation", "duplicate document mutation")
        return self


class KnowledgeDocumentMeta(Contract):
    document_id: Identifier
    tenant: Identifier
    source_identifier: Identifier
    source_version: Identifier
    contract_id: Identifier | None = None
    contract_version: Identifier | None = None
    contract_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    lifecycle: DocumentLifecycle
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(ge=0)


class KnowledgeMutationReceipt(Contract):
    tenant: Identifier
    contract_id: Identifier
    request_key: Identifier
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tenant_revision: int = Field(ge=1)
    source_revision: int = Field(ge=1)
    documents: tuple[KnowledgeDocumentMeta, ...]
    origin_authenticated: Literal[False] = False
    provenance_authenticated: Literal[False] = False


class KnowledgeSourceHead(Contract):
    source_identifier: Identifier
    revision: int = Field(ge=0)
    state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class KnowledgeState(Contract):
    tenant: Identifier
    tenant_revision: int = Field(ge=0)
    state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    sources: tuple[KnowledgeSourceHead, ...]
    documents: tuple[KnowledgeDocumentMeta, ...]


class SourceSnapshotDocument(Contract):
    candidate: DocumentCandidate
    title: str = Field(min_length=1, max_length=200)
    valid_until: AwareDatetime


class SourceSnapshotInput(Contract):
    contract_id: Identifier
    request_key: Identifier
    expected_tenant_revision: int = Field(ge=0)
    expected_source_revision: int = Field(ge=0)
    documents: tuple[SourceSnapshotDocument, ...] = Field(min_length=1, max_length=100)
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def document_ids_must_be_unique(self) -> Self:
        document_ids = tuple(document.candidate.document_id for document in self.documents)
        if len(document_ids) != len(set(document_ids)):
            raise PydanticCustomError("duplicate_snapshot_document", "duplicate snapshot document")
        return self


def mutation_batch_from_snapshot(snapshot: SourceSnapshotInput) -> KnowledgeMutationBatch:
    return KnowledgeMutationBatch(
        contract_id=snapshot.contract_id,
        request_key=snapshot.request_key,
        expected_tenant_revision=snapshot.expected_tenant_revision,
        expected_source_revision=snapshot.expected_source_revision,
        mutations=tuple(
            UpsertDocument(
                candidate=document.candidate,
                title=document.title,
                valid_until=document.valid_until,
            )
            for document in snapshot.documents
        ),
    )


def _mutation_document_id(mutation: KnowledgeMutation) -> str:
    match mutation:
        case UpsertDocument(candidate=candidate):
            return candidate.document_id
        case RetireDocument(document_id=document_id):
            return document_id
        case TombstoneDocument(document_id=document_id):
            return document_id
        case ChangeDocumentAccess(document_id=document_id):
            return document_id
        case unreachable:
            assert_never(unreachable)
