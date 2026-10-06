from collections.abc import Callable
from datetime import datetime

from ax_starter.common import Principal, Purpose, Sensitivity
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query
from ax_starter.store import Store
from ax_starter.wiki_compile_flow import compile_wiki
from ax_starter.wiki_contracts import (
    WikiAnswer,
    WikiCompilerCallable,
    WikiCompileRequest,
    WikiDraft,
    WikiExport,
    WikiIndexEntry,
    WikiLintFinding,
    WikiPage,
)
from ax_starter.wiki_publish_flow import publish_wiki
from ax_starter.wiki_query_export import export_wiki, lint_wiki, query_wiki
from ax_starter.wiki_reads import index_wiki, read_wiki_page, view_wiki_draft
from ax_starter.wiki_runtime import CompileCommand, WikiRuntime


class WikiService:
    def __init__(  # noqa: PLR0913 - public constructor exposes explicit security dependencies.
        self,
        store: Store,
        template: DomainPack,
        *,
        credential_guard: Callable[[], None] | None = None,
        principal_resolver: Callable[[], tuple[Principal, ...]] | None = None,
        server_query_floor: Sensitivity = Sensitivity.RESTRICTED,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store: Store = store
        self.template: DomainPack = template
        self.credential_guard: Callable[[], None] | None = credential_guard
        self.principal_resolver: Callable[[], tuple[Principal, ...]] | None = principal_resolver
        self.server_query_floor: Sensitivity = server_query_floor
        self.clock: Callable[[], datetime] | None = clock

    def compile(
        self,
        actor: Principal,
        request: WikiCompileRequest,
        now: datetime,
        compiler: WikiCompilerCallable,
    ) -> WikiDraft:
        return compile_wiki(
            self._runtime(),
            CompileCommand(actor=actor, request=request, now=now, compiler=compiler),
        )

    def view_draft(self, actor: Principal, draft_id: str, now: datetime) -> WikiDraft:
        return view_wiki_draft(self._runtime(), actor, draft_id, now)

    def publish(
        self,
        actor: Principal,
        draft_id: str,
        reviewed_payload_hash: str,
        now: datetime,
    ) -> WikiPage:
        return publish_wiki(self._runtime(), actor, draft_id, reviewed_payload_hash, now)

    def index(
        self, actor: Principal, purpose: Purpose, now: datetime
    ) -> tuple[WikiIndexEntry, ...]:
        return index_wiki(self._runtime(), actor, purpose, now)

    def page(
        self,
        actor: Principal,
        page_id: str,
        purpose: Purpose,
        now: datetime,
    ) -> WikiPage:
        return read_wiki_page(self._runtime(), actor, page_id, purpose, now)

    def query(self, actor: Principal, query: Query, now: datetime) -> WikiAnswer:
        return query_wiki(self._runtime(), actor, query, now)

    def lint(
        self, actor: Principal, purpose: Purpose, now: datetime
    ) -> tuple[WikiLintFinding, ...]:
        return lint_wiki(self._runtime(), actor, purpose, now)

    def export(
        self,
        actor: Principal,
        page_id: str,
        purpose: Purpose,
        now: datetime,
    ) -> WikiExport:
        return export_wiki(self._runtime(), actor, page_id, purpose, now)

    def _runtime(self) -> WikiRuntime:
        return WikiRuntime(
            store=self.store,
            template=self.template,
            credential_guard=self.credential_guard,
            principal_resolver=self.principal_resolver,
            clock=self.clock,
            server_query_floor=self.server_query_floor,
        )
