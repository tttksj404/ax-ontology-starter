from datetime import datetime

import pytest

from ax_starter.actions import ActionEngine
from ax_starter.common import ActorKind, AXError, Principal
from tests.test_actions import request


def test_alias_of_same_person_cannot_approve(
    engine: ActionEngine,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    proposer = principals[0].model_copy(update={"person_id": "person-a"})
    approver = principals[1].model_copy(update={"person_id": "person-a"})
    engine.principals = (proposer, approver, *principals[2:])
    proposal = engine.propose(proposer, request(), now)
    # When / Then
    with pytest.raises(AXError, match="self_approval_forbidden"):
        _ = engine.approve(approver, proposal.id, now, proposal.payload_hash)


def test_service_account_cannot_supply_human_approval(
    engine: ActionEngine,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    approver = principals[1].model_copy(update={"actor_kind": ActorKind.SERVICE})
    engine.principals = (principals[0], approver, *principals[2:])
    proposal = engine.propose(principals[0], request(), now)
    # When / Then
    with pytest.raises(AXError, match="human_approval_required"):
        _ = engine.approve(approver, proposal.id, now, proposal.payload_hash)


def test_person_mapping_change_after_approval_blocks_execution(
    engine: ActionEngine,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    approver = principals[1].model_copy(update={"person_id": principals[0].subject})
    engine.principals = (principals[0], approver, *principals[2:])
    # When / Then
    with pytest.raises(AXError, match="principal_identity_changed"):
        _ = engine.execute(principals[0], proposal.id, now)
    with engine.store.transaction() as conn:
        assert engine.store.entity(conn, "request-1").version == 1
        assert engine.store.audit_check(conn, "acme").event_count == 2
