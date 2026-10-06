# pyright: reportAny=false
# SQLite result cells are asserted directly in the lifecycle integration case.
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ax_starter.common import AXError, Principal, Purpose
from ax_starter.data_contracts import DataContract, DataContractRegistry
from ax_starter.knowledge import KnowledgeService
from ax_starter.knowledge_contracts import KnowledgeMutationBatch, TombstoneDocument
from ax_starter.knowledge_store import (
    StoredDocument,
    access_hash,
    document_record,
    save_document,
)
from ax_starter.retrieval import Answer, content_hash
from ax_starter.store import Store
from ax_starter.wiki import WikiService
from ax_starter.wiki_contracts import WikiCompilation, WikiCompileRequest
from ax_starter.wiki_schema import migrate_wiki
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_pack,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


@dataclass(frozen=True, slots=True)
class _ManagedContext:
    store: Store
    wiki: WikiService
    knowledge: KnowledgeService
    registries: list[DataContractRegistry]
    contract: DataContract
    author: Principal
    reviewer: Principal


def _managed_context(path: Path, now: datetime) -> _ManagedContext:
    pack = wiki_pack()
    base_contract = registry().contracts[0]
    contract_access = base_contract.access.model_copy(
        update={"purposes": frozenset({Purpose.AUDIT, Purpose.OPERATIONS})}
    )
    contract = base_contract.model_copy(update={"access": contract_access})
    registries = [DataContractRegistry(contracts=(contract,))]
    store = Store(path, pack, contract_resolver=lambda: registries[0])
    with store.transaction() as conn:
        migrate_wiki(conn)
    managed_access = candidate().access.model_copy(
        update={"purposes": frozenset({Purpose.AUDIT, Purpose.OPERATIONS})}
    )
    managed_candidate = candidate(content=b"managed review knowledge").model_copy(
        update={"access": managed_access}
    )
    knowledge = KnowledgeService(store, pack, registries[0])
    _ = knowledge.apply(
        management_actor(),
        upsert_batch(now + timedelta(days=30), document=managed_candidate),
        now,
    )
    author, reviewer = wiki_author(), wiki_reviewer()
    wiki = WikiService(
        store,
        pack,
        principal_resolver=lambda: (author, reviewer),
        server_query_floor=managed_access.sensitivity,
        clock=lambda: now,
    )
    return _ManagedContext(
        store=store,
        wiki=wiki,
        knowledge=knowledge,
        registries=registries,
        contract=contract,
        author=author,
        reviewer=reviewer,
    )


def _managed_request() -> WikiCompileRequest:
    return wiki_request().model_copy(
        update={"query": wiki_request().query.model_copy(update={"question": "managed knowledge"})}
    )


def _change_title(service: WikiService, document_id: str, title: str) -> None:
    with service.store.transaction() as conn:
        stored = document_record(conn, document_id)
        assert stored is not None
        assert stored.document is not None
        changed = stored.document.model_copy(update={"title": title})
        save_document(
            conn,
            StoredDocument(
                meta=stored.meta,
                document=changed,
                access_snapshot=stored.access_snapshot,
            ),
        )


def _revoke_source_acl(service: WikiService, document_id: str) -> None:
    with service.store.transaction() as conn:
        stored = document_record(conn, document_id)
        assert stored is not None
        assert stored.document is not None
        access = stored.document.access.model_copy(update={"groups": frozenset({"private-board"})})
        changed = stored.document.model_copy(update={"access": access})
        save_document(
            conn,
            StoredDocument(
                meta=stored.meta.model_copy(update={"access_sha256": access_hash(access)}),
                document=changed,
                access_snapshot=access,
            ),
        )


