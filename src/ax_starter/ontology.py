from enum import StrEnum
from typing import Annotated, Literal, LiteralString, assert_never

from pydantic import AwareDatetime, Field, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import Access, Contract, Identifier, Sensitivity


class ValueKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"


class PropertySpec(Contract):
    key: Identifier
    kind: ValueKind
    required: bool = True
    sensitivity: Sensitivity = Sensitivity.RESTRICTED


class ObjectType(Contract):
    id: Identifier
    label: str = Field(min_length=1, max_length=200)
    properties: tuple[PropertySpec, ...] = Field(min_length=1, max_length=40)
    minimum_sensitivity: Sensitivity = Sensitivity.RESTRICTED


class PropertyValue(Contract):
    key: Identifier
    value: (
        Annotated[str, Field(strict=True)]
        | Annotated[int, Field(strict=True)]
        | Annotated[float, Field(strict=True, allow_inf_nan=False)]
        | Annotated[bool, Field(strict=True)]
    )


class Entity(Contract):
    id: Identifier
    type: Identifier
    label: str = Field(min_length=1, max_length=200)
    access: Access
    properties: tuple[PropertyValue, ...] = Field(max_length=40)
    version: int = Field(default=1, ge=1)
    source: str = Field(min_length=1, max_length=300)

    def property(self, key: str) -> str | int | float | bool | None:
        return next((item.value for item in self.properties if item.key == key), None)


class LinkType(Contract):
    id: Identifier
    source_type: Identifier
    target_type: Identifier


class Link(Contract):
    id: Identifier
    type: Identifier
    source_id: Identifier
    target_id: Identifier
    access: Access


class Document(Contract):
    id: Identifier
    object_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=16_000)
    source_uri: str = Field(min_length=1, max_length=300)
    source_version: Identifier
    access: Access
    valid_until: AwareDatetime


class Transition(Contract):
    before: Identifier
    after: Identifier


class ActionType(Contract):
    id: Identifier
    handler: Literal["set_status"]
    object_type: Identifier
    property: Literal["status"]
    transitions: tuple[Transition, ...] = Field(min_length=1, max_length=20)
    requires_approval: Literal[True] = True
    reversible: Literal[True] = True


def _fail(code: LiteralString) -> None:
    raise PydanticCustomError(code, code)


def _check_entity(entity: Entity, definition: ObjectType) -> None:
    if entity.access.sensitivity < max(
        definition.minimum_sensitivity, *(spec.sensitivity for spec in definition.properties)
    ):
        _fail("object_underclassified")
    specs = {spec.key: spec for spec in definition.properties}
    values = {prop.key: prop.value for prop in entity.properties}
    if len(specs) != len(definition.properties) or len(values) != len(entity.properties):
        _fail("duplicate_property")
    if not values.keys() <= specs.keys():
        _fail("unknown_property")
    if any(spec.required and spec.key not in values for spec in definition.properties):
        _fail("missing_property")
    for key, value in values.items():
        match specs[key].kind:
            case ValueKind.TEXT:
                valid = type(value) is str
            case ValueKind.NUMBER:
                valid = type(value) in (int, float)
            case ValueKind.BOOLEAN:
                valid = type(value) is bool
            case unreachable:
                assert_never(unreachable)
        if not valid:
            _fail("property_type_mismatch")


def _check_link(link: Link, entities: dict[str, Entity], definitions: dict[str, LinkType]) -> None:
    if (
        link.type not in definitions
        or link.source_id not in entities
        or link.target_id not in entities
    ):
        _fail("unknown_link_endpoint")
    source, target, definition = (
        entities[link.source_id],
        entities[link.target_id],
        definitions[link.type],
    )
    if (source.type, target.type) != (definition.source_type, definition.target_type):
        _fail("link_type_mismatch")
    if len({source.access.tenant, target.access.tenant, link.access.tenant}) != 1:
        _fail("cross_tenant_link")


def _check_document(doc: Document, entities: dict[str, Entity]) -> None:
    if any(
        key not in entities or entities[key].access.tenant != doc.access.tenant
        for key in doc.object_ids
    ):
        _fail("invalid_document_scope")
    if any(doc.access.sensitivity < entities[key].access.sensitivity for key in doc.object_ids):
        _fail("document_underclassified")


def _check_action(action: ActionType, definitions: dict[str, ObjectType]) -> None:
    if action.object_type not in definitions:
        _fail("unknown_action_object_type")
    if not any(
        spec.key == action.property and spec.kind == ValueKind.TEXT
        for spec in definitions[action.object_type].properties
    ):
        _fail("invalid_action_property")


class DomainPack(Contract):
    id: Identifier
    version: Identifier
    description: str = Field(min_length=1, max_length=500)
    object_types: tuple[ObjectType, ...] = Field(min_length=1, max_length=50)
    link_types: tuple[LinkType, ...] = Field(max_length=50)
    action_types: tuple[ActionType, ...] = Field(max_length=30)
    objects: tuple[Entity, ...] = Field(min_length=1, max_length=5000)
    links: tuple[Link, ...] = Field(max_length=20_000)
    documents: tuple[Document, ...] = Field(max_length=5000)

    @model_validator(mode="after")
    def check_graph(self) -> "DomainPack":
        for collection in (
            self.object_types,
            self.link_types,
            self.action_types,
            self.objects,
            self.links,
            self.documents,
        ):
            if len({item.id for item in collection}) != len(collection):
                _fail("duplicate_id")
        types = {item.id: item for item in self.object_types}
        entities = {item.id: item for item in self.objects}
        link_types = {item.id: item for item in self.link_types}
        for entity in self.objects:
            if entity.type not in types:
                _fail("unknown_object_type")
            _check_entity(entity, types[entity.type])
        for definition in self.link_types:
            if definition.source_type not in types or definition.target_type not in types:
                _fail("unknown_link_endpoint_type")
        for link in self.links:
            _check_link(link, entities, link_types)
        for doc in self.documents:
            _check_document(doc, entities)
        for action in self.action_types:
            _check_action(action, types)
        return self
