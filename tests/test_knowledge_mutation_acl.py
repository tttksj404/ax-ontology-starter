from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, assert_never

import pytest

from ax_starter.common import Access, AXError, Operation, Principal, Purpose, Sensitivity
from ax_starter.data_contracts import DataContractRegistry, DocumentCandidate
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    KnowledgeMutation,
    KnowledgeMutationBatch,
    RetireDocument,
    TombstoneDocument,
    UpsertDocument,
)
from ax_starter.knowledge_store import stored_batch
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, registry, upsert_batch

MutationName = Literal["upsert", "change_acl", "retire", "tombstone"]


def _steward(group: str) -> Principal:
    return Principal(
        subject=f"{group}-manager",
        tenant="acme",
        groups=frozenset({group}),
        clearance=Sensitivity.RESTRICTED,
        operations=frozenset({Operation.READ, Operation.MANAGE_KNOWLEDGE}),
        purposes=frozenset({Purpose.AUDIT}),
    )


def _private_candidate(
    *, source_version: str = "1", purposes: frozenset[Purpose] | None = None
) -> DocumentCandidate:
    access = Access(
        tenant="acme",
        groups=frozenset({"private"}),
        sensitivity=Sensitivity.RESTRICTED,
        purposes=frozenset({Purpose.AUDIT}) if purposes is None else purposes,
    )
    return candidate(source_version=source_version).model_copy(update={"access": access})


def _mutation(name: MutationName, now: datetime) -> KnowledgeMutation:
    match name:
        case "upsert":
            return UpsertDocument(
                candidate=_private_candidate(source_version="2"),
                title="Private replacement",
                valid_until=now + timedelta(days=30),
            )
        case "change_acl":
            return ChangeDocumentAccess(
                document_id="acme.managed-1", access=_private_candidate().access
            )
        case "retire":
            return RetireDocument(document_id="acme.managed-1")
        case "tombstone":
            return TombstoneDocument(document_id="acme.managed-1")
        case unreachable:
            assert_never(unreachable)


def _batch(name: MutationName, now: datetime) -> KnowledgeMutationBatch:
    return KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key=f"private-{name}",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(_mutation(name, now),),
    )


@pytest.mark.parametrize("operation", ["upsert", "change_acl", "retire", "tombstone"])
def test_non_owner_group_cannot_mutate_existing_private_document(
    tmp_path: Path, pack: DomainPack, now: datetime, operation: MutationName
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / f"denied-{operation}.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    _ = service.apply(
        _steward("private"),
        upsert_batch(now + timedelta(days=30), document=_private_candidate()),
        now,
    )

    # When / Then
    with pytest.raises(AXError, match="document_not_found") as raised:
        _ = service.apply(_steward("procurement"), _batch(operation, now), now)
    assert raised.value.status == 404
    assert service.state(_steward("private")).tenant_revision == 1
    with store.transaction() as conn:
        assert conn.execute(
            """SELECT COUNT(*) FROM knowledge_accepted_versions
            WHERE document_id = 'acme.managed-1'"""
        ).fetchone() == (1,)
        assert store.audit_check(conn, "acme").event_count == 1


@pytest.mark.parametrize("operation", ["upsert", "change_acl", "retire", "tombstone"])
def test_owner_group_can_mutate_existing_private_document(
    tmp_path: Path, pack: DomainPack, now: datetime, operation: MutationName
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / f"allowed-{operation}.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    owner = _steward("private")
    _ = service.apply(
        owner,
        upsert_batch(now + timedelta(days=30), document=_private_candidate()),
        now,
    )

    # When
    receipt = service.apply(owner, _batch(operation, now), now)

    # Then
    assert receipt.tenant_revision == 2
    assert receipt.documents[0].document_id == "acme.managed-1"


def test_document_purpose_does_not_block_authorized_management(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    base = registry().contracts[0]
    contract = base.model_copy(
        update={
            "access": base.access.model_copy(
                update={"purposes": frozenset({Purpose.AUDIT, Purpose.OPERATIONS})}
            )
        }
    )
    contracts = DataContractRegistry(contracts=(contract,))
    store = Store(tmp_path / "purpose-management.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    owner = _steward("private")
    operations_only = _private_candidate(purposes=frozenset({Purpose.OPERATIONS}))
    _ = service.apply(
        owner,
        upsert_batch(now + timedelta(days=30), document=operations_only),
        now,
    )

    # When
    receipt = service.apply(owner, _batch("retire", now), now)

    # Then
    assert receipt.tenant_revision == 2
    assert receipt.documents == ()
    assert "acme.managed-1" not in {item.document_id for item in service.state(owner).documents}


def test_success_receipt_is_projected_after_actor_removes_own_group(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "self-revoke.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    actor = _steward("procurement")
    _ = service.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    batch = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="self-revoke",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(
            ChangeDocumentAccess(document_id="acme.managed-1", access=_private_candidate().access),
        ),
    )

    # When
    projected = service.apply(actor, batch, now)

    # Then
    assert projected.documents == ()
    with store.transaction() as conn:
        persisted = stored_batch(conn, "acme", "knowledge-contract", "apply", "self-revoke")
        assert persisted is not None
        assert len(persisted.receipt.documents) == 1
        assert store.audit_check(conn, "acme").event_count == 2


def test_replay_projects_documents_to_current_actor_visibility(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "replay-projection.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    owner = _steward("private")
    other = _steward("procurement")
    batch = upsert_batch(now + timedelta(days=30), document=_private_candidate())
    accepted = service.apply(owner, batch, now)

    # When
    hidden = service.apply(other, batch, now)
    visible = service.apply(owner, batch, now)

    # Then
    assert hidden.documents == ()
    assert visible == accepted
    assert hidden.model_copy(update={"documents": accepted.documents}) == accepted
    with store.transaction() as conn:
        assert store.audit_check(conn, "acme").event_count == 1
