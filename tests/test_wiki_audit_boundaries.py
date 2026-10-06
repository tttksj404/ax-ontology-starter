from datetime import datetime
from pathlib import Path

import pytest

from ax_starter.common import ActorKind, AXError, Operation, Principal, Purpose, Sensitivity
from ax_starter.retrieval import Answer
from ax_starter.wiki import WikiService
from ax_starter.wiki_contracts import WikiCompilation, WikiCompileRequest, WikiKind, WikiPage
from ax_starter.wiki_schema import invalidate_wiki_sources
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


def _privileged(subject: str, person_id: str, *, reviewer: bool) -> Principal:
    operation = Operation.APPROVE if reviewer else Operation.MANAGE_KNOWLEDGE
    return Principal(
        subject=subject,
        person_id=person_id,
        tenant="acme",
        groups=frozenset({"procurement", "private-board"}),
        clearance=Sensitivity.RESTRICTED,
        operations=frozenset({Operation.READ, operation}),
        purposes=frozenset({Purpose.OPERATIONS}),
    )


def _publish_hidden_page(
    path: Path, now: datetime
) -> tuple[WikiService, WikiPage, Principal, Principal]:
    low_author, low_reviewer = wiki_author(), wiki_reviewer()
    high_author = _privileged("high-author", "high-author-person", reviewer=False)
    high_reviewer = _privileged("high-reviewer", "high-reviewer-person", reviewer=True)
    service = wiki_service(
        path,
        now,
        principals=(low_author, low_reviewer, high_author, high_reviewer),
    )
    request = wiki_request(request_key="hidden-create").model_copy(
        update={
            "page_id": "acme.secret",
            "title": "비공개 절차",
            "kind": WikiKind.CONCEPT,
            "query": wiki_request().query.model_copy(update={"question": "RESTRICTED_SENTINEL"}),
        }
    )
    draft = service.compile(high_author, request, now, extractive_compiler)
    page = service.publish(high_reviewer, draft.id, draft.payload_hash, now)
    return service, page, low_author, low_reviewer


@pytest.mark.parametrize("expected_revision", [0, 1, 99])
def test_hidden_head_compile_is_indistinguishable_for_every_revision_guess(
    tmp_path: Path, now: datetime, expected_revision: int
) -> None:
    # Given: a published head exists only under a stronger source ACL.
    service, page, low_author, _ = _publish_hidden_page(tmp_path / "hidden-head.db", now)
    calls = 0

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        nonlocal calls
        calls += 1
        return extractive_compiler(request, answer)

    overwrite = wiki_request(request_key=f"guess-{expected_revision}").model_copy(
        update={"page_id": page.page_id, "expected_page_revision": expected_revision}
    )

    # When / Then: neither existence, revision, nor a model call is observable.
    with pytest.raises(AXError, match="wiki_page_not_found") as raised:
        _ = service.compile(low_author, overwrite, now, compiler)
    assert raised.value.status == 404
    assert calls == 0


def test_hidden_head_reviewer_cannot_publish_overwrite(tmp_path: Path, now: datetime) -> None:
    # Given: a privileged author prepares a replacement for an existing hidden head.
    service, page, _, low_reviewer = _publish_hidden_page(tmp_path / "hidden-review.db", now)
    high_author = _privileged("high-author", "high-author-person", reviewer=False)
    replacement = wiki_request(request_key="hidden-replace").model_copy(
        update={"page_id": page.page_id, "expected_page_revision": page.revision}
    )
    draft = service.compile(high_author, replacement, now, extractive_compiler)

    # When / Then: a reviewer unable to read the replaced head gets the uniform 404.
    with pytest.raises(AXError, match="wiki_page_not_found") as raised:
        _ = service.publish(low_reviewer, draft.id, draft.payload_hash, now)
    assert raised.value.status == 404
    current = service.page(high_author, page.page_id, Purpose.OPERATIONS, now)
    assert current.version_id == page.version_id


