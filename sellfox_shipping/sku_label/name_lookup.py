"""SKU 名称查询 — 通用工具，从 ERPNext Item 获取中/西语品名 + 通途 SKU。

用途：背贴 PDF、包裹详情页、面单品名填充等。
数据来源：ERPNext Item.item_languages 子表（tt_sku / item_name_cn / item_name_es）。
"""

import os
from typing import Optional
from urllib.parse import quote

import httpx


class SkuNameLookup:
    """按 commodity_sku 查询中文名称、西班牙语名称和通途 SKU。

    查询链: ERPNext Item → commodity_sku 兜底

    用法:
        lookup = SkuNameLookup(
            erpnext_base="https://erpnext.vilavi.cn",
            erpnext_api_key=os.getenv("ERP_API_KEY"),
            erpnext_api_secret=os.getenv("ERP_API_SECRET"),
        )
        name = lookup.get("KS0205-LXGFHLSR-100-BEIGE")
        # → {"sku": "TT0020038K0063336", "cn": "欧式布艺沙发...", "es": "Sofá de tela..."}
    """

    def __init__(
        self,
        *,
        erpnext_base: str,
        erpnext_api_key: str,
        erpnext_api_secret: str,
        http_client: Optional[httpx.Client] = None,
    ):
        self._base = erpnext_base.rstrip("/")
        self._headers = {"Authorization": f"token {erpnext_api_key}:{erpnext_api_secret}"}
        self._client = http_client or httpx.Client(timeout=30)
        self._cache: dict[str, dict[str, str] | None] = {}

    def get(self, commodity_sku: str) -> dict[str, str]:
        """返回 {"sku": str, "cn": str, "es": str}。
        sku 来自 item_languages.tt_sku，cn 来自 item_name_cn，es 来自 item_name_es。
        未找到时 sku/cn = commodity_sku, es = ""。
        """
        sku = (commodity_sku or "").strip()
        if not sku:
            return {"sku": "", "cn": "", "es": ""}
        if sku not in self._cache:
            self._cache[sku] = self._resolve(sku)
        result = self._cache[sku]
        return result if result else {"sku": sku, "cn": sku, "es": ""}

    def prefetch(self, skus: list[str]) -> None:
        for s in skus:
            self.get(s)

    def close(self) -> None:
        self._client.close()

    # ── private ────────────────────────────────────────────────────

    def _resolve(self, commodity_sku: str) -> dict[str, str] | None:
        item = self._fetch_erpnext_item(commodity_sku)
        if item is None:
            return None

        langs = item.get("item_languages") or []
        if isinstance(langs, list) and len(langs) > 0:
            lang = langs[0]
            cn = (lang.get("item_name_cn") or "").strip()
            es = (lang.get("item_name_es") or "").strip()
            tt = (lang.get("tt_sku") or "").strip()
            result: dict[str, str] = {}
            if cn:
                result["cn"] = cn
            if tt:
                result["sku"] = tt
            if es:
                result["es"] = es
            if result:
                return {"sku": commodity_sku, "cn": commodity_sku, "es": "", **result}

        # Fallback: use item_name
        cn = (item.get("item_name") or "").strip()
        if cn:
            return {"sku": commodity_sku, "cn": cn, "es": ""}
        return None

    def _fetch_erpnext_item(self, commodity_sku: str) -> dict | None:
        try:
            path = quote(commodity_sku, safe="")
            url = f"{self._base}/api/resource/Item/{path}"
            resp = self._client.get(url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data") if data.get("data") else None
        except Exception:
            return None
