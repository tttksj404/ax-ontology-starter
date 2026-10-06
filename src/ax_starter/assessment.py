from typing import Final, assert_never

from ax_starter.intake import (
    Assessment,
    AutomationMode,
    BusinessIntake,
    DecisionImpact,
    Risk,
    SourceStatus,
    Step,
    StepAssessment,
)

MIN_READINESS_SCORE: Final = 70
MAX_EXCEPTION_RATE: Final = 0.3


def _blockers(step: Step) -> list[str]:
    blockers: list[str] = []
    if not step.owner or not step.inputs or not step.outputs:
        blockers.append("담당자와 입력·산출물을 먼저 확인해야 합니다.")
    if not step.authorized:
        blockers.append("업무 변경 권한과 책임자 승인을 확보해야 합니다.")
    if not step.rules or not step.evidence_sources:
        blockers.append("판단 규칙 또는 검증할 근거가 누락되었습니다.")
    if step.digital_readiness == 0:
        blockers.append("입력 데이터의 수집·정합성 계약부터 정의해야 합니다.")
    return blockers


def _assist_reasons(step: Step, score: float | None) -> list[str]:
    reasons: list[str] = []
    if not step.reversible:
        reasons.append("비가역 작업은 사람의 판단과 별도 실행 통제가 필요합니다.")
    if (
        score is None
        or score < MIN_READINESS_SCORE
        or (step.exception_rate is not None and step.exception_rate > MAX_EXCEPTION_RATE)
    ):
        reasons.append("자료·규칙·예외 처리가 충분히 정리되지 않았습니다.")
    if step.evidence_status not in (SourceStatus.OBSERVED, SourceStatus.DOCUMENTED):
        reasons.append("진술 또는 미확인 정보만으로 자동화 수준을 높이지 않습니다.")
    if step.control_point or step.decision_impact != DecisionImpact.ADMINISTRATIVE:
        reasons.append("통제 결정과 금전·권리·안전 영향의 판단은 사람에게 남깁니다.")
    return reasons


def _step(step: Step) -> StepAssessment:
    blockers = _blockers(step)
    score = None
    if (
        step.repetitive is not None
        and step.digital_readiness is not None
        and step.rule_clarity is not None
        and step.exception_rate is not None
    ):
        score = 25 * (
            step.repetitive + step.digital_readiness + step.rule_clarity + 1 - step.exception_rate
        )
    match step.risk:
        case Risk.LOW:
            penalty = 0
            mode = AutomationMode.AUTOMATE
        case Risk.MEDIUM:
            penalty = 15
            mode = AutomationMode.APPROVAL
        case Risk.HIGH:
            penalty = 35
            mode = AutomationMode.APPROVAL
        case Risk.CRITICAL:
            penalty = 60
            mode = AutomationMode.ASSIST
        case unreachable:
            assert_never(unreachable)
    reasons = ["점수는 도입 우선순위 휴리스틱이며 절감 효과의 실측값이 아닙니다."]
    assist_reasons = _assist_reasons(step, score)
    if assist_reasons:
        mode = AutomationMode.ASSIST
        reasons.extend(assist_reasons)
    if blockers:
        mode = AutomationMode.DEFER
        reasons.extend(blockers)
    return StepAssessment(
        step_id=step.id,
        mode=mode,
        priority_score=round(max(0, score - penalty), 2) if score is not None else None,
        baseline_hours_monthly=round(step.monthly_cases * step.minutes_per_case / 60, 2)
        if step.value_status == SourceStatus.OBSERVED
        and step.monthly_cases is not None
        and step.minutes_per_case is not None
        else None,
        reasons=tuple(reasons),
        next_steps=(
            "현행 처리시간·오류율의 기준선을 측정합니다.",
            "예외 사례를 포함한 평가셋으로 그림자 운영합니다.",
        ),
    )


def assess(intake: BusinessIntake) -> Assessment:
    assessed = {step.id: _step(step) for step in intake.steps}
    pending = set(assessed)
    resolved: set[str] = set()
    while pending:
        for step in intake.steps:
            if step.id not in pending or not set(step.depends_on) <= resolved:
                continue
            if any(assessed[key].mode == AutomationMode.DEFER for key in step.depends_on):
                assessed[step.id] = assessed[step.id].model_copy(
                    update={
                        "mode": AutomationMode.DEFER,
                        "reasons": (
                            *assessed[step.id].reasons,
                            "선행 단계의 도입 조건이 충족되지 않았습니다.",
                        ),
                    }
                )
            pending.remove(step.id)
            resolved.add(step.id)
    warnings = [
        "처리시간과 대기·인계·재작업을 함께 측정해야 전체 업무의 병목을 판단할 수 있습니다."
    ]
    if intake.process_owner is None:
        warnings.append("프로세스 책임자가 없어 도입 채택을 보류해야 합니다.")
        assessed = {
            key: item.model_copy(update={"mode": AutomationMode.DEFER})
            for key, item in assessed.items()
        }
    return Assessment(
        business=intake.business,
        steps=tuple(assessed[step.id] for step in intake.steps),
        control_points=tuple(step.id for step in intake.steps if step.control_point),
        process_warnings=tuple(warnings),
    )
