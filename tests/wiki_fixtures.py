from datetime import datetime
from pathlib import Path

from ax_starter.common import ActorKind, Operation, Principal, Purpose, Sensitivity
from ax_starter.demo import demo_pack
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Answer, Query
from ax_starter.store import Store
from ax_starter.wiki import WikiService
from ax_starter.wiki_contracts import WikiCompilation, WikiCompileRequest, WikiKind
from ax_starter.wiki_schema import migrate_wiki


def wiki_pack() -> DomainPack:
    return demo_pack()


def wiki_author(*, subject: str = "wiki-author", person_id: str = "person-author") -> Principal:
    return Principal(
        subject=subject,
        tenant="acme",
        actor_kind=ActorKind.HUMAN,
        person_id=person_id,
        groups=frozenset({"procurement"}),
        clearance=Sensitivity.RESTRICTED,
        operations=frozenset({Operation.READ, Operation.MANAGE_KNOWLEDGE}),
        purposes=frozenset({Purpose.OPERATIONS}),
    )


def wiki_reviewer(
    *, subject: str = "wiki-reviewer", person_id: str = "person-reviewer"
) -> Principal:
    return Principal(
        subject=subject,
        tenant="acme",
        actor_kind=ActorKind.HUMAN,
        person_id=person_id,
        groups=frozenset({"procurement"}),
        clearance=Sensitivity.RESTRICTED,
        operations=frozenset({Operation.READ, Operation.APPROVE}),
        purposes=frozenset({Purpose.OPERATIONS}),
    )


def wiki_request(*, request_key: str = "wiki-request-1") -> WikiCompileRequest:
    return WikiCompileRequest(
        request_key=request_key,
        page_id="acme.review-procedure",
        title="검토 절차",
        kind=WikiKind.PROCEDURE,
        query=Query(
            question="검토 절차",
            purpose=Purpose.OPERATIONS,
            sensitivity=Sensitivity.INTERNAL,
        ),
    )


def extractive_compiler(
    request: WikiCompileRequest,
    answer: Answer,
) -> WikiCompilation:
    del request
    return WikiCompilation(
        body=answer.text,
        citations=answer.citations,
        compiler_mode="offline_extractive",
        sensitivity=answer.sensitivity,
    )


def wiki_service(
    path: Path,
    now: datetime,
    *,
    principals: tuple[Principal, ...] | None = None,
) -> WikiService:
    pack = wiki_pack()
    store = Store(path, pack)
    with store.transaction() as conn:
        migrate_wiki(conn)
    directory = principals or (wiki_author(), wiki_reviewer())
    return WikiService(
        store,
        pack,
        principal_resolver=lambda: directory,
        clock=lambda: now,
        server_query_floor=Sensitivity.INTERNAL,
    )
