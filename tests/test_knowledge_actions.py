from datetime import datetime
from hashlib import sha256

import pytest

from ax_starter.action_contracts import ProposeRequest
from ax_starter.actions import ActionEngine
from ax_starter.common import AXError, Principal
from ax_starter.knowledge_store import access_hash
from ax_starter.ontology import Document
from ax_starter.retrieval import content_hash


def action_request(key: str) -> ProposeRequest:
    return ProposeRequest(
        action_type="mark_reviewed",
        object_id="request-1",
        new_status="reviewed",
        expected_version=1,
        evidence_ids=("sop-1",),
        request_key=key,
    )


def replace_document(engine: ActionEngine, document: Document) -> None:
    with engine.store.transaction() as conn:
        _ = conn.execute(
            """UPDATE knowledge_documents SET source_version = ?, document_json = ?,
            content_sha256 = ?, access_sha256 = ?, access_json = ?, revision = revision + 1
            WHERE document_id = ?""",
            (
                document.source_version,
                document.model_dump_json(),
                sha256(document.text.encode()).hexdigest(),
                access_hash(document.access),
                document.access.model_dump_json(),
                document.id,
            ),
        )


def tombstone(engine: ActionEngine, document_id: str) -> None:
    with engine.store.transaction() as conn:
        _ = conn.execute(
            """UPDATE knowledge_documents SET lifecycle = 'tombstone', document_json = NULL,
            revision = revision + 1 WHERE document_id = ?""",
            (document_id,),
        )


def test_simulation_is_blocked_when_evidence_is_tombstoned(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("tombstone-simulate"), now)
    tombstone(engine, "sop-1")

    # When / Then
    with pytest.raises(AXError, match="evidence_changed_or_revoked"):
        _ = engine.simulate(principals[0], proposal.id, now)


def test_repeated_approval_revalidates_revoked_evidence(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("repeat-approve"), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    tombstone(engine, "sop-1")

    # When / Then
    with pytest.raises(AXError, match="evidence_changed_or_revoked"):
        _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)


def test_approval_is_blocked_when_evidence_acl_changes(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("acl-change"), now)
    document = next(item for item in engine.pack.documents if item.id == "sop-1")
    restricted = document.model_copy(
        update={"access": document.access.model_copy(update={"groups": frozenset({"private"})})}
    )
    replace_document(engine, restricted)

    # When / Then
    with pytest.raises(AXError, match="evidence_changed_or_revoked"):
        _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)


def test_approval_is_blocked_when_source_version_changes(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("source-version"), now)
    document = next(item for item in engine.pack.documents if item.id == "sop-1")
    replace_document(engine, document.model_copy(update={"source_version": "2"}))

    # When / Then
    with pytest.raises(AXError, match="evidence_changed_or_revoked"):
        _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)


def test_unrelated_document_change_does_not_invalidate_proposal(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("unrelated-document"), now)
    tombstone(engine, "beta-doc")

    # When
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    result = engine.execute(principals[0], proposal.id, now)

    # Then
    assert result.result_version == 2


def test_execution_reads_identity_directory_once(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    calls = 0

    def resolve() -> tuple[Principal, ...]:
        nonlocal calls
        calls += 1
        return principals

    current = ActionEngine(engine.store, engine.pack, principals, principal_resolver=resolve)
    proposal = current.propose(principals[0], action_request("identity-snapshot"), now)
    _ = current.approve(principals[1], proposal.id, now, proposal.payload_hash)
    calls = 0

    # When
    _ = current.execute(principals[0], proposal.id, now)

    # Then
    assert calls == 1


def test_execute_is_blocked_when_approved_evidence_is_tombstoned(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("tombstone-execute"), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    tombstone(engine, "sop-1")

    # When / Then
    with pytest.raises(AXError, match="evidence_changed_or_revoked"):
        _ = engine.execute(principals[0], proposal.id, now)


def test_legacy_pending_proposal_requires_reproposal(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("legacy-pending"), now)
    legacy_payload = proposal.payload.model_copy(update={"evidence_refs": ()})
    legacy = proposal.model_copy(
        update={
            "payload": legacy_payload,
            "payload_hash": content_hash(legacy_payload.model_dump_json()),
        }
    )
    with engine.store.transaction() as conn:
        engine.store.save_proposal(conn, legacy)

    # When / Then
    with pytest.raises(AXError, match="proposal_reproposal_required"):
        _ = engine.approve(principals[1], legacy.id, now, legacy.payload_hash)


def test_completed_legacy_receipt_keeps_idempotent_execute_replay(
    engine: ActionEngine, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    proposal = engine.propose(principals[0], action_request("legacy-executed"), now)
    _ = engine.approve(principals[1], proposal.id, now, proposal.payload_hash)
    executed = engine.execute(principals[0], proposal.id, now)
    legacy_payload = executed.payload.model_copy(update={"evidence_refs": ()})
    legacy = executed.model_copy(
        update={
            "payload": legacy_payload,
            "payload_hash": content_hash(legacy_payload.model_dump_json()),
        }
    )
    with engine.store.transaction() as conn:
        engine.store.save_proposal(conn, legacy)

    # When
    replay = engine.execute(principals[0], legacy.id, now)

    # Then
    assert replay == legacy
