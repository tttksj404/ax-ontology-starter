from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import AXError
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.knowledge import KnowledgeService
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import management_actor, registry, upsert_batch


def test_contract_change_before_transaction_blocks_stale_write_atomically(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    upgraded = DataContractRegistry(
        contracts=(initial.contracts[0].model_copy(update={"version": "2"}),)
    )
    live_registry = [initial]
    store = Store(
        tmp_path / "contract-toctou.db",
        pack,
        contract_resolver=lambda: live_registry[0],
    )
    stale_service = KnowledgeService(store, pack, initial)
    batch = upsert_batch(now + timedelta(days=30))
    live_registry[0] = upgraded

    # When / Then
    with pytest.raises(AXError, match="data_contract_changed") as raised:
        _ = stale_service.apply(management_actor(), batch, now)
    assert raised.value.status == 409
    with store.transaction() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM knowledge_documents WHERE document_id = 'acme.managed-1'"
        ).fetchone() == (0,)
        assert conn.execute("SELECT COUNT(*) FROM knowledge_batches").fetchone() == (0,)
        assert conn.execute(
            """SELECT COUNT(*) FROM knowledge_accepted_versions
            WHERE document_id = 'acme.managed-1'"""
        ).fetchone() == (0,)
        assert store.audit_check(conn, "acme").event_count == 0

    # A fresh request bound to the live contract may commit.
    receipt = KnowledgeService(store, pack, upgraded).apply(management_actor(), batch, now)
    assert receipt.documents[0].contract_version == "2"


def test_state_uses_live_registry_and_hides_stale_binding(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    live_registry = [initial]
    store = Store(
        tmp_path / "state-live-registry.db",
        pack,
        contract_resolver=lambda: live_registry[0],
    )
    service = KnowledgeService(store, pack, initial)
    actor = management_actor()
    _ = service.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    live_registry[0] = DataContractRegistry(
        contracts=(initial.contracts[0].model_copy(update={"version": "2"}),)
    )

    # When
    state = service.state(actor)

    # Then
    assert "acme.managed-1" not in {item.document_id for item in state.documents}


def test_configured_missing_registry_fails_closed_before_replay_or_write(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    initial = registry()
    live_registry: list[DataContractRegistry | None] = [initial]
    store = Store(
        tmp_path / "missing-live-registry.db",
        pack,
        contract_resolver=lambda: live_registry[0],
    )
    service = KnowledgeService(store, pack, initial)
    live_registry[0] = None

    # When / Then
    with pytest.raises(AXError, match="data_contract_registry_unavailable") as raised:
        _ = service.apply(management_actor(), upsert_batch(now + timedelta(days=30)), now)
    assert raised.value.status == 503
    with pytest.raises(AXError, match="data_contract_registry_unavailable"):
        _ = service.state(management_actor())
