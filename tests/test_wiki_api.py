from datetime import datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from ax_starter.api import create_app
from ax_starter.common import Operation, Principal, Sensitivity
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query
from ax_starter.wiki_contracts import (
    WikiAnswer,
    WikiCompileRequest,
    WikiDraft,
    WikiExport,
    WikiKind,
    WikiPage,
)
from tests.test_api import headers, registry


def wiki_principals(principals: tuple[Principal, ...]) -> tuple[Principal, ...]:
    return tuple(
        principal.model_copy(
            update={
                "clearance": Sensitivity.RESTRICTED,
                "operations": principal.operations | {Operation.MANAGE_KNOWLEDGE}
                if index == 0
                else principal.operations,
            }
        )
        for index, principal in enumerate(principals)
    )


def wiki_request() -> WikiCompileRequest:
    return WikiCompileRequest(
        request_key="http-wiki-1",
        page_id="acme.review-policy",
        title="검토 절차",
        kind=WikiKind.PROCEDURE,
        query=Query(question="검토"),
    )


@pytest.fixture
def wiki_client(
    tmp_path: Path, pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> TestClient:
    actors = wiki_principals(principals)
    return TestClient(
        create_app(pack, tmp_path / "wiki-api.db", registry(actors), clock=lambda: now),
        base_url="http://127.0.0.1",
    )


def test_http_draft_review_publish_query_and_raw_citation_boundary(wiki_client: TestClient) -> None:
    # Given
    request = wiki_request()
    created = wiki_client.post(
        "/v1/wiki/compile", content=request.model_dump_json(), headers=headers(0)
    )
    assert created.status_code == 200
    draft = WikiDraft.model_validate_json(created.content)
    # When: same request replays; a different real human publishes the reviewed payload.
    replay = wiki_client.post(
        "/v1/wiki/compile", content=request.model_dump_json(), headers=headers(0)
    )
    assert WikiDraft.model_validate_json(replay.content).id == draft.id
    assert wiki_client.get("/v1/wiki/index", headers=headers(0)).json() == []
    reviewed = wiki_client.get(f"/v1/wiki/drafts/{draft.id}", headers=headers(1))
    assert reviewed.status_code == 200
    review_packet = WikiDraft.model_validate_json(reviewed.content)
    assert review_packet.payload.input_citations == draft.payload.input_citations
    published = wiki_client.post(
        f"/v1/wiki/drafts/{draft.id}/publish",
        json={"reviewed_payload_hash": review_packet.payload_hash},
        headers=headers(1),
    )
    assert published.status_code == 200
    page = WikiPage.model_validate_json(published.content)
    queried = wiki_client.post(
        "/v1/wiki/query", content=request.query.model_dump_json(), headers=headers(0)
    )
    # Then
    assert page.revision == 1
    result = WikiAnswer.model_validate_json(queried.content)
    assert result.pages[0].page_id == request.page_id
    assert result.answer.requires_review
    assert request.page_id not in {cite.document_id for cite in result.answer.citations}
    assert {cite.document_id for cite in result.answer.citations} <= {
        cite.document_id for cite in draft.payload.citations
    }
    exported = wiki_client.get(f"/v1/wiki/pages/{request.page_id}/export", headers=headers(0))
    assert exported.status_code == 200
    snapshot = WikiExport.model_validate_json(exported.content)
    assert snapshot.manifest.non_authoritative is True
    assert snapshot.text.startswith("AX_DERIVED_WIKI_V1")


def test_http_requires_auth_and_real_independent_review(wiki_client: TestClient) -> None:
    # Given
    request = wiki_request()
    # When / Then
    unauthenticated = wiki_client.post("/v1/wiki/compile", content=request.model_dump_json())
    assert unauthenticated.status_code == 401
    created = wiki_client.post(
        "/v1/wiki/compile", content=request.model_dump_json(), headers=headers(0)
    )
    draft = WikiDraft.model_validate_json(created.content)
    denied = wiki_client.post(
        f"/v1/wiki/drafts/{draft.id}/publish",
        json={"reviewed_payload_hash": draft.payload_hash},
        headers=headers(0),
    )
    assert denied.status_code == 403
    assert wiki_client.get("/v1/wiki/index", headers=headers(0)).json() == []


def test_http_wiki_query_does_not_silently_generate(wiki_client: TestClient) -> None:
    # Given
    query = Query(question="검토", generate=True)
    # When
    response = wiki_client.post(
        "/v1/wiki/query", content=query.model_dump_json(), headers=headers(0)
    )
    # Then
    assert response.status_code == 422
    assert response.json() == {"error": "wiki_query_generation_not_supported"}


def test_http_rejects_duplicate_links_before_draft_save(wiki_client: TestClient) -> None:
    # Given: duplicate links would violate the publish table's unique relation key.
    request = wiki_request().model_copy(update={"links": ("acme.target", "acme.target")})
    # When
    response = wiki_client.post(
        "/v1/wiki/compile", content=request.model_dump_json(), headers=headers(0)
    )
    # Then: reject the public input, without a delayed SQL constraint error.
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert wiki_client.get("/v1/wiki/index", headers=headers(0)).json() == []
