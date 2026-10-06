from datetime import datetime

import pytest
from pydantic import ValidationError

from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.generation import verify_synthesis
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig, ProviderMode, enforce_route
from ax_starter.retrieval import Query, retrieve


def test_local_route_when_classification_is_restricted(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토", sensitivity=Sensitivity.RESTRICTED)
    answer = retrieve(pack, principals[0], query, now)
    config = ProviderConfig(
        mode=ProviderMode.LOCAL, endpoint="http://127.0.0.1:11434", model="approved-model"
    )
    # When / Then
    enforce_route(config, query, answer)


def test_cloud_denied_when_caller_lowers_question_label(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토", sensitivity=Sensitivity.PUBLIC)
    answer = retrieve(pack, principals[0], query, now)
    config = ProviderConfig(
        mode=ProviderMode.CLOUD,
        endpoint="https://gateway.example/v1",
        model="approved-model",
        approved_hosts=("gateway.example",),
        egress_approved=True,
    )
    # When / Then
    with pytest.raises(AXError, match="provider_classification_denied"):
        enforce_route(config, query, answer)


def test_pii_denied_when_gateway_is_approved(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토 개인정보 900101-1234567", sensitivity=Sensitivity.INTERNAL)
    answer = retrieve(pack, principals[0], query, now)
    config = ProviderConfig(
        mode=ProviderMode.CLOUD,
        endpoint="https://gateway.example/v1",
        model="approved-model",
        approved_hosts=("gateway.example",),
        egress_approved=True,
        minimum_query_sensitivity=Sensitivity.INTERNAL,
    )
    # When / Then
    with pytest.raises(AXError, match="sensitive_content_egress_denied"):
        enforce_route(config, query, answer)


@pytest.mark.parametrize(
    "endpoint",
    ["http://localhost:11434", "http://10.0.0.5:11434", "https://127.0.0.1@attacker.example"],
)
def test_local_endpoint_denied_when_not_literal_loopback(endpoint: str) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        _ = ProviderConfig(mode=ProviderMode.LOCAL, endpoint=endpoint, model="approved")


def test_false_citation_denied_when_model_fabricates_quote(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    answer = retrieve(pack, principals[0], Query(question="검토"), now)
    raw = '{"draft":"초안","quotes":[{"document_id":"sop-1","quote":"지급을 완료했습니다"}]}'
    # When / Then
    with pytest.raises(AXError, match="model_citation_invalid"):
        _ = verify_synthesis(answer, raw)


def test_model_tools_denied_when_output_contains_tool_call(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    answer = retrieve(pack, principals[0], Query(question="검토"), now)
    raw = (
        '{"draft":"초안","quotes":[{"document_id":"sop-1","quote":"구매요청"}],'
        '"tool_calls":["execute"]}'
    )
    # When / Then
    with pytest.raises(AXError, match="model_output_schema_invalid"):
        _ = verify_synthesis(answer, raw)
