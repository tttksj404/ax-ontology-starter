import re
from typing import Final
from unicodedata import normalize

from ax_starter.retrieval import Citation, Query
from ax_starter.wiki_contracts import WikiPage

MAX_WIKI_CITATIONS: Final = 10


def select_pages(
    pages: tuple[WikiPage, ...], query: Query, scope: frozenset[str]
) -> tuple[WikiPage, ...]:
    terms = frozenset(
        match.group()
        for match in re.finditer(r"[\w]+", normalize("NFC", query.question).casefold())
    )
    scored = (
        (
            sum(term in normalize("NFC", f"{page.title} {page.body}").casefold() for term in terms),
            page,
        )
        for page in pages
        if all(set(binding.object_ids) <= scope for binding in page.source_bindings)
        and {binding.object_id for binding in page.scope_object_bindings} <= scope
    )
    selected: list[WikiPage] = []
    citation_keys: set[tuple[str, str]] = set()
    for score, page in sorted(scored, key=lambda pair: (-pair[0], pair[1].page_id)):
        if score == 0:
            continue
        keys = {(cite.document_id, cite.content_sha256) for cite in page.citations}
        if len(citation_keys | keys) > MAX_WIKI_CITATIONS:
            continue
        selected.append(page)
        citation_keys.update(keys)
        if len(selected) == query.top_k:
            break
    return tuple(selected)


def flatten_citations(
    pages: tuple[WikiPage, ...], raw: tuple[Citation, ...]
) -> tuple[Citation, ...]:
    # Reviewed page quotes retain priority; extra current raw results fill the remaining budget.
    ordered = (*(citation for page in pages for citation in page.citations), *raw)
    seen: set[tuple[str, str]] = set()
    citations: list[Citation] = []
    for citation in ordered:
        key = (citation.document_id, citation.content_sha256)
        if key not in seen:
            seen.add(key)
            citations.append(citation)
        if len(citations) == MAX_WIKI_CITATIONS:
            break
    return tuple(citations)
