from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import Principal, Purpose
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    KnowledgeMutationBatch,
    RetireDocument,
    TombstoneDocument,
)
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query, retrieve
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def service(tmp_path: Path, pack: DomainPack) -> KnowledgeService:
    contracts = registry()
    store = Store(tmp_path / "retrieval.db", pack, contract_resolver=lambda: contracts)
    return KnowledgeService(store, pack, contracts)


def answer(current: KnowledgeService, pack: DomainPack, actor: Principal, now: datetime) -> str:
    with current.store.transaction() as conn:
        active = current.store.current_pack(conn, pack)
    result = retrieve(
        active,
        actor,
        Query(question="managed knowledge", object_id="procedure-1", purpose=Purpose.AUDIT),
        now,
    )
    return "|".join(
        f"{citation.document_id}:{citation.source_version}:{citation.content_sha256}"
        for citation in result.citations
    )


@pytest.mark.parametrize(
    "mutation",
    [
        RetireDocument(document_id="acme.managed-1"),
        TombstoneDocument(document_id="acme.managed-1"),
    ],
)
def test_retire_and_tombstone_remove_document_from_search(
    tmp_path: Path,
    pack: DomainPack,
    now: datetime,
    mutation: RetireDocument | TombstoneDocument,
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    assert "acme.managed-1:1:" in answer(current, pack, actor, now)

    # When
    _ = current.apply(
        actor,
        KnowledgeMutationBatch(
            contract_id="knowledge-contract",
            request_key="retire-search",
            expected_tenant_revision=1,
            expected_source_revision=1,
            mutations=(mutation,),
        ),
        now,
    )

    # Then
    assert "acme.managed-1" not in answer(current, pack, actor, now)


def test_replacement_returns_only_new_evidence_version(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    first = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    old_hash = first.documents[0].content_sha256

    # When
    second = current.apply(
        actor,
        upsert_batch(
            now + timedelta(days=30),
            request_key="replace-search",
            tenant_revision=1,
            source_revision=1,
            document=candidate(source_version="2", content=b"managed knowledge replacement"),
        ),
        now,
    )

    # Then
    evidence = answer(current, pack, actor, now)
    assert f"acme.managed-1:2:{second.documents[0].content_sha256}" in evidence
    assert old_hash not in evidence


def test_acl_change_removes_document_from_previous_group_search(
    tmp_path: Path,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    current = service(tmp_path, pack)
    actor = management_actor()
    _ = current.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    auditor = principals[2]
    assert "acme.managed-1:1:" in answer(current, pack, auditor, now)
    private_access = candidate().access.model_copy(update={"groups": frozenset({"private"})})

    # When
    _ = current.apply(
        actor,
        KnowledgeMutationBatch(
            contract_id="knowledge-contract",
            request_key="acl-search",
            expected_tenant_revision=1,
            expected_source_revision=1,
            mutations=(ChangeDocumentAccess(document_id="acme.managed-1", access=private_access),),
        ),
        now,
    )

    # Then
    assert "acme.managed-1" not in answer(current, pack, auditor, now)
