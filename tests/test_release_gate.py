from pathlib import Path

import pytest
from pydantic import ValidationError

from ax_starter.release_gate import (
    CaseMeasurement,
    CriterionFailure,
    EvaluationTargetManifest,
    ReleaseBoundary,
    ReleaseCriteria,
    ReleaseDecision,
    ReleaseEvaluation,
    VetoReason,
    evaluate_release,
)
from tests.release_gate_fixtures import criteria, evaluation, passing_case, target


def test_manifest_digest_must_bind_the_canonical_target() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match="manifest_digest_mismatch"):
        _ = EvaluationTargetManifest(
            target=target(criteria(), (passing_case(),)),
            manifest_sha256="0" * 64,
        )


def test_manifest_and_evaluation_targets_must_match() -> None:
    # Given
    mismatched_case = passing_case().model_copy(update={"target_manifest_sha256": "a" * 64})
    subject = evaluation().model_copy(
        update={
            "evidence_target_manifest_sha256": "b" * 64,
            "cases": (mismatched_case,),
        }
    )
    # When
    gate = evaluate_release(subject, criteria())
    # Then
    assert gate.decision == ReleaseDecision.BLOCKED
    assert set(gate.boundaries) == {
        ReleaseBoundary.EVIDENCE_TARGET_MISMATCH,
        ReleaseBoundary.CASE_TARGET_MISMATCH,
    }


def test_runtime_criteria_must_match_the_manifest_rubric_digest() -> None:
    # Given
    strict = criteria()
    subject = evaluation(strict).model_copy(update={"synthetic": False})
    lenient = strict.model_copy(update={"minimum_quality": 0.0})
    # When
    gate = evaluate_release(subject, lenient)
    # Then
    assert gate.decision == ReleaseDecision.BLOCKED
    assert ReleaseBoundary.RUBRIC_DIGEST_MISMATCH in gate.boundaries


def test_runtime_fixture_set_must_match_the_manifest_case_set_digest() -> None:
    # Given
    subject = evaluation().model_copy(update={"synthetic": False})
    changed_fixture = subject.cases[0].model_copy(update={"fixture_digest": "f" * 64})
    changed = subject.model_copy(update={"cases": (changed_fixture,)})
    # When
    gate = evaluate_release(changed, criteria())
    # Then
    assert gate.decision == ReleaseDecision.BLOCKED
    assert ReleaseBoundary.CASE_SET_DIGEST_MISMATCH in gate.boundaries


def test_case_set_digest_excludes_baseline_and_candidate_measurements() -> None:
    # Given
    original = evaluation()
    remeasured_case = passing_case().model_copy(
        update={
            "candidate": passing_case().candidate.model_copy(update={"quality": 0.96}),
        }
    )
    remeasured = evaluation(cases=(remeasured_case,))
    # When / Then
    assert remeasured.target_manifest is not None
    assert original.target_manifest is not None
    assert (
        remeasured.target_manifest.target.case_set.sha256
        == original.target_manifest.target.case_set.sha256
    )
    gate = evaluate_release(remeasured.model_copy(update={"synthetic": False}), criteria())
    assert gate.decision == ReleaseDecision.ELIGIBLE_FOR_FIELD_REVIEW


def test_release_evaluation_rejects_duplicate_case_ids_before_averaging() -> None:
    # Given
    low_case = passing_case().model_copy(
        update={
            "id": "case-low",
            "fixture_digest": "0" * 64,
            "baseline": passing_case().baseline.model_copy(update={"quality": 0.4}),
            "candidate": passing_case().candidate.model_copy(update={"quality": 0.4}),
        }
    )
    inflated_cases = (low_case, *(passing_case() for _ in range(10)))
    # When / Then
    with pytest.raises(ValidationError, match="duplicate_release_case_id"):
        _ = evaluation(cases=inflated_cases)


def test_legacy_evaluation_without_manifest_is_valid_but_blocked() -> None:
    # Given
    legacy_case = passing_case().model_copy(update={"target_manifest_sha256": None})
    subject = evaluation().model_copy(
        update={
            "target_manifest": None,
            "evidence_target_manifest_sha256": None,
            "cases": (legacy_case,),
        }
    )
    # When
    gate = evaluate_release(subject, criteria())
    # Then
    assert gate.decision == ReleaseDecision.BLOCKED
    assert gate.eligible_for_field_review is False
    assert gate.boundaries == (ReleaseBoundary.EVALUATION_TARGET_MANIFEST_MISSING,)
    assert gate.target_manifest_sha256 is None


def test_safety_veto_blocks_even_when_quality_and_efficiency_are_perfect() -> None:
    # Given
    unsafe = passing_case().model_copy(update={"safety_failure": True})
    subject = evaluation(cases=(unsafe,))
    # When
    gate = evaluate_release(subject, criteria())
    # Then
    assert gate.decision == ReleaseDecision.BLOCKED
    assert gate.vetoes == (VetoReason.SAFETY_FAILURE,)
    assert gate.failed_criteria == ()


