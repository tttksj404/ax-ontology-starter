from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Final, Literal, Self

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import Contract, Identifier

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_MANIFEST_SCHEMA: Final = "release-evaluation-target/v1"
_CRITERIA_SCHEMA: Final = "release-criteria/v1"
_CASE_SET_SCHEMA: Final = "release-case-set/v1"


class EvaluationArtifactRef(Contract):
    version: Identifier
    sha256: Sha256Digest


class EvaluationTarget(Contract):
    pack: EvaluationArtifactRef
    data_contract: EvaluationArtifactRef
    model: EvaluationArtifactRef
    prompt: EvaluationArtifactRef
    policy: EvaluationArtifactRef
    case_set: EvaluationArtifactRef
    rubric: EvaluationArtifactRef
    code: EvaluationArtifactRef


def canonical_manifest_sha256(target: EvaluationTarget) -> str:
    artifacts = (
        ("pack", target.pack),
        ("data_contract", target.data_contract),
        ("model", target.model),
        ("prompt", target.prompt),
        ("policy", target.policy),
        ("case_set", target.case_set),
        ("rubric", target.rubric),
        ("code", target.code),
    )
    artifact_lines = (
        f"{name}|{artifact.version}|{artifact.sha256}" for name, artifact in artifacts
    )
    canonical = "\n".join((_MANIFEST_SCHEMA, *artifact_lines))
    return sha256(canonical.encode()).hexdigest()


class EvaluationTargetManifest(Contract):
    target: EvaluationTarget
    manifest_sha256: Sha256Digest

    @model_validator(mode="after")
    def manifest_digest_must_match_target(self) -> Self:
        if self.manifest_sha256 != canonical_manifest_sha256(self.target):
            raise PydanticCustomError(
                "manifest_digest_mismatch",
                "manifest digest does not match canonical evaluation target",
            )
        return self


class VetoReason(StrEnum):
    SAFETY_FAILURE = "safety_failure"
    PRIVILEGE_VIOLATION = "privilege_violation"
    DELETION_OMISSION = "deletion_omission"


class CriterionFailure(StrEnum):
    QUALITY_MINIMUM = "quality_minimum"
    QUALITY_REGRESSION = "quality_regression"
    REFUSAL_RATE = "unnecessary_refusal_rate"
    REFUSAL_REGRESSION = "unnecessary_refusal_regression"
    LATENCY_LIMIT = "latency_limit"
    LATENCY_REGRESSION = "latency_regression"
    COST_LIMIT = "cost_limit"
    COST_REGRESSION = "cost_regression"


class ReleaseBoundary(StrEnum):
    EVALUATION_TARGET_MANIFEST_MISSING = "evaluation_target_manifest_missing"
    EVIDENCE_TARGET_MISMATCH = "evidence_target_mismatch"
    CASE_TARGET_MISMATCH = "case_target_mismatch"
    RUBRIC_DIGEST_MISMATCH = "rubric_digest_mismatch"
    CASE_SET_DIGEST_MISMATCH = "case_set_digest_mismatch"
    SYNTHETIC_EVIDENCE_ONLY = "synthetic_evidence_only"
    FIELD_REVIEWER_MISSING = "field_reviewer_missing"


class ReleaseDecision(StrEnum):
    BLOCKED = "blocked"
    SYNTHETIC_EVALUATION_ONLY = "synthetic_evaluation_only"
    FIELD_REVIEW_REQUIRED = "field_review_required"
    ELIGIBLE_FOR_FIELD_REVIEW = "eligible_for_field_review"


class CaseMeasurement(Contract):
    quality: float = Field(ge=0, le=1, allow_inf_nan=False)
    unnecessary_refusal: bool
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    cost: float = Field(ge=0, allow_inf_nan=False)


class ReleaseCaseResult(Contract):
    id: Identifier
    domain: Identifier
    fixture_digest: Sha256Digest
    baseline: CaseMeasurement
    candidate: CaseMeasurement
    safety_failure: bool = False
    privilege_violation: bool = False
    deletion_omission: bool = False
    target_manifest_sha256: Sha256Digest | None = None


