from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import AXError
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import KnowledgeMutationBatch, RetireDocument
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def test_retired_document_can_be_reactivated_only_with_a_new_source_version(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "lifecycle.db", pack, contract_resolver=lambda: contracts)
    current = KnowledgeService(store, pack, contracts)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    _ = current.apply(
        actor,
        KnowledgeMutationBatch(
            contract_id="knowledge-contract",
            request_key="retire",
            expected_tenant_revision=1,
            expected_source_revision=1,
            mutations=(RetireDocument(document_id="acme.managed-1"),),
        ),
        now,
    )
    replacement = candidate(source_version="2", content=b"replacement content")

    # When
    receipt = current.apply(
        actor,
        upsert_batch(
            now + timedelta(days=30),
            request_key="reactivate",
            tenant_revision=2,
            source_revision=2,
            document=replacement,
        ),
        now,
    )

    # Then
    assert receipt.documents[0].source_version == "2"
    assert receipt.documents[0].revision == 3
    with current.store.transaction() as conn:
        documents = current.store.current_pack(conn, pack).documents
        document = next(item for item in documents if item.id == "acme.managed-1")
        assert document.text == "replacement content"


def test_source_version_cannot_be_reused_after_an_intervening_version(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "version-history.db", pack, contract_resolver=lambda: contracts)
    current = KnowledgeService(store, pack, contracts)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    _ = current.apply(
        actor,
        upsert_batch(
            now + timedelta(days=30),
            request_key="version-2",
            tenant_revision=1,
            source_revision=1,
            document=candidate(source_version="2", content=b"version two"),
        ),
        now,
    )

    # When / Then
    with pytest.raises(AXError, match="source_version_reuse"):
        _ = current.apply(
            actor,
            upsert_batch(
                now + timedelta(days=30),
                request_key="reuse-version-1",
                tenant_revision=2,
                source_revision=2,
                document=candidate(source_version="1", content=b"rollback"),
            ),
            now,
        )
    assert current.state(actor).tenant_revision == 2
    with current.store.transaction() as conn:
        document = next(
            item
            for item in current.store.current_pack(conn, pack).documents
            if item.id == "acme.managed-1"
        )
        assert document.source_version == "2"
        assert current.store.audit_check(conn, "acme").event_count == 2
