import pytest
from typer.testing import CliRunner

from ax_starter.cli import app
from ax_starter.demo import DemoDomain
from ax_starter.wiki_demo import WikiDemoReport


@pytest.mark.parametrize("domain", list(DemoDomain))
def test_wiki_demo_persists_reviewed_knowledge_with_raw_citations(domain: DemoDomain) -> None:
    # Given / When: the complete public demo must work in each supported synthetic domain.
    result = CliRunner().invoke(app, ["wiki", "demo", "--domain", domain.value])
    # Then
    assert result.exit_code == 0
    report = WikiDemoReport.model_validate_json(result.stdout)
    assert report.synthetic
    assert not report.model_executed
    assert report.self_review_blocked
    assert report.persisted_after_restart
    assert report.expired_source_hidden
    assert report.raw_citation_ids == ("sop-1",)
