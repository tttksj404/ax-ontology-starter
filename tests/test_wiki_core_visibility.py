from datetime import datetime
from pathlib import Path

import pytest

from ax_starter.common import AXError, Operation, Principal, Purpose, Sensitivity
from ax_starter.ontology import Document, Entity
from ax_starter.retrieval import Answer
from ax_starter.store import Store
from ax_starter.wiki import WikiService
from ax_starter.wiki_contracts import (
    WikiCompilation,
    WikiCompileRequest,
    WikiGenerationRoute,
    WikiKind,
)
from ax_starter.wiki_schema import migrate_wiki
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_pack,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


def dual_group_service(path: Path, now: datetime) -> tuple[WikiService, Principal, Principal]:
    base = wiki_pack()
    second_access = base.documents[0].access.model_copy(update={"groups": frozenset({"finance"})})
    second_entity = Entity(
        id="procedure-2",
        type="Procedure",
        label="추가 검토 절차",
        access=second_access,
        properties=base.objects[1].properties,
        source="synthetic:procedure-2",
    )
    second_document = Document(
        id="sop-2",
        object_ids=(second_entity.id,),
        title="추가 검토 절차",
        text="추가 검토 절차를 적용합니다.",
        source_uri="synthetic://sop/review-2",
        source_version="1",
        access=second_access,
        valid_until=base.documents[0].valid_until,
    )
    pack = base.model_copy(
        update={
            "objects": (*base.objects, second_entity),
            "documents": (*base.documents, second_document),
        }
    )
    author = wiki_author().model_copy(update={"groups": frozenset({"procurement", "finance"})})
    reviewer = wiki_reviewer().model_copy(update={"groups": frozenset({"procurement", "finance"})})
    store = Store(path, pack)
    with store.transaction() as conn:
        migrate_wiki(conn)
    service = WikiService(
        store,
        pack,
        principal_resolver=lambda: (author, reviewer),
        server_query_floor=Sensitivity.INTERNAL,
        clock=lambda: now,
    )
    return service, author, reviewer


def _principal(subject: str, person_id: str, *, approve: bool) -> Principal:
    operations = {Operation.READ, Operation.MANAGE_KNOWLEDGE}
    if approve:
        operations = {Operation.READ, Operation.APPROVE}
    return Principal(
        subject=subject,
        person_id=person_id,
        tenant="acme",
        groups=frozenset({"procurement", "private-board"}),
        clearance=Sensitivity.RESTRICTED,
        operations=frozenset(operations),
        purposes=frozenset({Purpose.OPERATIONS}),
    )


def test_mixed_groups_apply_conjunctive_visibility_per_source(
    tmp_path: Path, now: datetime
) -> None:
    # Given: two raw sources use disjoint groups and one human has both roles.
    service, author, reviewer = dual_group_service(tmp_path / "mixed.db", now)

    # When: one draft compiles from the full two-source model context.
    draft = service.compile(author, wiki_request(), now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)

    # Then: each source policy passes independently despite an empty global intersection.
    assert {source.document_id for source in page.source_bindings} == {"sop-1", "sop-2"}


def test_review_payload_keeps_full_input_context_when_compiler_cites_subset(
    tmp_path: Path, now: datetime
) -> None:
    # Given: raw retrieval supplies two independently authorized sources.
    service, author, reviewer = dual_group_service(tmp_path / "review-context.db", now)

    def subset_compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        del request
        return WikiCompilation(
            body=answer.text,
            citations=(answer.citations[0],),
            compiler_mode="model_draft",
            sensitivity=answer.sensitivity,
            generation_route=WikiGenerationRoute(
                mode="private_gateway",
                endpoint_host="gateway.example",
                model="synthetic-review-model",
                provider_settings_sha256="a" * 64,
            ),
        )

    # When: the model chooses only one citation for its generated body.
    draft = service.compile(author, wiki_request(), now, subset_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)

    # Then: review and immutable page retain the complete server-retrieved context.
    assert len(draft.payload.citations) == 1
    assert {item.document_id for item in draft.payload.input_citations} == {"sop-1", "sop-2"}
    assert page.input_citations == draft.payload.input_citations
    assert draft.payload.generation_route == page.generation_route
    exported = service.export(author, page.page_id, Purpose.OPERATIONS, now)
    assert exported.manifest.generation_route == page.generation_route


