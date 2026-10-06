# pyright: reportAny=false
# SQLite entity rows are mutated to exercise current-object checks.
from datetime import datetime
from pathlib import Path
from typing import Literal, assert_never

import pytest

from ax_starter.common import AXError, Principal, Purpose, Sensitivity
from ax_starter.ontology import Link
from ax_starter.store import Store
from ax_starter.wiki import WikiService
from ax_starter.wiki_contracts import WikiCompileRequest
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_pack,
    wiki_request,
    wiki_reviewer,
)


def _scope_service(
    path: Path,
    now: datetime,
) -> tuple[WikiService, Principal, Principal, Principal]:
    base = wiki_pack()
    secret = next(entity for entity in base.objects if entity.id == "restricted-case")
    link = Link(
        id="secret-policy",
        type="governed_by",
        source_id=secret.id,
        target_id="procedure-1",
        access=secret.access,
    )
    pack = base.model_copy(
        update={
            "links": (*base.links, link),
            "documents": tuple(doc for doc in base.documents if doc.id != "restricted-doc"),
        }
    )
    author = wiki_author().model_copy(
        update={"groups": frozenset({"procurement", "private-board"})}
    )
    high_reviewer = wiki_reviewer().model_copy(
        update={"groups": frozenset({"procurement", "private-board"})}
    )
    low_reviewer = wiki_reviewer(subject="low-reviewer", person_id="low-reviewer-person")
    store = Store(path, pack)
    service = WikiService(
        store,
        pack,
        principal_resolver=lambda: (author, high_reviewer, low_reviewer),
        server_query_floor=Sensitivity.INTERNAL,
        clock=lambda: now,
    )
    return service, author, high_reviewer, low_reviewer


def _scope_request() -> WikiCompileRequest:
    return wiki_request().model_copy(
        update={
            "query": wiki_request().query.model_copy(
                update={
                    "question": "검토 운영 절차",
                    "object_id": "restricted-case",
                    "hops": 1,
                }
            )
        }
    )


def test_anchor_and_hop_objects_are_review_hash_bound_and_required_for_reviewer(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a hidden anchor reaches a public-to-the-group source through one graph hop.
    service, author, _, low_reviewer = _scope_service(tmp_path / "scope-review.db", now)
    draft = service.compile(author, _scope_request(), now, extractive_compiler)

    # Then: the complete retrieval scope, including the non-source anchor, is bound.
    assert {item.object_id for item in draft.payload.scope_object_bindings} == {
        "procedure-1",
        "restricted-case",
    }

    # When / Then: a reviewer who sees the document but not the anchor gets a uniform 404.
    with pytest.raises(AXError, match="wiki_page_not_found") as raised:
        _ = service.publish(low_reviewer, draft.id, draft.payload_hash, now)
    assert raised.value.status == 404


def test_scope_objects_gate_read_and_query_selection(tmp_path: Path, now: datetime) -> None:
    # Given: a page was reviewed by principals who see the hidden anchor and its hop.
    service, author, reviewer, low_reader = _scope_service(tmp_path / "scope-read.db", now)
    draft = service.compile(author, _scope_request(), now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)

    # Then: a reader missing only the anchor cannot observe the page.
    assert service.index(low_reader, Purpose.OPERATIONS, now) == ()
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.page(low_reader, page.page_id, Purpose.OPERATIONS, now)

    # And: a narrower query scope cannot select a page compiled from a wider scope.
    narrow = _scope_request().query.model_copy(update={"object_id": "procedure-1", "hops": 0})
    answer = service.query(author, narrow, now)
    assert answer.pages == ()


@pytest.mark.parametrize(
    "change",
    ["classification", "acl"],
)
def test_current_scope_object_change_hides_page_and_requires_recompile(
    tmp_path: Path,
    now: datetime,
    change: Literal["classification", "acl"],
) -> None:
    # Given: a reviewed page binds the full object and ACL snapshots.
    service, author, reviewer, _ = _scope_service(tmp_path / "scope-drift.db", now)
    draft = service.compile(author, _scope_request(), now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)
    with service.store.transaction() as conn:
        entity = service.store.entity(conn, "restricted-case")
        match change:
            case "classification":
                access = entity.access.model_copy(update={"sensitivity": Sensitivity.CONFIDENTIAL})
            case "acl":
                access = entity.access.model_copy(
                    update={"groups": frozenset({"private-board", "procurement"})}
                )
            case unreachable:
                assert_never(unreachable)
        changed = entity.model_copy(update={"access": access})
        service.store.save_entity(conn, changed)

    # When / Then: ordinary reads hide the page while management gets a recovery revision.
    assert service.index(author, Purpose.OPERATIONS, now) == ()
    findings = service.lint(author, Purpose.OPERATIONS, now)
    assert [(item.page_id, item.revision, item.reason) for item in findings] == [
        (page.page_id, page.revision, "object_changed")
    ]


def test_more_than_one_hundred_bound_objects_fails_with_typed_422(
    tmp_path: Path,
    now: datetime,
) -> None:
    # Given: four eligible documents collectively bind 101 distinct source objects.
    base = wiki_pack()
    prototype = next(entity for entity in base.objects if entity.id == "procedure-1")
    objects = tuple(
        prototype.model_copy(update={"id": f"scope-{index:03d}", "label": f"Scope {index}"})
        for index in range(101)
    )
    source = base.documents[0]
    documents = tuple(
        source.model_copy(
            update={
                "id": f"scope-doc-{index}",
                "object_ids": tuple(item.id for item in objects[index * 30 : (index + 1) * 30]),
                "title": "scope overflow",
                "text": "scope overflow",
                "source_uri": f"memory://scope/{index}",
            }
        )
        for index in range(4)
    )
    pack = base.model_copy(update={"objects": objects, "links": (), "documents": documents})
    author, reviewer = wiki_author(), wiki_reviewer()
    service = WikiService(
        Store(tmp_path / "scope-limit.db", pack),
        pack,
        principal_resolver=lambda: (author, reviewer),
        server_query_floor=Sensitivity.INTERNAL,
        clock=lambda: now,
    )
    request = wiki_request().model_copy(
        update={"query": wiki_request().query.model_copy(update={"question": "scope overflow"})}
    )

    # When / Then: the boundary closes as a stable client error before payload validation.
    with pytest.raises(AXError, match="wiki_object_scope_limit") as raised:
        _ = service.compile(author, request, now, extractive_compiler)
    assert raised.value.status == 422
