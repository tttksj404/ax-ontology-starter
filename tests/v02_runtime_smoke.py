"""Real loopback HTTP and CLI smoke, reusable from an installed wheel."""

import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import typer

import ax_starter
from ax_starter.action_contracts import (
    AuditCheck,
    Proposal,
    ProposalState,
    ProposeRequest,
    Simulation,
)
from ax_starter.bootstrap import DemoCredentials
from ax_starter.common import Contract
from ax_starter.knowledge_contracts import (
    DocumentLifecycle,
    KnowledgeMutationBatch,
    KnowledgeMutationReceipt,
    KnowledgeState,
    RetireDocument,
    SourceSnapshotInput,
    TombstoneDocument,
)
from ax_starter.onboarding_contracts import OnboardingReport, ReadinessDecision
from ax_starter.release_gate import ReleaseGate
from ax_starter.retrieval import Answer
from ax_starter.runtime import load_app
from tests.live_server import live_server


class SmokeFailureError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)


def command(
    environment: dict[str, str],
    arguments: tuple[str, ...],
    expected_code: int = 0,
    expected_error: str | None = None,
) -> str:
    result = subprocess.run(  # noqa: S603 - fixed interpreter, argv only, local synthetic smoke
        [sys.executable, "-m", "ax_starter", *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env=environment,
    )
    credential = environment.get("AX_TOKEN")
    if credential and credential in result.stdout + result.stderr:
        raise SmokeFailureError("smoke_credential_leak")
    if result.returncode != expected_code:
        raise SmokeFailureError("smoke_command_failed_" + arguments[0])
    if expected_error is not None and result.stderr.strip() != expected_error:
        raise SmokeFailureError("smoke_error_mismatch_" + arguments[0])
    return result.stdout


def write_contract(path: Path, contract: Contract) -> str:
    _ = path.write_text(contract.model_dump_json(), encoding="utf-8")
    return str(path)


@contextmanager
def runtime_environment(values: dict[str, str]) -> Generator[None, None, None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                _ = os.environ.pop(key, None)
            else:
                os.environ[key] = value


def verify_actions(environment: dict[str, str], reviewer: str, pilot: Path) -> None:
    proposal = Proposal.model_validate_json(
        command(
            environment,
            (
                "action",
                "propose",
                write_contract(
                    pilot / "propose.json",
                    ProposeRequest(
                        action_type="mark_reviewed",
                        object_id="request-1",
                        new_status="reviewed",
                        expected_version=1,
                        evidence_ids=("sop-1",),
                        request_key="wheel-smoke-action",
                    ),
                ),
            ),
        )
    )
    simulation = Simulation.model_validate_json(
        command(environment, ("action", "simulate", proposal.id))
    )
    assert not simulation.will_execute
    approval = (
        "action",
        "approve",
        proposal.id,
        "--reviewed-hash",
        simulation.reviewed_payload_hash,
    )
    _ = command(environment, approval, expected_code=1)
    review_environment = {**environment, "AX_TOKEN": reviewer}
    approved = Proposal.model_validate_json(command(review_environment, approval))
    assert approved.state == ProposalState.APPROVED
    executed = Proposal.model_validate_json(
        command(environment, ("action", "execute", proposal.id))
    )
    assert executed.state == ProposalState.EXECUTED
    replayed = Proposal.model_validate_json(
        command(environment, ("action", "execute", proposal.id))
    )
    assert replayed == executed
    rolled_back = Proposal.model_validate_json(
        command(review_environment, ("action", "rollback", proposal.id))
    )
    assert rolled_back.state == ProposalState.ROLLED_BACK


def verify_knowledge(environment: dict[str, str], pilot: Path) -> None:
    empty = KnowledgeState.model_validate_json(command(environment, ("knowledge", "state")))
    assert empty.tenant_revision == 0
    assert all(item.document_id != "restricted-doc" for item in empty.documents)
    snapshot = SourceSnapshotInput.model_validate_json(
        (pilot / "source-snapshot.json").read_bytes()
    )
    duplicate = snapshot.model_copy(
        update={"documents": (*snapshot.documents, snapshot.documents[0])}
    )
    _ = command(
        environment,
        ("knowledge", "import", write_contract(pilot / "duplicate-snapshot.json", duplicate)),
        expected_code=1,
        expected_error="invalid_input_file",
    )
    assert KnowledgeState.model_validate_json(command(environment, ("knowledge", "state"))) == empty
    arguments = ("knowledge", "import", str(pilot / "source-snapshot.json"))
    imported = KnowledgeMutationReceipt.model_validate_json(command(environment, arguments))
    replay = KnowledgeMutationReceipt.model_validate_json(command(environment, arguments))
    assert imported == replay
    assert imported.tenant_revision == 1
    assert not imported.origin_authenticated
    assert not imported.provenance_authenticated
    answer = Answer.model_validate_json(
        command(environment, ("ask", "추가 검토 정책", "--object-id", "request-1"))
    )
    assert any(cite.document_id == "acme.pilot-policy-1" for cite in answer.citations)
    for revision, mutation in enumerate(
        (
            RetireDocument(document_id="acme.pilot-policy-1"),
            TombstoneDocument(document_id="acme.pilot-policy-1"),
        ),
        start=1,
    ):
        batch = KnowledgeMutationBatch(
            contract_id="demo-knowledge",
            request_key=f"wheel-smoke-mutation-{revision}",
            expected_tenant_revision=revision,
            expected_source_revision=revision,
            mutations=(mutation,),
        )
        receipt = KnowledgeMutationReceipt.model_validate_json(
            command(
                environment, ("knowledge", "apply", write_contract(pilot / "mutation.json", batch))
            )
        )
        assert receipt.tenant_revision == revision + 1
        current = Answer.model_validate_json(
            command(environment, ("ask", "추가 검토 정책", "--object-id", "request-1"))
        )
        assert all(cite.document_id != "acme.pilot-policy-1" for cite in current.citations)


def verify_installed_runtime() -> None:
    assert version("ax-ontology-starter") == "0.2.0"
    assert ax_starter.__file__ is not None
    assert "src" not in Path(ax_starter.__file__).parts
    installed = Path(ax_starter.__file__).parent
    reference = Path(__file__).resolve().parents[1] / "src" / "ax_starter"
    for module in reference.rglob("*.py"):
        assert (installed / module.relative_to(reference)).read_bytes() == module.read_bytes()
    with TemporaryDirectory(prefix="ax-v02-wheel-") as temporary:
        pilot = Path(temporary) / "pilot"
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "AX_INPUT_ROOT": str(pilot)}
        _ = environment.pop("AX_TOKEN", None)
        _ = command(environment, ("init", str(pilot)))
        credentials = DemoCredentials.model_validate_json(
            (pilot / "demo-credentials.json").read_bytes()
        )
        tokens = {item.subject: item.token for item in credentials.credentials}
        onboarding = OnboardingReport.model_validate_json(
            command(environment, ("onboard", "evaluate", str(pilot / "onboarding-request.json")), 2)
        )
        assert onboarding.decision == ReadinessDecision.BLOCKED
        release = ReleaseGate.model_validate_json(
            command(
                environment,
                (
                    "release",
                    "evaluate",
                    str(pilot / "release-evaluation.json"),
                    str(pilot / "release-criteria.json"),
                ),
                2,
            )
        )
        assert not release.eligible_for_field_review
        assert not release.live_validated
        _ = command(environment, ("contract", "validate", str(pilot / "data-contracts.json")))
        settings = {
            "AX_PACK_FILE": str(pilot / "domain-pack.json"),
            "AX_AUTH_FILE": str(pilot / "identities.json"),
            "AX_DB_FILE": str(pilot / "state.db"),
            "AX_PROVIDER_FILE": str(pilot / "provider.json"),
            "AX_DATA_CONTRACTS_FILE": str(pilot / "data-contracts.json"),
        }
        with runtime_environment(settings):
            with live_server(load_app()) as endpoint:
                steward = {**environment, "AX_API_BASE": endpoint, "AX_TOKEN": tokens["steward"]}
                _ = command({**steward, "AX_TOKEN": tokens["operator"]}, ("knowledge", "state"), 1)
                verify_knowledge(steward, pilot)
                operator = {**steward, "AX_TOKEN": tokens["operator"]}
                verify_actions(operator, tokens["reviewer"], pilot)
                audit = AuditCheck.model_validate_json(
                    command({**steward, "AX_TOKEN": tokens["auditor"]}, ("audit",))
                )
                assert audit.intact
                assert audit.event_count == 7
            with live_server(load_app()) as restarted:
                state = KnowledgeState.model_validate_json(
                    command({**steward, "AX_API_BASE": restarted}, ("knowledge", "state"))
                )
                assert state.tenant_revision == 3
                assert (
                    next(
                        item
                        for item in state.documents
                        if item.document_id == "acme.pilot-policy-1"
                    ).lifecycle
                    == DocumentLifecycle.TOMBSTONE
                )
    typer.echo("V02_WHEEL_SMOKE_PASSED version=0.2.0 local_http_cli_restart=verified")


if __name__ == "__main__":
    verify_installed_runtime()
