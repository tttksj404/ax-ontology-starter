# pyright: reportAny=false
# sqlite3's DB-API values are untyped; JSON blobs are parsed into frozen contracts here.
import sqlite3
from collections.abc import Callable, Generator
from contextlib import closing, contextmanager
from pathlib import Path

from ax_starter.action_contracts import AuditCheck, AuditEvent, Proposal
from ax_starter.common import AXError
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.knowledge_schema import migrate_knowledge
from ax_starter.knowledge_store import active_documents
from ax_starter.ontology import DomainPack, Entity
from ax_starter.retrieval import content_hash
from ax_starter.wiki_schema import migrate_wiki


class Store:
    def __init__(
        self,
        path: Path,
        pack: DomainPack,
        *,
        busy_timeout_seconds: float = 5,
        contract_resolver: Callable[[], DataContractRegistry | None] | None = None,
    ) -> None:
        self.path: Path = path
        self.busy_timeout_seconds: float = busy_timeout_seconds
        self.contract_resolver: Callable[[], DataContractRegistry | None] | None = contract_resolver
        self.pack_hash: str = content_hash(pack.model_dump_json())
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            _ = conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (id TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            _ = conn.execute(
                "CREATE TABLE IF NOT EXISTS entities (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            )
            _ = conn.execute(
                """CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY,
                tenant TEXT NOT NULL, proposer TEXT NOT NULL, request_key TEXT NOT NULL,
                data TEXT NOT NULL, UNIQUE(tenant, proposer, request_key))"""
            )
            _ = conn.execute(
                """CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant TEXT NOT NULL, data TEXT NOT NULL, previous TEXT NOT NULL,
                hash TEXT NOT NULL)"""
            )
            row = conn.execute("SELECT value FROM meta WHERE id = 'pack_hash'").fetchone()
            if row is not None:
                if str(row[0]) != self.pack_hash:
                    raise AXError("pack_changed_migration_required")
            else:
                _ = conn.execute("INSERT INTO meta VALUES ('pack_hash', ?)", (self.pack_hash,))
                _ = conn.executemany(
                    "INSERT INTO entities VALUES (?, ?)",
                    [(entity.id, entity.model_dump_json()) for entity in pack.objects],
                )
            migrate_knowledge(conn, pack)
            migrate_wiki(conn)

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        try:
            with (
                closing(sqlite3.connect(self.path, timeout=self.busy_timeout_seconds)) as conn,
                conn,
            ):
                _ = conn.execute("PRAGMA foreign_keys = ON")
                _ = conn.execute("BEGIN IMMEDIATE")
                yield conn
        except sqlite3.OperationalError as exc:
            if exc.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise AXError("state_busy", 503) from exc
            raise AXError("state_storage_failed", 503) from exc

    def entity(self, conn: sqlite3.Connection, key: str) -> Entity:
        row = conn.execute("SELECT data FROM entities WHERE id = ?", (key,)).fetchone()
        if row is None:
            raise AXError("object_not_found", 404)
        return Entity.model_validate_json(str(row[0]))

    def save_entity(self, conn: sqlite3.Connection, entity: Entity) -> None:
        _ = conn.execute(
            "UPDATE entities SET data = ? WHERE id = ?", (entity.model_dump_json(), entity.id)
        )

    def current_pack(
        self,
        conn: sqlite3.Connection,
        template: DomainPack,
        *,
        registry: DataContractRegistry | None = None,
    ) -> DomainPack:
        rows = conn.execute("SELECT data FROM entities ORDER BY id").fetchall()
        entities = tuple(Entity.model_validate_json(str(row[0])) for row in rows)
        current_registry = (
            registry
            if registry is not None
            else None
            if self.contract_resolver is None
            else self.contract_resolver()
        )
        return DomainPack(
            id=template.id,
            version=template.version,
            description=template.description,
            object_types=template.object_types,
            link_types=template.link_types,
            action_types=template.action_types,
            objects=entities,
            links=template.links,
            documents=active_documents(conn, current_registry),
        )

    def proposal(self, conn: sqlite3.Connection, key: str) -> Proposal:
        row = conn.execute("SELECT data FROM proposals WHERE id = ?", (key,)).fetchone()
        if row is None:
            raise AXError("proposal_not_found", 404)
        proposal = Proposal.model_validate_json(str(row[0]))
        if content_hash(proposal.payload.model_dump_json()) != proposal.payload_hash:
            raise AXError("proposal_integrity_failure")
        return proposal

    def by_request(
        self, conn: sqlite3.Connection, tenant: str, actor: str, request_key: str
    ) -> Proposal | None:
        row = conn.execute(
            "SELECT id FROM proposals WHERE tenant = ? AND proposer = ? AND request_key = ?",
            (tenant, actor, request_key),
        ).fetchone()
        return self.proposal(conn, str(row[0])) if row else None

    def insert_proposal(self, conn: sqlite3.Connection, proposal: Proposal) -> None:
        _ = conn.execute(
            "INSERT INTO proposals VALUES (?, ?, ?, ?, ?)",
            (
                proposal.id,
                proposal.payload.tenant,
                proposal.payload.proposer,
                proposal.request_key,
                proposal.model_dump_json(),
            ),
        )

    def save_proposal(self, conn: sqlite3.Connection, proposal: Proposal) -> None:
        _ = conn.execute(
            "UPDATE proposals SET data = ? WHERE id = ?", (proposal.model_dump_json(), proposal.id)
        )

    def append_audit(self, conn: sqlite3.Connection, event: AuditEvent) -> None:
        row = conn.execute(
            "SELECT hash FROM audit WHERE tenant = ? ORDER BY seq DESC LIMIT 1", (event.tenant,)
        ).fetchone()
        previous = str(row[0]) if row else "GENESIS"
        data = event.model_dump_json()
        digest = content_hash(previous + "\n" + data)
        _ = conn.execute(
            "INSERT INTO audit (tenant, data, previous, hash) VALUES (?, ?, ?, ?)",
            (event.tenant, data, previous, digest),
        )

    def audit_check(self, conn: sqlite3.Connection, tenant: str) -> AuditCheck:
        rows = conn.execute(
            "SELECT data, previous, hash FROM audit WHERE tenant = ? ORDER BY seq", (tenant,)
        ).fetchall()
        previous = "GENESIS"
        for row in rows:
            data, parent, digest = str(row[0]), str(row[1]), str(row[2])
            if parent != previous or content_hash(parent + "\n" + data) != digest:
                return AuditCheck(intact=False, event_count=len(rows), head_hash=previous)
            previous = digest
        return AuditCheck(intact=True, event_count=len(rows), head_hash=previous)
