from __future__ import annotations

from collections.abc import Mapping


def authorize(key: Mapping[str, object], account: str, operation: str) -> None:
    accounts = key.get("accounts", [])
    operations = key.get("operations", [])
    if account not in accounts:
        raise PermissionError(f"Key is not authorized for account '{account}'")
    if operation not in operations:
        raise PermissionError(f"Key is not authorized for operation '{operation}'")
