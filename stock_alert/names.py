# -*- coding: utf-8 -*-
"""SKU → 产品名称 缓存（通途 `goodsQuery.productName`）。

名称会变（改名/新增），所以：
- 本地缓存 `stock_alert_output/sku_names.json`，每个 SKU 记 `name + fetched_at`；
- 每次只补**缺失**的 SKU（`goodsQuery` 批量 10/次，受通途 5 次/分钟限制）；
- 每 `full_refresh_days`（默认 7）**全量重建**一次（分页列全部商品），纠正改名；
- 查不到 → 空名称，调用方用 SKU 兜底。
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

BATCH = 10
DEFAULT_FULL_REFRESH_DAYS = 7


def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


class NameCache:
    def __init__(self, api, path, *, full_refresh_days: int = DEFAULT_FULL_REFRESH_DAYS, today: _dt.date | None = None):
        self.api = api
        self.path = Path(path)
        self.full_refresh_days = full_refresh_days
        self._today = today or _dt.date.today()
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("names"), dict):
                    return data
            except Exception:  # noqa: BLE001 - 损坏则重建
                pass
        return {"names": {}, "last_full_refresh": "", "schema": 1}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _extract(products) -> dict[str, str]:
        """商品列表 → {variant goodsSku: productName}（也含商品级 sku）。"""
        mapping: dict[str, str] = {}
        for product in products or []:
            name = product.get("productName") or product.get("declareCnName") or product.get("sku") or ""
            if product.get("sku"):
                mapping.setdefault(product["sku"], name)
            for detail in product.get("goodsDetail") or []:
                sku = detail.get("goodsSku")
                if sku:
                    mapping[sku] = name
        return mapping

    def _full_refresh(self) -> None:
        names: dict[str, str] = {}
        page = 1
        while page <= 500:
            payload = self.api.request(
                "/openapi/tongtool/goodsQuery",
                {"productType": "0", "pageNo": page, "pageSize": 100},
            )
            rows = (payload.get("datas") or {}).get("array") or []
            names.update(self._extract(rows))
            if len(rows) < 100:
                break
            page += 1
        now = _now_iso()
        self.data["names"] = {k: {"name": v, "fetched_at": now} for k, v in names.items()}
        self.data["last_full_refresh"] = self._today.isoformat()
        self._save()

    def _full_refresh_due(self) -> bool:
        last = self.data.get("last_full_refresh") or ""
        if not last:
            return True
        try:
            return (self._today - _dt.date.fromisoformat(last)).days >= self.full_refresh_days
        except ValueError:
            return True

    def resolve(self, skus) -> dict[str, str]:
        """返回 {sku: 产品名称}；缺失的批量补查，必要时全量重建。"""
        skus = list(dict.fromkeys(s for s in (skus or []) if s))
        if not skus:
            return {}
        if self._full_refresh_due():
            self._full_refresh()
        cache = self.data["names"]
        missing = [s for s in skus if s not in cache]
        changed = False
        for i in range(0, len(missing), BATCH):
            batch = missing[i:i + BATCH]
            payload = self.api.request(
                "/openapi/tongtool/goodsQuery",
                {"productType": "0", "skus": batch, "pageNo": 1, "pageSize": len(batch)},
            )
            mapping = self._extract((payload.get("datas") or {}).get("array") or [])
            now = _now_iso()
            for sku in batch:
                cache[sku] = {"name": mapping.get(sku, ""), "fetched_at": now}
                changed = True
        if changed:
            self._save()
        return {s: (cache.get(s, {}).get("name") or "") for s in skus}
