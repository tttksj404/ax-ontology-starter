from datetime import datetime

import pytest

from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig
from ax_starter.retrieval import Answer, Query, retrieve
from ax_starter.wiki_compiler import compile_wiki
from ax_starter.wiki_contracts import WikiCompileRequest, WikiKind


def compile_request(*, generate: bool = False, question: str = "검토") -> WikiCompileRequest:
    return WikiCompileRequest(
        request_key="wiki-test-1",
        page_id="acme.review-policy",
        title="검토 절차",
        kind=WikiKind.PROCEDURE,
        query=Query(question=question, generate=generate),
    )


def test_offline_compiler_preserves_raw_citations_without_model(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given: offline would reject any generation call.
    request = compile_request()
    raw = retrieve(pack, principals[0], request.query, now)
    # When
    result = compile_wiki(ProviderConfig(), request, raw)
    # Then
    assert result.compiler_mode == "offline_extractive"
    assert result.generation_route is None
    assert result.sensitivity == Sensitivity.RESTRICTED
    assert {cite.document_id for cite in result.citations} == {
        cite.document_id for cite in raw.citations
    }
    assert all(
        cite.quote
        in next(source.quote for source in raw.citations if source.document_id == cite.document_id)
        for cite in result.citations
    )


def test_compiler_refuses_empty_evidence(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    request = compile_request(question="neverfound_zzzz")
    raw = retrieve(pack, principals[0], request.query, now)
    # When / Then
    with pytest.raises(AXError, match="wiki_evidence_required"):
        _ = compile_wiki(ProviderConfig(), request, raw)


def test_model_request_cannot_silently_fall_back_to_offline(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    request = compile_request(generate=True)
    raw = retrieve(pack, principals[0], request.query, now)
    # When / Then
    with pytest.raises(AXError, match="generation_disabled"):
        _ = compile_wiki(ProviderConfig(), request, raw)


def test_extractive_compilation_bounds_large_source_context(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    request = compile_request()
    base = retrieve(pack, principals[0], request.query, now)
    citations = tuple(
        base.citations[0].model_copy(
            update={"document_id": f"acme.source-{index}", "quote": "한" * 16_000}
        )
        for index in range(10)
    )
    raw = base.model_copy(update={"citations": citations})
    # When
    result = compile_wiki(ProviderConfig(), request, raw)
    # Then
    assert len(result.body) <= 8_000
    assert len(result.citations) == 10
    assert all(len(cite.quote) <= 640 for cite in result.citations)


def test_server_floor_survives_lowered_query_and_evidence_labels(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    request = compile_request()
    request = request.model_copy(
        update={"query": request.query.model_copy(update={"sensitivity": Sensitivity.PUBLIC})}
    )
    base = retrieve(pack, principals[0], request.query, now)
    raw: Answer = base.model_copy(
        update={
            "sensitivity": Sensitivity.PUBLIC,
            "citations": tuple(
                cite.model_copy(update={"sensitivity": Sensitivity.PUBLIC})
                for cite in base.citations
            ),
        }
    )
    # When
    result = compile_wiki(ProviderConfig(), request, raw)
    # Then
    assert result.sensitivity == Sensitivity.RESTRICTED
