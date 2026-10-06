import hashlib
import re
from datetime import datetime
from typing import Final, Literal
from unicodedata import normalize

from pydantic import Field

from ax_starter.common import (
    AXError,
    Contract,
    Identifier,
    Operation,
    Principal,
    Purpose,
    Sensitivity,
)
from ax_starter.ontology import Document, DomainPack, Entity
from ax_starter.policy import visible

MAX_SCOPE_NODES: Final = 100
MAX_NEIGHBORS_PER_HOP: Final = 50


class Query(Contract):
    question: str = Field(min_length=2, max_length=2000)
    purpose: Purpose = Purpose.OPERATIONS
    object_id: Identifier | None = None
    top_k: int = Field(default=4, ge=1, le=10)
    hops: int = Field(default=1, ge=0, le=2)
    sensitivity: Sensitivity = Sensitivity.CONFIDENTIAL
    generate: bool = False


class Citation(Contract):
    document_id: str
    title: str
    source_uri: str
    source_version: str
    content_sha256: str
    access_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    object_ids: tuple[str, ...]
    quote: str
    sensitivity: Sensitivity


class Answer(Contract):
    mode: Literal["extractive", "model_draft", "abstain"]
    text: str
    citations: tuple[Citation, ...]
    object_ids: tuple[str, ...]
    requires_review: bool
    sensitivity: Sensitivity = Sensitivity.RESTRICTED
    retrieval_strategy: Literal["keyword-and-authorized-graph"] = "keyword-and-authorized-graph"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authorized_objects(
    pack: DomainPack, principal: Principal, purpose: Purpose
) -> tuple[Entity, ...]:
    if Operation.READ not in principal.operations or purpose not in principal.purposes:
        raise AXError("access_denied", 403)
    return tuple(entity for entity in pack.objects if visible(principal, entity.access, purpose))


def scope_ids(pack: DomainPack, principal: Principal, query: Query) -> frozenset[str]:
    accessible = {entity.id for entity in authorized_objects(pack, principal, query.purpose)}
    if query.object_id is None:
        return frozenset(accessible)
    if query.object_id not in accessible:
        raise AXError("object_not_found", 404)
    scope = {query.object_id}
    for _ in range(query.hops):
        neighbors: set[str] = set()
        for link in pack.links:
            if not visible(principal, link.access, query.purpose):
                continue
            if {link.source_id, link.target_id} <= accessible and (
                link.source_id in scope or link.target_id in scope
            ):
                neighbors.update((link.source_id, link.target_id))
        new_nodes = neighbors - scope
        if len(new_nodes) > MAX_NEIGHBORS_PER_HOP:
            raise AXError("graph_fanout_limit", 413)
        scope.update(new_nodes)
        if len(scope) > MAX_SCOPE_NODES:
            raise AXError("graph_scope_limit", 413)
    return frozenset(scope)


def evidence_documents(
    pack: DomainPack, principal: Principal, query: Query, now: datetime
) -> tuple[Document, ...]:
    scope = scope_ids(pack, principal, query)
    return tuple(
        doc
        for doc in pack.documents
        if visible(principal, doc.access, query.purpose)
        and doc.valid_until > now
        and set(doc.object_ids) <= scope
    )


def context_sensitivity(pack: DomainPack, principal: Principal, query: Query) -> Sensitivity:
    if query.object_id is None:
        return query.sensitivity
    scope = scope_ids(pack, principal, query)
    labels = [query.sensitivity]
    labels.extend(entity.access.sensitivity for entity in pack.objects if entity.id in scope)
    if query.hops:
        labels.extend(
            link.access.sensitivity
            for link in pack.links
            if {link.source_id, link.target_id} <= scope
            and visible(principal, link.access, query.purpose)
        )
    return max(labels)


def retrieve(pack: DomainPack, principal: Principal, query: Query, now: datetime) -> Answer:
    terms = frozenset(
        match.group()
        for match in re.finditer(r"[\w]+", normalize("NFC", query.question).casefold())
    )
    docs = evidence_documents(pack, principal, query, now)
    scored = [
        (sum(term in normalize("NFC", f"{doc.title} {doc.text}").casefold() for term in terms), doc)
        for doc in docs
    ]
    selected = sorted(
        (pair for pair in scored if pair[0] > 0), key=lambda pair: (-pair[0], pair[1].id)
    )[: query.top_k]
    citations = tuple(
        Citation(
            document_id=doc.id,
            title=doc.title,
            source_uri=doc.source_uri,
            source_version=doc.source_version,
            content_sha256=content_hash(doc.text),
            access_sha256=content_hash(doc.access.model_dump_json()),
            object_ids=doc.object_ids,
            quote=doc.text,
            sensitivity=doc.access.sensitivity,
        )
        for _, doc in selected
    )
    sensitivity = max(
        query.sensitivity,
        context_sensitivity(pack, principal, query),
        *(cite.sensitivity for cite in citations),
    )
    if not citations:
        return Answer(
            mode="abstain",
            text="권한과 유효기간을 충족하는 근거를 찾지 못했습니다.",
            citations=(),
            object_ids=(),
            requires_review=True,
            sensitivity=sensitivity,
        )
    return Answer(
        mode="extractive",
        text="\n\n".join(f"[{cite.document_id}] {cite.quote}" for cite in citations),
        citations=citations,
        object_ids=tuple(sorted({key for cite in citations for key in cite.object_ids})),
        requires_review=False,
        sensitivity=sensitivity,
    )
