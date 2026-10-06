from dataclasses import dataclass
from typing import Final, assert_never

from ax_starter.intake import SourceStatus
from ax_starter.onboarding_contracts import (
    ApprovalRequirement,
    ApprovalState,
    EvidenceGap,
    OnboardingGap,
    OnboardingNextStep,
    OnboardingReport,
    OnboardingRequest,
    PolicyConflict,
    ProfileEvidence,
    ReadinessDecision,
)

CRITICAL_GAPS: Final = frozenset(
    {
        OnboardingGap.DEPLOYMENT_POLICY_UNKNOWN,
        OnboardingGap.MAXIMUM_SENSITIVITY_UNKNOWN,
        OnboardingGap.TRANSFER_POLICY_UNKNOWN,
        OnboardingGap.REGION_POLICY_UNKNOWN,
        OnboardingGap.MODEL_POLICY_UNKNOWN,
        OnboardingGap.TOOL_POLICY_UNKNOWN,
        OnboardingGap.ACCESS_POLICY_UNKNOWN,
        OnboardingGap.PROCESS_OWNER_UNKNOWN,
    }
)
CRITICAL_EVIDENCE: Final = frozenset(
    {
        EvidenceGap.DEPLOYMENT,
        EvidenceGap.DATA_CLASSIFICATION,
        EvidenceGap.TRANSFER_POLICY,
        EvidenceGap.REGION_POLICY,
        EvidenceGap.MODEL_POLICY,
        EvidenceGap.TOOL_POLICY,
        EvidenceGap.ACCESS_POLICY,
    }
)


@dataclass(frozen=True, slots=True)
class _ApprovalReview:
    required: frozenset[ApprovalRequirement]
    rejected: frozenset[ApprovalRequirement]


def _missing_information(request: OnboardingRequest) -> set[OnboardingGap]:
    profile = request.profile
    gaps: set[OnboardingGap] = set()
    checks = (
        (profile.owner, OnboardingGap.COMPANY_OWNER_UNKNOWN),
        (profile.deployment_modes, OnboardingGap.DEPLOYMENT_POLICY_UNKNOWN),
        (profile.maximum_sensitivity, OnboardingGap.MAXIMUM_SENSITIVITY_UNKNOWN),
        (profile.allowed_transfers, OnboardingGap.TRANSFER_POLICY_UNKNOWN),
        (profile.allowed_regions, OnboardingGap.REGION_POLICY_UNKNOWN),
        (profile.allowed_models, OnboardingGap.MODEL_POLICY_UNKNOWN),
        (profile.allowed_tools, OnboardingGap.TOOL_POLICY_UNKNOWN),
        (profile.retention_days, OnboardingGap.RETENTION_POLICY_UNKNOWN),
        (profile.authorized_groups, OnboardingGap.ACCESS_POLICY_UNKNOWN),
        (profile.risk_owner, OnboardingGap.RISK_OWNER_UNKNOWN),
        (profile.field_reviewer, OnboardingGap.FIELD_REVIEWER_UNKNOWN),
        (request.intake.process_owner, OnboardingGap.PROCESS_OWNER_UNKNOWN),
    )
    gaps.update(gap for value, gap in checks if value is None)
    return gaps


def _evidence_gaps(evidence: ProfileEvidence) -> set[EvidenceGap]:
    checks = (
        (evidence.governance, EvidenceGap.GOVERNANCE),
        (evidence.deployment, EvidenceGap.DEPLOYMENT),
        (evidence.data_classification, EvidenceGap.DATA_CLASSIFICATION),
        (evidence.transfer_policy, EvidenceGap.TRANSFER_POLICY),
        (evidence.region_policy, EvidenceGap.REGION_POLICY),
        (evidence.model_policy, EvidenceGap.MODEL_POLICY),
        (evidence.tool_policy, EvidenceGap.TOOL_POLICY),
        (evidence.retention_policy, EvidenceGap.RETENTION_POLICY),
        (evidence.access_policy, EvidenceGap.ACCESS_POLICY),
        (evidence.risk_assessment, EvidenceGap.RISK_ASSESSMENT),
        (evidence.field_evaluation, EvidenceGap.FIELD_EVALUATION),
    )
    gaps: set[EvidenceGap] = set()
    for status, gap in checks:
        match status:
            case SourceStatus.UNKNOWN:
                gaps.add(gap)
            case SourceStatus.OBSERVED | SourceStatus.DOCUMENTED | SourceStatus.REPORTED:
                pass
            case unreachable:
                assert_never(unreachable)
    return gaps


