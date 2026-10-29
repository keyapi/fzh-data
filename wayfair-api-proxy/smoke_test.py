from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx

INVENTORY_PATH = "/v1/accounts/{account}/inventory/query"


def _fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


async def run(base_url: str, key: str, account: str, sku: str) -> int:
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        health = await client.get("/health")
        print(f"health: {health.status_code}")
        if health.status_code != 200:
            return _fail("health check failed")

        ready = await client.get("/ready")
        print(f"ready: {ready.status_code}")
        if ready.status_code not in (200, 503):
            return _fail("readiness probe returned unexpected status")

        anonymous = await client.post(
            INVENTORY_PATH.format(account=account),
            json={"skus": [sku], "mode": "snapshot"},
        )
        print(f"anonymous inventory: {anonymous.status_code}")
        if anonymous.status_code != 401:
            return _fail("inventory endpoint did not reject unauthenticated call")

        accounts = await client.get("/v1/accounts", headers=headers)
        print(f"accounts: {accounts.status_code}")
        if accounts.status_code != 200:
            return _fail("account list failed; key may be invalid")

        allowed = {item["id"] for item in accounts.json().get("accounts", [])}
        if account not in allowed:
            return _fail(f"key is not authorized for {account}")

        snapshot = await client.post(
            INVENTORY_PATH.format(account=account),
            json={"skus": [sku], "mode": "snapshot"},
            headers=headers,
        )
        print(f"snapshot query: {snapshot.status_code}")
        if snapshot.status_code == 200:
            body = snapshot.json()
            print(
                "snapshot meta: "
                f"source={body['meta']['source']} "
                f"age_seconds={body['meta']['age_seconds']} "
                f"stale={body['meta']['stale']} "
                f"items={len(body['items'])}"
            )
        elif snapshot.status_code in (404, 501):
            print(f"snapshot unavailable: {snapshot.json()['detail']['code']}")
        else:
            return _fail("snapshot query returned unexpected status")

    print("OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the Wayfair API proxy")
    parser.add_argument(
        "--url",
        default=os.getenv("WAYFAIR_SMOKE_URL", "http://127.0.0.1:8410"),
    )
    parser.add_argument("--account", default=os.getenv("WAYFAIR_SMOKE_ACCOUNT", "centrade"))
    parser.add_argument("--sku", default=os.getenv("WAYFAIR_SMOKE_SKU", ""))
    args = parser.parse_args()

    key = os.getenv("WAYFAIR_SMOKE_KEY", "")
    if not key:
        return _fail("WAYFAIR_SMOKE_KEY is not set")
    if not args.sku:
        return _fail("set --sku or WAYFAIR_SMOKE_SKU")

    return asyncio.run(run(args.url, key, args.account, args.sku))


if __name__ == "__main__":
    sys.exit(main())