class ReleaseEvaluation(Contract):
    baseline_id: Identifier
    candidate_id: Identifier
    evidence_digest: Sha256Digest
    synthetic: bool
    field_reviewer: str | None = Field(default=None, min_length=1, max_length=120)
    target_manifest: EvaluationTargetManifest | None = None
    evidence_target_manifest_sha256: Sha256Digest | None = None
    cases: tuple[ReleaseCaseResult, ...] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise PydanticCustomError(
                "duplicate_release_case_id",
                "release case ids must be unique",
            )
        return self


class ReleaseCriteria(Contract):
    minimum_quality: float = Field(ge=0, le=1, allow_inf_nan=False)
    maximum_quality_regression: float = Field(ge=0, le=1, allow_inf_nan=False)
    maximum_unnecessary_refusal_rate: float = Field(ge=0, le=1, allow_inf_nan=False)
    maximum_refusal_rate_increase: float = Field(ge=0, le=1, allow_inf_nan=False)
    maximum_mean_latency_ms: float = Field(ge=0, allow_inf_nan=False)
    maximum_latency_increase_ms: float = Field(ge=0, allow_inf_nan=False)
    maximum_mean_cost: float = Field(ge=0, allow_inf_nan=False)
    maximum_cost_increase: float = Field(ge=0, allow_inf_nan=False)


def canonical_criteria_sha256(criteria: ReleaseCriteria) -> str:
    return sha256(f"{_CRITERIA_SCHEMA}\n{criteria.model_dump_json()}".encode()).hexdigest()


def canonical_case_set_sha256(cases: tuple[ReleaseCaseResult, ...]) -> str:
    fixture_lines = sorted(f"{case.id}|{case.domain}|{case.fixture_digest}" for case in cases)
    canonical = "\n".join((_CASE_SET_SCHEMA, *fixture_lines))
    return sha256(canonical.encode()).hexdigest()


class MetricSummary(Contract):
    quality: float
    unnecessary_refusal_rate: float
    mean_latency_ms: float
    mean_cost: float


class ReleaseGate(Contract):
    baseline_id: Identifier
    candidate_id: Identifier
    evidence_digest: Sha256Digest
    target_manifest_sha256: Sha256Digest | None
    field_reviewer: str | None
    decision: ReleaseDecision
    assurance: Literal["input_derived_recommendation"] = "input_derived_recommendation"
    live_validated: Literal[False] = False
    evidence_origin_verified: Literal[False] = False
    eligible_for_field_review: bool
    vetoes: tuple[VetoReason, ...]
    failed_criteria: tuple[CriterionFailure, ...]
    boundaries: tuple[ReleaseBoundary, ...]
    baseline: MetricSummary
    candidate: MetricSummary


def _summarize(measurements: tuple[CaseMeasurement, ...]) -> MetricSummary:
    count = len(measurements)
    return MetricSummary(
        quality=sum(item.quality for item in measurements) / count,
        unnecessary_refusal_rate=sum(item.unnecessary_refusal for item in measurements) / count,
        mean_latency_ms=sum(item.latency_ms for item in measurements) / count,
        mean_cost=sum(item.cost for item in measurements) / count,
    )


def _target_boundaries(
    evaluation: ReleaseEvaluation,
    criteria: ReleaseCriteria,
) -> tuple[str | None, tuple[ReleaseBoundary, ...]]:
    manifest = evaluation.target_manifest
    if manifest is None:
        return None, (ReleaseBoundary.EVALUATION_TARGET_MANIFEST_MISSING,)
    digest = manifest.manifest_sha256
    checks = (
        (
            evaluation.evidence_target_manifest_sha256 != digest,
            ReleaseBoundary.EVIDENCE_TARGET_MISMATCH,
        ),
        (
            any(case.target_manifest_sha256 != digest for case in evaluation.cases),
            ReleaseBoundary.CASE_TARGET_MISMATCH,
        ),
        (
            canonical_criteria_sha256(criteria) != manifest.target.rubric.sha256,
            ReleaseBoundary.RUBRIC_DIGEST_MISMATCH,
        ),
        (
            canonical_case_set_sha256(evaluation.cases) != manifest.target.case_set.sha256,
            ReleaseBoundary.CASE_SET_DIGEST_MISMATCH,
        ),
    )
    return digest, tuple(boundary for failed, boundary in checks if failed)


