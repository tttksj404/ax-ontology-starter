from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import AXError, Principal
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    KnowledgeMutationBatch,
    RetireDocument,
    TombstoneDocument,
)
from ax_starter.knowledge_store import document_record
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def service(tmp_path: Path, pack: DomainPack) -> KnowledgeService:
    contracts = registry()
    store = Store(tmp_path / "knowledge.db", pack, contract_resolver=lambda: contracts)
    return KnowledgeService(store, pack, contracts)


def test_upsert_is_persisted_and_exact_replay_has_no_new_side_effect(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    batch = upsert_batch(now + timedelta(days=30))

    # When
    first = current.apply(actor, batch, now)
    replay = current.apply(actor, batch, now)

    # Then
    assert replay == first
    assert first.tenant_revision == 1
    assert first.source_revision == 1
    assert first.origin_authenticated is False
    source_heads = {item.source_identifier: item for item in current.state(actor).sources}
    assert source_heads["source-a"].revision == 1
    with current.store.transaction() as conn:
        documents = {item.id for item in current.store.current_pack(conn, pack).documents}
        assert "acme.managed-1" in documents
        assert current.store.audit_check(conn, "acme").event_count == 1


def test_idempotency_payload_conflict_is_rejected(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    first = upsert_batch(now + timedelta(days=30))
    conflict = first.model_copy(
        update={"mutations": (first.mutations[0].model_copy(update={"title": "Changed"}),)}
    )
    _ = current.apply(actor, first, now)

    # When / Then
    with pytest.raises(AXError, match="idempotency_conflict"):
        _ = current.apply(actor, conflict, now)


def test_tenant_and_source_revision_cas_are_enforced(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)

    # When / Then
    with pytest.raises(AXError, match="tenant_revision_conflict"):
        _ = current.apply(
            actor,
            upsert_batch(now + timedelta(days=30), request_key="stale-tenant"),
            now,
        )
    with pytest.raises(AXError, match="source_revision_conflict"):
        _ = current.apply(
            actor,
            upsert_batch(
                now + timedelta(days=30),
                request_key="stale-source",
                tenant_revision=1,
            ),
            now,
        )


def test_retire_excludes_document_and_same_source_version_cannot_replace_it(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    retire = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="retire",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(RetireDocument(document_id="acme.managed-1"),),
    )

    # When
    _ = current.apply(actor, retire, now)

    # Then
    with current.store.transaction() as conn:
        assert "acme.managed-1" not in {
            item.id for item in current.store.current_pack(conn, pack).documents
        }
    with pytest.raises(AXError, match="source_version_reuse"):
        _ = current.apply(
            actor,
            upsert_batch(
                now + timedelta(days=30),
                request_key="same-version",
                tenant_revision=2,
                source_revision=2,
            ),
            now,
        )


def test_tombstone_removes_logical_body_and_cannot_be_recreated(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    tombstone = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="tombstone",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(TombstoneDocument(document_id="acme.managed-1"),),
    )

    # When
    receipt = current.apply(actor, tombstone, now)

    # Then
    assert receipt.documents[0].lifecycle.value == "tombstone"
    with current.store.transaction() as conn:
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.document is None
        assert len(stored.meta.content_sha256) == len(stored.meta.access_sha256) == 64
    replacement = candidate(source_version="2", content=b"replacement")
    with pytest.raises(AXError, match="tombstone_recreation_forbidden"):
        _ = current.apply(
            actor,
            upsert_batch(
                now + timedelta(days=30),
                request_key="recreate",
                tenant_revision=2,
                source_revision=2,
                document=replacement,
            ),
            now,
        )


def test_acl_change_updates_current_pack_and_invalid_document_scope_rolls_back(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    private_access = candidate().access.model_copy(update={"groups": frozenset({"private"})})
    change = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key="change-acl",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(ChangeDocumentAccess(document_id="acme.managed-1", access=private_access),),
    )

    # When
    _ = current.apply(actor, change, now)

    # Then
    with current.store.transaction() as conn:
        documents = current.store.current_pack(conn, pack).documents
        document = next(item for item in documents if item.id == "acme.managed-1")
        assert document.access.groups == frozenset({"private"})
    invalid = upsert_batch(
        now + timedelta(days=30),
        request_key="invalid-scope",
        tenant_revision=2,
        source_revision=2,
        document=candidate(document_id="acme.bad-doc").model_copy(
            update={"object_scope": ("missing-object",)}
        ),
    )
    with pytest.raises(AXError, match="data_contract_violation"):
        _ = current.apply(actor, invalid, now)
    assert current.state(actor).tenant_revision == 2


def test_management_requires_current_tenant_audit_authority(
    tmp_path: Path, pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)

    # When / Then
    with pytest.raises(AXError, match="access_denied"):
        _ = current.apply(principals[0], upsert_batch(now + timedelta(days=30)), now)
    with pytest.raises(AXError, match="access_denied"):
        _ = current.state(principals[0])


def test_state_does_not_expose_another_tenant_source_head(tmp_path: Path, pack: DomainPack) -> None:
    # Given
    current = service(tmp_path, pack)
    with current.store.transaction() as conn:
        _ = conn.execute(
            """INSERT INTO knowledge_source_state
            (tenant, source_identifier, revision, state_hash) VALUES (?, ?, ?, ?)""",
            ("other-tenant", "secret-source", 9, "0" * 64),
        )

    # When
    state = current.state(management_actor())

    # Then
    assert all(item.source_identifier != "secret-source" for item in state.sources)


def test_credential_guard_blocks_apply_replay_and_state_after_revocation(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(tmp_path / "credential-guard.db", pack, contract_resolver=lambda: contracts)
    revoked = False

    def guard() -> None:
        if revoked:
            raise AXError("credential_revoked", 401)

    current = KnowledgeService(store, pack, contracts, credential_guard=guard)
    actor = management_actor()
    batch = upsert_batch(now + timedelta(days=30))
    _ = current.apply(actor, batch, now)
    revoked = True

    # When / Then
    with pytest.raises(AXError, match="credential_revoked"):
        _ = current.apply(actor, batch, now)
    with pytest.raises(AXError, match="credential_revoked"):
        _ = current.state(actor)
