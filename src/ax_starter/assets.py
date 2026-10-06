import json
from datetime import UTC, datetime
from pathlib import Path

from ax_starter.auth import IdentityRegistry
from ax_starter.bootstrap import example_evaluations, example_log
from ax_starter.common import AXError, Sensitivity
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.demo import DemoDomain, demo_pack
from ax_starter.evaluation import EvaluationSet
from ax_starter.intake import BusinessIntake
from ax_starter.intake_demo import demo_intake
from ax_starter.knowledge_contracts import KnowledgeMutationBatch, SourceSnapshotInput
from ax_starter.onboarding_contracts import OnboardingRequest
from ax_starter.ontology import DomainPack
from ax_starter.process_metrics import ProcessLog
from ax_starter.providers import ProviderConfig, ProviderMode
from ax_starter.release_gate import ReleaseCriteria, ReleaseEvaluation
from ax_starter.v02_examples import v02_artifacts


def export_assets(directory: Path) -> int:
    """Export public synthetic examples and JSON schemas; never export credentials."""
    if directory.exists():
        raise AXError("assets_directory_exists")
    directory.mkdir(parents=True)
    artifacts: dict[str, str] = {}
    as_of = datetime.now(UTC)
    for domain in DemoDomain:
        pack = demo_pack(domain, as_of=as_of)
        intake = demo_intake(domain)
        artifacts[domain.value + "/domain-pack.json"] = pack.model_dump_json(indent=2)
        artifacts[domain.value + "/intake.json"] = intake.model_dump_json(indent=2)
        for name, contract in v02_artifacts(pack, intake, as_of):
            artifacts[domain.value + "/" + name] = contract.model_dump_json(indent=2)
    artifacts["evaluation-set.json"] = example_evaluations().model_dump_json(indent=2)
    artifacts["process-log.json"] = example_log().model_dump_json(indent=2)
    for name, contract in (
        ("domain-pack", DomainPack),
        ("business-intake", BusinessIntake),
        ("provider", ProviderConfig),
        ("evaluation-set", EvaluationSet),
        ("process-log", ProcessLog),
        ("identity-registry", IdentityRegistry),
        ("onboarding-request", OnboardingRequest),
        ("data-contracts", DataContractRegistry),
        ("knowledge-mutation-batch", KnowledgeMutationBatch),
        ("source-snapshot", SourceSnapshotInput),
        ("release-evaluation", ReleaseEvaluation),
        ("release-criteria", ReleaseCriteria),
    ):
        artifacts["schemas/" + name + ".schema.json"] = json.dumps(
            contract.model_json_schema(), ensure_ascii=False, indent=2
        )
    providers = {
        "offline": ProviderConfig(),
        "local": ProviderConfig(
            mode=ProviderMode.LOCAL,
            endpoint="http://127.0.0.1:11434",
            model="replace-with-installed-model",
            minimum_query_sensitivity=Sensitivity.RESTRICTED,
        ),
        "private-gateway": ProviderConfig(
            mode=ProviderMode.PRIVATE,
            endpoint="https://ai-gateway.example.com/v1",
            model="replace-with-approved-deployment",
            approved_hosts=("ai-gateway.example.com",),
        ),
        "cloud-gateway": ProviderConfig(
            mode=ProviderMode.CLOUD,
            endpoint="https://ai-gateway.example.com/v1",
            model="replace-with-approved-deployment",
            approved_hosts=("ai-gateway.example.com",),
            minimum_query_sensitivity=Sensitivity.RESTRICTED,
        ),
    }
    for name, provider in providers.items():
        artifacts["providers/" + name + ".json"] = provider.model_dump_json(indent=2)
    for name, content in artifacts.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content + "\n", encoding="utf-8")
    return len(artifacts)
