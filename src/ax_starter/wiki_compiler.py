from typing import Final, Literal, assert_never
from urllib.parse import urlsplit

from ax_starter.common import AXError
from ax_starter.generation import generate
from ax_starter.providers import ProviderConfig, ProviderMode
from ax_starter.retrieval import Answer, content_hash
from ax_starter.wiki_contracts import WikiCompilation, WikiCompileRequest, WikiGenerationRoute

EXTRACTIVE_QUOTE_CHARS: Final = 640


def compile_wiki(
    provider: ProviderConfig, request: WikiCompileRequest, raw_answer: Answer
) -> WikiCompilation:
    """Compile a review candidate; the service binds every input source and checks live ACLs."""
    if not raw_answer.citations:
        raise AXError("wiki_evidence_required", 409)
    classification = max(
        provider.minimum_query_sensitivity,
        request.query.sensitivity,
        raw_answer.sensitivity,
        *(cite.sensitivity for cite in raw_answer.citations),
    )
    if request.query.generate:
        draft = generate(provider, request.query, raw_answer)
        return WikiCompilation(
            body=draft.text,
            citations=draft.citations,
            compiler_mode="model_draft",
            sensitivity=max(classification, draft.sensitivity),
            generation_route=_generation_route(provider),
        )
    citations = tuple(
        cite.model_copy(update={"quote": cite.quote[:EXTRACTIVE_QUOTE_CHARS]})
        for cite in raw_answer.citations
    )
    return WikiCompilation(
        body="\n\n".join(f"[{cite.document_id}] {cite.quote}" for cite in citations),
        citations=citations,
        compiler_mode="offline_extractive",
        sensitivity=classification,
    )


def _generation_route(provider: ProviderConfig) -> WikiGenerationRoute:
    mode: Literal["local", "private_gateway", "cloud_gateway"]
    match provider.mode:
        case ProviderMode.LOCAL:
            mode = "local"
        case ProviderMode.PRIVATE:
            mode = "private_gateway"
        case ProviderMode.CLOUD:
            mode = "cloud_gateway"
        case ProviderMode.OFFLINE:
            raise AXError("generation_disabled", 503)
        case unreachable:
            assert_never(unreachable)
    endpoint_host = urlsplit(provider.endpoint or "").hostname
    if not endpoint_host or not provider.model:
        raise AXError("wiki_provider_route_missing")
    return WikiGenerationRoute(
        mode=mode,
        endpoint_host=endpoint_host,
        model=provider.model,
        provider_settings_sha256=content_hash(provider.model_dump_json()),
    )
