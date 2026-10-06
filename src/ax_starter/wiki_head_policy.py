# pyright: reportAny=false
# SQLite rows are parsed into frozen contracts before leaving this policy module.
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import ValidationError

from ax_starter.common import AXError, Operation, Principal
from ax_starter.retrieval import content_hash
from ax_starter.wiki_contracts import WikiHeadState, WikiPage
from ax_starter.wiki_object_policy import (
    require_scope_object_access,
    require_scope_objects_current,
)
from ax_starter.wiki_runtime import WikiRuntime
from ax_starter.wiki_source_policy import (
    SourcePolicyContext,
    require_sources_access,
    require_sources_current,
)
from ax_starter.wiki_store import WikiHead, page_head

HeadRecompileReason = Literal[
    "source_changed", "object_changed", "head_stale", "classification_floor"
]


@dataclass(frozen=True, slots=True)
class AuthorizedHead:
    head: WikiHead
    page: WikiPage


def require_existing_head_access(
    conn: sqlite3.Connection,
    runtime: WikiRuntime,
    actor: Principal,
    page_id: str,
    now: datetime,
) -> AuthorizedHead | None:
    """Return an existing head only after historical and current access both pass."""
    head = page_head(conn, actor.tenant, page_id)
    if head is None:
        return None
    if head.state is WikiHeadState.SCRUBBED:
        raise AXError("wiki_page_not_found", 404)
    page = _stored_head_page(conn, actor.tenant, page_id, head)
    if (
        Operation.READ not in actor.operations
        or page.purpose not in actor.purposes
        or actor.clearance < max(page.classification, runtime.server_query_floor)
    ):
        raise AXError("wiki_page_not_found", 404)
    context = _context(conn, runtime, actor, page, now)
    source_floor = require_sources_access(context, page.source_bindings)
    object_floor = require_scope_object_access(context, page.scope_object_bindings, page.query)
    if actor.clearance < max(source_floor, object_floor, runtime.server_query_floor):
        raise AXError("wiki_page_not_found", 404)
    return AuthorizedHead(head=head, page=page)


def head_recompile_reason(
    conn: sqlite3.Connection,
    runtime: WikiRuntime,
    actor: Principal,
    authorized: AuthorizedHead,
    now: datetime,
) -> HeadRecompileReason | None:
    page = authorized.page
    if authorized.head.state is WikiHeadState.STALE:
        return "head_stale"
    if page.classification < runtime.server_query_floor:
        return "classification_floor"
    context = _context(conn, runtime, actor, page, now)
    source_reason = _source_recompile_reason(context, page)
    if source_reason is not None:
        return source_reason
    return _object_recompile_reason(context, page)


def _source_recompile_reason(
    context: SourcePolicyContext,
    page: WikiPage,
) -> Literal["source_changed"] | None:
    try:
        source_floor = require_sources_current(
            context,
            page.source_bindings,
            read_projection=True,
        )
    except AXError as exc:
        if exc.code == "wiki_page_not_found":
            return "source_changed"
        raise
    if page.classification < source_floor:
        return "source_changed"
    return None


def _object_recompile_reason(
    context: SourcePolicyContext,
    page: WikiPage,
) -> Literal["object_changed"] | None:
    try:
        object_floor = require_scope_objects_current(
            context,
            page.scope_object_bindings,
            page.query,
            read_projection=True,
        )
    except AXError as exc:
        if exc.code == "wiki_page_not_found":
            return "object_changed"
        raise
    if page.classification < object_floor:
        return "object_changed"
    return None


def managed_head_ids(conn: sqlite3.Connection, tenant: str) -> tuple[str, ...]:
    rows = conn.execute(
        """SELECT page_id FROM wiki_page_heads
        WHERE tenant = ? AND state != 'scrubbed' ORDER BY page_id""",
        (tenant,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _context(
    conn: sqlite3.Connection,
    runtime: WikiRuntime,
    actor: Principal,
    page: WikiPage,
    now: datetime,
) -> SourcePolicyContext:
    return SourcePolicyContext(
        conn=conn,
        store=runtime.store,
        template=runtime.template,
        actor=actor,
        purpose=page.purpose,
        query_sensitivity=page.query.sensitivity,
        now=now,
    )


def _stored_head_page(
    conn: sqlite3.Connection,
    tenant: str,
    page_id: str,
    head: WikiHead,
) -> WikiPage:
    row = conn.execute(
        """SELECT version_id, page_hash, data FROM wiki_page_versions
        WHERE tenant = ? AND page_id = ? AND revision = ?""",
        (tenant, page_id, head.revision),
    ).fetchone()
    if row is None or row[2] is None:
        raise AXError("wiki_page_not_found", 404)
    try:
        page = WikiPage.model_validate_json(str(row[2]))
    except ValidationError as exc:
        raise AXError("wiki_integrity_failure") from exc
    if (
        page.tenant != tenant
        or page.page_id != page_id
        or page.revision != head.revision
        or page.version_id != head.version_id
        or str(row[0]) != head.version_id
        or str(row[1]) != head.page_hash
        or content_hash(page.model_dump_json()) != head.page_hash
    ):
        raise AXError("wiki_integrity_failure")
    return page
