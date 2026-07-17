"""One-off VITE test-env createShipment + getLabel smoke (not production).

Uses virtual test balance. Key from VITE_API_KEY or vite-api test-credentials.md.
Never prints the key.

Usage:
  uv run python sellfox_shipping/scripts/vite_test_shipment_label_smoke.py
  uv run python sellfox_shipping/scripts/vite_test_shipment_label_smoke.py --order-id PPGF-...
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

from sellfox_shipping.carriers.vite import ViteClientError, ViteGofoClient


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
        start = line.find("`")
        end = line.rfind("`")
        if start >= 0 and end > start:
            return line[start + 1 : end].strip()
    raise SystemExit("could not parse API Key from credentials doc")


def _request_id() -> str:
    # Colleague pattern: timestamp + digits; must be >=15 chars and globally unique.
    return f"{int(time.time() * 1000)}{random.randint(100, 999)}"


def _poll_label(
    client: ViteGofoClient,
    order_id: str,
    *,
    timeout_s: float = 180.0,
    interval_s: float = 5.0,
) -> dict | None:
    deadline = time.monotonic() + timeout_s
    label0: dict | None = None
    last_status = None
    while time.monotonic() < deadline:
        try:
            labels = client.get_label(order_id)
        except ViteClientError as exc:
            print(f"getLabel_wait err={exc}")
            time.sleep(interval_s)
            continue
        label0 = labels[0] if labels else None
        last_status = (label0 or {}).get("status")
        url = (label0 or {}).get("url")
        track = (label0 or {}).get("trackingNumber")
        print(
            f"getLabel_poll n={len(labels)} status={last_status!r} "
            f"tracking={track!r} url_present={bool(url)}"
        )
        if last_status in ("OK", "canceled", "failed"):
            return label0
        time.sleep(interval_s)
    print(f"getLabel_TIMEOUT final_status={last_status!r}")
    return label0


def main() -> int:
    parser = argparse.ArgumentParser(description="VITE test createShipment+getLabel smoke")
    parser.add_argument(
        "--order-id",
        default="",
        help="Skip create; only poll getLabel for this orderId",
    )
    parser.add_argument("--timeout", type=float, default=180.0, help="getLabel poll seconds")
    args = parser.parse_args()

    key = _load_key()
    print(f"key_source={'env' if os.getenv('VITE_API_KEY') else 'vite-api-doc'} key_len={len(key)}")

    with ViteGofoClient(api_key=key, base_url="https://test-api.vitedirect.com") as client:
        before = client._client.get("/user/account")
        print(f"balance_before status={before.status_code} body={before.text[:200]}")
        if before.status_code >= 400:
            return 1

        order_id = (args.order_id or "").strip()
        if not order_id:
            rid = _request_id()
            body = {
                "requestId": rid,
                "shipDate": date.today().isoformat(),
                "serviceType": "GOFO_PX",
                "channel": "PARCEL",
                "memo": "sellfox_shipping_smoke",
                "reference": f"SMOKE-{rid[-6:]}",
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
            try:
                created = client.create_shipment_gofo(body)
            except ViteClientError as exc:
                print(f"create_FAIL err={exc}")
                return 1
            order_id = str(created.get("orderId") or "")
            print(
                f"create_OK requestId={created.get('requestId')!r} "
                f"orderId={order_id!r} status={created.get('status')!r} "
                f"totalAmount={created.get('totalAmount')!r} "
                f"currentBalance={created.get('currentBalance')!r}"
            )
            if not order_id:
                print("create_FAIL missing orderId")
                return 1
        else:
            print(f"poll_only orderId={order_id!r}")

        label0 = _poll_label(client, order_id, timeout_s=args.timeout)
        after = client._client.get("/user/account")
        print(f"balance_after status={after.status_code} body={after.text[:200]}")

        status = (label0 or {}).get("status")
        if status != "OK":
            print(f"getLabel_FAIL final_status={status!r}")
            return 1
        print(
            f"getLabel_OK orderId={(label0 or {}).get('orderId')!r} "
            f"tracking={(label0 or {}).get('trackingNumber')!r} "
            f"url={(label0 or {}).get('url')!r}"
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
