from typing import Final, Never

from ax_starter.common import AXError, Sensitivity
from ax_starter.ontology import DomainPack
from ax_starter.policy import visible
from ax_starter.retrieval import Answer, Query, content_hash, context_sensitivity, scope_ids
from ax_starter.wiki_contracts import MAX_WIKI_SCOPE_OBJECTS, WikiObjectBinding
from ax_starter.wiki_source_policy import SourcePolicyContext

_SCOPE_ACCESS_ERRORS: Final = frozenset(
    {"access_denied", "object_not_found", "graph_fanout_limit", "graph_scope_limit"}
)


def build_scope_object_bindings(
    context: SourcePolicyContext,
    answer: Answer,
    query: Query,
) -> tuple[tuple[WikiObjectBinding, ...], Sensitivity]:
    """Bind every source object plus the exact anchor-and-hop retrieval scope."""
    pack = context.store.current_pack(context.conn, context.template)
    objects = {entity.id: entity for entity in pack.objects}
    retrieval_scope: frozenset[str] = (
        scope_ids(pack, context.actor, query) if query.object_id is not None else frozenset()
    )
    bound_ids: frozenset[str] = frozenset(answer.object_ids) | retrieval_scope
    if len(bound_ids) > MAX_WIKI_SCOPE_OBJECTS:
        raise AXError("wiki_object_scope_limit", 422)
    bindings: list[WikiObjectBinding] = []
    labels = [context_sensitivity(pack, context.actor, query)]
    for object_id in sorted(bound_ids):
        entity = objects.get(object_id)
        if entity is None or not visible(context.actor, entity.access, context.purpose):
            raise AXError("access_denied", 403)
        labels.append(entity.access.sensitivity)
        bindings.append(
            WikiObjectBinding(
                object_id=entity.id,
                object_sha256=content_hash(entity.model_dump_json()),
                access_sha256=content_hash(entity.access.model_dump_json()),
                access_snapshot=entity.access,
            )
        )
    if not bindings:
        raise AXError("wiki_source_required", 422)
    return tuple(bindings), max(labels)


def require_scope_objects_current(
    context: SourcePolicyContext,
    bindings: tuple[WikiObjectBinding, ...],
    query: Query,
    *,
    read_projection: bool,
) -> Sensitivity:
    pack = context.store.current_pack(context.conn, context.template)
    _require_query_scope(context, pack, bindings, query, read_projection=read_projection)
    objects = {entity.id: entity for entity in pack.objects}
    labels = [context_sensitivity(pack, context.actor, query)]
    for binding in bindings:
        entity = objects.get(binding.object_id)
        if entity is None:
            _object_failure(read_projection)
        if not visible(context.actor, binding.access_snapshot, context.purpose):
            _object_failure(read_projection)
        if not visible(context.actor, entity.access, context.purpose):
            _object_failure(read_projection)
        if (
            binding.object_sha256 != content_hash(entity.model_dump_json())
            or binding.access_sha256 != content_hash(entity.access.model_dump_json())
            or binding.access_snapshot != entity.access
        ):
            _object_failure(read_projection)
        labels.append(entity.access.sensitivity)
    return max(labels)


def require_scope_object_access(
    context: SourcePolicyContext,
    bindings: tuple[WikiObjectBinding, ...],
    query: Query,
) -> Sensitivity:
    """Authorize historical and current object ACLs while allowing expected drift."""
    pack = context.store.current_pack(context.conn, context.template)
    _require_query_scope(context, pack, bindings, query, read_projection=True)
    objects = {entity.id: entity for entity in pack.objects}
    labels = [context_sensitivity(pack, context.actor, query)]
    for binding in bindings:
        entity = objects.get(binding.object_id)
        if entity is None:
            _object_failure(read_projection=True)
        if not visible(context.actor, binding.access_snapshot, context.purpose):
            _object_failure(read_projection=True)
        if not visible(context.actor, entity.access, context.purpose):
            _object_failure(read_projection=True)
        labels.append(entity.access.sensitivity)
    return max(labels)


def _require_query_scope(
    context: SourcePolicyContext,
    pack: DomainPack,
    bindings: tuple[WikiObjectBinding, ...],
    query: Query,
    *,
    read_projection: bool,
) -> None:
    try:
        current_scope = scope_ids(pack, context.actor, query)
    except AXError as exc:
        if exc.code in _SCOPE_ACCESS_ERRORS:
            _object_failure(read_projection)
        raise
    if not {binding.object_id for binding in bindings} <= current_scope:
        _object_failure(read_projection)


def _object_failure(read_projection: bool) -> Never:
    if read_projection:
        raise AXError("wiki_page_not_found", 404)
    raise AXError("wiki_source_stale", 409)
