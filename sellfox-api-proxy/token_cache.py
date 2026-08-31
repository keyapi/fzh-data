import asyncio
import time
import httpx

from config import app_config


class TokenCache:
    """OAuth2 client_credentials token cache per account, with single-flight refresh."""

    def __init__(self):
        self._tokens: dict[str, tuple[str, float]] = {}

    async def get(self, account_id: str) -> str:
        now = time.monotonic()
        cached = self._tokens.get(account_id)
        if cached:
            token, expires_at = cached
            if now < expires_at - 300:
                return token

        async with asyncio.Lock():
            cached = self._tokens.get(account_id)
            if cached:
                token, expires_at = cached
                if now < expires_at - 300:
                    return token

            acc = app_config.accounts.get(account_id)
            if not acc or not acc.oauth:
                raise ValueError(f"Account {account_id} has no oauth config")

            app_id = app_config.resolve_env(acc.credentials.app_id)
            app_secret = app_config.resolve_env(acc.credentials.app_secret)
            token_url = f"{acc.upstream}{acc.oauth.token_url}"

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    token_url,
                    params={
                        "client_id": app_id,
                        "client_secret": app_secret,
                        "grant_type": "client_credentials",
                    },
                    timeout=15,
                )
                data = resp.json()
                if data.get("code") != 0:
                    raise RuntimeError(f"Token refresh failed for {account_id}: {data}")

            token = data["data"]["access_token"]
            expires_ms = data["data"]["expires_in"]
            expires_at = time.monotonic() + (expires_ms / 1000)
            self._tokens[account_id] = (token, expires_at)
            return token


token_cache = TokenCache()