def test_source_change_during_compiler_call_fails_post_call_snapshot(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a compiler that changes the raw source after receiving its answer.
    service = wiki_service(tmp_path / "toctou.db", now)

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        _change_title(service, answer.citations[0].document_id, "변경된 원문 제목")
        return extractive_compiler(request, answer)

    # When / Then: the second transaction rejects the stale model output.
    with pytest.raises(AXError, match="wiki_source_stale") as raised:
        _ = service.compile(wiki_author(), wiki_request(), now, compiler)
    assert raised.value.status == 409


def test_compile_replay_revalidates_source_without_calling_model_again(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a durable draft and a raw source that later changes outside the hook path.
    service = wiki_service(tmp_path / "replay-stale.db", now)
    calls = 0

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        nonlocal calls
        calls += 1
        return extractive_compiler(request, answer)

    draft = service.compile(wiki_author(), wiki_request(), now, compiler)
    _change_title(service, draft.payload.source_bindings[0].document_id, "재생 전 변경")

    # When / Then: replay rejects the stale payload before another model call.
    with pytest.raises(AXError, match="wiki_source_stale") as raised:
        _ = service.compile(wiki_author(), wiki_request(), now, compiler)
    assert raised.value.status == 409
    assert calls == 1


def test_fresh_clock_rejects_source_that_expires_during_compilation(
    tmp_path: Path, now: datetime
) -> None:
    # Given: pre-retrieval succeeds but the post-model clock reaches source expiry.
    service = wiki_service(tmp_path / "expiry.db", now)
    source_expiry = service.template.documents[0].valid_until
    service.clock = lambda: source_expiry

    # When / Then: the post-call transaction treats the answer as stale.
    with pytest.raises(AXError, match="wiki_source_stale") as raised:
        _ = service.compile(wiki_author(), wiki_request(), now, extractive_compiler)
    assert raised.value.status == 409


@pytest.mark.parametrize("fake_id", ["acme.review-procedure", "AX_DERIVED_WIKI_V1"])
def test_compiler_cannot_invent_or_self_cite_source_ids(
    tmp_path: Path, now: datetime, fake_id: str
) -> None:
    # Given: a callback substitutes an identifier absent from the raw context.
    service = wiki_service(tmp_path / f"fake-{fake_id}.db", now)

    def compiler(request: WikiCompileRequest, answer: Answer) -> WikiCompilation:
        result = extractive_compiler(request, answer)
        fake = result.citations[0].model_copy(update={"document_id": fake_id})
        return result.model_copy(update={"citations": (fake,)})

    # When / Then: only server-retrieved raw citations may enter the draft.
    with pytest.raises(AXError, match="wiki_citation_invalid") as raised:
        _ = service.compile(wiki_author(), wiki_request(), now, compiler)
    assert raised.value.status == 422


def test_lint_reports_only_visible_full_source_hash_change(tmp_path: Path, now: datetime) -> None:
    # Given: a published page whose visible source title changes without hook execution.
    service = wiki_service(tmp_path / "lint.db", now)
    draft = service.compile(wiki_author(), wiki_request(), now, extractive_compiler)
    page = service.publish(wiki_reviewer(), draft.id, draft.payload_hash, now)
    _change_title(service, page.source_bindings[0].document_id, "새 원문 제목")

    # When / Then: lint exposes only the allowed machine code, while normal reads hide the page.
    findings = service.lint(wiki_author(), Purpose.OPERATIONS, now)
    assert [(item.page_id, item.code) for item in findings] == [(page.page_id, "source_changed")]
    assert service.index(wiki_author(), Purpose.OPERATIONS, now) == ()


def test_acl_revocation_hides_page_and_lint_metadata(tmp_path: Path, now: datetime) -> None:
    # Given: a page is published before its raw source ACL is revoked.
    service = wiki_service(tmp_path / "acl.db", now)
    draft = service.compile(wiki_author(), wiki_request(), now, extractive_compiler)
    page = service.publish(wiki_reviewer(), draft.id, draft.payload_hash, now)
    _revoke_source_acl(service, page.source_bindings[0].document_id)

    # When / Then: title, count, and lint metadata are all suppressed.
    assert service.index(wiki_author(), Purpose.OPERATIONS, now) == ()
    assert service.lint(wiki_author(), Purpose.OPERATIONS, now) == ()
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.page(wiki_author(), page.page_id, Purpose.OPERATIONS, now)


def test_managed_contract_drift_hides_published_page(tmp_path: Path, now: datetime) -> None:
    # Given: wiki compilation uses a live managed document and captures its contract binding.
    context = _managed_context(tmp_path / "managed.db", now)
    draft = context.wiki.compile(context.author, _managed_request(), now, extractive_compiler)
    page = context.wiki.publish(context.reviewer, draft.id, draft.payload_hash, now)
    assert page.source_bindings[0].contract_id == context.contract.id

    # When: the same managed contract id advances to a new live version.
    upgraded = context.contract.model_copy(update={"version": "2"})
    context.registries[0] = DataContractRegistry(contracts=(upgraded,))
    with context.store.transaction() as conn:
        _ = conn.execute(
            """UPDATE knowledge_documents SET contract_version = ?, contract_sha256 = ?
            WHERE document_id = ?""",
            (upgraded.version, content_hash(upgraded.model_dump_json()), "acme.managed-1"),
        )

    # Then: current_pack excludes the drifted source and all page metadata disappears.
    assert context.wiki.index(context.author, Purpose.OPERATIONS, now) == ()
    findings = context.wiki.lint(context.author, Purpose.OPERATIONS, now)
    assert [(item.page_id, item.revision, item.reason) for item in findings] == [
        (page.page_id, page.revision, "source_changed")
    ]


def test_knowledge_tombstone_hook_scrubs_wiki_in_same_service(
    tmp_path: Path, now: datetime
) -> None:
    # Given: a managed source has a reviewed wiki page.
    context = _managed_context(tmp_path / "hook.db", now)
    draft = context.wiki.compile(context.author, _managed_request(), now, extractive_compiler)
    page = context.wiki.publish(context.reviewer, draft.id, draft.payload_hash, now)
    batch = KnowledgeMutationBatch(
        contract_id=context.contract.id,
        request_key="tombstone-source",
        expected_tenant_revision=1,
        expected_source_revision=1,
        mutations=(TombstoneDocument(document_id="acme.managed-1"),),
    )

    # When: the ordinary KnowledgeService tombstone path commits.
    _ = context.knowledge.apply(management_actor(), batch, now + timedelta(seconds=1))

    # Then: its in-transaction hook scrubs both draft and immutable version payloads.
    with context.store.transaction() as conn:
        draft_data = conn.execute(
            "SELECT data FROM wiki_drafts WHERE tenant = ? AND draft_id = ?",
            ("acme", draft.id),
        ).fetchone()
        page_data = conn.execute(
            """SELECT data FROM wiki_page_versions
            WHERE tenant = ? AND page_id = ? AND revision = ?""",
            ("acme", page.page_id, page.revision),
        ).fetchone()
        audit = context.store.audit_check(conn, "acme")
    assert draft_data == (None,)
    assert page_data == (None,)
    assert audit.intact is True
