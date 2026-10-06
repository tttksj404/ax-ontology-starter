from datetime import datetime

import pytest

from ax_starter.actions import ActionEngine
from ax_starter.common import AXError, Principal
from ax_starter.retrieval import content_hash
from tests.test_actions import request


@pytest.mark.parametrize("reassigned_role", ["proposer", "approver"])
def test_pending_action_cannot_survive_person_reassignment(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime, reassigned_role: str
) -> None:
    # Given
    proposer = principals[0].model_copy(update={"person_id": "person-a"})
    reviewer = principals[1].model_copy(update={"person_id": "person-b"})
    engine.principals = (proposer, reviewer, *principals[2:])
    proposal = engine.propose(proposer, request(), now)
    _ = engine.approve(reviewer, proposal.id, now, proposal.payload_hash)
    changed = (proposer if reassigned_role == "proposer" else reviewer).model_copy(
        update={"person_id": "person-c"}
    )
    engine.principals = (
        changed if reassigned_role == "proposer" else proposer,
        changed if reassigned_role == "approver" else reviewer,
        *principals[2:],
    )
    executor = changed if reassigned_role == "proposer" else proposer
    # When / Then
    with pytest.raises(AXError, match="principal_identity_changed") as error:
        _ = engine.execute(executor, proposal.id, now)
    assert error.value.status == 403
    with engine.store.transaction() as conn:
        assert engine.store.entity(conn, "request-1").version == 1
        assert engine.store.audit_check(conn, "acme").event_count == 2


def test_proposer_reassignment_is_blocked_before_approval(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposer = principals[0].model_copy(update={"person_id": "person-a"})
    engine.principals = (proposer, *principals[1:])
    proposal = engine.propose(proposer, request(), now)
    engine.principals = (proposer.model_copy(update={"person_id": "person-c"}), *principals[1:])
    # When / Then
    with pytest.raises(AXError, match="principal_identity_changed"):
        _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    with engine.store.transaction() as conn:
        assert engine.store.audit_check(conn, "acme").event_count == 1


def test_proposal_replay_cannot_claim_previous_person_identity(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    _ = engine.propose(principals[0], request(), now)
    replacement = principals[0].model_copy(update={"person_id": "new-person"})
    engine.principals = (replacement, *principals[1:])
    # When / Then
    with pytest.raises(AXError, match="principal_identity_changed"):
        _ = engine.propose(replacement, request(), now)


def test_approval_replay_cannot_claim_previous_approver_identity(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    replacement = principals[1].model_copy(update={"person_id": "new-person"})
    engine.principals = (principals[0], replacement, *principals[2:])
    # When / Then
    with pytest.raises(AXError, match="principal_identity_changed"):
        _ = engine.approve(replacement, proposal.id, now, proposal.payload_hash)


@pytest.mark.parametrize("terminal", [False, True])
def test_legacy_payload_hash_is_preserved_and_pending_work_is_closed(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime, terminal: bool
) -> None:
    # Given: emulate the exact v0.1 JSON without new identity/evidence fields.
    proposal = engine.propose(principals[0], request(), now)
    if terminal:
        _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
        proposal = engine.execute(principals[0], proposal.id, now)
    payload = proposal.payload.model_copy(
        update={"proposer_actor_kind": None, "proposer_person_id": None, "evidence_refs": ()}
    )
    legacy = proposal.model_copy(
        update={
            "payload": payload,
            "payload_hash": content_hash(payload.model_dump_json()),
            "approver_actor_kind": None,
            "approver_person_id": None,
        }
    )
    with engine.store.transaction() as conn:
        engine.store.save_proposal(conn, legacy)
    # When / Then
    if terminal:
        assert engine.execute(principals[0], proposal.id, now) == legacy
        _ = engine.rollback(principals[1], proposal.id, now)
    else:
        with pytest.raises(AXError, match="proposal_reproposal_required"):
            _ = engine.approve(principals[1], proposal.id, now, legacy.payload_hash)
        with pytest.raises(AXError, match="proposal_reproposal_required"):
            _ = engine.propose(principals[0], request(), now)
