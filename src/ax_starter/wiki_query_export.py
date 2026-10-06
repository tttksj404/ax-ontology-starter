import re
from datetime import datetime
from typing import Final

from ax_starter.common import AXError, Operation, Principal, Purpose
from ax_starter.evidence_roles import DERIVED_WIKI_MARKER
from ax_starter.retrieval import Answer, Query, content_hash, retrieve, scope_ids
from ax_starter.wiki_contracts import (
    WikiAnswer,
    WikiExport,
    WikiExportManifest,
    WikiExportSource,
    WikiLintFinding,
    WikiPage,
    WikiPageHit,
)
from ax_starter.wiki_head_policy import (
    head_recompile_reason,
    managed_head_ids,
    require_existing_head_access,
)
from ax_starter.wiki_policy import current_principal, require_page_id, require_read_access
from ax_starter.wiki_query_policy import flatten_citations, select_pages
from ax_starter.wiki_reads import visible_pages
from ax_starter.wiki_runtime import WikiRuntime

_HTML_PATTERN: Final = re.compile(r"<[A-Za-z][^>]*>")
_IMAGE_PATTERN: Final = re.compile(r"!\[")


def query_wiki(runtime: WikiRuntime, actor: Principal, query: Query, now: datetime) -> WikiAnswer:
    if query.generate:
        raise AXError("wiki_query_generation_not_supported", 422)
    with runtime.store.transaction() as conn:
        current = current_principal(actor, runtime.credential_guard, runtime.principal_resolver)
        require_read_access(current, query.purpose)
        pack = runtime.store.current_pack(conn, runtime.template)
        raw = retrieve(pack, current, query, now)
        pages = visible_pages(conn, runtime, current, query.purpose, now)
        selected = select_pages(tuple(pages.values()), query, scope_ids(pack, current, query))
        if not selected:
            return WikiAnswer(
                pages=(),
                answer=raw.model_copy(
                    update={"sensitivity": max(raw.sensitivity, runtime.server_query_floor)}
                ),
            )
        hits = tuple(
            WikiPageHit(
                page_id=page.page_id,
                title=page.title,
                excerpt=page.body[:240],
                revision=page.revision,
                classification=page.classification,
                source_bindings=page.source_bindings,
                input_citations=page.input_citations,
            )
            for page in selected
        )
        citations = flatten_citations(selected, raw.citations)
        sensitivity = max(
            runtime.server_query_floor,
            raw.sensitivity,
            *(page.classification for page in selected),
            *(citation.sensitivity for citation in citations),
        )
        answer = Answer(
            mode="model_draft",
            text="\n\n".join(
                (
                    *(_page_text(page) for page in selected),
                    *(f"[{cite.document_id}] {cite.quote}" for cite in citations),
                )
            ),
            citations=citations,
            object_ids=tuple(
                sorted({object_id for citation in citations for object_id in citation.object_ids})
            ),
            requires_review=True,
            sensitivity=sensitivity,
        )
        return WikiAnswer(pages=hits, answer=answer)


def lint_wiki(
    runtime: WikiRuntime, actor: Principal, purpose: Purpose, now: datetime
) -> tuple[WikiLintFinding, ...]:
    with runtime.store.transaction() as conn:
        current = current_principal(actor, runtime.credential_guard, runtime.principal_resolver)
        require_read_access(current, purpose)
        if Operation.MANAGE_KNOWLEDGE not in current.operations:
            raise AXError("access_denied", 403)
        findings: list[WikiLintFinding] = []
        for page_id in managed_head_ids(conn, current.tenant):
            try:
                authorized = require_existing_head_access(conn, runtime, current, page_id, now)
            except AXError as exc:
                if exc.code == "wiki_page_not_found":
                    continue
                raise
            if authorized is None or authorized.page.purpose != purpose:
                continue
            reason = head_recompile_reason(conn, runtime, current, authorized, now)
            if reason is None:
                continue
            code = "source_changed" if reason == "source_changed" else "recompile_required"
            findings.append(
                WikiLintFinding(
                    page_id=page_id,
                    revision=authorized.head.revision,
                    state=authorized.head.state,
                    code=code,
                    reason=reason,
                )
            )
        return tuple(findings)


def export_wiki(
    runtime: WikiRuntime,
    actor: Principal,
    page_id: str,
    purpose: Purpose,
    now: datetime,
) -> WikiExport:
    require_page_id(actor.tenant, page_id)
    with runtime.store.transaction() as conn:
        current = current_principal(actor, runtime.credential_guard, runtime.principal_resolver)
        require_read_access(current, purpose)
        pages = visible_pages(conn, runtime, current, purpose, now)
        page = pages.get(page_id)
        if page is None:
            raise AXError("wiki_page_not_found", 404)
        _require_safe_markdown(page)
        manifest = WikiExportManifest(
            tenant=page.tenant,
            page_id=page.page_id,
            page_revision=page.revision,
            page_hash=content_hash(page.model_dump_json()),
            purpose=purpose,
            classification=page.classification,
            generation_route=page.generation_route,
            sources=tuple(
                WikiExportSource(
                    document_id=source.document_id,
                    document_sha256=source.document_sha256,
                    content_sha256=source.content_sha256,
                    access_sha256=source.access_sha256,
                )
                for source in page.source_bindings
            ),
            exported_at=now,
            expires_at=min(source.valid_until for source in page.source_bindings),
            caller_fingerprint=content_hash(current.model_dump_json()),
        )
        source_lines = "\n".join(
            f"- `{citation.document_id}` ({citation.source_version})" for citation in page.citations
        )
        text = (
            f"{DERIVED_WIKI_MARKER}\n\n# {page.title}\n\n{page.body}\n\n"
            f"## Sources\n\n{source_lines}\n"
        )
        return WikiExport(text=text, manifest=manifest)


def _require_safe_markdown(page: WikiPage) -> None:
    combined = f"{page.title}\n{page.body}"
    if _HTML_PATTERN.search(combined) or _IMAGE_PATTERN.search(combined):
        raise AXError("wiki_export_unsafe_markup", 422)


def _page_text(page: WikiPage) -> str:
    return f"[wiki:{page.page_id}@{page.revision}] {page.body}"