def test_metric_failures_are_derived_from_independent_criteria() -> None:
    # Given
    weak = passing_case().model_copy(
        update={
            "candidate": CaseMeasurement(
                quality=0.8,
                unnecessary_refusal=True,
                latency_ms=200,
                cost=2,
            )
        }
    )
    subject = evaluation(cases=(weak,))
    # When
    gate = evaluate_release(subject, criteria())
    # Then
    assert set(gate.failed_criteria) == {
        CriterionFailure.QUALITY_MINIMUM,
        CriterionFailure.QUALITY_REGRESSION,
        CriterionFailure.REFUSAL_RATE,
        CriterionFailure.REFUSAL_REGRESSION,
        CriterionFailure.LATENCY_LIMIT,
        CriterionFailure.LATENCY_REGRESSION,
        CriterionFailure.COST_LIMIT,
        CriterionFailure.COST_REGRESSION,
    }


def test_metric_gates_use_unrounded_values_above_thresholds() -> None:
    # Given
    threshold = ReleaseCriteria(
        minimum_quality=0.9,
        maximum_quality_regression=0.05,
        maximum_unnecessary_refusal_rate=0.3333,
        maximum_refusal_rate_increase=0.3333,
        maximum_mean_latency_ms=100,
        maximum_latency_increase_ms=10,
        maximum_mean_cost=1,
        maximum_cost_increase=0.1,
    )
    cases = tuple(
        passing_case().model_copy(
            update={
                "id": f"case-{index}",
                "fixture_digest": str(index) * 64,
                "baseline": CaseMeasurement(
                    quality=0.95001,
                    unnecessary_refusal=False,
                    latency_ms=90,
                    cost=0.9,
                ),
                "candidate": CaseMeasurement(
                    quality=0.89996,
                    unnecessary_refusal=index == 1,
                    latency_ms=100.00004,
                    cost=1.00004,
                ),
            }
        )
        for index in range(1, 4)
    )
    # When
    gate = evaluate_release(evaluation(threshold, cases), threshold)
    # Then
    assert set(gate.failed_criteria) == set(CriterionFailure)


def test_metric_gates_accept_unrounded_values_below_thresholds() -> None:
    # Given
    threshold = ReleaseCriteria(
        minimum_quality=0.9,
        maximum_quality_regression=0.05,
        maximum_unnecessary_refusal_rate=0.3334,
        maximum_refusal_rate_increase=0.3334,
        maximum_mean_latency_ms=100,
        maximum_latency_increase_ms=10,
        maximum_mean_cost=1,
        maximum_cost_increase=0.1,
    )
    cases = tuple(
        passing_case().model_copy(
            update={
                "id": f"case-{index}",
                "fixture_digest": str(index) * 64,
                "baseline": CaseMeasurement(
                    quality=0.95003,
                    unnecessary_refusal=False,
                    latency_ms=90,
                    cost=0.9,
                ),
                "candidate": CaseMeasurement(
                    quality=0.90004,
                    unnecessary_refusal=index == 1,
                    latency_ms=99.99996,
                    cost=0.99996,
                ),
            }
        )
        for index in range(1, 4)
    )
    # When
    gate = evaluate_release(
        evaluation(threshold, cases).model_copy(update={"synthetic": False}),
        threshold,
    )
    # Then
    assert gate.failed_criteria == ()
    assert gate.decision == ReleaseDecision.ELIGIBLE_FOR_FIELD_REVIEW


def test_synthetic_pass_cannot_be_promoted_to_field_review_eligibility() -> None:
    # Given
    subject = evaluation()
    # When
    gate = evaluate_release(subject, criteria())
    # Then
    assert gate.decision == ReleaseDecision.SYNTHETIC_EVALUATION_ONLY
    assert gate.eligible_for_field_review is False
    assert gate.assurance == "input_derived_recommendation"
    assert gate.live_validated is False
    assert gate.evidence_origin_verified is False


def test_non_synthetic_pass_requires_named_field_reviewer() -> None:
    # Given
    subject = evaluation().model_copy(update={"synthetic": False, "field_reviewer": None})
    # When
    gate = evaluate_release(subject, criteria())
    # Then
    assert gate.decision == ReleaseDecision.FIELD_REVIEW_REQUIRED
    assert gate.eligible_for_field_review is False


def test_non_synthetic_pass_with_reviewer_is_eligible_for_field_review() -> None:
    # Given
    subject = evaluation().model_copy(update={"synthetic": False})
    # When
    gate = evaluate_release(subject, criteria())
    # Then
    assert gate.decision == ReleaseDecision.ELIGIBLE_FOR_FIELD_REVIEW
    assert gate.eligible_for_field_review is True
    assert gate.live_validated is False
    assert gate.evidence_origin_verified is False


def test_synthetic_release_example_stays_below_field_review_eligibility() -> None:
    # Given
    root = Path(__file__).parents[1] / "examples" / "v0.2"
    subject = ReleaseEvaluation.model_validate_json(
        (root / "release-evaluation.json").read_text(encoding="utf-8")
    )
    threshold = ReleaseCriteria.model_validate_json(
        (root / "release-criteria.json").read_text(encoding="utf-8")
    )
    # When
    gate = evaluate_release(subject, threshold)
    # Then
    assert gate.decision == ReleaseDecision.BLOCKED
    assert gate.eligible_for_field_review is False
    assert gate.boundaries == (ReleaseBoundary.EVALUATION_TARGET_MANIFEST_MISSING,)