def _review_approvals(request: OnboardingRequest) -> _ApprovalReview:
    required: set[ApprovalRequirement] = set()
    rejected: set[ApprovalRequirement] = set()
    approvals = request.profile.approvals
    items = (
        (ApprovalRequirement.PROCESS_OWNER, approvals.process_owner),
        (ApprovalRequirement.SECURITY, approvals.security),
        (ApprovalRequirement.PRIVACY, approvals.privacy),
        (ApprovalRequirement.RISK_OWNER, approvals.risk_owner),
        (ApprovalRequirement.FIELD_REVIEWER, approvals.field_reviewer),
    )
    for requirement, state in items:
        match state:
            case ApprovalState.APPROVED:
                pass
            case ApprovalState.REJECTED:
                required.add(requirement)
                rejected.add(requirement)
            case ApprovalState.UNKNOWN:
                required.add(requirement)
            case unreachable:
                assert_never(unreachable)
    if any(not step.authorized for step in request.intake.steps):
        required.add(ApprovalRequirement.WORKFLOW_CHANGE)
    return _ApprovalReview(required=frozenset(required), rejected=frozenset(rejected))


def _policy_conflicts(request: OnboardingRequest) -> set[PolicyConflict]:
    profile = request.profile
    conflicts: set[PolicyConflict] = set()
    if (
        profile.deployment_modes is not None
        and request.requested_deployment not in profile.deployment_modes
    ):
        conflicts.add(PolicyConflict.DEPLOYMENT_NOT_ALLOWED)
    if (
        profile.maximum_sensitivity is not None
        and request.requested_sensitivity > profile.maximum_sensitivity
    ):
        conflicts.add(PolicyConflict.SENSITIVITY_EXCEEDED)
    comparisons = (
        (
            request.requested_transfers,
            profile.allowed_transfers,
            PolicyConflict.TRANSFER_NOT_ALLOWED,
        ),
        (request.requested_regions, profile.allowed_regions, PolicyConflict.REGION_NOT_ALLOWED),
        (request.requested_models, profile.allowed_models, PolicyConflict.MODEL_NOT_ALLOWED),
        (request.requested_tools, profile.allowed_tools, PolicyConflict.TOOL_NOT_ALLOWED),
        (request.requested_groups, profile.authorized_groups, PolicyConflict.GROUP_NOT_ALLOWED),
    )
    conflicts.update(
        conflict
        for requested, allowed, conflict in comparisons
        if allowed is not None and not set(requested) <= set(allowed)
    )
    if any(step.sensitivity > request.requested_sensitivity for step in request.intake.steps):
        conflicts.add(PolicyConflict.WORKFLOW_SENSITIVITY_EXCEEDED)
    return conflicts


def assess_onboarding(request: OnboardingRequest) -> OnboardingReport:
    missing = _missing_information(request)
    evidence = _evidence_gaps(request.profile.evidence)
    approval_review = _review_approvals(request)
    approvals = approval_review.required
    rejected = approval_review.rejected
    conflicts = _policy_conflicts(request)
    if conflicts or rejected or missing & CRITICAL_GAPS or evidence & CRITICAL_EVIDENCE:
        decision = ReadinessDecision.BLOCKED
    elif missing or evidence or approvals:
        decision = ReadinessDecision.ON_HOLD
    else:
        decision = ReadinessDecision.PILOT_REVIEW
    next_steps: list[OnboardingNextStep] = []
    if missing:
        next_steps.append(OnboardingNextStep.COMPLETE_PROFILE)
    if conflicts:
        next_steps.append(OnboardingNextStep.RESOLVE_POLICY_CONFLICTS)
    if evidence:
        next_steps.append(OnboardingNextStep.COLLECT_EVIDENCE)
    if approvals:
        next_steps.append(OnboardingNextStep.OBTAIN_APPROVALS)
    match decision:
        case ReadinessDecision.PILOT_REVIEW:
            next_steps.append(OnboardingNextStep.RUN_CONTROLLED_PILOT)
        case ReadinessDecision.BLOCKED | ReadinessDecision.ON_HOLD:
            pass
        case unreachable:
            assert_never(unreachable)
    return OnboardingReport(
        decision=decision,
        missing_information=tuple(sorted(missing, key=lambda item: item.value)),
        required_approvals=tuple(sorted(approvals, key=lambda item: item.value)),
        rejected_approvals=tuple(sorted(rejected, key=lambda item: item.value)),
        evidence_gaps=tuple(sorted(evidence, key=lambda item: item.value)),
        policy_conflicts=tuple(sorted(conflicts, key=lambda item: item.value)),
        next_steps=tuple(next_steps),
    )
