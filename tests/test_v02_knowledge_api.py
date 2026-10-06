from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ax_starter.api import create_app
from ax_starter.auth import IdentityRegistry
from ax_starter.common import Principal
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.demo import DemoDomain
from ax_starter.intake_demo import demo_intake
from ax_starter.knowledge_contracts import (
    DocumentLifecycle,
    KnowledgeMutationBatch,
    KnowledgeMutationReceipt,
    KnowledgeState,
    RetireDocument,
    SourceSnapshotInput,
    TombstoneDocument,
)
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig
from ax_starter.retrieval import Answer, Query
from ax_starter.v02_examples import demo_steward, v02_artifacts
from tests.test_api import headers, registry


@dataclass(frozen=True, slots=True)
class ManagedAPI:
    client: TestClient
    database: Path
    pack: DomainPack
    identities: IdentityRegistry
    contracts: DataContractRegistry
    snapshot: SourceSnapshotInput
    now: datetime


@pytest.fixture
def managed_api(
    tmp_path: Path,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
) -> ManagedAPI:
    artifacts = dict(v02_artifacts(pack, demo_intake(DemoDomain.PROCUREMENT), now))
    contracts = DataContractRegistry.model_validate_json(
        artifacts["data-contracts.json"].model_dump_json()
    )
    snapshot = SourceSnapshotInput.model_validate_json(
        artifacts["source-snapshot.json"].model_dump_json()
    )
    identities = registry((*principals, demo_steward(principals[0])))
    database = tmp_path / "state.db"
    client = TestClient(
        create_app(pack, database, identities, data_contracts=contracts, clock=lambda: now),
        base_url="http://127.0.0.1",
    )
    return ManagedAPI(client, database, pack, identities, contracts, snapshot, now)


def import_demo(api: ManagedAPI) -> KnowledgeMutationReceipt:
    response = api.client.post(
        "/v1/knowledge/import", content=api.snapshot.model_dump_json(), headers=headers(4)
    )
    assert response.status_code == 200
    return KnowledgeMutationReceipt.model_validate_json(response.content)


def retire_batch(api: ManagedAPI) -> KnowledgeMutationBatch:
    return KnowledgeMutationBatch(
        contract_id=api.snapshot.contract_id,
        request_key="retire-demo",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(RetireDocument(document_id="acme.pilot-policy-1"),),
    )


def test_import_replay_retire_tombstone_and_restart_are_consistent(managed_api: ManagedAPI) -> None:
    # Given / When
    api = managed_api
    imported = import_demo(api)
    replayed = import_demo(api)
    # Then
    assert imported == replayed
    state = KnowledgeState.model_validate_json(
        api.client.get("/v1/knowledge/state", headers=headers(4)).content
    )
    assert state.tenant_revision == 1
    assert any(
        source.source_identifier == "demo-source" and source.revision == 1
        for source in state.sources
    )
    # When
    retired = api.client.post(
        "/v1/knowledge/apply", content=retire_batch(api).model_dump_json(), headers=headers(4)
    )
    assert retired.status_code == 200
    deletion = KnowledgeMutationBatch(
        contract_id=api.snapshot.contract_id,
        request_key="delete-demo",
        expected_tenant_revision=2,
        expected_source_revision=2,
        mutations=(TombstoneDocument(document_id="acme.pilot-policy-1"),),
    )
    removed = api.client.post(
        "/v1/knowledge/apply", content=deletion.model_dump_json(), headers=headers(4)
    )
    assert removed.status_code == 200
    restarted = TestClient(
        create_app(
            api.pack,
            api.database,
            api.identities,
            data_contracts=api.contracts,
            clock=lambda: api.now,
        ),
        base_url="http://127.0.0.1",
    )
    # Then
    current = KnowledgeState.model_validate_json(
        restarted.get("/v1/knowledge/state", headers=headers(4)).content
    )
    assert current.tenant_revision == 3
    assert (
        next(
            document
            for document in current.documents
            if document.document_id == "acme.pilot-policy-1"
        ).lifecycle
        == DocumentLifecycle.TOMBSTONE
    )
    answer = Answer.model_validate_json(
        restarted.post(
            "/v1/ask",
            content=Query(question="합성 파일 입력", object_id="request-1").model_dump_json(),
            headers=headers(0),
        ).content
    )
    assert all(citation.document_id != "acme.pilot-policy-1" for citation in answer.citations)


def test_import_denies_reader_without_disclosing_contract(managed_api: ManagedAPI) -> None:
    # Given / When
    response = managed_api.client.post(
        "/v1/knowledge/import", content=managed_api.snapshot.model_dump_json(), headers=headers(0)
    )
    # Then
    assert response.status_code == 403
    assert response.json() == {"error": "access_denied"}


def test_source_uri_auth_material_is_rejected_without_echo(managed_api: ManagedAPI) -> None:
    # Given
    marker = "synthetic-source-secret-marker"
    body = managed_api.snapshot.model_dump_json().replace(
        "synthetic://pilot-collection", "https://source.example.com?token=" + marker
    )
    # When
    response = managed_api.client.post("/v1/knowledge/import", content=body, headers=headers(4))
    # Then
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert marker not in response.text


def test_retirement_during_provider_call_blocks_generated_return(
    managed_api: ManagedAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    api = managed_api
    _ = import_demo(api)

    def provider_handoff(_config: ProviderConfig, _query: Query, answer: Answer) -> Answer:
        assert any(citation.document_id == "acme.pilot-policy-1" for citation in answer.citations)
        response = api.client.post(
            "/v1/knowledge/apply", content=retire_batch(api).model_dump_json(), headers=headers(4)
        )
        assert response.status_code == 200
        return answer.model_copy(update={"mode": "model_draft", "requires_review": True})

    monkeypatch.setattr("ax_starter.api.generate", provider_handoff)
    query = Query(question="합성 파일 입력", object_id="request-1", generate=True)
    # When
    response = api.client.post(
        "/v1/ask",
        content=query.model_dump_json(),
        headers=headers(0),
    )
    # Then
    assert response.status_code == 409
    assert response.json() == {"error": "knowledge_snapshot_changed"}


def test_retirement_before_provider_handoff_prevents_call(
    managed_api: ManagedAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    api = managed_api
    _ = import_demo(api)
    clock_calls = 0
    provider_calls = 0

    def clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 3:
            response = api.client.post(
                "/v1/knowledge/apply",
                content=retire_batch(api).model_dump_json(),
                headers=headers(4),
            )
            assert response.status_code == 200
        return api.now

    def provider_handoff(_config: ProviderConfig, _query: Query, answer: Answer) -> Answer:
        nonlocal provider_calls
        provider_calls += 1
        return answer

    monkeypatch.setattr("ax_starter.api.generate", provider_handoff)
    guarded = TestClient(
        create_app(
            api.pack, api.database, api.identities, data_contracts=api.contracts, clock=clock
        ),
        base_url="http://127.0.0.1",
    )
    query = Query(question="합성 파일 입력", object_id="request-1", generate=True)
    # When
    response = guarded.post(
        "/v1/ask",
        content=query.model_dump_json(),
        headers=headers(0),
    )
    # Then
    assert response.status_code == 409
    assert provider_calls == 0
