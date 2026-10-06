from ax_starter.common import Access, AXError, Operation, Principal, Purpose


def visible(principal: Principal, access: Access, purpose: Purpose) -> bool:
    return (
        principal.tenant == access.tenant
        and bool(principal.groups & access.groups)
        and principal.clearance >= access.sensitivity
        and purpose in principal.purposes
        and purpose in access.purposes
        and Operation.READ in principal.operations
    )


def require(principal: Principal, access: Access, purpose: Purpose, operation: Operation) -> None:
    if operation not in principal.operations or not visible(principal, access, purpose):
        raise AXError("access_denied", 403)
