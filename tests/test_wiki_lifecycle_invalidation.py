# pyright: reportAny=false
# SQLite result cells are asserted directly in this persistence test.
from datetime import datetime
from pathlib import Path

import pytest

from ax_starter.common import AXError, Purpose, Sensitivity
from ax_starter.ontology import Document, Entity
from ax_starter.store import Store
from ax_starter.wiki import WikiService
from ax_starter.wiki_contracts import WikiDraft, WikiDraftState, WikiPage
from ax_starter.wiki_schema import invalidate_wiki_sources
from tests.wiki_fixtures import (
    extractive_compiler,
    wiki_author,
    wiki_request,
    wiki_reviewer,
    wiki_service,
)


class BatchAbortError(RuntimeError):
    """Force the surrounding SQLite transaction to roll back."""


def _published_service(path: Path, now: datetime) -> tuple[WikiService, WikiDraft, WikiPage]:
    service = wiki_service(path, now)
    draft = service.compile(wiki_author(), wiki_request(), now, extractive_compiler)
    page = service.publish(wiki_reviewer(), draft.id, draft.payload_hash, now)
    return service, draft, page


def _abort_invalidation(service: WikiService, source_id: str) -> None:
    with service.store.transaction() as conn:
        invalidate_wiki_sources(conn, "acme", (source_id,), ())
        raise BatchAbortError


def _two_source_service(path: Path, now: datetime) -> WikiService:
    base = wiki_service(path, now)
    pack = base.template
    access = pack.documents[0].access
    entity = Entity(
        id="procedure-2",
        type="Procedure",
        label="정산 전용 절차",
        access=access,
        properties=pack.objects[1].properties,
        source="synthetic:procedure-2",
    )
    document = Document(
        id="sop-2",
        object_ids=(entity.id,),
        title="정산 전용 절차",
        text="정산 전용 근거입니다.",
        source_uri="synthetic://sop/settlement",
        source_version="1",
        access=access,
        valid_until=pack.documents[0].valid_until,
    )
    expanded = pack.model_copy(
        update={"objects": (*pack.objects, entity), "documents": (*pack.documents, document)}
    )
    store = Store(path.with_name(f"expanded-{path.name}"), expanded)
    author, reviewer = wiki_author(), wiki_reviewer()
    return WikiService(
        store,
        expanded,
        principal_resolver=lambda: (author, reviewer),
        server_query_floor=Sensitivity.INTERNAL,
        clock=lambda: now,
    )


def _publish_two_revisions(
    service: WikiService, now: datetime
) -> tuple[WikiDraft, WikiDraft, WikiPage]:
    first_request = wiki_request().model_copy(
        update={
            "query": wiki_request().query.model_copy(update={"object_id": "procedure-1", "hops": 0})
        }
    )
    first = service.compile(wiki_author(), first_request, now, extractive_compiler)
    _ = service.publish(wiki_reviewer(), first.id, first.payload_hash, now)
    second_request = wiki_request(request_key="revision-2").model_copy(
        update={
            "expected_page_revision": 1,
            "query": wiki_request().query.model_copy(
                update={
                    "question": "정산 전용",
                    "object_id": "procedure-2",
                    "hops": 0,
                }
            ),
        }
    )
    second = service.compile(wiki_author(), second_request, now, extractive_compiler)
    page = service.publish(wiki_reviewer(), second.id, second.payload_hash, now)
    return first, second, page


def test_changed_source_hides_page_and_draft_metadata(tmp_path: Path, now: datetime) -> None:
    # Given: a published page bound to a raw document.
    service, draft, page = _published_service(tmp_path / "changed.db", now)
    source_id = page.source_bindings[0].document_id

    # When: the knowledge transaction invalidates that source.
    with service.store.transaction() as conn:
        invalidate_wiki_sources(conn, "acme", (source_id,), ())
        audit = service.store.audit_check(conn, "acme")

    # Then: neither page title nor draft payload is observable.
    assert service.index(wiki_author(), Purpose.OPERATIONS, now) == ()
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.page(wiki_author(), page.page_id, Purpose.OPERATIONS, now)
    with pytest.raises(AXError, match="wiki_draft_not_found"):
        _ = service.view_draft(wiki_author(), draft.id, now)
    assert audit.intact is True
    assert audit.event_count == 4


def test_tombstone_scrubs_all_dependent_json(tmp_path: Path, now: datetime) -> None:
    # Given: a draft and immutable published version still retain derived text.
    service, draft, page = _published_service(tmp_path / "scrub.db", now)
    source_id = page.source_bindings[0].document_id

    # When: the source is tombstoned in the same SQLite transaction.
    with service.store.transaction() as conn:
        invalidate_wiki_sources(conn, "acme", (), (source_id,))

    # Then: title/body/query/citations are physically absent from live table cells.
    with service.store.transaction() as conn:
        draft_data = conn.execute(
            "SELECT data FROM wiki_drafts WHERE tenant = ? AND draft_id = ?",
            ("acme", draft.id),
        ).fetchone()
        version_data = conn.execute(
            """SELECT data FROM wiki_page_versions
            WHERE tenant = ? AND page_id = ? AND revision = ?""",
            ("acme", page.page_id, page.revision),
        ).fetchone()
    assert draft_data == (None,)
    assert version_data == (None,)
    replacement = wiki_request(request_key="replacement").model_copy(
        update={"expected_page_revision": page.revision}
    )
    with pytest.raises(AXError, match="wiki_page_not_found"):
        _ = service.compile(wiki_author(), replacement, now, extractive_compiler)


