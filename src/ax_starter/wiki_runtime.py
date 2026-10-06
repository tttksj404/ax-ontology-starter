from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ax_starter.common import Principal, Sensitivity
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from ax_starter.wiki_contracts import WikiCompilerCallable, WikiCompileRequest


@dataclass(frozen=True, slots=True)
class WikiRuntime:
    store: Store
    template: DomainPack
    credential_guard: Callable[[], None] | None
    principal_resolver: Callable[[], tuple[Principal, ...]] | None
    clock: Callable[[], datetime] | None
    server_query_floor: Sensitivity


@dataclass(frozen=True, slots=True)
class CompileCommand:
    actor: Principal
    request: WikiCompileRequest
    now: datetime
    compiler: WikiCompilerCallable
