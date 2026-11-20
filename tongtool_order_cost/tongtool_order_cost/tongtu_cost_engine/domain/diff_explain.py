# -*- coding: utf-8 -*-
"""Phase 4.1 canary 差异行级解释（本地，不写 GS）。

按 item_fg 汇总新旧差，给出 Top 物料/样例行，并分类：
旧写回陈旧 / BOM 月末版本变化 / method 兜底 / disabled 物料 / 变体映射 / 旧值含包装口径。
另随机抽 10 行用 BOM 明细手算并与新值对账。
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .bom_cost import (
    METHOD_FINISHED,
    METHOD_SEMI,
    METHODS,
    SHAPE_FINISHED,
    US_OVERSEAS,
    _same_product,
    _unit_costs,
    load_bom_cost,
    load_bundles,
    load_kit_report,
    load_warehouse_map,
    warehouse_bucket,
)
from .split_merge import EnResolver, normalize_sku, sku_shape, is_non_product_accessory

COLS = ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本")
REASONS = (
    "method 兜底", "disabled 物料", "变体映射", "旧值含包装口径",
    "BOM 月末版本变化", "旧写回陈旧", "未解释",
)


def _num(v) -> float | None:
    s = str(v).strip() if v is not None else ""
    if s in ("", "nan", "None", "NULL"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _text(v) -> str:
    return str(v).strip() if v is not None else ""


def _key(row: Mapping) -> tuple[str, str, str]:
    return (
        _text(row.get("订单号")),
        normalize_sku(row.get("平台SKU_统一") or row.get("平台SKU")),
        normalize_sku(row.get("通途SKU")),
    )


def _keyed(rows: Sequence[Mapping]) -> list[tuple[str, Mapping]]:
    counter: Counter = Counter()
    out = []
    for row in rows:
        base = "|".join(_key(row))
        counter[base] += 1
        out.append((f"{base}#{counter[base]}", row))
    return out


def _amount_col(col: str) -> str:
    return "头程运费*数量" if col == "头程运费金额" else f"{col}*数量"


@dataclass
class ExplainResult:
    rows: list[dict]
    by_item: list[dict]
    by_reason: list[dict]
    manual: list[dict]
    summary: dict

    @property
    def coverage(self) -> float:
        return float(self.summary.get("coverage") or 0.0)


def _current_units(
    p2: Mapping,
    bom_index: Mapping[str, list[dict]],
    bundle_map: Mapping,
    kit_report: Mapping[str, dict],
    bucket: str,
) -> tuple[dict[str, float | None], str]:
    """当前 BOM/报表的单位成本（用于判断旧值是否陈旧）。"""
    item_fg = _text(p2.get("item_fg"))
    method = _text(p2.get("method"))
    if p2.get("method_source") == "kit_bundle":
        report = kit_report.get(item_fg)
        if not report:
            return {c: None for c in COLS}, ""
        rate_field = {
            "USNJ": "usnj_valuation_rate", "USTX": "ustx_valuation_rate",
            "PL": "pl_valuation_rate", US_OVERSEAS: "ustx_valuation_rate",
        }.get(bucket)
        return {
            "皮壳成本": _num(report.get("cost_fg")),
            "头程运费金额": None,
            "二次加工成本": _num(report.get(rate_field)) if rate_field else 0.0,
            "绍兴二次加工成本": (
                _num(report.get("cost_sxbzbcp")) if method == METHOD_SEMI
                else _num(report.get("cost_sxbzcp")) if method == METHOD_FINISHED else 0.0
            ),
        }, "kit"
    rows = bom_index.get(item_fg) or []
    if len(rows) != 1:
        return {c: None for c in COLS}, ""
    bom = rows[0]
    shape = SHAPE_FINISHED if p2.get("merged") else sku_shape(_text(p2.get("SKU")).split(",")[0])
    costs, reason = _unit_costs(bom, bucket, method, shape)
    if reason:
        return {c: None for c in COLS}, ""
    return {
        "皮壳成本": costs["shell"],
        "头程运费金额": costs["freight"],
        "二次加工成本": costs["processing"],
        "绍兴二次加工成本": costs["sx"],
    }, "bom"


def _prev_units(prev_rows: Mapping[str, dict], method: str, bucket: str) -> dict[str, float | None]:
    if not prev_rows:
        return {c: None for c in COLS}
    rate_field = {
        "USNJ": "美东加工成本, USNJ",
        "USTX": "美中加工成本, USTX",
        "PL": "波兰加工成本, PL",
        US_OVERSEAS: "美中加工成本, USTX",
    }.get(bucket)
    return {
        "皮壳成本": _num(prev_rows.get("皮壳成本")),
        "头程运费金额": None,
        "二次加工成本": _num(prev_rows.get(rate_field)) if rate_field else 0.0,
        "绍兴二次加工成本": (
            _num(prev_rows.get("绍兴包装半成品成本")) if method == METHOD_SEMI
            else _num(prev_rows.get("绍兴包装成品成本")) if method == METHOD_FINISHED else 0.0
        ),
    }


def explain_canary(
    canary_rows: Sequence[dict],
    canary_phase2: Sequence[Mapping],
    old_rows: Sequence[dict],
    *,
    bom_csv: str | Path,
    ref_map_csv: str | Path,
    wh_tsv: str | Path,
    bundle_map_csv: str | Path | None = None,
    kit_report_csv: str | Path | None = None,
    prev_bom_csv: str | Path | None = None,
    disabled_items: set[str] | None = None,
    bucket: str,
) -> ExplainResult:
    bom_index = load_bom_cost(bom_csv)
    resolver = EnResolver.from_items_csv(ref_map_csv)
    wh_map = load_warehouse_map(wh_tsv)
    bundle_map = load_bundles(bundle_map_csv)
    kit_report = load_kit_report(kit_report_csv)
    disabled = set(disabled_items or ())

    prev_rows: dict[str, dict] = {}
    if prev_bom_csv and Path(prev_bom_csv).exists():
        pdf = pd.read_csv(prev_bom_csv, dtype=str, low_memory=False, keep_default_na=False)
        for rec in pdf.to_dict("records"):
            for key in (_text(rec.get("产品编号")), normalize_sku(rec.get("客户物料号"))):
                if key:
                    prev_rows.setdefault(key, rec)

    old_by_key: dict[str, list[dict]] = {}
    for key, old_row in _keyed(old_rows):
        old_by_key.setdefault(key, []).append(old_row)
    keyed_canary = _keyed(canary_rows)
    rows: list[dict] = []
    for (key, row), p2 in zip(keyed_canary, canary_phase2):
        old_list = old_by_key.get(key, [])
        item_fg = _text(p2.get("item_fg"))
        method = _text(p2.get("method"))
        method_source = _text(p2.get("method_source"))
        status = _text(row.get("cost_status"))
        bucket_row = warehouse_bucket(wh_map.get(_text(row.get("发货仓库")), "")) or bucket
        current, current_src = _current_units(p2, bom_index, bundle_map, kit_report, bucket_row)
        prev = _prev_units(prev_rows.get(item_fg, {}), method, bucket_row)
        old_costs = {}
        for c in COLS:
            old_total = sum(
                (_num(o.get(c)) or 0.0) * (_num(o.get("发货数量")) or 0.0) for o in old_list
            )
            old_qty = sum((_num(o.get("发货数量")) or 0.0) for o in old_list)
            old_costs[c] = (old_total, (old_total / old_qty) if old_qty else None)
        packaging = old_list[0] if old_list else {}
        for c in COLS:
            new_total = float(row.get(_amount_col(c)) or 0.0)
            old_total, old_unit = old_costs[c]
            qty_new = (
                _num(row.get("cost_qty")) or _num(row.get("pieces"))
                or _num(row.get("发货数量")) or 1.0
            )
            new_unit = new_total / qty_new if qty_new else None
            diff = round(new_total - old_total, 6)
            if abs(diff) <= 0.01:
                reason = ""
            elif status == "excluded_non_product" or "非商品配件" in _text(row.get("derived_reason")):
                reason = "非商品配件"
            elif method_source == "item_group_fallback":
                reason = "method 兜底"
            elif item_fg in disabled:
                reason = "disabled 物料"
            elif old_list and resolver.items_for_sku(_text(old_list[0].get("通途SKU"))) and (
                set(resolver.items_for_sku(_text(old_list[0].get("通途SKU")))) != {item_fg}
            ):
                reason = "变体映射"
            elif c == "皮壳成本" and old_list and (
                abs((old_unit or -1) - (_num(packaging.get("皮壳含包装成本")) or -1)) <= 0.01
                or abs((old_unit or -1) - (_num(packaging.get("皮壳不含包装成本")) or -1)) <= 0.01
            ) and abs((new_unit or -1) - (current[c] if current[c] is not None else -2)) > 0.01:
                reason = "旧值含包装口径"
            elif old_unit is not None and prev.get(c) is not None and abs(old_unit - prev[c]) <= 0.01 \
                    and (current[c] is None or abs(old_unit - current[c]) > 0.01):
                reason = "BOM 月末版本变化"
            elif old_unit is not None and current[c] is not None and abs(old_unit - current[c]) > 0.01 \
                    and new_unit is not None and abs(new_unit - current[c]) <= 0.01:
                reason = "旧写回陈旧"
            else:
                reason = "未解释"
            rows.append({
                "key": key, "item_fg": item_fg, "method": method, "column": c,
                "old_total": round(old_total, 6), "new_total": round(new_total, 6),
                "diff": diff, "reason": reason,
                "old_unit": old_unit, "new_unit": new_unit,
                "current_unit": current.get(c), "prev_unit": prev.get(c),
                "method_source": method_source, "status": status,
            })

    # 按物料 Top
    item_map: dict[tuple[str, str], dict] = {}
    for r in rows:
        k = (r["item_fg"], r["reason"])
        item = item_map.setdefault(k, {
            "item_fg": r["item_fg"], "reason": r["reason"], "rows": 0,
            **{f"diff_{c}": 0.0 for c in COLS}, "sample_key": r["key"],
        })
        item["rows"] += 1
        item[f"diff_{r['column']}"] += r["diff"]
    by_item = []
    for item in item_map.values():
        item["abs_diff"] = round(sum(abs(item[f"diff_{c}"]) for c in COLS), 6)
        by_item.append(item)
    by_item.sort(key=lambda x: -x["abs_diff"])

    # 按原因
    reason_rows: dict[str, dict] = {
        reason: {"reason": reason, "rows": 0, **{f"diff_{c}": 0.0 for c in COLS}}
        for reason in REASONS
    }
    total_abs = sum(abs(r["diff"]) for r in rows) or 1.0
    for r in rows:
        reason = r["reason"] or "无差异"
        entry = reason_rows.setdefault(reason, {
            "reason": reason, "rows": 0, **{f"diff_{c}": 0.0 for c in COLS},
        })
        entry["rows"] += 1
        entry[f"diff_{r['column']}"] += r["diff"]
    by_reason = []
    for reason, entry in reason_rows.items():
        abs_diff = sum(abs(entry[f"diff_{c}"]) for c in COLS)
        entry["abs_diff"] = round(abs_diff, 6)
        entry["share"] = round(abs_diff / total_abs, 6)
        by_reason.append(entry)
    by_reason.sort(key=lambda x: -x["abs_diff"])

    # 目标解释（对应 Phase4.1 的四笔差异）
    target_specs = [
        ("皮壳成本 / method:皮壳", lambda r: r["column"] == "皮壳成本" and r["method"] == "皮壳"),
        ("成品皮壳 / method:成品", lambda r: r["column"] == "皮壳成本" and r["method"] == "成品"),
        ("二次加工 / 全部", lambda r: r["column"] == "二次加工成本"),
        ("头程运费 / 全部", lambda r: r["column"] == "头程运费金额"),
    ]
    targets = []
    for name, pred in target_specs:
        tr = [r for r in rows if pred(r)]
        t_abs = sum(abs(r["diff"]) for r in tr) or 1.0
        reasons: dict[str, dict] = {}
        for r in tr:
            rn = r["reason"] or "无差异"
            rec = reasons.setdefault(rn, {"reason": rn, "rows": 0, "diff": 0.0})
            rec["rows"] += 1
            rec["diff"] += r["diff"]
        reason_list = []
        for rec in reasons.values():
            rec["abs_diff"] = round(abs(rec["diff"]), 6)
            rec["share"] = round(rec["abs_diff"] / t_abs, 6)
            reason_list.append(rec)
        reason_list.sort(key=lambda x: -x["abs_diff"])
        item_map: dict[str, dict] = {}
        for r in tr:
            it = item_map.setdefault(r["item_fg"], {
                "item_fg": r["item_fg"], "diff": 0.0, "abs_diff": 0.0,
                "reason": r["reason"], "sample_key": r["key"],
            })
            it["diff"] += r["diff"]
            it["abs_diff"] += abs(r["diff"])
        top_items = sorted(item_map.values(), key=lambda x: -x["abs_diff"])[:20]
        explained = sum(abs(r["diff"]) for r in tr if r["reason"] not in ("未解释",))
        targets.append({
            "target": name, "total_diff": round(sum(r["diff"] for r in tr), 6),
            "total_abs_diff": round(t_abs, 6), "explained_abs_diff": round(explained, 6),
            "unexplained_abs_diff": round(t_abs - explained, 6),
            "coverage": round(explained / t_abs, 6),
            "by_reason": reason_list, "top_items": top_items,
        })

    # 随机抽 10 行手算
    candidates = [
        (i, r) for i, r in enumerate(canary_rows)
        if r.get("cost_status") == "ok"
        and canary_phase2[i].get("method_source") != "kit_bundle"
        and canary_phase2[i].get("item_fg")
    ]
    manual = []
    rng = random.Random(42)
    for i, row in rng.sample(candidates, min(10, len(candidates))):
        p2 = canary_phase2[i]
        bucket_row = warehouse_bucket(wh_map.get(_text(row.get("发货仓库")), "")) or bucket
        current, src = _current_units(p2, bom_index, bundle_map, kit_report, bucket_row)
        units = _num(row.get("cost_qty")) or 1.0
        for c in COLS:
            new_unit = _num(row.get(c))
            bom_unit = current.get(c)
            ok = new_unit is not None and bom_unit is not None and abs(new_unit - bom_unit) <= 0.01
            manual.append({
                "订单号": row.get("订单号"), "item_fg": p2.get("item_fg"),
                "column": c, "new_unit": new_unit, "bom_unit": bom_unit, "pass": ok,
            })

    explained_abs = sum(
        abs(r["diff"]) for r in rows if r["reason"] not in ("未解释",)
    )
    coverage = explained_abs / total_abs
    summary = {
        "rows": len(rows), "total_abs_diff": round(total_abs, 6),
        "explained_abs_diff": round(explained_abs, 6),
        "unexplained_abs_diff": round(total_abs - explained_abs, 6),
        "coverage": round(coverage, 6),
        "manual_rows": len({(m["订单号"], m["item_fg"]) for m in manual}),
        "manual_pass": sum(1 for m in manual if m["pass"]),
        "manual_total": len(manual),
        "by_reason": by_reason,
        "targets": targets,
    }
    return ExplainResult(rows=rows, by_item=by_item, by_reason=by_reason,
                         manual=manual, summary=summary)


def write_explain_xlsx(result: ExplainResult, path: str | Path) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([{k: v for k, v in result.summary.items() if k != "by_reason"}]).to_excel(
            writer, sheet_name="汇总", index=False)
        pd.DataFrame(result.by_item[:20]).to_excel(writer, sheet_name="按物料Top", index=False)
        pd.DataFrame(result.by_reason).to_excel(writer, sheet_name="按原因", index=False)
        target_reason_rows = []
        target_item_rows = []
        for t in result.summary.get("targets", []):
            for rc in t["by_reason"]:
                target_reason_rows.append({"目标": t["target"], **rc})
            for it in t["top_items"]:
                target_item_rows.append({"目标": t["target"], **it})
        pd.DataFrame(target_reason_rows).to_excel(writer, sheet_name="目标解释", index=False)
        pd.DataFrame(target_item_rows).to_excel(writer, sheet_name="目标物料Top", index=False)
        pd.DataFrame(result.manual).to_excel(writer, sheet_name="抽样手算", index=False)
        pd.DataFrame([r for r in result.rows if r["reason"] == "未解释"]).to_excel(
            writer, sheet_name="未解释", index=False)


def render_explain_md(result: ExplainResult) -> str:
    s = result.summary
    lines = [
        "# Canary 差异解释",
        "",
        f"- 总绝对差: {s['total_abs_diff']:g}；已解释 {s['explained_abs_diff']:g}；"
        f"未解释 {s['unexplained_abs_diff']:g}；覆盖率 **{s['coverage']:.2%}**",
        f"- 随机手算: {s['manual_pass']}/{s['manual_total']} 通过（{s['manual_rows']} 行）",
        "",
        "## 按原因",
        "",
        "| 原因 | 行数 | 皮壳 | 头程 | 二次 | 绍兴二次 | 绝对差 | 占比 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in result.by_reason:
        lines.append(
            f"| {r['reason']} | {r['rows']} | {r['diff_皮壳成本']:g} | "
            f"{r['diff_头程运费金额']:g} | {r['diff_二次加工成本']:g} | "
            f"{r['diff_绍兴二次加工成本']:g} | {r['abs_diff']:g} | {r['share']:.1%} |"
        )
    lines += ["", "## 目标解释", ""]
    for t in s.get("targets", []):
        lines.append(f"### {t['target']}（总差 {t['total_diff']:g}，覆盖率 {t['coverage']:.1%}）")
        lines.append("")
        lines.append("| 原因 | 行数 | 金额 | 占比 |")
        lines.append("|---|---:|---:|---:|")
        for rc in t["by_reason"]:
            lines.append(f"| {rc['reason']} | {rc['rows']} | {rc['diff']:g} | {rc['share']:.1%} |")
        lines.append("")
        lines.append("Top 物料：")
        for it in t["top_items"][:5]:
            lines.append(f"- {it['item_fg']}: {it['diff']:g}（{it['reason']}，样例 {it['sample_key']}）")
        lines.append("")
    lines += ["## 物料差异 Top 20（总）", "", "| item_fg | 原因 | 皮壳 | 头程 | 二次 | 绍兴二次 |",
              "|---|---|---:|---:|---:|---:|"]
    for r in result.by_item[:20]:
        lines.append(
            f"| {r['item_fg']} | {r['reason']} | {r['diff_皮壳成本']:g} | "
            f"{r['diff_头程运费金额']:g} | {r['diff_二次加工成本']:g} | "
            f"{r['diff_绍兴二次加工成本']:g} |"
        )
    lines.append("")
    return "\n".join(lines)
