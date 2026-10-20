#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1a 补充：未匹配归因（P1 BOM 成本表 vs P2 EN Tongtool Cost Review）。

只读本地文件；输出聚合计数，不含 PII/原始行。
"""

from __future__ import annotations

import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
OUT.mkdir(parents=True, exist_ok=True)
BOM = Path(r"D:/Work/王忠于/成本核算/EN产品BOM成本列表20261016.xlsx")
COST_REVIEW = Path(r"D:/Work/赛狐/Cursor/en_tongtool_cost_review/EN Tongtool Cost Review 导入6仓库存 导出成本 20260514 1129.xlsx")
ORDER_GLOB = r"D:/Work/王忠于/成本核算/2026年{month}月订单_order_cost_*.xlsx"
MONTHS = range(4, 10)
FAMILIES = ("KS0001", "KS0248")
G1_WH = {"美东-CENTRADE", "美中-FZH-DANEEY"}


def cell(row, idx):
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def norm_wh(w):
    u = (w or "").strip().upper()
    if "CENTRADE" in u:
        return "美东-CENTRADE"
    if "DANEEY" in u:
        if "退货" in u:
            return "DANEEY-退货仓"
        if "皮壳" in u or "半成品" in u:
            return "DANEEY-皮壳/半成品"
        return "美中-FZH-DANEEY"
    if "POLAND" in u or "波兰" in u:
        return "波兰"
    return "其他"


def load_bom():
    wb = openpyxl.load_workbook(BOM, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    hdr = list(next(rows))
    idx = {n: (hdr.index(n) if n in hdr else None) for n in ("产品编号", "客户物料号")}
    reverse = defaultdict(set)
    for r in rows:
        if not r:
            continue
        item = str(cell(r, idx["产品编号"]) or "").strip()
        if not item.startswith(FAMILIES):
            continue
        code = str(cell(r, idx["客户物料号"]) or "").strip()
        if not code or code.startswith("已删除"):
            continue
        reverse[code].add(item)
    wb.close()
    return {k: next(iter(v)) for k, v in reverse.items() if len(v) == 1}


def load_cost_review():
    wb = openpyxl.load_workbook(COST_REVIEW, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    first = next(rows)
    # 文件 A1 是 "批量编辑Items"，第二行才是表头
    hdr = list(next(rows)) if first and str(first[0]).strip() == "批量编辑Items" else first
    idx = {n: (hdr.index(n) if n in hdr else None)
           for n in ("Tongtool SKU", "ERPNext物料号", "Match Status")}
    out = {}
    for r in rows:
        if not r:
            continue
        sku = str(cell(r, idx["Tongtool SKU"]) or "").strip()
        if not sku:
            continue
        erp = str(cell(r, idx["ERPNext物料号"]) or "").strip()
        status = str(cell(r, idx["Match Status"]) or "").strip()
        out.setdefault(sku, set()).add((erp, status))
    wb.close()
    return out


def candidates(sku, extra):
    raw = (sku or "").strip()
    out = [(raw, "raw")]
    for label, v in (("platform_sku", extra.get("平台SKU")), ("parsed_sku", extra.get("解析后SKU"))):
        v = str(v or "").strip()
        if v and v != raw:
            out.append((v, label))
    # 尾缀/改名候选（只在 P1 中存在时才算命中）
    for suf in ("-Cover", "-Foam", "-淘汰", "-out"):
        if raw.endswith(suf):
            out.append((raw[: -len(suf)].strip(), f"strip{suf}"))
    if raw.endswith("-"):
        out.append((raw.rstrip("-").strip(), "strip-trailing-dash"))
    m = re.match(r"^(.*)-(\d{1,2})$", raw)
    if m:
        out.append((m.group(1), "strip-1-2-digit-suffix"))
    # 去重保序
    seen = set()
    res = []
    for v, label in out:
        if v and v not in seen:
            seen.add(v)
            res.append((v, label))
    return res


def latest_order_file(m):
    fs = sorted(glob.glob(ORDER_GLOB.format(month=m)))
    return fs[-1] if fs else None


def main():
    p1 = load_bom()
    p1_ci = {k.upper(): v for k, v in p1.items()}
    p2 = load_cost_review()
    p2_ci = {k.upper(): v for k, v in p2.items()}

    global_missing_by_wh = Counter()
    global_tri_by_wh = Counter()
    g1_missing = []
    for m in MONTHS:
        p = latest_order_file(m)
        if not p:
            continue
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = ws.iter_rows(values_only=True)
        hdr = list(next(rows))
        ix = lambda n: hdr.index(n) if n in hdr else None
        cols = {k: ix(k) for k in ("发货日期", "平台SKU", "通途SKU", "解析后SKU",
                                   "产品名称", "品类orig", "品类", "品类统一名",
                                   "材料编码", "尺寸", "有无扣", "品类编码",
                                   "发货数量", "渠道", "发货仓库")}
        for r in rows:
            if not r:
                continue
            sku = str(cell(r, cols["通途SKU"]) or "").strip()
            texts = [str(cell(r, cols[k]) or "") for k in
                     ("产品名称", "品类orig", "品类", "品类统一名")]
            p2_family = any(str(erp).startswith(FAMILIES)
                            for erp, _ in p2_ci.get(sku.upper(), set()))
            is_tri = any("三角" in t for t in texts) or (sku.upper() in p1_ci) or p2_family
            if not is_tri:
                continue
            wh = norm_wh(cell(r, cols["发货仓库"]))
            global_tri_by_wh[wh] += 1
            if sku.upper() in p1_ci:
                continue
            global_missing_by_wh[wh] += 1
            if wh not in G1_WH:
                continue
            extra = {k: cell(r, cols[k]) for k in ("平台SKU", "解析后SKU")}
            cands = candidates(sku, extra)
            hit_p1 = None
            hit_p2 = None
            for v, label in cands:
                if v.upper() in p1_ci:
                    hit_p1 = (v, label, p1_ci[v.upper()])
                    break
            if not hit_p1:
                for v, label in cands:
                    if v.upper() in p2_ci:
                        hit_p2 = (v, label, sorted(p2_ci[v.upper()])[:3])
                        break
            g1_missing.append({
                "month": f"2026-{m:02d}",
                "sku": sku,
                "wh": wh,
                "qty": float(cell(r, cols["发货数量"]) or 0),
                "category_orig": str(cell(r, cols["品类orig"]) or ""),
                "category": str(cell(r, cols["品类"]) or ""),
                "category_unified": str(cell(r, cols["品类统一名"]) or ""),
                "product": str(cell(r, cols["产品名称"]) or ""),
                "material_code": str(cell(r, cols["材料编码"]) or ""),
                "has_item_code": bool(cell(r, cols["品类编码"])),
                "hit_p1": hit_p1,
                "hit_p2": hit_p2,
                "candidates": cands,
            })
        wb.close()

    reasons = Counter()
    recovered_p1 = []
    recovered_p2 = []
    still = []
    p1_methods = Counter()
    p2_non_family_items = Counter()
    for x in g1_missing:
        if x["hit_p1"]:
            reasons["recoverable_p1_suffix_or_platform"] += 1
            p1_methods[x["hit_p1"][1]] += 1
            recovered_p1.append(x)
        elif x["hit_p2"]:
            family_hits = [t for t in x["hit_p2"][2] if str(t[0]).startswith(FAMILIES)]
            if family_hits:
                reasons["recoverable_p2_cost_review"] += 1
                x["hit_p2_family"] = family_hits
                recovered_p2.append(x)
            else:
                reasons["p2_maps_non_family"] += 1
                for erp, _ in x["hit_p2"][2]:
                    p2_non_family_items[str(erp)] += 1
                still.append(x)
        else:
            cat = (x["category_orig"] + " " + x["category"] + " " + x["category_unified"] + " " + x["product"])
            if any(k in cat for k in ("配件", "圆枕", "沙发", "床头", "拼色褶皱")):
                reasons["non_family_category"] += 1
            elif not x["material_code"]:
                reasons["no_material_code"] += 1
            else:
                reasons["still_missing"] += 1
            still.append(x)

    out = {
        "global": {
            "tri_rows_by_warehouse": dict(global_tri_by_wh.most_common()),
            "missing_rows_by_warehouse": dict(global_missing_by_wh.most_common()),
            "global_missing_rows": sum(global_missing_by_wh.values()),
            "g1_missing_rows": len(g1_missing),
            "excluded_warehouse_missing_rows": sum(
                v for k, v in global_missing_by_wh.items() if k not in G1_WH),
        },
        "g1_missing_breakdown": dict(reasons),
        "recovered_p1_by_method": dict(p1_methods),
        "p2_non_family_top_items": dict(p2_non_family_items.most_common(20)),
        "g1_missing_total": len(g1_missing),
        "recovered_p1_sample": [
            {"sku": x["sku"], "hit": x["hit_p1"][0], "how": x["hit_p1"][1], "en_item": x["hit_p1"][2]}
            for x in recovered_p1[:20]
        ],
        "recovered_p2_sample": [
            {"sku": x["sku"], "hit": x["hit_p2"][0], "how": x["hit_p2"][1], "cost_review": x["hit_p2"][2]}
            for x in recovered_p2[:20]
        ],
        "still_missing_sample": [
            {"sku": x["sku"], "wh": x["wh"], "qty": x["qty"],
             "category": x["category"], "unified": x["category_unified"],
             "material_code": x["material_code"], "product": x["product"][:60]}
            for x in still[:30]
        ],
    }
    (OUT / "missing_analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
