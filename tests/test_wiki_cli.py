import pytest
from typer.testing import CliRunner

from ax_starter.common import Contract, Sensitivity
from ax_starter.retrieval import Query
from ax_starter.wiki_cli import wiki_app


def test_wiki_query_cli_accepts_explicit_numeric_sensitivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: capture the exact request without making a network call.
    emitted: list[Contract] = []

    def capture(method: str, path: str, payload: Contract | None = None) -> None:
        assert method == "POST"
        assert path == "/v1/wiki/query"
        assert payload is not None
        emitted.append(payload)

    monkeypatch.setattr("ax_starter.wiki_cli.emit_request", capture)
    # When
    result = CliRunner().invoke(wiki_app, ["query", "검토 절차", "--sensitivity", "1"])
    # Then
    assert result.exit_code == 0, result.output
    assert len(emitted) == 1
    assert isinstance(emitted[0], Query)
    assert emitted[0].sensitivity is Sensitivity.INTERNAL
