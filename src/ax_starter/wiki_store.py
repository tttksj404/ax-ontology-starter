# pyright: reportAny=false
# SQLite rows are parsed into frozen contracts before leaving this module.
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from ax_starter.common import AXError
from ax_starter.retrieval import content_hash
from ax_starter.wiki_contracts import (
    WikiDraft,
    WikiDraftPayload,
    WikiDraftState,
    WikiHeadState,
    WikiPage,
)


@dataclass(frozen=True, slots=True)
class WikiHead:
    revision: int
    version_id: str
    page_hash: str
    state: WikiHeadState


@dataclass(frozen=True, slots=True)
class WikiAuditRecord:
    tenant: str
    event: str
    reference: str
    payload_hash: str
    occurred_at: datetime


def reviewed_payload_hash(payload: WikiDraftPayload, compiler_mode: str) -> str:
    return content_hash(payload.model_dump_json() + "\n" + compiler_mode)


def request_hash(request_json: str) -> str:
    return content_hash(request_json)


def draft_by_request(
    conn: sqlite3.Connection, tenant: str, proposer: str, request_key: str
) -> WikiDraft | None:
    row = conn.execute(
        """SELECT draft_id, page_id, request_sha256, payload_hash, state, data, created_at
        FROM wiki_drafts WHERE tenant = ? AND proposer = ? AND request_key = ?""",
        (tenant, proposer, request_key),
    ).fetchone()
    if row is None:
        return None
    if str(row[4]) in (WikiDraftState.STALE, WikiDraftState.SCRUBBED) or row[5] is None:
        raise AXError("wiki_source_stale", 409)
    return _parse_draft(row, tenant, proposer, request_key)


def draft_record(conn: sqlite3.Connection, tenant: str, draft_id: str) -> WikiDraft:
    row = conn.execute(
        """SELECT draft_id, page_id, request_sha256, payload_hash, state, data, created_at,
        proposer, request_key FROM wiki_drafts WHERE tenant = ? AND draft_id = ?""",
        (tenant, draft_id),
    ).fetchone()
    if row is None or str(row[4]) in (WikiDraftState.STALE, WikiDraftState.SCRUBBED):
        raise AXError("wiki_draft_not_found", 404)
    if row[5] is None:
        raise AXError("wiki_draft_not_found", 404)
    normalized = row[:7]
    return _parse_draft(normalized, tenant, str(row[7]), str(row[8]))


