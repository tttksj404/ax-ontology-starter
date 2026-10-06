from pathlib import Path
from typing import assert_never

import typer

from ax_starter.client_cli import emit_request
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.knowledge_contracts import KnowledgeMutationBatch, SourceSnapshotInput
from ax_starter.local_input import read_input
from ax_starter.onboarding import assess_onboarding
from ax_starter.onboarding_contracts import OnboardingRequest, ReadinessDecision
from ax_starter.release_gate import ReleaseCriteria, ReleaseEvaluation, evaluate_release

onboard_app = typer.Typer(
    help="회사 정책·업무 근거의 도입 진단", pretty_exceptions_show_locals=False
)
release_app = typer.Typer(
    help="평가 결과를 현업 검토 조건과 비교", pretty_exceptions_show_locals=False
)
knowledge_app = typer.Typer(
    help="인증된 로컬 API의 문서·ACL 수명주기 관리", pretty_exceptions_show_locals=False
)
contract_app = typer.Typer(
    help="운영자가 등록할 데이터 계약 검증", pretty_exceptions_show_locals=False
)


@onboard_app.command("evaluate")
def onboard(file: Path) -> None:
    report = assess_onboarding(read_input(file, OnboardingRequest))
    typer.echo(report.model_dump_json(indent=2))
    match report.decision:
        case ReadinessDecision.PILOT_REVIEW:
            return
        case ReadinessDecision.BLOCKED | ReadinessDecision.ON_HOLD:
            raise typer.Exit(code=2)
        case _ as unreachable:
            assert_never(unreachable)


@release_app.command("evaluate")
def release(evaluation: Path, criteria: Path) -> None:
    report = evaluate_release(
        read_input(evaluation, ReleaseEvaluation), read_input(criteria, ReleaseCriteria)
    )
    typer.echo(report.model_dump_json(indent=2))
    if not report.eligible_for_field_review:
        raise typer.Exit(code=2)


@contract_app.command("validate")
def contracts(file: Path) -> None:
    registry = read_input(file, DataContractRegistry)
    typer.echo(f"CONTRACTS_VALID count={len(registry.contracts)}")


@knowledge_app.command("state")
def knowledge_state() -> None:
    emit_request("GET", "/v1/knowledge/state")


@knowledge_app.command("apply")
def knowledge_apply(file: Path) -> None:
    emit_request("POST", "/v1/knowledge/apply", read_input(file, KnowledgeMutationBatch))


@knowledge_app.command("import")
def knowledge_import(file: Path) -> None:
    emit_request("POST", "/v1/knowledge/import", read_input(file, SourceSnapshotInput))
