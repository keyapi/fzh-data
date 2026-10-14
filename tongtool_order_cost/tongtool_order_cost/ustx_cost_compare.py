# -*- coding: utf-8 -*-
"""美中 USTX 三方案成本对比（A 现状 / B1 测算表 / B2 import 重建）。

口径（用户 2026-10-14 确认）
---------------------------
- **A（现状）**：美中行直接用订单表的 皮壳成本 / 头程运费金额 / 二次加工成本 /
  绍兴二次加工成本（即 2CJG-SX 口径，二次加工成本记的是绍兴二次加工费）。
- **B1（测算表）**：在 A 基础上，只把美中行的「二次加工成本」替换为
  `测算 美中USTX二次加工成本` 的最新月度列值；该表缺该键、但 import 表可重建时
  用 B2 公式补（formula_filled）；再缺 → unmatched。
- **B2（EN 式 import 重建）**：四项全按 import 表重建——
  - 皮壳成本 = `importBOMCostList.皮壳成本` 按重量模板取 max（沿用 Colab 的 EN 聚合规则）
  - 头程运费 = import 表无来源 → 保留 A 现值
  - 二次加工成本 = `importBOMCostList.美中加工成本, USTX`（按重量模板唯一）
  - 绍兴二次加工成本 = 按 `绍兴发货方式` 取 绍兴包装半成品成本 / 绍兴包装成品成本 / 0

设计约束
--------
- **纯离线**：只吃 snapshot 冻结出来的 CSV 行，无网络、无写操作。
- **不猜**：缺列抛 ContractError；重复键 / 公式多模板 → 记 blocked_reasons，
  不取 first/last，不 fillna(0)。
- **血缘**：每个值都能追回源 sheet 与行号。

> 已知不确定性：EN 美中USTX包装工站工资拟从 167.8 降至 105（尚未调整），
> 会让 B2 的二次加工成本偏高；报告侧以 caveat 标注，不在本模块内调整。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ─────────────────────────── 列合同常量 ───────────────────────────

KEY_COL = "品类尺寸面料编码"
QTY_COL = "发货数量"
WAREHOUSE_COL = "发货仓库"
WAREHOUSE_CLASS_COL = "发货仓按销售汇总分类"
CATEGORY_COL = "品类"

# 订单表四项成本（顺序固定：皮壳 / 头程 / 二次加工 / 绍兴二次加工）
COMPONENT_COLS: tuple[str, str, str, str] = (
    "皮壳成本",
    "头程运费金额",
    "二次加工成本",
    "绍兴二次加工成本",
)
HEAD_FREIGHT_COL = "头程运费金额"

USTX_CLASS = "USTX分公司"

# import 表列
SHELL_IMPORT_SHEET = "import皮壳成本"
SHELL_IMPORT_KEY = "品类尺寸面料编码"
SHELL_IMPORT_WT = "EN重量模板物料号"

BOM_SHEET = "importBOMCostList"
BOM_WT = "重量模板, 编号"
BOM_SHIP_METHOD = "绍兴发货方式"
BOM_SHELL_COST = "皮壳成本"
BOM_USTX_COST = "美中加工成本, USTX"
BOM_SX_SEMI = "绍兴包装半成品成本"
BOM_SX_FIN = "绍兴包装成品成本"

# B1 测算表最新月度列
B1_SHEET = "测算 美中USTX二次加工成本"
B1_MONTH_COL = "二次加工成本*系数多月202411"

# 仓库映射表列
WH_SRC_SHEET = "订单发货仓库对应成本来源"
WH_SRC_WAREHOUSE = "发货仓库"
WH_SRC_CLASS = "发货仓按销售汇总分类"

# 头程表列（EN BOM 成本列表 = importBOMCostList 的超集，按重量模板给三种头程）
HEAD_FREIGHT_SHEET = "EN产品BOM成本列表20260202"
HEAD_WT_COL = "重量模板, 编号"
HEAD_METHOD_COL = "绍兴发货方式"
# 发货方式 → (头程运费列, 重量列)
HEAD_COLS = {
    "皮壳": ("头程皮壳运费, 美中USTX", "皮壳单重, (g)"),
    "半成品": ("头程半成品运费, 美中USTX", "半成品计费重量, (kg)"),
    "成品": ("头程成品运费, 美中USTX", "成品计费重量, (kg)"),
}

FORMULA_VERSION = "ustx-import-v1"

SHIP_METHOD_SHELL = "皮壳"
SHIP_METHOD_SEMI = "半成品"
SHIP_METHOD_FIN = "成品"

# 方案标签
SCENARIO_A = "A"
SCENARIO_B1 = "B1"
SCENARIO_B2 = "B2"

# 来源标记
SRC_MEASURED = "measured"
SRC_FORMULA_FILLED = "formula_filled"
SRC_IMPORT = "import"
SRC_UNMATCHED = "unmatched"
SRC_NOT_USTX = "not_ustx"
SRC_KEPT_A = "kept_a"


class ContractError(ValueError):
    """列合同不满足 —— 立即失败，不猜列。"""


# ─────────────────────────── 列合同 ───────────────────────────


@dataclass(frozen=True)
class FormulaContract:
    key_column: str
    shell_import_weight_column: str
    bom_weight_column: str
    shipping_method_column: str
    component_columns: tuple[str, str, str, str]
    b1_month_column: str
    formula_version: str


def _require(headers: Sequence[str], cols: Iterable[str], context: str) -> None:
    present = {str(h).strip() for h in headers}
    missing = [c for c in cols if c not in present]
    if missing:
        raise ContractError(f"{context} 缺少必需列: {missing}；现有列数={len(headers)}")


def validate_formula_contract(
    shell_headers: Sequence[str],
    bom_headers: Sequence[str],
    b1_headers: Sequence[str],
) -> FormulaContract:
    """三张源表列名齐备才返回合同；缺任一列立即抛 ContractError。"""
    _require(
        shell_headers,
        (SHELL_IMPORT_KEY, SHELL_IMPORT_WT, "绍兴二次加工成本"),
        SHELL_IMPORT_SHEET,
    )
    _require(
        bom_headers,
        (BOM_WT, BOM_SHIP_METHOD, BOM_SHELL_COST, BOM_USTX_COST, BOM_SX_SEMI, BOM_SX_FIN),
        BOM_SHEET,
    )
    _require(b1_headers, (KEY_COL, B1_MONTH_COL), B1_SHEET)
    return FormulaContract(
        key_column=KEY_COL,
        shell_import_weight_column=SHELL_IMPORT_WT,
        bom_weight_column=BOM_WT,
        shipping_method_column=BOM_SHIP_METHOD,
        component_columns=COMPONENT_COLS,
        b1_month_column=B1_MONTH_COL,
        formula_version=FORMULA_VERSION,
    )


# ─────────────────────────── 小工具 ───────────────────────────


def to_float(value: object) -> float | None:
    """空/非数字 → None（不把空当 0）。"""
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rows_to_dicts(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[dict[str, str]]:
    h = [str(x).strip() for x in headers]
    out: list[dict[str, str]] = []
    for r in rows:
        out.append({h[i]: (str(r[i]).strip() if i < len(r) else "") for i in range(len(h))})
    return out


# ─────────────────────────── 维表索引 ───────────────────────────


@dataclass
class BomTemplate:
    weight_template: str
    shell_cost_max: float | None
    ustx_processing: float | None
    sx_semi: float | None
    sx_fin: float | None
    ship_methods: frozenset[str]
    source_rows: tuple[int, ...]


@dataclass
class BomIndex:
    by_template: dict[str, BomTemplate]
    duplicate_keys: list[dict[str, str]]      # 重量模板在 shell 表重复且指向不同模板
    ambiguities: list[dict[str, str]]         # 同模板多个绍兴发货方式且包装成本不同


def build_shell_weight_index(
    shell_headers: Sequence[str], shell_rows: Sequence[Sequence[str]]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """品类尺寸面料编码 → EN重量模板物料号。

    同键指向**不同**重量模板 → 视为歧义：该键**不进索引**（不取首/末行），
    在返回的 dups 里逐条记录，调用方须把对应行按 `ambiguous_shell_key` 排除。
    """
    dicts = _rows_to_dicts(shell_headers, shell_rows)
    index: dict[str, str] = {}
    ambiguous: dict[str, set[str]] = {}
    for i, r in enumerate(dicts, start=2):
        key = r.get(SHELL_IMPORT_KEY, "")
        wt = r.get(SHELL_IMPORT_WT, "")
        if not key or not wt:
            continue
        if key in ambiguous:
            ambiguous[key].add(wt)
            continue
        if key in index and index[key] != wt:
            ambiguous[key] = {index.pop(key), wt}
            continue
        index.setdefault(key, wt)
    dups = [
        {"key": k, "reason": "import皮壳成本 同键不同重量模板", "values": "|".join(sorted(v))}
        for k, v in ambiguous.items()
    ]
    return index, dups


def build_bom_index(
    bom_headers: Sequence[str], bom_rows: Sequence[Sequence[str]]
) -> BomIndex:
    """按重量模板聚合 importBOMCostList；皮壳成本取 max（沿用 Colab EN 聚合）。"""
    dicts = _rows_to_dicts(bom_headers, bom_rows)
    grouped: dict[str, list[dict[str, str]]] = {}
    rows_by_wt: dict[str, list[int]] = {}
    for i, r in enumerate(dicts, start=2):
        wt = r.get(BOM_WT, "")
        if not wt:
            continue
        grouped.setdefault(wt, []).append(r)
        rows_by_wt.setdefault(wt, []).append(i)

    by_template: dict[str, BomTemplate] = {}
    ambiguities: list[dict[str, str]] = []
    for wt, group in grouped.items():
        shells = [to_float(r.get(BOM_SHELL_COST)) for r in group]
        shells = [x for x in shells if x is not None]
        ustx = {r.get(BOM_USTX_COST, "") for r in group}
        methods = {r.get(BOM_SHIP_METHOD, "") for r in group if r.get(BOM_SHIP_METHOD, "")}

        def _first_num(col: str) -> float | None:
            for r in group:
                v = to_float(r.get(col))
                if v is not None:
                    return v
            return None

        by_template[wt] = BomTemplate(
            weight_template=wt,
            shell_cost_max=max(shells) if shells else None,
            ustx_processing=_first_num(BOM_USTX_COST),
            sx_semi=_first_num(BOM_SX_SEMI),
            sx_fin=_first_num(BOM_SX_FIN),
            ship_methods=frozenset(methods),
            source_rows=tuple(rows_by_wt[wt]),
        )
        if len(methods) > 1:
            ambiguities.append(
                {
                    "weight_template": wt,
                    "reason": "同一重量模板出现多个绍兴发货方式",
                    "values": "|".join(sorted(methods)),
                }
            )
        if len(ustx) > 1:
            ambiguities.append(
                {
                    "weight_template": wt,
                    "reason": "同一重量模板 USTX 加工成本不唯一",
                    "values": "|".join(sorted(ustx)),
                }
            )
    return BomIndex(by_template=by_template, duplicate_keys=[], ambiguities=ambiguities)


def ustx_warehouses(wh_headers: Sequence[str], wh_rows: Sequence[Sequence[str]]) -> set[str]:
    """从仓库映射表取「发货仓按销售汇总分类 == USTX分公司」的仓库名集合。"""
    dicts = _rows_to_dicts(wh_headers, wh_rows)
    return {
        r.get(WH_SRC_WAREHOUSE, "")
        for r in dicts
        if r.get(WH_SRC_CLASS, "") == USTX_CLASS and r.get(WH_SRC_WAREHOUSE, "")
    }


# ─────────────────────────── 头程（按绍兴发货方式） ───────────────────────────


@dataclass
class HeadFreightIndex:
    """按重量模板 × 绍兴发货方式的头程费用（EN BOM 成本列表）。

    `resolve(wt, method)`：先取该方法对应的头程；为空则回退皮壳头程
    （用户口径：半成品应有半成品重量，缺则皮壳重量兜底）。
    """

    by_template: dict[str, dict[str, float]]
    weight_by_template: dict[str, dict[str, float]]
    source_rows: dict[str, int]

    def resolve(self, weight_template: str, ship_method: str) -> tuple[float | None, str]:
        m = self.by_template.get(weight_template)
        if not m:
            return None, ""
        v = m.get(ship_method)
        if v:
            return v, f"头程{ship_method}运费"
        v = m.get("皮壳")
        if v:
            return v, "头程皮壳运费(兜底)"
        return None, ""


def build_head_freight_index(
    en_bom_headers: Sequence[str], en_bom_rows: Sequence[Sequence[str]]
) -> HeadFreightIndex:
    """从 `EN产品BOM成本列表20260202` 建头程索引（键=重量模板，值按绍兴发货方式）。

    同模板多行取**最大**（与处理成本/皮壳成本一致）。
    """
    missing = [c for c in (HEAD_WT_COL, HEAD_METHOD_COL) if c not in [str(h).strip() for h in en_bom_headers]]
    head_cols = {m: c for m, (c, _w) in HEAD_COLS.items()}
    present = {str(h).strip() for h in en_bom_headers}
    missing += [c for c in head_cols.values() if c not in present]
    if missing:
        raise ContractError(f"{HEAD_FREIGHT_SHEET} 缺列: {missing}")

    dicts = _rows_to_dicts(en_bom_headers, en_bom_rows)
    grouped: dict[str, list[dict[str, str]]] = {}
    rows_by_wt: dict[str, list[int]] = {}
    for i, r in enumerate(dicts, start=2):
        wt = r.get(HEAD_WT_COL, "")
        if not wt:
            continue
        grouped.setdefault(wt, []).append(r)
        rows_by_wt.setdefault(wt, []).append(i)

    by_template: dict[str, dict[str, float]] = {}
    weight_by_template: dict[str, dict[str, float]] = {}
    src: dict[str, int] = {}
    for wt, group in grouped.items():
        amounts: dict[str, float] = {}
        weights: dict[str, float] = {}
        for method, (amt_col, wt_col) in HEAD_COLS.items():
            vals = [to_float(r.get(amt_col)) for r in group]
            vals = [v for v in vals if v is not None]
            if vals:
                amounts[method] = max(vals)
            wvals = [to_float(r.get(wt_col)) for r in group]
            wvals = [v for v in wvals if v is not None]
            if wvals:
                weights[method] = max(wvals)
        if amounts:
            by_template[wt] = amounts
            weight_by_template[wt] = weights
            src[wt] = rows_by_wt[wt][0]
    return HeadFreightIndex(by_template=by_template, weight_by_template=weight_by_template, source_rows=src)


# ─────────────────────────── 成本目录 ───────────────────────────


@dataclass
class CostCatalogResult:
    rows: dict[str, dict] = field(default_factory=dict)
    unmatched: list[dict] = field(default_factory=list)
    duplicate_keys: list[dict] = field(default_factory=list)
    formula_checks: list[dict] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)


def _ship_method_for(methods: frozenset[str]) -> str:
    """按 半成品 > 成品 > 皮壳 优先级归一；空集按皮壳。"""
    if SHIP_METHOD_SEMI in methods:
        return SHIP_METHOD_SEMI
    if SHIP_METHOD_FIN in methods:
        return SHIP_METHOD_FIN
    return SHIP_METHOD_SHELL


def _sx_processing_for_ship_method(bom: BomTemplate, method: str) -> tuple[float, str]:
    """绍兴二次加工成本（EN 逻辑）：半成品→绍兴包装半成品成本；成品→绍兴包装成品成本；皮壳→0。"""
    if method == SHIP_METHOD_SEMI:
        return (bom.sx_semi if bom.sx_semi is not None else 0.0, "绍兴包装半成品成本")
    if method == SHIP_METHOD_FIN:
        return (bom.sx_fin if bom.sx_fin is not None else 0.0, "绍兴包装成品成本")
    return (0.0, "皮壳不计绍兴二次加工")


def build_b2_catalog(
    shell_index: dict[str, str],
    bom_index: BomIndex,
    *,
    keys: Iterable[str],
    ambiguous_keys: Iterable[str] = (),
) -> CostCatalogResult:
    """B2：四项全按 import 表重建。歧义键不解析（不猜首/末行）。"""
    result = CostCatalogResult()
    if bom_index.ambiguities:
        result.blocked_reasons.append(
            f"importBOMCostList 存在 {len(bom_index.ambiguities)} 个歧义重量模板"
        )
    ambiguous = set(ambiguous_keys)
    for key in sorted(ambiguous):
        result.duplicate_keys.append({"key": key, "reason": "import皮壳成本 同键不同重量模板"})

    for key in keys:
        if key in ambiguous:
            result.unmatched.append({"key": key, "reason": "ambiguous_shell_key"})
            continue
        wt = shell_index.get(key)
        if not wt:
            result.unmatched.append({"key": key, "reason": "missing_shell_import"})
            continue
        bom = bom_index.by_template.get(wt)
        if bom is None:
            result.unmatched.append({"key": key, "reason": "missing_bom_import", "weight_template": wt})
            continue
        if bom.ustx_processing is None:
            result.unmatched.append(
                {"key": key, "reason": "missing_ustx_processing", "weight_template": wt}
            )
            continue
        method = _ship_method_for(bom.ship_methods)
        sx2, sx2_src = _sx_processing_for_ship_method(bom, method)
        result.rows[key] = {
            "key": key,
            "source_kind": SRC_IMPORT,
            "weight_template": wt,
            "shipping_method": method,
            "shell_cost": bom.shell_cost_max,
            "head_freight": None,          # import 表无来源 → 调用方保留 A
            "processing_cost": bom.ustx_processing,
            "sx_processing_cost": sx2,
            "formula_version": FORMULA_VERSION,
            "lineage": (
                f"{SHELL_IMPORT_SHEET}:{SHELL_IMPORT_KEY}={key}->{SHELL_IMPORT_WT}={wt}",
                f"{BOM_SHEET}:{BOM_WT}={wt}(rows={','.join(map(str, bom.source_rows[:5]))})",
                f"{BOM_SHEET}:{BOM_USTX_COST}={bom.ustx_processing}",
                f"sx2_source={sx2_src}",
            ),
        }
    result.source_counts = {
        SRC_IMPORT: len(result.rows),
        "unmatched": len(result.unmatched),
    }
    return result


def build_b1_catalog(
    b1_key_values: dict[str, float],
    b2_catalog: CostCatalogResult,
    *,
    keys: Iterable[str],
) -> CostCatalogResult:
    """B1：测算表已有值优先（measured）；缺且 B2 可重建 → formula_filled；否则 unmatched。"""
    result = CostCatalogResult()
    result.blocked_reasons.extend(b2_catalog.blocked_reasons)
    for dup in b2_catalog.duplicate_keys:
        result.duplicate_keys.append(dict(dup))

    for key in keys:
        if key in b1_key_values:
            v = b1_key_values[key]
            result.rows[key] = {
                "key": key,
                "source_kind": SRC_MEASURED,
                "shipping_method": b2_catalog.rows.get(key, {}).get("shipping_method", ""),
                "shell_cost": None,          # B1 只改二次加工成本，其余沿用 A
                "head_freight": None,
                "processing_cost": v,
                "sx_processing_cost": None,  # 沿用 A
                "b1_source_sheet": B1_SHEET,
                "b1_source_column": B1_MONTH_COL,
                "formula_version": FORMULA_VERSION,
                "lineage": (f"{B1_SHEET}:{B1_MONTH_COL}={v}",),
            }
            continue
        b2 = b2_catalog.rows.get(key)
        if b2 is not None:
            result.rows[key] = {
                "key": key,
                "source_kind": SRC_FORMULA_FILLED,
                "shipping_method": b2["shipping_method"],
                "shell_cost": None,
                "head_freight": None,
                "processing_cost": b2["processing_cost"],
                "sx_processing_cost": None,
                "formula_version": FORMULA_VERSION,
                "lineage": ("formula_filled<-" + ";".join(b2["lineage"]),),
            }
            continue
        reason = "missing_b1_and_b2"
        for u in b2_catalog.unmatched:
            if u["key"] == key:
                reason = "b1_missing_" + u["reason"]
                break
        result.unmatched.append({"key": key, "reason": reason})

    measured = sum(1 for r in result.rows.values() if r["source_kind"] == SRC_MEASURED)
    filled = sum(1 for r in result.rows.values() if r["source_kind"] == SRC_FORMULA_FILLED)
    result.source_counts = {
        SRC_MEASURED: measured,
        SRC_FORMULA_FILLED: filled,
        "unmatched": len(result.unmatched),
    }
    return result


def b1_key_values(
    b1_headers: Sequence[str], b1_rows: Sequence[Sequence[str]]
) -> dict[str, float]:
    """测算 美中USTX二次加工成本 → {键: 最新月度列值}（空/0 视为缺）。"""
    dicts = _rows_to_dicts(b1_headers, b1_rows)
    out: dict[str, float] = {}
    for r in dicts:
        key = r.get(KEY_COL, "")
        if not key:
            continue
        v = to_float(r.get(B1_MONTH_COL))
        if v:
            out[key] = v
    return out


# ─────────────────────────── 全月逐行比较 ───────────────────────────

TOL = 0.01


@dataclass
class MonthlyComparisonResult:
    rows: list[dict] = field(default_factory=list)
    raw_coverage: list[dict] = field(default_factory=list)
    ustx_rows: list[dict] = field(default_factory=list)
    component_waterfall: list[dict] = field(default_factory=list)
    attribution: list[dict] = field(default_factory=list)
    unmatched: list[dict] = field(default_factory=list)
    duplicate_keys: list[dict] = field(default_factory=list)
    gates: list[dict] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    head_shell_sensitivity: float | None = None

    @property
    def conclusions_blocked(self) -> bool:
        return any(g["status"] == "fail" and g["blocking"] for g in self.gates)


def _gate(name: str, ok: bool, detail: str, blocking: bool = True) -> dict:
    return {
        "gate": name,
        "status": "pass" if ok else "fail",
        "blocking": blocking,
        "detail": detail,
    }


def _lineage_tuple(record) -> tuple:
    k = record.key
    return (k.order_id, k.package_id, k.tongtool_sku, k.platform_sku, k.occurrence_index)


def _record_business_key(record) -> str:
    return "|".join(str(x) for x in _lineage_tuple(record))


def order_row_to_record(row) -> dict:
    """把 SourceRow 抽成比较所需的扁平字典（A 四项 + 血缘）。"""
    comps = [to_float(row.get(c)) for c in COMPONENT_COLS]
    return {
        "source_sheet": row.source_sheet,
        "source_row": row.row_number,
        "occurrence_index": row.key.occurrence_index,
        "biz_key": _record_business_key(row),
        "key": row.get(KEY_COL),
        "key_nofabric": row.get("品类尺寸编码"),
        "warehouse": row.get(WAREHOUSE_COL),
        "category": row.get(CATEGORY_COL),
        "qty": to_float(row.get(QTY_COL)) or 0.0,
        "a": dict(zip(COMPONENT_COLS, comps)),
    }


def compare_monthly_costs(
    order_rows: Sequence,
    raw_rows: Sequence,
    *,
    ustx_warehouse_names: set[str],
    b1_catalog: CostCatalogResult,
    b2_catalog: CostCatalogResult,
    contract: FormulaContract,
    head_index: "HeadFreightIndex | None" = None,
) -> MonthlyComparisonResult:
    """全月逐行 A/B1/B2 比较；非 USTX 行严格复制 A；输出对账与闸门。

    `head_index`（皮壳头程）给了就把 B2 的「头程运费」换成皮壳头程；
    没给或该键未命中则保留 A。
    """
    result = MonthlyComparisonResult()
    result.blocked_reasons.extend(sorted(set(b1_catalog.blocked_reasons + b2_catalog.blocked_reasons)))
    seen_dups: set[tuple] = set()
    for d in list(b1_catalog.duplicate_keys) + list(b2_catalog.duplicate_keys):
        sig = (d.get("key"), d.get("reason"))
        if sig in seen_dups:
            continue
        seen_dups.add(sig)
        result.duplicate_keys.append(d)

    pk_col, head_col, proc_col, sx2_col = COMPONENT_COLS
    ustx_keys: set[str] = set()
    b1_used = 0
    b2_used = 0
    head_hit = 0
    head_miss = 0

    for row in order_rows:
        rec = order_row_to_record(row)
        key = rec["key"]
        a = rec["a"]
        is_ustx = rec["warehouse"] in ustx_warehouse_names

        if is_ustx:
            ustx_keys.add(key)

        b1 = dict(a)
        b2 = dict(a)
        b1_kind = SRC_NOT_USTX
        b2_kind = SRC_NOT_USTX
        b1_lineage = ""
        b2_lineage = ""
        head_src = ""
        b2_head_shell = None

        if is_ustx:
            cat1 = b1_catalog.rows.get(key)
            if cat1 is not None:
                b1[proc_col] = cat1["processing_cost"]
                b1_kind = cat1["source_kind"]
                b1_lineage = ";".join(cat1.get("lineage", ()))
                b1_used += 1
            else:
                b1_kind = SRC_UNMATCHED

            cat2 = b2_catalog.rows.get(key)
            if cat2 is not None:
                if cat2["shell_cost"] is not None:
                    b2[pk_col] = cat2["shell_cost"]
                b2[proc_col] = cat2["processing_cost"]
                b2[sx2_col] = cat2["sx_processing_cost"]
                b2_kind = SRC_IMPORT
                b2_lineage = ";".join(cat2.get("lineage", ()))
                b2_used += 1
            else:
                b2_kind = SRC_UNMATCHED

            if head_index is not None and cat2 is not None:
                tmpl = head_index.by_template.get(cat2["weight_template"], {})
                b2_head_shell = tmpl.get("皮壳")
                amt, head_src = head_index.resolve(
                    cat2["weight_template"], cat2["shipping_method"]
                )
                if amt is not None:
                    b2[head_col] = amt
                    head_hit += 1
                else:
                    head_miss += 1
            elif head_index is not None:
                head_miss += 1

        def _sum(d):
            return sum((d[c] or 0.0) for c in COMPONENT_COLS)

        unit_a = _sum(a)
        unit_b1 = _sum(b1)
        unit_b2 = _sum(b2)
        qty = rec["qty"]

        out = {
            "source_sheet": rec["source_sheet"],
            "source_row": rec["source_row"],
            "occurrence_index": rec["occurrence_index"],
            "biz_key": rec["biz_key"],
            "key": key,
            "warehouse": rec["warehouse"],
            "category": rec["category"],
            "shipping_method": (
                b2_catalog.rows.get(key, {}).get("shipping_method", "")
                if is_ustx
                else ""
            ),
            "qty": qty,
            "is_ustx": is_ustx,
            "b1_source": b1_kind,
            "b2_source": b2_kind,
            "head_src": head_src,
            "B2_head_shell": b2_head_shell,
            "b1_lineage": b1_lineage,
            "b2_lineage": b2_lineage,
        }
        for label, comp in zip(("pk", "head", "proc", "sx2"), COMPONENT_COLS):
            out[f"A_{label}"] = a[comp]
            out[f"B1_{label}"] = b1[comp]
            out[f"B2_{label}"] = b2[comp]
            out[f"d1_{label}"] = round((b1[comp] or 0.0) - (a[comp] or 0.0), 6)
            out[f"d2_{label}"] = round((b2[comp] or 0.0) - (a[comp] or 0.0), 6)
        out["unit_A"] = round(unit_a, 6)
        out["unit_B1"] = round(unit_b1, 6)
        out["unit_B2"] = round(unit_b2, 6)
        out["d_unit_B1"] = round(unit_b1 - unit_a, 6)
        out["d_unit_B2"] = round(unit_b2 - unit_a, 6)
        out["amt_B1"] = round((unit_b1 - unit_a) * qty, 6)
        out["amt_B2"] = round((unit_b2 - unit_a) * qty, 6)
        result.rows.append(out)

    result.ustx_rows = [r for r in result.rows if r["is_ustx"]]

    # ── 未匹配（仅 USTX 且两目录都缺）──
    for r in result.ustx_rows:
        if r["b1_source"] == SRC_UNMATCHED:
            result.unmatched.append(
                {"scenario": "B1", "key": r["key"], "source_row": r["source_row"],
                 "reason": "b1_missing_and_b2_unmatched"}
            )
        if r["b2_source"] == SRC_UNMATCHED:
            result.unmatched.append(
                {"scenario": "B2", "key": r["key"], "source_row": r["source_row"],
                 "reason": "b2_unmatched"}
            )

    # ── raw 覆盖对账 ──
    raw_keys = [_record_business_key(r) for r in raw_rows]
    wb_keys = [r["biz_key"] for r in result.rows]
    raw_set, wb_set = set(raw_keys), set(wb_keys)
    result.raw_coverage = [
        {"bucket": "raw_input", "rows": len(raw_keys)},
        {"bucket": "writeback_input", "rows": len(wb_keys)},
        {"bucket": "raw_only", "rows": len(raw_set - wb_set)},
        {"bucket": "writeback_only", "rows": len(wb_set - raw_set)},
        {"bucket": "both", "rows": len(raw_set & wb_set)},
    ]

    # ── USTX 四项瀑布（金额按发货数量加权）──
    waterfall = []
    for label, comp in zip(("皮壳成本", "头程运费", "二次加工成本", "绍兴二次加工成本"), COMPONENT_COLS):
        a_amt = sum((r[f"A_{k}"] or 0.0) * r["qty"] for r in result.ustx_rows for k in [_key_of(label)])
        b1_amt = sum((r[f"B1_{k}"] or 0.0) * r["qty"] for r in result.ustx_rows for k in [_key_of(label)])
        b2_amt = sum((r[f"B2_{k}"] or 0.0) * r["qty"] for r in result.ustx_rows for k in [_key_of(label)])
        waterfall.append(
            {
                "component": label,
                "A_amount": round(a_amt, 2),
                "B1_amount": round(b1_amt, 2),
                "B2_amount": round(b2_amt, 2),
                "d1_amount": round(b1_amt - a_amt, 2),
                "d2_amount": round(b2_amt - a_amt, 2),
            }
        )
    result.component_waterfall = waterfall

    # ── 归因：仓库 × 品类 × 绍兴发货方式 ──
    agg: dict[tuple, dict] = {}
    for r in result.ustx_rows:
        k = (r["warehouse"], r["category"], r["shipping_method"])
        cell = agg.setdefault(
            k,
            {"warehouse": r["warehouse"], "category": r["category"],
             "shipping_method": r["shipping_method"], "rows": 0, "qty": 0.0,
             "amt_A": 0.0, "amt_B1": 0.0, "amt_B2": 0.0,
             "d1_pk": 0.0, "d1_proc": 0.0, "d2_pk": 0.0, "d2_proc": 0.0, "d2_sx2": 0.0},
        )
        q = r["qty"]
        cell["rows"] += 1
        cell["qty"] += q
        cell["amt_A"] += r["unit_A"] * q
        cell["amt_B1"] += r["unit_B1"] * q
        cell["amt_B2"] += r["unit_B2"] * q
        cell["d1_pk"] += r["d1_pk"] * q
        cell["d1_proc"] += r["d1_proc"] * q
        cell["d2_pk"] += r["d2_pk"] * q
        cell["d2_proc"] += r["d2_proc"] * q
        cell["d2_sx2"] += r["d2_sx2"] * q
    result.attribution = [
        {**v, "d1_amt": round(v["amt_B1"] - v["amt_A"], 2), "d2_amt": round(v["amt_B2"] - v["amt_A"], 2)}
        for v in sorted(agg.values(), key=lambda x: -abs(x["amt_B2"] - x["amt_A"]))
    ]

    # ── 闸门 ──
    gates = []
    gates.append(_gate("writeback_row_conservation",
                       len(result.rows) == len(order_rows),
                       f"输出 {len(result.rows)} 行 / 输入 {len(order_rows)} 行"))
    non_ustx_bad = [r for r in result.rows if not r["is_ustx"] and (
        abs(r["d_unit_B1"]) > TOL or abs(r["d_unit_B2"]) > TOL)]
    gates.append(_gate("non_ustx_zero_delta", not non_ustx_bad,
                       f"非 USTX 行有差异 {len(non_ustx_bad)} 行"))
    counts = b1_catalog.source_counts
    # 目录必须**闭合覆盖**所有美中键：rows(measured+formula_filled) + unmatched == 键数
    gates.append(_gate(
        "b1_source_conservation",
        len(b1_catalog.rows) + len(b1_catalog.unmatched) == len(ustx_keys),
        f"B1 目录 {len(b1_catalog.rows)}+{len(b1_catalog.unmatched)} 键 vs 美中 {len(ustx_keys)} 键"
        f"（measured={counts.get(SRC_MEASURED,0)} formula_filled={counts.get(SRC_FORMULA_FILLED,0)}）",
    ))
    b2_missing_lineage = [r for r in result.ustx_rows
                          if r["b2_source"] == SRC_IMPORT and not r["b2_lineage"]]
    gates.append(_gate("b2_lineage_complete", not b2_missing_lineage,
                       f"B2 匹配行缺血缘 {len(b2_missing_lineage)} 行"))
    identity_bad = [r for r in result.rows
                    if abs(sum(r[f"d1_{k}"] for k in ("pk", "head", "proc", "sx2")) - r["d_unit_B1"]) > TOL
                    or abs(sum(r[f"d2_{k}"] for k in ("pk", "head", "proc", "sx2")) - r["d_unit_B2"]) > TOL]
    gates.append(_gate("component_identity", not identity_bad,
                       f"四项 delta 之和 != 单价 delta 的行 {len(identity_bad)}"))
    gates.append(_gate("no_ambiguous_dimension_keys",
                       not b2_catalog.blocked_reasons and not b2_catalog.duplicate_keys,
                       f"歧义原因 {len(b2_catalog.blocked_reasons)} 条 + 冲突键 "
                       f"{len(b2_catalog.duplicate_keys)} 个（对应行已排除，不猜值）",
                       blocking=False))
    gates.append(_gate("raw_coverage_conservation",
                       len(raw_set - wb_set) + len(wb_set - raw_set) + len(raw_set & wb_set)
                       == len(raw_set | wb_set),
                       f"raw {len(raw_keys)} / writeback {len(wb_keys)}："
                       f"raw_only={len(raw_set - wb_set)} wb_only={len(wb_set - raw_set)} both={len(raw_set & wb_set)}"))
    if head_index is not None:
        gates.append(_gate("b2_head_freight_coverage",
                           head_miss == 0,
                           f"B2 头程(按绍兴发货方式)命中 {head_hit} 行 / 未命中 {head_miss} 行（未命中保留 A）",
                           blocking=False))
    result.gates = gates

    if head_index is not None:
        result.notes.append(
            f"B2 头程=EN BOM 按绍兴发货方式取（半成品→半成品头程、成品→成品头程、皮壳→皮壳头程，"
            f"缺则皮壳兜底）：命中 {head_hit} 行 / 未命中 {head_miss} 行（未命中保留 A）。"
        )
        # 敏感度：若改用「按皮壳重量」勾选项（全部行取皮壳头程）的差额
        head_shell_delta = sum(
            ((r["B2_head_shell"] if r["B2_head_shell"] is not None else (r["A_head"] or 0.0))
             - (r["A_head"] or 0.0)) * r["qty"]
            for r in result.ustx_rows
        )
        result.head_shell_sensitivity = round(head_shell_delta, 2)
        result.notes.append(
            f"A 的头程已含 EN 覆盖层、与 B2 同源 → Δ=0。若勾选「按皮壳重量」口径，头程将再变 "
            f"{head_shell_delta:+,.0f}（7 月，￥加权）。"
        )
    else:
        result.notes.append("头程运费未接入 EN BOM 成本列表 → A/B1/B2 均沿用订单现值（Δ=0）。")
    result.notes.append("B1 与 B2 非同源：B1=人工测算表，B2=EN/import 重建，差异本身即结论。")
    result.notes.append("B2 二次加工成本取自 EN 美中USTX包装 BOM；工资 167.8→105 尚未调整，值可能偏高。")
    return result


def _key_of(component_label: str) -> str:
    return {
        "皮壳成本": "pk",
        "头程运费": "head",
        "二次加工成本": "proc",
        "绍兴二次加工成本": "sx2",
    }[component_label]


# ─────────────────────────── 产出 ───────────────────────────

REPORT_SHEETS = [
    "00_管理摘要",
    "01_源清单",
    "02_键覆盖",
    "03_全量A_B1_B2逐行",
    "04_仅美中差异",
    "05_四项成本瀑布",
    "06_仓库品类发货方式",
    "07_未匹配",
    "08_重复歧义键",
    "09_闸门",
]

_ROW_COLUMNS = [
    "source_sheet", "source_row", "occurrence_index", "key", "warehouse", "category",
    "shipping_method", "qty", "is_ustx", "b1_source", "b2_source", "head_src",
    "A_pk", "A_head", "A_proc", "A_sx2",
    "B1_pk", "B1_head", "B1_proc", "B1_sx2",
    "B2_pk", "B2_head", "B2_proc", "B2_sx2",
    "d1_pk", "d1_head", "d1_proc", "d1_sx2",
    "d2_pk", "d2_head", "d2_proc", "d2_sx2",
    "unit_A", "unit_B1", "unit_B2", "d_unit_B1", "d_unit_B2", "amt_B1", "amt_B2",
    "B2_head_shell", "head_src",
    "b1_lineage", "b2_lineage",
]


def build_sheets(
    result: MonthlyComparisonResult,
    *,
    sources: Sequence[dict] | None = None,
) -> dict:
    """把比较结果转成 {sheet_name: DataFrame}。"""
    import pandas as pd

    def df(rows, cols=None):
        if not rows:
            return pd.DataFrame(columns=cols or [])
        d = pd.DataFrame(rows)
        if cols:
            for c in cols:
                if c not in d.columns:
                    d[c] = None
            d = d[cols]
        return d

    ustx = result.ustx_rows
    only_ustx_diff = [r for r in ustx if abs(r["d_unit_B1"]) > TOL or abs(r["d_unit_B2"]) > TOL]

    summary = [
        {"metric": "写回表总行数", "value": len(result.rows)},
        {"metric": "美中(USTX)行数", "value": len(ustx)},
        {"metric": "非美中行数", "value": len(result.rows) - len(ustx)},
        {"metric": "B1 measured 键", "value": sum(1 for r in ustx if r["b1_source"] == SRC_MEASURED)},
        {"metric": "B1 formula_filled 键", "value": sum(1 for r in ustx if r["b1_source"] == SRC_FORMULA_FILLED)},
        {"metric": "B1 unmatched 行", "value": sum(1 for r in ustx if r["b1_source"] == SRC_UNMATCHED)},
        {"metric": "B2 import 匹配行", "value": sum(1 for r in ustx if r["b2_source"] == SRC_IMPORT)},
        {"metric": "B2 unmatched 行", "value": sum(1 for r in ustx if r["b2_source"] == SRC_UNMATCHED)},
        {"metric": "结论是否阻断", "value": "是" if result.conclusions_blocked else "否"},
    ]
    for w in result.component_waterfall:
        summary.append({"metric": f"瀑布 Δ(B1) {w['component']}", "value": w["d1_amount"]})
        summary.append({"metric": f"瀑布 Δ(B2) {w['component']}", "value": w["d2_amount"]})
    for n in result.notes:
        summary.append({"metric": "note", "value": n})

    key_cov = []
    seen: dict[str, dict] = {}
    for r in ustx:
        c = seen.setdefault(r["key"], {"key": r["key"], "rows": 0,
                                       "b1": r["b1_source"], "b2": r["b2_source"]})
        c["rows"] += 1
    key_cov = sorted(seen.values(), key=lambda x: x["key"])

    return {
        "00_管理摘要": df(summary, ["metric", "value"]),
        "01_源清单": df(list(sources or [])) ,
        "02_键覆盖": df(key_cov, ["key", "rows", "b1", "b2"]),
        "03_全量A_B1_B2逐行": df(result.rows, _ROW_COLUMNS),
        "04_仅美中差异": df(only_ustx_diff, _ROW_COLUMNS),
        "05_四项成本瀑布": df(result.component_waterfall),
        "06_仓库品类发货方式": df(result.attribution),
        "07_未匹配": df(result.unmatched, ["scenario", "key", "source_row", "reason"]),
        "08_重复歧义键": df(result.duplicate_keys),
        "09_闸门": df(result.gates, ["gate", "status", "blocking", "detail"]),
    }


def _json_payload(result: MonthlyComparisonResult, *, run_id: str, sources: Sequence[dict] | None) -> dict:
    return {
        "run_id": run_id,
        "formula_version": FORMULA_VERSION,
        "conclusions_blocked": result.conclusions_blocked,
        "counts": {
            "rows_total": len(result.rows),
            "rows_ustx": len(result.ustx_rows),
            "b1_measured": sum(1 for r in result.ustx_rows if r["b1_source"] == SRC_MEASURED),
            "b1_formula_filled": sum(1 for r in result.ustx_rows if r["b1_source"] == SRC_FORMULA_FILLED),
            "b1_unmatched": sum(1 for r in result.ustx_rows if r["b1_source"] == SRC_UNMATCHED),
            "b2_import": sum(1 for r in result.ustx_rows if r["b2_source"] == SRC_IMPORT),
            "b2_unmatched": sum(1 for r in result.ustx_rows if r["b2_source"] == SRC_UNMATCHED),
        },
        "component_waterfall": result.component_waterfall,
        "head_shell_sensitivity": result.head_shell_sensitivity,
        "raw_coverage": result.raw_coverage,
        "gates": result.gates,
        "blocked_reasons": result.blocked_reasons,
        "notes": result.notes,
        "sources": list(sources or []),
    }


def render_memo(result: MonthlyComparisonResult) -> str:
    lines = ["# 美中 USTX 成本三方案对比（管理摘要）", ""]
    if result.conclusions_blocked:
        lines.append("> **结论已阻断**：存在未通过的 blocking 闸门，下列金额仅供参考，须先排除阻断原因。")
        for g in result.gates:
            if g["status"] == "fail":
                lines.append(f"> - ❌ {g['gate']}：{g['detail']}")
        lines += [""]
    lines.append("## 口径")
    lines.append("- A：现状（美中走 2CJG-SX，二次加工成本记绍兴加工费）")
    lines.append("- B1：A 基础上把美中「二次加工成本」换成测算表最新月度列（多月202411），缺行用 B2 公式补")
    lines.append("- B2：四项按 EN/import 表重建（皮壳取 max；头程按绍兴发货方式取、皮壳兜底；")
    lines.append("  二次加工=美中USTX；绍兴二次加工按绍兴发货方式取包装半/成品成本）")
    lines.append("")
    lines.append("## 全月差额（仅美中，按发货数量加权，￥）")
    lines.append("")
    lines.append("| 分项 | A | B1 | B2 | ΔB1 | ΔB2 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for w in result.component_waterfall:
        lines.append(
            f"| {w['component']} | {w['A_amount']:,.0f} | {w['B1_amount']:,.0f} | {w['B2_amount']:,.0f} "
            f"| {w['d1_amount']:,.0f} | {w['d2_amount']:,.0f} |"
        )
    tot_a = sum(w["A_amount"] for w in result.component_waterfall)
    tot_1 = sum(w["B1_amount"] for w in result.component_waterfall)
    tot_2 = sum(w["B2_amount"] for w in result.component_waterfall)
    lines.append(f"| **合计** | **{tot_a:,.0f}** | **{tot_1:,.0f}** | **{tot_2:,.0f}** | **{tot_1-tot_a:,.0f}** | **{tot_2-tot_a:,.0f}** |")
    lines.append("")
    lines.append("## 关键数字")
    lines.append(f"- 写回表行数 {len(result.rows)}，美中 {len(result.ustx_rows)} 行")
    lines.append(f"- B1 来源：measured {sum(1 for r in result.ustx_rows if r['b1_source']==SRC_MEASURED)} / "
                 f"formula_filled {sum(1 for r in result.ustx_rows if r['b1_source']==SRC_FORMULA_FILLED)} / "
                 f"unmatched {sum(1 for r in result.ustx_rows if r['b1_source']==SRC_UNMATCHED)}")
    lines.append("")
    lines.append("## 未匹配 / 歧义（不猜值，逐条保留）")
    b2_un = sum(1 for r in result.ustx_rows if r["b2_source"] == SRC_UNMATCHED)
    for co in result.raw_coverage:
        lines.append(f"- {co['bucket']}：{co['rows']} 行")
    lines.append(f"- B2 未匹配美中行：{b2_un}（见 `07_未匹配`）")
    lines.append(f"- 冲突/歧义维表键：{len(result.duplicate_keys)} 个（见 `08_重复歧义键`，对应美中行已排除）")
    for g in result.gates:
        if g["status"] == "fail" and not g["blocking"]:
            lines.append(f"- ⚠️ 非阻断告警 {g['gate']}：{g['detail']}")
    lines.append("")
    lines.append("## 注意事项")
    for n in result.notes:
        lines.append(f"- {n}")
    return "\n".join(lines) + "\n"


def write_outputs(
    result: MonthlyComparisonResult,
    out_dir: Path | str,
    *,
    run_id: str,
    sources: Sequence[dict] | None = None,
) -> dict[str, str]:
    """写 audit.json / audit.xlsx / 管理摘要.md；目录已存在则拒绝（不覆盖历史）。"""
    import json
    from pathlib import Path as _P

    out = _P(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"输出目录已存在且非空，拒绝覆盖: {out}")
    out.mkdir(parents=True, exist_ok=True)

    payload = _json_payload(result, run_id=run_id, sources=sources)
    jp = out / "audit.json"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    mp = out / "管理摘要.md"
    mp.write_text(render_memo(result), encoding="utf-8")

    sheets = build_sheets(result, sources=sources)
    xp = out / "audit.xlsx"
    import pandas as pd

    with pd.ExcelWriter(xp, engine="openpyxl") as writer:
        for name in REPORT_SHEETS:
            sheets[name].to_excel(writer, sheet_name=name, index=False)

    return {"audit_json": str(jp), "audit_xlsx": str(xp), "memo": str(mp)}
