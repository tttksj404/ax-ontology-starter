from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from ax_starter.common import AXError, Contract, Principal, Purpose, Sensitivity
from ax_starter.demo import DemoDomain, demo_pack, demo_principals
from ax_starter.providers import ProviderConfig
from ax_starter.retrieval import Query
from ax_starter.store import Store
from ax_starter.v02_examples import demo_steward
from ax_starter.wiki import WikiService
from ax_starter.wiki_compiler import compile_wiki
from ax_starter.wiki_contracts import WikiCompileRequest, WikiKind


class WikiDemoReport(Contract):
    synthetic: bool = True
    model_executed: bool = False
    domain: DemoDomain
    compiler_mode: str
    page_id: str
    revision: int
    raw_citation_ids: tuple[str, ...]
    self_review_blocked: bool
    persisted_after_restart: bool
    expired_source_hidden: bool
    export_non_authoritative: bool


def run_wiki_demo(domain: DemoDomain) -> WikiDemoReport:
    now = datetime(2026, 10, 2, tzinfo=UTC)
    pack = demo_pack(domain, as_of=now)
    identities = tuple(
        actor.model_copy(update={"clearance": Sensitivity.RESTRICTED})
        for actor in demo_principals(domain)
    )
    author = demo_steward(identities[0])
    directory: tuple[Principal, ...] = (*identities, author)
    reviewer = identities[1]
    request = WikiCompileRequest(
        request_key="demo-wiki",
        page_id="acme.review-procedure",
        title="업무 검토 절차",
        kind=WikiKind.PROCEDURE,
        query=Query(question="검토 절차", object_id="request-1"),
    )
    with TemporaryDirectory(prefix="ax-wiki-demo-") as temporary:
        database = Path(temporary) / "wiki.db"
        service = WikiService(
            Store(database, pack), pack, principal_resolver=lambda: directory, clock=lambda: now
        )
        draft = service.compile(
            author, request, now, lambda task, answer: compile_wiki(ProviderConfig(), task, answer)
        )
        self_review_blocked = False
        try:
            _ = service.publish(author, draft.id, draft.payload_hash, now)
        except AXError as exc:
            if exc.code != "access_denied":
                raise
            self_review_blocked = True
        page = service.publish(reviewer, draft.id, draft.payload_hash, now)
        reopened = WikiService(
            Store(database, pack), pack, principal_resolver=lambda: directory, clock=lambda: now
        )
        answer = reopened.query(author, request.query, now)
        snapshot = reopened.export(author, page.page_id, Purpose.OPERATIONS, now)
        return WikiDemoReport(
            domain=domain,
            compiler_mode=draft.compiler_mode,
            page_id=page.page_id,
            revision=page.revision,
            raw_citation_ids=tuple(cite.document_id for cite in answer.answer.citations),
            self_review_blocked=self_review_blocked,
            persisted_after_restart=reopened.page(author, page.page_id, Purpose.OPERATIONS, now)
            == page,
            expired_source_hidden=not reopened.index(
                author, Purpose.OPERATIONS, now + timedelta(days=366)
            ),
            export_non_authoritative=snapshot.manifest.non_authoritative,
        )
