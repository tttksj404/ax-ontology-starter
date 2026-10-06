from datetime import datetime
from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI, Request

from ax_starter.api import create_app
from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.generation import OllamaResponse, QuotedEvidence, Synthesis, WireMessage, generate
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig, ProviderMode
from ax_starter.retrieval import Answer, Query, retrieve
from tests.live_server import live_server
from tests.test_api import headers, registry


def test_local_llm_wire_when_model_server_uses_ollama_contract(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given: a real HTTP server implementing the wire protocol, without a model.
    captured: list[bytes] = []
    mock_server = FastAPI()
    synthesis = Synthesis(
        draft="근거 검토 초안",
        quotes=(QuotedEvidence(document_id="sop-1", quote=pack.documents[0].text),),
    )

    @mock_server.post("/api/chat")
    async def model(request: Request) -> OllamaResponse:
        captured.append(await request.body())
        return OllamaResponse(message=WireMessage(content=synthesis.model_dump_json()))

    query = Query(question="검토 절차", generate=True)
    answer = retrieve(pack, principals[0], query, now)
    with live_server(mock_server) as endpoint:
        config = ProviderConfig(
            mode=ProviderMode.LOCAL, endpoint=endpoint, model="synthetic-wire-server"
        )
        # When
        result = generate(config, query, answer)
    # Then
    assert result.mode == "model_draft"
    assert result.requires_review
    assert len(captured) == 1
    assert b"BETA_SENTINEL" not in captured[0]
    assert b"RESTRICTED_SENTINEL" not in captured[0]


@pytest.mark.parametrize("mode", [ProviderMode.PRIVATE, ProviderMode.CLOUD])
def test_gateway_wire_when_egress_is_approved(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
    mode: ProviderMode,
) -> None:
    # Given: an HTTP-level fake transport; no actual cloud service.
    received: list[httpx2.Request] = []
    synthesis = Synthesis(
        draft="근거 검토 초안",
        quotes=(QuotedEvidence(document_id="sop-1", quote=pack.documents[0].text),),
    )

    def backend(request: httpx2.Request) -> httpx2.Response:
        received.append(request)
        return httpx2.Response(
            200, json={"choices": [{"message": {"content": synthesis.model_dump_json()}}]}
        )

    def client_factory() -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(backend), follow_redirects=False)

    monkeypatch.setattr("ax_starter.generation.provider_client", client_factory)
    monkeypatch.setenv("AX_LLM_API_KEY", "synthetic-gateway-test-credential")
    config = ProviderConfig(
        mode=mode,
        endpoint="https://gateway.example/v1",
        model="approved-deployment",
        approved_hosts=("gateway.example",),
        egress_approved=True,
        minimum_query_sensitivity=Sensitivity.INTERNAL,
    )
    query = Query(question="검토 절차", sensitivity=Sensitivity.INTERNAL, generate=True)
    answer = retrieve(pack, principals[0], query, now)
    # When
    result = generate(config, query, answer)
    # Then
    assert result.mode == "model_draft"
    assert received[0].url.path == "/v1/chat/completions"
    assert b"SENTINEL" not in received[0].content


def test_http_api_when_served_on_real_socket(
    tmp_path: Path, principals: tuple[Principal, ...], pack: DomainPack, now: datetime
) -> None:
    # Given
    app = create_app(pack, tmp_path / "state.db", registry(principals), clock=lambda: now)
    with live_server(app) as endpoint, httpx2.Client(base_url=endpoint) as client:
        # When
        response = client.post(
            "/v1/ask", json={"question": "검토 절차", "object_id": "request-1"}, headers=headers(0)
        )
    # Then
    assert response.status_code == 200
    assert tuple(
        cite.document_id for cite in Answer.model_validate_json(response.content).citations
    ) == ("sop-1",)


def test_no_network_when_restricted_evidence_targets_cloud(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    attempts: list[str] = []

    def client_factory() -> httpx2.Client:
        attempts.append("attempt")
        return httpx2.Client()

    monkeypatch.setattr("ax_starter.generation.provider_client", client_factory)
    config = ProviderConfig(
        mode=ProviderMode.CLOUD,
        endpoint="https://gateway.example/v1",
        model="approved",
        approved_hosts=("gateway.example",),
        egress_approved=True,
    )
    query = Query(question="검토", sensitivity=Sensitivity.RESTRICTED, generate=True)
    answer = retrieve(pack, principals[0], query, now)
    # When / Then
    with pytest.raises(AXError, match="provider_classification_denied"):
        _ = generate(config, query, answer)
    assert attempts == []
