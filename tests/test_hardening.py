from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ax_starter.action_contracts import ProposalState
from ax_starter.actions import ActionEngine, changed
from ax_starter.common import AXError, Principal, Sensitivity
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query, retrieve
from ax_starter.store import Store
from tests.test_actions import request


def test_concurrent_execute_when_same_approved_proposal(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    # When
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = tuple(
            executor.submit(engine.execute, principals[0], proposal.id, now) for _ in range(2)
        )
        results = tuple(future.result() for future in futures)
    # Then
    assert results[0] == results[1]
    with engine.store.transaction() as conn:
        assert engine.store.audit_check(conn, "acme").event_count == 3


def test_parameter_tampering_when_db_payload_changed(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    forged = proposal.model_copy(
        update={
            "payload": proposal.payload.model_copy(update={"new_status": "attacker"}),
            "state": ProposalState.APPROVED,
        }
    )
    with engine.store.transaction() as conn:
        engine.store.save_proposal(conn, forged)
    # When / Then
    with pytest.raises(AXError, match="proposal_integrity_failure"):
        _ = engine.execute(principals[0], proposal.id, now)


def test_rollback_denied_when_newer_change_exists(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    _ = engine.execute(principals[0], proposal.id, now)
    with engine.store.transaction() as conn:
        current = engine.store.entity(conn, "request-1")
        engine.store.save_entity(conn, changed(current, "reviewed"))
    # When / Then
    with pytest.raises(AXError, match="rollback_would_overwrite_newer_change"):
        _ = engine.rollback(principals[1], proposal.id, now)


def test_rollback_denied_when_window_has_expired(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    _ = engine.execute(principals[0], proposal.id, now)
    # When / Then
    with pytest.raises(AXError, match="rollback_window_expired"):
        _ = engine.rollback(principals[1], proposal.id, now + timedelta(days=2))


def test_hidden_data_noninterference_when_hidden_document_removed(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    reduced = pack.model_copy(
        update={"documents": (pack.documents[0],), "objects": pack.objects[:2]}
    )
    query = Query(question="검토 절차 SENTINEL")
    expected = retrieve(reduced, principals[0], query, now)
    # When
    actual = retrieve(pack, principals[0], query, now)
    # Then
    assert actual.model_dump_json() == expected.model_dump_json()


def test_idempotency_when_proposal_replayed_after_execution(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], request(), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    executed = engine.execute(principals[0], proposal.id, now)
    # When
    replay = engine.propose(principals[0], request(), now)
    # Then
    assert replay == executed


def test_pack_validation_when_handler_is_untrusted(pack: DomainPack) -> None:
    # Given
    invalid = pack.model_copy(
        update={"action_types": (pack.action_types[0].model_copy(update={"handler": "run_shell"}),)}
    )
    # When / Then
    with pytest.raises(ValidationError):
        _ = DomainPack.model_validate_json(invalid.model_dump_json())


def test_pack_validation_when_object_label_is_lower_than_property(pack: DomainPack) -> None:
    # Given
    objects = (
        pack.objects[0].model_copy(
            update={
                "access": pack.objects[0].access.model_copy(
                    update={"sensitivity": Sensitivity.PUBLIC}
                )
            }
        ),
        *pack.objects[1:],
    )
    invalid = pack.model_copy(update={"objects": objects})
    # When / Then
    with pytest.raises(ValidationError):
        _ = DomainPack.model_validate_json(invalid.model_dump_json())


def test_audit_integrity_when_audit_row_is_modified(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    _ = engine.propose(principals[0], request(), now)
    with engine.store.transaction() as conn:
        _ = conn.execute("UPDATE audit SET data = ? WHERE tenant = ?", ("modified", "acme"))
    # When
    with engine.store.transaction() as conn:
        check = engine.store.audit_check(conn, "acme")
    # Then
    assert check.intact is False


def test_pack_fingerprint_when_restart_reloads_json(tmp_path: Path, pack: DomainPack) -> None:
    # Given
    database = tmp_path / "state.db"
    initial = Store(database, pack)
    parsed = DomainPack.model_validate_json(pack.model_dump_json())
    # When
    restarted = Store(database, parsed)
    # Then
    assert initial.pack_hash == restarted.pack_hash
