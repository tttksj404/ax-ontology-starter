from datetime import datetime
from pathlib import Path

import pytest

from ax_starter.common import AXError, Principal, Purpose, Sensitivity
from ax_starter.ontology import DomainPack
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


def _link_pack(groups: frozenset[str]) -> DomainPack:
    base = wiki_pack()
    link = base.links[0].model_copy(
        update={"access": base.links[0].access.model_copy(update={"groups": groups})}
    )
    return base.model_copy(update={"links": (link,)})


def _link_request(*, request_key: str = "link-scope") -> WikiCompileRequest:
    return wiki_request(request_key=request_key).model_copy(
        update={
            "query": wiki_request().query.model_copy(update={"object_id": "request-1", "hops": 1})
        }
    )


def _hidden_link_service(
    path: Path,
    now: datetime,
) -> tuple[WikiService, Principal, Principal, Principal]:
    pack = _link_pack(frozenset({"hr-case"}))
    author = wiki_author().model_copy(update={"groups": frozenset({"procurement", "hr-case"})})
    high_reviewer = wiki_reviewer().model_copy(
        update={"groups": frozenset({"procurement", "hr-case"})}
    )
    low_reviewer = wiki_reviewer(subject="low-reviewer", person_id="low-reviewer-person")
    service = WikiService(
        Store(path, pack),
        pack,
        principal_resolver=lambda: (author, high_reviewer, low_reviewer),
        server_query_floor=Sensitivity.INTERNAL,
        clock=lambda: now,
    )
    return service, author, high_reviewer, low_reviewer


def test_reviewer_missing_hop_link_cannot_view_review_packet(
    tmp_path: Path,
    now: datetime,
) -> None:
    # Given: the reviewer sees both endpoint objects and the source, but not their link.
    service, author, _, low_reviewer = _hidden_link_service(tmp_path / "packet.db", now)
    draft = service.compile(author, _link_request(), now, extractive_compiler)

    # When / Then: the packet does not reveal the author's hidden relationship scope.
    with pytest.raises(AXError, match="wiki_draft_not_found") as raised:
        _ = service.view_draft(low_reviewer, draft.id, now)
    assert raised.value.status == 404


def test_reviewer_missing_hop_link_cannot_publish(
    tmp_path: Path,
    now: datetime,
) -> None:
    # Given: a draft was compiled through a relationship hidden from the reviewer.
    service, author, _, low_reviewer = _hidden_link_service(tmp_path / "publish.db", now)
    draft = service.compile(author, _link_request(), now, extractive_compiler)

    # When / Then: publish closes with the same page-not-found projection.
    with pytest.raises(AXError, match="wiki_page_not_found") as raised:
        _ = service.publish(low_reviewer, draft.id, draft.payload_hash, now)
    assert raised.value.status == 404


def test_revoked_hop_link_hides_cached_page_and_blocks_recompile(
    tmp_path: Path,
    now: datetime,
) -> None:
    # Given: a page was published while its retrieval link was visible to the normal roles.
    visible_pack = _link_pack(frozenset({"procurement"}))
    author, reviewer = wiki_author(), wiki_reviewer()
    link_manager = wiki_author(subject="link-manager", person_id="link-manager-person").model_copy(
        update={"groups": frozenset({"procurement", "hr-case"})}
    )
    service = WikiService(
        Store(tmp_path / "revoked.db", visible_pack),
        visible_pack,
        principal_resolver=lambda: (author, reviewer, link_manager),
        server_query_floor=Sensitivity.INTERNAL,
        clock=lambda: now,
    )
    request = _link_request()
    draft = service.compile(author, request, now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)
    assert service.query(reviewer, request.query, now).pages

    # When: the same link is restricted while both endpoint object ACLs remain unchanged.
    service.template = _link_pack(frozenset({"hr-case"}))

    # Then: every ordinary projection and same-page recompile closes for the former reader.
    assert service.index(reviewer, Purpose.OPERATIONS, now) == ()
    assert service.query(reviewer, request.query, now).pages == ()
    assert service.lint(author, Purpose.OPERATIONS, now) == ()
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.page(reviewer, page.page_id, Purpose.OPERATIONS, now)
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.export(reviewer, page.page_id, Purpose.OPERATIONS, now)
    replacement = _link_request(request_key="low-recompile").model_copy(
        update={"expected_page_revision": page.revision}
    )
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.compile(author, replacement, now, extractive_compiler)

    # A manager with the current link scope can still use the known revision for recovery.
    allowed = _link_request(request_key="manager-recompile").model_copy(
        update={"expected_page_revision": page.revision}
    )
    recovered = service.compile(link_manager, allowed, now, extractive_compiler)
    assert recovered.payload.expected_page_revision == page.revision


def test_raised_link_classification_hides_page_until_recompile(
    tmp_path: Path,
    now: datetime,
) -> None:
    # Given: a page was classified while its visible retrieval link was INTERNAL.
    initial_pack = _link_pack(frozenset({"procurement"}))
    author, reviewer = wiki_author(), wiki_reviewer()
    service = WikiService(
        Store(tmp_path / "link-floor.db", initial_pack),
        initial_pack,
        principal_resolver=lambda: (author, reviewer),
        server_query_floor=Sensitivity.INTERNAL,
        clock=lambda: now,
    )
    request = _link_request()
    draft = service.compile(author, request, now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)
    assert page.classification is Sensitivity.INTERNAL

    # When: only the same link's current classification rises to RESTRICTED.
    raised_link = initial_pack.links[0].model_copy(
        update={
            "access": initial_pack.links[0].access.model_copy(
                update={"sensitivity": Sensitivity.RESTRICTED}
            )
        }
    )
    service.template = initial_pack.model_copy(update={"links": (raised_link,)})

    # Then: the cached classification cannot authorize read/export and lint requests recompile.
    assert service.index(reviewer, Purpose.OPERATIONS, now) == ()
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.page(reviewer, page.page_id, Purpose.OPERATIONS, now)
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.export(reviewer, page.page_id, Purpose.OPERATIONS, now)
    findings = service.lint(author, Purpose.OPERATIONS, now)
    assert [(item.page_id, item.revision, item.reason) for item in findings] == [
        (page.page_id, page.revision, "object_changed")
    ]

    replacement = _link_request(request_key="link-floor-recompile").model_copy(
        update={"expected_page_revision": page.revision}
    )
    recovered = service.compile(author, replacement, now, extractive_compiler)
    assert recovered.payload.classification is Sensitivity.RESTRICTED
