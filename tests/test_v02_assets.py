from pathlib import Path

import pytest
from typer.testing import CliRunner

from ax_starter.bootstrap import initialize
from ax_starter.cli import app
from ax_starter.common import Operation
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.demo import DemoDomain
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import SourceSnapshotInput
from ax_starter.ontology import DomainPack
from ax_starter.store import Store


@pytest.mark.parametrize("domain", list(DemoDomain))
def test_initialized_company_has_separate_steward_and_importable_snapshot(
    tmp_path: Path,
    domain: DemoDomain,
) -> None:
    # Given
    directory = tmp_path / "company"
    identities = initialize(directory, domain)
    pack = DomainPack.model_validate_json((directory / "domain-pack.json").read_bytes())
    contracts = DataContractRegistry.model_validate_json(
        (directory / "data-contracts.json").read_bytes()
    )
    snapshot = SourceSnapshotInput.model_validate_json(
        (directory / "source-snapshot.json").read_bytes()
    )
    steward = next(actor for actor in identities.principals() if actor.subject == "steward")
    # When
    store = Store(directory / "state.db", pack)
    receipt = KnowledgeService(store, pack, contracts).import_snapshot(
        steward, snapshot, snapshot.observed_at
    )
    # Then
    assert Operation.MANAGE_KNOWLEDGE in steward.operations
    assert all(
        Operation.MANAGE_KNOWLEDGE not in actor.operations
        for actor in identities.principals()
        if actor.subject != "steward"
    )
    assert receipt.tenant_revision == 1
    assert receipt.origin_authenticated is False
    assert (directory / "onboarding-request.json").is_file()


def test_wheel_assets_include_v02_contracts_and_company_questions_without_credentials(
    tmp_path: Path,
) -> None:
    # Given / When
    directory = tmp_path / "assets"
    result = CliRunner().invoke(app, ["assets", str(directory)])
    # Then
    assert result.exit_code == 0
    for domain in DemoDomain:
        assert (directory / domain.value / "data-contracts.json").is_file()
        assert (directory / domain.value / "onboarding-request.json").is_file()
    assert (directory / "schemas" / "source-snapshot.schema.json").is_file()
    assert not tuple(directory.rglob("*credentials*"))
