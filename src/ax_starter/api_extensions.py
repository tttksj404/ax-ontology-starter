from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials

from ax_starter.api_contracts import AuthenticatedContext, ReleaseRequest
from ax_starter.common import AXError, Operation
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    KnowledgeMutationBatch,
    KnowledgeMutationReceipt,
    KnowledgeState,
    SourceSnapshotInput,
)
from ax_starter.onboarding import assess_onboarding
from ax_starter.onboarding_contracts import OnboardingReport, OnboardingRequest
from ax_starter.release_gate import ReleaseGate, evaluate_release


def mount_extensions(
    app: FastAPI,
    get_context: Callable[[HTTPAuthorizationCredentials | None], AuthenticatedContext],
    knowledge_factory: Callable[[AuthenticatedContext], KnowledgeService],
    clock: Callable[[], datetime],
) -> None:
    @app.post("/v1/onboard")
    def onboard(
        body: OnboardingRequest,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> OnboardingReport:
        if Operation.READ not in context.principal.operations:
            raise AXError("access_denied", 403)
        return assess_onboarding(body)

    @app.post("/v1/release/evaluate")
    def release_evaluation(
        body: ReleaseRequest,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> ReleaseGate:
        if Operation.READ not in context.principal.operations:
            raise AXError("access_denied", 403)
        return evaluate_release(body.evaluation, body.criteria)

    @app.get("/v1/knowledge/state")
    def knowledge_state(
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> KnowledgeState:
        return knowledge_factory(context).state(context.principal)

    @app.post("/v1/knowledge/apply")
    def knowledge_apply(
        body: KnowledgeMutationBatch,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> KnowledgeMutationReceipt:
        return knowledge_factory(context).apply(context.principal, body, clock())

    @app.post("/v1/knowledge/import")
    def knowledge_import(
        body: SourceSnapshotInput,
        context: Annotated[AuthenticatedContext, Depends(get_context)],
    ) -> KnowledgeMutationReceipt:
        return knowledge_factory(context).import_snapshot(context.principal, body, clock())
