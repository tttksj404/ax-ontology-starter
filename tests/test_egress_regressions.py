import gzip
import json
from datetime import datetime

import httpx2
import pytest

from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.generation import generate
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig, ProviderMode, model_context
from ax_starter.retrieval import Query, retrieve


@pytest.mark.parametrize(
    "text",
    [
        "ghp_" + "a" * 25,
        "github_pat_" + "b" * 25,
        "주민번호900101-1234567",
        "9001015123456",
        "900101-8123456",
        "api_key\n= synthetic-example-not-a-real-key",
    ],
    ids=[
        "classic-token",
        "fine-grained-token",
        "attached-korean-id",
        "plain-id",
        "foreign-id",
        "multiline-secret",
    ],
)
def test_no_network_when_sensitive_pattern_is_embedded(
    text: str,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    attempts: list[str] = []

    def forbidden_client() -> httpx2.Client:
        attempts.append("attempt")
        return httpx2.Client()

    monkeypatch.setattr("ax_starter.generation.provider_client", forbidden_client)
    config = ProviderConfig(
        mode=ProviderMode.PRIVATE,
        endpoint="https://gateway.example/v1",
        model="approved",
        approved_hosts=("gateway.example",),
        egress_approved=True,
        minimum_query_sensitivity=Sensitivity.CONFIDENTIAL,
    )
    query = Query(question="검토 " + text, generate=True)
    answer = retrieve(pack, principals[0], query, now)
    # When / Then
    with pytest.raises(AXError, match="sensitive_content_egress_denied"):
        _ = generate(config, query, answer)
    assert attempts == []


def test_metadata_when_model_context_is_minimized(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토")
    answer = retrieve(pack, principals[0], query, now)
    # When
    context = model_context(query, answer)
    # Then
    assert '"document_id"' in context
    assert '"quote"' in context
    assert '"source_uri"' not in context
    assert '"object_ids"' not in context
    assert '"title"' not in context


def test_routing_when_authorized_relationship_is_more_sensitive(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    links = tuple(
        link.model_copy(
            update={
                "access": link.access.model_copy(update={"sensitivity": Sensitivity.RESTRICTED})
            }
        )
        for link in pack.links
    )
    confidential_graph = pack.model_copy(update={"links": links})
    actor = principals[0].model_copy(update={"clearance": Sensitivity.RESTRICTED})
    query = Query(question="검토", object_id="request-1", sensitivity=Sensitivity.INTERNAL)
    answer = retrieve(confidential_graph, actor, query, now)
    config = ProviderConfig(
        mode=ProviderMode.CLOUD,
        endpoint="https://gateway.example/v1",
        model="approved",
        approved_hosts=("gateway.example",),
        egress_approved=True,
        minimum_query_sensitivity=Sensitivity.INTERNAL,
    )
    # When / Then
    assert answer.sensitivity == Sensitivity.RESTRICTED
    with pytest.raises(AXError, match="provider_classification_denied"):
        _ = generate(config, query, answer)


def test_model_when_compressed_response_is_unexpected(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    query = Query(question="검토", generate=True)
    answer = retrieve(pack, principals[0], query, now)
    config = ProviderConfig(
        mode=ProviderMode.LOCAL, endpoint="http://127.0.0.1:11434", model="local"
    )
    compressed = gzip.compress(json.dumps({"message": {"content": "ignored"}}).encode())

    def response(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=compressed, headers={"Content-Encoding": "gzip"})

    monkeypatch.setattr(
        "ax_starter.generation.provider_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(response)),
    )
    # When / Then
    with pytest.raises(AXError, match="model_compressed_response_denied"):
        _ = generate(config, query, answer)
