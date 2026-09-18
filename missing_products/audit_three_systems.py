# -*- coding: utf-8 -*-
"""Fresh three-system consistency audit: EN BOM -> Tongtu -> Sellfox.

Data sources:
  - EN BOM Cost List (latest generated from ERPNext server)
  - EN Item/Item Group via production REST API
  - Tongtu combined inventory (latest available export)
  - Sellfox full SKU list via OpenAPI
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from collections import defaultdict
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parent
MAIN = Path(r"D:\Work\赛狐\Cursor")
WEB = WORKTREE / "web_automation"
sys.path.insert(0, str(WORKTREE))

from SELLFOX_API.client import SellfoxClient, SellfoxConfig

KNOWN_SUFFIXES = ["-淘汰", "-out", "-Cover", "-Foam"]


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (MAIN / ".env", MAIN / "EN_API" / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    values.update({key: value for key, value in __import__("os").environ.items() if value})
    return values


def norm(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def to_int(value) -> int:
    text = norm(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def clean_suffix(sku: str) -> str:
    text = norm(sku)
    for suffix in KNOWN_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


@dataclass(frozen=True)
class TongtuEnMatch:
    status: str
    exact_products: tuple[str, ...]
    candidate_products: tuple[str, ...]


def match_tongtu_to_en_products(
    sku: str, customer_to_products: dict[str, list[str]]
) -> TongtuEnMatch:
    """Match the complete Tongtu SKU exactly; suffix-stripped codes are candidates only."""
    complete = norm(sku).lower()
    base = clean_suffix(sku).lower()
    exact = tuple(sorted(set(customer_to_products.get(complete, []))))
    candidates = ()
    if base and base != complete:
        candidates = tuple(sorted(set(customer_to_products.get(base, []))))
    if exact:
        status = "已精确登记"
    elif candidates:
        status = "仅基码匹配"
    else:
        status = "真正未登记"
    return TongtuEnMatch(status, exact, candidates)


def count_exact_matches(matches: dict[str, TongtuEnMatch]) -> int:
    return sum(bool(match.exact_products) for match in matches.values())


def sellfox_status_for_products(
    product_codes: tuple[str, ...], sellfox_by_sku: dict[str, dict]
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if not product_codes:
        return "待EN产品映射", (), ()
    present = tuple(code for code in product_codes if code in sellfox_by_sku)
    missing = tuple(code for code in product_codes if code not in sellfox_by_sku)
    if not missing:
        status = "全部存在"
    elif present:
        status = "部分存在"
    else:
        status = "全部缺失"
    return status, present, missing


def classify_unmatched(sku: str, name: str = "") -> str:
    upper = sku.upper()
    lower = sku.lower()
    if lower.endswith(("-cover", "-foam")) or any(key in name for key in ["皮壳", "海绵", "骨架"]):
        return "半成品/辅料(皮壳/海绵/骨架)"
    if any(key in upper for key in ["BUTTONKIT", "COTTON", "CARD", "-PP", "5LB", "BOX-PL"]):
        return "辅料/耗材类"
    if upper.startswith("497") and len(upper) >= 9:
        return "疑似Amazon ASIN"
    if upper.startswith("TT0") and any(char.isdigit() for char in upper[2:]):
        return "TT编码(需核实)"
    if upper.startswith("CEN") and "OLD" in upper:
        return "淘汰旧编码"
    return "其他未分类"


def en_session(env: dict[str, str]) -> tuple[str, requests.Session]:
    key = env.get("PROD_ERP_API_KEY") or env.get("ERP_API_KEY")
    secret = env.get("PROD_ERP_API_SECRET") or env.get("ERP_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Production EN API credentials are unavailable")
    session = requests.Session()
    session.headers["Authorization"] = f"token {key}:{secret}"
    return env.get("ERP_URL", "https://erpnext.vilavi.cn").rstrip("/"), session


def latest_file(folder: Path, pattern: str) -> Path:
    matches = [path for path in folder.glob(pattern) if not path.name.startswith("~$")]
    if not matches:
        raise FileNotFoundError(f"No file matching {pattern} in {folder}")
    return max(matches, key=lambda path: path.stat().st_mtime)


def load_bom() -> pd.DataFrame:
    folder = HERE / "数据源"
    if not folder.exists():
        folder = MAIN / "warehouse_restock" / "数据源"
    path = latest_file(folder, "EN产品BOM成本列表*.xlsx")
    print(f"EN BOM: {path.name}")
    return pd.read_excel(path, dtype=str)


def load_tongtu() -> pd.DataFrame:
    for folder in (WEB / "output", WEB / "downloads", HERE / "数据源"):
        if not folder.exists():
            continue
        try:
            path = latest_file(folder, "通途合并库存结存清单*.xlsx")
            print(f"通途: {path.name}")
            return pd.read_excel(path, dtype=str)
        except FileNotFoundError:
            continue
    raise FileNotFoundError("No Tongtu inventory export")


def fetch_en_items(base: str, session: requests.Session) -> list[dict]:
    response = session.get(
        f"{base}/api/resource/Item",
        params={
            "fields": json.dumps(["name", "item_code", "item_name", "item_group", "variant_of", "disabled", "has_variants"]),
            "limit_page_length": 0,
        },
        timeout=300,
    )
    response.raise_for_status()
    rows = response.json().get("data", [])
    print(f"EN Items: {len(rows)}")
    return rows


def fetch_en_item_groups(base: str, session: requests.Session) -> tuple[list[dict], dict[str, dict]]:
    response = session.get(
        f"{base}/api/resource/Item Group",
        params={
            "fields": json.dumps(["name", "item_group_name", "parent_item_group", "is_group", "custom_model_id"]),
            "limit_page_length": 0,
        },
        timeout=300,
    )
    response.raise_for_status()
    groups = response.json().get("data", [])
    index = {row.get("name"): row for row in groups if row.get("name")}

    def under_product(name: str, seen: set | None = None) -> bool:
        if seen is None:
            seen = set()
        if name in seen:
            return False
        seen.add(name)
        if name == "产品":
            return True
        parent = index.get(name, {}).get("parent_item_group") or ""
        return bool(parent) and under_product(parent, seen)

    leaves = [
        row for row in groups
        if row.get("is_group") == 0 and norm(row.get("custom_model_id")) and under_product(row.get("name"))
    ]
    print(f"EN Item Group leaves under 产品: {len(leaves)}")
    return groups, {norm(row.get("custom_model_id")): row for row in leaves}


def get_en_item(base: str, session: requests.Session, item_code: str) -> dict:
    response = session.get(
        f"{base}/api/resource/Item/{quote(item_code, safe='')}", timeout=60
    )
    response.raise_for_status()
    return response.json()["data"]


def fetch_en_attributes(base: str, session: requests.Session, codes: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    thread_local = threading.local()

    def worker_session() -> requests.Session:
        if not hasattr(thread_local, "session"):
            new_session = requests.Session()
            new_session.headers["Authorization"] = session.headers["Authorization"]
            thread_local.session = new_session
        return thread_local.session

    def fetch(code: str):
        try:
            return code, get_en_item(base, worker_session(), code)
        except Exception as exc:
            return code, {"error": str(exc)}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, code) for code in codes]
        for future in as_completed(futures):
            code, item = future.result()
            result[code] = item
    errors = [code for code, item in result.items() if "error" in item]
    if errors:
        print(f"  EN attribute fetch errors: {len(errors)}; first={errors[:5]}")
    return result


def fetch_sellfox_rows(client: SellfoxClient) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        data = client.signed_post(
            "/api/commodity/pageList.json", {"pageNo": str(page), "pageSize": "200"}
        )
        batch = data.get("rows") or []
        rows.extend(batch)
        if len(batch) < 200:
            break
        page += 1
        time.sleep(1.2)
    print(f"Sellfox SKU rows: {len(rows)}")
    return rows


def en_attr_pairs(item: dict) -> list[tuple[str, str]]:
    if "error" in item or not item.get("attributes"):
        return []
    return [
        (norm(row.get("attribute")), norm(row.get("attribute_value")))
        for row in item.get("attributes") or []
        if norm(row.get("attribute"))
    ]


def sx_attr_pairs(row: dict) -> list[tuple[str, str]]:
    return [
        (norm(attr.get("attributeCn")), norm(attr.get("attributeValueCn")))
        for attr in row.get("commodityAttributeValueRelaList") or []
        if norm(attr.get("attributeCn"))
    ]


def main() -> None:
    env = load_env()
    base, session = en_session(env)
    client = SellfoxClient(SellfoxConfig.from_env(MAIN / ".env", MAIN / "EN_API" / ".env"))

    print("Loading BOM, Tongtu, EN and Sellfox data...")
    bom = load_bom()
    tongtu = load_tongtu()
    en_items = fetch_en_items(base, session)
    en_item_map = {row.get("item_code"): row for row in en_items if row.get("item_code")}
    _, leaf_groups = fetch_en_item_groups(base, session)

    en_products: dict[str, dict] = {}
    cust_to_en: dict[str, list[str]] = defaultdict(list)
    for _, row in bom.iterrows():
        code = norm(row.get("产品编号"))
        if not code:
            continue
        customer = norm(row.get("客户物料号"))
        if customer:
            cust_to_en[customer.lower()].append(code)
        en_products.setdefault(
            code,
            {
                "name": norm(row.get("产品名称")),
                "customer": customer,
                "ship": norm(row.get("绍兴发货方式")),
            },
        )
    print(f"EN BOM products: {len(en_products)}")

    codes = sorted(en_products)
    print(f"Fetching EN attributes for {len(codes)} variants...")
    en_attrs = fetch_en_attributes(base, session, codes)

    en_spu_products: dict[str, list[str]] = defaultdict(list)
    spu_names: dict[str, str] = {}
    for code in codes:
        item = en_attrs.get(code) or en_item_map.get(code) or {}
        spu = norm(item.get("variant_of")) or code.split("-")[0]
        en_spu_products[spu].append(code)
        spu_names[spu] = norm(item.get("item_group")) or spu_names.get(spu, "")
    for model_id, leaf in leaf_groups.items():
        if model_id not in spu_names or not spu_names[model_id]:
            spu_names[model_id] = norm(leaf.get("item_group_name"))

    print("Loading Tongtu stock...")
    tt_sku_stock: dict[str, int] = defaultdict(int)
    tt_sku_name: dict[str, str] = {}
    tt_sku_wh: dict[str, set[str]] = defaultdict(set)
    alias_to_sku: dict[str, set[str]] = defaultdict(set)
    for _, row in tongtu.iterrows():
        sku = norm(row.get("SKU"))
        qty = to_int(row.get("可用库存"))
        if not sku or qty <= 0:
            continue
        tt_sku_stock[sku] += qty
        tt_sku_name[sku] = norm(row.get("货品名称/规格"))
        tt_sku_wh[sku].add(norm(row.get("仓库")))
        for alias in re.split(r"[;,，；]", norm(row.get("SKU别名"))):
            if alias:
                alias_to_sku[alias].add(sku)
    print(f"Tongtu in-stock SKUs: {len(tt_sku_stock)}")

    # The BOM report can expose only one customer code per product row. Replace
    # that partial index with the complete customer_items child table fetched
    # from each EN product Item.
    complete_cust_to_en: dict[str, list[str]] = defaultdict(list)
    for code in codes:
        for customer in (en_attrs.get(code) or {}).get("customer_items") or []:
            ref_code = norm(customer.get("ref_code"))
            if ref_code:
                complete_cust_to_en[ref_code.lower()].append(code)

    tt_matches: dict[str, TongtuEnMatch] = {}
    tt_matched: dict[str, list[str]] = defaultdict(list)
    for sku in tt_sku_stock:
        match = match_tongtu_to_en_products(sku, complete_cust_to_en)
        tt_matches[sku] = match
        tt_matched[sku].extend(match.exact_products)

    en_cust_stock: dict[str, int] = defaultdict(int)
    spu_stock: dict[str, int] = defaultdict(int)
    for sku, stock in tt_sku_stock.items():
        for code in tt_matched.get(sku, []):
            en_cust_stock[code] += stock
            spu = (en_attrs.get(code) or en_item_map.get(code) or {}).get("variant_of") or code.split("-")[0]
            spu_stock[spu] += stock

    print("Fetching Sellfox SKU list...")
    sx_rows = fetch_sellfox_rows(client)
    sx_by_spu: dict[str, list[dict]] = defaultdict(list)
    sx_by_sku: dict[str, dict] = {}
    for row in sx_rows:
        sku = norm(row.get("sku"))
        if not sku:
            continue
        spu = norm(row.get("spu")) or sku.split("-")[0]
        sx_by_spu[spu].append(row)
        sx_by_sku[sku] = row

    missing_spu_rows = []
    missing_sku_rows = []
    mismatch_rows = []
    only_sellfox_rows = []
    spu_all_rows = []
    for spu in sorted(set(en_spu_products) | set(sx_by_spu)):
        en_codes = set(en_spu_products.get(spu, []))
        sx_codes = {norm(row.get("sku")) for row in sx_by_spu.get(spu, [])}
        sx_rows_spu = sx_by_spu.get(spu, [])
        name = spu_names.get(spu) or (sx_rows_spu[0].get("spuName") if sx_rows_spu else spu)
        parent = leaf_groups.get(spu, {}).get("parent_item_group", "")
        stock = spu_stock.get(spu, 0)
        is_ks = spu.startswith("KS")
        product_flag = "成品" if is_ks else "结构/配件待确认"

        if not en_codes:
            only_sellfox_rows.append(
                {
                    "赛狐SPU": spu,
                    "赛狐款名": name,
                    "赛狐SKU数": len(sx_codes),
                    "说明": "仅赛狐存在，EN/BOM无对应变体",
                }
            )
            continue

        if not sx_codes:
            status = "有库存需创建" if stock > 0 else "无库存待定"
            missing_spu_rows.append(
                {
                    "EN_SPU": spu,
                    "EN物料组": name,
                    "父级": parent,
                    "类型": product_flag,
                    "EN变体数": len(en_codes),
                    "客户码数": sum(1 for code in en_codes if en_products.get(code, {}).get("customer")),
                    "通途库存": stock,
                    "状态": status,
                }
            )
            spu_all_rows.append(
                {
                    "SPU": spu,
                    "EN物料组": name,
                    "父级": parent,
                    "类型": product_flag,
                    "EN变体数": len(en_codes),
                    "赛狐SKU数": 0,
                    "通途库存": stock,
                    "分类": "赛狐缺SPU",
                }
            )
            continue

        missing_codes = sorted(en_codes - sx_codes)
        for code in missing_codes:
            missing_sku_rows.append(
                {
                    "SPU": spu,
                    "EN物料组": name,
                    "EN产品编号": code,
                    "EN产品名称": en_products.get(code, {}).get("name") or (en_attrs.get(code) or {}).get("item_name"),
                    "EN客户物料号": en_products.get(code, {}).get("customer"),
                    "通途库存": en_cust_stock.get(code, 0),
                    "状态": "有库存" if en_cust_stock.get(code, 0) > 0 else "无库存",
                }
            )

        for code in sorted(en_codes & sx_codes):
            sx = sx_by_sku.get(code, {})
            en_item = en_attrs.get(code) or {}
            en_name = (en_item.get("item_name") or en_products.get(code, {}).get("name") or "").strip()
            sx_name = norm(sx.get("name"))
            en_pairs = sorted(set(en_attr_pairs(en_item)))
            sx_pairs = sorted(set(sx_attr_pairs(sx)))
            if en_name != sx_name or en_pairs != sx_pairs:
                mismatch_rows.append(
                    {
                        "SPU": spu,
                        "EN产品编号": code,
                        "EN名称": en_name,
                        "赛狐名称": sx_name,
                        "EN属性": " | ".join(f"{k}={v}" for k, v in en_pairs),
                        "赛狐属性": " | ".join(f"{k}={v}" for k, v in sx_pairs),
                        "差异类型": "名称" if en_name != sx_name else "属性",
                    }
                )

        extra_codes = sorted(sx_codes - en_codes)
        spu_all_rows.append(
            {
                "SPU": spu,
                "EN物料组": name,
                "父级": parent,
                "类型": product_flag,
                "EN变体数": len(en_codes),
                "赛狐SKU数": len(sx_codes),
                "通途库存": stock,
                "分类": "已存在",
                "赛狐独有SKU": len(extra_codes),
            }
        )

    tt_mapping_rows = []
    tt_unmatched_rows = []
    for sku in sorted(tt_sku_stock):
        match = tt_matches[sku]
        warehouses = ", ".join(sorted(tt_sku_wh.get(sku, [])))
        mapped_products = match.exact_products or match.candidate_products
        sx_status, sx_present, sx_missing = sellfox_status_for_products(
            mapped_products, sx_by_sku
        )
        mapping_row = {
            "通途SKU": sku,
            "清理后SKU": clean_suffix(sku),
            "仓库": warehouses,
            "可用库存": tt_sku_stock[sku],
            "货品名称": tt_sku_name.get(sku, ""),
            "分类": classify_unmatched(sku, tt_sku_name.get(sku, "")),
            "EN登记状态": match.status,
            "EN精确登记次数": len(match.exact_products),
            "EN精确登记产品": " | ".join(match.exact_products),
            "基码候选产品": " | ".join(match.candidate_products),
            "赛狐产品SKU状态": sx_status,
            "赛狐已存在SKU": " | ".join(sx_present),
            "赛狐缺失SKU": " | ".join(sx_missing),
        }
        tt_mapping_rows.append(mapping_row)
        if not match.exact_products:
            mapping_row["建议"] = "登记到候选EN产品" if match.candidate_products else "发给运营核对"
            tt_unmatched_rows.append(mapping_row)

    tt_total = len(tt_sku_stock)
    tt_matched_count = count_exact_matches(tt_matches)
    tt_unmatched_count = len(tt_unmatched_rows)
    summary = [
        {"指标": "EN BOM变体数", "值": len(en_products)},
        {"指标": "EN SPU数(BOM variant_of)", "值": len(en_spu_products)},
        {"指标": "赛狐SPU数", "值": len(sx_by_spu)},
        {"指标": "赛狐SKU数", "值": len(sx_by_sku)},
        {"指标": "赛狐缺SPU", "值": len(missing_spu_rows)},
        {"指标": "已有SPU缺SKU", "值": len(missing_sku_rows)},
        {"指标": "名称/属性不一致", "值": len(mismatch_rows)},
        {"指标": "---", "值": "---"},
        {"指标": "通途有货SKU", "值": tt_total},
        {"指标": "通途已登记EN客户物料号", "值": tt_matched_count},
        {"指标": "通途未登记", "值": tt_unmatched_count},
        *[{"指标": f"  未登记-{category}", "值": count} for category, count in Counter(row["分类"] for row in tt_unmatched_rows).most_common()],
        {"指标": "---", "值": "---"},
        {"指标": "仅赛狐SPU", "值": len(only_sellfox_rows)},
        {"指标": "运行时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ]

    out = HERE / "out" / f"三方一致性审计_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(missing_spu_rows).to_excel(writer, sheet_name="赛狐缺SPU", index=False)
        pd.DataFrame(missing_sku_rows).to_excel(writer, sheet_name="已有SPU缺SKU", index=False)
        pd.DataFrame(mismatch_rows).to_excel(writer, sheet_name="名称属性不一致", index=False)
        pd.DataFrame(tt_unmatched_rows).to_excel(writer, sheet_name="通途未登记", index=False)
        pd.DataFrame(tt_mapping_rows).to_excel(writer, sheet_name="通途映射全量", index=False)
        pd.DataFrame(only_sellfox_rows).to_excel(writer, sheet_name="仅赛狐有", index=False)
        pd.DataFrame(spu_all_rows).to_excel(writer, sheet_name="SPU比对全量", index=False)

    print(f"\n审计报告: {out}")
    print(f"  缺SPU: {len(missing_spu_rows)} | 缺SKU: {len(missing_sku_rows)} | 不一致: {len(mismatch_rows)}")
    print(f"  通途有货 {tt_total} / 已登记 {tt_matched_count} / 未登记 {tt_unmatched_count}")


if __name__ == "__main__":
    main()
