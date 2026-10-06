from datetime import datetime

import pytest

from ax_starter.common import AXError, Principal, Purpose
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query, retrieve


def test_graph_evidence_when_query_is_scoped_to_request(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토 절차", object_id="request-1")
    # When
    answer = retrieve(pack, principals[0], query, now)
    # Then
    assert tuple(item.document_id for item in answer.citations) == ("sop-1",)
    assert answer.citations[0].source_version == "1"


def test_no_evidence_when_graph_hops_are_zero(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토 절차", object_id="request-1", hops=0)
    # When
    answer = retrieve(pack, principals[0], query, now)
    # Then
    assert answer.mode == "abstain"


@pytest.mark.parametrize("object_id", ["beta-request", "restricted-case", "missing"])
def test_invisible_objects_when_attacker_supplies_id(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime, object_id: str
) -> None:
    # Given
    query = Query(question="검토", object_id=object_id)
    # When / Then
    with pytest.raises(AXError, match="object_not_found"):
        _ = retrieve(pack, principals[0], query, now)


def test_no_foreign_evidence_when_query_is_unscoped(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토 SENTINEL")
    # When
    answer = retrieve(pack, principals[0], query, now)
    # Then
    assert "SENTINEL" not in answer.model_dump_json()


def test_purpose_denied_when_actor_changes_purpose(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    query = Query(question="검토", purpose=Purpose.AUDIT)
    # When
    with pytest.raises(AXError, match="access_denied"):
        _ = retrieve(pack, principals[0], query, now)


def test_expired_evidence_when_date_has_passed(
    pack: DomainPack, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    expired = pack.model_copy(
        update={
            "documents": tuple(
                doc.model_copy(update={"valid_until": now}) for doc in pack.documents
            )
        }
    )
    # When
    answer = retrieve(expired, principals[0], Query(question="검토"), now)
    # Then
    assert answer.mode == "abstain"
