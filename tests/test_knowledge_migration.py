import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from ax_starter.action_contracts import ProposeRequest
from ax_starter.actions import ActionEngine
from ax_starter.common import AXError, Principal
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import SourceSnapshotDocument, SourceSnapshotInput
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def test_v1_restart_migrates_documents_and_preserves_operational_state(
    tmp_path: Path,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    path = tmp_path / "v1.db"
    original = Store(path, pack)
    engine = ActionEngine(original, pack, principals)
    proposal = engine.propose(
        principals[0],
        ProposeRequest(
            action_type="mark_reviewed",
            object_id="request-1",
            new_status="reviewed",
            expected_version=1,
            evidence_ids=("sop-1",),
            request_key="before-migration",
        ),
        now,
    )
    with sqlite3.connect(path) as conn:
        for table in (
            "knowledge_batches",
            "knowledge_source_state",
            "knowledge_tenant_state",
            "knowledge_documents",
            "knowledge_accepted_versions",
        ):
            _ = conn.execute(f"DROP TABLE {table}")
        _ = conn.execute("DELETE FROM meta WHERE id = 'schema_version'")

    # When
    migrated = Store(path, pack)

    # Then
    with migrated.transaction() as conn:
        assert migrated.proposal(conn, proposal.id) == proposal
        assert migrated.entity(conn, "request-1").version == 1
        assert migrated.audit_check(conn, "acme").event_count == 1
        assert conn.execute("SELECT value FROM meta WHERE id = 'schema_version'").fetchone() == (
            "4",
        )
        assert conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone() == (
            len(pack.documents),
        )
        migrated_documents = {item.id: item for item in migrated.current_pack(conn, pack).documents}
        assert migrated_documents == {item.id: item for item in pack.documents}


def test_v2_restart_adds_watermark_namespace_and_version_history(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    path = tmp_path / "v2.db"
    contracts = registry()
    original = Store(path, pack, contract_resolver=lambda: contracts)
    service = KnowledgeService(original, pack, contracts)
    actor = management_actor()
    _ = service.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    _ = service.apply(
        actor,
        upsert_batch(
            now + timedelta(days=30),
            request_key="version-2",
            tenant_revision=1,
            source_revision=1,
            document=candidate(source_version="2", content=b"version two"),
        ),
        now,
    )
    _downgrade_to_v2(path)

    # When
    migrated = Store(path, pack)
    older_snapshot = SourceSnapshotInput(
        contract_id="knowledge-contract",
        request_key="older-after-migration",
        expected_tenant_revision=2,
        expected_source_revision=2,
        documents=(
            SourceSnapshotDocument(
                candidate=candidate(source_version="3", content=b"older"),
                title="Older snapshot",
                valid_until=now + timedelta(days=30),
            ),
        ),
        observed_at=now - timedelta(minutes=1),
    )

    # Then
    with migrated.transaction() as conn:
        assert conn.execute("SELECT value FROM meta WHERE id = 'schema_version'").fetchone() == (
            "4",
        )
        source_rows = cast(
            "list[tuple[str]]",
            conn.execute("SELECT name FROM pragma_table_info('knowledge_source_state')").fetchall(),
        )
        batch_rows = cast(
            "list[tuple[str]]",
            conn.execute("SELECT name FROM pragma_table_info('knowledge_batches')").fetchall(),
        )
        source_columns = {row[0] for row in source_rows}
        batch_columns = {row[0] for row in batch_rows}
        assert "last_observed_at" in source_columns
        assert "request_kind" in batch_columns
        assert conn.execute(
            """SELECT source_version FROM knowledge_accepted_versions
            WHERE document_id = 'acme.managed-1' ORDER BY source_version"""
        ).fetchall() == [("1",), ("2",)]
        assert conn.execute(
            """SELECT last_observed_at FROM knowledge_source_state
            WHERE tenant = 'acme' AND source_identifier = 'source-a'"""
        ).fetchone() == (now.isoformat(),)
    with pytest.raises(AXError, match="snapshot_watermark_conflict"):
        _ = KnowledgeService(migrated, pack, contracts).import_snapshot(
            management_actor(), older_snapshot, now + timedelta(minutes=1)
        )


def test_v2_migration_without_audit_uses_migration_time_watermark(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    path = tmp_path / "v2-audit-gap.db"
    contracts = registry()
    original = Store(path, pack, contract_resolver=lambda: contracts)
    _ = KnowledgeService(original, pack, contracts).apply(
        management_actor(), upsert_batch(now + timedelta(days=30)), now
    )
    with sqlite3.connect(path) as conn:
        _ = conn.execute("DELETE FROM audit")
    _downgrade_to_v2(path)

    # When
    migrated = Store(path, pack)
    with migrated.transaction() as conn:
        row = cast(
            "tuple[str | None] | None",
            conn.execute(
                """SELECT last_observed_at FROM knowledge_source_state
                WHERE tenant = 'acme' AND source_identifier = 'source-a'"""
            ).fetchone(),
        )
        assert row is not None
        assert row[0] is not None
        watermark = datetime.fromisoformat(str(row[0]))
    older_snapshot = SourceSnapshotInput(
        contract_id="knowledge-contract",
        request_key="audit-gap-older",
        expected_tenant_revision=1,
        expected_source_revision=1,
        documents=(
            SourceSnapshotDocument(
                candidate=candidate(source_version="2", content=b"older"),
                title="Older snapshot",
                valid_until=watermark + timedelta(days=30),
            ),
        ),
        observed_at=watermark - timedelta(minutes=1),
    )

    # Then
    with pytest.raises(AXError, match="snapshot_watermark_conflict"):
        _ = KnowledgeService(migrated, pack, contracts).import_snapshot(
            management_actor(), older_snapshot, watermark + timedelta(minutes=1)
        )


def _downgrade_to_v2(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        _ = conn.execute("DROP TABLE knowledge_accepted_versions")
        _ = conn.execute("ALTER TABLE knowledge_source_state RENAME TO source_state_v3")
        _ = conn.execute(
            """CREATE TABLE knowledge_source_state (
            tenant TEXT NOT NULL, source_identifier TEXT NOT NULL,
            revision INTEGER NOT NULL, state_hash TEXT NOT NULL,
            PRIMARY KEY (tenant, source_identifier))"""
        )
        _ = conn.execute(
            """INSERT INTO knowledge_source_state
            SELECT tenant, source_identifier, revision, state_hash FROM source_state_v3"""
        )
        _ = conn.execute("DROP TABLE source_state_v3")
        _ = conn.execute("ALTER TABLE knowledge_batches RENAME TO batches_v3")
        _ = conn.execute(
            """CREATE TABLE knowledge_batches (
            tenant TEXT NOT NULL, contract_id TEXT NOT NULL, request_key TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL,
            PRIMARY KEY (tenant, contract_id, request_key))"""
        )
        _ = conn.execute(
            """INSERT INTO knowledge_batches
            SELECT tenant, contract_id, request_key, payload_sha256, receipt_json
            FROM batches_v3 WHERE request_kind = 'apply'"""
        )
        _ = conn.execute("DROP TABLE batches_v3")
        _ = conn.execute("UPDATE meta SET value = '2' WHERE id = 'schema_version'")
