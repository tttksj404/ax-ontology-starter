from uuid import uuid4

from ax_starter.action_contracts import AuditEvent
from ax_starter.common import AXError
from ax_starter.retrieval import content_hash, retrieve
from ax_starter.wiki_compile_policy import (
    current_replay,
    require_revision,
    same_request,
)
from ax_starter.wiki_contracts import (
    WikiDraft,
    WikiDraftPayload,
    WikiDraftState,
)
from ax_starter.wiki_object_policy import build_scope_object_bindings
from ax_starter.wiki_policy import (
    current_principal,
    require_compilation_citations,
    require_compile_access,
    require_page_id,
)
from ax_starter.wiki_runtime import CompileCommand, WikiRuntime
from ax_starter.wiki_source_policy import (
    SourcePolicyContext,
    build_source_bindings,
)
from ax_starter.wiki_store import (
    WikiAuditRecord,
    append_audit,
    draft_by_request,
    request_hash,
    reviewed_payload_hash,
    save_draft,
)


def compile_wiki(runtime: WikiRuntime, command: CompileCommand) -> WikiDraft:
    request = command.request
    require_page_id(command.actor.tenant, request.page_id)
    for target in request.links:
        require_page_id(command.actor.tenant, target)
    request_sha256 = request_hash(request.model_dump_json())
    with runtime.store.transaction() as conn:
        actor = current_principal(
            command.actor, runtime.credential_guard, runtime.principal_resolver
        )
        _ = require_compile_access(actor, request.query)
        existing = draft_by_request(conn, actor.tenant, actor.subject, request.request_key)
        if existing is not None:
            replay_now = runtime.clock() if runtime.clock is not None else command.now
            replay = same_request(existing, request_sha256)
            return current_replay(conn, runtime, actor, replay, replay_now)
        require_revision(conn, runtime, actor, request, command.now)
        pack = runtime.store.current_pack(conn, runtime.template)
        raw_answer = retrieve(pack, actor, request.query, command.now)
        bindings, source_floor = build_source_bindings(
            SourcePolicyContext(
                conn=conn,
                store=runtime.store,
                template=runtime.template,
                actor=actor,
                purpose=request.query.purpose,
                query_sensitivity=request.query.sensitivity,
                now=command.now,
            ),
            raw_answer,
        )
        object_bindings, object_floor = build_scope_object_bindings(
            SourcePolicyContext(
                conn=conn,
                store=runtime.store,
                template=runtime.template,
                actor=actor,
                purpose=request.query.purpose,
                query_sensitivity=request.query.sensitivity,
                now=command.now,
            ),
            raw_answer,
            request.query,
        )
        if actor.clearance < max(runtime.server_query_floor, source_floor, object_floor):
            raise AXError("access_denied", 403)
    compilation = command.compiler(request, raw_answer)
    require_compilation_citations(compilation, raw_answer)
    post_now = runtime.clock() if runtime.clock is not None else command.now
    with runtime.store.transaction() as conn:
        actor = current_principal(
            command.actor, runtime.credential_guard, runtime.principal_resolver
        )
        proposer_person_id = require_compile_access(actor, request.query)
        existing = draft_by_request(conn, actor.tenant, actor.subject, request.request_key)
        if existing is not None:
            replay = same_request(existing, request_sha256)
            return current_replay(conn, runtime, actor, replay, post_now)
        require_revision(conn, runtime, actor, request, post_now)
        current_pack = runtime.store.current_pack(conn, runtime.template)
        current_answer = retrieve(current_pack, actor, request.query, post_now)
        try:
            current_bindings, current_floor = build_source_bindings(
                SourcePolicyContext(
                    conn=conn,
                    store=runtime.store,
                    template=runtime.template,
                    actor=actor,
                    purpose=request.query.purpose,
                    query_sensitivity=request.query.sensitivity,
                    now=post_now,
                ),
                current_answer,
            )
            current_object_bindings, current_object_floor = build_scope_object_bindings(
                SourcePolicyContext(
                    conn=conn,
                    store=runtime.store,
                    template=runtime.template,
                    actor=actor,
                    purpose=request.query.purpose,
                    query_sensitivity=request.query.sensitivity,
                    now=post_now,
                ),
                current_answer,
                request.query,
            )
        except AXError as exc:
            if exc.code == "wiki_source_required":
                raise AXError("wiki_source_stale", 409) from exc
            raise
        if (
            current_bindings != bindings
            or current_floor != source_floor
            or current_object_bindings != object_bindings
            or current_object_floor != object_floor
            or content_hash(current_answer.model_dump_json())
            != content_hash(raw_answer.model_dump_json())
        ):
            raise AXError("wiki_source_stale", 409)
        require_compilation_citations(compilation, current_answer)
        classification = max(
            runtime.server_query_floor,
            current_floor,
            current_object_floor,
            compilation.sensitivity,
        )
        if actor.clearance < classification:
            raise AXError("access_denied", 403)
        payload = WikiDraftPayload(
            tenant=actor.tenant,
            request_key=request.request_key,
            page_id=request.page_id,
            title=request.title,
            body=compilation.body,
            kind=request.kind,
            purpose=request.query.purpose,
            query=request.query,
            expected_page_revision=request.expected_page_revision,
            links=request.links,
            citations=compilation.citations,
            input_citations=current_answer.citations,
            source_bindings=current_bindings,
            scope_object_bindings=current_object_bindings,
            classification=classification,
            server_query_floor=runtime.server_query_floor,
            generation_route=compilation.generation_route,
            proposer=actor.subject,
            proposer_actor_kind=actor.actor_kind,
            proposer_person_id=proposer_person_id,
        )
        payload_hash = reviewed_payload_hash(payload, compilation.compiler_mode)
        draft = WikiDraft(
            id=str(uuid4()),
            request_key=request.request_key,
            request_sha256=request_sha256,
            payload=payload,
            payload_hash=payload_hash,
            compiler_mode=compilation.compiler_mode,
            state=WikiDraftState.DRAFT,
            created_at=post_now,
        )
        save_draft(conn, draft)
        append_audit(
            conn,
            WikiAuditRecord(
                tenant=actor.tenant,
                event="wiki.draft_compiled",
                reference=draft.id,
                payload_hash=draft.payload_hash,
                occurred_at=post_now,
            ),
        )
        runtime.store.append_audit(
            conn,
            AuditEvent(
                tenant=actor.tenant,
                actor=actor.subject,
                event="wiki.draft_compiled",
                reference=draft.id,
                payload_hash=draft.payload_hash,
                occurred_at=post_now,
            ),
        )
        return draft
