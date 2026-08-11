# -*- coding: utf-8 -*-
"""Register approved in-stock Tongtu cover SKUs on EN product variants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests
import pandas as pd

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[3]

REGISTRATIONS = {
    "C/Linen-Coffee-194-661-WOW-Cover": "KS0001-CMM-194-COFFEE",
    "C/Linen-Natural-183-688-wow-Cover": "KS0001-XMMBS-183-HEMPNATURAL",
    "TT0000750K0063009-Cover": "KS0002-DL-100-BLACK",
}


def strip_semifinished_suffix(code: str) -> str:
    for suffix in ("-Cover", "-Foam"):
        if code.lower().endswith(suffix.lower()):
            return code[: -len(suffix)]
    return code


def validate_registration(
    ref_code: str, target_code: str, target: dict, occupied_by: list[str]
) -> None:
    if not target_code.startswith("KS") or target_code.startswith("PK#"):
        raise ValueError(f"{target_code} 不是 EN产品成品变体")
    base_code = strip_semifinished_suffix(ref_code)
    target_refs = {row.get("ref_code") for row in target.get("customer_items") or []}
    if base_code not in target_refs:
        raise ValueError(f"{ref_code} 基码 {base_code} 未登记到 {target_code}")
    conflicts = [code for code in occupied_by if code != target_code]
    if conflicts:
        raise ValueError(f"{ref_code} 已被占用: {', '.join(conflicts)}")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (MAIN / ".env", MAIN / "EN_API" / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip("'\"")
    return env


class ENClient:
    def __init__(self) -> None:
        env = load_env()
        key = env.get("PROD_ERP_API_KEY") or env.get("ERP_API_KEY")
        secret = env.get("PROD_ERP_API_SECRET") or env.get("ERP_API_SECRET")
        if not key or not secret:
            raise RuntimeError("Production EN API credentials are unavailable")
        self.base = env.get("ERP_URL", "https://erpnext.vilavi.cn").rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {key}:{secret}"

    def get_item(self, item_code: str) -> dict:
        response = self.session.get(
            f"{self.base}/api/resource/Item/{requests.utils.quote(item_code, safe='')}",
            params={"fields": json.dumps(["item_code", "item_name", "item_group", "variant_of", "customer_items"])},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["data"]

    def put_customer_items(self, item_code: str, customer_items: list[dict]) -> None:
        payload = {
            "customer_items": [
                {
                    "customer_group": row.get("customer_group") or "美国公司",
                    "ref_code": row.get("ref_code"),
                }
                for row in customer_items
                if row.get("ref_code")
            ]
        }
        response = self.session.put(
            f"{self.base}/api/resource/Item/{requests.utils.quote(item_code, safe='')}",
            json=payload,
            timeout=60,
        )
        response.raise_for_status()


def owners_from_latest_audit(ref_code: str) -> list[str]:
    reports = sorted((HERE / "out").glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
    for report in reports:
        excel = pd.ExcelFile(report)
        if "通途映射全量" not in excel.sheet_names:
            continue
        rows = pd.read_excel(report, sheet_name="通途映射全量", dtype=str)
        match = rows[rows["通途SKU"].str.casefold() == ref_code.casefold()]
        if match.empty:
            return []
        products = str(match.iloc[0].get("EN精确登记产品") or "")
        if products.lower() == "nan":
            return []
        return [code.strip() for code in products.split("|") if code.strip()]
    raise RuntimeError("Run audit_three_systems.py before applying registrations")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write approved registrations to production EN")
    args = parser.parse_args()
    client = ENClient()
    results = []
    for ref_code, target_code in REGISTRATIONS.items():
        target = client.get_item(target_code)
        owners = owners_from_latest_audit(ref_code)
        validate_registration(ref_code, target_code, target, owners)
        refs = {row.get("ref_code") for row in target.get("customer_items") or []}
        action = "already_registered" if ref_code in refs else "would_register"
        if args.apply and ref_code not in refs:
            customer_items = list(target.get("customer_items") or [])
            customer_items.append({"customer_group": "美国公司", "ref_code": ref_code})
            client.put_customer_items(target_code, customer_items)
            verified = client.get_item(target_code)
            verified_refs = {row.get("ref_code") for row in verified.get("customer_items") or []}
            if ref_code not in verified_refs:
                raise RuntimeError(f"Verification failed: {target_code} -> {ref_code}")
            action = "registered_and_verified"
        results.append({"tongtu_sku": ref_code, "en_product": target_code, "action": action})

    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
