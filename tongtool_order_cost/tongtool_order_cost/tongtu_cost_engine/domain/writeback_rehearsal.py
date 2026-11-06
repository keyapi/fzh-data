# -*- coding: utf-8 -*-
"""Phase 3.0 写回演练（本地，不写 GS）。

- 模板：现有写回表 166 列表头（按列名合同，原样输出）。
- 行集合：Phase1 合并明细（合并组 1 行 + 透传原行）。
- 四列成本：Phase2 结果；skipped/blocked 行四列留空 + reason，**不沿用旧值、不填 0**。
- 非成本列：优先原始订单；缺列按 `(order_common, 平台SKU)` 从旧写回映射；
  多值冲突/无来源 → 留空并在 `unmapped_columns` 标注，不伪造。
- 成本派生列（*数量/*系数/1件产品成本/订单总成本等）不写旧值，留空。
- 血缘：每行输出 source_row/group_id/pieces/method/source，并断言 100% 可追溯。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from .bom_cost import Phase2Result
from .split_merge import (
    SHAPE_COVER,
    Assertion,
    MergeShadowResult,
    normalize_sku,
    sku_base,
    sku_shape,
)

PRIMARY_COST_COLUMNS: tuple[str, ...] = (
    "皮壳成本",
    "头程运费金额",
    "二次加工成本",
    "绍兴二次加工成本",
)

# 由四列/数量派生的旧成本列：Phase3 不写旧值，避免与 Phase2 口径打架。
COST_DERIVED_COLUMNS: tuple[str, ...] = (
    "皮壳成本*数量",
    "绍兴二次加工成本*数量",
    "二次加工成本*数量",
    "头程运费*数量",
    "1件产品成本",
    "产品成本*数量",
    "订单总成本",
    "订单利润",
    "皮壳不含包装成本",
    "皮壳含包装成本",
    "皮壳不含包装成本*系数",
    "皮壳含包装成本*系数",
    "二次加工成本*系数",
    "绍兴二次加工成本*系数",
    "皮壳成本*系数",
    "皮壳成本*系数*数量",
    "二次加工成本*系数*数量",
    "绍兴二次加工成本*系数*数量",
    "1件产品成本*系数",
    "产品成本*系数*数量",
    "海外仓成本_USHWC",
    "海外仓成本",
    "海外仓成本*数量",
    "订单总成本*系数",
    "订单利润*系数",
    "EN绍兴包装半成品成本",
    "EN绍兴包装成品成本",
)

DERIVED_FILL_COLUMNS: tuple[str, ...] = (
    "皮壳成本*数量",
    "头程运费*数量",
    "二次加工成本*数量",
    "绍兴二次加工成本*数量",
    "1件产品成本",
    "产品成本*数量",
)
DERIVED_OPTIONAL_COLUMNS: tuple[str, ...] = ("订单总成本", "订单利润")

EXTRA_COLUMNS: tuple[str, ...] = (
    "source_row",
    "group_id",
    "merged",
    "cost_qty",
    "pieces",
    "method",
    "method_source",
    "bundle_version",
    "kit_method",
    "kit_report_diff",
    "source",
    "cost_status",
    "cost_reason",
    "derived_reason",
    "suggested_items",
    "revenue_available",
    "lineage_status",
    "mapping_status",
    "unmapped_columns",
)


@dataclass
class WritebackRehearsal:
    month: str
    template_columns: list[str]
    rows: list[dict]
    assertions: list[Assertion]
    stats: dict
    diff_breakdown: list[dict]
    mapping_comparison: list[dict]

    @property
    def ok(self) -> bool:
        return all(a.status != "fail" for a in self.assertions)


def _nonempty(v: object) -> str:
    return str(v).strip() if v is not None else ""


def _to_float(value: object) -> float | None:
    text = str(value).strip() if value is not None else ""
    if text in ("", "nan", "None", "NULL"):
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _source_indices(value: object) -> list[int]:
    return [int(x) for x in str(value).split(",") if str(x).strip()]


PRODUCT_LEVEL_COLUMNS: tuple[str, ...] = ("产品发售日期", "当月是否新品", "件套")


def _wb_index(old: pd.DataFrame) -> tuple[dict, dict, dict]:
    by_group: dict[tuple[str, str], list[dict]] = {}
    by_row: dict[tuple[str, str], list[dict]] = {}
    by_product: dict[str, list[dict]] = {}
    for rec in old.to_dict("records"):
        group_key = (
            _nonempty(rec.get("订单号_公共部分")),
            normalize_sku(rec.get("平台SKU_统一") or rec.get("平台SKU")),
        )
        row_key = (_nonempty(rec.get("订单号")), normalize_sku(rec.get("通途SKU")))
        by_group.setdefault(group_key, []).append(rec)
        by_row.setdefault(row_key, []).append(rec)
        product_key = _nonempty(rec.get("品类尺寸面料编码"))
        if product_key:
            by_product.setdefault(product_key, []).append(rec)
    return by_group, by_row, by_product


def _pick_value(candidates: Sequence[dict], col: str) -> tuple[str, str]:
    """返回 (value, status)；status=ok/conflict/no_source。"""
    values = sorted({_nonempty(r.get(col)) for r in candidates if _nonempty(r.get(col))})
    if len(values) == 1:
        return values[0], "ok"
    if len(values) > 1:
        return "", "conflict"
    return "", "no_source"


def build_writeback_rehearsal(
    shadow: MergeShadowResult,
    phase2: Phase2Result,
    old_writeback_csv: str | Path,
    *,
    month: str = "",
    disabled_items: Iterable[str] | None = None,
) -> WritebackRehearsal:
    old = pd.read_csv(old_writeback_csv, dtype=str, low_memory=False, keep_default_na=False)
    template = list(old.columns)
    # 只允许有效订单行参与映射；作废原单/模板独有行不得把运费、身份带进有效子单
    valid_ids = {r.order_id for r in shadow.rows}
    old_active = old[old["订单号"].isin(valid_ids)]
    by_group, by_row, by_product = _wb_index(old_active)
    nonempty_cols = {
        c for c in template
        if any(_nonempty(v) for v in old[c].tolist())
    }
    disabled = set(disabled_items or ())
    by_index = {r.index: r for r in shadow.rows}
    # 模板运费池：同一 (订单号, 通途SKU) 可能多行，按出现次数消费
    freight_pool: dict[tuple[str, str], list[str]] = {}
    for rec in old_active.to_dict("records"):
        key = (_nonempty(rec.get("订单号")), normalize_sku(rec.get("通途SKU")))
        freight_pool.setdefault(key, []).append(_nonempty(rec.get("运费")))
    freight_used: dict[tuple[str, str], int] = defaultdict(int)

    rows: list[dict] = []
    for detail, p2 in zip(shadow.detail_rows, phase2.rows):
        out = {c: "" for c in template}
        for col in template:
            val = _nonempty(detail.get(col))
            if val:
                out[col] = val

        merged = bool(detail.get("merged"))
        order_common = _nonempty(detail.get("order_common"))
        platform_sku = normalize_sku(detail.get("platform_sku"))
        sku = normalize_sku(detail.get("通途SKU"))
        out["订单号_公共部分"] = order_common
        out["平台SKU_统一"] = platform_sku
        out["需要合并"] = "TRUE" if merged else "FALSE"
        out["包含包裹"] = "TRUE" if merged else "FALSE"
        out["merge_group"] = _nonempty(detail.get("group_id"))
        out["通途SKU_公共部分"] = sku_base(sku)
        out["sku_base"] = sku_base(sku)

        src_idx = _source_indices(detail.get("source_rows", ""))
        src_rows = [by_index[i] for i in src_idx if i in by_index]
        # 运费：按源行从模板逐行取（同一键可多行，按出现顺序消费）。
        # 合并组必须把组件行的尾程运费求和到载体行，否则中间表会少计。
        freight_sum = 0.0
        freight_found = False
        for src in src_rows:
            key = (src.order_id, src.sku)
            values = freight_pool.get(key, [])
            idx_used = freight_used[key]
            if idx_used < len(values):
                value = _to_float(values[idx_used])
                freight_used[key] = idx_used + 1
                if value is not None:
                    freight_sum += value
                    freight_found = True
        if freight_found:
            freight_text = f"{freight_sum:.6f}".rstrip("0").rstrip(".")
            out["运费"] = freight_text if merged else (out.get("运费") or freight_text)
        # 原始订单：同一组内任一源行有值即带出（唯一才用，冲突留待旧写回/留空）
        for col in template:
            if col in PRIMARY_COST_COLUMNS or col in COST_DERIVED_COLUMNS:
                continue
            if out[col]:
                continue
            values = sorted({_nonempty(r.raw.get(col)) for r in src_rows if _nonempty(r.raw.get(col))})
            if len(values) == 1:
                out[col] = values[0]

        # 是否皮壳：由 EN method / 源行 SKU 形态推出，皮壳行不得为空
        method_value = _nonempty(detail.get("pricing_method"))
        is_shell = method_value == "皮壳" or (
            not method_value and any(sku_shape(r.sku) == SHAPE_COVER for r in src_rows)
        )
        # 合同要求该列不能空：皮壳行="皮壳"，非皮壳="否"
        out["是否皮壳"] = "皮壳" if is_shell else "否"

        # 缺列一律优先按 (order_common, 平台SKU) 映射；仅当组键无行时才回退精确行键
        candidates = by_group.get((order_common, platform_sku), [])
        direct_candidates = by_row.get((_nonempty(detail.get("订单号")), sku), [])
        if not candidates:
            candidates = direct_candidates

        unmapped: list[str] = []
        for col in template:
            if col in PRIMARY_COST_COLUMNS or col in COST_DERIVED_COLUMNS:
                continue
            if out[col]:
                continue
            if col not in nonempty_cols:
                continue
            value, status = _pick_value(candidates, col)
            if status != "ok" and direct_candidates is not candidates:
                value, status = _pick_value(direct_candidates, col)
            if status == "ok":
                out[col] = value
            else:
                unmapped.append(f"{col}:{status}")

        # 产品级属性兜底：产品发售日期/当月是否新品/件套 同一产品应一致
        product_key = _nonempty(out.get("品类尺寸面料编码"))
        if product_key:
            for col in PRODUCT_LEVEL_COLUMNS:
                if out.get(col):
                    continue
                value, status = _pick_value(by_product.get(product_key, []), col)
                if status == "ok":
                    out[col] = value

        # 运费兜底：只有模板完全没有该行时，才用原始订单包裹总运费（行总额）。
        # 合并组只要任一源行命中模板，就不能再加兜底，否则会把组件运费重复计。
        if not out.get("运费") and not freight_found:
            pkg_values = [
                _to_float(r.raw.get("包裹总运费")) for r in src_rows
                if _nonempty(r.raw.get("包裹总运费"))
            ]
            pkg_values = [v for v in pkg_values if v is not None]
            if pkg_values:
                out["运费"] = f"{sum(pkg_values):.6f}".rstrip("0").rstrip(".")
        # suffix / 件套：原始订单/旧写回都没有时，从平台SKU/产品名推导
        if not out.get("suffix"):
            import re
            m = re.search(r"-(\d{1,3})$", platform_sku)
            if m:
                out["suffix"] = m.group(1)
        if not out.get("件套"):
            import re
            text = f"{platform_sku} {_nonempty(detail.get('产品名称'))}"
            m = re.search(r"SET(\d+)", text, re.IGNORECASE)
            if m:
                out["件套"] = f"SET{int(m.group(1))}"
        # 已通过其他来源补上的列，不再列为未映射
        unmapped = [u for u in unmapped if not out.get(u.split(":")[0])]

        status = str(p2.get("status") or "blocked")
        cost_qty = (
            _to_float(detail.get("pieces")) if merged else _to_float(detail.get("发货数量"))
        ) or 0.0
        if merged:
            out["发货数量"] = f"{cost_qty:g}"  # 合并行数量 = pieces
        derived_reason: list[str] = []
        revenue_available = False
        for col in COST_DERIVED_COLUMNS:
            if col in out:
                out[col] = ""

        if status in ("non_product_accessory", "component_absorbed"):
            for col in PRIMARY_COST_COLUMNS:
                out[col] = "0"
            for col in DERIVED_FILL_COLUMNS:
                if col in out:
                    out[col] = "0"
            for col in DERIVED_OPTIONAL_COLUMNS:
                if col in out:
                    out[col] = ""
            derived_reason.append(
                "非商品配件：零成本，不参与订单成本"
                if status == "non_product_accessory"
                else "组件已并入同订单皮壳/成品成本：零成本"
            )
        elif status == "pending_bundle":
            for col in PRIMARY_COST_COLUMNS:
                out[col] = ""
            for col in (*DERIVED_FILL_COLUMNS, *DERIVED_OPTIONAL_COLUMNS):
                if col in out:
                    out[col] = ""
            derived_reason.append("套件待审：未展开")
        elif status == "ok" and cost_qty > 0:
            units: dict[str, float] = {}
            for col in PRIMARY_COST_COLUMNS:
                total = _to_float(p2.get(col))
                if total is None:
                    status = "blocked"
                    derived_reason.append(f"{col}:phase2缺失")
                    break
                units[col] = total / cost_qty
                out[col] = f"{units[col]:.6f}".rstrip("0").rstrip(".")
            if status == "ok":
                for col, unit in units.items():
                    derived_col = "头程运费*数量" if col == "头程运费金额" else f"{col}*数量"
                    if derived_col in out:
                        out[derived_col] = f"{unit * cost_qty:g}"
                one_piece = units["皮壳成本"] + units["绍兴二次加工成本"] + units["二次加工成本"]
                out["1件产品成本"] = f"{one_piece:.6f}".rstrip("0").rstrip(".")
                out["产品成本*数量"] = f"{one_piece * cost_qty:g}"
                freight_total = _to_float(out.get("运费"))
                if freight_total is None:
                    derived_reason.append("订单总成本:运费未映射")
                    derived_reason.append("订单利润:订单总成本不可得")
                else:
                    # 运费是行总额（不乘数量）；海外仓成本是单位成本（乘数量）
                    overseas_unit = _to_float(out.get("海外仓成本")) or 0.0
                    order_total = (sum(units.values()) + overseas_unit) * cost_qty + freight_total
                    out["订单总成本"] = f"{order_total:g}"
                    revenue_values = [
                        _to_float(by_index[i].raw.get("收入(人民币)"))
                        for i in _source_indices(detail.get("source_rows", ""))
                        if i in by_index
                    ]
                    revenue_values = [v for v in revenue_values if v is not None]
                    if revenue_values:
                        revenue_available = True
                        out["订单利润"] = f"{sum(revenue_values) - order_total:g}"
                    else:
                        derived_reason.append("订单利润:收入不可得")
        else:
            for col in PRIMARY_COST_COLUMNS:
                out[col] = ""
            for col in (*DERIVED_FILL_COLUMNS, *DERIVED_OPTIONAL_COLUMNS):
                if col in out:
                    out[col] = ""
            derived_reason.append(
                "成本阻断" if status == "blocked" else "成本跳过（Phase1 不可定价）"
            )

        out.update({
            "source_row": ",".join(
                str(i) for i in _source_indices(detail.get("source_rows", ""))
            ),
            "group_id": _nonempty(detail.get("group_id")),
            "merged": merged,
            "pieces": _nonempty(detail.get("pieces")),
            "cost_qty": f"{cost_qty:g}",
            "method": _nonempty(detail.get("pricing_method")) or _nonempty(p2.get("method")),
            "method_source": _nonempty(p2.get("method_source")) or _nonempty(detail.get("method_source")),
            "bundle_version": _nonempty(p2.get("bundle_version")),
            "kit_method": _nonempty(p2.get("kit_method")),
            "kit_report_diff": _nonempty(p2.get("kit_report_diff")),
            "source": _nonempty(p2.get("source")),
            "cost_status": status,
            "cost_reason": "" if status == "ok" else _nonempty(
                p2.get("reason") or detail.get("cost_blocked_reason")
            ),
            "derived_reason": "|".join(derived_reason),
            "suggested_items": _nonempty(p2.get("suggested_items")),
            "revenue_available": "是" if revenue_available else "否",
            "lineage_status": (
                "ok" if _nonempty(detail.get("source_rows")) and (not merged or _nonempty(detail.get("group_id")))
                else "bad"
            ),
            "mapping_status": "ok" if not unmapped else "partial",
            "unmapped_columns": "|".join(unmapped),
        })
        rows.append(out)

    assertions = [
        _assert_template(template),
        _assert_rows(shadow, rows),
        _assert_lineage(shadow, rows),
        _assert_cost_blanks(rows),
        _assert_per_unit(rows, phase2.rows),
        _assert_one_piece(rows),
        _assert_conservation(rows, old, shadow),
        _assert_key_columns(rows),
        _assert_derived_rates(rows),
    ]
    stats = _stats(rows, phase2, shadow)
    by_name = {a.name: a for a in assertions}
    stats["per_unit_fail_rows"] = len(by_name["per_unit×数量=Phase2合计"].violations)
    stats["one_piece_fail_rows"] = len(by_name["1件成本=四列(除头程)之和"].violations)
    stats["assertion_status"] = {a.name: a.status for a in assertions}
    breakdown = _diff_breakdown(phase2, disabled)
    comparison = []
    for col in template:
        old_n = sum(1 for v in old[col].tolist() if _nonempty(v))
        new_n = sum(1 for r in rows if _nonempty(r.get(col)))
        comparison.append({
            "列": col, "旧写回非空": old_n, "新输出非空": new_n,
            "变化": new_n - old_n, "新输出空白": len(rows) - new_n,
        })
    comparison.sort(key=lambda x: (-x["变化"], x["列"]))
    return WritebackRehearsal(
        month=month,
        template_columns=template,
        rows=rows,
        assertions=assertions,
        stats=stats,
        diff_breakdown=breakdown,
        mapping_comparison=comparison,
    )


def _assert_template(template: Sequence[str]) -> Assertion:
    dup = sorted({c for c in template if list(template).count(c) > 1})
    return Assertion(
        name="166 列合同",
        status="fail" if dup else "pass",
        checked=len(template),
        detail=f"模板 {len(template)} 列；重复列 {dup or '无'}",
        violations=[{"duplicate": c} for c in dup],
    )


def _assert_rows(shadow: MergeShadowResult, rows: Sequence[dict]) -> Assertion:
    ok = len(rows) == len(shadow.detail_rows)
    return Assertion(
        name="行集合=Phase1合并明细",
        status="pass" if ok else "fail",
        checked=len(rows),
        detail=f"输出 {len(rows)} 行；Phase1 明细 {len(shadow.detail_rows)} 行",
        violations=[] if ok else [{"rows": len(rows), "detail": len(shadow.detail_rows)}],
    )


def _assert_lineage(shadow: MergeShadowResult, rows: Sequence[dict]) -> Assertion:
    violations: list[dict] = []
    seen: Counter = Counter()
    for row in rows:
        idxs = _source_indices(row.get("source_row", ""))
        for i in idxs:
            seen[i] += 1
        if not idxs:
            violations.append({"group_id": row.get("group_id"), "reason": "source_row 为空"})
        if row.get("merged") and not row.get("group_id"):
            violations.append({"reason": "合并行无 group_id", "source_row": row.get("source_row")})
        if not row.get("merged") and len(idxs) != 1:
            violations.append({"reason": "透传行 source_row 不为 1", "source_row": row.get("source_row")})
    expected = {r.index for r in shadow.rows}
    if set(seen) != expected:
        violations.append({
            "reason": "源行未完整消费",
            "missing": sorted(expected - set(seen))[:20],
            "unknown": sorted(set(seen) - expected)[:20],
        })
    dup = [i for i, n in seen.items() if n > 1]
    if dup:
        violations.append({"reason": "源行被多行消费", "rows": sorted(dup)[:20]})
    return Assertion(
        name="100% 可追溯",
        status="fail" if violations else "pass",
        checked=len(rows),
        detail=f"{len(rows)} 行均带 source_row；源行 {len(expected)} 条各消费一次",
        violations=violations,
    )


def _assert_cost_blanks(rows: Sequence[dict]) -> Assertion:
    violations: list[dict] = []
    for row in rows:
        status = row.get("cost_status")
        vals = [row.get(c, "") for c in PRIMARY_COST_COLUMNS]
        filled = [v for v in vals if _nonempty(v)]
        if status == "ok":
            if len(filled) != 4:
                violations.append({"group_id": row.get("group_id"), "reason": "定价行四列不全"})
        elif status in ("non_product_accessory", "component_absorbed"):
            if any(v != "0" for v in vals):
                violations.append({"group_id": row.get("group_id"), "reason": "零成本行四列不为 0"})
        else:
            if filled:
                violations.append({
                    "group_id": row.get("group_id"),
                    "reason": "阻断/跳过行四列未留空",
                    "values": vals,
                })
    return Assertion(
        name="四列口径（阻断留空、不填0）",
        status="fail" if violations else "pass",
        checked=len(rows),
        detail=f"{len(rows)} 行：定价行四列齐全；阻断/跳过行四列留空",
        violations=violations[:50],
    )


def _assert_per_unit(rows: Sequence[dict], p2_rows: Sequence[dict]) -> Assertion:
    violations: list[dict] = []
    checked = 0
    for row, p2 in zip(rows, p2_rows):
        if row.get("cost_status") != "ok":
            continue
        qty = _to_float(row.get("cost_qty")) or 0.0
        for col in PRIMARY_COST_COLUMNS:
            unit = _to_float(row.get(col))
            total = _to_float(p2.get(col))
            if unit is None or total is None or qty <= 0:
                violations.append({"group_id": row.get("group_id"), "列": col, "reason": "缺值"})
                continue
            checked += 1
            if abs(unit * qty - total) > 0.01:
                violations.append({
                    "group_id": row.get("group_id"), "列": col,
                    "unit": unit, "qty": qty,
                    "unit×qty": round(unit * qty, 6), "phase2": total,
                })
    return Assertion(
        name="per_unit×数量=Phase2合计",
        status="fail" if violations else "pass",
        checked=checked,
        detail=f"{checked} 个 单位×数量 校验；容差 0.01",
        violations=violations[:50],
    )


def _assert_one_piece(rows: Sequence[dict]) -> Assertion:
    violations: list[dict] = []
    checked = 0
    for row in rows:
        if row.get("cost_status") != "ok":
            continue
        one = _to_float(row.get("1件产品成本"))
        shell = _to_float(row.get("皮壳成本"))
        sx = _to_float(row.get("绍兴二次加工成本"))
        proc = _to_float(row.get("二次加工成本"))
        if None in (one, shell, sx, proc):
            violations.append({"group_id": row.get("group_id"), "reason": "缺值"})
            continue
        checked += 1
        if abs(one - (shell + sx + proc)) > 0.01:
            violations.append({
                "group_id": row.get("group_id"),
                "1件": one, "sum": round(shell + sx + proc, 6),
            })
    return Assertion(
        name="1件成本=四列(除头程)之和",
        status="fail" if violations else "pass",
        checked=checked,
        detail=f"{checked} 个定价行校验；容差 0.01",
        violations=violations[:50],
    )


KEY_MAPPING_COLUMNS: tuple[str, ...] = (
    "是否皮壳", "运费", "suffix", "件套", "当月是否新品",
    "虚拟跟踪号", "物流商单号", "产品发售日期",
)


def _assert_conservation(
    rows: Sequence[dict], old: pd.DataFrame, shadow: MergeShadowResult,
) -> Assertion:
    """合并前后销售额与尾程运费必须守恒。

    - 销售额：以有效源行（shadow.rows）为基准；
    - 运费：以模板按源行逐行消费为基准（同一键多行按出现顺序），
      模板完全没有该行时才允许用「包裹总运费」兜底。
    """
    by_index = {r.index: r for r in shadow.rows}
    valid_ids = {r.order_id for r in shadow.rows}
    cols = (
        {c: (c in rows[0]) for c in ("售价", "售价(人民币)", "运费")}
        if rows else {c: False for c in ("售价", "售价(人民币)", "运费")}
    )
    pool: dict[tuple[str, str], list[float | None]] = defaultdict(list)
    for rec in old.to_dict("records"):
        if _nonempty(rec.get("订单号")) not in valid_ids:
            continue
        key = (_nonempty(rec.get("订单号")), normalize_sku(rec.get("通途SKU")))
        pool[key].append(_to_float(rec.get("运费")))
    used: dict[tuple[str, str], int] = defaultdict(int)
    expected_freight = 0.0
    for detail in shadow.detail_rows:
        found = False
        for i in _source_indices(detail.get("source_rows", "")):
            src = by_index.get(i)
            if src is None:
                continue
            key = (src.order_id, src.sku)
            values = pool.get(key, [])
            if used[key] < len(values):
                value = values[used[key]]
                used[key] += 1
                if value is not None:
                    expected_freight += value
                    found = True
        if not found:
            expected_freight += sum(
                _to_float(src.raw.get("包裹总运费")) or 0.0
                for i in _source_indices(detail.get("source_rows", ""))
                for src in (by_index.get(i),)
                if src is not None and _nonempty(src.raw.get("包裹总运费"))
            )
    t_sale = sum(r.sale for r in shadow.rows)
    t_sale_cny = sum(r.sale_cny for r in shadow.rows)
    n_sale = sum(_to_float(r.get("售价")) or 0.0 for r in rows) if cols.get("售价") else 0.0
    n_sale_cny = (
        sum(_to_float(r.get("售价(人民币)")) or 0.0 for r in rows) if cols.get("售价(人民币)") else 0.0
    )
    n_freight = sum(_to_float(r.get("运费")) or 0.0 for r in rows) if cols.get("运费") else 0.0
    diffs = {}
    if cols.get("售价"):
        diffs["售价"] = round(n_sale - t_sale, 4)
    if cols.get("售价(人民币)"):
        diffs["售价(人民币)"] = round(n_sale_cny - t_sale_cny, 4)
    if cols.get("运费"):
        diffs["运费"] = round(n_freight - expected_freight, 4)
    bad = {k: v for k, v in diffs.items() if abs(v) > 0.01}
    detail = (
        f"售价 {t_sale:.2f}→{n_sale:.2f}；售价(人民币) {t_sale_cny:.2f}→{n_sale_cny:.2f}；"
        f"运费（源行模板合计） {expected_freight:.2f}→{n_freight:.2f}"
    )
    return Assertion(
        name="销售额与尾程运费守恒",
        status="fail" if bad else "pass",
        checked=len(diffs) or 1,
        detail=detail + ("；差异 " + str(bad) if bad else "；合并前后一致"),
        violations=[{"field": k, "diff": v} for k, v in bad.items()],
    )


def _assert_key_columns(rows: Sequence[dict]) -> Assertion:
    violations: list[dict] = []
    shell_rows = [r for r in rows if r.get("method") == "皮壳"]
    for r in rows:
        if not _nonempty(r.get("是否皮壳")):
            violations.append({"group_id": r.get("group_id"), "reason": "是否皮壳 为空"})
    for r in shell_rows:
        if r.get("是否皮壳") != "皮壳":
            violations.append({"group_id": r.get("group_id"), "reason": "皮壳行 是否皮壳 不为皮壳"})
    priced = [r for r in rows if r.get("cost_status") == "ok"]
    for r in priced:
        if not _nonempty(r.get("运费")):
            violations.append({"group_id": r.get("group_id"), "reason": "定价行 运费 为空"})
    rates = {
        c: (sum(1 for r in rows if _nonempty(r.get(c))), len(rows))
        for c in KEY_MAPPING_COLUMNS
    }
    return Assertion(
        name="关键列非空率",
        status="fail" if violations else "pass",
        checked=len(rows),
        detail=(
            f"皮壳行 是否皮壳 {sum(1 for r in shell_rows if r.get('是否皮壳') == '皮壳')}/{len(shell_rows)}；"
            f"定价行 运费 {sum(1 for r in priced if _nonempty(r.get('运费')))}/{len(priced)}；"
            f"全表非空率 {rates}"
        ),
        violations=violations[:50],
    )


def _assert_derived_rates(rows: Sequence[dict]) -> Assertion:
    violations: list[dict] = []
    priced = [r for r in rows if r.get("cost_status") == "ok"]
    base_cols = (*DERIVED_FILL_COLUMNS,)
    for r in priced:
        for col in base_cols:
            if not _nonempty(r.get(col)):
                violations.append({"group_id": r.get("group_id"), "reason": f"{col} 为空"})
        if not _nonempty(r.get("订单总成本")):
            violations.append({"group_id": r.get("group_id"), "reason": "订单总成本为空"})
        if r.get("revenue_available") == "是" and not _nonempty(r.get("订单利润")):
            violations.append({"group_id": r.get("group_id"), "reason": "有收入但订单利润为空"})
    rates = {
        c: (sum(1 for r in priced if _nonempty(r.get(c))), len(priced))
        for c in (*DERIVED_FILL_COLUMNS, "订单总成本", "订单利润")
    }
    return Assertion(
        name="派生列可算率",
        status="fail" if violations else ("skip" if not priced else "pass"),
        checked=len(priced),
        detail=f"定价行派生列可算率 {rates}",
        violations=violations[:50],
    )


def _stats(rows: Sequence[dict], phase2: Phase2Result, shadow: MergeShadowResult) -> dict:
    ok = [r for r in rows if r["cost_status"] == "ok"]
    blocked = [r for r in rows if r["cost_status"] == "blocked"]
    skipped = [r for r in rows if r["cost_status"] == "skipped_ineligible"]
    zero_cost = [r for r in rows if r["cost_status"] == "non_product_accessory"]
    absorbed = [r for r in rows if r["cost_status"] == "component_absorbed"]
    pending = [r for r in rows if r["cost_status"] == "pending_bundle"]
    totals = {
        c: round(
            sum(
                float(r["头程运费*数量" if c == "头程运费金额" else f"{c}*数量"])
                for r in ok
                if _nonempty(r.get("头程运费*数量" if c == "头程运费金额" else f"{c}*数量"))
            ), 6
        )
        for c in PRIMARY_COST_COLUMNS
    }
    derived_reasons: Counter = Counter()
    for r in rows:
        for item in str(r.get("derived_reason") or "").split("|"):
            if item:
                derived_reasons[item] += 1
    unmapped_counter: Counter = Counter()
    for r in rows:
        for item in str(r.get("unmapped_columns") or "").split("|"):
            if item:
                unmapped_counter[item.split(":")[0]] += 1
    derived_blank = {
        col: sum(1 for r in rows if not _nonempty(r.get(col)))
        for col in (*DERIVED_FILL_COLUMNS, *DERIVED_OPTIONAL_COLUMNS)
    }
    key_rates = {
        c: (sum(1 for r in rows if _nonempty(r.get(c))), len(rows))
        for c in KEY_MAPPING_COLUMNS
    }
    return {
        "rows": len(rows),
        "priced": len(ok),
        "key_blank": {c: len(rows) - n for c, (n, _) in key_rates.items()},
        "key_rates": {c: f"{n}/{total}" for c, (n, total) in key_rates.items()},
        "derived_blank_counts": derived_blank,
        "derived_blank_reasons": dict(derived_reasons),
        "blocked": len(blocked),
        "skipped": len(skipped),
        "blank_cost_rows": len(blocked) + len(skipped) + len(pending),
        "zero_cost_rows": len(zero_cost),
        "absorbed_rows": len(absorbed),
        "pending_bundle_rows": len(pending),
        "totals": totals,
        "rows_with_unmapped": sum(1 for r in rows if r.get("unmapped_columns")),
        "top_unmapped": unmapped_counter.most_common(10),
        "lineage_fail": sum(1 for r in rows if r.get("lineage_status") != "ok"),
        "per_unit_fail_rows": None,
        "one_piece_fail_rows": None,
        "diff_wb_abs": phase2.stats.get("phase2_wb_abs_diff"),
        "detail_rows": len(shadow.detail_rows),
    }


def _diff_breakdown(phase2: Phase2Result, disabled: set[str]) -> list[dict]:
    buckets: dict[tuple, dict] = {}
    for row in phase2.rows:
        is_disabled = str(row.get("item_fg") or "") in disabled
        for col in PRIMARY_COST_COLUMNS:
            key = (
                col, row.get("method") or "-",
                "合并" if row.get("merged") else "透传",
                "是" if is_disabled else "否",
                row.get("status") or "-",
            )
            item = buckets.setdefault(key, {
                "列": col, "method": key[1], "合并/透传": key[2],
                "disabled": key[3], "status": key[4],
                "行数": 0, "我方合计": 0.0, "写回合计": 0.0,
                "差异(我方−写回)": 0.0, "绝对差": 0.0, "可比": True,
            })
            item["行数"] += 1
            diff = row.get(f"diff_vs_writeback_{col}")
            if diff is None:
                item["可比"] = False
                continue
            item["我方合计"] += float(row.get(col) or 0.0)
            item["写回合计"] += float(row.get(f"wb_{col}") or 0.0)
            item["差异(我方−写回)"] += float(diff)
            item["绝对差"] += abs(float(diff))
    for item in buckets.values():
        for k in ("我方合计", "写回合计", "差异(我方−写回)", "绝对差"):
            item[k] = round(item[k], 6)
    return sorted(
        buckets.values(),
        key=lambda x: (x["列"], x["method"], x["合并/透传"], x["disabled"], x["status"]),
    )


# ─────────────────────────── 输出 ───────────────────────────


def summary_rows(rehearsal: WritebackRehearsal) -> list[dict]:
    s = rehearsal.stats
    t = s["totals"]
    return [
        {"指标": "月份", "值": rehearsal.month},
        {"指标": "输出行数", "值": s["rows"]},
        {"指标": "可定价行", "值": s["priced"]},
        {"指标": "阻断行", "值": s["blocked"]},
        {"指标": "跳过行", "值": s["skipped"]},
        {"指标": "非商品配件 0 成本行", "值": s["zero_cost_rows"]},
        {"指标": "组件吸收 0 成本行", "值": s["absorbed_rows"]},
        {"指标": "套件待审行", "值": s["pending_bundle_rows"]},
        {"指标": "四列空白行", "值": s["blank_cost_rows"]},
        {"指标": "单位成本恒等失败行", "值": s["per_unit_fail_rows"]},
        {"指标": "1件成本恒等失败行", "值": s["one_piece_fail_rows"]},
        {"指标": "派生列空值数", "值": str(s["derived_blank_counts"])},
        {"指标": "派生列留空原因", "值": str(s["derived_blank_reasons"])},
        {"指标": "关键列空白数", "值": str(s["key_blank"])},
        {"指标": "关键列非空率", "值": str(s["key_rates"])},
        {"指标": "皮壳成本合计", "值": t["皮壳成本"]},
        {"指标": "头程运费合计", "值": t["头程运费金额"]},
        {"指标": "二次加工合计", "值": t["二次加工成本"]},
        {"指标": "绍兴二次加工合计", "值": t["绍兴二次加工成本"]},
        {"指标": "写回差异绝对差（仅对账）", "值": s["diff_wb_abs"]},
        {"指标": "含未映射列的行", "值": s["rows_with_unmapped"]},
        {"指标": "Top 未映射列", "值": str(s["top_unmapped"])},
        {"指标": "血缘失败行", "值": s["lineage_fail"]},
    ]


def assertion_rows(rehearsal: WritebackRehearsal) -> list[dict]:
    text = {"pass": "通过", "fail": "阻断", "skip": "跳过"}
    return [{
        "断言": a.name, "结果": text.get(a.status, a.status),
        "检查数": a.checked, "说明": a.detail,
        "违规": str(a.violations[:20]) if a.violations else "",
    } for a in rehearsal.assertions]


def write_csv(rehearsal: WritebackRehearsal, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rehearsal.rows).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_xlsx(rehearsal: WritebackRehearsal, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows(rehearsal)).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(rehearsal.rows).to_excel(writer, sheet_name="写回行", index=False)
        pd.DataFrame(rehearsal.diff_breakdown).to_excel(writer, sheet_name="差异归因", index=False)
        pd.DataFrame(mapping_gap_rows(rehearsal.rows)).to_excel(
            writer, sheet_name="映射缺口", index=False,
        )
        pd.DataFrame(rehearsal.mapping_comparison).to_excel(
            writer, sheet_name="未映射对比", index=False,
        )
        whitelist = [
            r for r in rehearsal.rows
            if r.get("cost_status") in ("blocked", "pending_bundle")
            or (
                r.get("cost_status") == "skipped_ineligible"
                and ("歧义" in str(r.get("cost_reason")) or "载体" in str(r.get("cost_reason")))
            )
        ]
        pd.DataFrame([{
            "订单号": r.get("订单号"),
            "SKU": r.get("通途SKU"),
            "cost_status": r.get("cost_status"),
            "reason": r.get("cost_reason"),
            "suggested_items": r.get("suggested_items", ""),
        } for r in whitelist]).to_excel(writer, sheet_name="待审建议白名单", index=False)
        pd.DataFrame(assertion_rows(rehearsal)).to_excel(writer, sheet_name="断言", index=False)
        blocked = [r for r in rehearsal.rows if r["cost_status"] != "ok"]
        pd.DataFrame(blocked).to_excel(writer, sheet_name="阻断清单", index=False)
    return path


def mapping_gap_rows(rows: Sequence[dict]) -> list[dict]:
    counter: Counter = Counter()
    for row in rows:
        for item in str(row.get("unmapped_columns") or "").split("|"):
            if not item:
                continue
            col, _, reason = item.partition(":")
            counter[(col, reason)] += 1
    return [
        {"列": col, "原因": reason, "行数": n}
        for (col, reason), n in counter.most_common()
    ]


def render_markdown(rehearsal: WritebackRehearsal) -> str:
    s = rehearsal.stats
    t = s["totals"]
    lines = [
        f"# 写回演练 — {rehearsal.month}",
        "",
        "> 本地演练，不写 GS。模板 = 现有写回表列合同；四列成本来自 Phase2；"
        "阻断/跳过行四列留空 + reason。",
        "",
        "## 汇总",
        "",
        f"- 输出行数：{s['rows']}（Phase1 明细 {s['detail_rows']} 行）",
        f"- 可定价：{s['priced']}；阻断：{s['blocked']}；跳过：{s['skipped']}；"
        f"非商品配件 0 成本：{s['zero_cost_rows']}；组件吸收 0 成本：{s['absorbed_rows']}；"
        f"套件待审：{s['pending_bundle_rows']}；"
        f"四列空白：{s['blank_cost_rows']}",
        f"- 单位成本恒等失败行：{s['per_unit_fail_rows']}；1件成本恒等失败行：{s['one_piece_fail_rows']}",
        f"- 派生列空值数：{s['derived_blank_counts']}",
        f"- 派生列留空原因：{s['derived_blank_reasons']}",
        f"- 关键列空白数：{s['key_blank']}",
        f"- 关键列非空率：{s['key_rates']}",
        f"- 四列合计：皮壳 {t['皮壳成本']:g} / 头程 {t['头程运费金额']:g} / "
        f"二次加工 {t['二次加工成本']:g} / 绍兴二次 {t['绍兴二次加工成本']:g}",
        "- 注：四列是 **单位成本**；`*数量`/`产品成本*数量`/`订单总成本`/`订单利润` 为按合同补齐的合计/派生值；"
        "其余旧派生列（*系数/海外仓成本等）仍留空。",
        f"- 写回差异绝对差（仅对账）：{s['diff_wb_abs']}",
        f"- 含未映射列的行：{s['rows_with_unmapped']}；Top 未映射列：{s['top_unmapped']}",
        "- 未映射对比为「旧写回非空 vs 新输出非空」；阻断/跳过行按规则留空，故订单总成本/利润非空数少于旧表。",
        f"- 血缘失败行：{s['lineage_fail']}",
        "",
        "## 断言",
        "",
        "| 断言 | 结果 | 检查数 | 说明 |",
        "|---|---|---:|---|",
    ]
    for row in assertion_rows(rehearsal):
        lines.append(f"| {row['断言']} | {row['结果']} | {row['检查数']} | {row['说明']} |")
    lines += ["", "## 未映射列前后对比（Top 10 改善）", ""]
    top_improve = [r for r in rehearsal.mapping_comparison if r["变化"] > 0][:10]
    if top_improve:
        lines.append("| 列 | 旧写回非空 | 新输出非空 | 变化 |")
        lines.append("|---|---:|---:|---:|")
        for r in top_improve:
            lines.append(f"| {r['列']} | {r['旧写回非空']} | {r['新输出非空']} | +{r['变化']} |")
    else:
        lines.append("- 无")
    whitelist = [
        r for r in rehearsal.rows
        if r.get("cost_status") in ("blocked", "pending_bundle")
        or (
            r.get("cost_status") == "skipped_ineligible"
            and ("歧义" in str(r.get("cost_reason")) or "载体" in str(r.get("cost_reason")))
        )
    ]
    lines += ["", f"## 待审/阻断与建议白名单（{len(whitelist)}）", ""]
    if whitelist:
        lines.append("| 订单号 | SKU | 状态 | 原因 | 建议候选 item_fg |")
        lines.append("|---|---|---|---|---|")
        for r in whitelist[:20]:
            lines.append(
                f"| {r.get('订单号')} | {r.get('通途SKU')} | {r.get('cost_status')} | "
                f"{r.get('cost_reason')} | {r.get('suggested_items')} |"
            )
    else:
        lines.append("- 无")
    lines += ["", "## 差异归因（Top 10 绝对差）", ""]
    top = sorted(rehearsal.diff_breakdown, key=lambda r: -r["绝对差"])[:10]
    if top:
        lines.append("| 列 | method | 合并/透传 | disabled | status | 行数 | 绝对差 |")
        lines.append("|---|---|---|---|---|---:|---:|")
        for r in top:
            lines.append(
                f"| {r['列']} | {r['method']} | {r['合并/透传']} | {r['disabled']} | "
                f"{r['status']} | {r['行数']} | {r['绝对差']} |"
            )
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)
