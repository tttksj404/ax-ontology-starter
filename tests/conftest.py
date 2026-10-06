from datetime import UTC, datetime
from pathlib import Path

import pytest

from ax_starter.actions import ActionEngine
from ax_starter.common import Principal
from ax_starter.demo import demo_pack, demo_principals
from ax_starter.ontology import DomainPack
from ax_starter.store import Store


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def pack() -> DomainPack:
    return demo_pack()


@pytest.fixture
def principals() -> tuple[Principal, ...]:
    return demo_principals()


@pytest.fixture
def engine(tmp_path: Path, pack: DomainPack, principals: tuple[Principal, ...]) -> ActionEngine:
    return ActionEngine(Store(tmp_path / "state.db", pack), pack, principals)
