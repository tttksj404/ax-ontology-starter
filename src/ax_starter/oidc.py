from datetime import datetime

from ax_starter.common import AXError, Principal
from ax_starter.oidc_contracts import OIDCRegistry, OIDCSubjectKind
from ax_starter.oidc_tokens import verify_access_token


def authenticate_oidc(registry: OIDCRegistry, token: str, now: datetime) -> Principal:
    verified = verify_access_token(token, registry, now)
    binding = next(
        (
            item
            for item in registry.bindings
            if item.enabled and item.issuer == verified.issuer and item.subject == verified.subject
        ),
        None,
    )
    if binding is None:
        raise AXError("authentication_required", 401)
    if verified.client_id not in binding.allowed_client_ids:
        raise AXError("authentication_required", 401)
    if binding.subject_kind is OIDCSubjectKind.USER:
        if verified.subject == verified.client_id:
            raise AXError("authentication_required", 401)
    elif verified.subject != verified.client_id:
        raise AXError("authentication_required", 401)
    return binding.principal
