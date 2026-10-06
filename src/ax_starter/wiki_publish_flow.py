from datetime import datetime
from uuid import uuid4

from ax_starter.action_contracts import AuditEvent
from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.retrieval import content_hash
from ax_starter.wiki_contracts import WikiDraftState, WikiPage
from ax_starter.wiki_head_policy import require_existing_head_access
from ax_starter.wiki_object_policy import require_scope_objects_current
from ax_starter.wiki_policy import (
    current_principal,
    current_proposer,
    require_compile_access,
    require_current_classification,
    require_read_access,
    require_reviewer,
)
from ax_starter.wiki_runtime import WikiRuntime
from ax_starter.wiki_source_policy import SourcePolicyContext, require_sources_current
from ax_starter.wiki_store import current_page, draft_record, save_page


def publish_wiki(
    runtime: WikiRuntime,
    actor: Principal,
    draft_id: str,
    reviewed_payload_hash: str,
    fallback_now: datetime,
) -> WikiPage:
    publish_now = runtime.clock() if runtime.clock is not None else fallback_now
    with runtime.store.transaction() as conn:
        reviewer = current_principal(actor, runtime.credential_guard, runtime.principal_resolver)
        draft = draft_record(conn, reviewer.tenant, draft_id)
        payload = draft.payload
        require_read_access(reviewer, payload.purpose)
        proposer = current_proposer(
            payload.proposer,
            payload.proposer_actor_kind,
            payload.proposer_person_id,
            payload.tenant,
            runtime.principal_resolver,
        )
        _ = require_compile_access(proposer, payload.query)
        reviewer_person_id = require_reviewer(reviewer, proposer)
        _require_page_clearance(proposer, payload.classification)
        _require_page_clearance(reviewer, payload.classification)
        proposer_head = require_existing_head_access(
            conn, runtime, proposer, payload.page_id, publish_now
        )
        reviewer_head = require_existing_head_access(
            conn, runtime, reviewer, payload.page_id, publish_now
        )
        if (proposer_head is None) != (reviewer_head is None):
            raise AXError("wiki_integrity_failure")
        if (
            proposer_head is not None
            and reviewer_head is not None
            and proposer_head.head != reviewer_head.head
        ):
            raise AXError("wiki_integrity_failure")
        require_current_classification(
            payload.classification,
            runtime.server_query_floor,
            read_projection=False,
        )
        proposer_floor = require_sources_current(
            SourcePolicyContext(
                conn=conn,
                store=runtime.store,
                template=runtime.template,
                actor=proposer,
                purpose=payload.purpose,
                query_sensitivity=payload.query.sensitivity,
                now=publish_now,
            ),
            payload.source_bindings,
            read_projection=True,
        )
        reviewer_floor = require_sources_current(
            SourcePolicyContext(
                conn=conn,
                store=runtime.store,
                template=runtime.template,
                actor=reviewer,
                purpose=payload.purpose,
                query_sensitivity=payload.query.sensitivity,
                now=publish_now,
            ),
            payload.source_bindings,
            read_projection=False,
        )
        proposer_object_floor = require_scope_objects_current(
            SourcePolicyContext(
                conn=conn,
                store=runtime.store,
                template=runtime.template,
                actor=proposer,
                purpose=payload.purpose,
                query_sensitivity=payload.query.sensitivity,
                now=publish_now,
            ),
            payload.scope_object_bindings,
            payload.query,
            read_projection=False,
        )
        reviewer_object_floor = require_scope_objects_current(
            SourcePolicyContext(
                conn=conn,
                store=runtime.store,
                template=runtime.template,
                actor=reviewer,
                purpose=payload.purpose,
                query_sensitivity=payload.query.sensitivity,
                now=publish_now,
            ),
            payload.scope_object_bindings,
            payload.query,
            read_projection=True,
        )
        require_current_classification(
            payload.classification,
            max(
                proposer_floor,
                reviewer_floor,
                proposer_object_floor,
                reviewer_object_floor,
            ),
            read_projection=False,
        )
        if reviewed_payload_hash != draft.payload_hash:
            raise AXError("wiki_review_hash_mismatch", 409)
        head = None if proposer_head is None else proposer_head.head
        if draft.state is WikiDraftState.PUBLISHED:
            if draft.reviewer != reviewer.subject or draft.reviewer_person_id != reviewer_person_id:
                raise AXError("wiki_review_owner_mismatch", 403)
            if draft.published_revision is None or head is None:
                raise AXError("wiki_integrity_failure")
            if head.revision != draft.published_revision:
                raise AXError("wiki_publish_replay_superseded", 409)
            page = current_page(conn, payload.tenant, payload.page_id)
            if page.payload_hash != draft.payload_hash:
                raise AXError("wiki_integrity_failure")
            return page
        revision = 0 if head is None else head.revision
        if revision != payload.expected_page_revision:
            raise AXError("wiki_page_revision_conflict", 409)
        page = WikiPage(
            tenant=payload.tenant,
            request_key=payload.request_key,
            page_id=payload.page_id,
            version_id=str(uuid4()),
            revision=revision + 1,
            title=payload.title,
            body=payload.body,
            kind=payload.kind,
            purpose=payload.purpose,
            query=payload.query,
            expected_page_revision=payload.expected_page_revision,
            links=payload.links,
            citations=payload.citations,
            input_citations=payload.input_citations,
            source_bindings=payload.source_bindings,
            scope_object_bindings=payload.scope_object_bindings,
            classification=payload.classification,
            server_query_floor=payload.server_query_floor,
            compiler_mode=draft.compiler_mode,
            generation_route=payload.generation_route,
            payload_hash=draft.payload_hash,
            proposer=payload.proposer,
            proposer_person_id=payload.proposer_person_id,
            reviewer=reviewer.subject,
            reviewer_person_id=reviewer_person_id,
            published_at=publish_now,
        )
        page_hash = content_hash(page.model_dump_json())
        _ = save_page(conn, draft, page, publish_now)
        runtime.store.append_audit(
            conn,
            AuditEvent(
                tenant=page.tenant,
                actor=reviewer.subject,
                event="wiki.page_published",
                reference=page.page_id,
                payload_hash=page_hash,
                occurred_at=publish_now,
            ),
        )
        return page


def _require_page_clearance(actor: Principal, classification: Sensitivity) -> None:
    if actor.clearance < classification:
        raise AXError("access_denied", 403)
