from pathlib import Path

import pytest

from ax_starter.common import Sensitivity
from ax_starter.intake import (
    BusinessIntake,
    DecisionImpact,
    Risk,
    SourceStatus,
    Step,
)
from ax_starter.onboarding import assess_onboarding
from ax_starter.onboarding_contracts import (
    ApprovalRequirement,
    ApprovalState,
    CompanyApprovals,
    CompanyProfile,
    DeploymentMode,
    EvidenceGap,
    OnboardingGap,
    OnboardingRequest,
    PolicyConflict,
    ProfileEvidence,
    ReadinessDecision,
)


def complete_intake() -> BusinessIntake:
    return BusinessIntake(
        business="합성 구매 검토",
        objective="검토 대기시간 측정",
        process_owner="process-owner",
        industry="synthetic",
        constraints=("외부 전송 금지",),
        steps=(
            Step(
                id="review",
                name="요청 검토",
                owner="operator",
                inputs=("request",),
                outputs=("decision",),
                systems=("synthetic-erp",),
                rules=("synthetic-rule",),
                exceptions=("missing-field",),
                evidence_sources=("synthetic-sop",),
                risk=Risk.MEDIUM,
                sensitivity=Sensitivity.CONFIDENTIAL,
                authorized=True,
                reversible=True,
                evidence_status=SourceStatus.DOCUMENTED,
                value_status=SourceStatus.DOCUMENTED,
                control_point=True,
                decision_impact=DecisionImpact.ADMINISTRATIVE,
            ),
        ),
    )


def complete_profile() -> CompanyProfile:
    return CompanyProfile(
        company="Synthetic Co",
        industry="synthetic",
        jurisdictions=("kr",),
        owner="company-owner",
        deployment_modes=(DeploymentMode.PRIVATE,),
        maximum_sensitivity=Sensitivity.CONFIDENTIAL,
        allowed_transfers=(),
        allowed_regions=("kr",),
        allowed_models=("candidate-a",),
        allowed_tools=("retrieval",),
        retention_days=30,
        authorized_groups=("operators",),
        risk_owner="risk-owner",
        field_reviewer="field-reviewer",
        evidence=ProfileEvidence(
            governance=SourceStatus.DOCUMENTED,
            deployment=SourceStatus.DOCUMENTED,
            data_classification=SourceStatus.DOCUMENTED,
            transfer_policy=SourceStatus.DOCUMENTED,
            region_policy=SourceStatus.DOCUMENTED,
            model_policy=SourceStatus.DOCUMENTED,
            tool_policy=SourceStatus.DOCUMENTED,
            retention_policy=SourceStatus.DOCUMENTED,
            access_policy=SourceStatus.DOCUMENTED,
            risk_assessment=SourceStatus.DOCUMENTED,
            field_evaluation=SourceStatus.DOCUMENTED,
        ),
        approvals=CompanyApprovals(
            process_owner=ApprovalState.APPROVED,
            security=ApprovalState.APPROVED,
            privacy=ApprovalState.APPROVED,
            risk_owner=ApprovalState.APPROVED,
            field_reviewer=ApprovalState.APPROVED,
        ),
    )


def complete_request() -> OnboardingRequest:
    return OnboardingRequest(
        profile=complete_profile(),
        intake=complete_intake(),
        requested_deployment=DeploymentMode.PRIVATE,
        requested_sensitivity=Sensitivity.CONFIDENTIAL,
        requested_transfers=(),
        requested_regions=("kr",),
        requested_models=("candidate-a",),
        requested_tools=("retrieval",),
        requested_groups=("operators",),
    )


def test_unknown_controls_block_readiness_when_profile_is_self_reported() -> None:
    # Given
    profile = CompanyProfile(
        company="Synthetic Co",
        industry="synthetic",
        jurisdictions=("kr",),
    )
    request = complete_request().model_copy(update={"profile": profile})
    # When
    report = assess_onboarding(request)
    # Then
    assert report.decision == ReadinessDecision.BLOCKED
    assert OnboardingGap.MAXIMUM_SENSITIVITY_UNKNOWN in report.missing_information
    assert ApprovalRequirement.SECURITY in report.required_approvals
    assert report.live_validated is False
    assert report.security_certified is False


def test_complete_controls_allow_only_preliminary_pilot_review() -> None:
    # Given
    request = complete_request()
    # When
    report = assess_onboarding(request)
    # Then
    assert report.decision == ReadinessDecision.PILOT_REVIEW
    assert report.assurance == "self_reported_readiness"
    assert report.live_validated is False
    assert report.security_certified is False


@pytest.mark.parametrize(
    ("field", "gap"),
    [
        ("region_policy", EvidenceGap.REGION_POLICY),
        ("model_policy", EvidenceGap.MODEL_POLICY),
        ("tool_policy", EvidenceGap.TOOL_POLICY),
    ],
)
def test_unknown_critical_policy_evidence_blocks_readiness(
    field: str,
    gap: EvidenceGap,
) -> None:
    # Given
    evidence = complete_profile().evidence.model_copy(update={field: SourceStatus.UNKNOWN})
    profile = complete_profile().model_copy(update={"evidence": evidence})
    request = complete_request().model_copy(update={"profile": profile})
    # When
    report = assess_onboarding(request)
    # Then
    assert report.decision == ReadinessDecision.BLOCKED
    assert report.evidence_gaps == (gap,)


@pytest.mark.parametrize("field", ["region_policy", "model_policy", "tool_policy"])
def test_reported_critical_policy_is_unverified_self_report(field: str) -> None:
    # Given
    evidence = complete_profile().evidence.model_copy(update={field: SourceStatus.REPORTED})
    profile = complete_profile().model_copy(update={"evidence": evidence})
    request = complete_request().model_copy(update={"profile": profile})
    # When
    report = assess_onboarding(request)
    # Then
    assert report.decision == ReadinessDecision.PILOT_REVIEW
    assert report.assurance == "self_reported_readiness"
    assert report.live_validated is False
    assert report.security_certified is False


def test_requested_model_blocks_when_company_policy_does_not_allow_it() -> None:
    # Given
    profile = complete_profile().model_copy(update={"allowed_models": ("candidate-b",)})
    request = complete_request().model_copy(update={"profile": profile})
    # When
    report = assess_onboarding(request)
    # Then
    assert report.decision == ReadinessDecision.BLOCKED
    assert PolicyConflict.MODEL_NOT_ALLOWED in report.policy_conflicts


def test_rejected_approval_is_preserved_as_a_blocking_reason() -> None:
    # Given
    approvals = complete_profile().approvals.model_copy(update={"security": ApprovalState.REJECTED})
    profile = complete_profile().model_copy(update={"approvals": approvals})
    request = complete_request().model_copy(update={"profile": profile})
    # When
    report = assess_onboarding(request)
    # Then
    assert report.decision == ReadinessDecision.BLOCKED
    assert report.rejected_approvals == (ApprovalRequirement.SECURITY,)


def test_synthetic_onboarding_example_is_executable() -> None:
    # Given
    path = Path(__file__).parents[1] / "examples" / "v0.2" / "onboarding-request.json"
    request = OnboardingRequest.model_validate_json(path.read_text(encoding="utf-8"))
    # When
    report = assess_onboarding(request)
    # Then
    assert report.decision == ReadinessDecision.PILOT_REVIEW
