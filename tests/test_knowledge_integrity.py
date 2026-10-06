from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, assert_never, cast

import pytest

from ax_starter.common import AXError
from ax_starter.knowledge import KnowledgeService
from ax_starter.ontology import Document, DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


@pytest.mark.parametrize(
    "field",
    ["text", "access", "id", "source_version", "tenant"],
)
def test_document_row_metadata_mismatch_fails_closed(
    tmp_path: Path,
    pack: DomainPack,
    now: datetime,
    field: Literal["text", "access", "id", "source_version", "tenant"],
) -> None:
    # Given
    contracts = registry()
    store = Store(
        tmp_path / f"integrity-{field}.db",
        pack,
        contract_resolver=lambda: contracts,
    )
    _ = KnowledgeService(store, pack, contracts).apply(
        management_actor(), upsert_batch(now + timedelta(days=30)), now
    )
    with store.transaction() as conn:
        row = cast(
            "tuple[str] | None",
            conn.execute(
                """SELECT document_json FROM knowledge_documents
                WHERE document_id = 'acme.managed-1'"""
            ).fetchone(),
        )
        assert row is not None
        document = Document.model_validate_json(row[0])
        changed = _tamper(document, field)
        _ = conn.execute(
            "UPDATE knowledge_documents SET document_json = ? WHERE document_id = 'acme.managed-1'",
            (changed.model_dump_json(),),
        )

    # When / Then
    with store.transaction() as conn:
        with pytest.raises(AXError, match="knowledge_integrity_failure"):
            _ = store.current_pack(conn, pack)
        audit = store.audit_check(conn, "acme")
        assert audit.intact is True
        assert audit.event_count == 1


def test_access_snapshot_hash_mismatch_fails_closed(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    contracts = registry()
    store = Store(
        tmp_path / "access-snapshot-integrity.db",
        pack,
        contract_resolver=lambda: contracts,
    )
    _ = KnowledgeService(store, pack, contracts).apply(
        management_actor(), upsert_batch(now + timedelta(days=30)), now
    )
    changed = candidate().access.model_copy(update={"groups": frozenset({"private"})})
    with store.transaction() as conn:
        _ = conn.execute(
            """UPDATE knowledge_documents SET access_json = ?
            WHERE document_id = 'acme.managed-1'""",
            (changed.model_dump_json(),),
        )

    # When / Then
    with (
        store.transaction() as conn,
        pytest.raises(AXError, match="knowledge_integrity_failure"),
    ):
        _ = store.current_pack(conn, pack)


def _tamper(
    document: Document,
    field: Literal["text", "access", "id", "source_version", "tenant"],
) -> Document:
    match field:
        case "text":
            return document.model_copy(update={"text": "tampered"})
        case "access":
            access = document.access.model_copy(update={"groups": frozenset({"private"})})
            return document.model_copy(update={"access": access})
        case "id":
            return document.model_copy(update={"id": "other-doc"})
        case "source_version":
            return document.model_copy(update={"source_version": "tampered"})
        case "tenant":
            access = document.access.model_copy(update={"tenant": "other-tenant"})
            return document.model_copy(update={"access": access})
        case unreachable:
            assert_never(unreachable)
