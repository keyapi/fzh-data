"""One-off VITE test-env rate smoke (not for production).

Reads key from env VITE_API_KEY, else from vite-api test-credentials.md.
Never prints the key.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

from sellfox_shipping.carriers.vite import ViteGofoClient


def _load_key() -> str:
    env = (os.getenv("VITE_API_KEY") or "").strip()
    if env:
        return env
    cred = Path("vite-api/docs/test-guide/test-credentials.md")
    if not cred.is_file():
        raise SystemExit("VITE_API_KEY unset and vite-api credentials doc missing")
    for line in cred.read_text(encoding="utf-8").splitlines():
        if "API Key" not in line:
            continue
        # Prefer fenced cell: | API Key | `...` |
        start = line.find("`")
        end = line.rfind("`")
        if start >= 0 and end > start:
            return line[start + 1 : end].strip()
    raise SystemExit("could not parse API Key from credentials doc")


def main() -> int:
    key = _load_key()
    print(f"key_source={'env' if os.getenv('VITE_API_KEY') else 'vite-api-doc'} key_len={len(key)}")

    base = {
        "shipDate": date.today().isoformat(),
        # Same in-coverage pair as vite-api test-report-2026-07-16 §2.1
        "from": {
            "fullName": "FZH Test",
            "address1": "90 Chester rd",
            "city": "Belmont",
            "state": "MA",
            "zipCode": "02478",
            "phoneNumber": "1111111111",
        },
        "to": {
            "fullName": "Wilson",
            "address1": "55 Harvey road",
            "city": "Londonderry",
            "state": "NH",
            "zipCode": "03053",
            "phoneNumber": "1111111111",
        },
        "packages": [{"weight": 2, "length": 10, "width": 8, "height": 6}],
    }
    # Combos validated in vite-api test-report-2026-07-16 (test env).
    combos = [
        ("GOFO_PX", "PARCEL"),
        ("GOFO_PARCEL", "GFUS"),
        ("GOFO_PARCEL", "YT"),
    ]

    with ViteGofoClient(api_key=key, base_url="https://test-api.vitedirect.com") as client:
        acc = client._client.get("/user/account")
        print(f"account_status={acc.status_code} body={acc.text[:300]}")
        if acc.status_code >= 400:
            return 1
        failed = 0
        for service, channel in combos:
            body = {**base, "serviceType": service, "channel": channel}
            try:
                rate = client.rate_gofo(body)
            except Exception as exc:  # noqa: BLE001 — smoke script
                failed += 1
                print(f"FAIL service={service} channel={channel} err={exc}")
                continue
            ad = rate.get("amountDetails") or {}
            print(
                f"OK service={service} channel={channel} "
                f"totalAmount={rate.get('totalAmount')!r} "
                f"postage={ad.get('postageAmount')!r} "
                f"zone={rate.get('zone')!r} "
                f"billingWeight={rate.get('billingWeight')!r} "
                f"desc={rate.get('serviceDescription')!r}"
            )
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
