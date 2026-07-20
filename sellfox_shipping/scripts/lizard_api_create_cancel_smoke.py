"""One-off 蜴国际 live smoke: create → getLabel → cancel (1 order).

Credentials: YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY from repo-root .env (never print secrets).
Legacy LIZARD_* names still accepted.
"""

from __future__ import annotations

import os
import sys
import time

from sellfox_shipping.carriers.lizard.api_client import (
    LizardApiClient,
    LizardApiError,
    parse_create_order_result,
    parse_get_label_result,
)
from sellfox_shipping.carriers.lizard.order_adapter import shipper_address_for_code
from sellfox_shipping.env_loader import load_dotenv


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        val = (os.getenv(name) or "").strip()
        if val:
            return val
    return default


def _load_creds() -> tuple[str, str, str]:
    load_dotenv()
    token = _env_first("YIGLOBAL_APP_TOKEN", "LIZARD_APP_TOKEN", "LIZARD_TOKEN")
    key = _env_first("YIGLOBAL_APP_KEY", "LIZARD_APP_KEY", "LIZARD_KEY")
    base = _env_first(
        "YIGLOBAL_API_BASE_URL",
        "LIZARD_API_BASE_URL",
        default="http://47.106.72.196",
    )
    if not token or not key:
        raise SystemExit(
            "YIGLOBAL_APP_TOKEN/YIGLOBAL_APP_KEY unset; "
            "copy sellfox_shipping/.env.example keys into repo-root .env"
        )
    return token, key, base


def main() -> int:
    token, key, base = _load_creds()
    print(f"base={base} token_len={len(token)} key_len={len(key)}")
    ref = f"SMOKE-{int(time.time())}"
    # PR91 documented in-coverage shipper (S0143) + simple US consignee.
    body = {
        "sm_code": "FedEx-Ground-J-TX",
        "reference_no": ref,
        "weight_unit_type": "1",
        "parcel_declared_value": 10,
        "parcel_quantity": 1,
        "box_list": [
            {
                "box_actual_weight": 2,
                "box_length": 10,
                "box_width": 8,
                "box_height": 6,
            }
        ],
        "oa_firstname": "Smoke Test",
        "oa_company": "FZH",
        "oa_country": "US",
        "oa_state": "TX",
        "oa_city": "Houston",
        "oa_postcode": "77099",
        "oa_street_address1": "10812 Fallstone Rd",
        "oa_street_address2": "Suite 100",
        "oa_telphone": "2816770938",
        "oa_doorplate": "",
        "oa_phone_ext": "",
        "oa_email": "noreply@example.com",
        "signature_service": "",
        "shipper_address": shipper_address_for_code("S0143"),
    }

    with LizardApiClient(app_token=token, app_key=key, base_url=base) as client:
        print("get_token...")
        client.get_token()
        print("create_order...")
        try:
            created = client.create_order(body)
        except LizardApiError as exc:
            print(f"create_FAIL {exc}")
            return 1
        result = created.get("result") if isinstance(created.get("result"), dict) else {}
        parsed_create = parse_create_order_result(created)
        order_code = parsed_create["order_code"]
        track = parsed_create["tracking_number"]
        print(
            f"create_OK reference_no={ref!r} order_code={order_code!r} "
            f"tracking={track!r} label_url_present={bool(parsed_create['label_url'])} "
            f"code={created.get('code')!r} result_keys={sorted(result.keys())}"
        )
        if not order_code:
            print("create_FAIL missing order_code; keys=", list(result.keys())[:20])
            return 1

        # Poll getLabel up to ~3 min (IT: ~30s); create may already have label.
        label_ok = False
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                lab = client.get_label(order_code=order_code, reference_no=ref)
            except LizardApiError as exc:
                print(f"getLabel_wait {exc}")
                time.sleep(15)
                continue
            parsed_lab = parse_get_label_result(lab)
            print(
                f"getLabel code={parsed_lab['code']!r} sync={parsed_lab['sync_service_status']!r} "
                f"order_status={parsed_lab['order_status']!r} "
                f"tracking={parsed_lab['tracking_number'] or track!r} "
                f"url_present={bool(parsed_lab['label_url'])}"
            )
            if parsed_lab["label_ready"]:
                label_ok = True
                print(
                    f"getLabel_OK tracking={parsed_lab['tracking_number'] or track!r} "
                    f"url_present={bool(parsed_lab['label_url'])}"
                )
                break
            time.sleep(15)
        if not label_ok:
            print("getLabel_WARN not confirmed OK; still attempting cancel")

        print("cancel_order...")
        try:
            canceled = client.cancel_order(order_code=order_code, reference_no=ref)
            print(f"cancel_OK code={canceled.get('code')!r} msg={canceled.get('msg')!r}")
        except LizardApiError as exc:
            print(f"cancel_FAIL {exc}")
            return 1
        return 0 if label_ok else 2


if __name__ == "__main__":
    sys.exit(main())
