from collections.abc import Callable

from ax_starter.common import ActorKind, AXError, Operation, Principal, Purpose, Sensitivity
from ax_starter.retrieval import Answer, Query
from ax_starter.wiki_contracts import WikiCompilation


def require_page_id(tenant: str, page_id: str) -> None:
    prefix = f"{tenant}."
    suffix = page_id.removeprefix(prefix)
    if not page_id.startswith(prefix) or not suffix or "." in suffix:
        raise AXError("wiki_page_not_found", 404)


def current_principal(
    actor: Principal,
    credential_guard: Callable[[], None] | None,
    resolver: Callable[[], tuple[Principal, ...]] | None,
) -> Principal:
    if credential_guard is not None:
        credential_guard()
    if resolver is None:
        return actor
    current = next(
        (
            principal
            for principal in resolver()
            if principal.tenant == actor.tenant and principal.subject == actor.subject
        ),
        None,
    )
    if current is None or current != actor:
        raise AXError("authentication_required", 401)
    return current


def require_compile_access(actor: Principal, query: Query) -> str:
    if (
        Operation.READ not in actor.operations
        or Operation.MANAGE_KNOWLEDGE not in actor.operations
        or query.purpose not in actor.purposes
    ):
        raise AXError("access_denied", 403)
    if actor.effective_person_id is None:
        raise AXError("wiki_proposer_identity_required", 403)
    return actor.effective_person_id


def require_read_access(actor: Principal, purpose: Purpose) -> None:
    if Operation.READ not in actor.operations or purpose not in actor.purposes:
        raise AXError("access_denied", 403)


def require_reviewer(
    actor: Principal,
    proposer: Principal,
) -> str:
    if actor.actor_kind is not ActorKind.HUMAN or actor.effective_person_id is None:
        raise AXError("wiki_human_review_required", 403)
    if Operation.READ not in actor.operations or Operation.APPROVE not in actor.operations:
        raise AXError("access_denied", 403)
    proposer_person = proposer.effective_person_id
    if proposer_person is None:
        raise AXError("wiki_proposer_identity_required", 403)
    if actor.subject == proposer.subject or actor.effective_person_id == proposer_person:
        raise AXError("wiki_independent_review_required", 403)
    return actor.effective_person_id


def current_proposer(
    draft_subject: str,
    draft_kind: ActorKind,
    draft_person_id: str,
    tenant: str,
    resolver: Callable[[], tuple[Principal, ...]] | None,
) -> Principal:
    if resolver is None:
        return Principal(
            subject=draft_subject,
            tenant=tenant,
            actor_kind=draft_kind,
            person_id=draft_person_id,
            groups=frozenset(),
            clearance=Sensitivity.PUBLIC,
            operations=frozenset(),
            purposes=frozenset(),
        )
    proposer = next(
        (
            principal
            for principal in resolver()
            if principal.tenant == tenant and principal.subject == draft_subject
        ),
        None,
    )
    if (
        proposer is None
        or proposer.actor_kind is not draft_kind
        or proposer.effective_person_id != draft_person_id
    ):
        raise AXError("wiki_proposer_identity_changed", 409)
    return proposer


def require_compilation_citations(compilation: WikiCompilation, raw: Answer) -> None:
    raw_by_id = {citation.document_id: citation for citation in raw.citations}
    if len(raw_by_id) != len(raw.citations):
        raise AXError("wiki_source_integrity_failure")
    seen: set[str] = set()
    for citation in compilation.citations:
        source = raw_by_id.get(citation.document_id)
        if source is None or citation.document_id in seen:
            raise AXError("wiki_citation_invalid", 422)
        seen.add(citation.document_id)
        if (
            citation.title != source.title
            or citation.source_uri != source.source_uri
            or citation.source_version != source.source_version
            or citation.content_sha256 != source.content_sha256
            or citation.access_sha256 != source.access_sha256
            or citation.object_ids != source.object_ids
            or citation.sensitivity != source.sensitivity
            or not citation.quote
            or citation.quote not in source.quote
        ):
            raise AXError("wiki_citation_invalid", 422)


def require_current_classification(
    classification: Sensitivity,
    required_floor: Sensitivity,
    *,
    read_projection: bool,
) -> None:
    if classification >= required_floor:
        return
    if read_projection:
        raise AXError("wiki_page_not_found", 404)
    raise AXError("wiki_recompile_required", 409)
