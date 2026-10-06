from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ax_starter.bootstrap import initialize
from ax_starter.common import AXError
from ax_starter.demo import DemoDomain
from ax_starter.runtime import load_app


def configure(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    monkeypatch.setenv("AX_AUTH_FILE", str(directory / "identities.json"))
    monkeypatch.setenv("AX_PACK_FILE", str(directory / "domain-pack.json"))
    monkeypatch.delenv("AX_PROVIDER_FILE", raising=False)


def test_runtime_when_explicit_db_is_inside_pilot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    directory = tmp_path / "pilot"
    _ = initialize(directory, DemoDomain.PROCUREMENT)
    configure(monkeypatch, directory)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AX_DB_FILE", str(directory / "state.db"))
    # When
    _ = load_app()
    # Then
    assert (directory / "state.db").exists()
    assert not (tmp_path / ".runtime" / "state.db").exists()


def test_runtime_when_database_configuration_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    configure(monkeypatch, tmp_path)
    monkeypatch.delenv("AX_DB_FILE", raising=False)
    monkeypatch.setenv("AX_DATABASE", str(tmp_path / "deprecated.db"))
    # When / Then
    with pytest.raises(AXError, match="runtime_configuration_required"):
        _ = load_app()


def test_production_hosts_when_testserver_header_is_received(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    directory = tmp_path / "pilot"
    _ = initialize(directory, DemoDomain.PROCUREMENT)
    configure(monkeypatch, directory)
    monkeypatch.setenv("AX_DB_FILE", str(directory / "state.db"))
    # When
    with TestClient(load_app(), base_url="http://testserver") as client:
        response = client.get("/health")
    # Then
    assert response.status_code == 400


def test_init_when_directory_is_created_between_check_and_mkdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: emulate the prior exists-check result while a competing creator has now won.
    directory = tmp_path / "claimed"
    directory.mkdir()
    _ = (directory / "preserve.txt").write_text("preserve", encoding="utf-8")
    original = Path.exists

    def stale_exists(path: Path) -> bool:
        return False if path == directory else original(path)

    monkeypatch.setattr(Path, "exists", stale_exists)
    # When / Then
    with pytest.raises(AXError, match="initialization_directory_not_empty"):
        _ = initialize(directory, DemoDomain.PROCUREMENT)
    assert (directory / "preserve.txt").read_text(encoding="utf-8") == "preserve"
    assert not (directory / "demo-credentials.json").exists()
