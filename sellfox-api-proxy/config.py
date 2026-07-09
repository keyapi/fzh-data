import os
import yaml
from pydantic import BaseModel
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class CredentialsConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    app_key: str = ""
    # for static_key auth
    api_key: str = ""


class OAuthConfig(BaseModel):
    token_url: str = "/api/oauth/v2/token.json"


class RateLimitConfig(BaseModel):
    global_rps: float = 1.0
    default_key_rps: float = 0.3


class AccountConfig(BaseModel):
    name: str
    upstream: str
    auth_type: str = "static_key"
    signing_type: str = "none"
    credentials: CredentialsConfig = CredentialsConfig()
    oauth: OAuthConfig | None = None
    rate_limit: RateLimitConfig = RateLimitConfig()


class OIDCConfig(BaseModel):
    issuer: str = "https://api.vilavi.cn/oidc"
    client_id: str = "sellfox-api-proxy"
    client_secret: str = ""
    redirect_uri: str = "https://api.vilavi.cn/sellfox/admin/oidc-callback"


class AppConfig(BaseModel):
    default_account: str = ""
    account_overrides: dict[str, str] = {}
    accounts: dict[str, AccountConfig]
    oidc: OIDCConfig = OIDCConfig()

    def resolve_env(self, value: str) -> str:
        if value.startswith("${") and value.endswith("}"):
            return os.getenv(value[2:-1], "")
        return value

    @classmethod
    def load(cls) -> "AppConfig":
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f)
        return cls.model_validate(raw)


class Settings(BaseModel):
    sellfox_app_id: str = os.getenv("SELLFOX_APP_ID", "")
    sellfox_app_secret: str = os.getenv("SELLFOX_APP_SECRET", "")
    admin_key: str = os.getenv("ADMIN_API_KEY", "")
    db_path: str = os.getenv("DB_PATH", "/data/sellfox-proxy.db")
    bind_port: int = int(os.getenv("BIND_PORT", "8400"))


settings = Settings()
app_config = AppConfig.load()
