from datetime import datetime, timedelta
from pathlib import Path

from ax_starter.common import Access, Operation, Principal, Purpose, Sensitivity
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


def test_v3_acl_snapshot_migration_backfills_bodies_and_hides_unknown_tombstones(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    database = tmp_path / "v3-acl.db"
    store = Store(database, pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    private = _steward("private")
    private_access = Access(
        tenant="acme",
        groups=frozenset({"private"}),
        sensitivity=Sensitivity.RESTRICTED,
        purposes=frozenset({Purpose.AUDIT}),
    )
    private_document = candidate(document_id="acme.legacy-tombstone").model_copy(
        update={"access": private_access}
    )
    _ = service.apply(
        private,
        upsert_batch(now + timedelta(days=30), document=private_document),
        now,
    )
    _ = service.apply(
        private,
        KnowledgeMutationBatch(
            contract_id="knowledge-contract",
            request_key="legacy-tombstone",
            expected_tenant_revision=1,
            expected_source_revision=1,
            mutations=(TombstoneDocument(document_id="acme.legacy-tombstone"),),
        ),
        now,
    )
    with store.transaction() as conn:
        _ = conn.execute("ALTER TABLE knowledge_documents DROP COLUMN access_json")
        _ = conn.execute("UPDATE meta SET value = '3' WHERE id = 'schema_version'")

    # When
    restarted = Store(database, pack, contract_resolver=lambda: contracts)
    current = KnowledgeService(restarted, pack, contracts)

    # Then
    with restarted.transaction() as conn:
        assert conn.execute("SELECT value FROM meta WHERE id = 'schema_version'").fetchone() == (
            "4",
        )
        assert conn.execute(
            "SELECT access_json IS NOT NULL FROM knowledge_documents WHERE document_id = 'sop-1'"
        ).fetchone() == (1,)
        assert conn.execute(
            """SELECT access_json FROM knowledge_documents
            WHERE document_id = 'acme.legacy-tombstone'"""
        ).fetchone() == (None,)
    assert "acme.legacy-tombstone" not in {
        item.document_id for item in current.state(private).documents
    }
    assert "restricted-doc" in {
        item.document_id for item in current.state(_steward("private-board")).documents
    }
