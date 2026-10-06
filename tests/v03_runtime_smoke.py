"""Verify all installed runtime source bytes, previous flows and the Wiki extension."""

import os
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import typer

import ax_starter
from ax_starter.action_contracts import AuditCheck
from ax_starter.bootstrap import DemoCredentials
from ax_starter.common import Sensitivity
from ax_starter.providers import ProviderConfig
from ax_starter.runtime import load_app
from ax_starter.wiki_contracts import WikiPage
from tests.live_server import live_server
from tests.v02_runtime_smoke import (
    command,
    runtime_environment,
    verify_actions,
    verify_knowledge,
    write_contract,
)
from tests.v03_wiki_smoke import verify_wiki, verify_wiki_invalidation


def settings(pilot: Path) -> dict[str, str]:
    return {
        "AX_PACK_FILE": str(pilot / "domain-pack.json"),
        "AX_AUTH_FILE": str(pilot / "identities.json"),
        "AX_DB_FILE": str(pilot / "state.db"),
        "AX_PROVIDER_FILE": str(pilot / "provider.json"),
        "AX_DATA_CONTRACTS_FILE": str(pilot / "data-contracts.json"),
    }


def verify_installed_runtime() -> None:
    assert version("ax-ontology-starter") == "0.3.0"
    assert ax_starter.__file__ is not None
    assert "src" not in Path(ax_starter.__file__).parts
    installed = Path(ax_starter.__file__).parent
    reference = Path(__file__).resolve().parents[1] / "src" / "ax_starter"
    modules = tuple(reference.rglob("*.py"))
    for module in modules:
        assert (installed / module.relative_to(reference)).read_bytes() == module.read_bytes()
    with TemporaryDirectory(prefix="ax-v03-wheel-") as temporary:
        root = Path(temporary)
        for name in ("regression", "wiki"):
            page: WikiPage | None = None
            pilot = root / name
            environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "AX_INPUT_ROOT": str(pilot)}
            _ = environment.pop("AX_TOKEN", None)
            _ = command(environment, ("init", str(pilot)))
            credentials = DemoCredentials.model_validate_json(
                (pilot / "demo-credentials.json").read_bytes()
            )
            tokens = {item.subject: item.token for item in credentials.credentials}
            # This is an explicit server-side floor for synthetic internal sources, no egress.
            _ = write_contract(
                pilot / "provider.json",
                ProviderConfig(minimum_query_sensitivity=Sensitivity.INTERNAL),
            )
            with runtime_environment(settings(pilot)):
                with live_server(load_app()) as endpoint:
                    steward = {
                        **environment,
                        "AX_API_BASE": endpoint,
                        "AX_TOKEN": tokens["steward"],
                    }
                    if name == "regression":
                        verify_knowledge(steward, pilot)
                        verify_actions(
                            {**steward, "AX_TOKEN": tokens["operator"]}, tokens["reviewer"], pilot
                        )
                        audit = AuditCheck.model_validate_json(
                            command({**steward, "AX_TOKEN": tokens["auditor"]}, ("audit",))
                        )
                        assert audit.intact
                        assert audit.event_count == 7
                    else:
                        page = verify_wiki(steward, tokens["reviewer"], pilot)
                if name == "wiki":
                    assert page is not None
                    with live_server(load_app()) as endpoint:
                        steward = {**steward, "AX_API_BASE": endpoint}
                        recovered = WikiPage.model_validate_json(
                            command(steward, ("wiki", "page", page.page_id))
                        )
                        assert recovered == page
                        verify_wiki_invalidation(steward, pilot, page)
                        audit = AuditCheck.model_validate_json(
                            command({**steward, "AX_TOKEN": tokens["auditor"]}, ("audit",))
                        )
                        assert audit.intact
                        assert audit.event_count > 3
    typer.echo(
        " ".join(
            (
                f"V03_WHEEL_SMOKE_PASSED version=0.3.0 modules={len(modules)}",
                "local_http_cli_restart=verified wiki_source_lifecycle=verified",
            )
        )
    )


if __name__ == "__main__":
    verify_installed_runtime()
