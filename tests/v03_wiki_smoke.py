"""Installed-wheel Wiki CLI, real HTTP, persistence and source lifecycle probes."""

from pathlib import Path

from pydantic import TypeAdapter

from ax_starter.common import Sensitivity
from ax_starter.knowledge_contracts import (
    KnowledgeMutationBatch,
    KnowledgeMutationReceipt,
    RetireDocument,
    TombstoneDocument,
)
from ax_starter.retrieval import Query
from ax_starter.wiki_contracts import (
    WikiAnswer,
    WikiCompileRequest,
    WikiDraft,
    WikiExport,
    WikiIndexEntry,
    WikiKind,
    WikiLintFinding,
    WikiPage,
)
from tests.v02_runtime_smoke import command, write_contract


def verify_wiki(environment: dict[str, str], reviewer: str, pilot: Path) -> WikiPage:
    # Initial managed raw snapshot, revision 1. The original file remains unmodified.
    _ = command(environment, ("knowledge", "import", str(pilot / "source-snapshot.json")))
    task = WikiCompileRequest(
        request_key="wheel-wiki-1",
        page_id="acme.review-policy",
        title="추가 검토 정책",
        kind=WikiKind.PROCEDURE,
        query=Query(
            question="추가 검토 정책", object_id="request-1", sensitivity=Sensitivity.INTERNAL
        ),
    )
    arguments = ("wiki", "compile", write_contract(pilot / "wiki-request.json", task))
    draft = WikiDraft.model_validate_json(command(environment, arguments))
    replay = WikiDraft.model_validate_json(command(environment, arguments))
    assert draft == replay
    assert "acme.pilot-policy-1" in {
        binding.document_id for binding in draft.payload.source_bindings
    }
    assert WikiDraft.model_validate_json(command(environment, ("wiki", "draft", draft.id))) == draft
    _ = command(
        {key: value for key, value in environment.items() if key != "AX_TOKEN"},
        ("wiki", "index"),
        1,
        "AX_TOKEN_required",
    )
    publish = ("wiki", "publish", draft.id, "--reviewed-hash", draft.payload_hash)
    _ = command(environment, publish, 1, "access_denied")
    review_environment = {**environment, "AX_TOKEN": reviewer}
    review_packet = WikiDraft.model_validate_json(
        command(review_environment, ("wiki", "draft", draft.id))
    )
    assert review_packet.payload.input_citations == draft.payload.input_citations
    assert review_packet.payload_hash == draft.payload_hash
    _ = command(
        review_environment,
        ("wiki", "publish", draft.id, "--reviewed-hash", "0" * 64),
        1,
        "wiki_review_hash_mismatch",
    )
    page = WikiPage.model_validate_json(command(review_environment, publish))
    assert WikiPage.model_validate_json(command(review_environment, publish)) == page
    recovered = WikiPage.model_validate_json(command(environment, ("wiki", "page", page.page_id)))
    assert recovered == page
    index = TypeAdapter(tuple[WikiIndexEntry, ...]).validate_json(
        command(environment, ("wiki", "index"))
    )
    assert index[0].page_id == page.page_id
    answer = WikiAnswer.model_validate_json(command(environment, ("wiki", "query", "추가 검토")))
    assert answer.pages[0].page_id == page.page_id
    assert all(cite.document_id != page.page_id for cite in answer.answer.citations)
    snapshot = WikiExport.model_validate_json(
        command(environment, ("wiki", "export", page.page_id))
    )
    assert snapshot.text.startswith("AX_DERIVED_WIKI_V1")
    assert snapshot.manifest.non_authoritative
    assert command(environment, ("wiki", "lint")).strip() == "[]"
    return page


def verify_wiki_invalidation(environment: dict[str, str], pilot: Path, page: WikiPage) -> None:
    for revision, mutation in enumerate(
        (
            RetireDocument(document_id="acme.pilot-policy-1"),
            TombstoneDocument(document_id="acme.pilot-policy-1"),
        ),
        start=1,
    ):
        task = KnowledgeMutationBatch(
            contract_id="demo-knowledge",
            request_key=f"wheel-wiki-delete-{revision}",
            expected_tenant_revision=revision,
            expected_source_revision=revision,
            mutations=(mutation,),
        )
        receipt = KnowledgeMutationReceipt.model_validate_json(
            command(
                environment,
                ("knowledge", "apply", write_contract(pilot / "wiki-mutation.json", task)),
            )
        )
        assert receipt.tenant_revision == revision + 1
        _ = command(environment, ("wiki", "page", page.page_id), 1, "wiki_page_not_found")
        _ = command(environment, ("wiki", "export", page.page_id), 1, "wiki_page_not_found")
        assert command(environment, ("wiki", "index")).strip() == "[]"
        findings = TypeAdapter[tuple[WikiLintFinding, ...]](
            tuple[WikiLintFinding, ...]
        ).validate_json(command(environment, ("wiki", "lint")))
        if isinstance(mutation, RetireDocument):
            assert len(findings) == 1
            assert findings[0].page_id == page.page_id
            assert findings[0].revision == page.revision
            assert findings[0].state == "stale"
            assert findings[0].reason == "head_stale"
        else:
            assert findings == ()
