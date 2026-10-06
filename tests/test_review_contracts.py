from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ax_starter.action_contracts import Proposal, ProposalState, Simulation
from ax_starter.actions import ActionEngine
from ax_starter.api import create_app
from ax_starter.common import AXError, Principal
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import content_hash
from ax_starter.store import Store
from tests.test_actions import request
from tests.test_api import headers, registry


def short_lived_engine(
    path: Path, pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> ActionEngine:
    short = pack.model_copy(
        update={
            "documents": tuple(
                doc.model_copy(update={"valid_until": now + timedelta(minutes=20)})
                for doc in pack.documents
            )
        }
    )
    return ActionEngine(Store(path, short), short, principals)


def test_review_when_full_payload_must_be_visible(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    # When
    sim = engine.simulate(principals[1], proposal.id, now)
    # Then
    assert content_hash(sim.payload.model_dump_json()) == sim.reviewed_payload_hash
    assert sim.payload.proposer == "operator"
    assert sim.payload.evidence_ids == ("sop-1",)
    assert sim.state == ProposalState.PROPOSED
    assert sim.stale is False


def test_http_review_when_reviewer_needs_payload_and_outsider_is_hidden(
    tmp_path: Path, pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    app = create_app(pack, tmp_path / "state.db", registry(principals), clock=lambda: now)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        proposal = Proposal.model_validate_json(
            client.post(
                "/v1/actions/propose", content=request().model_dump_json(), headers=headers(0)
            ).content
        )
        # When
        response = client.get(f"/v1/actions/{proposal.id}/simulate", headers=headers(1))
        missing = client.get("/v1/actions/missing/simulate", headers=headers(3))
        hidden = client.get(f"/v1/actions/{proposal.id}/simulate", headers=headers(3))
    # Then
    sim = Simulation.model_validate_json(response.content)
    assert content_hash(sim.payload.model_dump_json()) == sim.reviewed_payload_hash
    assert sim.payload.tenant == "acme"
    assert missing.status_code == hidden.status_code == 404
    assert missing.content == hidden.content


def test_receipt_and_rollback_when_evidence_expires_after_execution(
    tmp_path: Path, pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    engine = short_lived_engine(tmp_path / "short.db", pack, principals, now)
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(
        principals[1], proposal.id, now + timedelta(minutes=1), proposal.payload_hash
    )
    executed = engine.execute(principals[0], proposal.id, now + timedelta(minutes=2))
    # When
    replay = engine.execute(principals[0], proposal.id, now + timedelta(minutes=25))
    rolled = engine.rollback(principals[1], proposal.id, now + timedelta(minutes=25))
    # Then
    assert replay == executed
    assert rolled.state == ProposalState.ROLLED_BACK
    with engine.store.transaction() as conn:
        assert engine.store.entity(conn, "request-1").property("status") == "submitted"
        check = engine.store.audit_check(conn, "acme")
        assert check.intact
        assert check.event_count == 4


@pytest.mark.parametrize("operation", ["approve", "execute", "simulate"])
def test_new_effect_or_review_when_evidence_is_expired(
    tmp_path: Path,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    operation: str,
) -> None:
    # Given
    engine = short_lived_engine(tmp_path / "short.db", pack, principals, now)
    proposal = engine.propose(principals[0], request(), now)
    if operation == "execute":
        _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    late = now + timedelta(minutes=25)

    def act() -> Proposal | Simulation:
        if operation == "approve":
            return engine.approve(principals[1], proposal.id, late, proposal.payload_hash)
        if operation == "simulate":
            return engine.simulate(principals[1], proposal.id, late)
        return engine.execute(principals[0], proposal.id, late)

    # When / Then
    with pytest.raises(AXError, match="evidence_changed_or_revoked"):
        _ = act()


def test_proposal_when_current_same_tenant_actor_loses_target_visibility(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    actor = principals[1].model_copy(update={"groups": frozenset({"other"})})
    engine.principals = (principals[0], actor)
    # When / Then
    for key in (proposal.id, "missing"):
        with pytest.raises(AXError, match="proposal_not_found") as error:
            _ = engine.simulate(actor, key, now)
        assert error.value.status == 404


def test_approval_when_same_reviewer_retries_identical_payload(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    first = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    # When
    repeated = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    # Then
    assert repeated == first
    with engine.store.transaction() as conn:
        assert engine.store.audit_check(conn, "acme").event_count == 2
