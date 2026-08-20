# -*- coding: utf-8 -*-
"""ERPNext Product Bundle REST helpers for combo sync.

Create payload is items-only. Never send new_item_code or empty-then-PUT.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

import requests

from combo_reconcile import BundleChild, EnBundle, require_positive_int

PROD_URL = "https://erpnext.vilavi.cn"
TEST_URL = "https://ensh.vilavi.cn"
PREVIEW_METHOD = "work_order_task.api.product_bundle.get_bundle_serial_preview"


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip("'\"")
    return env


def en_create_payload(children: Sequence[tuple[str, int]]) -> dict[str, Any]:
    if not children:
        raise ValueError("EN Product Bundle 创建必须带 items")
    items: list[dict[str, Any]] = []
    for sku, qty in children:
        code = str(sku).strip()
        if not code:
            raise ValueError("EN 创建禁止空 item_code")
        number = require_positive_int(qty, label=code)
        items.append({"item_code": code, "qty": number})
    return {"items": items}


def assert_en_create_payload(payload: dict[str, Any]) -> None:
    extra = set(payload) - {"items"}
    if extra:
        raise ValueError(f"EN 创建禁止传额外字段: {sorted(extra)}")
    if not payload.get("items"):
        raise ValueError("EN 创建禁止空 items")
    for key in ("new_item_code", "new_item_code_name", "name"):
        if key in payload:
            raise ValueError(f"EN 创建禁止传 {key}")


def make_en_session(root: Path, env_name: str = "prod") -> tuple[str, requests.Session]:
    env: dict[str, str] = {}
    for path in (root / ".env", root / "EN_API" / ".env"):
        env.update(load_env_file(path))
    if env_name == "test":
        key = env.get("TEST_ERP_API_KEY") or env.get("ERP_API_KEY") or ""
        secret = env.get("TEST_ERP_API_SECRET") or env.get("ERP_API_SECRET") or ""
        base = env.get("TEST_ERP_URL") or TEST_URL
    else:
        key = env.get("PROD_ERP_API_KEY") or env.get("ERP_API_KEY") or ""
        secret = env.get("PROD_ERP_API_SECRET") or env.get("ERP_API_SECRET") or ""
        base = env.get("ERP_URL") or PROD_URL
    if not key or not secret:
        raise SystemExit(f"EN {env_name} 凭证缺失：检查 EN_API/.env")
    session = requests.Session()
    session.headers["Authorization"] = f"token {key}:{secret}"
    session.headers["Accept"] = "application/json"
    return str(base).rstrip("/"), session


class EnRestClient:
    def __init__(self, base: str, session: requests.Session):
        self.base = base.rstrip("/")
        self.session = session

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(f"{self.base}{path}", params=params, timeout=120)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self.session.post(f"{self.base}{path}", json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    def list_bundle_names(self, *, name_like: str | None, names: list[str] | None) -> list[str]:
        filters: list[Any]
        if names:
            filters = [["name", "in", names]]
        elif name_like:
            filters = [["name", "like", name_like]]
        else:
            raise ValueError("必须提供 --like 或 --sku，禁止无范围全量拉取")
        names_out: list[str] = []
        start = 0
        page_size = 500
        while True:
            data = self._get(
                "/api/resource/Product Bundle",
                {
                    "filters": json.dumps(filters),
                    "fields": json.dumps(["name"]),
                    "limit_page_length": page_size,
                    "limit_start": start,
                },
            )
            rows = data.get("data") or []
            names_out.extend(str(row["name"]) for row in rows if row.get("name"))
            if len(rows) < page_size:
                break
            start += page_size
        return names_out

    def get_product_bundle(self, name: str) -> dict[str, Any]:
        encoded = quote(name, safe="")
        data = self._get(f"/api/resource/Product Bundle/{encoded}")
        return data.get("data") or {}

    def get_item(self, item_code: str) -> dict[str, Any] | None:
        if not item_code:
            return None
        encoded = quote(item_code, safe="")
        response = self.session.get(
            f"{self.base}/api/resource/Item/{encoded}",
            params={
                "fields": json.dumps(["item_code", "item_name", "item_group"]),
            },
            timeout=120,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("data") or {}

    def preview(self, children: Sequence[tuple[str, int]]) -> dict[str, Any]:
        items = [{"item_code": sku, "qty": int(qty)} for sku, qty in children]
        data = self._post(
            f"/api/method/{PREVIEW_METHOD}",
            {"items_json": json.dumps(items, ensure_ascii=False)},
        )
        return data.get("message") or data

    def create_bundle(self, children: Sequence[tuple[str, int]]) -> dict[str, Any]:
        payload = en_create_payload(children)
        assert_en_create_payload(payload)
        data = self._post("/api/resource/Product Bundle", payload)
        return data.get("data") or data


def bundle_from_docs(pb: dict[str, Any], item: dict[str, Any] | None) -> EnBundle:
    items = tuple(
        BundleChild(str(row.get("item_code") or ""), int(row.get("qty") or 0))
        for row in (pb.get("items") or [])
    )
    item = item or {}
    return EnBundle(
        name=str(pb.get("name") or ""),
        new_item_code=str(pb.get("new_item_code") or ""),
        new_item_code_name=str(pb.get("new_item_code_name") or ""),
        items=items,
        item_code=str(item.get("item_code") or ""),
        item_name=str(item.get("item_name") or ""),
        item_group=str(item.get("item_group") or ""),
    )


def fetch_en_bundles(
    client: EnRestClient, *, name_like: str | None, names: list[str] | None
) -> list[EnBundle]:
    found = client.list_bundle_names(name_like=name_like, names=names)
    bundles: list[EnBundle] = []
    for name in found:
        pb = client.get_product_bundle(name)
        item_code = str(pb.get("new_item_code") or pb.get("name") or "")
        item = client.get_item(item_code)
        bundles.append(bundle_from_docs(pb, item))
    return bundles
