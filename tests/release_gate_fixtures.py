from ax_starter.release_gate import (
    CaseMeasurement,
    EvaluationArtifactRef,
    EvaluationTarget,
    EvaluationTargetManifest,
    ReleaseCaseResult,
    ReleaseCriteria,
    ReleaseEvaluation,
    canonical_case_set_sha256,
    canonical_criteria_sha256,
    canonical_manifest_sha256,
)


def artifact(name: str, digest_character: str) -> EvaluationArtifactRef:
    return EvaluationArtifactRef(version=f"{name}-v1", sha256=digest_character * 64)


def target(
    threshold: ReleaseCriteria,
    cases: tuple[ReleaseCaseResult, ...],
) -> EvaluationTarget:
    return EvaluationTarget(
        pack=artifact("pack", "1"),
        data_contract=artifact("data-contract", "2"),
        model=artifact("model", "3"),
        prompt=artifact("prompt", "4"),
        policy=artifact("policy", "5"),
        case_set=EvaluationArtifactRef(
            version="case-set-v1",
            sha256=canonical_case_set_sha256(cases),
        ),
        rubric=EvaluationArtifactRef(
            version="rubric-v1",
            sha256=canonical_criteria_sha256(threshold),
        ),
        code=artifact("code", "8"),
    )


def manifest(
    threshold: ReleaseCriteria,
    cases: tuple[ReleaseCaseResult, ...],
) -> EvaluationTargetManifest:
    evaluation_target = target(threshold, cases)
    return EvaluationTargetManifest(
        target=evaluation_target,
        manifest_sha256=canonical_manifest_sha256(evaluation_target),
    )


def passing_case() -> ReleaseCaseResult:
    return ReleaseCaseResult(
        id="case-1",
        domain="synthetic-support",
        fixture_digest="a" * 64,
        baseline=CaseMeasurement(
            quality=0.9,
            unnecessary_refusal=False,
            latency_ms=80,
            cost=0.5,
        ),
        candidate=CaseMeasurement(
            quality=0.95,
            unnecessary_refusal=False,
            latency_ms=70,
            cost=0.4,
        ),
    )


def criteria() -> ReleaseCriteria:
    return ReleaseCriteria(
        minimum_quality=0.9,
        maximum_quality_regression=0,
        maximum_unnecessary_refusal_rate=0.1,
        maximum_refusal_rate_increase=0,
        maximum_mean_latency_ms=100,
        maximum_latency_increase_ms=10,
        maximum_mean_cost=1,
        maximum_cost_increase=0.1,
    )


def evaluation(
    threshold: ReleaseCriteria | None = None,
    cases: tuple[ReleaseCaseResult, ...] | None = None,
) -> ReleaseEvaluation:
    applied_criteria = threshold or criteria()
    unbound_cases = cases or (passing_case(),)
    target_manifest = manifest(applied_criteria, unbound_cases)
    bound_cases = tuple(
        case.model_copy(update={"target_manifest_sha256": target_manifest.manifest_sha256})
        for case in unbound_cases
    )
    return ReleaseEvaluation(
        baseline_id="baseline-1",
        candidate_id="candidate-2",
        evidence_digest="b" * 64,
        synthetic=True,
        field_reviewer="field-reviewer",
        target_manifest=target_manifest,
        evidence_target_manifest_sha256=target_manifest.manifest_sha256,
        cases=bound_cases,
    )
