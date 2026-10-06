from enum import StrEnum
from typing import Literal

from pydantic import Field

from ax_starter.common import Contract, Identifier, Sensitivity
from ax_starter.intake import BusinessIntake, SourceStatus


class DeploymentMode(StrEnum):
    OFFLINE = "offline"
    PRIVATE = "private"
    GATEWAY = "gateway"
    HYBRID = "hybrid"


class ApprovalState(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class ReadinessDecision(StrEnum):
    BLOCKED = "blocked"
    ON_HOLD = "on_hold"
    PILOT_REVIEW = "pilot_review"


class OnboardingGap(StrEnum):
    COMPANY_OWNER_UNKNOWN = "company_owner_unknown"
    DEPLOYMENT_POLICY_UNKNOWN = "deployment_policy_unknown"
    MAXIMUM_SENSITIVITY_UNKNOWN = "maximum_sensitivity_unknown"
    TRANSFER_POLICY_UNKNOWN = "transfer_policy_unknown"
    REGION_POLICY_UNKNOWN = "region_policy_unknown"
    MODEL_POLICY_UNKNOWN = "model_policy_unknown"
    TOOL_POLICY_UNKNOWN = "tool_policy_unknown"
    RETENTION_POLICY_UNKNOWN = "retention_policy_unknown"
    ACCESS_POLICY_UNKNOWN = "access_policy_unknown"
    RISK_OWNER_UNKNOWN = "risk_owner_unknown"
    FIELD_REVIEWER_UNKNOWN = "field_reviewer_unknown"
    PROCESS_OWNER_UNKNOWN = "process_owner_unknown"


class EvidenceGap(StrEnum):
    GOVERNANCE = "governance_evidence_unknown"
    DEPLOYMENT = "deployment_evidence_unknown"
    DATA_CLASSIFICATION = "data_classification_evidence_unknown"
    TRANSFER_POLICY = "transfer_policy_evidence_unknown"
    REGION_POLICY = "region_policy_evidence_unknown"
    MODEL_POLICY = "model_policy_evidence_unknown"
    TOOL_POLICY = "tool_policy_evidence_unknown"
    RETENTION_POLICY = "retention_policy_evidence_unknown"
    ACCESS_POLICY = "access_policy_evidence_unknown"
    RISK_ASSESSMENT = "risk_assessment_evidence_unknown"
    FIELD_EVALUATION = "field_evaluation_evidence_unknown"


class ApprovalRequirement(StrEnum):
    PROCESS_OWNER = "process_owner_approval"
    SECURITY = "security_approval"
    PRIVACY = "privacy_approval"
    RISK_OWNER = "risk_owner_approval"
    FIELD_REVIEWER = "field_reviewer_approval"
    WORKFLOW_CHANGE = "workflow_change_approval"


class PolicyConflict(StrEnum):
    DEPLOYMENT_NOT_ALLOWED = "deployment_not_allowed"
    SENSITIVITY_EXCEEDED = "sensitivity_exceeded"
    TRANSFER_NOT_ALLOWED = "transfer_not_allowed"
    REGION_NOT_ALLOWED = "region_not_allowed"
    MODEL_NOT_ALLOWED = "model_not_allowed"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    GROUP_NOT_ALLOWED = "group_not_allowed"
    WORKFLOW_SENSITIVITY_EXCEEDED = "workflow_sensitivity_exceeded"


class OnboardingNextStep(StrEnum):
    COMPLETE_PROFILE = "complete_profile"
    RESOLVE_POLICY_CONFLICTS = "resolve_policy_conflicts"
    COLLECT_EVIDENCE = "collect_evidence"
    OBTAIN_APPROVALS = "obtain_approvals"
    RUN_CONTROLLED_PILOT = "run_controlled_pilot"


class ProfileEvidence(Contract):
    governance: SourceStatus = SourceStatus.UNKNOWN
    deployment: SourceStatus = SourceStatus.UNKNOWN
    data_classification: SourceStatus = SourceStatus.UNKNOWN
    transfer_policy: SourceStatus = SourceStatus.UNKNOWN
    region_policy: SourceStatus = SourceStatus.UNKNOWN
    model_policy: SourceStatus = SourceStatus.UNKNOWN
    tool_policy: SourceStatus = SourceStatus.UNKNOWN
    retention_policy: SourceStatus = SourceStatus.UNKNOWN
    access_policy: SourceStatus = SourceStatus.UNKNOWN
    risk_assessment: SourceStatus = SourceStatus.UNKNOWN
    field_evaluation: SourceStatus = SourceStatus.UNKNOWN


class CompanyApprovals(Contract):
    process_owner: ApprovalState = ApprovalState.UNKNOWN
    security: ApprovalState = ApprovalState.UNKNOWN
    privacy: ApprovalState = ApprovalState.UNKNOWN
    risk_owner: ApprovalState = ApprovalState.UNKNOWN
    field_reviewer: ApprovalState = ApprovalState.UNKNOWN


class CompanyProfile(Contract):
    company: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=120)
    jurisdictions: tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    owner: str | None = Field(default=None, min_length=1, max_length=120)
    deployment_modes: tuple[DeploymentMode, ...] | None = Field(default=None, max_length=4)
    maximum_sensitivity: Sensitivity | None = None
    allowed_transfers: tuple[Identifier, ...] | None = Field(default=None, max_length=30)
    allowed_regions: tuple[Identifier, ...] | None = Field(default=None, max_length=30)
    allowed_models: tuple[Identifier, ...] | None = Field(default=None, max_length=30)
    allowed_tools: tuple[Identifier, ...] | None = Field(default=None, max_length=100)
    retention_days: int | None = Field(default=None, ge=0, le=36_500)
    authorized_groups: tuple[Identifier, ...] | None = Field(default=None, max_length=100)
    risk_owner: str | None = Field(default=None, min_length=1, max_length=120)
    field_reviewer: str | None = Field(default=None, min_length=1, max_length=120)
    evidence: ProfileEvidence = Field(default_factory=ProfileEvidence)
    approvals: CompanyApprovals = Field(default_factory=CompanyApprovals)


class OnboardingRequest(Contract):
    profile: CompanyProfile
    intake: BusinessIntake
    requested_deployment: DeploymentMode
    requested_sensitivity: Sensitivity
    requested_transfers: tuple[Identifier, ...] = Field(default=(), max_length=30)
    requested_regions: tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    requested_models: tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    requested_tools: tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    requested_groups: tuple[Identifier, ...] = Field(min_length=1, max_length=100)


class OnboardingReport(Contract):
    decision: ReadinessDecision
    assurance: Literal["self_reported_readiness"] = "self_reported_readiness"
    live_validated: Literal[False] = False
    security_certified: Literal[False] = False
    missing_information: tuple[OnboardingGap, ...]
    required_approvals: tuple[ApprovalRequirement, ...]
    rejected_approvals: tuple[ApprovalRequirement, ...]
    evidence_gaps: tuple[EvidenceGap, ...]
    policy_conflicts: tuple[PolicyConflict, ...]
    next_steps: tuple[OnboardingNextStep, ...]
