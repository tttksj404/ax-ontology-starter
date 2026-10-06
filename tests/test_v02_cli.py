from pathlib import Path

import pytest
from typer.testing import CliRunner

from ax_starter.cli import app
from ax_starter.onboarding_contracts import OnboardingReport, OnboardingRequest, ReadinessDecision
from ax_starter.release_gate import ReleaseBoundary, ReleaseDecision, ReleaseGate

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "v0.2"


def test_onboarding_unknown_policy_emits_questions_and_blocks(tmp_path: Path) -> None:
    # Given
    request = OnboardingRequest.model_validate_json(
        (EXAMPLES / "onboarding-request.json").read_bytes()
    )
    request = request.model_copy(
        update={
            "profile": request.profile.model_copy(
                update={"owner": None, "maximum_sensitivity": None}
            )
        }
    )
    path = tmp_path / "request.json"
    _ = path.write_text(request.model_dump_json(), encoding="utf-8")
    # When
    result = CliRunner().invoke(
        app, ["onboard", "evaluate", str(path)], env={"AX_INPUT_ROOT": str(tmp_path)}
    )
    # Then
    report = OnboardingReport.model_validate_json(result.stdout)
    assert result.exit_code == 2
    assert report.decision == ReadinessDecision.BLOCKED
    assert "company_owner_unknown" in report.missing_information
    assert report.next_steps
    assert report.live_validated is False


def test_synthetic_release_cannot_be_promoted_from_cli() -> None:
    # Given / When
    result = CliRunner().invoke(
        app,
        [
            "release",
            "evaluate",
            str(EXAMPLES / "release-evaluation.json"),
            str(EXAMPLES / "release-criteria.json"),
        ],
    )
    # Then
    report = ReleaseGate.model_validate_json(result.stdout)
    assert result.exit_code == 2
    assert report.decision == ReleaseDecision.BLOCKED
    assert report.boundaries == (ReleaseBoundary.EVALUATION_TARGET_MANIFEST_MISSING,)
    assert report.eligible_for_field_review is False
    assert report.evidence_origin_verified is False


def test_invalid_input_never_echoes_source_or_secret(tmp_path: Path) -> None:
    # Given
    marker = "synthetic-secret-do-not-echo"
    path = tmp_path / "request.json"
    _ = path.write_text('{"private_note":"' + marker + '"}', encoding="utf-8")
    # When
    result = CliRunner().invoke(
        app, ["onboard", "evaluate", str(path)], env={"AX_INPUT_ROOT": str(tmp_path)}
    )
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "invalid_input_file"
    assert marker not in result.output


def test_contract_cli_validates_without_emitting_document_content() -> None:
    # Given / When
    result = CliRunner().invoke(
        app, ["contract", "validate", str(EXAMPLES / "data-contract-registry.json")]
    )
    # Then
    assert result.exit_code == 0
    assert "CONTRACTS_VALID count=1" in result.stdout
    assert "source_uri" not in result.output


def test_knowledge_cli_requires_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.delenv("AX_TOKEN", raising=False)
    # When
    result = CliRunner().invoke(app, ["knowledge", "state"])
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "AX_TOKEN_required"


def test_knowledge_cli_denies_external_api_without_echoing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    marker = "synthetic-auth-marker-do-not-echo"
    monkeypatch.setenv("AX_TOKEN", marker)
    monkeypatch.setenv("AX_API_BASE", "https://outside.example.com")
    # When
    result = CliRunner().invoke(app, ["knowledge", "state"])
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "cli_requires_loopback_api"
    assert marker not in result.output
