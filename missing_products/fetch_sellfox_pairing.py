# -*- coding: utf-8 -*-
"""Read-only Sellfox pairing inventory: Amazon online products + multi-platform pairings.

Only read endpoints are called:
  - /api/order/api/product/pageList.json (Amazon online products)
  - /api/multiplatform/match/getList.json (multi-platform pairings)

No write endpoint is called. Raw API rows are cached under missing_products/out/
so reruns do not need to fetch 50k+ Amazon rows again; use --refresh to force a
fresh pull. Output goes to missing_products/out/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

HERE = Path(__file__).resolve().parent
MAIN = Path(r"D:\Work\赛狐\Cursor")
OUT = HERE / "out"
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from SELLFOX_API.client import SellfoxClient, SellfoxConfig
from tongtu_data import (
    latest_mainline_audit_path,
    latest_tongtu_zip_path,
    load_mainline_mapping,
    load_tongtu_aliases,
    norm,
)

PAGE_SIZE = 200
SLEEP = 0.35
CACHE_DIR = OUT / "pairing_cache"


def cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def load_cache(name: str):
    path = cache_path(name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(name: str, rows: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(name).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


AMAZON_COLS = [
    "shopId",
    "marketplaceId",
    "sku",
    "asin",
    "parentAsin",
    "onlineStatus",
    "quantity",
    "fnsku",
    "title",
    "commoditySku",
    "commodityName",
    "commodityId",
]
MULTI_COLS = [
    "id",
    "shopId",
    "shopName",
    "platformType",
    "platformName",
    "sku",
    "commodityId",
    "commoditySku",
    "commodityName",
    "matchStatus",
    "skuId",
    "pid",
    "createTime",
    "updateTime",
]


def fetch_all(client: SellfoxClient, path: str, body_builder: Callable[[int], dict]) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        body = body_builder(page)
        data = None
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                data = client.signed_post(path, body) or {}
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = 2 ** attempt
                print(f"  {path} 第{page}页 第{attempt + 1}次失败: {type(exc).__name__} {str(exc)[:100]}")
                if attempt < 4:
                    time.sleep(wait)
        if data is None:
            raise last_exc or RuntimeError(f"{path} 第{page}页拉取失败")
        batch = data.get("rows") or []
        rows.extend(batch)
        total = data.get("totalSize") or 0
        if page % 20 == 0:
            print(f"  {path} 已拉取 {len(rows)} / {total}")
        if len(rows) >= total or not batch:
            break
        page += 1
        time.sleep(SLEEP)
    return rows


def amazon_frame(rows: Iterable[dict], match: str) -> pd.DataFrame:
    out = []
    for row in rows:
        out.append({col: norm(row.get(col)) for col in AMAZON_COLS})
    df = pd.DataFrame(out)
    df.insert(0, "配对状态", "已配对" if match == "true" else "未配对")
    return df


def multi_frame(rows: Iterable[dict]) -> pd.DataFrame:
    out = []
    for row in rows:
        out.append({col: norm(row.get(col)) for col in MULTI_COLS})
    return pd.DataFrame(out)


def build_known_maps(mapping: pd.DataFrame, aliases: pd.DataFrame) -> tuple[set[str], set[str], dict[str, set[str]]]:
    tt_keys: set[str] = set()
    for _, row in aliases.iterrows():
        tt_keys.add(norm(row.get("通途SKU")))
        tt_keys.add(norm(row.get("SKU别名")))

    en_skus: set[str] = set()
    tt_to_en: dict[str, set[str]] = {}
    for _, row in mapping.iterrows():
        sku = norm(row.get("通途SKU"))
        local = norm(row.get("赛狐已存在SKU")) or norm(row.get("赛狐缺失SKU"))
        for code in [x.strip() for x in local.split("|") if x.strip()]:
            en_skus.add(code)
            if sku:
                tt_to_en.setdefault(sku, set()).add(code)
    return tt_keys, en_skus, tt_to_en


def annotate(df: pd.DataFrame, tt_keys: set[str], en_skus: set[str], tt_to_en: dict[str, set[str]]) -> pd.DataFrame:
    result = df.copy()
    reasons: list[str] = []
    for _, row in result.iterrows():
        key = norm(row.get("sku"))
        local = norm(row.get("commoditySku"))
        in_tt = key in tt_keys
        expected = tt_to_en.get(key, set()) if in_tt else set()
        local_in_en = local in en_skus
        if not in_tt:
            reason = ""
        elif not local:
            reason = "通途别名未配对"
        elif not local_in_en:
            reason = "本地SKU不在EN映射"
        elif expected and local not in expected:
            reason = "本地SKU与EN映射不一致"
        else:
            reason = ""
        reasons.append(reason)
    result["通途别名匹配"] = result["sku"].map(lambda x: "是" if norm(x) in tt_keys else "否")
    result["EN映射SKU匹配"] = result["commoditySku"].map(
        lambda x: ("是" if norm(x) in en_skus else "否") if norm(x) else "无本地SKU"
    )
    result["差异原因"] = reasons
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--refresh", action="store_true", help="忽略本地缓存，重新拉取赛狐 API")
    args = ap.parse_args()

    client = SellfoxClient(SellfoxConfig.from_env(MAIN / ".env", MAIN / "EN_API" / ".env"))
    print(f"赛狐模式: {client.config.mode}")

    amazon_matched = None if args.refresh else load_cache("amazon_matched")
    if amazon_matched is None:
        print("拉取 Amazon 在线产品（已配对）...")
        amazon_matched = fetch_all(
            client,
            "/api/order/api/product/pageList.json",
            lambda page: {"pageNo": str(page), "pageSize": str(PAGE_SIZE), "match": "true"},
        )
        save_cache("amazon_matched", amazon_matched)
    print(f"  已配对: {len(amazon_matched)}")

    amazon_unmatched = None if args.refresh else load_cache("amazon_unmatched")
    if amazon_unmatched is None:
        print("拉取 Amazon 在线产品（未配对）...")
        amazon_unmatched = fetch_all(
            client,
            "/api/order/api/product/pageList.json",
            lambda page: {"pageNo": str(page), "pageSize": str(PAGE_SIZE), "match": "false"},
        )
        save_cache("amazon_unmatched", amazon_unmatched)
    print(f"  未配对: {len(amazon_unmatched)}")

    multi = None if args.refresh else load_cache("multiplatform")
    if multi is None:
        print("拉取多平台配对...")
        multi = fetch_all(
            client,
            "/api/multiplatform/match/getList.json",
            lambda page: {
                "searchType": "commoditySku",
                "searchMode": "exact",
                "matchStatus": "1",
                "pageNo": str(page),
                "pageSize": str(PAGE_SIZE),
            },
        )
        save_cache("multiplatform", multi)
    print(f"  多平台已配对: {len(multi)}")
    multi_amazon = sum(1 for r in multi if norm(r.get("platformType")) in ("0", "13"))
    multi_amazon_vc = sum(1 for r in multi if norm(r.get("platformType")) == "13")

    am_df = amazon_frame(amazon_matched, "true")
    au_df = amazon_frame(amazon_unmatched, "false")
    mp_df = multi_frame(multi)

    audit_path = latest_mainline_audit_path()
    zip_path = latest_tongtu_zip_path()
    mapping = load_mainline_mapping(audit_path) if audit_path else pd.DataFrame()
    aliases = load_tongtu_aliases(zip_path) if zip_path else pd.DataFrame()
    tt_keys, en_skus, tt_to_en = build_known_maps(mapping, aliases)

    am_ann = annotate(am_df, tt_keys, en_skus, tt_to_en)
    au_ann = annotate(au_df, tt_keys, en_skus, tt_to_en)
    mp_ann = annotate(mp_df, tt_keys, en_skus, tt_to_en)

    diff = pd.concat(
        [am_ann[am_ann["差异原因"] != ""], au_ann[au_ann["差异原因"] != ""], mp_ann[mp_ann["差异原因"] != ""]],
        ignore_index=True,
    )
    pending = diff[diff["差异原因"].isin(["本地SKU不在EN映射", "本地SKU与EN映射不一致"])].copy()

    summary = pd.DataFrame(
        [
            ("Amazon 在线产品总数", len(am_df) + len(au_df)),
            ("Amazon 已配对", len(am_df)),
            ("Amazon 未配对", len(au_df)),
            ("多平台配对总数", len(mp_df)),
            ("多平台 Amazon/Amazon_VC 配对", multi_amazon),
            ("多平台 Amazon_VC 配对", multi_amazon_vc),
            ("通途别名来源", zip_path.name if zip_path else "未找到"),
            ("EN 映射底表", audit_path.name if audit_path else "未找到"),
            ("差异行数", len(diff)),
            ("待确认行数", len(pending)),
            ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ],
        columns=["指标", "值"],
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (OUT / f"赛狐配对盘点_{stamp}.xlsx")
    OUT.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="汇总", index=False)
        am_ann.to_excel(writer, sheet_name="Amazon已配对", index=False)
        au_ann.to_excel(writer, sheet_name="Amazon未配对", index=False)
        mp_ann.to_excel(writer, sheet_name="多平台现有配对", index=False)
        diff.to_excel(writer, sheet_name="通途别名_EN差异", index=False)
        pending.to_excel(writer, sheet_name="待确认", index=False)

    print(f"已生成: {out_path}")
    print(
        f"Amazon={len(am_df)}+{len(au_df)} 多平台={len(mp_df)} "
        f"Amazon/Amazon_VC={multi_amazon} 差异={len(diff)} 待确认={len(pending)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
