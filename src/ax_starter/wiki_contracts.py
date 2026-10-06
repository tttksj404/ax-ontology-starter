from collections.abc import Callable
from enum import StrEnum
from typing import Final, Literal, Protocol, Self

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import Access, ActorKind, Contract, Identifier, Purpose, Sensitivity
from ax_starter.retrieval import Answer, Citation, Query

MAX_WIKI_SCOPE_OBJECTS: Final = 100


class WikiKind(StrEnum):
    SOURCE = "source"
    ENTITY = "entity"
    CONCEPT = "concept"
    SYNTHESIS = "synthesis"
    PROCEDURE = "procedure"


class WikiDraftState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    STALE = "stale"
    SCRUBBED = "scrubbed"


class WikiHeadState(StrEnum):
    PUBLISHED = "published"
    STALE = "stale"
    SCRUBBED = "scrubbed"


class WikiCompileRequest(Contract):
    request_key: Identifier
    page_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    kind: WikiKind
    query: Query
    expected_page_revision: int = Field(default=0, ge=0)
    links: tuple[Identifier, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def links_must_be_unique(self) -> Self:
        if len(set(self.links)) != len(self.links):
            raise PydanticCustomError("duplicate_wiki_link", "wiki links must be unique")
        return self


class WikiGenerationRoute(Contract):
    mode: Literal["local", "private_gateway", "cloud_gateway"]
    endpoint_host: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=120)
    provider_settings_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class WikiCompilation(Contract):
    body: str = Field(min_length=1, max_length=8_000)
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=10)
    compiler_mode: Literal["offline_extractive", "model_draft"]
    sensitivity: Sensitivity
    generation_route: WikiGenerationRoute | None = None

    @model_validator(mode="after")
    def route_matches_compiler_mode(self) -> Self:
        route_required = self.compiler_mode == "model_draft"
        if route_required != (self.generation_route is not None):
            raise PydanticCustomError(
                "wiki_generation_route_invalid",
                "generation route must be present exactly for model drafts",
            )
        return self


class WikiCompiler(Protocol):
    def __call__(self, request: WikiCompileRequest, answer: Answer) -> WikiCompilation: ...


WikiCompilerCallable = Callable[[WikiCompileRequest, Answer], WikiCompilation]


class WikiSourceBinding(Contract):
    document_id: Identifier
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_identifier: Identifier
    source_version: Identifier
    object_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    access_snapshot: Access
    valid_until: AwareDatetime
    contract_id: Identifier | None = None
    contract_version: Identifier | None = None
    contract_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class WikiObjectBinding(Contract):
    object_id: Identifier
    object_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_snapshot: Access


class WikiDraftPayload(Contract):
    tenant: Identifier
    request_key: Identifier
    page_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8_000)
    kind: WikiKind
    purpose: Purpose
    query: Query
    expected_page_revision: int = Field(ge=0)
    links: tuple[Identifier, ...] = Field(max_length=20)
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=10)
    input_citations: tuple[Citation, ...] = Field(min_length=1, max_length=10)
    source_bindings: tuple[WikiSourceBinding, ...] = Field(min_length=1, max_length=10)
    scope_object_bindings: tuple[WikiObjectBinding, ...] = Field(
        min_length=1,
        max_length=MAX_WIKI_SCOPE_OBJECTS,
    )
    classification: Sensitivity
    server_query_floor: Sensitivity
    generation_route: WikiGenerationRoute | None = None
    proposer: Identifier
    proposer_actor_kind: ActorKind
    proposer_person_id: Identifier


class WikiDraft(Contract):
    id: Identifier
    request_key: Identifier
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: WikiDraftPayload
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    compiler_mode: Literal["offline_extractive", "model_draft"]
    state: WikiDraftState
    created_at: AwareDatetime
    published_revision: int | None = Field(default=None, ge=1)
    reviewer: Identifier | None = None
    reviewer_person_id: Identifier | None = None

    @model_validator(mode="after")
    def route_matches_compiler_mode(self) -> Self:
        route_required = self.compiler_mode == "model_draft"
        if route_required != (self.payload.generation_route is not None):
            raise PydanticCustomError(
                "wiki_generation_route_invalid",
                "generation route must be present exactly for model drafts",
            )
        return self


class WikiPage(Contract):
    tenant: Identifier
    request_key: Identifier
    page_id: Identifier
    version_id: Identifier
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8_000)
    kind: WikiKind
    purpose: Purpose
    query: Query
    expected_page_revision: int = Field(ge=0)
    links: tuple[Identifier, ...] = Field(max_length=20)
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=10)
    input_citations: tuple[Citation, ...] = Field(min_length=1, max_length=10)
    source_bindings: tuple[WikiSourceBinding, ...] = Field(min_length=1, max_length=10)
    scope_object_bindings: tuple[WikiObjectBinding, ...] = Field(
        min_length=1,
        max_length=MAX_WIKI_SCOPE_OBJECTS,
    )
    classification: Sensitivity
    server_query_floor: Sensitivity
    compiler_mode: Literal["offline_extractive", "model_draft"]
    generation_route: WikiGenerationRoute | None = None
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposer: Identifier
    proposer_person_id: Identifier
    reviewer: Identifier
    reviewer_person_id: Identifier
    published_at: AwareDatetime

    @model_validator(mode="after")
    def route_matches_compiler_mode(self) -> Self:
        route_required = self.compiler_mode == "model_draft"
        if route_required != (self.generation_route is not None):
            raise PydanticCustomError(
                "wiki_generation_route_invalid",
                "generation route must be present exactly for model drafts",
            )
        return self


class WikiIndexEntry(Contract):
    page_id: Identifier
    title: str
    kind: WikiKind
    revision: int = Field(ge=1)
    classification: Sensitivity
    links: tuple[Identifier, ...]
    backlinks: tuple[Identifier, ...]


class WikiPageHit(Contract):
    page_id: Identifier
    title: str
    excerpt: str
    revision: int = Field(ge=1)
    classification: Sensitivity
    source_bindings: tuple[WikiSourceBinding, ...] = Field(min_length=1, max_length=10)
    input_citations: tuple[Citation, ...] = Field(min_length=1, max_length=10)


class WikiAnswer(Contract):
    pages: tuple[WikiPageHit, ...]
    answer: Answer


class WikiLintFinding(Contract):
    page_id: Identifier
    revision: int = Field(ge=1)
    state: WikiHeadState
    code: Literal["source_changed", "recompile_required"]
    reason: Literal["source_changed", "object_changed", "head_stale", "classification_floor"]


class WikiExportSource(Contract):
    document_id: Identifier
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class WikiExportManifest(Contract):
    non_authoritative: Literal[True] = True
    tenant: Identifier
    page_id: Identifier
    page_revision: int = Field(ge=1)
    page_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    purpose: Purpose
    classification: Sensitivity
    generation_route: WikiGenerationRoute | None = None
    sources: tuple[WikiExportSource, ...] = Field(min_length=1, max_length=10)
    exported_at: AwareDatetime
    expires_at: AwareDatetime
    caller_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class WikiExport(Contract):
    text: str = Field(min_length=1)
    manifest: WikiExportManifest
