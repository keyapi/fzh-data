"""One-off 蜴国际 live smoke: create → getLabel → cancel (1 order).

Credentials: YIGLOBAL_APP_TOKEN / YIGLOBAL_APP_KEY from repo-root .env (never print secrets).
Legacy LIZARD_* names still accepted.
"""

from __future__ import annotations

import os
import sys
import time

from sellfox_shipping.carriers.lizard.api_client import LizardApiClient, LizardApiError
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
        "signature_service": "",
        "shipper_address": {
            "shipper_name": "Dan-zhao",
            "shipper_postal_code": "77099",
            "shipper_address1": "10812 Fallstone Rd",
            "shipper_address2": "Suite 402",
            "shipper_state_province": "TX",
            "shipper_city": "Houston",
            "shipper_country": "US",
            "shipper_telphone": "2816770938",
        },
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
        order_code = str(
            result.get("order_code")
            or result.get("orderCode")
            or created.get("order_code")
            or ""
        ).strip()
        track = (
            result.get("tracking_number")
            or result.get("trackingNumber")
            or result.get("server_hawbcode")
            or result.get("shipping_method_no")
            or result.get("hawb_code")
            or ""
        )
        print(
            f"create_OK reference_no={ref!r} order_code={order_code!r} "
            f"tracking={track!r} code={created.get('code')!r} "
            f"result_keys={sorted(result.keys())}"
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
            code = lab.get("code")
            lab_result = lab.get("result") if isinstance(lab.get("result"), dict) else {}
            sync = lab_result.get("sync_service_status")
            lab_track = (
                lab_result.get("tracking_number")
                or lab_result.get("server_hawbcode")
                or lab_result.get("shipping_method_no")
                or track
                or ""
            )
            url = (
                lab_result.get("label_url")
                or lab_result.get("url")
                or lab_result.get("lable_file")  # API typo seen in some docs
                or lab_result.get("label_file")
                or ""
            )
            print(
                f"getLabel code={code!r} sync={sync!r} "
                f"order_status={lab_result.get('order_status')!r} "
                f"keys={sorted(lab_result.keys())}"
            )
            if code in (200, "200") and sync in (1, "1"):
                label_ok = True
                print(
                    f"getLabel_OK tracking={lab_track!r} url_present={bool(url)}"
                )
                break
            if code in (202, "202") or sync in (0, "0", None):
                time.sleep(15)
                continue
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
