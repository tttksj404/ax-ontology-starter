from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import Access, AXError, Purpose, Sensitivity
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    KnowledgeMutationBatch,
    RetireDocument,
    UpsertDocument,
)
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def service(tmp_path: Path, pack: DomainPack) -> KnowledgeService:
    contracts = registry()
    store = Store(tmp_path / "atomic.db", pack, contract_resolver=lambda: contracts)
    return KnowledgeService(store, pack, contracts)


def test_middle_failure_rolls_back_documents_revisions_and_audit(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    private_access = candidate().access.model_copy(update={"groups": frozenset({"private"})})
    batch = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="partial-failure",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(
            ChangeDocumentAccess(document_id="acme.managed-1", access=private_access),
            RetireDocument(document_id="missing-doc"),
        ),
    )

    # When / Then
    with pytest.raises(AXError, match="document_not_found"):
        _ = current.apply(actor, batch, now)
    assert current.state(actor).tenant_revision == 1
    with current.store.transaction() as conn:
        documents = current.store.current_pack(conn, pack).documents
        document = next(item for item in documents if item.id == "acme.managed-1")
        assert document.access.groups == frozenset({"procurement"})
        assert current.store.audit_check(conn, "acme").event_count == 1


def test_document_model_validation_is_typed_and_rolls_back_batch(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    private_access = candidate().access.model_copy(update={"groups": frozenset({"private"})})
    oversized = candidate(
        document_id="acme.oversized-doc", source_version="2", content=b"x" * 16_001
    )
    batch = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="invalid-document",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(
            ChangeDocumentAccess(document_id="acme.managed-1", access=private_access),
            UpsertDocument(
                candidate=oversized,
                title="Oversized",
                valid_until=now + timedelta(days=30),
            ),
        ),
    )

    # When / Then
    with pytest.raises(AXError, match="document_domain_invalid") as raised:
        _ = current.apply(actor, batch, now)
    assert raised.value.status == 422
    assert current.state(actor).tenant_revision == 1
    with current.store.transaction() as conn:
        documents = current.store.current_pack(conn, pack).documents
        document = next(item for item in documents if item.id == "acme.managed-1")
        assert document.access.groups == frozenset({"procurement"})
        assert all(item.id != "acme.oversized-doc" for item in documents)
        assert current.store.audit_check(conn, "acme").event_count == 1


def test_failed_batch_does_not_reserve_source_version(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    replacement = candidate(source_version="2", content=b"version two")
    failed = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="failed-version",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(
            UpsertDocument(
                candidate=replacement,
                title="Version two",
                valid_until=now + timedelta(days=30),
            ),
            RetireDocument(document_id="missing-doc"),
        ),
    )

    # When / Then
    with pytest.raises(AXError, match="document_not_found"):
        _ = current.apply(actor, failed, now)
    receipt = current.apply(
        actor,
        upsert_batch(
            now + timedelta(days=30),
            request_key="retry-version",
            tenant_revision=1,
            source_revision=1,
            document=replacement,
        ),
        now,
    )
    assert receipt.documents[0].source_version == "2"
    assert receipt.tenant_revision == 2
    with current.store.transaction() as conn:
        assert current.store.audit_check(conn, "acme").event_count == 2


def test_other_tenant_cannot_claim_existing_document_id(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    acme_registry = registry().contracts[0]
    beta_access = acme_registry.access.model_copy(update={"tenant": "beta"})
    beta_contract = acme_registry.model_copy(
        update={
            "tenant": "beta",
            "access": beta_access,
            "object_scope": ("beta-request",),
        }
    )
    contracts = DataContractRegistry(contracts=(acme_registry, beta_contract))
    current = KnowledgeService(
        Store(tmp_path / "tenant.db", pack, contract_resolver=lambda: contracts),
        pack,
        contracts,
    )
    acme_actor = management_actor()
    _ = current.apply(acme_actor, upsert_batch(now + timedelta(days=30)), now)
    beta_actor = management_actor("beta")
    steal = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="steal",
        expected_tenant_revision=0,
        expected_source_revision=0,
        mutations=(RetireDocument(document_id="acme.managed-1"),),
    )

    # When / Then
    with pytest.raises(AXError, match="document_not_found"):
        _ = current.apply(beta_actor, steal, now)


@pytest.mark.parametrize(
    "access",
    [
        Access(
            tenant="acme",
            groups=frozenset({"unknown"}),
            sensitivity=Sensitivity.INTERNAL,
            purposes=frozenset({Purpose.AUDIT}),
        ),
        Access(
            tenant="acme",
            groups=frozenset({"procurement"}),
            sensitivity=Sensitivity.INTERNAL,
            purposes=frozenset({Purpose.OPERATIONS}),
        ),
    ],
)
def test_contract_access_ceiling_violation_is_rejected_without_state_change(
    tmp_path: Path, pack: DomainPack, now: datetime, access: Access
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    invalid = candidate().model_copy(update={"access": access})

    # When / Then
    with pytest.raises(AXError, match="data_contract_violation"):
        _ = current.apply(
            actor,
            upsert_batch(now + timedelta(days=30), document=invalid),
            now,
        )
    assert current.state(actor).tenant_revision == 0


def test_domain_pack_rejects_underclassified_document(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contract = (
        registry().contracts[0].model_copy(update={"minimum_sensitivity": Sensitivity.PUBLIC})
    )
    contracts = DataContractRegistry(contracts=(contract,))
    current = KnowledgeService(
        Store(tmp_path / "domain.db", pack, contract_resolver=lambda: contracts),
        pack,
        contracts,
    )
    actor = management_actor()
    public_access = candidate().access.model_copy(update={"sensitivity": Sensitivity.PUBLIC})
    invalid = candidate().model_copy(update={"access": public_access})

    # When / Then
    with pytest.raises(AXError, match="document_domain_invalid"):
        _ = current.apply(
            actor,
            upsert_batch(now + timedelta(days=30), document=invalid),
            now,
        )
    assert current.state(actor).tenant_revision == 0
