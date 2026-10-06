import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from ax_starter.action_contracts import AuditCheck, Proposal, ProposeRequest, Simulation
from ax_starter.actions import ActionEngine
from ax_starter.api_contracts import ApprovalRequest, AuthenticatedContext
from ax_starter.api_extensions import mount_extensions
from ax_starter.assessment import assess
from ax_starter.auth import IdentityRegistry, read_identities
from ax_starter.common import AXError, Operation, Principal, Purpose
from ax_starter.contract_registry import read_contracts
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.generation import generate
from ax_starter.intake import Assessment, BusinessIntake
from ax_starter.knowledge import KnowledgeService
from ax_starter.middleware import BodyLimitMiddleware
from ax_starter.ontology import DomainPack, Entity
from ax_starter.providers import ProviderConfig
from ax_starter.retrieval import Answer, Query, authorized_objects, retrieve
from ax_starter.store import Store
from ax_starter.wiki import WikiService
from ax_starter.wiki_api import mount_wiki

__all__ = ["ApprovalRequest", "create_app"]


def create_app(  # noqa: C901, PLR0913, PLR0915 - factory assembles independent routes/dependencies
    pack: DomainPack,
    database: Path,
    identities: IdentityRegistry,
    provider: ProviderConfig | None = None,
    *,
    identity_path: Path | None = None,
    data_contracts: DataContractRegistry | None = None,
    contract_path: Path | None = None,
    clock: Callable[[], datetime] | None = None,
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost"),
) -> FastAPI:
    def current_contracts() -> DataContractRegistry | None:
        return read_contracts(contract_path) if contract_path else data_contracts

    store = Store(database, pack, contract_resolver=current_contracts)

    def current_registry() -> IdentityRegistry:
        return read_identities(identity_path) if identity_path else identities

    runtime = provider or ProviderConfig()
    at = clock or (lambda: datetime.now(UTC))
    app = FastAPI(
        title="AX Ontology Starter", docs_url=None, redoc_url=None, openapi_url=None, debug=False
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.add_middleware(BodyLimitMiddleware)
    security = HTTPBearer(auto_error=False)

    def authenticated_context(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    ) -> AuthenticatedContext:
        if credentials is None:
            raise AXError("authentication_required", 401)
        now = at()
        actor = current_registry().authenticate(credentials.credentials, now=now)
        return AuthenticatedContext(actor, SecretStr(credentials.credentials))

    def authenticated(
        context: Annotated[AuthenticatedContext, Depends(authenticated_context)],
    ) -> Principal:
        return context.principal

    def reauthenticated_registry(
        context: AuthenticatedContext,
        now: datetime,
    ) -> IdentityRegistry:
        registry = current_registry()
        actor = registry.authenticate(context.credential.get_secret_value(), now=now)
        if actor != context.principal:
            raise AXError("identity_changed", 409)
        return registry

    def request_engine(context: AuthenticatedContext) -> ActionEngine:
        return ActionEngine(
            store,
            pack,
            (),
            principal_resolver=lambda: reauthenticated_registry(context, at()).principals(),
        )

    def fresh_answer(context: AuthenticatedContext, query: Query) -> Answer:
        now = at()
        _ = reauthenticated_registry(context, now)
        with store.transaction() as conn:
            current = store.current_pack(conn, pack)
            return retrieve(current, context.principal, query, now)

    def knowledge_service(context: AuthenticatedContext) -> KnowledgeService:
        actor = context.principal
        if (
            Operation.MANAGE_KNOWLEDGE not in actor.operations
            or Purpose.AUDIT not in actor.purposes
        ):
            raise AXError("access_denied", 403)
        contracts = current_contracts()
        if contracts is None:
            raise AXError("data_contract_registry_required", 503)

        def check_credential() -> None:
            _ = reauthenticated_registry(context, at())

        return KnowledgeService(store, pack, contracts, credential_guard=check_credential)

    def wiki_service(context: AuthenticatedContext) -> WikiService:
        return WikiService(
            store,
            pack,
            credential_guard=lambda: check_wiki_credential(context),
            principal_resolver=lambda: reauthenticated_registry(context, at()).principals(),
            server_query_floor=runtime.minimum_query_sensitivity,
            clock=at,
        )

    def check_wiki_credential(context: AuthenticatedContext) -> None:
        _ = reauthenticated_registry(context, at())

    mount_extensions(app, authenticated_context, knowledge_service, at)
    mount_wiki(app, authenticated_context, wiki_service, runtime, at)

    @app.exception_handler(AXError)
    async def handle_ax_error(_request: Request, exc: AXError) -> JSONResponse:
        if exc.status >= HTTP_500_INTERNAL_SERVER_ERROR:
            logging.getLogger("ax_starter").error("request.failed", extra={"reason_code": exc.code})
        else:
            logging.getLogger("ax_starter").info("request.denied", extra={"reason_code": exc.code})
        return JSONResponse({"error": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "invalid_request"}, status_code=422)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "reference-runtime"}

    @app.post("/v1/assess")
    def assessment(
        intake: BusinessIntake, actor: Annotated[Principal, Depends(authenticated)]
    ) -> Assessment:
        if Operation.READ not in actor.operations:
            raise AXError("access_denied", 403)
        return assess(intake)

    @app.get("/v1/objects")
    def objects(
        actor: Annotated[Principal, Depends(authenticated)], purpose: Purpose = Purpose.OPERATIONS
    ) -> tuple[Entity, ...]:
        with store.transaction() as conn:
            current = store.current_pack(conn, pack)
        return authorized_objects(current, actor, purpose)

    @app.post("/v1/ask")
    def ask(
        query: Query, context: Annotated[AuthenticatedContext, Depends(authenticated_context)]
    ) -> Answer:
        with store.transaction() as conn:
            current = store.current_pack(conn, pack)
            answer = retrieve(current, context.principal, query, at())
        if not query.generate:
            return answer
        if fresh_answer(context, query) != answer:
            raise AXError("knowledge_snapshot_changed", 409)
        result = generate(runtime, query, answer)
        if fresh_answer(context, query) != answer:
            raise AXError("knowledge_snapshot_changed", 409)
        return result

    @app.post("/v1/actions/propose")
    def propose(
        body: ProposeRequest,
        context: Annotated[AuthenticatedContext, Depends(authenticated_context)],
    ) -> Proposal:
        return request_engine(context).propose(context.principal, body, at())

    @app.get("/v1/actions/{key}/simulate")
    def simulate(
        key: str,
        context: Annotated[AuthenticatedContext, Depends(authenticated_context)],
    ) -> Simulation:
        return request_engine(context).simulate(context.principal, key, at())

    @app.post("/v1/actions/{key}/approve")
    def approve(
        key: str,
        body: ApprovalRequest,
        context: Annotated[AuthenticatedContext, Depends(authenticated_context)],
    ) -> Proposal:
        return request_engine(context).approve(
            context.principal, key, at(), body.reviewed_payload_hash
        )

    @app.post("/v1/actions/{key}/execute")
    def execute(
        key: str,
        context: Annotated[AuthenticatedContext, Depends(authenticated_context)],
    ) -> Proposal:
        return request_engine(context).execute(context.principal, key, at())

    @app.post("/v1/actions/{key}/rollback")
    def rollback(
        key: str,
        context: Annotated[AuthenticatedContext, Depends(authenticated_context)],
    ) -> Proposal:
        return request_engine(context).rollback(context.principal, key, at())

    @app.get("/v1/audit/verify")
    def audit(actor: Annotated[Principal, Depends(authenticated)]) -> AuditCheck:
        if Operation.READ not in actor.operations or Purpose.AUDIT not in actor.purposes:
            raise AXError("access_denied", 403)
        with store.transaction() as conn:
            return store.audit_check(conn, actor.tenant)

    return app
