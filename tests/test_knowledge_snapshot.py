from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import AXError, Principal
from ax_starter.data_contracts import DocumentCandidate
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import SourceSnapshotDocument, SourceSnapshotInput
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def service(tmp_path: Path, pack: DomainPack) -> KnowledgeService:
    contracts = registry()
    store = Store(tmp_path / "snapshot.db", pack, contract_resolver=lambda: contracts)
    return KnowledgeService(store, pack, contracts)


def snapshot(
    now: datetime,
    *,
    request_key: str,
    observed_at: datetime,
    document: DocumentCandidate | None = None,
    revisions: tuple[int, int] = (0, 0),
) -> SourceSnapshotInput:
    return SourceSnapshotInput(
        contract_id="knowledge-contract",
        request_key=request_key,
        expected_tenant_revision=revisions[0],
        expected_source_revision=revisions[1],
        documents=(
            SourceSnapshotDocument(
                candidate=document or candidate(),
                title="Snapshot",
                valid_until=now + timedelta(days=30),
            ),
        ),
        observed_at=observed_at,
    )


def test_snapshot_import_uses_the_same_contract_and_apply_path(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    source = snapshot(now, request_key="snapshot", observed_at=now)

    # When
    receipt = current.import_snapshot(management_actor(), source, now)

    # Then
    assert receipt.tenant_revision == 1
    assert receipt.origin_authenticated is False


@pytest.mark.parametrize(
    ("observed_delta", "error_code"),
    [
        (timedelta(seconds=1), "snapshot_observed_in_future"),
        (timedelta(hours=-25), "snapshot_stale"),
    ],
)
def test_snapshot_import_rejects_invalid_observation_time(
    tmp_path: Path,
    pack: DomainPack,
    now: datetime,
    observed_delta: timedelta,
    error_code: str,
) -> None:
    # Given
    current = service(tmp_path, pack)
    source = snapshot(
        now,
        request_key="invalid-observation",
        observed_at=now + observed_delta,
    )

    # When / Then
    with pytest.raises(AXError, match=error_code) as raised:
        _ = current.import_snapshot(management_actor(), source, now)
    assert raised.value.status == 422
    assert current.state(management_actor()).tenant_revision == 0


def test_accepted_snapshot_replay_is_allowed_after_refresh_interval(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    source = snapshot(now, request_key="snapshot-replay", observed_at=now)
    accepted = current.import_snapshot(actor, source, now)

    # When
    replay = current.import_snapshot(actor, source, now + timedelta(hours=25))

    # Then
    assert replay == accepted
    assert current.state(actor).tenant_revision == 1


def test_snapshot_envelope_change_conflicts_with_accepted_request_key(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    accepted = snapshot(now, request_key="bound-envelope", observed_at=now)
    _ = current.import_snapshot(actor, accepted, now)
    changed = accepted.model_copy(update={"observed_at": now + timedelta(seconds=1)})

    # When / Then
    with pytest.raises(AXError, match="idempotency_conflict"):
        _ = current.import_snapshot(actor, changed, now + timedelta(seconds=1))
    assert current.state(actor).tenant_revision == 1


def test_apply_and_import_request_keys_have_separate_namespaces(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    source = snapshot(now, request_key="shared-key", observed_at=now)
    _ = current.import_snapshot(actor, source, now)
    replacement = candidate(source_version="2", content=b"replacement")

    # When
    receipt = current.apply(
        actor,
        upsert_batch(
            now + timedelta(days=30),
            request_key="shared-key",
            tenant_revision=1,
            source_revision=1,
            document=replacement,
        ),
        now,
    )

    # Then
    assert receipt.documents[0].source_version == "2"


def test_snapshot_source_watermark_blocks_older_acl_reimport(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    broad_access = candidate().access.model_copy(
        update={"groups": frozenset({"procurement", "private"})}
    )
    broad = candidate().model_copy(update={"access": broad_access})
    _ = current.import_snapshot(
        actor,
        snapshot(now, request_key="broad", observed_at=now, document=broad),
        now,
    )
    narrow_access = candidate().access.model_copy(update={"groups": frozenset({"private"})})
    narrow = candidate(source_version="2", content=b"narrow").model_copy(
        update={"access": narrow_access}
    )
    _ = current.import_snapshot(
        actor,
        snapshot(
            now,
            request_key="narrow",
            observed_at=now + timedelta(minutes=2),
            document=narrow,
            revisions=(1, 1),
        ),
        now + timedelta(minutes=2),
    )
    older = candidate(source_version="3", content=b"older broad").model_copy(
        update={"access": broad_access}
    )

    # When / Then
    with pytest.raises(AXError, match="snapshot_watermark_conflict"):
        _ = current.import_snapshot(
            actor,
            snapshot(
                now,
                request_key="older",
                observed_at=now + timedelta(minutes=1),
                document=older,
                revisions=(2, 2),
            ),
            now + timedelta(minutes=3),
        )
    assert current.state(actor).tenant_revision == 2
    with current.store.transaction() as conn:
        document = next(
            item
            for item in current.store.current_pack(conn, pack).documents
            if item.id == "acme.managed-1"
        )
        assert document.access.groups == frozenset({"private"})
        assert current.store.audit_check(conn, "acme").event_count == 2


def test_snapshot_time_validation_follows_contract_authorization(
    tmp_path: Path, pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    stale = snapshot(
        now,
        request_key="unauthorized-snapshot",
        observed_at=now - timedelta(hours=25),
    )

    # When / Then
    with pytest.raises(AXError, match="access_denied"):
        _ = current.import_snapshot(principals[0], stale, now)


def test_credential_guard_blocks_snapshot_replay_after_revocation(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "snapshot-guard.db", pack, contract_resolver=lambda: contracts)
    revoked = False

    def guard() -> None:
        if revoked:
            raise AXError("credential_revoked", 401)

    current = KnowledgeService(store, pack, contracts, credential_guard=guard)
    actor = management_actor()
    source = snapshot(now, request_key="guarded-replay", observed_at=now)
    _ = current.import_snapshot(actor, source, now)
    revoked = True

    # When / Then
    with pytest.raises(AXError, match="credential_revoked"):
        _ = current.import_snapshot(actor, source, now + timedelta(minutes=1))
