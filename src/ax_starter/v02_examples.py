from datetime import datetime, timedelta

from ax_starter.common import Access, Contract, Operation, Principal, Purpose
from ax_starter.data_contracts import (
    DataContract,
    DataContractRegistry,
    DeletionPolicy,
    DocumentCandidate,
    LifecyclePolicy,
    ProvenanceClaim,
    ReconciliationAction,
    ReconciliationPolicy,
    SourceReference,
)
from ax_starter.intake import BusinessIntake
from ax_starter.knowledge_contracts import SourceSnapshotDocument, SourceSnapshotInput
from ax_starter.onboarding_contracts import CompanyProfile, DeploymentMode, OnboardingRequest
from ax_starter.ontology import DomainPack
from ax_starter.release_gate import (
    CaseMeasurement,
    ReleaseCaseResult,
    ReleaseCriteria,
    ReleaseEvaluation,
)
from ax_starter.retrieval import content_hash


def demo_steward(operator: Principal) -> Principal:
    return Principal(
        subject="steward",
        tenant=operator.tenant,
        groups=operator.groups,
        clearance=operator.clearance,
        operations=frozenset({Operation.READ, Operation.MANAGE_KNOWLEDGE}),
        purposes=frozenset({Purpose.OPERATIONS, Purpose.AUDIT}),
    )


def v02_artifacts(
    pack: DomainPack,
    intake: BusinessIntake,
    as_of: datetime,
) -> tuple[tuple[str, Contract], ...]:
    policy = next(document for document in pack.documents if document.id == "sop-1")
    contract = DataContract(
        id="demo-knowledge",
        version="1",
        tenant=policy.access.tenant,
        owner="steward",
        collection_source=SourceReference(
            identifier="demo-source", uri="synthetic://pilot-collection"
        ),
        object_scope=policy.object_ids,
        access=Access(
            tenant=policy.access.tenant,
            groups=policy.access.groups,
            sensitivity=policy.access.sensitivity,
            purposes=frozenset({Purpose.OPERATIONS, Purpose.AUDIT}),
        ),
        minimum_sensitivity=policy.access.sensitivity,
        lifecycle=LifecyclePolicy(
            refresh_interval_hours=24,
            deletion=DeletionPolicy(
                retention_days=30, delete_within_hours=24, propagate_source_deletion=True
            ),
            reconciliation=ReconciliationPolicy(
                interval_hours=24, action=ReconciliationAction.REJECT
            ),
        ),
        required_provenance=frozenset({"demo-source"}),
    )
    text = "합성 파일 입력으로 추가한 검토 절차입니다. " + policy.text
    digest = content_hash(text)
    managed_document_id = f"{contract.tenant}.pilot-policy-1"
    candidate = DocumentCandidate(
        document_id=managed_document_id,
        tenant=contract.tenant,
        origin=contract.collection_source,
        source_version="1",
        object_scope=contract.object_scope,
        access=policy.access,
        content=text.encode("utf-8"),
        declared_sha256=digest,
        provenance=(
            ProvenanceClaim(
                source_identifier="demo-source",
                record_identifier=managed_document_id,
                content_sha256=digest,
            ),
        ),
    )
    snapshot = SourceSnapshotInput(
        contract_id=contract.id,
        request_key="demo-import-1",
        expected_tenant_revision=0,
        expected_source_revision=0,
        observed_at=as_of,
        documents=(
            SourceSnapshotDocument(
                candidate=candidate,
                title="합성 추가 검토 절차",
                valid_until=as_of + timedelta(days=365),
            ),
        ),
    )
    profile = CompanyProfile(
        company="합성 도입 예시",
        industry=intake.industry,
        jurisdictions=("kr",),
        deployment_modes=(DeploymentMode.OFFLINE,),
        maximum_sensitivity=policy.access.sensitivity,
        allowed_transfers=(),
        allowed_regions=("local",),
        allowed_models=("offline",),
        allowed_tools=("retrieval",),
        retention_days=30,
        authorized_groups=tuple(sorted(policy.access.groups)),
    )
    onboarding = OnboardingRequest(
        profile=profile,
        intake=intake,
        requested_deployment=DeploymentMode.OFFLINE,
        requested_sensitivity=policy.access.sensitivity,
        requested_regions=("local",),
        requested_models=("offline",),
        requested_tools=("retrieval",),
        requested_groups=tuple(sorted(policy.access.groups)),
    )
    measurement = CaseMeasurement(quality=1, unnecessary_refusal=False, latency_ms=10, cost=0)
    evaluation = ReleaseEvaluation(
        baseline_id="illustrative-baseline",
        candidate_id="illustrative-candidate",
        evidence_digest=content_hash(pack.model_dump_json()),
        synthetic=True,
        cases=(
            ReleaseCaseResult(
                id="illustrative-only",
                domain=pack.id,
                fixture_digest=digest,
                baseline=measurement,
                candidate=measurement,
            ),
        ),
    )
    criteria = ReleaseCriteria(
        minimum_quality=1,
        maximum_quality_regression=0,
        maximum_unnecessary_refusal_rate=0,
        maximum_refusal_rate_increase=0,
        maximum_mean_latency_ms=1_000,
        maximum_latency_increase_ms=0,
        maximum_mean_cost=0,
        maximum_cost_increase=0,
    )
    return (
        ("data-contracts.json", DataContractRegistry(contracts=(contract,))),
        ("source-snapshot.json", snapshot),
        ("onboarding-request.json", onboarding),
        ("release-evaluation.json", evaluation),
        ("release-criteria.json", criteria),
    )
