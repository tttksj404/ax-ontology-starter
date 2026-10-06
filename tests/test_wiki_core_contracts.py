from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ax_starter.common import Purpose, Sensitivity
from ax_starter.retrieval import Citation, Query
from ax_starter.wiki_contracts import WikiCompilation, WikiCompileRequest, WikiKind


def _query() -> Query:
    return Query(question="환불 절차", purpose=Purpose.OPERATIONS)


def _citation() -> Citation:
    return Citation(
        document_id="acme.source-1",
        title="절차",
        source_uri="local://source-1",
        source_version="v1",
        content_sha256="a" * 64,
        access_sha256="b" * 64,
        object_ids=("acme-procedure",),
        quote="승인 후 처리합니다.",
        sensitivity=Sensitivity.CONFIDENTIAL,
    )


def test_compile_request_rejects_nested_page_suffix() -> None:
    # Given: a syntactically valid Identifier with an ambiguous nested suffix.
    values = {
        "request_key": "wiki-request-1",
        "page_id": "acme.refund.extra",
        "title": "환불 절차",
        "kind": WikiKind.PROCEDURE,
        "query": _query(),
    }

    # When / Then: the tenant-aware service must still reject this before lookup;
    # the boundary contract keeps the identifier parseable for that check.
    request = WikiCompileRequest.model_validate(values)
    assert request.page_id == "acme.refund.extra"


def test_compilation_requires_a_bounded_body_and_citation() -> None:
    # Given: an empty model draft.
    values = {
        "body": "",
        "citations": (_citation(),),
        "compiler_mode": "model_draft",
        "sensitivity": Sensitivity.CONFIDENTIAL,
    }

    # When / Then: boundary validation rejects content that cannot become a page.
    with pytest.raises(ValidationError):
        _ = WikiCompilation.model_validate(values)


def test_model_compilation_requires_a_bound_generation_route() -> None:
    # Given: a model draft records the exact configured route reviewed with its payload.
    values = {
        "body": "검토 초안",
        "citations": (_citation(),),
        "compiler_mode": "model_draft",
        "sensitivity": Sensitivity.CONFIDENTIAL,
        "generation_route": {
            "mode": "private_gateway",
            "endpoint_host": "gateway.example",
            "model": "approved-model",
            "provider_settings_sha256": "c" * 64,
        },
    }

    # When / Then: the route is part of the frozen compilation contract.
    compilation = WikiCompilation.model_validate(values)
    assert compilation.generation_route is not None
    assert compilation.generation_route.endpoint_host == "gateway.example"


def test_model_compilation_without_route_fails_closed() -> None:
    # Given: a callback claims model generation without provider provenance.
    values = {
        "body": "검토 초안",
        "citations": (_citation(),),
        "compiler_mode": "model_draft",
        "sensitivity": Sensitivity.CONFIDENTIAL,
    }

    # When / Then: an unbound model route cannot enter the review flow.
    with pytest.raises(ValidationError):
        _ = WikiCompilation.model_validate(values)


def test_compile_request_has_zero_revision_and_empty_links_defaults() -> None:
    # Given / When: the smallest valid compile request is parsed.
    request = WikiCompileRequest(
        request_key="wiki-request-1",
        page_id="acme.refund",
        title="환불 절차",
        kind=WikiKind.PROCEDURE,
        query=_query(),
    )

    # Then: create semantics and no outgoing links are explicit.
    assert request.expected_page_revision == 0
    assert request.links == ()
    assert datetime.now(UTC).tzinfo is not None