def test_hidden_page_title_link_backlink_and_count_do_not_leak(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a visible page links to a second page based on restricted raw context.
    low_author, low_reviewer = wiki_author(), wiki_reviewer()
    high_author = _principal("secret-author", "person-secret-author", approve=False)
    high_reviewer = _principal("secret-reviewer", "person-secret-reviewer", approve=True)
    principals = (low_author, low_reviewer, high_author, high_reviewer)
    service = wiki_service(tmp_path / "hidden.db", now, principals=principals)
    public_request = wiki_request().model_copy(update={"links": ("acme.secret",)})
    public_draft = service.compile(low_author, public_request, now, extractive_compiler)
    _ = service.publish(low_reviewer, public_draft.id, public_draft.payload_hash, now)
    secret_request = wiki_request(request_key="secret-request").model_copy(
        update={
            "page_id": "acme.secret",
            "title": "HIDDEN_TITLE_SENTINEL",
            "kind": WikiKind.CONCEPT,
            "query": wiki_request().query.model_copy(
                update={"question": "RESTRICTED_SENTINEL 검토"}
            ),
        }
    )
    secret_draft = service.compile(high_author, secret_request, now, extractive_compiler)
    _ = service.publish(high_reviewer, secret_draft.id, secret_draft.payload_hash, now)

    # When: the lower-privilege reader opens index and searches for the hidden title.
    index = service.index(low_author, Purpose.OPERATIONS, now)
    answer = service.query(
        low_author,
        wiki_request().query.model_copy(update={"question": "HIDDEN_TITLE_SENTINEL"}),
        now,
    )

    # Then: neither cardinality metadata nor graph metadata reveals the hidden page.
    assert len(index) == 1
    assert index[0].links == ()
    assert index[0].backlinks == ()
    assert answer.pages == ()
    assert "HIDDEN_TITLE_SENTINEL" not in answer.answer.text


def test_runtime_floor_raise_hides_existing_published_page(tmp_path: Path, now: datetime) -> None:
    # Given: a reviewed page whose stored classification matches the old floor.
    service = wiki_service(tmp_path / "floor-page.db", now)
    author, reviewer = wiki_author(), wiki_reviewer()
    draft = service.compile(author, wiki_request(), now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)
    assert page.classification < Sensitivity.RESTRICTED

    # When: the server-owned query floor is raised after publication.
    service.server_query_floor = Sensitivity.RESTRICTED

    # Then: read projections reveal neither the page nor its index cardinality.
    assert service.index(author, Purpose.OPERATIONS, now) == ()
    with pytest.raises(AXError, match="wiki_page_not_found") as raised:
        _ = service.page(author, page.page_id, Purpose.OPERATIONS, now)
    assert raised.value.status == 404


def test_page_cas_and_publish_reviewer_idempotency(tmp_path: Path, now: datetime) -> None:
    # Given: two current authors compile revision zero concurrently.
    first_author = wiki_author()
    second_author = wiki_author(subject="author-2", person_id="person-author-2")
    first_reviewer = wiki_reviewer()
    second_reviewer = wiki_reviewer(subject="reviewer-2", person_id="person-reviewer-2")
    service = wiki_service(
        tmp_path / "cas.db",
        now,
        principals=(first_author, second_author, first_reviewer, second_reviewer),
    )
    first = service.compile(first_author, wiki_request(), now, extractive_compiler)
    second = service.compile(
        second_author,
        wiki_request(request_key="wiki-request-2"),
        now,
        extractive_compiler,
    )

    # When: one review wins, its exact retry succeeds, and competitors retry.
    published = service.publish(first_reviewer, first.id, first.payload_hash, now)
    retried = service.publish(first_reviewer, first.id, first.payload_hash, now)

    # Then: reviewer binding is idempotent while stale CAS and another reviewer fail.
    assert retried == published
    with pytest.raises(AXError, match="wiki_page_revision_conflict"):
        _ = service.publish(second_reviewer, second.id, second.payload_hash, now)
    with pytest.raises(AXError, match="wiki_review_owner_mismatch"):
        _ = service.publish(second_reviewer, first.id, first.payload_hash, now)
