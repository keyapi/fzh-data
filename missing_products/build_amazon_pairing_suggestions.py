# -*- coding: utf-8 -*-
"""Build Amazon pairing import suggestions and triangle-candidate suggestions.

Inputs (all read-only):
  - latest Amazon 在售未配对分析 workbook (out/)
  - latest 通途EN赛狐映射表 workbook (out/)
  - latest 通途商品导出 zip (D:/Work/赛狐/商品 or 配对)
  - latest 赛狐配对盘点 workbook (out/, for mismatch analysis)
  - latest EN BOM Cost List (for Chinese item names)

Output:
  - out/Amazon配对导入建议_*.xlsx
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))

from tongtu_data import (
    latest_bom_path,
    latest_file,
    latest_tongtu_zip_path,
    load_tongtu_aliases,
    norm,
)

TRIANGLE_SIZES = ("60", "100", "138", "153", "194", "200")
MISMATCH_REASON = "本地SKU与EN映射不一致"
NO_EN_REASON = "通途主SKU无EN映射"

FABRIC_HINTS = {
    "faux fur": "仿兔毛",
    "corduroy": "条绒/灯芯绒",
    "velvet": "绒面(荷兰绒/雪尼尔需确认)",
    "boucle": "圈圈呢",
    "linen": "亚麻/涤麻",
    "cotton": "棉",
    "polyester": "涤纶",
    "chenille": "雪尼尔",
}

COLOR_HINTS = {
    "royal blue": "宝蓝",
    "navy": "藏青",
    "dark blue": "深蓝",
    "black": "黑色",
    "white": "白色",
    "grey": "灰色",
    "gray": "灰色",
    "blue": "蓝色",
    "camel": "驼色",
    "coffee": "咖啡色",
    "brown": "棕色",
    "pink": "粉色",
    "red": "红色",
    "orange": "橙色",
    "green": "绿色",
    "beige": "米色",
    "cream": "奶油色",
    "yellow": "黄色",
    "purple": "紫色",
    "lilac": "丁香紫",
}


def latest_analysis() -> Path:
    return latest_file(OUT, "Amazon在售未配对分析_*.xlsx")


def latest_mapping() -> Path:
    return latest_file(OUT, "通途EN赛狐映射表_*.xlsx")


def latest_pairing() -> Path:
    return latest_file(OUT, "赛狐配对盘点_*.xlsx")


def build_alias_map(aliases: pd.DataFrame) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for _, row in aliases.iterrows():
        main_sku = norm(row.get("通途SKU"))
        alias = norm(row.get("SKU别名"))
        result.setdefault(main_sku, set()).add(main_sku)
        if alias:
            result.setdefault(alias, set()).add(main_sku)
    return result


def build_tongtu_to_en(mapping: pd.DataFrame) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for _, row in mapping.iterrows():
        sku = norm(row.get("通途SKU"))
        en_codes = [x.strip() for x in str(row.get("EN产品编号") or "").split("|") if x.strip()]
        names = [x.strip() for x in str(row.get("EN物料名称") or "").split(";") if x.strip()]
        sellfox = [x.strip() for x in str(row.get("赛狐SKU") or "").split("|") if x.strip()]
        if not sku:
            continue
        for idx, code in enumerate(en_codes):
            result.setdefault(sku, []).append(
                {
                    "EN产品编号": code,
                    "EN物料名称": names[idx] if idx < len(names) else "",
                    "赛狐SKU": sellfox[idx] if idx < len(sellfox) else (sellfox[0] if sellfox else ""),
                }
            )
    return result


def load_bom_names() -> dict[str, str]:
    path = latest_bom_path()
    if not path:
        return {}
    df = pd.read_excel(path, sheet_name=0, dtype=str)
    result: dict[str, str] = {}
    for _, row in df.iterrows():
        code = norm(row.get("产品编号"))
        if code and code not in result:
            result[code] = norm(row.get("产品名称"))
    return result


def extract_sizes(text: str) -> list[str]:
    found = []
    for size in TRIANGLE_SIZES:
        if re.search(rf"(?<![0-9]){size}(?![0-9])", text):
            found.append(size)
    return found


def chinese_hint(title: str) -> str:
    text = title.lower()
    hints = []
    for key, value in FABRIC_HINTS.items():
        if key in text:
            hints.append(value)
    for key, value in COLOR_HINTS.items():
        if key in text:
            hints.append(value)
    return ";".join(dict.fromkeys(hints))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    analysis = latest_analysis()
    mapping_path = latest_mapping()
    pairing_path = latest_pairing()
    zip_path = latest_tongtu_zip_path()
    bom_names = load_bom_names()
    print(f"分析底表: {analysis.name}")
    print(f"映射底表: {mapping_path.name if mapping_path else '未找到'}")
    print(f"配对底表: {pairing_path.name if pairing_path else '未找到'}")
    print(f"通途导出: {zip_path.name if zip_path else '未找到'}")
    print(f"BOM 名称表: {len(bom_names)} 个产品")

    unpaired = pd.read_excel(analysis, sheet_name=1, dtype=str)
    triangle = pd.read_excel(analysis, sheet_name=2, dtype=str)
    mapping = pd.read_excel(mapping_path, sheet_name=1, dtype=str) if mapping_path else pd.DataFrame()

    aliases = load_tongtu_aliases(zip_path) if zip_path else pd.DataFrame()
    alias_map = build_alias_map(aliases)
    tongtu_to_en = build_tongtu_to_en(mapping)
    mapping_tt_skus = set(mapping.get("通途SKU", pd.Series(dtype=str)).astype(str))

    import_rows: list[dict] = []
    review_rows: list[dict] = []
    for _, row in unpaired.iterrows():
        platform_sku = norm(row.get("平台SKU"))
        if norm(row.get("通途别名匹配")) != "是" or not platform_sku:
            continue
        tt_skus = sorted(alias_map.get(platform_sku, set()))
        for tt_sku in tt_skus:
            en_list = tongtu_to_en.get(tt_sku, [])
            if len(en_list) == 1:
                en = en_list[0]
                import_rows.append(
                    {
                        "*MSKU": platform_sku,
                        "店铺名称": "",
                        "*商品SKU": en["赛狐SKU"],
                        "通途SKU": tt_sku,
                        "EN产品编号": en["EN产品编号"],
                        "EN物料名称": en["EN物料名称"],
                        "来源别名": platform_sku,
                        "备注": "建议导入",
                    }
                )
            else:
                in_mapping = "是" if tt_sku in mapping_tt_skus else "否"
                if not en_list:
                    reason = NO_EN_REASON
                    detail = (
                        "平台SKU命中通途主SKU/别名，但该通途主SKU未出现在1411有库存EN映射中"
                        "（未精确登记EN产品成品，或不在本轮有库存范围）"
                    )
                else:
                    reason = "一对多/候选不唯一"
                    detail = "通途主SKU存在EN映射，但对应多个EN产品变体，需人工选择"
                review_rows.append(
                    {
                        "平台SKU": platform_sku,
                        "通途主SKU": tt_sku,
                        "通途SKU是否在EN映射": in_mapping,
                        "EN候选数": len(en_list),
                        "EN候选": " | ".join(f"{e['EN产品编号']}->{e['赛狐SKU']}" for e in en_list),
                        "原因": reason,
                        "说明": detail,
                    }
                )
    import_df = pd.DataFrame(import_rows).drop_duplicates(subset=["*MSKU", "*商品SKU"])
    review_df = pd.DataFrame(review_rows)

    ks0001 = mapping[mapping["EN产品编号"].astype(str).str.startswith("KS0001-")].copy()
    tri_rows: list[dict] = []
    for _, row in triangle.iterrows():
        platform_sku = norm(row.get("平台SKU"))
        title = norm(row.get("标题"))
        sizes = extract_sizes(platform_sku + " " + title)
        candidates = []
        if sizes:
            for size in sizes:
                subset = ks0001[ks0001["EN产品编号"].astype(str).str.contains(f"-{size}-", regex=False)]
                for _, cand in subset.iterrows():
                    candidates.append(
                        {
                            "EN产品编号": norm(cand.get("EN产品编号")),
                            "EN物料名称": norm(cand.get("EN物料名称")),
                            "赛狐SKU": norm(cand.get("赛狐SKU")),
                            "尺寸命中": size,
                        }
                    )
        seen = set()
        uniq = []
        for c in candidates:
            key = c["EN产品编号"]
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        tri_rows.append(
            {
                "平台SKU": platform_sku,
                "ASIN": norm(row.get("ASIN")),
                "标题(原文)": title,
                "标题中文提示(粗略字典)": chinese_hint(title),
                "识别尺寸": ";".join(sizes),
                "候选EN产品": " | ".join(c["EN产品编号"] for c in uniq[:5]),
                "候选EN名称": " | ".join(c["EN物料名称"] for c in uniq[:5]),
                "候选赛狐SKU": " | ".join(c["赛狐SKU"] for c in uniq[:5]),
                "候选数": len(uniq),
                "匹配方式": (
                    "从平台SKU/标题正则提取尺寸，再匹配EN KS0001 item_code 含该尺寸；"
                    "未做翻译、颜色/面料匹配"
                ),
                "建议": "人工核验" if len(uniq) <= 3 else "需进一步筛选",
            }
        )
    tri_df = pd.DataFrame(tri_rows)

    mismatch_rows: list[dict] = []
    if pairing_path:
        pending = pd.read_excel(pairing_path, sheet_name=5, dtype=str)
        mismatch = pending[pending.iloc[:, 15] == MISMATCH_REASON].copy()
        for _, row in mismatch.iterrows():
            platform_sku = norm(row.iloc[3])
            title = norm(row.iloc[9])
            local = norm(row.iloc[10])
            expected_entries = []
            for tt_sku in alias_map.get(platform_sku, set()):
                for en in tongtu_to_en.get(tt_sku, []):
                    expected_entries.append(en)
            expected_skus = sorted({e["赛狐SKU"] for e in expected_entries if e["赛狐SKU"]})
            expected_codes = sorted({e["EN产品编号"] for e in expected_entries if e["EN产品编号"]})
            expected_names = ";".join(
                dict.fromkeys(
                    e["EN物料名称"] or bom_names.get(e["EN产品编号"], "") for e in expected_entries
                )
            )
            mismatch_rows.append(
                {
                    "平台SKU": platform_sku,
                    "ASIN": norm(row.iloc[4]),
                    "标题(原文)": title,
                    "标题中文提示(粗略字典)": chinese_hint(title),
                    "本地赛狐SKU": local,
                    "本地商品名称": bom_names.get(local, ""),
                    "期望赛狐SKU": ";".join(expected_skus),
                    "期望EN产品编号": ";".join(expected_codes),
                    "期望EN物料名称": expected_names,
                    "通途别名匹配": norm(row.iloc[13]),
                    "差异原因": MISMATCH_REASON,
                    "建议": "人工核对，疑似错配或别名撞码，勿自动修改",
                }
            )
    mismatch_df = pd.DataFrame(mismatch_rows)

    notes = [
        ("导入建议", "可导入行已按 import_product_msku_match 模板结构生成；请人工复核后由运营在赛狐导入。"),
        ("别名命中", "442 条为在售未配对且平台SKU命中通途主SKU/别名。"),
        ("无EN映射", "指平台SKU命中了通途主SKU/别名，但该通途主SKU未出现在1411有库存EN映射中（未精确登记EN产品成品，或不在本轮有库存范围）；不是通途没有该SKU。"),
        ("三角靠枕", "275 条候选按尺寸正则匹配 KS0001 EN 变体；标题中文提示仅为粗略字典，颜色/面料需运营或后续模型确认。"),
        ("不一致分析", "本地SKU与EN映射不一致共 65 条；表格已含平台标题、双方SKU与中文名称，供人工或脚本三方比对。"),
    ]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (OUT / f"Amazon配对导入建议_{stamp}.xlsx")
    OUT.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                ("在售未配对", len(unpaired)),
                ("别名命中(平台SKU去重)", unpaired[unpaired.iloc[:, 8] == "是"]["平台SKU"].nunique()),
                ("可生成导入行", len(import_df)),
                ("需人工核对行", len(review_df)),
                ("需人工核对(平台SKU去重)", review_df["平台SKU"].nunique() if len(review_df) else 0),
                ("三角靠枕候选", len(tri_df)),
                ("不一致条数", len(mismatch_df)),
                ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ],
            columns=["指标", "值"],
        ).to_excel(writer, sheet_name="汇总", index=False)
        import_df.to_excel(writer, sheet_name="可导入建议", index=False)
        review_df.to_excel(writer, sheet_name="需人工核对", index=False)
        tri_df.to_excel(writer, sheet_name="三角靠枕建议", index=False)
        mismatch_df.to_excel(writer, sheet_name="65条不一致分析", index=False)
        pd.DataFrame(notes, columns=["项目", "说明"]).to_excel(writer, sheet_name="说明", index=False)

    print(f"已生成: {out_path}")
    print(
        f"可导入={len(import_df)} 人工核对={len(review_df)} "
        f"三角建议={len(tri_df)} 不一致分析={len(mismatch_df)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
