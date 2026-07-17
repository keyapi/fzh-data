"""VITE test-env: create one label, poll to OK, then cancel (virtual balance)."""

from __future__ import annotations

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


def main() -> int:
    key = _load_key()
    rid = f"{int(time.time() * 1000)}{random.randint(100, 999)}"
    body = {
        "requestId": rid,
        "shipDate": date.today().isoformat(),
        "serviceType": "GOFO_PX",
        "channel": "PARCEL",
        "memo": "cancel_smoke",
        "reference": f"CXL-{rid[-6:]}",
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

    with ViteGofoClient(api_key=key, base_url="https://test-api.vitedirect.com") as client:
        before = client._client.get("/user/account")
        print(f"balance_before={before.text}")
        created = client.create_shipment_gofo(body)
        order_id = str(created.get("orderId") or "")
        print(
            f"create_OK requestId={rid!r} orderId={order_id!r} "
            f"status={created.get('status')!r} totalAmount={created.get('totalAmount')!r}"
        )
        if not order_id:
            return 1

        deadline = time.monotonic() + 180
        status = None
        while time.monotonic() < deadline:
            labels = client.get_label(order_id)
            status = (labels[0] if labels else {}).get("status")
            print(f"poll status={status!r}")
            if status == "OK":
                break
            if status in ("failed", "canceled"):
                print("unexpected pre-cancel status")
                return 1
            time.sleep(5)
        if status != "OK":
            print("TIMEOUT waiting OK before cancel")
            return 1

        # Colleague report: prefer orderId; also try documenting requestId if needed.
        try:
            cancel_out = client.cancel_label(order_id)
            cancel_ref = "orderId"
        except ViteClientError as exc:
            print(f"cancel_via_orderId_FAIL err={exc}; trying requestId")
            cancel_out = client.cancel_label(rid)
            cancel_ref = "requestId"
        print(f"cancel_OK via={cancel_ref} body={cancel_out}")

        labels = client.get_label(order_id)
        lab = labels[0] if labels else {}
        print(
            f"getLabel_after status={lab.get('status')!r} "
            f"url_present={bool(lab.get('url'))}"
        )
        after = client._client.get("/user/account")
        print(f"balance_after={after.text}")
        if lab.get("status") != "canceled":
            print("WARN expected getLabel status=canceled")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
