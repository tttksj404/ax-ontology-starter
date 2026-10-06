from datetime import datetime, timedelta
from pathlib import Path

from ax_starter.common import Access, Operation, Principal, Purpose, Sensitivity
from ax_starter.data_contracts import DataContractRegistry, DocumentCandidate, SourceReference
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import KnowledgeMutationBatch, TombstoneDocument
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, registry, upsert_batch


def _steward(group: str) -> Principal:
    return Principal(
        subject=f"{group}-steward",
        tenant="acme",
        groups=frozenset({group}),
        clearance=Sensitivity.RESTRICTED,
        operations=frozenset({Operation.READ, Operation.MANAGE_KNOWLEDGE}),
        purposes=frozenset({Purpose.AUDIT}),
    )


def _private_candidate() -> DocumentCandidate:
    access = Access(
        tenant="acme",
        groups=frozenset({"private"}),
        sensitivity=Sensitivity.RESTRICTED,
        purposes=frozenset({Purpose.AUDIT}),
    )
    return candidate(document_id="acme.private-managed").model_copy(update={"access": access})


def test_state_filters_bootstrap_and_managed_metadata_by_actor_access(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "visibility.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    private = _steward("private")
    _ = service.apply(
        private,
        upsert_batch(now + timedelta(days=30), document=_private_candidate()),
        now,
    )

    # When
    procurement_ids = {
        item.document_id for item in service.state(_steward("procurement")).documents
    }
    private_ids = {item.document_id for item in service.state(private).documents}
    restricted_ids = {
        item.document_id for item in service.state(_steward("private-board")).documents
    }

    # Then
    assert "sop-1" in procurement_ids
    assert "restricted-doc" not in procurement_ids
    assert "acme.private-managed" not in procurement_ids
    assert "acme.private-managed" in private_ids
    assert "restricted-doc" in restricted_ids


def test_tombstone_keeps_acl_snapshot_for_authorized_metadata_visibility(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "tombstone-visibility.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    private = _steward("private")
    _ = service.apply(
        private,
        upsert_batch(now + timedelta(days=30), document=_private_candidate()),
        now,
    )
    tombstone = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="private-tombstone",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(TombstoneDocument(document_id="acme.private-managed"),),
    )

    # When
    _ = service.apply(private, tombstone, now)

    # Then
    assert "acme.private-managed" in {item.document_id for item in service.state(private).documents}
    assert "acme.private-managed" not in {
        item.document_id for item in service.state(_steward("procurement")).documents
    }


def test_state_source_heads_only_include_manageable_current_contracts(
    tmp_path: Path, pack: DomainPack
) -> None:
    # Given
    base = registry().contracts[0]
    private_access = base.access.model_copy(update={"groups": frozenset({"private"})})
    private_contract = base.model_copy(
        update={
            "id": "private-contract",
            "collection_source": SourceReference(
                identifier="private-source", uri="source://private-policy"
            ),
            "access": private_access,
        }
    )
    contracts = DataContractRegistry(contracts=(base, private_contract))
    store = Store(tmp_path / "head-visibility.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    with store.transaction() as conn:
        _ = conn.executemany(
            """INSERT INTO knowledge_source_state
            (tenant, source_identifier, revision, state_hash) VALUES (?, ?, ?, ?)""",
            (("acme", "source-a", 1, "1" * 64), ("acme", "private-source", 2, "2" * 64)),
        )

    # When
    sources = {item.source_identifier for item in service.state(_steward("procurement")).sources}

    # Then
    assert "source-a" in sources
    assert "private-source" not in sources
