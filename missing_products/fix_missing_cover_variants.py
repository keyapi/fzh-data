# -*- coding: utf-8 -*-
"""Attach/create missing PK# cover variants for known product SKUs.

Default is dry-run. Production writes require --apply.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

from missing_products.cover_variant_rules import (
    CoverGap,
    classify_cover_gap,
    cover_item_code,
    cover_variant_payload,
    strip_bom_for_recreate,
)

ROOT = Path(__file__).resolve().parents[1]

GAPS = [
    {
        "product": "KS0001-CMM-153-PURPLE",
        "product_template": "KS0001",
        "cover_template": "PK#KS0001",
        "cover_group": "皮壳#三角靠枕",
    },
    {
        "product": "KS0001-DM-140-SKYBLUE",
        "product_template": "KS0001",
        "cover_template": "PK#KS0001",
        "cover_group": "皮壳#三角靠枕",
    },
    {
        "product": "KS0001-TR-100-ROSERED",
        "product_template": "KS0001",
        "cover_template": "PK#KS0001",
        "cover_group": "皮壳#三角靠枕",
    },
    {
        "product": "KS0248-DM-153-RED",
        "product_template": "KS0248",
        "cover_template": "PK#KS0248",
        "cover_group": "皮壳#三角靠枕无扣",
    },
    {
        "product": "KS0248-QDKTR-45-DEEPBLUE",
        "product_template": "KS0248",
        "cover_template": "PK#KS0248",
        "cover_group": "皮壳#三角靠枕无扣",
    },
    {
        "product": "KS0248-QDKTR-45-GREY",
        "product_template": "KS0248",
        "cover_template": "PK#KS0248",
        "cover_group": "皮壳#三角靠枕无扣",
    },
]


def _load_dotenv() -> None:
    for p in [ROOT / "EN_API" / ".env", ROOT / ".env"]:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


class NoExpect(HTTPAdapter):
    def add_headers(self, request, **kwargs):  # type: ignore[override]
        super().add_headers(request, **kwargs)
        request.headers.pop("Expect", None)


class EN:
    def __init__(self, base: str, key: str, secret: str) -> None:
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{secret}"
        self.s.headers["Accept"] = "application/json"
        self.s.mount("https://", NoExpect())

    def get_item(self, name: str) -> dict[str, Any] | None:
        r = self.s.get(
            f"{self.base}/api/resource/Item/{quote(name, safe='')}",
            timeout=60,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("data")

    def post_item(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        r = self.s.post(f"{self.base}/api/resource/Item", json=payload, timeout=60)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}

    def put_item(self, name: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        r = self.s.put(
            f"{self.base}/api/resource/Item/{quote(name, safe='')}",
            json=payload,
            timeout=60,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}

    def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        r = self.s.get(
            f"{self.base}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            timeout=60,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("data")

    def list_docs(self, doctype: str, filters: list[Any], fields: list[str]) -> list[dict[str, Any]]:
        r = self.s.get(
            f"{self.base}/api/resource/{quote(doctype, safe='')}",
            params={
                "filters": json.dumps(filters),
                "fields": json.dumps(fields),
                "limit_page_length": 50,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("data") or []

    def put_doc(self, doctype: str, name: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        r = self.s.put(
            f"{self.base}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            json=payload,
            timeout=60,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}

    def post_doc(self, doctype: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        r = self.s.post(
            f"{self.base}/api/resource/{quote(doctype, safe='')}",
            json=payload,
            timeout=60,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:500]}

    def delete_doc(self, doctype: str, name: str) -> tuple[int, dict[str, Any] | str]:
        r = self.s.delete(
            f"{self.base}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            timeout=60,
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text[:500]


def _recreate_as_variant(api: EN, spec: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    """variant_of is set-once; cancel/delete BOMs, delete item, POST as variant, restore BOMs."""
    cover_code = payload["item_code"]
    product_code = spec["product"]
    steps: list[str] = []
    pk_boms = api.list_docs("BOM", [["item", "=", cover_code]], ["name", "docstatus"])
    product_boms = api.list_docs("BOM", [["item", "=", product_code]], ["name", "docstatus"])
    saved = []
    for row in pk_boms + product_boms:
        doc = api.get_doc("BOM", row["name"])
        if doc:
            saved.append(strip_bom_for_recreate(doc))
            if doc.get("docstatus") == 1:
                c1, _ = api.put_doc("BOM", row["name"], {"docstatus": 2})
                steps.append(f"cancel {row['name']} -> {c1}")
            d1, _ = api.delete_doc("BOM", row["name"])
            steps.append(f"delete {row['name']} -> {d1}")
    d_item, body = api.delete_doc("Item", cover_code)
    steps.append(f"delete Item {cover_code} -> {d_item}")
    if d_item not in (200, 202):
        return {"status": "FAIL", "gap": "recreate", "cover": cover_code, "detail": body, "steps": steps}
    c_item, cres = api.post_item(payload)
    steps.append(f"create variant {cover_code} -> {c_item}")
    if c_item != 200:
        return {"status": "FAIL", "gap": "recreate", "cover": cover_code, "detail": cres, "steps": steps}
    for bom in saved:
        p1, pres = api.post_doc("BOM", bom)
        steps.append(f"create BOM {bom['item']} -> {p1}")
        if p1 != 200:
            return {"status": "FAIL", "gap": "recreate", "cover": cover_code, "detail": pres, "steps": steps}
        bom_name = (pres.get("data") or {}).get("name")
        if bom_name:
            s1, _ = api.put_doc("BOM", bom_name, {"docstatus": 1})
            steps.append(f"submit {bom_name} -> {s1}")
    return {"status": "OK", "gap": "recreate", "cover": cover_code, "product": product_code, "steps": steps}


def _apply_one(api: EN, spec: dict[str, str], apply: bool) -> dict[str, Any]:
    product = api.get_item(spec["product"])
    if not product:
        return {"product": spec["product"], "status": "FAIL", "detail": "成品不存在"}
    cover_code = cover_item_code(
        spec["product"], spec["product_template"], spec["cover_template"]
    )
    cover = api.get_item(cover_code)
    gap = classify_cover_gap(
        product=product, cover=cover, cover_template=spec["cover_template"]
    )
    payload = cover_variant_payload(
        product,
        product_template=spec["product_template"],
        cover_template=spec["cover_template"],
        cover_group=spec["cover_group"],
    )
    row = {
        "product": spec["product"],
        "cover": cover_code,
        "gap": gap.value,
        "payload": payload,
    }
    if gap == CoverGap.OK:
        row["status"] = "SKIP"
        return row
    if not apply:
        row["status"] = "DRY-RUN"
        return row
    if gap == CoverGap.CREATE_VARIANT:
        code, res = api.post_item(payload)
        row["http"] = code
        row["status"] = "OK" if code == 200 else "FAIL"
        if code != 200:
            row["detail"] = res
        return row
    code, res = api.put_item(
        cover_code,
        {
            "variant_of": payload["variant_of"],
            "has_variants": 0,
            "item_group": payload["item_group"],
            "attributes": payload["attributes"],
            "item_name": payload["item_name"],
        },
    )
    if code == 200:
        row["http"] = code
        row["status"] = "OK"
        return row
    exc = str(res)
    if "CannotChangeConstantError" in exc or "Variant Of" in exc:
        rec = _recreate_as_variant(api, spec, payload)
        rec.update({k: row[k] for k in ("product", "cover", "payload") if k not in rec})
        rec["gap"] = CoverGap.ATTACH_TO_TEMPLATE.value + "/recreate"
        return rec
    row["http"] = code
    row["status"] = "FAIL"
    row["detail"] = res
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="补齐成品缺失的皮壳多规格变体")
    ap.add_argument("--apply", action="store_true", help="写入生产；默认只预览")
    args = ap.parse_args()
    _load_dotenv()
    key = os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY") or ""
    secret = os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET") or ""
    url = os.getenv("ERP_URL") or "https://erpnext.vilavi.cn"
    if not key or not secret:
        print("missing EN credentials")
        return 1
    api = EN(url, key, secret)
    results = []
    for spec in GAPS:
        row = _apply_one(api, spec, args.apply)
        results.append(row)
        print(
            f"{row.get('status')} {row.get('gap')} {row.get('product')} -> {row.get('cover')}"
        )
        if row.get("detail"):
            print(" ", json.dumps(row["detail"], ensure_ascii=False)[:500])
    failed = [r for r in results if r.get("status") == "FAIL"]
    if args.apply:
        for spec in GAPS:
            cover_code = cover_item_code(
                spec["product"], spec["product_template"], spec["cover_template"]
            )
            cover = api.get_item(cover_code)
            ok = (
                cover
                and cover.get("variant_of") == spec["cover_template"]
                and (cover.get("attributes") or [])
            )
            print(
                f"VERIFY {cover_code} variant_of={cover.get('variant_of') if cover else None} attrs={len((cover or {}).get('attributes') or [])} {'OK' if ok else 'FAIL'}"
            )
            if not ok:
                failed.append({"cover": cover_code, "status": "FAIL"})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