def test_stale_head_lint_exposes_revision_only_to_authorized_manager_and_recovers(
    tmp_path: Path, now: datetime
) -> None:
    # Given: an authorized manager owns a page whose source invalidation made its head stale.
    service = wiki_service(tmp_path / "stale-recovery.db", now)
    author, reviewer = wiki_author(), wiki_reviewer()
    draft = service.compile(author, wiki_request(), now, extractive_compiler)
    page = service.publish(reviewer, draft.id, draft.payload_hash, now)
    retired_source = page.source_bindings[0].document_id
    with service.store.transaction() as conn:
        _ = conn.execute(
            "UPDATE knowledge_documents SET lifecycle = 'retired' WHERE document_id = ?",
            (retired_source,),
        )
        invalidate_wiki_sources(conn, "acme", (retired_source,), ())

    # When: the management lint surface reports the last revision and recovery reason.
    findings = service.lint(author, Purpose.OPERATIONS, now)

    # Then: that revision is usable for an authorized stale-head recompile.
    assert [(item.page_id, item.revision, item.state, item.reason) for item in findings] == [
        (page.page_id, page.revision, "stale", "head_stale")
    ]
    with service.store.transaction() as conn:
        _ = conn.execute(
            "UPDATE knowledge_documents SET lifecycle = 'active' WHERE document_id = ?",
            (retired_source,),
        )
    replacement = wiki_request(request_key="stale-recompile").model_copy(
        update={"expected_page_revision": findings[0].revision}
    )
    recovered = service.compile(author, replacement, now, extractive_compiler)
    assert recovered.payload.expected_page_revision == page.revision


def test_service_without_effective_person_cannot_compile(tmp_path: Path, now: datetime) -> None:
    # Given: a service credential has knowledge rights but no registry-bound person.
    service_actor = wiki_author().model_copy(
        update={"subject": "wiki-bot", "actor_kind": ActorKind.SERVICE, "person_id": None}
    )
    service = wiki_service(
        tmp_path / "service-author.db",
        now,
        principals=(service_actor, wiki_reviewer()),
    )

    # When / Then: drafts always bind a non-null effective proposer person.
    with pytest.raises(AXError, match="wiki_proposer_identity_required"):
        _ = service.compile(service_actor, wiki_request(), now, extractive_compiler)


def test_compile_replay_rechecks_saved_person_binding(tmp_path: Path, now: datetime) -> None:
    # Given: the same subject is reassigned to a different person after compilation.
    author, reviewer = wiki_author(), wiki_reviewer()
    service = wiki_service(tmp_path / "replay-person.db", now, principals=(author, reviewer))
    _ = service.compile(author, wiki_request(), now, extractive_compiler)
    reassigned = author.model_copy(update={"person_id": "new-owner"})
    service.principal_resolver = lambda: (reassigned, reviewer)

    # When / Then: an exact request replay cannot return the previous person's draft.
    with pytest.raises(AXError, match="wiki_proposer_identity_changed"):
        _ = service.compile(reassigned, wiki_request(), now, extractive_compiler)


def test_publish_checks_authorization_before_review_hash(tmp_path: Path, now: datetime) -> None:
    # Given: an unprivileged tenant member knows a draft UUID and supplies a wrong hash.
    author, reviewer = wiki_author(), wiki_reviewer()
    outsider = wiki_author(subject="reader", person_id="reader-person").model_copy(
        update={"operations": frozenset({Operation.READ})}
    )
    service = wiki_service(tmp_path / "hash-order.db", now, principals=(author, reviewer, outsider))
    draft = service.compile(author, wiki_request(), now, extractive_compiler)

    # When / Then: permission denial occurs before review-hash disclosure.
    with pytest.raises(AXError, match="access_denied"):
        _ = service.publish(outsider, draft.id, "0" * 64, now)


def test_compile_checks_clearance_before_model_callback(tmp_path: Path, now: datetime) -> None:
    # Given: current source access passes but the server floor exceeds proposer clearance.
    author = wiki_author().model_copy(update={"clearance": Sensitivity.CONFIDENTIAL})
    reviewer = wiki_reviewer()
    service = wiki_service(tmp_path / "pre-model-clearance.db", now, principals=(author, reviewer))
    service.server_query_floor = Sensitivity.RESTRICTED
    calls = 0

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        nonlocal calls
        calls += 1
        return extractive_compiler(request, answer)

    # When / Then: denied work never crosses the model callback boundary.
    with pytest.raises(AXError, match="access_denied"):
        _ = service.compile(author, wiki_request(), now, compiler)
    assert calls == 0


def test_publish_rechecks_current_proposer_clearance(tmp_path: Path, now: datetime) -> None:
    # Given: output classification is restricted while its raw source remains internal.
    author, reviewer = wiki_author(), wiki_reviewer()
    service = wiki_service(tmp_path / "proposer-clearance.db", now, principals=(author, reviewer))

    def restricted_compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        return extractive_compiler(request, answer).model_copy(
            update={"sensitivity": Sensitivity.RESTRICTED}
        )

    draft = service.compile(author, wiki_request(), now, restricted_compiler)
    lowered = author.model_copy(update={"clearance": Sensitivity.CONFIDENTIAL})
    service.principal_resolver = lambda: (lowered, reviewer)

    # When / Then: the current proposer must still clear the reviewed page classification.
    with pytest.raises(AXError, match="access_denied"):
        _ = service.publish(reviewer, draft.id, draft.payload_hash, now)
