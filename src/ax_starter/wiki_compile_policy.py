import sqlite3
from datetime import datetime

from ax_starter.common import AXError, Principal
from ax_starter.wiki_contracts import WikiCompileRequest, WikiDraft, WikiDraftState
from ax_starter.wiki_head_policy import require_existing_head_access
from ax_starter.wiki_object_policy import require_scope_objects_current
from ax_starter.wiki_policy import require_current_classification
from ax_starter.wiki_runtime import WikiRuntime
from ax_starter.wiki_source_policy import SourcePolicyContext, require_sources_current


def same_request(existing: WikiDraft, request_sha256: str) -> WikiDraft:
    if existing.request_sha256 != request_sha256:
        raise AXError("wiki_idempotency_conflict", 409)
    return existing


def current_replay(
    conn: sqlite3.Connection,
    runtime: WikiRuntime,
    actor: Principal,
    draft: WikiDraft,
    now: datetime,
) -> WikiDraft:
    if draft.state not in (WikiDraftState.DRAFT, WikiDraftState.PUBLISHED):
        raise AXError("wiki_source_stale", 409)
    if actor.clearance < draft.payload.classification:
        raise AXError("wiki_draft_not_found", 404)
    if (
        actor.actor_kind is not draft.payload.proposer_actor_kind
        or actor.effective_person_id != draft.payload.proposer_person_id
    ):
        raise AXError("wiki_proposer_identity_changed", 409)
    authorized = require_existing_head_access(
        conn,
        runtime,
        actor,
        draft.payload.page_id,
        now,
    )
    if authorized is None:
        if draft.payload.expected_page_revision != 0:
            raise AXError("wiki_page_not_found", 404)
    elif (
        not (
            draft.state is WikiDraftState.PUBLISHED
            and draft.published_revision == authorized.head.revision
        )
        and authorized.head.revision != draft.payload.expected_page_revision
    ):
        raise AXError("wiki_page_revision_conflict", 409)
    require_current_classification(
        draft.payload.classification,
        runtime.server_query_floor,
        read_projection=False,
    )
    context = SourcePolicyContext(
        conn=conn,
        store=runtime.store,
        template=runtime.template,
        actor=actor,
        purpose=draft.payload.purpose,
        query_sensitivity=draft.payload.query.sensitivity,
        now=now,
    )
    source_floor = require_sources_current(
        context,
        draft.payload.source_bindings,
        read_projection=False,
    )
    object_floor = require_scope_objects_current(
        context,
        draft.payload.scope_object_bindings,
        draft.payload.query,
        read_projection=False,
    )
    require_current_classification(
        draft.payload.classification,
        max(source_floor, object_floor),
        read_projection=False,
    )
    return draft


def require_revision(
    conn: sqlite3.Connection,
    runtime: WikiRuntime,
    actor: Principal,
    request: WikiCompileRequest,
    now: datetime,
) -> None:
    authorized = require_existing_head_access(conn, runtime, actor, request.page_id, now)
    if authorized is None and request.expected_page_revision != 0:
        raise AXError("wiki_page_not_found", 404)
    current_revision = 0 if authorized is None else authorized.head.revision
    if current_revision != request.expected_page_revision:
        raise AXError("wiki_page_revision_conflict", 409)
