from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final

import typer

from ax_starter.assessment import assess
from ax_starter.assets import export_assets
from ax_starter.auth import IdentityRegistry
from ax_starter.bootstrap import initialize
from ax_starter.client_cli import action_app, ask, audit
from ax_starter.common import AXError
from ax_starter.demo import DemoDomain
from ax_starter.demo_run import run_demo
from ax_starter.evaluation import EvaluationSet, evaluate
from ax_starter.intake import BusinessIntake
from ax_starter.local_input import read_input
from ax_starter.ontology import DomainPack
from ax_starter.process_metrics import ProcessLog, process_metrics
from ax_starter.v02_cli import contract_app, knowledge_app, onboard_app, release_app
from ax_starter.wiki_cli import wiki_app

TIMEZONE_REQUIRED: Final = "as-of는 timezone을 포함해야 합니다."

app = typer.Typer(
    help="범용 업무 AX 진단·온톨로지·승인 실행 스타터팩", pretty_exceptions_show_locals=False
)
pack_app = typer.Typer(help="도메인팩 스키마 검증과 검색 평가", pretty_exceptions_show_locals=False)
app.add_typer(pack_app, name="pack")
app.add_typer(action_app, name="action")
app.add_typer(onboard_app, name="onboard")
app.add_typer(release_app, name="release")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(contract_app, name="contract")
app.add_typer(wiki_app, name="wiki")
_ = app.command("ask")(ask)
_ = app.command("audit")(audit)


@app.command("init")
def init(
    directory: Path, domain: Annotated[DemoDomain, typer.Option()] = DemoDomain.PROCUREMENT
) -> None:
    try:
        _ = initialize(directory, domain)
    except AXError as exc:
        typer.echo(exc.code, err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.echo("initialization_storage_failed", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"초기화: {directory.resolve()} (합성 데이터, credential 값은 출력하지 않음)")


@app.command("demo")
def demo(domain: Annotated[DemoDomain, typer.Option()] = DemoDomain.PROCUREMENT) -> None:
    typer.echo(run_demo(domain).model_dump_json(indent=2))


@app.command("assets")
def assets(directory: Path) -> None:
    try:
        count = export_assets(directory)
    except AXError as exc:
        typer.echo(exc.code, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"ASSETS_EXPORTED files={count} directory={directory.resolve()}")


@app.command("assess")
def assessment(file: Path) -> None:
    typer.echo(assess(read_input(file, BusinessIntake)).model_dump_json(indent=2))


@app.command("process")
def metrics(file: Path) -> None:
    typer.echo(process_metrics(read_input(file, ProcessLog)).model_dump_json(indent=2))


@pack_app.command("validate")
def validate_pack(file: Path) -> None:
    pack = read_input(file, DomainPack)
    typer.echo(
        " ".join(
            (
                f"PACK_VALID id={pack.id} version={pack.version}",
                f"objects={len(pack.objects)} documents={len(pack.documents)}",
            )
        )
    )


@pack_app.command("eval")
def eval_pack(
    file: Path,
    identities: Path,
    cases: Path,
    as_of: Annotated[datetime | None, typer.Option(formats=["%Y-%m-%dT%H:%M:%S%z"])] = None,
) -> None:
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None:
        raise typer.BadParameter(TIMEZONE_REQUIRED)
    try:
        report = evaluate(
            read_input(file, DomainPack),
            read_input(identities, IdentityRegistry),
            read_input(cases, EvaluationSet),
            now,
        )
    except AXError as exc:
        typer.echo(exc.code, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(report.model_dump_json(indent=2))
    if not report.passed:
        raise typer.Exit(code=1)