def test_historical_tombstone_scrubs_only_dependent_revision_and_draft(
    tmp_path: Path, now: datetime
) -> None:
    # Given: revision one depends on sop-1 and the clean current revision depends on sop-2.
    service = _two_source_service(tmp_path / "historical.db", now)
    first, second, current = _publish_two_revisions(service, now)
    assert current.revision == 2
    assert {item.document_id for item in current.source_bindings} == {"sop-2"}

    # When: only the source used by historical revision one is tombstoned.
    with service.store.transaction() as conn:
        invalidate_wiki_sources(conn, "acme", (), ("sop-1",))
        rows = conn.execute(
            """SELECT revision, data FROM wiki_page_versions
            WHERE tenant = ? AND page_id = ? ORDER BY revision""",
            ("acme", current.page_id),
        ).fetchall()
        draft_rows = conn.execute(
            """SELECT draft_id, data FROM wiki_drafts
            WHERE tenant = ? ORDER BY draft_id""",
            ("acme",),
        ).fetchall()

    # Then: historical derived data is scrubbed while the current head remains usable.
    assert rows[0] == (1, None)
    assert rows[1][0] == 2
    assert rows[1][1] is not None
    data_by_draft = {str(row[0]): row[1] for row in draft_rows}
    assert data_by_draft[first.id] is None
    assert data_by_draft[second.id] is not None
    assert service.page(wiki_author(), current.page_id, Purpose.OPERATIONS, now) == current


def test_historical_source_change_does_not_stale_clean_current_head(
    tmp_path: Path, now: datetime
) -> None:
    # Given: only historical revision one depends on sop-1.
    service = _two_source_service(tmp_path / "historical-change.db", now)
    first, second, current = _publish_two_revisions(service, now)

    # When: sop-1 changes while the current revision depends only on sop-2.
    with service.store.transaction() as conn:
        invalidate_wiki_sources(conn, "acme", ("sop-1",), ())
        head = conn.execute(
            """SELECT revision, state FROM wiki_page_heads
            WHERE tenant = ? AND page_id = ?""",
            ("acme", current.page_id),
        ).fetchone()
        old_version = conn.execute(
            """SELECT data FROM wiki_page_versions
            WHERE tenant = ? AND page_id = ? AND revision = 1""",
            ("acme", current.page_id),
        ).fetchone()

    # Then: current page and its draft stay usable; only the dependent draft is stale.
    assert head == (2, "published")
    assert old_version is not None
    assert old_version[0] is not None
    assert service.page(wiki_author(), current.page_id, Purpose.OPERATIONS, now) == current
    current_draft = service.view_draft(wiki_author(), second.id, now)
    assert current_draft.state is WikiDraftState.PUBLISHED
    assert current_draft.published_revision == current.revision
    with pytest.raises(AXError, match="wiki_draft_not_found"):
        _ = service.view_draft(wiki_author(), first.id, now)


def test_publish_retry_of_superseded_revision_returns_explicit_conflict(
    tmp_path: Path, now: datetime
) -> None:
    # Given: the same page has advanced from reviewed revision one to revision two.
    service = _two_source_service(tmp_path / "superseded.db", now)
    first, _, current = _publish_two_revisions(service, now)

    # When / Then: retrying revision one's exact review does not read revision two as its result.
    with pytest.raises(AXError, match="wiki_publish_replay_superseded") as raised:
        _ = service.publish(wiki_reviewer(), first.id, first.payload_hash, now)
    assert raised.value.status == 409
    assert service.page(wiki_author(), current.page_id, Purpose.OPERATIONS, now) == current


def test_invalidation_rolls_back_with_parent_batch(tmp_path: Path, now: datetime) -> None:
    # Given: a published page and a transaction that later fails.
    service, _, page = _published_service(tmp_path / "rollback.db", now)
    source_id = page.source_bindings[0].document_id

    # When: invalidation runs but the surrounding knowledge batch rolls back.
    with pytest.raises(BatchAbortError):
        _abort_invalidation(service, source_id)

    # Then: the page remains readable after rollback.
    current = service.page(wiki_author(), page.page_id, Purpose.OPERATIONS, now)
    assert current.page_id == page.page_id


def test_published_page_survives_store_restart(tmp_path: Path, now: datetime) -> None:
    # Given: a committed page and a fully closed transaction boundary.
    path = tmp_path / "restart.db"
    service, _, page = _published_service(path, now)

    # When: a new Store and WikiService instance open the same SQLite file.
    restarted_store = Store(path, service.template)
    restarted = WikiService(
        restarted_store,
        service.template,
        principal_resolver=lambda: (wiki_author(), wiki_reviewer()),
        server_query_floor=service.server_query_floor,
        clock=lambda: now,
    )

    # Then: immutable page state and source checks still validate after restart.
    current = restarted.page(wiki_author(), page.page_id, Purpose.OPERATIONS, now)
    assert current == page
