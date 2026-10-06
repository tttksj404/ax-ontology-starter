from datetime import datetime

import httpx2
import pytest
from fastapi import FastAPI, Request

from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.generation import OllamaResponse, QuotedEvidence, Synthesis, WireMessage
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig, ProviderMode
from ax_starter.retrieval import Query, content_hash, retrieve
from ax_starter.wiki_compiler import compile_wiki
from ax_starter.wiki_contracts import WikiCompileRequest, WikiKind
from tests.live_server import live_server


def model_request() -> WikiCompileRequest:
    return WikiCompileRequest(
        request_key="wiki-wire",
        page_id="acme.wire-policy",
        title="검토 지식",
        kind=WikiKind.PROCEDURE,
        query=Query(question="검토 절차", sensitivity=Sensitivity.INTERNAL, generate=True),
    )


def synthesis(pack: DomainPack) -> Synthesis:
    return Synthesis(
        draft="원문에 따른 위키 검토 초안",
        quotes=(QuotedEvidence(document_id="sop-1", quote=pack.documents[0].text),),
    )


def test_wiki_compiler_real_loopback_model_protocol(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given: a real local HTTP protocol server; this is not model quality evidence.
    captured: list[bytes] = []
    server = FastAPI()

    @server.post("/api/chat")
    async def model(request: Request) -> OllamaResponse:
        captured.append(await request.body())
        return OllamaResponse(message=WireMessage(content=synthesis(pack).model_dump_json()))

    request = model_request()
    answer = retrieve(pack, principals[0], request.query, now)
    with live_server(server) as endpoint:
        provider = ProviderConfig(mode=ProviderMode.LOCAL, endpoint=endpoint, model="wire-fake")
        # When
        compiled = compile_wiki(provider, request, answer)
    # Then
    assert compiled.compiler_mode == "model_draft"
    assert compiled.body == synthesis(pack).draft
    assert compiled.sensitivity is Sensitivity.RESTRICTED
    assert compiled.generation_route is not None
    assert compiled.generation_route.mode == "local"
    assert compiled.generation_route.endpoint_host == "127.0.0.1"
    assert compiled.generation_route.model == "wire-fake"
    assert compiled.generation_route.provider_settings_sha256 == content_hash(
        provider.model_dump_json()
    )
    assert len(captured) == 1
    assert b"SENTINEL" not in captured[0]


@pytest.mark.parametrize("mode", [ProviderMode.PRIVATE, ProviderMode.CLOUD])
def test_wiki_compiler_gateway_wire_after_approved_egress(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
    mode: ProviderMode,
) -> None:
    # Given: an HTTP transport fake, not a live cloud model.
    captured: list[httpx2.Request] = []

    def backend(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(
            200, json={"choices": [{"message": {"content": synthesis(pack).model_dump_json()}}]}
        )

    def client() -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(backend), follow_redirects=False)

    monkeypatch.setattr("ax_starter.generation.provider_client", client)
    monkeypatch.setenv("AX_LLM_API_KEY", "synthetic-wiki-wire-credential")
    config = ProviderConfig(
        mode=mode,
        endpoint="https://gateway.example/v1",
        model="wire-fake",
        approved_hosts=("gateway.example",),
        egress_approved=True,
        minimum_query_sensitivity=Sensitivity.INTERNAL,
    )
    request = model_request()
    # When
    compiled = compile_wiki(config, request, retrieve(pack, principals[0], request.query, now))
    # Then
    assert compiled.compiler_mode == "model_draft"
    assert compiled.generation_route is not None
    assert compiled.generation_route.mode == mode.value
    assert compiled.generation_route.endpoint_host == "gateway.example"
    assert compiled.generation_route.model == "wire-fake"
    assert compiled.generation_route.provider_settings_sha256 == content_hash(
        config.model_dump_json()
    )
    assert len(captured) == 1
    assert captured[0].url.path == "/v1/chat/completions"
    assert b"SENTINEL" not in captured[0].content


@pytest.mark.parametrize(
    "case",
    [
        ("검토 절차", Sensitivity.RESTRICTED, "provider_classification_denied"),
        ("검토 person@example.com", Sensitivity.INTERNAL, "sensitive_content_egress_denied"),
    ],
)
def test_wiki_compiler_denies_egress_before_network(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[str, Sensitivity, str],
) -> None:
    # Given
    question, floor, expected = case
    attempted: list[str] = []

    def client() -> httpx2.Client:
        attempted.append("network")
        return httpx2.Client()

    monkeypatch.setattr("ax_starter.generation.provider_client", client)
    request = model_request().model_copy(
        update={"query": model_request().query.model_copy(update={"question": question})}
    )
    config = ProviderConfig(
        mode=ProviderMode.CLOUD,
        endpoint="https://gateway.example/v1",
        model="wire-fake",
        approved_hosts=("gateway.example",),
        egress_approved=True,
        minimum_query_sensitivity=floor,
    )
    # When / Then
    with pytest.raises(AXError, match=expected):
        _ = compile_wiki(config, request, retrieve(pack, principals[0], request.query, now))
    assert attempted == []
