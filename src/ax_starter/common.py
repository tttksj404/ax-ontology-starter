from enum import IntEnum, StrEnum
from typing import Annotated, ClassVar, NewType

from pydantic import BaseModel, ConfigDict, StringConstraints, field_serializer, model_validator
from pydantic_core import PydanticCustomError

ObjectId = NewType("ObjectId", str)
SubjectId = NewType("SubjectId", str)
TenantId = NewType("TenantId", str)
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=96, pattern=r"^[\w.-]+$")]


class Contract(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class Sensitivity(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


class Operation(StrEnum):
    READ = "read"
    MANAGE_KNOWLEDGE = "manage_knowledge"
    PROPOSE = "propose"
    APPROVE = "approve"
    EXECUTE = "execute"
    ROLLBACK = "rollback"


class Purpose(StrEnum):
    OPERATIONS = "operations"
    AUDIT = "audit"


class ActorKind(StrEnum):
    HUMAN = "human"
    SERVICE = "service"


class Principal(Contract):
    subject: Identifier
    tenant: Identifier
    actor_kind: ActorKind = ActorKind.HUMAN
    person_id: Identifier | None = None
    groups: frozenset[Identifier]
    clearance: Sensitivity
    operations: frozenset[Operation]
    purposes: frozenset[Purpose]

    @model_validator(mode="after")
    def service_has_no_person_id(self) -> "Principal":
        if self.actor_kind is ActorKind.SERVICE and self.person_id is not None:
            raise PydanticCustomError(
                "service_principal_person", "service principal cannot have person_id"
            )
        return self

    @property
    def effective_person_id(self) -> str | None:
        if self.actor_kind is ActorKind.HUMAN:
            return self.person_id or self.subject
        return None

    @field_serializer("groups", "operations", "purposes")
    def stable_sets(self, members: frozenset[str | Operation | Purpose]) -> tuple[str, ...]:
        return tuple(sorted(str(member) for member in members))


class Access(Contract):
    tenant: Identifier
    groups: frozenset[Identifier] = frozenset()
    sensitivity: Sensitivity = Sensitivity.RESTRICTED
    purposes: frozenset[Purpose] = frozenset()

    @field_serializer("groups", "purposes")
    def stable_sets(self, members: frozenset[str | Purpose]) -> tuple[str, ...]:
        return tuple(sorted(str(member) for member in members))


class AXError(Exception):
    def __init__(self, code: str, status: int = 409) -> None:
        self.code: str = code
        self.status: int = status
        super().__init__(code)
