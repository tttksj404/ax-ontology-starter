import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from typer.testing import CliRunner

from ax_starter.actions import ActionEngine
from ax_starter.auth import IdentityBinding, IdentityRegistry
from ax_starter.bootstrap import initialize
from ax_starter.cli import app
from ax_starter.client_cli import request_api
from ax_starter.common import AXError, Principal
from ax_starter.demo import DemoDomain
from ax_starter.demo_run import run_demo
from ax_starter.evaluation import EvaluationCase, EvaluationSet, evaluate
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query, retrieve
from tests.test_api import registry


def test_demo_when_clock_has_passed_original_expiry() -> None:
    # Given / When
    report = run_demo(DemoDomain.PROCUREMENT, now=datetime(2028, 6, 1, tzinfo=UTC))
    # Then
    assert report.passed


def test_eval_cli_when_explicit_timezone_is_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("AX_INPUT_ROOT", str(tmp_path))
    pilot = tmp_path / "pilot"
    _ = initialize(pilot, DemoDomain.PROCUREMENT)
    # When
    result = CliRunner().invoke(
        app,
        [
            "pack",
            "eval",
            str(pilot / "domain-pack.json"),
            str(pilot / "identities.json"),
            str(pilot / "evaluation-set.json"),
            "--as-of",
            "2026-10-01T00:00:00+00:00",
        ],
    )
    # Then
    assert result.exit_code == 0
    assert '"passed": true' in result.stdout


def test_evaluation_when_subject_name_exists_in_two_tenants(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    original = registry(principals)
    same_name = principals[3].model_copy(update={"subject": "operator"})
    identities = IdentityRegistry(
        bindings=(*original.bindings, IdentityBinding(token_sha256="a" * 64, principal=same_name))
    )
    dataset = EvaluationSet(
        synthetic=True,
        cases=(
            EvaluationCase(
                id="beta-operator",
                tenant="beta",
                subject="operator",
                query=Query(question="검토", object_id="beta-request"),
                expected_documents=("beta-doc",),
            ),
        ),
    )
    # When / Then
    assert evaluate(pack, identities, dataset, now).passed


def test_graph_when_visible_fanout_exceeds_budget(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    procedure = next(entity for entity in pack.objects if entity.id == "procedure-1")
    prototypes = tuple(procedure.model_copy(update={"id": f"proc-{index}"}) for index in range(51))
    links = tuple(
        pack.links[0].model_copy(update={"id": f"wide-{index}", "target_id": entity.id})
        for index, entity in enumerate(prototypes)
    )
    wide = pack.model_copy(
        update={"objects": (*pack.objects, *prototypes), "links": (*pack.links, *links)}
    )
    # When / Then
    with pytest.raises(AXError, match="graph_fanout_limit"):
        _ = retrieve(wide, principals[0], Query(question="검토", object_id="request-1"), now)


def test_storage_when_lock_wait_is_exhausted(engine: ActionEngine) -> None:
    # Given
    engine.store.busy_timeout_seconds = 0.01
    with closing(sqlite3.connect(engine.store.path)) as locked:
        _ = locked.execute("BEGIN IMMEDIATE")
        # When / Then
        with pytest.raises(AXError, match="state_busy") as error, engine.store.transaction():
            pytest.fail("locked transaction unexpectedly started")
        assert error.value.status == 503


def test_cli_when_api_returns_a_safe_machine_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setenv("AX_API_BASE", "http://127.0.0.1:8000")
    monkeypatch.setenv("AX_TOKEN", "synthetic-local-test-only-credential")

    def rejected(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json={"error": "self_approval_forbidden"})

    monkeypatch.setattr(
        "ax_starter.client_cli.provider_client",
        lambda: httpx2.Client(transport=httpx2.MockTransport(rejected)),
    )
    # When / Then
    with pytest.raises(AXError, match="self_approval_forbidden") as error:
        _ = request_api("POST", "/v1/actions/example/approve")
    assert error.value.status == 403
