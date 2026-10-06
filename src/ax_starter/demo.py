from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TypedDict, assert_never

from ax_starter.common import Access, Operation, Principal, Purpose, Sensitivity
from ax_starter.ontology import (
    ActionType,
    Document,
    DomainPack,
    Entity,
    Link,
    LinkType,
    ObjectType,
    PropertySpec,
    PropertyValue,
    Transition,
    ValueKind,
)


class DemoDomain(StrEnum):
    PROCUREMENT = "procurement"
    SUPPORT = "support"
    HR = "hr"


class SharedIdentity(TypedDict):
    tenant: str
    groups: frozenset[str]
    clearance: Sensitivity
    purposes: frozenset[Purpose]


def domain_values(domain: DemoDomain) -> tuple[str, str, str, str, Sensitivity]:
    match domain:
        case DemoDomain.PROCUREMENT:
            return (
                "구매 요청 검토",
                "PurchaseRequest",
                "procurement",
                " ".join(  # noqa: FLY002 - bounded Korean source lines
                    (
                        "구매요청은 품목·수량과 재고를 확인한 뒤 reviewed 상태로 기록합니다.",
                        "발주·지급은 별도의 사람 승인과 ERP 절차를 따릅니다.",
                    )
                ),
                Sensitivity.INTERNAL,
            )
        case DemoDomain.SUPPORT:
            return (
                "고객 지원 요청 검토",
                "SupportTicket",
                "support",
                " ".join(  # noqa: FLY002 - bounded Korean source lines
                    (
                        "고객지원은 유형·재현 정보를 확인하고 reviewed 상태로 기록합니다.",
                        "환불과 외부 답변은 별도 승인 절차를 따릅니다.",
                    )
                ),
                Sensitivity.INTERNAL,
            )
        case DemoDomain.HR:
            return (
                "입사 서류 검토",
                "OnboardingCase",
                "hr",
                " ".join(  # noqa: FLY002 - bounded Korean source lines
                    (
                        "입사서류는 필수 서류와 제출 상태를 확인하고 reviewed 상태로 기록합니다.",
                        "채용·인사평가의 최종 결정은 담당자가 수행합니다.",
                    )
                ),
                Sensitivity.RESTRICTED,
            )
        case unreachable:
            assert_never(unreachable)


def demo_principals(domain: DemoDomain = DemoDomain.PROCUREMENT) -> tuple[Principal, ...]:
    _, _, group, _, sensitivity = domain_values(domain)
    shared: SharedIdentity = {
        "tenant": "acme",
        "groups": frozenset({group}),
        "clearance": sensitivity,
        "purposes": frozenset({Purpose.OPERATIONS}),
    }
    return (
        Principal(
            subject="operator",
            operations=frozenset({Operation.READ, Operation.PROPOSE, Operation.EXECUTE}),
            **shared,
        ),
        Principal(
            subject="reviewer",
            operations=frozenset(
                {Operation.READ, Operation.APPROVE, Operation.EXECUTE, Operation.ROLLBACK}
            ),
            **shared,
        ),
        Principal(
            subject="auditor",
            tenant="acme",
            groups=frozenset({group}),
            clearance=sensitivity,
            operations=frozenset({Operation.READ}),
            purposes=frozenset({Purpose.AUDIT}),
        ),
        Principal(
            subject="outsider",
            tenant="beta",
            groups=frozenset({group}),
            clearance=sensitivity,
            operations=frozenset({Operation.READ}),
            purposes=frozenset({Purpose.OPERATIONS}),
        ),
    )


def demo_pack(
    domain: DemoDomain = DemoDomain.PROCUREMENT, *, as_of: datetime | None = None
) -> DomainPack:
    label, kind, group, text, sensitivity = domain_values(domain)
    valid_until = as_of + timedelta(days=365) if as_of else datetime(2028, 1, 1, tzinfo=UTC)
    access = Access(
        tenant="acme",
        groups=frozenset({group}),
        sensitivity=sensitivity,
        purposes=frozenset({Purpose.OPERATIONS, Purpose.AUDIT}),
    )
    beta = access.model_copy(update={"tenant": "beta"})
    restricted = access.model_copy(
        update={"groups": frozenset({"private-board"}), "sensitivity": Sensitivity.RESTRICTED}
    )
    properties = (
        PropertySpec(key="status", kind=ValueKind.TEXT, sensitivity=sensitivity),
        PropertySpec(key="summary", kind=ValueKind.TEXT, sensitivity=sensitivity),
    )
    state = (
        PropertyValue(key="status", value="submitted"),
        PropertyValue(key="summary", value="합성 업무 사례"),
    )
    return DomainPack(
        id=f"{domain}-demo",
        version="1.0.0",
        description=f"{label}: 실제 개인정보가 없는 합성 도메인팩",
        object_types=(
            ObjectType(
                id=kind, label=label, properties=properties, minimum_sensitivity=sensitivity
            ),
            ObjectType(
                id="Procedure",
                label="업무 절차",
                properties=(
                    PropertySpec(key="summary", kind=ValueKind.TEXT, sensitivity=sensitivity),
                ),
                minimum_sensitivity=sensitivity,
            ),
        ),
        link_types=(LinkType(id="governed_by", source_type=kind, target_type="Procedure"),),
        action_types=(
            ActionType(
                id="mark_reviewed",
                handler="set_status",
                object_type=kind,
                property="status",
                transitions=(Transition(before="submitted", after="reviewed"),),
            ),
        ),
        objects=(
            Entity(
                id="request-1",
                type=kind,
                label=label,
                access=access,
                properties=state,
                source="synthetic:request-1",
            ),
            Entity(
                id="procedure-1",
                type="Procedure",
                label="표준 운영 절차",
                access=access,
                properties=(PropertyValue(key="summary", value="검토 절차"),),
                source="synthetic:procedure-1",
            ),
            Entity(
                id="beta-request",
                type=kind,
                label="다른 테넌트의 합성 요청",
                access=beta,
                properties=state,
                source="synthetic:beta",
            ),
            Entity(
                id="restricted-case",
                type=kind,
                label="접근 제한 합성 기록",
                access=restricted,
                properties=state,
                source="synthetic:restricted",
            ),
        ),
        links=(
            Link(
                id="request-policy",
                type="governed_by",
                source_id="request-1",
                target_id="procedure-1",
                access=access,
            ),
        ),
        documents=(
            Document(
                id="sop-1",
                object_ids=("procedure-1",),
                title="검토 운영 절차",
                text=text,
                source_uri="synthetic://sop/review",
                source_version="1",
                access=access,
                valid_until=valid_until,
            ),
            Document(
                id="beta-doc",
                object_ids=("beta-request",),
                title="검토 절차",
                text="BETA_SENTINEL 합성 타사 기밀",
                source_uri="synthetic://beta",
                source_version="1",
                access=beta,
                valid_until=valid_until,
            ),
            Document(
                id="restricted-doc",
                object_ids=("restricted-case",),
                title="검토 절차",
                text="RESTRICTED_SENTINEL 합성 접근제한 기록",
                source_uri="synthetic://restricted",
                source_version="1",
                access=restricted,
                valid_until=valid_until,
            ),
        ),
    )
