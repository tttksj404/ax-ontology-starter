from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import AXError
from ax_starter.data_contracts import DataContractRegistry, DocumentCandidate
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import (
    DocumentLifecycle,
    KnowledgeMutationBatch,
    RetireDocument,
    TombstoneDocument,
)
from ax_starter.knowledge_store import StoredDocument, document_record, save_document
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch


def _tenant_candidate(
    tenant: str,
    document_id: str,
    *,
    empty_groups: bool = False,
    object_id: str = "beta-procedure",
) -> DocumentCandidate:
    base = candidate(document_id=document_id)
    groups: frozenset[str] = frozenset() if empty_groups else base.access.groups
    return base.model_copy(
        update={
            "tenant": tenant,
            "object_scope": (object_id,),
            "access": base.access.model_copy(update={"tenant": tenant, "groups": groups}),
        }
    )


def _services(tmp_path: Path, pack: DomainPack) -> tuple[KnowledgeService, KnowledgeService]:
    acme = registry(tenant="acme")
    beta_base = registry(tenant="beta").contracts[0]
    beta = DataContractRegistry(
        contracts=(beta_base.model_copy(update={"object_scope": ("beta-procedure",)}),)
    )
    contracts = DataContractRegistry(contracts=(*acme.contracts, *beta.contracts))
    tenant_pack = _pack_with_tenant_object(pack, "beta", "beta-procedure")
    store = Store(
        tmp_path / "tenant-namespace.db",
        tenant_pack,
        contract_resolver=lambda: contracts,
    )
    return (
        KnowledgeService(store, tenant_pack, contracts),
        KnowledgeService(store, tenant_pack, contracts),
    )


def _pack_with_tenant_object(pack: DomainPack, tenant: str, object_id: str) -> DomainPack:
    base = next(item for item in pack.objects if item.id == "procedure-1")
    added = base.model_copy(
        update={"id": object_id, "access": base.access.model_copy(update={"tenant": tenant})}
    )
    return DomainPack.model_validate(
        pack.model_copy(update={"objects": (*pack.objects, added)}).model_dump()
    )


@pytest.mark.parametrize("document_id", ["acme.secret-like", "acme.missing-like"])
@pytest.mark.parametrize("empty_groups", [False, True])
def test_foreign_tenant_document_id_is_uniform_422_before_lookup(
    tmp_path: Path,
    pack: DomainPack,
    now: datetime,
    document_id: str,
    *,
    empty_groups: bool,
) -> None:
    # Given
    acme, beta = _services(tmp_path, pack)
    _ = acme.apply(
        management_actor("acme"),
        upsert_batch(
            now + timedelta(days=30),
            document=candidate(document_id="acme.secret-like"),
        ),
        now,
    )
    attack = upsert_batch(
        now + timedelta(days=30),
        request_key=f"attack-{document_id}-{empty_groups}",
        document=_tenant_candidate("beta", document_id, empty_groups=empty_groups),
    )

    # When / Then
    with pytest.raises(AXError, match="data_contract_violation") as raised:
        _ = beta.apply(management_actor("beta"), attack, now)
    assert raised.value.status == 422
    assert acme.state(management_actor("acme")).tenant_revision == 1
    assert beta.state(management_actor("beta")).tenant_revision == 0
    with beta.store.transaction() as conn:
        assert beta.store.audit_check(conn, "acme").event_count == 1
        assert beta.store.audit_check(conn, "beta").event_count == 0


def test_each_tenant_can_create_same_local_document_suffix(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    acme, beta = _services(tmp_path, pack)

    # When
    beta_receipt = beta.apply(
        management_actor("beta"),
        upsert_batch(now + timedelta(days=30), document=_tenant_candidate("beta", "beta.same")),
        now,
    )
    acme_receipt = acme.apply(
        management_actor("acme"),
        upsert_batch(now + timedelta(days=30), document=candidate(document_id="acme.same")),
        now,
    )

    # Then
    assert beta_receipt.documents[0].document_id == "beta.same"
    assert acme_receipt.documents[0].document_id == "acme.same"


def test_tenant_name_with_dots_is_the_exact_document_prefix(
    tmp_path: Path, pack: DomainPack, now: datetime
) -> None:
    # Given
    base = registry(tenant="acme.eu").contracts[0]
    contracts = DataContractRegistry(
        contracts=(base.model_copy(update={"object_scope": ("eu-procedure",)}),)
    )
    tenant_pack = _pack_with_tenant_object(pack, "acme.eu", "eu-procedure")
    store = Store(
        tmp_path / "dotted-tenant.db",
        tenant_pack,
        contract_resolver=lambda: contracts,
    )
    service = KnowledgeService(store, tenant_pack, contracts)

    # When
    receipt = service.apply(
        management_actor("acme.eu"),
        upsert_batch(
            now + timedelta(days=30),
            document=_tenant_candidate("acme.eu", "acme.eu.same", object_id="eu-procedure"),
        ),
        now,
    )

    # Then
    assert receipt.documents[0].document_id == "acme.eu.same"


@pytest.mark.parametrize("operation", ["retire", "tombstone"])
def test_legacy_unqualified_managed_document_remains_cleanable(
    tmp_path: Path,
    pack: DomainPack,
    now: datetime,
    operation: str,
) -> None:
    # Given: simulate a managed row accepted before the namespace rule.
    contracts = registry()
    store = Store(
        tmp_path / f"legacy-{operation}.db",
        pack,
        contract_resolver=lambda: contracts,
    )
    service = KnowledgeService(store, pack, contracts)
    actor = management_actor()
    _ = service.apply(actor, upsert_batch(now + timedelta(days=30)), now)
    with store.transaction() as conn:
        stored = document_record(conn, "acme.managed-1")
        assert stored is not None
        assert stored.document is not None
        save_document(
            conn,
            StoredDocument(
                meta=stored.meta.model_copy(update={"document_id": "legacy-managed"}),
                document=stored.document.model_copy(update={"id": "legacy-managed"}),
                access_snapshot=stored.access_snapshot,
            ),
        )
        _ = conn.execute("DELETE FROM knowledge_documents WHERE document_id = 'acme.managed-1'")
    mutation = (
        RetireDocument(document_id="legacy-managed")
        if operation == "retire"
        else TombstoneDocument(document_id="legacy-managed")
    )
    batch = KnowledgeMutationBatch(
        contract_id="knowledge-contract",
        request_key=f"legacy-{operation}",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(mutation,),
    )

    # When
    _ = service.apply(actor, batch, now)

    # Then
    with store.transaction() as conn:
        cleaned = document_record(conn, "legacy-managed")
        assert cleaned is not None
        expected = (
            DocumentLifecycle.RETIRED if operation == "retire" else DocumentLifecycle.TOMBSTONE
        )
        assert cleaned.meta.lifecycle is expected
        if operation == "tombstone":
            assert cleaned.document is None
