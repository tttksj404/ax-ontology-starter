import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ax_starter.cli import app
from ax_starter.ontology import DomainPack


@pytest.mark.parametrize("domain", ["procurement", "support", "hr"])
def test_demo_when_domain_changes_without_core_changes(domain: str) -> None:
    # Given
    runner = CliRunner()
    # When
    result = runner.invoke(app, ["demo", "--domain", domain])
    # Then
    assert result.exit_code == 0
    assert '"passed": true' in result.stdout


def test_cli_binary_when_invoked_in_real_process() -> None:
    # Given / When
    result = subprocess.run(
        [sys.executable, "-m", "ax_starter", "demo", "--domain", "support"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    # Then
    assert result.returncode == 0
    assert '"passed": true' in result.stdout


def test_init_when_directory_contains_user_files(tmp_path: Path) -> None:
    # Given
    _ = (tmp_path / "preserve.txt").write_text("preserve", encoding="utf-8")
    # When
    result = CliRunner().invoke(app, ["init", str(tmp_path)])
    # Then
    assert result.exit_code == 1
    assert (tmp_path / "preserve.txt").read_text(encoding="utf-8") == "preserve"


def test_exported_pack_when_used_as_public_distribution(tmp_path: Path) -> None:
    # Given / When
    directory = tmp_path / "public-assets"
    result = CliRunner().invoke(app, ["assets", str(directory)])
    # Then
    assert result.exit_code == 0
    for domain in ("procurement", "support", "hr"):
        pack = DomainPack.model_validate_json(
            (directory / domain / "domain-pack.json").read_bytes()
        )
        assert pack.id == domain + "-demo"
    assert not tuple(directory.rglob("*credentials*"))
    assert not tuple(directory.rglob("*identities*"))
    # When / Then: an existing export is preserved rather than overwritten.
    again = CliRunner().invoke(app, ["assets", str(directory)])
    assert again.exit_code == 1
