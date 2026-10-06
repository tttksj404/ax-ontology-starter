from datetime import datetime, timedelta

import pytest

from ax_starter.action_contracts import ProposalState, ProposeRequest
from ax_starter.actions import ActionEngine
from ax_starter.common import AXError, Operation, Principal


def request(key: str = "request-a") -> ProposeRequest:
    return ProposeRequest(
        action_type="mark_reviewed",
        object_id="request-1",
        new_status="reviewed",
        expected_version=1,
        evidence_ids=("sop-1",),
        request_key=key,
    )


def test_transactional_execute_when_independent_approval_exists(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    # When
    result = engine.execute(principals[0], proposal.id, now)
    # Then
    assert result.state == ProposalState.EXECUTED
    with engine.store.transaction() as conn:
        assert engine.store.entity(conn, "request-1").property("status") == "reviewed"
        assert engine.store.audit_check(conn, "acme").event_count == 3


def test_cannot_execute_when_no_approval(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    # When / Then
    with pytest.raises(AXError, match="independent_approval_required"):
        _ = engine.execute(principals[0], proposal.id, now)


def test_self_approval_denied_when_actor_has_both_roles(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    actor = principals[0].model_copy(update={"operations": frozenset(Operation)})
    engine.principals = (actor, *principals[1:])
    proposal = engine.propose(actor, request(), now)
    # When / Then
    with pytest.raises(AXError, match="self_approval_forbidden"):
        _ = engine.approve(actor, proposal.id, now, proposal.payload_hash)


def test_idempotent_execute_when_replayed(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    first = engine.execute(principals[0], proposal.id, now)
    # When
    second = engine.execute(principals[0], proposal.id, now)
    # Then
    assert second == first
    with engine.store.transaction() as conn:
        assert engine.store.entity(conn, "request-1").version == 2
        assert engine.store.audit_check(conn, "acme").event_count == 3


def test_version_conflict_when_another_proposal_executed(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    first = engine.propose(principals[0], request("first"), now)
    second = engine.propose(principals[0], request("second"), now)
    _ = engine.approve(principals[1], first.id, now, first.payload_hash)
    _ = engine.approve(principals[1], second.id, now, second.payload_hash)
    _ = engine.execute(principals[0], first.id, now)
    # When / Then
    with pytest.raises(AXError, match="stale_object_version"):
        _ = engine.execute(principals[0], second.id, now)


def test_approval_rechecked_when_reviewer_permission_revoked(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    revoked = principals[1].model_copy(update={"operations": frozenset({Operation.READ})})
    current = ActionEngine(engine.store, engine.pack, (principals[0], revoked))
    # When / Then
    with pytest.raises(AXError, match="access_denied"):
        _ = current.execute(principals[0], proposal.id, now)


def test_rollback_when_executed_state_is_unchanged(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    _ = engine.execute(principals[0], proposal.id, now)
    # When
    result = engine.rollback(principals[1], proposal.id, now + timedelta(hours=1))
    # Then
    assert result.state == ProposalState.ROLLED_BACK
    with engine.store.transaction() as conn:
        assert engine.store.entity(conn, "request-1").property("status") == "submitted"
        assert engine.store.audit_check(conn, "acme").intact


def test_approval_expired_when_operator_waits(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    # When / Then
    with pytest.raises(AXError, match="proposal_expired"):
        _ = engine.execute(principals[0], proposal.id, now + timedelta(hours=1))


def test_simulate_when_unapproved_proposal(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    # When
    result = engine.simulate(principals[0], proposal.id, now)
    # Then
    assert result.will_execute is False
    assert result.after.property("status") == "reviewed"
    with engine.store.transaction() as conn:
        assert engine.store.entity(conn, "request-1").version == 1
