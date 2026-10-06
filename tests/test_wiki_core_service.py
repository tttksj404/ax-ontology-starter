from datetime import datetime
from pathlib import Path

import pytest

from ax_starter.common import AXError, Operation, Purpose, Sensitivity
from ax_starter.retrieval import Answer
from ax_starter.wiki_contracts import (
    WikiCompilation,
    WikiCompileRequest,
    WikiKind,
)
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


def test_compile_publish_and_read_visible_page(tmp_path: Path, now: datetime) -> None:
    # Given: a manager compiles from authorized raw retrieval context.
    service = wiki_service(tmp_path / "wiki.db", now)
    author, reviewer = wiki_author(), wiki_reviewer()
    draft = service.compile(author, wiki_request(), now, extractive_compiler)

    # When: an independent human reviews the exact payload hash.
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)

    # Then: the immutable page is available through every read projection.
    assert page.revision == 1
    assert service.page(author, page.page_id, Purpose.OPERATIONS, now) == page
    assert service.index(author, Purpose.OPERATIONS, now)[0].page_id == page.page_id
    answer = service.query(author, wiki_request().query, now)
    assert answer.pages[0].page_id == page.page_id
    exported = service.export(author, page.page_id, Purpose.OPERATIONS, now)
    assert exported.manifest.non_authoritative is True
    assert exported.manifest.page_hash
    assert exported.text.startswith("AX_DERIVED_WIKI_V1\n")


def test_compile_retry_returns_saved_draft_without_calling_model_again(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a successful first compile and a compiler call counter.
    service = wiki_service(tmp_path / "retry.db", now)
    author = wiki_author()
    calls = 0

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        nonlocal calls
        calls += 1
        return extractive_compiler(request, answer)

    first = service.compile(author, wiki_request(), now, compiler)

    # When: the same actor retries the same request key and payload.
    second = service.compile(author, wiki_request(), now, compiler)

    # Then: durable idempotency wins before another compiler invocation.
    assert second == first
    assert calls == 1


def test_runtime_floor_raise_requires_recompile_before_replay_view_or_publish(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a draft compiled under a lower server-owned query floor.
    service = wiki_service(tmp_path / "floor-draft.db", now)
    author, reviewer = wiki_author(), wiki_reviewer()
    calls = 0

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        nonlocal calls
        calls += 1
        return extractive_compiler(request, answer)

    draft = service.compile(author, wiki_request(), now, compiler)
    assert draft.payload.classification < Sensitivity.RESTRICTED
    service.server_query_floor = Sensitivity.RESTRICTED

    # When / Then: every draft reuse path demands an explicit new request key.
    with pytest.raises(AXError, match="wiki_recompile_required") as replay:
        _ = service.compile(author, wiki_request(), now, compiler)
    with pytest.raises(AXError, match="wiki_recompile_required") as viewed:
        _ = service.view_draft(author, draft.id, now)
    with pytest.raises(AXError, match="wiki_recompile_required") as published:
        _ = service.publish(reviewer, draft.id, draft.payload_hash, now)
    assert {replay.value.status, viewed.value.status, published.value.status} == {409}
    assert calls == 1


def test_compile_replay_hides_draft_after_author_clearance_downcast(
    tmp_path: Path, now: datetime
) -> None:
    # Given: the author compiled a draft before their current clearance was reduced.
    author, reviewer = wiki_author(), wiki_reviewer()
    service = wiki_service(tmp_path / "replay-downcast.db", now, principals=(author, reviewer))
    calls = 0

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        nonlocal calls
        calls += 1
        return extractive_compiler(request, answer)

    _ = service.compile(author, wiki_request(), now, compiler)
    downcast = author.model_copy(update={"clearance": Sensitivity.PUBLIC})
    service.principal_resolver = lambda: (downcast, reviewer)

    # When / Then: exact replay reveals no stored payload and does not call the model.
    with pytest.raises(AXError, match="wiki_draft_not_found") as raised:
        _ = service.compile(downcast, wiki_request(), now, compiler)
    assert raised.value.status == 404
    assert calls == 1


def test_independent_reviewer_can_view_draft_but_read_only_actor_cannot(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a pending draft and two different humans with reviewer and read-only roles.
    author, reviewer = wiki_author(), wiki_reviewer()
    reader = reviewer.model_copy(
        update={
            "subject": "wiki-reader",
            "person_id": "person-reader",
            "operations": frozenset({Operation.READ}),
        }
    )
    service = wiki_service(
        tmp_path / "reviewer-view.db", now, principals=(author, reviewer, reader)
    )
    draft = service.compile(author, wiki_request(), now, extractive_compiler)

    # When / Then: an independent approver gets the full review payload; READ alone does not.
    viewed = service.view_draft(reviewer, draft.id, now)
    assert viewed == draft
    assert viewed.payload.input_citations
    with pytest.raises(AXError, match="access_denied") as raised:
        _ = service.view_draft(reader, draft.id, now)
    assert raised.value.status == 403


def test_page_namespace_is_checked_before_compiler_invocation(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a nested suffix that is a valid generic Identifier.
    service = wiki_service(tmp_path / "namespace.db", now)
    request = wiki_request().model_copy(update={"page_id": "acme.secret.page"})
    called = False

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        nonlocal called
        called = True
        return extractive_compiler(request, answer)

    # When / Then: tenant namespace validation fails before lookup or model work.
    with pytest.raises(AXError, match="wiki_page_not_found") as raised:
        _ = service.compile(wiki_author(), request, now, compiler)
    assert raised.value.status == 404
    assert called is False


def test_same_request_key_with_changed_payload_conflicts(tmp_path: Path, now: datetime) -> None:
    # Given: a saved draft for one exact request payload.
    service = wiki_service(tmp_path / "conflict.db", now)
    author = wiki_author()
    _ = service.compile(author, wiki_request(), now, extractive_compiler)
    changed = wiki_request().model_copy(update={"kind": WikiKind.SYNTHESIS})

    # When / Then: the idempotency key cannot be rebound.
    with pytest.raises(AXError, match="wiki_idempotency_conflict") as raised:
        _ = service.compile(author, changed, now, extractive_compiler)
    assert raised.value.status == 409


def test_wiki_query_rejects_implicit_model_generation(tmp_path: Path, now: datetime) -> None:
    # Given: a query requests the base RAG generation flag on the wiki surface.
    service = wiki_service(tmp_path / "generation.db", now)
    query = wiki_request().query.model_copy(update={"generate": True})

    # When / Then: wiki search remains an explicit retrieval-only operation.
    with pytest.raises(AXError, match="wiki_query_generation_not_supported") as raised:
        _ = service.query(wiki_author(), query, now)
    assert raised.value.status == 422
