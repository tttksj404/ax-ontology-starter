from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import typer

from ax_starter.api_contracts import ApprovalRequest
from ax_starter.client_cli import emit_request
from ax_starter.common import Purpose, Sensitivity
from ax_starter.demo import DemoDomain
from ax_starter.local_input import read_input
from ax_starter.retrieval import Query
from ax_starter.wiki_contracts import WikiCompileRequest
from ax_starter.wiki_demo import run_wiki_demo

wiki_app = typer.Typer(
    help="원천에 결속된 Wiki 초안·독립 검토 게시·검색·권한별 export",
    pretty_exceptions_show_locals=False,
)


@wiki_app.command("demo")
def demo(domain: Annotated[DemoDomain, typer.Option()] = DemoDomain.PROCUREMENT) -> None:
    typer.echo(run_wiki_demo(domain).model_dump_json(indent=2))


@wiki_app.command("compile")
def compile_page(file: Path) -> None:
    emit_request("POST", "/v1/wiki/compile", read_input(file, WikiCompileRequest))


@wiki_app.command("draft")
def draft(draft_id: str) -> None:
    emit_request("GET", "/v1/wiki/drafts/" + quote(draft_id, safe=""))


@wiki_app.command("publish")
def publish(draft_id: str, reviewed_hash: Annotated[str, typer.Option()]) -> None:
    emit_request(
        "POST",
        "/v1/wiki/drafts/" + quote(draft_id, safe="") + "/publish",
        ApprovalRequest(reviewed_payload_hash=reviewed_hash),
    )


@wiki_app.command("index")
def index(purpose: Annotated[Purpose, typer.Option()] = Purpose.OPERATIONS) -> None:
    emit_request("GET", "/v1/wiki/index?purpose=" + purpose.value)


@wiki_app.command("page")
def page(page_id: str, purpose: Annotated[Purpose, typer.Option()] = Purpose.OPERATIONS) -> None:
    emit_request("GET", "/v1/wiki/pages/" + quote(page_id, safe="") + "?purpose=" + purpose.value)


@wiki_app.command("query")
def query(
    question: str,
    purpose: Annotated[Purpose, typer.Option()] = Purpose.OPERATIONS,
    object_id: Annotated[str | None, typer.Option()] = None,
    sensitivity: Annotated[Sensitivity, typer.Option()] = Sensitivity.CONFIDENTIAL,
) -> None:
    emit_request(
        "POST",
        "/v1/wiki/query",
        Query(question=question, purpose=purpose, object_id=object_id, sensitivity=sensitivity),
    )


@wiki_app.command("lint")
def lint(purpose: Annotated[Purpose, typer.Option()] = Purpose.OPERATIONS) -> None:
    emit_request("GET", "/v1/wiki/lint?purpose=" + purpose.value)


@wiki_app.command("export")
def export(page_id: str, purpose: Annotated[Purpose, typer.Option()] = Purpose.OPERATIONS) -> None:
    """Return a non-authoritative snapshot; the caller controls file storage and retention."""
    emit_request(
        "GET", "/v1/wiki/pages/" + quote(page_id, safe="") + "/export?purpose=" + purpose.value
    )
