from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ax_starter.cli import app
from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig, ProviderMode, enforce_route
from ax_starter.retrieval import Query, retrieve


@pytest.mark.parametrize(
    "path",
    [
        r"\\untrusted.example\share\company.json",
        r"\\?\C:\company.json",
        r"C:\company.json:secret",
        r"C:company.json",
        "NUL",
        "file://host/share/company.json",
    ],
)
def test_unsafe_input_path_is_denied_before_file_open(path: str) -> None:
    # Given / When
    with patch.object(
        Path, "open", side_effect=AssertionError("file_access_must_not_happen")
    ) as opened:
        result = CliRunner().invoke(app, ["onboard", "evaluate", path])
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "input_path_must_be_local"
    opened.assert_not_called()


@pytest.mark.parametrize(
    "command", [("assess",), ("process",), ("pack", "validate"), ("action", "propose")]
)
def test_existing_file_commands_use_same_local_boundary(command: tuple[str, ...]) -> None:
    # Given / When
    with patch.object(
        Path, "open", side_effect=AssertionError("file_access_must_not_happen")
    ) as opened:
        result = CliRunner().invoke(app, [*command, r"\\untrusted.example\share\company.json"])
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "input_path_must_be_local"
    opened.assert_not_called()


def test_file_outside_allowed_root_is_denied(tmp_path: Path) -> None:
    # Given
    source = tmp_path / "company.json"
    _ = source.write_text("{}", encoding="utf-8")
    # When
    result = CliRunner().invoke(app, ["onboard", "evaluate", str(source)])
    # Then
    assert result.exit_code == 1
    assert result.stderr.strip() == "input_path_outside_root"


def test_private_gateway_does_not_trust_public_question_label(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    query = Query(question="merger plan codename ORCHID", sensitivity=Sensitivity.PUBLIC)
    answer = retrieve(pack, principals[0], query, now)
    config = ProviderConfig(
        mode=ProviderMode.PRIVATE,
        endpoint="https://gateway.example/v1",
        model="approved-model",
        approved_hosts=("gateway.example",),
        egress_approved=True,
    )
    # When / Then
    with pytest.raises(AXError, match="provider_classification_denied"):
        enforce_route(config, query, answer)
