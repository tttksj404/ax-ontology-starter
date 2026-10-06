from datetime import datetime
from typing import Literal
from unicodedata import normalize

import pytest

from ax_starter.common import Principal
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query, content_hash, retrieve


@pytest.mark.parametrize(("query_form", "document_form"), [("NFC", "NFD"), ("NFD", "NFC")])
def test_unicode_search_equivalence_preserves_original_evidence(
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
    query_form: Literal["NFC", "NFD"],
    document_form: Literal["NFC", "NFD"],
) -> None:
    # Given
    documents = tuple(
        doc.model_copy(
            update={
                "title": normalize(document_form, doc.title),
                "text": normalize(document_form, doc.text),
            }
        )
        for doc in pack.documents
    )
    source = pack.model_copy(update={"documents": documents})
    original = next(doc for doc in documents if doc.id == "sop-1")
    # When
    answer = retrieve(
        source,
        principals[0],
        Query(question=normalize(query_form, "검토 절차"), object_id="request-1"),
        now,
    )
    # Then
    assert answer.mode == "extractive"
    assert tuple(cite.document_id for cite in answer.citations) == ("sop-1",)
    assert answer.citations[0].quote == original.text
    assert answer.citations[0].content_sha256 == content_hash(original.text)
