import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ax_starter.actions import ActionEngine
from ax_starter.bootstrap import initialize
from ax_starter.cli import app
from ax_starter.common import AXError, Principal
from ax_starter.demo import DemoDomain
from ax_starter.evaluation import EvaluationCase, EvaluationSet, evaluate
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query
from ax_starter.runtime import load_app
from tests.test_actions import request
from tests.test_api import registry
from tests.test_runtime import configure


@pytest.mark.parametrize("base", ["http://127.0.0.1:8o00", "http://127.0.0.1:70000", "http://["])
def test_cli_when_api_url_is_malformed_does_not_print_credential(base: str) -> None:
    # Given: a synthetic sentinel must never enter error output.
    sentinel = "synthetic-only-credential-" + "x" * 32
    # When
    result = subprocess.run(
        [sys.executable, "-m", "ax_starter", "audit"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "AX_API_BASE": base,
            "AX_TOKEN": sentinel,
            "PYTHONIOENCODING": "utf-8",
            "COLUMNS": "240",
        },
    )
    # Then
    assert result.returncode == 1
    assert sentinel not in result.stdout + result.stderr
    assert result.stderr.strip() == "cli_requires_loopback_api"


def test_init_when_artifact_write_fails_has_safe_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    def failed_write(_path: Path, _data: str, **_kwargs: str | int | bool | None) -> int:
        raise OSError

    monkeypatch.setattr(Path, "write_text", failed_write)
    # When
    result = CliRunner().invoke(app, ["init", str(tmp_path / "pilot")])
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "initialization_storage_failed"


@pytest.mark.parametrize("kind", ["relative", "missing-parent"])
def test_runtime_when_database_parent_is_not_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    # Given
    pilot = tmp_path / "pilot"
    _ = initialize(pilot, DemoDomain.PROCUREMENT)
    configure(monkeypatch, pilot)
    monkeypatch.chdir(tmp_path)
    target = Path("relative.db") if kind == "relative" else tmp_path / "unprepared" / "state.db"
    monkeypatch.setenv("AX_DB_FILE", str(target))
    # When / Then
    with pytest.raises(AXError, match="runtime_configuration_required") as error:
        _ = load_app()
    assert error.value.status == 503
    assert not target.exists()
    assert not (tmp_path / "unprepared").exists()


@pytest.mark.parametrize("rolled_back", [False, True])
def test_approval_when_proposal_has_terminal_state(
    engine: ActionEngine,
    principals: tuple[Principal, ...],
    now: datetime,
    rolled_back: bool,
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    _ = engine.execute(principals[0], proposal.id, now)
    if rolled_back:
        _ = engine.rollback(principals[1], proposal.id, now)
    # When / Then
    with pytest.raises(AXError, match="proposal_state_conflict") as error:
        _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    assert error.value.status == 409


def test_execute_when_proposal_is_already_rolled_back(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    _ = engine.execute(principals[0], proposal.id, now)
    _ = engine.rollback(principals[1], proposal.id, now)
    # When / Then
    with pytest.raises(AXError, match="proposal_state_conflict") as error:
        _ = engine.execute(principals[0], proposal.id, now)
    assert error.value.status == 409


@pytest.mark.parametrize("expected_denial", [False, True])
def test_evaluation_when_graph_budget_is_exceeded_records_failed_case(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    expected_denial: bool,
) -> None:
    # Given
    procedure = next(entity for entity in pack.objects if entity.id == "procedure-1")
    objects = tuple(procedure.model_copy(update={"id": f"proc-{index}"}) for index in range(51))
    links = tuple(
        pack.links[0].model_copy(update={"id": f"wide-{index}", "target_id": entity.id})
        for index, entity in enumerate(objects)
    )
    wide = pack.model_copy(
        update={"objects": (*pack.objects, *objects), "links": (*pack.links, *links)}
    )
    dataset = EvaluationSet(
        synthetic=True,
        cases=(
            EvaluationCase(
                id="wide-graph",
                tenant="acme",
                subject="operator",
                query=Query(question="검토", object_id="request-1"),
                expected_documents=(),
                expected_denial=expected_denial,
            ),
        ),
    )
    # When
    report = evaluate(wide, registry(principals), dataset, now)
    # Then
    assert not report.passed
    assert not report.cases[0].passed
    assert not report.cases[0].denied
    assert report.cases[0].failure_code == "graph_fanout_limit"


def test_eval_cli_when_subject_is_missing_has_safe_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("AX_INPUT_ROOT", str(tmp_path))
    pilot = tmp_path / "pilot"
    _ = initialize(pilot, DemoDomain.PROCUREMENT)
    cases = EvaluationSet.model_validate_json((pilot / "evaluation-set.json").read_bytes())
    missing = cases.model_copy(
        update={"cases": (cases.cases[0].model_copy(update={"subject": "missing"}),)}
    )
    _ = (pilot / "evaluation-set.json").write_text(missing.model_dump_json(), encoding="utf-8")
    # When
    result = CliRunner().invoke(
        app,
        [
            "pack",
            "eval",
            str(pilot / "domain-pack.json"),
            str(pilot / "identities.json"),
            str(pilot / "evaluation-set.json"),
        ],
    )
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "evaluation_subject_missing"
