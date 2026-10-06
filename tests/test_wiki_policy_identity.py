from datetime import datetime
from pathlib import Path

import pytest

from ax_starter.common import ActorKind, AXError, Purpose
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


def test_same_human_alias_cannot_review_own_draft(tmp_path: Path, now: datetime) -> None:
    # Given: distinct subjects resolve to the same effective human.
    author = wiki_author(person_id="person-shared")
    alias = wiki_reviewer(subject="reviewer-alias", person_id="person-shared")
    service = wiki_service(tmp_path / "alias.db", now, principals=(author, alias))
    draft = service.compile(author, wiki_request(), now, extractive_compiler)

    # When / Then: subject aliasing cannot bypass separation of duties.
    with pytest.raises(AXError, match="wiki_independent_review_required") as raised:
        _ = service.publish(alias, draft.id, draft.payload_hash, now)
    assert raised.value.status == 403


def test_service_identity_cannot_publish(tmp_path: Path, now: datetime) -> None:
    # Given: a service credential with otherwise sufficient operations.
    author = wiki_author()
    human = wiki_reviewer()
    service_actor = human.model_copy(
        update={"subject": "review-bot", "actor_kind": ActorKind.SERVICE, "person_id": None}
    )
    service = wiki_service(
        tmp_path / "service-review.db", now, principals=(author, human, service_actor)
    )
    draft = service.compile(author, wiki_request(), now, extractive_compiler)

    # When / Then: only a current human identity can review.
    with pytest.raises(AXError, match="wiki_human_review_required") as raised:
        _ = service.publish(service_actor, draft.id, draft.payload_hash, now)
    assert raised.value.status == 403


def test_revoked_exact_credential_is_rejected_on_read(tmp_path: Path, now: datetime) -> None:
    # Given: publication succeeds while the author is in the live directory.
    author = wiki_author()
    reviewer = wiki_reviewer()
    directory = [author, reviewer]
    service = wiki_service(tmp_path / "revoked.db", now, principals=tuple(directory))
    draft = service.compile(author, wiki_request(), now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)
    directory.clear()

    # When / Then: a formerly valid principal cannot read after revocation.
    service.principal_resolver = lambda: tuple(directory)
    with pytest.raises(AXError, match="authentication_required") as raised:
        _ = service.page(author, page.page_id, Purpose.OPERATIONS, now)
    assert raised.value.status == 401


def test_proposer_person_binding_drift_blocks_publish(tmp_path: Path, now: datetime) -> None:
    # Given: the proposer identity binding changes after draft compilation.
    author = wiki_author()
    reviewer = wiki_reviewer()
    service = wiki_service(tmp_path / "proposer-drift.db", now, principals=(author, reviewer))
    draft = service.compile(author, wiki_request(), now, extractive_compiler)
    changed_author = author.model_copy(update={"person_id": "different-person"})
    service.principal_resolver = lambda: (changed_author, reviewer)

    # When / Then: review cannot bless a payload whose proposer is no longer current.
    with pytest.raises(AXError, match="wiki_proposer_identity_changed") as raised:
        _ = service.publish(reviewer, draft.id, draft.payload_hash, now)
    assert raised.value.status == 409


def test_cross_tenant_draft_uuid_is_indistinguishable_from_missing(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a valid draft id exists only in another tenant.
    author = wiki_author()
    reviewer = wiki_reviewer()
    outsider = wiki_author(subject="beta-author", person_id="beta-person").model_copy(
        update={"tenant": "beta"}
    )
    service = wiki_service(tmp_path / "draft-tenant.db", now, principals=(author, reviewer))
    draft = service.compile(author, wiki_request(), now, extractive_compiler)
    service.principal_resolver = lambda: (author, reviewer, outsider)

    # When / Then: UUID lookup remains tenant-scoped and returns only 404.
    with pytest.raises(AXError, match="wiki_draft_not_found") as raised:
        _ = service.view_draft(outsider, draft.id, now)
    assert raised.value.status == 404
