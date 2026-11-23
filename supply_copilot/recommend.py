"""Explainable replay of D6/D5/D3b/E decisions for one SKU × branch."""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd

BRANCH = {"USNJ": "美东USNJ", "美东": "美东USNJ", "美东USNJ": "美东USNJ",
          "USTX": "美中USTX", "美中": "美中USTX", "美中USTX": "美中USTX",
          "PL": "波兰", "波兰": "波兰"}


def _path(root, name):
    p = Path(root) / "data" / name
    if not p.exists():
        raise SystemExit(f"包内缺少文件：{name}")
    return p


def _need_columns(frame, cols, name):
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise SystemExit(f"{name} 缺少列：{missing}")


def recommend(data_root, branch, sku=None, limit=50):
    pool = BRANCH.get(str(branch), str(branch))
    d6 = pd.read_excel(_path(data_root, "D6_v6_22.xlsx"), sheet_name="1_全量动作")
    d5 = pd.read_excel(_path(data_root, "D5_v6_8.xlsx"), sheet_name="1_预测")
    d3 = pd.read_excel(_path(data_root, "D3b_v3_11.xlsx"), sheet_name="3_分类")
    _need_columns(d6, ["product_id", "池", "形态", "UOM", "q95", "C可发供给",
                       "en_stock在途+待发", "PO追加(去重)", "SO已下", "CG可调拨抵扣",
                       "净需求95", "建议动作", "新补数量", "催已有量", "建议数量",
                       "需要日", "下单日", "路线状态"], "D6")
    rows = d6[d6["池"].astype(str) == pool].copy()
    if sku:
        rows = rows[rows["product_id"].astype(str).str.contains(str(sku), case=False, na=False)]
    if rows.empty:
        raise SystemExit(f"D6 未找到 {pool} / {sku or '全部'}")
    d5 = d5[d5["horizon"].astype(str) == "97"][["product_id", "pool", "physical_form",
                                                "canonical_uom", "p50", "q90", "q95", "model"]]
    d5 = d5.rename(columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
                            "p50": "p50d5", "q90": "q90d5", "q95": "q95d5", "model": "模型"})
    rows = rows.merge(d5, on=["product_id", "池", "形态", "UOM"], how="left")
    d3 = d3[d3.get("pool", "").astype(str).eq(pool)] if "pool" in d3.columns else d3.iloc[0:0]
    if len(d3):
        d3 = d3[["product_id", "pool", "physical_form", "canonical_uom",
                 "adopted_model", "holdout_wape", "demand_pattern"]].rename(
            columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
                     "adopted_model": "adopted_model", "holdout_wape": "holdout_wape"})
        rows = rows.merge(d3, on=["product_id", "池", "形态", "UOM"], how="left")
    rows = rows.head(limit)
    return rows


def _i(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def to_report(frame, branch, as_of, pack_version):
    lines = [f"# 补货决策复核 — {branch}", "",
             f"- 数据包版本：{pack_version}；as_of：{as_of}",
             "- 口径：D6 q95 需求 − C/EN/PO/SO/CG → 净需求；催已有与新补分开；未知不补 0。", ""]
    for _, r in frame.iterrows():
        action = str(r.get("建议动作"))
        new = _i(r.get("新补数量"))
        exp = _i(r.get("催已有量"))
        lines += [f"## {r['product_id']} · {r.get('形态')} · {r.get('UOM')}", "",
                  f"**结论：{action}**" + (f"；催已有 {exp}" if exp else "") +
                  (f"；新补 {new}" if new else ""), "",
                  f"- 为什么：{r.get('动作原因') or r.get('建议动作')}",
                  f"- 需要日：{r.get('需要日')}；下单日：{r.get('下单日')}；路线：{r.get('路线状态')}",
                  f"- 需求：q95 {_i(r.get('q95'))}（D5 p50/q90/q95 = "
                  f"{_i(r.get('p50d5'))}/{_i(r.get('q90d5'))}/{_i(r.get('q95d5'))}）",
                  f"- 供给：C {_i(r.get('C可发供给'))}；EN在途+待发 {_i(r.get('en_stock在途+待发'))}；"
                  f"PO {_i(r.get('PO追加(去重)'))}；SO {_i(r.get('SO已下'))}；"
                  f"CG抵扣 {_i(r.get('CG可调拨抵扣'))}",
                  f"- 净需求95：{_i(r.get('净需求95'))}",
                  f"- 模型：{r.get('模型') or r.get('adopted_model') or '未知'}；"
                  f"回测 WAPE：{r.get('holdout_wape') if pd.notna(r.get('holdout_wape')) else '—'}", ""]
    return "\n".join(lines)
