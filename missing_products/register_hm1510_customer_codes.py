# -*- coding: utf-8 -*-
"""Register user-approved HM1510 customer codes with the 删除 prefix.

Current approved writes:
  - HM1510-YD2-LLK50x22x55-WHITE <- 删除Curve-Pillow-50-Foam

TT0031247K0064095-Foam is blocked because EN has no HM1510 item for
218x115x55; it is reported but not written.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
MAIN = HERE.parents[3]

DELETE_PREFIX = "\u5220\u9664"  # 删除

WRITES = [
    {
        "item_code": "HM1510-YD2-LLK50x22x55-WHITE",
        "ref_code": DELETE_PREFIX + "Curve-Pillow-50-Foam",
    }
]

BLOCKED = [
    {
        "sku": "TT0031247K0064095-Foam",
        "reason": "EN 未找到 218x115x55 对应的 HM1510 物料，需先确认或创建目标物料",
    }
]


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
            params={"fields": json.dumps(["item_code", "item_name", "item_group", "customer_items"])},
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
        if response.status_code != 200:
            raise RuntimeError(f"PUT failed {response.status_code}: {response.text[:800]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入生产 EN（默认只预览）")
    args = parser.parse_args()

    client = ENClient()
    results = []
    for write in WRITES:
        item = client.get_item(write["item_code"])
        refs = [row.get("ref_code") for row in item.get("customer_items") or []]
        present = write["ref_code"] in refs
        action = "already_registered" if present else ("would_register" if not args.apply else "registered_and_verified")
        if args.apply and not present:
            customer_items = list(item.get("customer_items") or [])
            customer_items.append({"customer_group": "美国公司", "ref_code": write["ref_code"]})
            client.put_customer_items(write["item_code"], customer_items)
            verified = client.get_item(write["item_code"])
            verified_refs = [row.get("ref_code") for row in verified.get("customer_items") or []]
            if write["ref_code"] not in verified_refs:
                raise RuntimeError(f"回读验证失败: {write['item_code']} -> {write['ref_code']}")
        results.append(
            {
                "item_code": write["item_code"],
                "ref_code": write["ref_code"],
                "action": action,
                "current_refs": refs,
            }
        )

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "results": results,
                "blocked": BLOCKED,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
