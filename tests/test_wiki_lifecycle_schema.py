# pyright: reportAny=false
# SQLite schema rows are asserted directly in this migration test.
import sqlite3

from ax_starter.wiki_schema import invalidate_wiki_sources, migrate_wiki


def test_invalidation_is_a_safe_noop_before_wiki_migration() -> None:
    # Given: an existing runtime database with no wiki tables.
    conn = sqlite3.connect(":memory:")

    # When: a knowledge hook runs before the optional wiki feature is installed.
    invalidate_wiki_sources(conn, "acme", ("sop-1",), ())

    # Then: no schema is created as a side effect.
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert tables == []


def test_wiki_migration_is_restart_safe() -> None:
    # Given: a live SQLite connection.
    conn = sqlite3.connect(":memory:")

    # When: migration runs twice as it will on process restart.
    migrate_wiki(conn)
    migrate_wiki(conn)

    # Then: the independently versioned wiki schema remains available once.
    version = conn.execute("SELECT value FROM wiki_meta WHERE id = 'schema_version'").fetchone()
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'wiki_%'"
        )
    }
    assert version == ("1",)
    assert {"wiki_drafts", "wiki_page_heads", "wiki_page_versions"} <= tables
