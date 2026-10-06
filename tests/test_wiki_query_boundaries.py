from datetime import datetime
from pathlib import Path

from ax_starter.common import Purpose, Sensitivity
from ax_starter.knowledge_store import StoredDocument, access_hash, document_record, save_document
from ax_starter.retrieval import Answer
from ax_starter.store import Store
from ax_starter.wiki import WikiService
from ax_starter.wiki_contracts import WikiCompilation, WikiCompileRequest
from tests.test_wiki_core_visibility import dual_group_service
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_pack,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


def test_wiki_query_respects_object_scope_and_zero_hops(tmp_path: Path, now: datetime) -> None:
    # Given: a page depends on procedure-1, reached from request-1 only with one hop.
    service = wiki_service(tmp_path / "scope.db", now)
    draft = service.compile(wiki_author(), wiki_request(), now, extractive_compiler)
    _ = service.publish(wiki_reviewer(), draft.id, draft.payload_hash, now)
    query = wiki_request().query.model_copy(update={"object_id": "request-1", "hops": 0})
    # When / Then
    result = service.query(wiki_author(), query, now)
    assert result.pages == ()
    assert result.answer.citations == ()
    assert "검토 절차" not in result.answer.text


def test_query_reports_all_model_input_sources_when_output_quotes_are_subset(
    tmp_path: Path, now: datetime
) -> None:
    # Given: the compiler saw two raw documents, but emitted a quote from only one.
    service, author, reviewer = dual_group_service(tmp_path / "provenance.db", now)

    def subset(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        return extractive_compiler(request, answer).model_copy(
            update={"citations": answer.citations[:1]}
        )

    draft = service.compile(author, wiki_request(), now, subset)
    _ = service.publish(reviewer, draft.id, draft.payload_hash, now)
    # When
    result = service.query(author, wiki_request().query, now)
    # Then: quote selection cannot erase the full input provenance manifest.
    assert len(draft.payload.citations) == 1
    assert len(result.pages[0].input_citations) == 2
    assert {binding.document_id for binding in result.pages[0].source_bindings} == {
        "sop-1",
        "sop-2",
    }


def test_lint_requires_historical_acl_even_after_acl_widening(
    tmp_path: Path, now: datetime
) -> None:
    # Given: finance can see the business object, but not the original source snapshot.
    author, reviewer = wiki_author(), wiki_reviewer()
    finance = author.model_copy(update={"subject": "finance", "groups": frozenset({"finance"})})
    service = wiki_service(
        tmp_path / "lint-snapshot.db", now, principals=(author, reviewer, finance)
    )
    draft = service.compile(author, wiki_request(), now, extractive_compiler)
    _ = service.publish(reviewer, draft.id, draft.payload_hash, now)
    with service.store.transaction() as conn:
        stored = document_record(conn, "sop-1")
        assert stored is not None
        assert stored.document is not None
        widened = stored.document.access.model_copy(
            update={"groups": frozenset({"procurement", "finance"})}
        )
        save_document(
            conn,
            StoredDocument(
                meta=stored.meta.model_copy(update={"access_sha256": access_hash(widened)}),
                document=stored.document.model_copy(update={"access": widened}),
                access_snapshot=widened,
            ),
        )
        for entity in service.template.objects:
            if entity.id not in stored.document.object_ids:
                continue
            widened_entity = entity.model_copy(update={"access": widened})
            _ = conn.execute(
                "UPDATE entities SET data = ? WHERE id = ?",
                (widened_entity.model_dump_json(), entity.id),
            )
    # When / Then: changed-source metadata is visible only under both ACLs.
    assert service.lint(author, Purpose.OPERATIONS, now)
    assert service.lint(finance, Purpose.OPERATIONS, now) == ()
    assert service.index(finance, Purpose.OPERATIONS, now) == ()


def test_no_page_fallback_keeps_server_classification_floor(tmp_path: Path, now: datetime) -> None:
    # Given: a caller supplies a lower query label than the server's minimum.
    service = wiki_service(tmp_path / "floor-output.db", now)
    service.server_query_floor = Sensitivity.RESTRICTED
    query = wiki_request().query.model_copy(update={"sensitivity": Sensitivity.PUBLIC})
    # When
    result = service.query(wiki_author(), query, now)
    # Then
    assert result.pages == ()
    assert result.answer.sensitivity is Sensitivity.RESTRICTED


def test_wiki_query_bounds_combined_citations_without_unquoted_page_text(
    tmp_path: Path, now: datetime
) -> None:
    # Given: two independently reviewed pages use 12 different raw documents.
    base = wiki_pack()
    source = base.documents[0]
    documents = tuple(
        source.model_copy(
            update={
                "id": f"source-{index}",
                "title": "공통",
                "text": "공통 첫문서" if index < 10 else "공통 마지막문서",
            }
        )
        for index in range(12)
    )
    pack = base.model_copy(update={"documents": documents})
    author, reviewer = wiki_author(), wiki_reviewer()
    service = WikiService(
        Store(tmp_path / "budget.db", pack),
        pack,
        principal_resolver=lambda: (author, reviewer),
        clock=lambda: now,
    )
    for key, word in (("a", "첫"), ("b", "마지막")):
        request = wiki_request(request_key="budget-" + key).model_copy(
            update={
                "page_id": "acme." + key,
                "query": wiki_request().query.model_copy(
                    update={"question": word + "문서", "top_k": 10}
                ),
            }
        )
        draft = service.compile(author, request, now, extractive_compiler)
        _ = service.publish(reviewer, draft.id, draft.payload_hash, now)
    # When
    result = service.query(
        author, wiki_request().query.model_copy(update={"question": "공통 검색", "top_k": 10}), now
    )
    # Then: each returned page's output references fit, and extra raw text is not unquoted.
    assert len(result.answer.citations) == 10
    assert len(result.pages) == 1
    assert "acme.b" not in result.answer.text
