from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ax_starter.api import create_app
from ax_starter.common import AXError
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    KnowledgeMutationBatch,
    KnowledgeState,
)
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch
from tests.test_api import headers
from tests.test_api import registry as identity_registry


def _empty_groups_batch(now: datetime) -> KnowledgeMutationBatch:
    document = candidate().model_copy(
        update={"access": candidate().access.model_copy(update={"groups": frozenset()})}
    )
    return upsert_batch(now + timedelta(days=30), document=document)


def test_new_managed_document_rejects_empty_access_groups_atomically(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "empty-upsert.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)

    # When / Then
    with pytest.raises(AXError, match="data_contract_violation") as raised:
        _ = service.apply(management_actor(), _empty_groups_batch(now), now)
    assert raised.value.status == 422
    assert service.state(management_actor()).tenant_revision == 0
    with store.transaction() as conn:
        assert conn.execute(
            """SELECT COUNT(*) FROM knowledge_accepted_versions
            WHERE document_id = 'acme.managed-1'"""
        ).fetchone() == (0,)
        assert store.audit_check(conn, "acme").event_count == 0


def test_existing_managed_document_rejects_empty_acl_change_atomically(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "empty-acl.db", pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(store, pack, contracts)
    actor = management_actor()
    _ = service.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    empty = candidate().access.model_copy(update={"groups": frozenset()})
    batch = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="empty-acl",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(ChangeDocumentAccess(document_id="acme.managed-1", access=empty),),
    )

    # When / Then
    with pytest.raises(AXError, match="data_contract_violation") as raised:
        _ = service.apply(actor, batch, now)
    assert raised.value.status == 422
    assert service.state(actor).tenant_revision == 1
    with store.transaction() as conn:
        assert conn.execute(
            """SELECT COUNT(*) FROM knowledge_accepted_versions
            WHERE document_id = 'acme.managed-1'"""
        ).fetchone() == (1,)
        assert store.audit_check(conn, "acme").event_count == 1


def test_empty_group_upsert_api_returns_422_without_revision_change(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    client = TestClient(
        create_app(
            pack,
            tmp_path / "empty-api.db",
            identity_registry((management_actor(),)),
            data_contracts=registry(),
            clock=lambda: now,
        ),
        base_url="http://127.0.0.1",
    )

    # When
    response = client.post(
        "/v1/knowledge/apply",
        content=_empty_groups_batch(now).model_dump_json(),
        headers=headers(0),
    )

    # Then
    assert response.status_code == 422
    assert response.json() == {"error": "data_contract_violation"}
    state = KnowledgeState.model_validate_json(
        client.get("/v1/knowledge/state", headers=headers(0)).content
    )
    assert state.tenant_revision == 0
