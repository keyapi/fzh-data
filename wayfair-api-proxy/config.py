from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, HttpUrl


class Capabilities(BaseModel):
    inventory_snapshot: bool = False
    inventory_live: bool = False
    inventory_transactions: bool = False
    inbound_live: bool = False


class Credentials(BaseModel):
    client_id: str
    client_secret: str


class AccountConfig(BaseModel):
    upstream: HttpUrl
    credentials: Credentials
    supplier_id: int | None = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
    account_rate_limit_rps: float = 1.0
    live_rate_limit_rps: float = 0.2


class OIDCConfig(BaseModel):
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    admin_identities: list[str] = Field(default_factory=list)
    cookie_secure: bool = True


class AppConfig(BaseModel):
    accounts: dict[str, AccountConfig]
    snapshot_stale_after_seconds: int = 3600
    snapshot_retention_days: int = 7
    oidc: OIDCConfig | None = None

    def resolve_secret(self, value: str) -> str:
        if value.startswith("${") and value.endswith("}"):
            name = value[2:-1]
            resolved = os.getenv(name)
            if not resolved:
                raise ValueError(f"Environment variable {name} is not set")
            return resolved
        return value


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(data)