def save_draft(conn: sqlite3.Connection, draft: WikiDraft) -> None:
    _ = conn.execute(
        """INSERT INTO wiki_drafts
        (tenant, draft_id, page_id, proposer, request_key, request_sha256, payload_hash,
        state, data, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            draft.payload.tenant,
            draft.id,
            draft.payload.page_id,
            draft.payload.proposer,
            draft.request_key,
            draft.request_sha256,
            draft.payload_hash,
            draft.state.value,
            draft.model_dump_json(),
            draft.created_at.isoformat(),
        ),
    )
    _ = conn.executemany(
        "INSERT INTO wiki_draft_sources VALUES (?, ?, ?)",
        [
            (draft.payload.tenant, draft.id, binding.document_id)
            for binding in draft.payload.source_bindings
        ],
    )


def page_head(conn: sqlite3.Connection, tenant: str, page_id: str) -> WikiHead | None:
    row = conn.execute(
        """SELECT revision, version_id, page_hash, state FROM wiki_page_heads
        WHERE tenant = ? AND page_id = ?""",
        (tenant, page_id),
    ).fetchone()
    if row is None:
        return None
    try:
        state = WikiHeadState(str(row[3]))
    except ValueError as exc:
        raise AXError("wiki_integrity_failure") from exc
    return WikiHead(
        revision=int(row[0]),
        version_id=str(row[1]),
        page_hash=str(row[2]),
        state=state,
    )


def current_page(conn: sqlite3.Connection, tenant: str, page_id: str) -> WikiPage:
    head = page_head(conn, tenant, page_id)
    if head is None or head.state is not WikiHeadState.PUBLISHED:
        raise AXError("wiki_page_not_found", 404)
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
    calculated = content_hash(page.model_dump_json())
    if (
        page.tenant != tenant
        or page.page_id != page_id
        or page.revision != head.revision
        or page.version_id != head.version_id
        or str(row[0]) != head.version_id
        or str(row[1]) != head.page_hash
        or calculated != head.page_hash
    ):
        raise AXError("wiki_integrity_failure")
    return page


def save_page(
    conn: sqlite3.Connection, draft: WikiDraft, page: WikiPage, now: datetime
) -> WikiDraft:
    page_hash = content_hash(page.model_dump_json())
    _ = conn.execute(
        "INSERT INTO wiki_page_versions VALUES (?, ?, ?, ?, ?, ?)",
        (
            page.tenant,
            page.page_id,
            page.revision,
            page.version_id,
            page_hash,
            page.model_dump_json(),
        ),
    )
    _ = conn.execute(
        """INSERT INTO wiki_page_heads VALUES (?, ?, ?, ?, ?, 'published')
        ON CONFLICT(tenant, page_id) DO UPDATE SET revision = excluded.revision,
        version_id = excluded.version_id, page_hash = excluded.page_hash, state = excluded.state""",
        (page.tenant, page.page_id, page.revision, page.version_id, page_hash),
    )
    _ = conn.executemany(
        "INSERT INTO wiki_page_sources VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                page.tenant,
                page.page_id,
                page.revision,
                source.document_id,
                source.document_sha256,
                source.content_sha256,
                source.access_sha256,
            )
            for source in page.source_bindings
        ],
    )
    _ = conn.executemany(
        "INSERT INTO wiki_links VALUES (?, ?, ?, ?)",
        [(page.tenant, page.page_id, page.revision, target) for target in page.links],
    )
    published = draft.model_copy(
        update={
            "state": WikiDraftState.PUBLISHED,
            "published_revision": page.revision,
            "reviewer": page.reviewer,
            "reviewer_person_id": page.reviewer_person_id,
        }
    )
    _ = conn.execute(
        """UPDATE wiki_drafts SET state = 'published', data = ?, reviewer = ?,
        reviewer_person_id = ?, published_revision = ?
        WHERE tenant = ? AND draft_id = ?""",
        (
            published.model_dump_json(),
            page.reviewer,
            page.reviewer_person_id,
            page.revision,
            page.tenant,
            draft.id,
        ),
    )
    append_audit(
        conn,
        WikiAuditRecord(
            tenant=page.tenant,
            event="wiki.page_published",
            reference=page.page_id,
            payload_hash=page_hash,
            occurred_at=now,
        ),
    )
    return published


def page_ids(conn: sqlite3.Connection, tenant: str) -> tuple[str, ...]:
    rows = conn.execute(
        """SELECT page_id FROM wiki_page_heads
        WHERE tenant = ? AND state = 'published' ORDER BY page_id""",
        (tenant,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def append_audit(
    conn: sqlite3.Connection,
    record: WikiAuditRecord,
) -> None:
    _ = conn.execute(
        """INSERT INTO wiki_audit (tenant, event, reference, payload_hash, occurred_at)
        VALUES (?, ?, ?, ?, ?)""",
        (
            record.tenant,
            record.event,
            record.reference,
            record.payload_hash,
            record.occurred_at.isoformat(),
        ),
    )


def _parse_draft(
    row: sqlite3.Row | tuple[str, ...], tenant: str, proposer: str, request_key: str
) -> WikiDraft:
    try:
        draft = WikiDraft.model_validate_json(str(row[5]))
    except ValidationError as exc:
        raise AXError("wiki_integrity_failure") from exc
    expected_hash = reviewed_payload_hash(draft.payload, draft.compiler_mode)
    if (
        draft.id != str(row[0])
        or draft.payload.tenant != tenant
        or draft.payload.page_id != str(row[1])
        or draft.payload.proposer != proposer
        or draft.request_key != request_key
        or draft.request_sha256 != str(row[2])
        or draft.payload_hash != str(row[3])
        or draft.payload_hash != expected_hash
        or draft.state.value != str(row[4])
    ):
        raise AXError("wiki_integrity_failure")
    return draft
