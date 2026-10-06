from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ax_starter.api import create_app
from ax_starter.auth import IdentityRegistry
from ax_starter.common import Principal
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig
from ax_starter.retrieval import Answer, Query
from tests.test_api import headers, registry


@pytest.fixture
def v02_client(tmp_path: Path, pack: DomainPack, principals: tuple[Principal, ...]) -> TestClient:
    return TestClient(
        create_app(pack, tmp_path / "state.db", registry(principals)),
        base_url="http://127.0.0.1",
    )


def test_knowledge_state_requires_authentication(v02_client: TestClient) -> None:
    # Given / When
    response = v02_client.get("/v1/knowledge/state")
    # Then
    assert response.status_code == 401


def test_knowledge_state_denies_read_only_user(v02_client: TestClient) -> None:
    # Given / When
    response = v02_client.get("/v1/knowledge/state", headers=headers(0))
    # Then
    assert response.status_code == 403


def test_credential_revoked_during_generation_blocks_return(
    tmp_path: Path,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    identities = registry(principals)
    identity_path = tmp_path / "identities.json"
    _ = identity_path.write_text(identities.model_dump_json(), encoding="utf-8")
    client = TestClient(
        create_app(
            pack,
            tmp_path / "state.db",
            identities,
            identity_path=identity_path,
            clock=lambda: now,
        ),
        base_url="http://127.0.0.1",
    )

    def provider_handoff(_config: ProviderConfig, _query: Query, answer: Answer) -> Answer:
        remaining = IdentityRegistry(bindings=identities.bindings[1:])
        _ = identity_path.write_text(remaining.model_dump_json(), encoding="utf-8")
        return answer.model_copy(update={"mode": "model_draft", "requires_review": True})

    monkeypatch.setattr("ax_starter.api.generate", provider_handoff)
    # When
    response = client.post(
        "/v1/ask",
        content=Query(question="검토 절차", object_id="request-1", generate=True).model_dump_json(),
        headers=headers(0),
    )
    # Then
    assert response.status_code == 401
    assert response.json() == {"error": "authentication_required"}
