from datetime import datetime
from hashlib import sha256

from ax_starter.common import Access, Operation, Principal, Purpose, Sensitivity
from ax_starter.data_contracts import (
    DataContract,
    DataContractRegistry,
    DeletionPolicy,
    DocumentCandidate,
    LifecyclePolicy,
    ProvenanceClaim,
    ReconciliationAction,
    ReconciliationPolicy,
    SourceReference,
)
from ax_starter.knowledge_contracts import KnowledgeMutationBatch, UpsertDocument


def management_actor(tenant: str = "acme") -> Principal:
    return Principal(
        subject="knowledge-admin",
        tenant=tenant,
        groups=frozenset({"procurement", "private"}),
        clearance=Sensitivity.RESTRICTED,
        operations=frozenset({Operation.READ, Operation.MANAGE_KNOWLEDGE}),
        purposes=frozenset({Purpose.AUDIT}),
    )


def registry(
    *, tenant: str = "acme", contract_id: str = "knowledge-contract"
) -> DataContractRegistry:
    access = Access(
        tenant=tenant,
        groups=frozenset({"procurement", "private"}),
        sensitivity=Sensitivity.RESTRICTED,
        purposes=frozenset({Purpose.AUDIT}),
    )
    return DataContractRegistry(
        contracts=(
            DataContract(
                id=contract_id,
                version="1",
                tenant=tenant,
                owner="knowledge-owner",
                collection_source=SourceReference(identifier="source-a", uri="source://policy"),
                object_scope=("procedure-1",),
                access=access,
                minimum_sensitivity=Sensitivity.INTERNAL,
                lifecycle=LifecyclePolicy(
                    refresh_interval_hours=24,
                    deletion=DeletionPolicy(
                        retention_days=30,
                        delete_within_hours=24,
                        propagate_source_deletion=True,
                    ),
                    reconciliation=ReconciliationPolicy(
                        interval_hours=24,
                        action=ReconciliationAction.REJECT,
                    ),
                ),
                required_provenance=frozenset({"source-a"}),
            ),
        )
    )


def candidate(
    *,
    document_id: str = "acme.managed-1",
    source_version: str = "1",
    content: bytes = b"managed knowledge",
) -> DocumentCandidate:
    digest = sha256(content).hexdigest()
    return DocumentCandidate(
        document_id=document_id,
        tenant="acme",
        origin=SourceReference(identifier="source-a", uri="source://policy"),
        source_version=source_version,
        object_scope=("procedure-1",),
        access=Access(
            tenant="acme",
            groups=frozenset({"procurement"}),
            sensitivity=Sensitivity.INTERNAL,
            purposes=frozenset({Purpose.AUDIT}),
        ),
        content=content,
        declared_sha256=digest,
        provenance=(
            ProvenanceClaim(
                source_identifier="source-a",
                record_identifier=document_id,
                content_sha256=digest,
            ),
        ),
    )


def upsert_batch(
    valid_until: datetime,
    *,
    request_key: str = "batch-1",
    tenant_revision: int = 0,
    source_revision: int = 0,
    document: DocumentCandidate | None = None,
) -> KnowledgeMutationBatch:
    return KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key=request_key,
        expected_tenant_revision=tenant_revision,
        expected_source_revision=source_revision,
        mutations=(
            UpsertDocument(
                candidate=document or candidate(),
                title="Managed knowledge",
                valid_until=valid_until,
            ),
        ),
    )