def evaluate_release(evaluation: ReleaseEvaluation, criteria: ReleaseCriteria) -> ReleaseGate:
    baseline = _summarize(tuple(case.baseline for case in evaluation.cases))
    candidate = _summarize(tuple(case.candidate for case in evaluation.cases))
    vetoes: list[VetoReason] = []
    if any(case.safety_failure for case in evaluation.cases):
        vetoes.append(VetoReason.SAFETY_FAILURE)
    if any(case.privilege_violation for case in evaluation.cases):
        vetoes.append(VetoReason.PRIVILEGE_VIOLATION)
    if any(case.deletion_omission for case in evaluation.cases):
        vetoes.append(VetoReason.DELETION_OMISSION)
    failures: list[CriterionFailure] = []
    checks = (
        (candidate.quality < criteria.minimum_quality, CriterionFailure.QUALITY_MINIMUM),
        (
            baseline.quality - candidate.quality > criteria.maximum_quality_regression,
            CriterionFailure.QUALITY_REGRESSION,
        ),
        (
            candidate.unnecessary_refusal_rate > criteria.maximum_unnecessary_refusal_rate,
            CriterionFailure.REFUSAL_RATE,
        ),
        (
            candidate.unnecessary_refusal_rate - baseline.unnecessary_refusal_rate
            > criteria.maximum_refusal_rate_increase,
            CriterionFailure.REFUSAL_REGRESSION,
        ),
        (
            candidate.mean_latency_ms > criteria.maximum_mean_latency_ms,
            CriterionFailure.LATENCY_LIMIT,
        ),
        (
            candidate.mean_latency_ms - baseline.mean_latency_ms
            > criteria.maximum_latency_increase_ms,
            CriterionFailure.LATENCY_REGRESSION,
        ),
        (candidate.mean_cost > criteria.maximum_mean_cost, CriterionFailure.COST_LIMIT),
        (
            candidate.mean_cost - baseline.mean_cost > criteria.maximum_cost_increase,
            CriterionFailure.COST_REGRESSION,
        ),
    )
    failures.extend(failure for failed, failure in checks if failed)
    target_manifest_sha256, target_boundaries = _target_boundaries(evaluation, criteria)
    boundaries = list(target_boundaries)
    if vetoes or failures or boundaries:
        decision = ReleaseDecision.BLOCKED
        eligible_for_field_review = False
    elif evaluation.synthetic:
        decision = ReleaseDecision.SYNTHETIC_EVALUATION_ONLY
        eligible_for_field_review = False
        boundaries.append(ReleaseBoundary.SYNTHETIC_EVIDENCE_ONLY)
    elif evaluation.field_reviewer is None:
        decision = ReleaseDecision.FIELD_REVIEW_REQUIRED
        eligible_for_field_review = False
        boundaries.append(ReleaseBoundary.FIELD_REVIEWER_MISSING)
    else:
        decision = ReleaseDecision.ELIGIBLE_FOR_FIELD_REVIEW
        eligible_for_field_review = True
    return ReleaseGate(
        baseline_id=evaluation.baseline_id,
        candidate_id=evaluation.candidate_id,
        evidence_digest=evaluation.evidence_digest,
        target_manifest_sha256=target_manifest_sha256,
        field_reviewer=evaluation.field_reviewer,
        decision=decision,
        eligible_for_field_review=eligible_for_field_review,
        vetoes=tuple(vetoes),
        failed_criteria=tuple(failures),
        boundaries=tuple(boundaries),
        baseline=baseline,
        candidate=candidate,
    )
