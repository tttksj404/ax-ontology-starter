import pytest

from ax_starter.assessment import assess
from ax_starter.common import Sensitivity
from ax_starter.intake import (
    AutomationMode,
    BusinessIntake,
    DecisionImpact,
    Risk,
    SourceStatus,
    Step,
)


def intake_for(
    risk: Risk, *, authorized: bool = True, rules: tuple[str, ...] = ("규칙",)
) -> BusinessIntake:
    return BusinessIntake(
        business="합성 업무",
        objective="처리 지연 감소",
        process_owner="운영 책임자",
        industry="범용",
        constraints=(),
        steps=(
            Step(
                id="collect",
                name="자료 수집",
                owner="담당자",
                inputs=("요청",),
                outputs=("검토 자료",),
                systems=("ERP",),
                rules=rules,
                exceptions=("미등록 자료",),
                evidence_sources=("SOP",),
                monthly_cases=120,
                minutes_per_case=10,
                repetitive=0.9,
                digital_readiness=0.9,
                rule_clarity=0.9,
                exception_rate=0.1,
                risk=risk,
                sensitivity=Sensitivity.INTERNAL,
                authorized=authorized,
                reversible=True,
                kpi="중앙 처리시간",
                evidence_status=SourceStatus.OBSERVED,
                value_status=SourceStatus.OBSERVED,
                control_point=False,
                decision_impact=DecisionImpact.ADMINISTRATIVE,
            ),
        ),
    )


def test_low_risk_can_be_candidate_when_inputs_are_ready() -> None:
    # Given
    intake = intake_for(Risk.LOW)
    # When
    result = assess(intake)
    # Then
    assert result.steps[0].mode == AutomationMode.AUTOMATE
    assert result.steps[0].baseline_hours_monthly == 20
    assert result.measured_roi is False


@pytest.mark.parametrize("risk", [Risk.HIGH, Risk.CRITICAL])
def test_high_risk_requires_human_when_readiness_is_high(risk: Risk) -> None:
    # Given
    intake = intake_for(risk)
    # When
    result = assess(intake)
    # Then
    assert result.steps[0].mode != AutomationMode.AUTOMATE


def test_authorization_blocks_when_permission_is_missing() -> None:
    # Given
    intake = intake_for(Risk.LOW, authorized=False)
    # When
    result = assess(intake)
    # Then
    assert result.steps[0].mode == AutomationMode.DEFER


def test_missing_rules_defer_when_summary_claims_clarity() -> None:
    # Given
    intake = intake_for(Risk.LOW, rules=())
    # When
    result = assess(intake)
    # Then
    assert result.steps[0].mode == AutomationMode.DEFER
