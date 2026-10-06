from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import Access, AXError, Operation, Principal, Purpose, Sensitivity
from ax_starter.data_contracts import DataContractRegistry, DocumentCandidate, SourceReference
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import KnowledgeMutationBatch, TombstoneDocument
from ax_starter.knowledge_store import document_record, source_head, tenant_head
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import content_hash
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, registry, upsert_batch


def _owner() -> Principal:
    return Principal(
        subject="private-owner",
        tenant="acme",
        groups=frozenset({"private"}),
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
    return candidate().model_copy(update={"access": access})


def _tombstone(*, source_revision: int) -> KnowledgeMutationBatch:
    return KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="drift-tombstone",
        expected_tenant_revision=1,
        expected_source_revision=source_revision,
        mutations=(TombstoneDocument(document_id="acme.managed-1"),),
    )


def test_tombstone_rebinds_same_owner_document_after_contract_version_drift(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    active = [initial]
    store = Store(tmp_path / "tombstone-drift.db", pack, contract_resolver=lambda: active[0])
    owner = _owner()
    _ = KnowledgeService(store, pack, initial).apply(
        owner,
        upsert_batch(now + timedelta(days=30), document=_private_candidate()),
        now,
    )
    upgraded_contract = initial.contracts[0].model_copy(update={"version": "2"})
    upgraded = DataContractRegistry(contracts=(upgraded_contract,))
    active[0] = upgraded

    # When
    receipt = KnowledgeService(store, pack, upgraded).apply(
        owner, _tombstone(source_revision=1), now
    )

    # Then
    assert receipt.documents[0].contract_version == "2"
    with store.transaction() as conn:
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.document is None
        assert stored.meta.contract_version == "2"
        assert stored.meta.contract_sha256 == content_hash(upgraded_contract.model_dump_json())
        assert stored.access_snapshot == _private_candidate().access


def test_tombstone_source_drift_fails_atomically(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    active = [initial]
    store = Store(tmp_path / "tombstone-source-drift.db", pack, contract_resolver=lambda: active[0])
    owner = _owner()
    _ = KnowledgeService(store, pack, initial).apply(
        owner,
        upsert_batch(now + timedelta(days=30), document=_private_candidate()),
        now,
    )
    changed = initial.contracts[0].model_copy(
        update={
            "version": "2",
            "collection_source": SourceReference(identifier="source-b", uri="source://replacement"),
        }
    )
    replacement = DataContractRegistry(contracts=(changed,))
    active[0] = replacement

    # When / Then
    with pytest.raises(AXError, match="document_not_found") as raised:
        _ = KnowledgeService(store, pack, replacement).apply(
            owner, _tombstone(source_revision=0), now
        )
    assert raised.value.status == 404
    with store.transaction() as conn:
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.document is not None
        assert stored.meta.contract_version == "1"
        assert conn.execute(
            """SELECT COUNT(*) FROM knowledge_source_state
            WHERE source_identifier = 'source-b'"""
        ).fetchone() == (0,)
        assert store.audit_check(conn, "acme").event_count == 1


def test_removed_contract_blocks_tombstone_until_same_owner_is_registered(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    active = [initial]
    store = Store(
        tmp_path / "tombstone-contract-removal.db",
        pack,
        contract_resolver=lambda: active[0],
    )
    owner = _owner()
    _ = KnowledgeService(store, pack, initial).apply(
        owner,
        upsert_batch(now + timedelta(days=30), document=_private_candidate()),
        now,
    )
    unrelated = initial.contracts[0].model_copy(update={"id": "other-contract"})
    active[0] = DataContractRegistry(contracts=(unrelated,))

    # When / Then: a removed live contract cannot authorize cleanup.
    with pytest.raises(AXError, match="data_contract_changed") as raised:
        _ = KnowledgeService(store, pack, initial).apply(owner, _tombstone(source_revision=1), now)
    assert raised.value.status == 409
    with store.transaction() as conn:
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.document is not None
        assert stored.meta.contract_version == "1"
        assert tenant_head(conn, "acme").revision == 1
        assert source_head(conn, "acme", "source-a").revision == 1
        assert store.audit_check(conn, "acme").event_count == 1

    # A controlled re-registration of the same owner permits drift cleanup.
    restored_contract = initial.contracts[0].model_copy(update={"version": "2"})
    restored = DataContractRegistry(contracts=(restored_contract,))
    active[0] = restored
    receipt = KnowledgeService(store, pack, restored).apply(
        owner, _tombstone(source_revision=1), now
    )
    assert receipt.documents[0].contract_version == "2"
    with store.transaction() as conn:
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.document is None
        assert tenant_head(conn, "acme").revision == 2
        assert source_head(conn, "acme", "source-a").revision == 2
        assert store.audit_check(conn, "acme").event_count == 2
