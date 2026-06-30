# -*- coding: utf-8 -*-
"""独立站 (daneey.com) 产品链接写入 EN 系统。

数据流：
  daneey.com 产品数据 (CSV / API)
    → 提取所有 SKU
    → 调用 vilavi_pim API 批量查询 SKU → 物料组 映射
    → 按物料组合并产品链接
    → 全量覆盖写入 Item Group.daneey_product_details

使用:
  python shopify_to_en.py --mode csv --dry-run --env test    # CSV 预览
  python shopify_to_en.py --mode csv --env test               # CSV 写测试
  python shopify_to_en.py --mode csv --env prod               # CSV 写生产
  python shopify_to_en.py --mode api --dry-run --env prod     # API 预览
  python shopify_to_en.py --mode api --env prod               # API 写生产（定时任务用）
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

import urllib3
from urllib3.connectionpool import HTTPConnectionPool

# ── urllib3 全局补丁 — 阻止 nginx 417 Expectation Failed ──
_orig_make_request = HTTPConnectionPool._make_request
def _patched_make_request(self, conn, method, url, body=None, headers=None, *args, **kw):
    if headers and "Expect" in headers:
        del headers["Expect"]
    return _orig_make_request(self, conn, method, url, body, headers, *args, **kw)
HTTPConnectionPool._make_request = _patched_make_request

_DIR = Path(__file__).resolve().parent
_OUT_DIR = _DIR / "out"
_OUT_DIR.mkdir(parents=True, exist_ok=True)
_STORE_URL = "https://daneey.com"
_CSV_DEFAULT = _DIR / "数据源" / "products_export_1.csv"


# ═══════════════════════════════════════════════════════════
# 环境配置
# ═══════════════════════════════════════════════════════════

ENV_URLS = {"test": "https://ensh.vilavi.cn", "prod": "https://erpnext.vilavi.cn"}
ENV_KEY_MAP = {
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
}

def load_dotenv() -> None:
    for p in [_DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env"]:
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

def get_erpnext_url(env: str = "test") -> str:
    return ENV_URLS.get(env, ENV_URLS["test"])

def get_erpnext_credentials(env: str = "test") -> tuple[str, str]:
    key_var, secret_var = ENV_KEY_MAP.get(env, ENV_KEY_MAP["test"])
    return os.getenv(key_var, ""), os.getenv(secret_var, "")

load_dotenv()


# ═══════════════════════════════════════════════════════════
# ERPNext API 客户端
# ═══════════════════════════════════════════════════════════

class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)

class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str, label: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label or base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())
        self._sku_cache: dict[str, dict[str, str]] = {}

    def _request(self, method: str, url: str, *, retries: int = 3, retry_delay: float = 3.0, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", (60, 180))
        for a in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                if a >= retries:
                    raise
                status = getattr(getattr(e, "response", None), "status_code", 0)
                delay = retry_delay * (a + 1) * (2 if status in (500, 502, 503, 504, 417, 408) else 1)
                print(f"    [RETRY {a+1}/{retries}] HTTP {status}, 等待 {delay:.0f}s...")
                time.sleep(delay)
        raise RuntimeError("unreachable")

    def _get(self, resource: str, docname: str | None = None, filters: list | None = None, fields: list[str] | None = None, params: dict | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/api/resource/{resource}" + (f"/{quote(docname, safe='')}" if docname else "")
        p = params or {}
        if fields: p["fields"] = json.dumps(fields)
        if filters: p["filters"] = json.dumps(filters)
        return self._request("GET", url, params=p).json()

    def _put(self, resource: str, docname: str, data: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/resource/{resource}/{quote(docname, safe='')}"
        return self._request("PUT", url, json=data).json()

    API_PATH = "vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping"

    def load_sku_mappings(self, skus: list[str], force_refresh: bool = False) -> dict[str, dict[str, str]]:
        skus_to_query = [s for s in skus if s not in self._sku_cache]
        if not skus_to_query and not force_refresh:
            return self._sku_cache

        # 提取基础 SKU：TT 前缀的 SKU 格式为 TT数字+K+数字，后面跟的是后缀
        # 如 TT0312640K0064285-1、TT0031131K0063816-C-peach、TT0312588K0064179-Foam
        # 基础码 = TT0312640K0064285、TT0031131K0063816、TT0312588K0064179
        import re
        base_skus = set()
        suffix_map = {}
        tt_pattern = re.compile(r'^(TT\d+K\d+)')
        for s in skus_to_query:
            m = tt_pattern.match(s)
            if m:
                base = m.group(1)
                if base != s:
                    base_skus.add(base)
                    suffix_map[s] = base

        expanded_skus = list(set(skus_to_query) | base_skus)
        url = f"{self.base_url}/api/method/{self.API_PATH}"
        print(f"  [API] 查询 {len(expanded_skus)} 个 SKU 的物料组映射（含 {len(base_skus)} 个基础码）...")
        try:
            resp = self._request("POST", url, json={"skus": expanded_skus}, retries=1, retry_delay=2, timeout=(60, 300))
            message = resp.json().get("message", {})
            for item in message.get("results", []):
                sku = item.get("sku", "").strip()
                if sku:
                    self._sku_cache[sku] = {"item_name": item.get("item_name", ""), "item_code": item.get("item_code", ""), "item_group": item.get("item_group", ""), "customer_name": item.get("customer_name", ""), "item_group_url": item.get("item_group_url", "")}
            # 后缀 → 基础码 映射：如果基础码查到但后缀没查到，让后缀指向基础码的结果
            for suffixed, base in suffix_map.items():
                if suffixed not in self._sku_cache and base in self._sku_cache and self._sku_cache[base].get("item_group"):
                    self._sku_cache[suffixed] = self._sku_cache[base]
            for sku in message.get("not_found", []):
                if sku not in self._sku_cache:
                    self._sku_cache[sku] = {}
            print(f"  [API] 成功: {message.get('total', 0)} 条, 未找到: {len(message.get('not_found', []))} 个")
        except Exception as e:
            err = getattr(e, "response", None)
            print(f"  [ERROR] 查询失败: {(err.text[:200] if err else str(e))}")
        return self._sku_cache

    def find_item_group_by_tt_sku(self, tt_sku: str) -> tuple[str | None, str | None]:
        info = self._sku_cache.get(tt_sku.strip(), {})
        return (info.get("item_name"), info.get("item_group")) if info and info.get("item_group") else (None, None)

    def update_daneey_urls(self, ig_name: str, html_content: str) -> bool:
        try:
            self._put("Item Group", ig_name, data={"daneey_product_details": html_content})
            return True
        except Exception as e:
            print(f"    [ERROR] 更新 {ig_name} 失败: {e}")
            return False

    def clear_daneey_urls(self, ig_name: str) -> bool:
        return self.update_daneey_urls(ig_name, "")

    def find_groups_with_daneey_urls(self) -> list[str]:
        try:
            data = self._get("Item Group", filters=[["Item Group", "daneey_product_details", "!=", ""]], fields=["item_group_name"], params={"limit_page_length": "0"})
            return [d.get("item_group_name", "") for d in data.get("data", []) if d.get("item_group_name")]
        except Exception as e:
            print(f"  [ERROR] 查询已有 daneey_product_details 物料组失败: {e}")
            return []


# ═══════════════════════════════════════════════════════════
# Shopify 数据源
# ═══════════════════════════════════════════════════════════

@dataclass
class Product:
    handle: str = ""
    title: str = ""
    url: str = ""
    skus: list[str] = field(default_factory=list)
    variants: list[dict[str, str]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    product_category: str = ""
    seo_title: str = ""
    seo_description: str = ""
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def from_csv(filepath: str, store_url: str = _STORE_URL) -> list[dict[str, Any]]:
    products: dict[str, Product] = {}
    with open(filepath, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            handle = row.get("Handle", "").strip()
            if not handle:
                continue
            if handle not in products:
                products[handle] = Product(handle=handle, title=row.get("Title", "").strip(), url=f"{store_url.rstrip('/')}/products/{handle}")
            p = products[handle]
            sku = row.get("Variant SKU", "").strip()
            if sku and sku not in p.skus:
                p.skus.append(sku)
                p.variants.append({"sku": sku, "price": row.get("Variant Price", "").strip(), "option1_name": row.get("Option1 Name", "").strip(), "option1_value": row.get("Option1 Value", "").strip()})
            img = row.get("Image Src", "").strip()
            if img and img not in p.images:
                p.images.append(img)
    return [p.to_dict() for p in products.values()]

def from_api(store_url: str = _STORE_URL, max_products: int | None = None) -> list[dict[str, Any]]:
    base = store_url.rstrip("/")
    products: dict[str, Product] = {}
    page = 1
    while True:
        print(f"  [API] 拉取第 {page} 页...")
        data = requests.get(f"{base}/products.json?limit=250&page={page}", timeout=30).json().get("products", [])
        if not data:
            break
        for item in data:
            handle = item.get("handle", "").strip()
            if not handle:
                continue
            p = Product(handle=handle, title=item.get("title", "").strip(), url=f"{base}/products/{handle}", product_category=item.get("product_type", "").strip() or "")
            for v in item.get("variants", []):
                sku = (v.get("sku") or "").strip()
                if sku:
                    if sku not in p.skus: p.skus.append(sku)
                    p.variants.append({"sku": sku, "price": str(v.get("price", "")), "option1_name": "", "option1_value": v.get("option1", "")})
            for img in item.get("images", []):
                src = img.get("src", "").strip()
                if src and src not in p.images: p.images.append(src)
            products[handle] = p
        page += 1
        if max_products and len(products) >= max_products: break
        time.sleep(0.3)
    return [p.to_dict() for p in products.values()]

def print_stats(products: list[dict[str, Any]]) -> None:
    total = len(products)
    multi_sku = sum(1 for p in products if len(p["skus"]) > 1)
    total_skus = sum(len(p["skus"]) for p in products)
    tt_skus = sum(1 for p in products for s in p["skus"] if s.startswith("TT"))
    print(f"  产品总数: {total}")
    print(f"  多变体产品: {multi_sku}")
    print(f"  SKU总数: {total_skus}")
    print(f"  TT前缀SKU: {tt_skus}")


# ═══════════════════════════════════════════════════════════
# 匹配器
# ═══════════════════════════════════════════════════════════

class EnMatcher:
    def __init__(self, client: ErpnextClient) -> None:
        self.client = client

    def load_all_skus(self, products: list[dict[str, Any]]) -> None:
        all_skus = list({s.strip() for prod in products for s in prod.get("skus", []) if s.strip()})
        self.client.load_sku_mappings(all_skus)

    def match_by_tt_sku(self, tt_sku: str) -> tuple[str | None, str | None]:
        return self.client.find_item_group_by_tt_sku(tt_sku)

    def match_batch(self, products: list[dict[str, Any]], progress_cb=None) -> list[dict[str, Any]]:
        self.load_all_skus(products)
        results = []
        total = len(products)
        for i, prod in enumerate(products):
            matched_groups, matched_items = set(), set()
            for sku in prod.get("skus", []):
                item_name, item_group = self.match_by_tt_sku(sku)
                if item_group:
                    matched_groups.add(item_group)
                    matched_items.add(item_name or "")
            if matched_groups:
                prod["match"] = {"item_name": ", ".join(sorted(matched_items)), "item_group": next(iter(matched_groups)), "all_groups": sorted(matched_groups)}
                prod["match_status"] = "ok"
            else:
                prod["match"] = None
                prod["match_status"] = "no_match"
            results.append(prod)
            if progress_cb: progress_cb(i + 1, total)
        return results

    @property
    def cache_size(self) -> int:
        return len(self.client._sku_cache)


# ═══════════════════════════════════════════════════════════
# 写入器
# ═══════════════════════════════════════════════════════════

class EnWriter:
    def __init__(self, client: ErpnextClient) -> None:
        self.client = client
        self.stats = {"成功更新": 0, "更新失败": 0, "清空旧数据": 0}

    def group_by_item_group(self, matched_products: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for prod in matched_products:
            ig = prod.get("match", {}).get("item_group")
            if ig: groups[ig].append(prod)
        return dict(groups)

    def build_html(self, products: list[dict[str, Any]]) -> str:
        parts = ['<div class="daneey-products" style="margin-top:8px;">']
        for prod in products:
            title = prod.get("title", "Unknown")
            url = prod.get("url", "#")
            skus = ", ".join(prod.get("skus", []))
            parts.append(f'  <div style="margin-bottom:8px;"><span style="font-weight:bold;">独立站详情链接：</span><a href="{url}" target="_blank" rel="noopener">{title}</a><br><span style="color:#666;font-size:12px;">SKU: {skus}</span></div>')
        parts.append("</div>")
        return "\n".join(parts)

    def write_all(self, matched_products: list[dict[str, Any]], dry_run: bool = False) -> list[dict[str, Any]]:
        groups = self.group_by_item_group(matched_products)
        log: list[dict] = []
        print(f"\n── {'预览' if dry_run else '写入'}物料组 daneey_product_details ──")
        print(f"  本次匹配物料组: {len(groups)} 个")
        for ig_name, prods in sorted(groups.items()):
            html = self.build_html(prods)
            sku_count = sum(len(p.get("skus", [])) for p in prods)
            if dry_run:
                print(f"  [UPDATE] {ig_name} ({len(prods)} 产品, {sku_count} SKU)")
                log.append({"物料组": ig_name, "产品数": len(prods), "SKU数": sku_count, "操作": "更新"})
            else:
                ok = self.client.update_daneey_urls(ig_name, html)
                s = "更新成功" if ok else "更新失败"
                if ok: self.stats["成功更新"] += 1
                else: self.stats["更新失败"] += 1
                print(f"  [{s}] {ig_name} ({len(prods)} 产品, {sku_count} SKU)")
                log.append({"物料组": ig_name, "产品数": len(prods), "SKU数": sku_count, "操作": s})
        if dry_run:
            existing = self.client.find_groups_with_daneey_urls()
            to_clear = [g for g in existing if g not in groups and g.strip()]
            if to_clear:
                print(f"\n  [DRY-RUN] 以下 {len(to_clear)} 个物料组将被清空（独立站已下架）:")
                for g in sorted(to_clear): print(f"    - {g}")
                log.append({"物料组": ", ".join(sorted(to_clear)), "产品数": len(to_clear), "操作": "将清空(DRY-RUN)"})
        else:
            existing = self.client.find_groups_with_daneey_urls()
            to_clear = [g for g in existing if g not in groups and g.strip()]
            if to_clear:
                print(f"\n  发现 {len(to_clear)} 个物料组需清空（独立站已下架）")
                for ig_name in sorted(to_clear):
                    ok = self.client.clear_daneey_urls(ig_name)
                    if ok: self.stats["清空旧数据"] += 1
                    print(f"  [{'CLEAR' if ok else 'CLEAR-FAIL'}] {ig_name}")
                    log.append({"物料组": ig_name, "操作": "清空" if ok else "清空失败"})
            else:
                print(f"\n  无需清空，所有已有数据均在本次匹配中")
        return log

    def print_summary(self) -> None:
        print(f"\n── 写入汇总 ──")
        for k, v in self.stats.items():
            if v: print(f"  {k}: {v}")


# ═══════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════

def generate_match_report(results: list[dict], unmatched: list[dict], stats: dict, out_dir: Path, dry_run: bool = True) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "预览" if dry_run else "执行"
    path = out_dir / f"独立站链接匹配结果_{tag}_{ts}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([{"指标": k, "数值": str(v)} for k, v in sorted(stats.items())]).to_excel(writer, sheet_name="汇总", index=False)
        if results:
            df_ok = pd.DataFrame(results)
            if "item_group" in df_ok.columns: df_ok = df_ok.sort_values("item_group")
            df_ok.to_excel(writer, sheet_name="匹配成功", index=False)
        # ── 未匹配（独立站在售但EN无对应物料组） ──
        if unmatched:
            df_no = pd.DataFrame(unmatched)
            # 保留关键列方便分析
            cols = ["title", "url", "skus", "product_category"]
            cols = [c for c in cols if c in df_no.columns]
            df_no = df_no[cols] if cols else df_no
            df_no.to_excel(writer, sheet_name="独立站独有_EN无对应", index=False)

            # ── 按分类汇总未匹配 ──
            if "product_category" in df_no.columns:
                cat_stats = df_no["product_category"].value_counts().reset_index()
                cat_stats.columns = ["Shopify 分类", "独立站有_EN无(产品数)"]
                cat_stats.to_excel(writer, sheet_name="差异分析_按分类", index=False)
        if results:
            by_group = defaultdict(list)
            for r in results: by_group[r.get("item_group", "(未知)")].append(r)
            merge_rows = [{"物料组": g, "关联产品数": len(items), "产品链接列表": "\n".join(f"{i.get('title','?')}: {i.get('url','')}" for i in items)} for g, items in sorted(by_group.items())]
            pd.DataFrame(merge_rows).to_excel(writer, sheet_name="按物料组汇总", index=False)
    print(f"  [OK] 报告已生成: {path}")
    return path


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def _process(products: list[dict], args: argparse.Namespace) -> int:
    if not products: return 1
    match_env, write_env = "prod", args.env
    mc = ErpnextClient(get_erpnext_url(match_env), *get_erpnext_credentials(match_env), label=f"匹配({match_env})")
    wc = ErpnextClient(get_erpnext_url(write_env), *get_erpnext_credentials(write_env), label=f"写入({write_env})") if write_env != match_env else mc
    print(f"\n── 匹配源: {match_env} ──\n── 写入目标: {write_env} ──")

    matcher = EnMatcher(mc)
    t0 = time.time()
    results = matcher.match_batch(products, progress_cb=lambda c, t: print(f"    进度: {c}/{t} ({c/t*100:.0f}%)") if t > 0 and c % 50 == 0 else None)
    matched = [r for r in results if r["match_status"] == "ok"]
    unmatched = [r for r in results if r["match_status"] == "no_match"]
    stats = {"数据源模式": "CSV" if args.mode == "csv" else "API", "产品总数": len(results), "匹配成功": len(matched), "匹配失败": len(unmatched), "匹配率": f"{len(matched)/len(results)*100:.1f}%", "耗时(秒)": f"{time.time()-t0:.1f}", "运行模式": "DRY-RUN" if args.dry_run else "执行", "执行时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    print(f"\n── 匹配统计 ──\n  总产品: {stats['产品总数']}\n  匹配成功: {stats['匹配成功']}\n  匹配失败: {stats['匹配失败']}\n  匹配率: {stats['匹配率']}")

    report_path = generate_match_report(matched, unmatched, stats, _OUT_DIR, args.dry_run)

    writer = EnWriter(wc)
    if matched:
        writer.write_all(matched, dry_run=args.dry_run)
        if not args.dry_run: writer.print_summary()
    else:
        print("\n  [SKIP] 无匹配产品，跳过写入")
    print(f"\n[OK] 完成! 报告: {report_path}")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(description="独立站产品链接写入 EN 系统物料组", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--mode", choices=["csv", "api"], default="csv")
    ap.add_argument("--csv-path", default=None)
    ap.add_argument("--env", choices=["test", "prod"], default="test")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-products", type=int, default=None)
    args = ap.parse_args()

    if args.mode == "csv":
        csv_path = Path(args.csv_path) if args.csv_path else _CSV_DEFAULT
        if not csv_path.exists(): print(f"[ERROR] CSV 文件不存在: {csv_path}"); return 1
        products = from_csv(str(csv_path))
    else:
        products = from_api(max_products=args.max_products)
    print_stats(products)
    return _process(products, args)

if __name__ == "__main__":
    sys.exit(main())
