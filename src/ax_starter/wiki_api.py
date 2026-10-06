from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials

from ax_starter.api_contracts import ApprovalRequest, AuthenticatedContext
from ax_starter.common import AXError, Identifier, Purpose
from ax_starter.providers import ProviderConfig
from ax_starter.retrieval import Query
from ax_starter.wiki import WikiService
from ax_starter.wiki_compiler import compile_wiki
from ax_starter.wiki_contracts import (
    WikiAnswer,
    WikiCompileRequest,
    WikiDraft,
    WikiExport,
    WikiIndexEntry,
    WikiLintFinding,
    WikiPage,
)


def mount_wiki(
    app: FastAPI,
    get_context: Callable[[HTTPAuthorizationCredentials | None], AuthenticatedContext],
    factory: Callable[[AuthenticatedContext], WikiService],
    provider: ProviderConfig,
    clock: Callable[[], datetime],
) -> None:
    @app.post("/v1/wiki/compile")
    def compile_page(
        body: WikiCompileRequest,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> WikiDraft:
        return factory(context).compile(
            context.principal,
            body,
            clock(),
            lambda request, answer: compile_wiki(provider, request, answer),
        )

    @app.get("/v1/wiki/drafts/{draft_id}")
    def draft(
        draft_id: Identifier,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> WikiDraft:
        return factory(context).view_draft(context.principal, draft_id, clock())

    @app.post("/v1/wiki/drafts/{draft_id}/publish")
    def publish(
        draft_id: Identifier,
        body: ApprovalRequest,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> WikiPage:
        return factory(context).publish(
            context.principal, draft_id, body.reviewed_payload_hash, clock()
        )

    @app.get("/v1/wiki/index")
    def index(
        context: Annotated[AuthenticatedContext, Depends(get_context)],
        purpose: Purpose = Purpose.OPERATIONS,
    ) -> tuple[WikiIndexEntry, ...]:
        return factory(context).index(context.principal, purpose, clock())

    @app.get("/v1/wiki/pages/{page_id}")
    def page(
        page_id: Identifier,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
        purpose: Purpose = Purpose.OPERATIONS,
    ) -> WikiPage:
        return factory(context).page(context.principal, page_id, purpose, clock())

    @app.post("/v1/wiki/query")
    def query(
        body: Query,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> WikiAnswer:
        if body.generate:
            raise AXError("wiki_query_generation_not_supported", 422)
        return factory(context).query(context.principal, body, clock())

    @app.get("/v1/wiki/lint")
    def lint(
        context: Annotated[AuthenticatedContext, Depends(get_context)],
        purpose: Purpose = Purpose.OPERATIONS,
    ) -> tuple[WikiLintFinding, ...]:
        return factory(context).lint(context.principal, purpose, clock())

    @app.get("/v1/wiki/pages/{page_id}/export")
    def export(
        page_id: Identifier,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
        purpose: Purpose = Purpose.OPERATIONS,
    ) -> WikiExport:
        return factory(context).export(context.principal, page_id, purpose, clock())
