import hashlib
import os
import re
import secrets
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ax_starter.auth import IdentityBinding, IdentityRegistry
from ax_starter.common import AXError, Contract
from ax_starter.demo import DemoDomain, demo_pack, demo_principals
from ax_starter.evaluation import EvaluationCase, EvaluationSet
from ax_starter.intake_demo import demo_intake
from ax_starter.process_metrics import ProcessEvent, ProcessLog
from ax_starter.providers import ProviderConfig
from ax_starter.retrieval import Query
from ax_starter.v02_examples import demo_steward, v02_artifacts


class DemoCredential(Contract):
    subject: str
    token: str


class DemoCredentials(Contract):
    warning: str = "로컬 합성 데모 전용. 실제 회사 인증에 사용하지 마세요."
    credentials: tuple[DemoCredential, ...]


def private_directory(path: Path) -> None:
    if os.name == "nt":
        try:
            system32 = Path(os.environ["SYSTEMROOT"]) / "System32"
            identity = subprocess.run(  # noqa: S603 - fixed native Windows identity command
                [str(system32 / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
                check=True,
                capture_output=True,
            )
            sid = re.search(rb"S-1-\d+(?:-\d+)+", identity.stdout)
            if sid is None:
                raise AXError("current_identity_sid_unavailable", 503)
            _ = subprocess.run(  # noqa: S603 - fixed Windows executable, argv only, newly created path
                [
                    str(system32 / "icacls.exe"),
                    str(path.resolve()),
                    "/inheritance:r",
                    "/grant:r",
                    "*" + sid.group().decode("ascii") + ":(OI)(CI)F",
                ],
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise AXError("private_directory_acl_failed", 503) from exc
    else:
        path.chmod(stat.S_IRWXU)


def example_log() -> ProcessLog:
    base = datetime(2026, 10, 1, tzinfo=UTC)
    events: list[ProcessEvent] = []
    for index in range(3):
        start = base + timedelta(hours=index)
        events.extend(
            (
                ProcessEvent(
                    case_id=f"case-{index}",
                    step_id="step-1",
                    owner="clerk",
                    received_at=start,
                    started_at=start + timedelta(minutes=2),
                    completed_at=start + timedelta(minutes=7),
                ),
                ProcessEvent(
                    case_id=f"case-{index}",
                    step_id="step-2",
                    owner="reviewer",
                    received_at=start + timedelta(minutes=7),
                    started_at=start + timedelta(minutes=27),
                    completed_at=start + timedelta(minutes=32),
                ),
            )
        )
    return ProcessLog(source="synthetic:three-cases", synthetic=True, events=tuple(events))


def example_evaluations() -> EvaluationSet:
    return EvaluationSet(
        synthetic=True,
        cases=(
            EvaluationCase(
                id="operator-sop",
                tenant="acme",
                subject="operator",
                query=Query(question="검토 절차", object_id="request-1"),
                expected_documents=("sop-1",),
            ),
            EvaluationCase(
                id="no-graph",
                tenant="acme",
                subject="operator",
                query=Query(question="검토 절차", object_id="request-1", hops=0),
                expected_documents=(),
            ),
            EvaluationCase(
                id="foreign-object",
                tenant="acme",
                subject="operator",
                query=Query(question="검토 절차", object_id="beta-request"),
                expected_documents=(),
                expected_denial=True,
            ),
            EvaluationCase(
                id="restricted-object",
                tenant="acme",
                subject="operator",
                query=Query(question="검토 절차", object_id="restricted-case"),
                expected_documents=(),
                expected_denial=True,
            ),
            EvaluationCase(
                id="outsider-sop",
                tenant="beta",
                subject="outsider",
                query=Query(question="검토 절차", object_id="beta-request"),
                expected_documents=("beta-doc",),
            ),
            EvaluationCase(
                id="unknown-query",
                tenant="acme",
                subject="operator",
                query=Query(question="不存在xyz987"),
                expected_documents=(),
            ),
        ),
    )


def initialize(directory: Path, domain: DemoDomain) -> IdentityRegistry:
    if directory.exists():
        raise AXError("initialization_directory_not_empty")
    try:
        directory.mkdir(parents=True)
    except FileExistsError as exc:
        raise AXError("initialization_directory_not_empty") from exc
    private_directory(directory)
    actors = demo_principals(domain)
    actors = (*actors, demo_steward(actors[0]))
    credentials = tuple(
        DemoCredential(subject=actor.subject, token=secrets.token_urlsafe(32)) for actor in actors
    )
    identities = IdentityRegistry(
        bindings=tuple(
            IdentityBinding(
                token_sha256=hashlib.sha256(item.token.encode("utf-8")).hexdigest(), principal=actor
            )
            for actor, item in zip(actors, credentials, strict=True)
        )
    )
    as_of = datetime.now(UTC)
    pack = demo_pack(domain, as_of=as_of)
    intake = demo_intake(domain)
    artifacts = (
        ("domain-pack.json", pack),
        ("intake.json", intake),
        ("identities.json", identities),
        ("demo-credentials.json", DemoCredentials(credentials=credentials)),
        ("provider.json", ProviderConfig()),
        ("evaluation-set.json", example_evaluations()),
        ("process-log.json", example_log()),
        *v02_artifacts(pack, intake, as_of),
    )
    for name, contract in artifacts:
        _ = (directory / name).write_text(contract.model_dump_json(indent=2), encoding="utf-8")
    return identities
