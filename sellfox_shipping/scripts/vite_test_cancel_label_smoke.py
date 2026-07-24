"""Cancel an existing VITE test-env label (no new create). Never prints the key."""

from __future__ import annotations

import argparse
import os
import sys

from sellfox_shipping.carriers.vite import ViteClientError, ViteGofoClient
from sellfox_shipping.env_loader import load_dotenv


def _load_key() -> str:
    load_dotenv()
    key = (os.getenv("VITE_API_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "VITE_API_KEY unset; copy sellfox_shipping/.env.example keys into repo-root .env"
        )
    return key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True, help="orderId or requestId for DELETE")
    args = parser.parse_args()
    key = _load_key()
    ref = args.ref.strip()
    print(f"key_len={len(key)} ref={ref!r}")

    with ViteGofoClient(api_key=key, base_url="https://test-api.vitedirect.com") as client:
        before = client._client.get("/user/account")
        print(f"balance_before={before.text[:200]}")
        try:
            out = client.cancel_label(ref)
        except ViteClientError as exc:
            print(f"cancel_FAIL err={exc}")
            return 1
        print(f"cancel_OK body={out}")
        try:
            labels = client.get_label(ref)
            lab = labels[0] if labels else {}
            print(
                f"getLabel_after status={lab.get('status')!r} "
                f"url_present={bool(lab.get('url'))} tracking={lab.get('trackingNumber')!r}"
            )
        except ViteClientError as exc:
            print(f"getLabel_after err={exc}")
        after = client._client.get("/user/account")
        print(f"balance_after={after.text[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
