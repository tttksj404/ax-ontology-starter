import sqlite3
from datetime import datetime

from ax_starter.common import AXError, Operation, Principal, Purpose
from ax_starter.wiki_contracts import WikiDraft, WikiIndexEntry, WikiPage
from ax_starter.wiki_object_policy import require_scope_objects_current
from ax_starter.wiki_policy import (
    current_principal,
    current_proposer,
    require_compile_access,
    require_current_classification,
    require_page_id,
    require_read_access,
    require_reviewer,
)
from ax_starter.wiki_runtime import WikiRuntime
from ax_starter.wiki_source_policy import SourcePolicyContext, require_sources_current
from ax_starter.wiki_store import current_page, draft_record, page_ids


def view_wiki_draft(
    runtime: WikiRuntime, actor: Principal, draft_id: str, now: datetime
) -> WikiDraft:
    with runtime.store.transaction() as conn:
        current = current_principal(actor, runtime.credential_guard, runtime.principal_resolver)
        draft = draft_record(conn, current.tenant, draft_id)
        _require_draft_access(runtime, current, draft)
        if current.clearance < draft.payload.classification:
            raise AXError("wiki_draft_not_found", 404)
        require_current_classification(
            draft.payload.classification,
            runtime.server_query_floor,
            read_projection=False,
        )
        try:
            source_floor = require_sources_current(
                SourcePolicyContext(
                    conn=conn,
                    store=runtime.store,
                    template=runtime.template,
                    actor=current,
                    purpose=draft.payload.purpose,
                    query_sensitivity=draft.payload.query.sensitivity,
                    now=now,
                ),
                draft.payload.source_bindings,
                read_projection=True,
            )
            object_floor = require_scope_objects_current(
                SourcePolicyContext(
                    conn=conn,
                    store=runtime.store,
                    template=runtime.template,
                    actor=current,
                    purpose=draft.payload.purpose,
                    query_sensitivity=draft.payload.query.sensitivity,
                    now=now,
                ),
                draft.payload.scope_object_bindings,
                draft.payload.query,
                read_projection=True,
            )
            require_current_classification(
                draft.payload.classification,
                max(source_floor, object_floor),
                read_projection=False,
            )
        except AXError as exc:
            if exc.code == "wiki_page_not_found":
                raise AXError("wiki_draft_not_found", 404) from exc
            raise
        return draft


def _require_draft_access(
    runtime: WikiRuntime,
    actor: Principal,
    draft: WikiDraft,
) -> None:
    payload = draft.payload
    if actor.subject == payload.proposer:
        if (
            actor.actor_kind is not payload.proposer_actor_kind
            or actor.effective_person_id != payload.proposer_person_id
        ):
            raise AXError("wiki_proposer_identity_changed", 409)
        _ = require_compile_access(actor, payload.query)
        return
    proposer = current_proposer(
        payload.proposer,
        payload.proposer_actor_kind,
        payload.proposer_person_id,
        payload.tenant,
        runtime.principal_resolver,
    )
    _ = require_compile_access(proposer, payload.query)
    if Operation.MANAGE_KNOWLEDGE in actor.operations:
        _ = require_compile_access(actor, payload.query)
        return
    require_read_access(actor, payload.purpose)
    _ = require_reviewer(actor, proposer)


def read_wiki_page(
    runtime: WikiRuntime,
    actor: Principal,
    page_id: str,
    purpose: Purpose,
    now: datetime,
) -> WikiPage:
    require_page_id(actor.tenant, page_id)
    with runtime.store.transaction() as conn:
        current = current_principal(actor, runtime.credential_guard, runtime.principal_resolver)
        require_read_access(current, purpose)
        pages = visible_pages(conn, runtime, current, purpose, now)
        page = pages.get(page_id)
        if page is None:
            raise AXError("wiki_page_not_found", 404)
        visible_ids = frozenset(pages)
        return page.model_copy(
            update={"links": tuple(target for target in page.links if target in visible_ids)}
        )


def index_wiki(
    runtime: WikiRuntime,
    actor: Principal,
    purpose: Purpose,
    now: datetime,
) -> tuple[WikiIndexEntry, ...]:
    with runtime.store.transaction() as conn:
        current = current_principal(actor, runtime.credential_guard, runtime.principal_resolver)
        require_read_access(current, purpose)
        pages = visible_pages(conn, runtime, current, purpose, now)
        visible_ids = frozenset(pages)
        entries: list[WikiIndexEntry] = []
        for page_id, page in pages.items():
            links = tuple(target for target in page.links if target in visible_ids)
            backlinks = tuple(
                source_id
                for source_id, source in pages.items()
                if page_id in source.links and source_id in visible_ids
            )
            entries.append(
                WikiIndexEntry(
                    page_id=page_id,
                    title=page.title,
                    kind=page.kind,
                    revision=page.revision,
                    classification=page.classification,
                    links=links,
                    backlinks=backlinks,
                )
            )
        return tuple(entries)


def visible_pages(
    conn: sqlite3.Connection,
    runtime: WikiRuntime,
    actor: Principal,
    purpose: Purpose,
    now: datetime,
) -> dict[str, WikiPage]:
    pages: dict[str, WikiPage] = {}
    for page_id in page_ids(conn, actor.tenant):
        page = current_page(conn, actor.tenant, page_id)
        if page.purpose != purpose or actor.clearance < page.classification:
            continue
        try:
            require_current_classification(
                page.classification,
                runtime.server_query_floor,
                read_projection=True,
            )
            source_floor = require_sources_current(
                SourcePolicyContext(
                    conn=conn,
                    store=runtime.store,
                    template=runtime.template,
                    actor=actor,
                    purpose=purpose,
                    query_sensitivity=page.query.sensitivity,
                    now=now,
                ),
                page.source_bindings,
                read_projection=True,
            )
            object_floor = require_scope_objects_current(
                SourcePolicyContext(
                    conn=conn,
                    store=runtime.store,
                    template=runtime.template,
                    actor=actor,
                    purpose=purpose,
                    query_sensitivity=page.query.sensitivity,
                    now=now,
                ),
                page.scope_object_bindings,
                page.query,
                read_projection=True,
            )
            require_current_classification(
                page.classification,
                max(source_floor, object_floor),
                read_projection=True,
            )
        except AXError as exc:
            if exc.code == "wiki_page_not_found":
                continue
            raise
        pages[page_id] = page
    return pages
