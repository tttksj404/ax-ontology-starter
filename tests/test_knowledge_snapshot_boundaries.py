import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from ax_starter.api import create_app
from ax_starter.cli import app
from ax_starter.knowledge_contracts import (
    KnowledgeState,
    SourceSnapshotDocument,
    SourceSnapshotInput,
)
from ax_starter.ontology import DomainPack
from tests.knowledge_fixtures import candidate, management_actor, registry
from tests.test_api import headers
from tests.test_api import registry as identity_registry


def _snapshot(now: datetime) -> SourceSnapshotInput:
    document = SourceSnapshotDocument(
        candidate=candidate(), title="Snapshot", valid_until=now + timedelta(days=30)
    )
    return SourceSnapshotInput(
        contract_id="knowledge-contract",
        request_key="duplicate-snapshot",
        expected_tenant_revision=0,
        expected_source_revision=0,
        documents=(document,),
        observed_at=now,
    )


def _duplicate_json(now: datetime) -> str:
    snapshot = _snapshot(now)
    document = snapshot.documents[0].model_dump_json()
    return "".join(
        (
            '{"contract_id":',
            json.dumps(snapshot.contract_id),
            ',"request_key":',
            json.dumps(snapshot.request_key),
            ',"expected_tenant_revision":0,"expected_source_revision":0,"documents":[',
            document,
            ",",
            document,
            '],"observed_at":',
            json.dumps(snapshot.observed_at.isoformat()),
            "}",
        )
    )


def test_snapshot_contract_rejects_duplicate_document_ids_with_fixed_code(now: datetime) -> None:
    # When / Then
    with pytest.raises(ValidationError) as raised:
        _ = SourceSnapshotInput.model_validate_json(_duplicate_json(now))
    assert raised.value.errors()[0]["type"] == "duplicate_snapshot_document"


def test_duplicate_snapshot_api_returns_422_without_advancing_revision(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    client = TestClient(
        create_app(
            pack,
            tmp_path / "duplicate-api.db",
            identity_registry((management_actor(),)),
            data_contracts=registry(),
            clock=lambda: now,
        ),
        base_url="http://127.0.0.1",
        raise_server_exceptions=False,
    )

    # When
    response = client.post("/v1/knowledge/import", content=_duplicate_json(now), headers=headers(0))

    # Then
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    state = KnowledgeState.model_validate_json(
        client.get("/v1/knowledge/state", headers=headers(0)).content
    )
    assert state.tenant_revision == 0


def test_duplicate_snapshot_cli_reports_invalid_input_file(tmp_path: Path, now: datetime) -> None:
    # Given
    source = tmp_path / "duplicate-snapshot.json"
    _ = source.write_text(_duplicate_json(now), encoding="utf-8")

    # When
    result = CliRunner().invoke(
        app,
        ["knowledge", "import", str(source)],
        env={"AX_INPUT_ROOT": str(tmp_path)},
    )

    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "invalid_input_file"
