import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, assert_never

import pytest
from pydantic import ValidationError

from ax_starter.common import Purpose
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.evidence_roles import EvidenceRole, EvidenceRoleEntry
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_store import document_record
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query, content_hash, retrieve
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def derived_registry(base: DataContractRegistry) -> DataContractRegistry:
    return DataContractRegistry(
        contracts=base.contracts,
        evidence_roles=(
            EvidenceRoleEntry(
                tenant="acme", contract_id="knowledge-contract", role=EvidenceRole.DERIVED_OUTPUT
            ),
        ),
    )


def test_derived_contract_is_retained_but_excluded_from_raw_retrieval(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    original = registry()
    live = [original]
    store = Store(tmp_path / "roles.db", pack, contract_resolver=lambda: live[0])
    actor = management_actor()
    service = KnowledgeService(store, pack, original)
    _ = service.apply(actor, upsert_batch(now + timedelta(days=1)), now)
    query = Query(question="managed", purpose=Purpose.AUDIT)
    with store.transaction() as conn:
        before = retrieve(store.current_pack(conn, pack), actor, query, now)
    # When
    live[0] = derived_registry(original)
    with store.transaction() as conn:
        current = store.current_pack(conn, pack)
        retained = document_record(conn, "acme.managed-1")
    after = retrieve(current, actor, query, now)
    # Then
    assert "acme.managed-1" in {cite.document_id for cite in before.citations}
    assert "acme.managed-1" not in {cite.document_id for cite in after.citations}
    assert retained is not None
    assert retained.document is not None
    assert original.contracts[0].model_dump_json() == live[0].contracts[0].model_dump_json()
    assert content_hash(original.contracts[0].model_dump_json()) == content_hash(
        live[0].contracts[0].model_dump_json()
    )


@pytest.mark.parametrize("representation", ["plain", "bom", "wrapper", "wrapper-bom"])
def test_export_marker_cannot_become_raw_evidence(
    tmp_path: Path,
    pack: DomainPack,
    now: datetime,
    representation: Literal["plain", "bom", "wrapper", "wrapper-bom"],
) -> None:
    # Given: even a wrongly labelled raw contract contains the recognizable export marker.
    original = registry()
    store = Store(tmp_path / "marked.db", pack, contract_resolver=lambda: original)
    actor = management_actor()
    service = KnowledgeService(store, pack, original)
    exported = "AX_DERIVED_WIKI_V1\nmanaged derived content"
    match representation:
        case "plain":
            pass
        case "bom":
            exported = "\ufeff \n" + exported
        case "wrapper":
            exported = json.dumps({"text": exported, "manifest": {"non_authoritative": True}})
        case "wrapper-bom":
            exported = "\ufeff \n" + json.dumps({"text": "\ufeff \n" + exported})
        case unreachable:
            assert_never(unreachable)
    marked = candidate(content=exported.encode("utf-8"))
    # When
    _ = service.apply(actor, upsert_batch(now + timedelta(days=1), document=marked), now)
    with store.transaction() as conn:
        answer = retrieve(
            store.current_pack(conn, pack),
            actor,
            Query(question="managed", purpose=Purpose.AUDIT),
            now,
        )
    # Then
    assert "acme.managed-1" not in {cite.document_id for cite in answer.citations}


@pytest.mark.parametrize("duplicate", [False, True])
def test_registry_rejects_unknown_or_duplicate_source_role(duplicate: bool) -> None:
    # Given
    base = registry()
    role = EvidenceRoleEntry(
        tenant="acme",
        contract_id="knowledge-contract" if duplicate else "unknown-contract",
        role=EvidenceRole.DERIVED_OUTPUT,
    )
    # When / Then
    with pytest.raises(ValidationError):
        _ = DataContractRegistry(
            contracts=base.contracts, evidence_roles=(role, role) if duplicate else (role,)
        )


@pytest.mark.parametrize("text", ['{"text":"managed raw source"}', '{"managed":'])
def test_unmarked_json_remains_raw_evidence(
    tmp_path: Path, pack: DomainPack, now: datetime, text: str
) -> None:
    # Given: JSON-shaped input does not prove Wiki origin.
    original = registry()
    store = Store(tmp_path / "raw-json.db", pack, contract_resolver=lambda: original)
    actor = management_actor()
    service = KnowledgeService(store, pack, original)
    source = candidate(content=text.encode("utf-8"))
    # When
    _ = service.apply(actor, upsert_batch(now + timedelta(days=1), document=source), now)
    with store.transaction() as conn:
        answer = retrieve(
            store.current_pack(conn, pack),
            actor,
            Query(question="managed", purpose=Purpose.AUDIT),
            now,
        )
    # Then
    assert "acme.managed-1" in {cite.document_id for cite in answer.citations}
