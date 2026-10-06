import ipaddress
import os
from pathlib import Path
from typing import Annotated, Final
from urllib.parse import urlsplit

import httpx2
import typer
from pydantic import Field, ValidationError

from ax_starter.action_contracts import ProposeRequest
from ax_starter.api import ApprovalRequest
from ax_starter.common import AXError, Contract, Sensitivity
from ax_starter.local_input import read_input
from ax_starter.providers import provider_client
from ax_starter.retrieval import Query

action_app = typer.Typer(
    help="인증된 로컬 API를 통해 제안·검토·승인·실행합니다.", pretty_exceptions_show_locals=False
)
MAX_ERROR_BODY_BYTES: Final = 2048


class ApiFailure(Contract):
    error: str = Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")


def request_api(method: str, path: str, body: Contract | None = None) -> str:
    base = os.environ.get("AX_API_BASE", "http://127.0.0.1:8000")
    try:
        url = urlsplit(base)
        _ = url.port
        if (
            not url.hostname
            or not ipaddress.ip_address(url.hostname).is_loopback
            or url.scheme not in ("http", "https")
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise AXError("cli_requires_loopback_api", 403)
    except ValueError as exc:
        raise AXError("cli_requires_loopback_api", 403) from exc
    credential = os.environ.get("AX_TOKEN")
    if not credential:
        raise AXError("AX_TOKEN_required", 401)
    try:
        with provider_client() as client:
            response = client.request(
                method,
                base.rstrip("/") + path,
                content=body.model_dump_json() if body else None,
                headers={
                    "Authorization": "Bearer " + credential,
                    "Content-Type": "application/json",
                },
            )
            _ = response.raise_for_status()
            return response.text
    except httpx2.HTTPStatusError as exc:
        if len(exc.response.content) > MAX_ERROR_BODY_BYTES:
            raise AXError("api_request_failed", 502) from exc
        try:
            failure = ApiFailure.model_validate_json(exc.response.content)
        except ValidationError as invalid:
            raise AXError("api_request_failed", 502) from invalid
        raise AXError(failure.error, exc.response.status_code) from exc
    except (httpx2.HTTPError, httpx2.InvalidURL) as exc:
        raise AXError("api_request_failed", 502) from exc


def emit_request(method: str, path: str, body: Contract | None = None) -> None:
    try:
        typer.echo(request_api(method, path, body))
    except AXError as exc:
        typer.echo(exc.code, err=True)
        raise typer.Exit(code=1) from exc


def ask(
    question: str,
    object_id: Annotated[str | None, typer.Option()] = None,
    generate: Annotated[bool, typer.Option()] = False,
    sensitivity: Annotated[int, typer.Option(min=0, max=3)] = 2,
) -> None:
    emit_request(
        "POST",
        "/v1/ask",
        Query(
            question=question,
            object_id=object_id,
            generate=generate,
            sensitivity=Sensitivity(sensitivity),
        ),
    )


@action_app.command("propose")
def propose(file: Path) -> None:
    body = read_input(file, ProposeRequest)
    emit_request("POST", "/v1/actions/propose", body)


@action_app.command("simulate")
def simulate(proposal_id: str) -> None:
    emit_request("GET", "/v1/actions/" + proposal_id + "/simulate")


@action_app.command("approve")
def approve(proposal_id: str, reviewed_hash: Annotated[str, typer.Option()]) -> None:
    emit_request(
        "POST",
        "/v1/actions/" + proposal_id + "/approve",
        ApprovalRequest(reviewed_payload_hash=reviewed_hash),
    )


@action_app.command("execute")
def execute(proposal_id: str) -> None:
    emit_request("POST", "/v1/actions/" + proposal_id + "/execute")


@action_app.command("rollback")
def rollback(proposal_id: str) -> None:
    emit_request("POST", "/v1/actions/" + proposal_id + "/rollback")


def audit() -> None:
    emit_request("GET", "/v1/audit/verify")
