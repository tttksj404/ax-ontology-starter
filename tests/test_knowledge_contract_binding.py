from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, assert_never

import pytest

from ax_starter.action_contracts import ProposeRequest
from ax_starter.actions import ActionEngine
from ax_starter.common import AXError, Principal, Purpose
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    KnowledgeMutationBatch,
    RetireDocument,
    TombstoneDocument,
    UpsertDocument,
)
from ax_starter.knowledge_store import document_record
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def test_managed_document_is_hidden_after_live_contract_drift(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    active_registry = [initial]
    store = Store(
        tmp_path / "contract-binding.db",
        pack,
        contract_resolver=lambda: active_registry[0],
    )
    service = KnowledgeService(store, pack, initial)
    _ = service.apply(management_actor(), upsert_batch(now + timedelta(days=30)), now)
    with store.transaction() as conn:
        assert "acme.managed-1" in {item.id for item in store.current_pack(conn, pack).documents}
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.meta.contract_id == "knowledge-contract"
        assert stored.meta.contract_version == "1"
        assert stored.meta.contract_sha256 is not None

    # When
    changed = initial.contracts[0].model_copy(update={"version": "2"})
    active_registry[0] = DataContractRegistry(contracts=(changed,))

    # Then
    with store.transaction() as conn:
        assert "acme.managed-1" not in {
            item.id for item in store.current_pack(conn, pack).documents
        }


def test_unbound_managed_document_is_hidden_but_bootstrap_documents_remain(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(
        tmp_path / "unbound.db",
        pack,
        contract_resolver=lambda: contracts,
    )
    service = KnowledgeService(store, pack, contracts)
    _ = service.apply(management_actor(), upsert_batch(now + timedelta(days=30)), now)
    with store.transaction() as conn:
        _ = conn.execute(
            """UPDATE knowledge_documents SET contract_id = NULL,
            contract_version = NULL, contract_sha256 = NULL WHERE document_id = 'acme.managed-1'"""
        )

    # When
    with store.transaction() as conn:
        current = store.current_pack(conn, pack)

    # Then
    assert "acme.managed-1" not in {item.id for item in current.documents}
    assert {item.id for item in pack.documents} <= {item.id for item in current.documents}


@pytest.mark.parametrize("operation", ["upsert", "change_acl", "retire", "tombstone"])
def test_other_contract_cannot_claim_managed_document_with_shared_source(
    tmp_path: Path,
    pack: DomainPack,
    now: datetime,
    operation: Literal["upsert", "change_acl", "retire", "tombstone"],
) -> None:
    # Given
    owner = registry().contracts[0]
    claimant = owner.model_copy(update={"id": "claimant-contract"})
    contracts = DataContractRegistry(contracts=(owner, claimant))
    store = Store(
        tmp_path / f"contract-owner-{operation}.db",
        pack,
        contract_resolver=lambda: contracts,
    )
    service = KnowledgeService(store, pack, contracts)
    actor = management_actor()
    _ = service.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    match operation:
        case "upsert":
            mutation = UpsertDocument(
                candidate=candidate(source_version="2", content=b"claimed"),
                title="Claimed",
                valid_until=now + timedelta(days=30),
            )
        case "change_acl":
            mutation = ChangeDocumentAccess(document_id="acme.managed-1", access=candidate().access)
        case "retire":
            mutation = RetireDocument(document_id="acme.managed-1")
        case "tombstone":
            mutation = TombstoneDocument(document_id="acme.managed-1")
        case unreachable:
            assert_never(unreachable)
    claim = KnowledgeMutationBatch(
        contract_id=claimant.id,
        request_key=f"claim-{operation}",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(mutation,),
    )

    # When / Then
    with pytest.raises(AXError, match="document_not_found") as raised:
        _ = service.apply(actor, claim, now)
    assert raised.value.status == 404
    assert service.state(actor).tenant_revision == 1
    with store.transaction() as conn:
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.meta.contract_id == owner.id
        assert stored.meta.source_version == "1"
        assert store.audit_check(conn, "acme").event_count == 1


def test_same_contract_id_can_rebind_after_live_version_upgrade(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    active_registry = [initial]
    store = Store(
        tmp_path / "contract-rebind.db",
        pack,
        contract_resolver=lambda: active_registry[0],
    )
    actor = management_actor()
    _ = KnowledgeService(store, pack, initial).apply(
        actor, upsert_batch(now + timedelta(days=30)), now
    )
    upgraded = DataContractRegistry(
        contracts=(initial.contracts[0].model_copy(update={"version": "2"}),)
    )
    active_registry[0] = upgraded

    # When
    receipt = KnowledgeService(store, pack, upgraded).apply(
        actor,
        upsert_batch(
            now + timedelta(days=30),
            request_key="contract-upgrade",
            tenant_revision=1,
            source_revision=1,
            document=candidate(source_version="2", content=b"upgraded"),
        ),
        now,
    )

    # Then
    assert receipt.documents[0].contract_id == "knowledge-contract"
    assert receipt.documents[0].contract_version == "2"
    with store.transaction() as conn:
        assert "acme.managed-1" in {item.id for item in store.current_pack(conn, pack).documents}


@pytest.mark.parametrize("phase", ["propose", "approve", "execute"])
def test_contract_drift_revokes_managed_action_evidence(
    tmp_path: Path,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    phase: str,
) -> None:
    # Given
    object_access = next(item.access for item in pack.objects if item.id == "request-1")
    base = registry().contracts[0]
    contract_access = base.access.model_copy(
        update={"purposes": frozenset({Purpose.AUDIT, Purpose.OPERATIONS})}
    )
    contract = base.model_copy(
        update={
            "object_scope": ("request-1",),
            "access": contract_access,
            "minimum_sensitivity": object_access.sensitivity,
        }
    )
    contracts = DataContractRegistry(contracts=(contract,))
    active_registry = [contracts]
    store = Store(
        tmp_path / f"action-binding-{phase}.db",
        pack,
        contract_resolver=lambda: active_registry[0],
    )
    service = KnowledgeService(store, pack, contracts)
    document_access = object_access.model_copy(update={"purposes": frozenset({Purpose.OPERATIONS})})
    managed = candidate().model_copy(
        update={"object_scope": ("request-1",), "access": document_access}
    )
    _ = service.apply(
        management_actor(),
        upsert_batch(now + timedelta(days=30), document=managed),
        now,
    )
    engine = ActionEngine(store, pack, principals)
    request = ProposeRequest(
        action_type="mark_reviewed",
        object_id="request-1",
        new_status="reviewed",
        expected_version=1,
        evidence_ids=("acme.managed-1",),
        request_key=f"contract-drift-{phase}",
    )
    proposal = None if phase == "propose" else engine.propose(principals[0], request, now)
    if phase == "execute":
        assert proposal is not None
        proposal = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    active_registry[0] = DataContractRegistry(
        contracts=(contract.model_copy(update={"version": "2"}),)
    )

    # When / Then
    if phase == "propose":
        with pytest.raises(AXError, match="evidence_not_available"):
            _ = engine.propose(principals[0], request, now)
    elif phase == "approve":
        assert proposal is not None
        with pytest.raises(AXError, match="evidence_changed_or_revoked"):
            _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    else:
        assert proposal is not None
        with pytest.raises(AXError, match="evidence_changed_or_revoked"):
            _ = engine.execute(principals[0], proposal.id, now)
