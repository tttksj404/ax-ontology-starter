from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from ax_starter.action_contracts import ProposeRequest
from ax_starter.actions import ActionEngine
from ax_starter.assessment import assess
from ax_starter.common import AXError, Contract
from ax_starter.demo import DemoDomain, demo_pack, demo_principals
from ax_starter.intake_demo import demo_intake
from ax_starter.retrieval import Query, retrieve
from ax_starter.store import Store

EXPECTED_AUDIT_EVENTS: Final = 4


class DemoReport(Contract):
    domain: DemoDomain
    assessment_steps: int
    answer_mode: str
    evidence_ids: tuple[str, ...]
    execution_version: int | None
    duplicate_execution_same_result: bool
    rollback_version: int | None
    audit_events: int
    audit_intact: bool
    passed: bool


def run_demo(domain: DemoDomain, *, now: datetime | None = None) -> DemoReport:
    now = now or datetime.now(UTC)
    pack = demo_pack(domain, as_of=now)
    actors = demo_principals(domain)
    with TemporaryDirectory(prefix="ax-synthetic-") as temporary:
        store = Store(Path(temporary) / "state.db", pack)
        engine = ActionEngine(store, pack, actors)
        assessment = assess(demo_intake(domain))
        answer = retrieve(pack, actors[0], Query(question="검토 절차", object_id="request-1"), now)
        proposal = engine.propose(
            actors[0],
            ProposeRequest(
                action_type="mark_reviewed",
                object_id="request-1",
                new_status="reviewed",
                expected_version=1,
                evidence_ids=tuple(item.document_id for item in answer.citations),
                request_key="demo",
            ),
            now,
        )
        _ = engine.approve(actors[1], proposal.id, now, proposal.payload_hash)
        executed = engine.execute(actors[0], proposal.id, now)
        duplicate = engine.execute(actors[0], proposal.id, now)
        rolled = engine.rollback(actors[1], proposal.id, now)
        with store.transaction() as conn:
            check = store.audit_check(conn, actors[0].tenant)
            entity = store.entity(conn, "request-1")
        passed = (
            executed == duplicate
            and check.intact
            and check.event_count == EXPECTED_AUDIT_EVENTS
            and entity.property("status") == "submitted"
        )
        if not passed:
            raise AXError("demo_verification_failed", 500)
        return DemoReport(
            domain=domain,
            assessment_steps=len(assessment.steps),
            answer_mode=answer.mode,
            evidence_ids=tuple(item.document_id for item in answer.citations),
            execution_version=executed.result_version,
            duplicate_execution_same_result=executed == duplicate,
            rollback_version=rolled.rollback_version,
            audit_events=check.event_count,
            audit_intact=check.intact,
            passed=passed,
        )
