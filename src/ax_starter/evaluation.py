from datetime import datetime
from http import HTTPStatus

from pydantic import Field

from ax_starter.auth import IdentityRegistry
from ax_starter.common import AXError, Contract, Identifier
from ax_starter.ontology import DomainPack
from ax_starter.retrieval import Query, retrieve


class EvaluationCase(Contract):
    id: Identifier
    tenant: Identifier
    subject: Identifier
    query: Query
    expected_documents: tuple[Identifier, ...]
    expected_denial: bool = False


class EvaluationSet(Contract):
    synthetic: bool
    cases: tuple[EvaluationCase, ...] = Field(min_length=1, max_length=500)
    minimum_recall: float = Field(default=0.9, ge=0, le=1)


class CaseResult(Contract):
    id: str
    passed: bool
    recall: float
    citation_exact: bool
    denied: bool
    unexpected_documents: int
    failure_code: Identifier | None = None


class EvaluationReport(Contract):
    synthetic: bool
    case_count: int
    recall_at_k: float
    exact_citation_rate: float
    unexpected_documents: int
    passed: bool
    cases: tuple[CaseResult, ...]


def evaluate(
    pack: DomainPack, identities: IdentityRegistry, dataset: EvaluationSet, now: datetime
) -> EvaluationReport:
    results: list[CaseResult] = []
    for case in dataset.cases:
        principal = next(
            (
                binding.principal
                for binding in identities.bindings
                if binding.principal.subject == case.subject
                and binding.principal.tenant == case.tenant
            ),
            None,
        )
        if principal is None:
            raise AXError("evaluation_subject_missing")
        denied = False
        failure_code: str | None = None
        exact = True
        found: set[str] = set()
        try:
            answer = retrieve(pack, principal, case.query, now)
            found = {citation.document_id for citation in answer.citations}
            source = {doc.id: doc for doc in pack.documents}
            exact = all(cite.quote in source[cite.document_id].text for cite in answer.citations)
        except AXError as exc:
            if exc.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE:
                failure_code = exc.code
                exact = False
            elif exc.status in (403, 404):
                denied = True
            else:
                raise
        expected = set(case.expected_documents)
        recall = len(found & expected) / len(expected) if expected else 1.0
        unexpected = len(found - expected)
        results.append(
            CaseResult(
                id=case.id,
                passed=(
                    failure_code is None
                    and recall == 1
                    and unexpected == 0
                    and exact
                    and denied == case.expected_denial
                ),
                recall=recall,
                citation_exact=exact,
                denied=denied,
                unexpected_documents=unexpected,
                failure_code=failure_code,
            )
        )
    recall = sum(result.recall for result in results) / len(results)
    exact_rate = sum(result.citation_exact for result in results) / len(results)
    return EvaluationReport(
        synthetic=dataset.synthetic,
        case_count=len(results),
        recall_at_k=round(recall, 4),
        exact_citation_rate=round(exact_rate, 4),
        unexpected_documents=sum(result.unexpected_documents for result in results),
        passed=all(result.passed for result in results) and recall >= dataset.minimum_recall,
        cases=tuple(results),
    )
