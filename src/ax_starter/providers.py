import ipaddress
import json
import re
import socket
from enum import StrEnum
from typing import Final, assert_never
from urllib.parse import urlsplit

import httpx2
from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import AXError, Contract, Sensitivity
from ax_starter.retrieval import Answer, Query


class ProviderMode(StrEnum):
    OFFLINE = "offline"
    LOCAL = "local"
    PRIVATE = "private_gateway"
    CLOUD = "cloud_gateway"


class ProviderConfig(Contract):
    mode: ProviderMode = ProviderMode.OFFLINE
    endpoint: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=120)
    approved_hosts: tuple[str, ...] = Field(default=(), max_length=10)
    egress_approved: bool = False
    minimum_query_sensitivity: Sensitivity = Sensitivity.RESTRICTED
    max_prompt_bytes: int = Field(default=64_000, ge=1000, le=128_000)

    @model_validator(mode="after")
    def endpoint_boundary(self) -> "ProviderConfig":
        if self.mode == ProviderMode.OFFLINE:
            return self
        if not self.endpoint or not self.model:
            raise PydanticCustomError("provider_incomplete", "endpoint와 model을 명시해야 합니다")
        url = urlsplit(self.endpoint)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise PydanticCustomError("unsafe_endpoint", "허용되지 않은 endpoint 형식")
        match self.mode:
            case ProviderMode.LOCAL:
                try:
                    address = ipaddress.ip_address(url.hostname)
                except ValueError as exc:
                    raise PydanticCustomError(
                        "local_requires_ip", "local은 loopback IP만 허용합니다"
                    ) from exc
                if not address.is_loopback or url.scheme not in ("http", "https"):
                    raise PydanticCustomError(
                        "local_requires_loopback", "local은 loopback에만 연결합니다"
                    )
            case ProviderMode.PRIVATE | ProviderMode.CLOUD:
                if url.scheme != "https" or url.hostname not in self.approved_hosts:
                    raise PydanticCustomError(
                        "gateway_not_allowlisted", "HTTPS 및 정확한 호스트 허용 목록이 필요합니다"
                    )
            case ProviderMode.OFFLINE:
                pass
            case unreachable:
                assert_never(unreachable)
        return self


SENSITIVE_PATTERNS: Final = (
    re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{12,}(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,}(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,}(?![A-Za-z0-9_])"),
    re.compile(r"(?<!\d)\d{6}-?[1-8]\d{6}(?!\d)"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?i)(?:password|api[_ -]?key|비밀번호|비밀키)\s*[:=]\s*\S+"),
)


def model_context(query: Query, answer: Answer) -> str:
    return json.dumps(
        {
            "question": query.question,
            "evidence": [
                {"document_id": cite.document_id, "quote": cite.quote} for cite in answer.citations
            ],
        },
        ensure_ascii=False,
    )


def enforce_route(config: ProviderConfig, query: Query, answer: Answer) -> None:
    match config.mode:
        case ProviderMode.OFFLINE:
            raise AXError("generation_disabled", 503)
        case ProviderMode.LOCAL:
            ceiling = Sensitivity.RESTRICTED
        case ProviderMode.PRIVATE:
            ceiling = Sensitivity.CONFIDENTIAL
        case ProviderMode.CLOUD:
            ceiling = Sensitivity.INTERNAL
        case unreachable:
            assert_never(unreachable)
    classification = max(
        config.minimum_query_sensitivity,
        query.sensitivity,
        answer.sensitivity,
        *(item.sensitivity for item in answer.citations),
    )
    if classification > ceiling:
        raise AXError("provider_classification_denied", 403)
    if config.mode in (ProviderMode.PRIVATE, ProviderMode.CLOUD):
        if not config.egress_approved:
            raise AXError("provider_egress_not_approved", 403)
        fields = (
            query.question,
            *(value for cite in answer.citations for value in (cite.document_id, cite.quote)),
        )
        if any(pattern.search(value) for pattern in SENSITIVE_PATTERNS for value in fields):
            raise AXError("sensitive_content_egress_denied", 403)


def provider_client() -> httpx2.Client:
    limits = httpx2.Limits(max_connections=200, max_keepalive_connections=40, keepalive_expiry=30)
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=limits,
        trust_env=False,
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    return httpx2.Client(
        transport=transport,
        timeout=httpx2.Timeout(connect=5, read=30, write=10, pool=10),
        trust_env=False,
        follow_redirects=False,
    )
