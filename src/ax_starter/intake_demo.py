from typing import Final

from ax_starter.demo import DemoDomain, domain_values
from ax_starter.intake import BusinessIntake, DecisionImpact, Risk, SourceStatus, Step

FINAL_DECISION_INDEX: Final = 4
EXCEPTION_REVIEW_INDEX: Final = 3


def demo_intake(domain: DemoDomain = DemoDomain.PROCUREMENT) -> BusinessIntake:
    label, _, _, _, sensitivity = domain_values(domain)
    steps: list[Step] = []
    stages = ("요청 접수", "중복 확인", "근거 대조", "예외 검토", "최종 결정", "완료 보고")
    for index, name in enumerate(stages):
        steps.append(
            Step(
                id=f"step-{index + 1}",
                name=name,
                owner="합성 업무 담당자",
                inputs=("업무 요청" if index == 0 else f"step-{index}의 산출물",),
                outputs=(f"{name} 기록",),
                systems=("기존 업무 시스템",),
                rules=("도메인팩의 승인된 SOP",),
                exceptions=("근거 누락",),
                evidence_sources=("sop-1",),
                depends_on=() if index == 0 else (f"step-{index}",),
                monthly_cases=100,
                minutes_per_case=5 + index * 2,
                repetitive=0.8,
                digital_readiness=0.8,
                rule_clarity=0.8,
                exception_rate=0.1,
                risk=Risk.CRITICAL
                if index == FINAL_DECISION_INDEX
                else Risk.MEDIUM
                if index == EXCEPTION_REVIEW_INDEX
                else Risk.LOW,
                sensitivity=sensitivity,
                authorized=True,
                reversible=index != FINAL_DECISION_INDEX,
                kpi="처리시간 및 재작업률",
                evidence_status=SourceStatus.DOCUMENTED,
                value_status=SourceStatus.REPORTED,
                control_point=index == FINAL_DECISION_INDEX,
                decision_impact=DecisionImpact.UNKNOWN
                if index == FINAL_DECISION_INDEX
                else DecisionImpact.ADMINISTRATIVE,
            )
        )
    return BusinessIntake(
        business=label,
        objective="근거 확인과 검토 기록의 일관성 향상",
        process_owner="합성 업무 책임자",
        industry=domain,
        constraints=("실제 발주·지급·인사 결정을 자동 실행하지 않음",),
        steps=tuple(steps),
    )
