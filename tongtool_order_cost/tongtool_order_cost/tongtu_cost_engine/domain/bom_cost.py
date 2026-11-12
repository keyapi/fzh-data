# -*- coding: utf-8 -*-
"""Phase 2 成本：BOM Cost List 单位成本 × 件数（shadow，只读）。

口径（用户 2026-11-04 确认）：
- 皮壳成本 = BOM `cost_fg`；
- 头程按仓库分类 + method 取对应头程列（-COVER→皮壳头程；-FOAM→成品/半成品头程−皮壳头程；
  FBA 用对应 FBA 成品头程；美国海外仓按 method 用 USTX、成品头程用 USFBA）；
- 二次加工 = 仓库分类对应 valuation_rate（USNJ/USTX/PL；FBA=0；美国海外仓=USTX）；
- 绍兴二次加工 = 半成品→cost_sxbzbcp；成品→cost_sxbzcp；皮壳→0；FBA→sx_cost_all−cost_fg；
- 合并组按 Phase 1 `pieces` 乘，透传行按 `qty` 乘。

约束：
- **method 规则（2026-11-10 定案）**：定价 method 一律取 **BOM master `shipping_method`**
  （load_orders 按 EN 行级 exact item / 别名候选解析 BOM method）；EN 订单行
  `shipping_method` 只作审计（`en_method`），不一致时输出 `method_diff` +
  `method_diff_alt_delta`，**不阻断、不影响定价**。
- BOM 多行/缺行/缺仓库分类/负值 → 该行成本阻断（不出值）。
- 多候选 item 只用 Phase 1 锁定的 `product_id` 子树；同产品仍多 Item → 阻断。
- 写回表四列与 BOM 结果逐列对账，**仅对账、不采信**，差异进 `diff_vs_writeback_*`。
- 不写 GS/EN。
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .split_merge import (
    METHOD_COVER,
    METHOD_FINISHED,
    METHOD_SEMI,
    METHODS,
    SHAPE_COVER,
    SHAPE_FINISHED,
    SHAPE_FOAM,
    SHAPE_PPCOTTON,
    TOL,
    Assertion,
    EnResolver,
    MergeShadowResult,
    is_non_product_accessory,
    normalize_sku,
    sku_shape,
)

# EN 头程列后缀（按仓库分类）
FREIGHT_LABELS: dict[str, str] = {
    "USNJ": "2kk9fsq8ln",
    "USTX": "e5asph24tk",
    "PL": "tmvvepd80f",
    "USFBA": "9rr7m7g3aj",
    "DEFBA": "88hko2ad7l",
    "UKFBA": "0hn57vpr4u",
    "JPFBA": "3s2n1bnpbj",
}
FBA_BUCKETS = {"USFBA", "DEFBA", "UKFBA", "JPFBA"}
US_OVERSEAS = "US_OVERSEAS"

BOM_REQUIRED_COLUMNS: tuple[str, ...] = (
    "item_fg",
    "shipping_method",
    "cost_fg",
    "cost_sxbzbcp",
    "cost_sxbzcp",
    "sx_cost_all",
    "usnj_valuation_rate",
    "ustx_valuation_rate",
    "pl_valuation_rate",
)

WB_COST_COLUMNS = ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本")

PHASE2_COST_COLUMNS: tuple[str, ...] = (
    "皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本",
)

PHASE2_COLUMNS: tuple[str, ...] = (
    "group_id",
    "merged",
    "订单号/子单",
    "平台SKU",
    "order_common",
    "SKU",
    "product_id",
    "item_fg",
    "method",
    "method_source",
    "bundle_version",
    "kit_method",
    "kit_report_diff",
    "bom_method",
    "method_diff",
    "method_diff_alt_delta",
    "warehouse_class",
    "warehouse_bucket",
    "units",
    "pieces",
    "qty",
    "皮壳成本",
    "头程运费金额",
    "二次加工成本",
    "绍兴二次加工成本",
    "四列合计",
    "1件成本(不含头程)",
    "status",
    "reason",
    "suggested_items",
    "source",
    "wb匹配行数",
    "wb_皮壳成本",
    "wb_头程运费金额",
    "wb_二次加工成本",
    "wb_绍兴二次加工成本",
    "diff_vs_writeback_皮壳成本",
    "diff_vs_writeback_头程运费金额",
    "diff_vs_writeback_二次加工成本",
    "diff_vs_writeback_绍兴二次加工成本",
    "diff_vs_writeback_合计",
)


@dataclass
class Phase2Result:
    rows: list[dict]
    assertions: list[Assertion]
    stats: dict

    @property
    def ok(self) -> bool:
        return all(a.status != "fail" for a in self.assertions)


def _num(value: object) -> float | None:
    s = str(value).strip() if value is not None else ""
    if s in ("", "nan", "None", "NULL"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def load_bom_cost(path: str | Path) -> dict[str, list[dict]]:
    """item_fg → BOM 行列表（多行留给调用方阻断）。"""
    df = pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False)
    missing = [c for c in BOM_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"BOM Cost List 缺列: {missing}")
    index: dict[str, list[dict]] = {}
    for rec in df.to_dict("records"):
        item = str(rec.get("item_fg") or "").strip()
        if item:
            index.setdefault(item, []).append(rec)
    return index


@dataclass(frozen=True)
class BundleInfo:
    components: tuple[tuple[str, float], ...]
    version: str
    child_hash: str


def load_bundles(path: str | Path | None) -> dict[str, BundleInfo]:
    """Product Bundle：bundle_item → 子件与版本（modified/creation + 子件 hash）。"""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    df = pd.read_csv(p, dtype=str, low_memory=False, keep_default_na=False)
    out: dict[str, BundleInfo] = {}
    for bundle, group in df.groupby("bundle_item", sort=False):
        components: list[tuple[str, float]] = []
        versions: set[str] = set()
        hashes: set[str] = set()
        modified = ""
        for rec in group.to_dict("records"):
            comp = str(rec.get("component_item") or "").strip()
            qty = _num(rec.get("qty")) or 0.0
            if comp and qty > 0:
                components.append((comp, qty))
            v = str(rec.get("bundle_version") or "").strip()
            if v:
                versions.add(v)
            h = str(rec.get("child_hash") or "").strip()
            if h:
                hashes.add(h)
            modified = modified or str(rec.get("bundle_modified") or rec.get("bundle_creation") or "").strip()
        child_hash = hashlib.sha256(
            "|".join(sorted(f"{c}:{q:g}" for c, q in components)).encode()
        ).hexdigest()[:12]
        version = ""
        if len(versions) == 1 and len(hashes) <= 1:
            version = next(iter(versions))
        elif modified:
            version = f"{modified}|{child_hash}"
        out[str(bundle)] = BundleInfo(tuple(components), version, child_hash)
    return out


def _bundle_unit_costs(
    components: Sequence[tuple[str, float]],
    bom_index: Mapping[str, list[dict]],
    bucket: str,
) -> tuple[dict | None, str]:
    """套件展开：子件按各自 BOM method 求和（单位成本）。"""
    comps = list(components)
    if not comps:
        return None, "bundle_missing"
    sums = {"shell": 0.0, "freight": 0.0, "processing": 0.0, "sx": 0.0}
    for comp, qty in comps:
        rows = bom_index.get(comp) or []
        if len(rows) != 1:
            return None, f"bundle_component_bom:{comp}"
        bom = rows[0]
        method = str(bom.get("shipping_method") or "").strip()
        if method not in METHODS:
            return None, f"bundle_component_method:{comp}"
        costs, reason = _unit_costs(bom, bucket, method, SHAPE_FINISHED)
        if reason:
            return None, f"bundle_component_cost:{comp}:{reason}"
        for k in sums:
            sums[k] += costs[k] * qty
    return {k: round(v, 6) for k, v in sums.items()}, ""


def load_kit_report(path: str | Path | None) -> dict[str, dict]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    df = pd.read_csv(p, dtype=str, low_memory=False, keep_default_na=False)
    return {
        str(r.get("item_fg") or "").strip(): r
        for r in df.to_dict("records")
        if str(r.get("item_fg") or "").strip().startswith("TJ#")
    }


def _bundle_audit(
    components: Sequence[tuple[str, float]],
    bom_index: Mapping[str, list[dict]],
    bucket: str,
) -> dict:
    """子件求和的审计值 + kit_method 候选。"""
    shell = semi = fin = sx_all = valuation = 0.0
    methods: list[str] = []
    rate_field = {
        "USNJ": "usnj_valuation_rate",
        "USTX": "ustx_valuation_rate",
        "PL": "pl_valuation_rate",
        US_OVERSEAS: "ustx_valuation_rate",
    }.get(bucket)
    for comp, qty in components:
        rows = bom_index.get(comp) or []
        if len(rows) != 1:
            methods.append("")
            continue
        bom = rows[0]
        methods.append(str(bom.get("shipping_method") or "").strip())
        shell += (_num(bom.get("cost_fg")) or 0.0) * qty
        semi += (_num(bom.get("cost_sxbzbcp")) or 0.0) * qty
        fin += (_num(bom.get("cost_sxbzcp")) or 0.0) * qty
        sx_all += (_num(bom.get("sx_cost_all")) or 0.0) * qty
        if rate_field:
            valuation += (_num(bom.get(rate_field)) or 0.0) * qty
    return {
        "shell": round(shell, 6), "semi": round(semi, 6), "fin": round(fin, 6),
        "sx_all": round(sx_all, 6), "valuation": round(valuation, 6),
        "methods": methods,
    }


def load_warehouse_map(path: str | Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name, cls = parts[0].strip(), parts[1].strip()
        if name == "name" or not name:
            continue
        mapping[name] = cls
    return mapping


def warehouse_bucket(classification: str) -> str:
    """仓库分类 → 成本桶。欧洲 FBA 默认按 DEFBA。"""
    c = str(classification or "").strip()
    if not c:
        return ""
    if "USNJ" in c or "美东" in c:
        return "USNJ"
    if "USTX" in c or "美中" in c:
        return "USTX"
    if "PL" in c or "波兰" in c:
        return "PL"
    if "美国FBA" in c:
        return "USFBA"
    if "日本FBA" in c:
        return "JPFBA"
    if "英国FBA" in c:
        return "UKFBA"
    if "FBA" in c:
        return "DEFBA"
    if "海外仓" in c:
        return US_OVERSEAS
    return ""


def _same_product(items: set[str], product_id: str, resolver: EnResolver) -> set[str]:
    """只保留属于 Phase 1 锁定产品的 Item，禁止从别的产品子树取 BOM。"""
    if not product_id:
        return set()
    return {i for i in items if resolver.product_for_item(i) == product_id}


def item_for_detail(
    detail: dict,
    resolver: EnResolver,
    bom_index: Mapping[str, list[dict]],
    anchor_items: Sequence[str] = (),
    context_product: str = "",
) -> tuple[str, str]:
    """解析 item_fg。

    - 合并组：**只用 Phase 1 的 carrier SKU + product**，不再逐行用组内组件 SKU 解析。
    - 透传行：先用自身 SKU 按产品过滤；仍是多个通用组件 Item 时，
      用同订单的 Cover/成品行锚定变体（唯一才用，否则阻断）。禁止组内任选。
    """
    product_id = str(detail.get("product_id") or "")
    en_item = str(detail.get("_en_item") or "").strip()
    if en_item:
        # EN 订单行已声明物料：直接用它查 BOM（行级权威，别名/产品只作校验）
        return (en_item, "") if en_item in bom_index else ("", "bom_item_missing")
    if detail.get("merged"):
        carrier = normalize_sku(detail.get("carrier_sku"))
        carrier_items = _same_product(set(resolver.items_for_sku(carrier)), product_id, resolver)
        if not carrier_items:
            # 皮壳组的 EN 登记可能只在“另一填充类型”的产品族上（同一皮壳用于 PP 棉/海绵）：
            # 用去掉 -Cover/-Foam 的基号在该产品族内再找一次；仍不唯一则阻断。
            base = re.sub(r'-(?:COVER|FOAM|PPCOTTON)\d*$', '',
                          str(detail.get("carrier_sku") or "").strip(), flags=re.I)
            if base and normalize_sku(base) != carrier:
                carrier_items = _same_product(
                    set(resolver.items_for_sku(base)), product_id, resolver)
        if len(carrier_items) == 1:
            item = next(iter(carrier_items))
            return (item, "") if item in bom_index else ("", "bom_item_missing")
        if len(carrier_items) > 1:
            return "", "bom_item_ambiguous"
        return "", "bom_item_missing"

    items = set(resolver.items_for_sku(detail.get("通途SKU")))
    if product_id:
        items = _same_product(items, product_id, resolver)
    elif context_product:
        items = {i for i in items if resolver.product_for_item(i) == context_product}
    if len(items) > 1 and context_product:
        narrowed = {i for i in items if resolver.product_for_item(i) == context_product}
        if narrowed:
            items = narrowed
    if len(items) == 1:
        item = next(iter(items))
        return (item, "") if item in bom_index else ("", "bom_item_missing")
    if len(items) > 1:
        # 通用组件（如 CURVE-PILLOW-*-PPCOTTON/-FOAM）：用同订单 Cover/成品行锚定
        anchors = sorted({i for i in anchor_items if i in bom_index})
        if len(anchors) == 1:
            return anchors[0], ""
        return "", "bom_item_ambiguous"
    return "", "bom_item_missing"


def _unit_costs(
    bom: dict,
    bucket: str,
    method: str,
    shape: str,
) -> tuple[dict | None, str]:
    """返回单件四列（不含件数）与阻断原因。"""
    if bucket not in set(FREIGHT_LABELS) | {US_OVERSEAS}:
        return None, "warehouse_unknown"
    if method not in METHODS:
        return None, "method_missing"

    shell = _num(bom.get("cost_fg"))
    if shell is None:
        return None, "bom_value_missing"

    # 头程
    if bucket in FBA_BUCKETS:
        freight = _num(bom.get(f"freight_{FREIGHT_LABELS[bucket]}"))
    elif bucket == US_OVERSEAS and method == METHOD_FINISHED:
        freight = _num(bom.get(f"freight_{FREIGHT_LABELS['USFBA']}"))
    else:
        label = FREIGHT_LABELS["USTX"] if bucket == US_OVERSEAS else FREIGHT_LABELS[bucket]
        total = _num(bom.get(f"freight_{label}"))
        cover = _num(bom.get(f"cover_freight_{label}"))
        sfg = _num(bom.get(f"sfg_freight_{label}"))
        if shape == SHAPE_COVER:
            freight = cover
        elif shape == SHAPE_FOAM:
            freight = None if total is None or cover is None else total - cover
        elif method == METHOD_COVER:
            freight = cover
        elif method == METHOD_SEMI:
            freight = sfg if sfg is not None else (
                None if total is None or cover is None else total - cover
            )
        else:  # METHOD_FINISHED
            freight = total
    if freight is None:
        return None, "bom_value_missing"

    # 二次加工
    if bucket in FBA_BUCKETS:
        processing = 0.0
    elif method == METHOD_FINISHED and bucket in ("USNJ", "USTX", "PL"):
        # 分公司发成品：国内已含加工 → 目的地二次=0；
        # 例外：美国本地采购/加工产品（无皮壳、无绍兴包装）成本只体现在目的地 valuation。
        sx = _num(bom.get("cost_sxbzcp")) or 0.0
        val = _num(bom.get({
            "USNJ": "usnj_valuation_rate",
            "USTX": "ustx_valuation_rate",
            "PL": "pl_valuation_rate",
        }[bucket]))
        processing = (val or 0.0) if (shell == 0 and sx == 0 and (val or 0) > 0) else 0.0
    elif bucket == "USNJ":
        processing = _num(bom.get("usnj_valuation_rate"))
    elif bucket in ("USTX", US_OVERSEAS):
        processing = _num(bom.get("ustx_valuation_rate"))
    elif bucket == "PL":
        processing = _num(bom.get("pl_valuation_rate"))
    else:
        return None, "warehouse_unknown"
    if processing is None:
        return None, "bom_value_missing"

    # 绍兴二次加工
    if bucket in FBA_BUCKETS:
        # FBA 成品口径：绍兴包装成品成本（cost_sxbzcp 已含半成品包装，见 95/113 行
        # sx_cost_all = cost_fg + cost_sxbzcp 的实测）；不再用 sx_cost_all−cost_fg，
        # 避免 sx_cost_all 缺失时算出负值。
        sx = _num(bom.get("cost_sxbzcp"))
    elif method == METHOD_SEMI:
        sx = _num(bom.get("cost_sxbzbcp"))
    elif method == METHOD_FINISHED:
        sx = _num(bom.get("cost_sxbzcp"))
    else:
        sx = 0.0
    if sx is None:
        return None, "bom_value_missing"

    # 单品后缀特例（EN `order_sync.py:2941-3003`，**仅非 FBA**）：
    # -COVER：绍兴发货成本=皮壳成本、头程=皮壳头程、加工成本=0 → sx/processing 归零
    # -FOAM ：绍兴发货成本=绍兴包装半成品/成品成本、头程=总额−皮壳 → 皮壳成本归零
    # -PPCOTTON（仅 method=皮壳）：绍兴发货成本=0、头程=0 → 皮壳/绍兴二次/头程归零
    if bucket not in FBA_BUCKETS:
        if shape == SHAPE_COVER:
            sx = 0.0
            processing = 0.0
        elif shape == SHAPE_FOAM and method in (METHOD_SEMI, METHOD_FINISHED):
            shell = 0.0
        elif shape == SHAPE_PPCOTTON and method == METHOD_COVER:
            shell = 0.0
            sx = 0.0
            freight = 0.0

    costs = {"shell": shell, "freight": freight, "processing": processing, "sx": sx}
    if any(v < 0 for v in costs.values()):
        return None, "negative_cost"
    return costs, ""


def _load_writeback(path: str | Path | None) -> dict[tuple[str, str], list[dict]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    df = pd.read_csv(p, dtype=str, low_memory=False, keep_default_na=False)
    index: dict[tuple[str, str], list[dict]] = {}
    for rec in df.to_dict("records"):
        key = (str(rec.get("订单号") or "").strip(), normalize_sku(rec.get("通途SKU")))
        index.setdefault(key, []).append(rec)
    return index


def _source_indices(value: object) -> list[int]:
    return [int(x) for x in str(value).split(",") if str(x).strip()]


def _writeback_totals(
    detail: dict,
    shadow: MergeShadowResult,
    wb_index: Mapping[tuple[str, str], list[dict]],
) -> tuple[int, dict[str, float]]:
    """按源行 (订单号, 通途SKU) 汇总写回表四列 × 数量。仅对账。"""
    by_index = {r.index: r for r in shadow.rows}
    rows: list[dict] = []
    for idx in _source_indices(detail.get("source_rows", "")):
        src = by_index.get(idx)
        if src is None:
            continue
        rows += wb_index.get((src.order_id, src.sku), [])
    totals = {c: 0.0 for c in WB_COST_COLUMNS}
    for rec in rows:
        qty = _num(rec.get("发货数量")) or 0.0
        for col in WB_COST_COLUMNS:
            totals[col] += (_num(rec.get(col)) or 0.0) * qty
    return len(rows), totals


def compute_phase2(
    shadow: MergeShadowResult,
    bom_csv: str | Path,
    ref_map_csv: str | Path,
    wh_tsv: str | Path,
    writeback_csv: str | Path | None = None,
    bundle_map_csv: str | Path | None = None,
    kit_report_csv: str | Path | None = None,
) -> Phase2Result:
    """对 Phase 1 合并明细逐行计算 BOM 四列成本。"""
    bom_index = load_bom_cost(bom_csv)
    resolver = EnResolver.from_items_csv(ref_map_csv)
    wh_map = load_warehouse_map(wh_tsv)
    wb_index = _load_writeback(writeback_csv)
    bundles = load_bundles(bundle_map_csv)
    kit_report = load_kit_report(kit_report_csv)

    rows: list[dict] = []
    row_details: list[dict] = []
    blocked_reasons: dict[str, int] = {}
    by_index = {r.index: r for r in shadow.rows}
    blocked_by_index: dict[int, object] = {}
    for b in shadow.blocked:
        for r in b.rows:
            blocked_by_index[r.index] = b
    rows_by_common: dict[str, list] = {}
    for r in shadow.rows:
        rows_by_common.setdefault(r.order_common, []).append(r)
    identity_violations: list[dict] = []
    suffix_violations: list[dict] = []
    for detail in shadow.detail_rows:
        item_fg = ""
        method = str(detail.get("pricing_method") or "")
        warehouse = str(detail.get("发货仓库") or "").strip()
        warehouse_class = wh_map.get(warehouse, "")
        bucket = warehouse_bucket(warehouse_class)
        pieces = _num(detail.get("pieces"))
        qty = _num(detail.get("发货数量")) or 0.0
        merged = bool(detail.get("merged"))
        units = pieces if merged else qty

        status, reason = "ok", ""
        skus = [normalize_sku(x) for x in str(detail.get("skus") or "").split(",") if x.strip()]
        is_accessory = any(is_non_product_accessory(x) for x in skus)
        is_bundle = (
            str(detail.get("product_id") or "").startswith("TJ#")
            or any(x.startswith("TJ#") for x in skus)
        )
        bundle_item = ""
        if is_bundle:
            candidates: set[str] = set()
            for s_sku in skus:
                candidates |= set(resolver.items_for_sku(s_sku))
            candidates &= set(bundles)
            if len(candidates) == 1:
                bundle_item = next(iter(candidates))
        original_reason = str(detail.get("cost_blocked_reason") or "")
        rescue_ambiguous = (
            not detail.get("cost_eligible") and "歧义" in original_reason
        )
        info = None
        kit_method = ""
        kit_diff = ""
        if is_bundle:
            info = bundles.get(bundle_item)
            b_costs = None
            if info is None:
                status, reason = "pending_bundle", "Product Bundle 未找到"
            elif not info.version:
                status, reason = "pending_bundle", "bundle_version_missing"
            else:
                audit = _bundle_audit(info.components, bom_index, bucket)
                methods = [m for m in audit["methods"] if m]
                if len(methods) != len(audit["methods"]) or not methods:
                    status, reason = "pending_bundle", "kit_method_missing"
                elif len(set(methods)) > 1:
                    status, reason = "pending_bundle", "kit_method_mixed"
                else:
                    kit_method = methods[0]
                    b_costs, b_reason = _bundle_unit_costs(info.components, bom_index, bucket)
                    if b_reason:
                        status, reason = "pending_bundle", b_reason
                    else:
                        report = kit_report.get(bundle_item)
                        if report is None:
                            status, reason = "pending_bundle", "kit_report_missing"
                        else:
                            rate_field = {
                                "USNJ": "usnj_valuation_rate",
                                "USTX": "ustx_valuation_rate",
                                "PL": "pl_valuation_rate",
                                US_OVERSEAS: "ustx_valuation_rate",
                            }.get(bucket)
                            checks = {
                                "cost_fg": (audit["shell"], _num(report.get("cost_fg"))),
                                "cost_sxbzbcp": (audit["semi"], _num(report.get("cost_sxbzbcp"))),
                                "cost_sxbzcp": (audit["fin"], _num(report.get("cost_sxbzcp"))),
                                "sx_cost_all": (
                                    audit["shell"] + audit["semi"] + audit["fin"],
                                    _num(report.get("sx_cost_all")),
                                ),
                            }
                            if rate_field:
                                checks["valuation"] = (audit["valuation"], _num(report.get(rate_field)))
                            diffs = {
                                k: round(a - b, 6)
                                for k, (a, b) in checks.items()
                                if a is not None and b is not None
                            }
                            bad = {k: v for k, v in diffs.items() if abs(v) > 0.01}
                            kit_diff = str(diffs)
                            if bad:
                                status, reason = "blocked", "kit_report_mismatch"
                            else:
                                identity = b_costs["shell"] + b_costs["sx"] + b_costs["processing"]
                                rows.append({
                                    **{c: None for c in PHASE2_COLUMNS},
                                    "group_id": detail.get("group_id"),
                                    "merged": merged,
                                    "订单号/子单": detail.get("sub_orders"),
                                    "平台SKU": detail.get("平台SKU"),
                                    "order_common": detail.get("order_common"),
                                    "SKU": detail.get("skus"),
                                    "product_id": detail.get("product_id"),
                                    "item_fg": bundle_item,
                                    "method": kit_method,
                                    "method_source": "kit_bundle",
                                    "bundle_version": info.version,
                                    "kit_method": kit_method,
                                    "kit_report_diff": kit_diff,
                                    "bom_method": kit_method,
                                    "method_diff": False,
                                    "method_diff_alt_delta": None,
                                    "warehouse_class": warehouse_class,
                                    "warehouse_bucket": bucket,
                                    "units": units,
                                    "pieces": pieces,
                                    "qty": qty,
                                    "皮壳成本": round(b_costs["shell"] * units, 6),
                                    "头程运费金额": round(b_costs["freight"] * units, 6),
                                    "二次加工成本": round(b_costs["processing"] * units, 6),
                                    "绍兴二次加工成本": round(b_costs["sx"] * units, 6),
                                    "四列合计": round(sum(b_costs.values()) * units, 6),
                                    "1件成本(不含头程)": round(identity, 6),
                                    "status": "ok",
                                    "reason": "",
                                    "suggested_items": "",
                                    "source": f"kit_bundle:{bundle_item}",
                                })
                                row_details.append(detail)
                                continue
        elif is_accessory:
            status, reason = "non_product_accessory", "非商品配件（零成本）"
        elif not detail.get("cost_eligible") and not rescue_ambiguous:
            status, reason = "skipped_ineligible", original_reason
        elif not warehouse_class:
            status, reason = "blocked", "warehouse_unknown"
        elif bucket == "":
            status, reason = "blocked", "warehouse_unknown"
        elif method not in METHODS:
            status, reason = "blocked", "method_missing"
        elif units is None or units <= 0:
            status, reason = "blocked", "units_invalid"
        else:
            anchor_items: tuple[str, ...] = ()
            context_product = ""
            if not merged:
                src_idx = _source_indices(detail.get("source_rows", ""))
                src = [by_index[i] for i in src_idx if i in by_index]
                excluded = set(src_idx)
                product_id = str(detail.get("product_id") or "")
                anchors: set[str] = set()
                for common in {r.order_common for r in src}:
                    for other in rows_by_common.get(common, []):
                        if other.index in excluded:
                            continue
                        if sku_shape(other.sku) not in (SHAPE_COVER, SHAPE_FINISHED):
                            continue
                        # 通用组件不按自身 product 过滤：用同订单 Cover/成品行锁定变体
                        its = set(resolver.items_for_sku(other.sku))
                        if len(its) == 1:
                            anchors |= its
                anchor_items = tuple(sorted(anchors))
                other_products: set[str] = set()
                for common in {r.order_common for r in src}:
                    for other in rows_by_common.get(common, []):
                        if other.index in excluded:
                            continue
                        for item in resolver.items_for_sku(other.sku):
                            product = resolver.product_for_item(item)
                            if product:
                                other_products.add(product)
                if len(other_products) == 1:
                    context_product = next(iter(other_products))
            item_fg, reason = item_for_detail(
                detail, resolver, bom_index, anchor_items, context_product,
            )
            if reason:
                status = "skipped_ineligible" if rescue_ambiguous else "blocked"
                if rescue_ambiguous:
                    reason = original_reason or reason
            else:
                bom_rows = bom_index.get(item_fg, [])
                if not bom_rows:
                    status, reason = (
                        "skipped_ineligible" if rescue_ambiguous else "blocked"
                    ), "bom_item_missing"
                elif len(bom_rows) > 1:
                    status, reason = (
                        "skipped_ineligible" if rescue_ambiguous else "blocked"
                    ), "bom_row_duplicate"
                else:
                    bom = bom_rows[0]
                    bom_method = str(bom.get("shipping_method") or "").strip()
                    en_method = str(detail.get("en_method") or "").strip()
                    # 定价 method = BOM 主档（load_orders 已按 BOM 解析）；EN method 仅审计。
                    method_source = detail.get("method_source") or ""
                    method_diff = bool(en_method and bom_method and en_method != bom_method)
                    shape = SHAPE_FINISHED if merged else sku_shape(detail.get("通途SKU"))
                    costs, reason = _unit_costs(bom, bucket, method, shape)
                    if reason:
                        status = "blocked"
                    else:
                        identity = costs["shell"] + costs["sx"] + costs["processing"]
                        alt_delta = None
                        if method_diff:
                            alt_costs, alt_reason = _unit_costs(bom, bucket, en_method, shape)
                            if not alt_reason:
                                alt_delta = round(
                                    (sum(alt_costs.values()) - sum(costs.values())) * units, 6
                                )
                        # 用 BOM 原始字段独立重算恒等式（与 _unit_costs 同一后缀矩阵）
                        if bucket in FBA_BUCKETS:
                            sx_all = _num(bom.get("sx_cost_all")) or 0.0
                            if sx_all <= 0:
                                sx_all = ((_num(bom.get("cost_fg")) or 0.0)
                                          + (_num(bom.get("cost_sxbzcp")) or 0.0))
                            en_shell = sx_all
                            en_sx, en_proc = 0.0, 0.0
                        else:
                            en_shell = _num(bom.get("cost_fg")) or 0.0
                            en_sx = (
                                (_num(bom.get("cost_sxbzbcp")) or 0.0) if method == METHOD_SEMI
                                else (_num(bom.get("cost_sxbzcp")) or 0.0) if method == METHOD_FINISHED
                                else 0.0
                            )
                            en_proc = (
                                (_num(bom.get("usnj_valuation_rate")) or 0.0) if bucket == "USNJ"
                                else (_num(bom.get("ustx_valuation_rate")) or 0.0) if bucket in ("USTX", US_OVERSEAS)
                                else (_num(bom.get("pl_valuation_rate")) or 0.0)
                            )
                            if method == METHOD_FINISHED and bucket in ("USNJ", "USTX", "PL"):
                                # 美国本地采购/加工（皮壳=0、绍兴=0）成本只在目的地 valuation
                                if not (en_shell == 0 and en_sx == 0 and en_proc > 0):
                                    en_proc = 0.0
                            if shape == SHAPE_COVER:
                                en_sx, en_proc = 0.0, 0.0
                            elif shape == SHAPE_FOAM and method in (METHOD_SEMI, METHOD_FINISHED):
                                en_shell = 0.0
                            elif shape == SHAPE_PPCOTTON and method == METHOD_COVER:
                                en_shell, en_sx = 0.0, 0.0
                        en_unit = en_shell + en_sx + en_proc
                        if abs(identity - en_unit) > 1e-6:
                            identity_violations.append({
                                "group_id": detail.get("group_id"),
                                "identity": round(identity, 6),
                                "en_unit": round(en_unit or 0.0, 6),
                            })
                        # 后缀硬闸门：防止两侧同错自洽
                        suffix_errors: list[str] = []
                        if bucket not in FBA_BUCKETS:
                            if shape == SHAPE_COVER and (costs["sx"] != 0 or costs["processing"] != 0):
                                suffix_errors.append("cover_sx_processing_nonzero")
                            if (shape == SHAPE_FOAM and method in (METHOD_SEMI, METHOD_FINISHED)
                                    and costs["shell"] != 0):
                                suffix_errors.append("foam_shell_nonzero")
                            if (shape == SHAPE_PPCOTTON and method == METHOD_COVER
                                    and (costs["shell"] != 0 or costs["sx"] != 0 or costs["freight"] != 0)):
                                suffix_errors.append("ppcotton_nonzero")
                        if suffix_errors:
                            suffix_violations.append({
                                "group_id": detail.get("group_id"),
                                "sku": detail.get("skus"),
                                "errors": suffix_errors,
                            })
                        rows.append({
                            **{c: None for c in PHASE2_COLUMNS},
                            "group_id": detail.get("group_id"),
                            "merged": merged,
                            "订单号/子单": detail.get("sub_orders"),
                            "平台SKU": detail.get("平台SKU"),
                            "order_common": detail.get("order_common"),
                            "SKU": detail.get("skus"),
                            "product_id": detail.get("product_id"),
                            "item_fg": item_fg,
                            "method": method,
                            "en_method": en_method,
                            "method_source": method_source,
                            "bundle_version": "",
                            "kit_method": "",
                            "kit_report_diff": "",
                            "bom_method": bom_method,
                            "method_diff": method_diff,
                            "method_diff_alt_delta": alt_delta,
                            "warehouse_class": warehouse_class,
                            "warehouse_bucket": bucket,
                            "units": units,
                            "pieces": pieces,
                            "qty": qty,
                            "皮壳成本": round(costs["shell"] * units, 6),
                            "头程运费金额": round(costs["freight"] * units, 6),
                            "二次加工成本": round(costs["processing"] * units, 6),
                            "绍兴二次加工成本": round(costs["sx"] * units, 6),
                            "四列合计": round(
                                (costs["shell"] + costs["freight"] + costs["processing"] + costs["sx"]) * units,
                                6,
                            ),
                            "1件成本(不含头程)": round(identity, 6),
                            "status": "ok",
                            "reason": "",
                            "suggested_items": "",
                            "source": f"BOM {item_fg}",
                        })
                        row_details.append(detail)
                        continue

        # 非商品配件：显式 0 成本，不进待审
        if status == "non_product_accessory":
            row = {c: None for c in PHASE2_COLUMNS}
            row.update({
                "group_id": detail.get("group_id"),
                "merged": merged,
                "订单号/子单": detail.get("sub_orders"),
                "平台SKU": detail.get("平台SKU"),
                "order_common": detail.get("order_common"),
                "SKU": detail.get("skus"),
                "product_id": detail.get("product_id"),
                "item_fg": "",
                "method": method,
                "method_source": detail.get("method_source") or "",
                "bom_method": "",
                "method_diff": False,
                "method_diff_alt_delta": None,
                "warehouse_class": warehouse_class,
                "warehouse_bucket": bucket,
                "units": units,
                "pieces": pieces,
                "qty": qty,
                "皮壳成本": 0.0,
                "头程运费金额": 0.0,
                "二次加工成本": 0.0,
                "绍兴二次加工成本": 0.0,
                "四列合计": 0.0,
                "1件成本(不含头程)": 0.0,
                "status": status,
                "reason": reason,
                "suggested_items": "",
                "source": "non_product_accessory",
            })
            rows.append(row)
            row_details.append(detail)
            continue

        # 未出值 / 跳过
        if status == "blocked":
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
        suggested: set[str] = set()
        ambiguous_like = (
            reason == "bom_item_ambiguous"
            or "歧义" in str(reason)
            or "载体" in str(reason)
        )
        if ambiguous_like:
            product_id = str(detail.get("product_id") or "")
            own_skus = (
                [normalize_sku(x) for x in str(detail.get("skus") or "").split(",") if x.strip()]
                if detail.get("merged") else [normalize_sku(detail.get("通途SKU"))]
            )
            for s_sku in own_skus:
                items = set(resolver.items_for_sku(s_sku))
                suggested |= _same_product(items, product_id, resolver) if product_id else items
            suggested |= {i for i in anchor_items if i}
            for idx in _source_indices(detail.get("source_rows", "")):
                b = blocked_by_index.get(idx)
                if b is not None:
                    for b_sku in getattr(b, "skus", []):
                        items = set(resolver.items_for_sku(b_sku))
                        suggested |= _same_product(items, product_id, resolver) if product_id else items
        row = {c: None for c in PHASE2_COLUMNS}
        row.update({
            "group_id": detail.get("group_id"),
            "merged": merged,
            "订单号/子单": detail.get("sub_orders"),
            "平台SKU": detail.get("平台SKU"),
            "order_common": detail.get("order_common"),
            "SKU": detail.get("skus"),
            "product_id": detail.get("product_id"),
            "item_fg": item_fg,
            "method": method,
            "method_source": "kit_bundle" if is_bundle else (detail.get("method_source") or ""),
            "bundle_version": info.version if info else "",
            "kit_method": kit_method,
            "kit_report_diff": kit_diff,
            "bom_method": "",
            "method_diff": False,
            "method_diff_alt_delta": None,
            "warehouse_class": warehouse_class,
            "warehouse_bucket": bucket,
            "units": units,
            "pieces": pieces,
            "qty": qty,
            "status": status,
            "reason": reason or str(detail.get("cost_blocked_reason") or ""),
            "suggested_items": ", ".join(sorted(suggested)),
            "source": "BOM" if item_fg else "",
        })
        rows.append(row)
        row_details.append(detail)

    # 写回对账（仅对账）
    for row, detail in zip(rows, row_details):
        matched, wb_totals = _writeback_totals(detail, shadow, wb_index)
        row["wb匹配行数"] = matched
        for col in WB_COST_COLUMNS:
            wb_val = round(wb_totals[col], 6) if wb_index else None
            row[f"wb_{col}"] = wb_val
            ours = row.get(col)
            row[f"diff_vs_writeback_{col}"] = (
                None if wb_val is None or ours is None else round(ours - wb_val, 6)
            )
        diffs = [row[f"diff_vs_writeback_{c}"] for c in WB_COST_COLUMNS]
        row["diff_vs_writeback_合计"] = (
            None if any(d is None for d in diffs) else round(sum(diffs), 6)
        )

    # 组件吸收：通用海绵/PP棉行若同订单的皮壳/成品行已定价且数量匹配，
    # 说明成本已含在成品 BOM 内 → 显式 0，避免重复计。
    covers_by_order: dict[str, list[dict]] = {}
    for r in rows:
        if r["status"] != "ok":
            continue
        sku_text = str(r.get("SKU") or "")
        if sku_text and sku_shape(sku_text.split(",")[0]) == SHAPE_COVER:
            covers_by_order.setdefault(str(r.get("order_common") or ""), []).append(r)
    for r in rows:
        if r["status"] != "blocked" or r.get("reason") != "bom_item_ambiguous":
            continue
        sku_text = str(r.get("SKU") or "")
        first = sku_text.split(",")[0]
        is_component = "PPCOTTON" in first.upper() or sku_shape(first) == SHAPE_FOAM
        if not is_component:
            continue
        covers = covers_by_order.get(str(r.get("order_common") or ""), [])
        cover_qty = sum(float(c.get("units") or 0.0) for c in covers)
        if covers and abs(cover_qty - float(r.get("units") or 0.0)) <= TOL:
            for c in PHASE2_COST_COLUMNS:
                r[c] = 0.0
            r["四列合计"] = 0.0
            r["1件成本(不含头程)"] = 0.0
            r["status"] = "component_absorbed"
            r["reason"] = "组件成本已并入同订单皮壳/成品行"
            r["source"] = "absorbed_into_covers"

    # 双计守卫：同订单既出现 TJ# 套件行、又出现其子件行 → 阻断，禁止静默去重
    for r in rows:
        if r.get("method_source") != "kit_bundle":
            continue
        info = bundles.get(str(r.get("item_fg") or ""))
        if info is None:
            continue
        children = {c for c, _ in info.components}
        for other in rows:
            if other is r or other.get("order_common") != r.get("order_common"):
                continue
            if str(other.get("item_fg") or "") in children:
                r["status"] = other["status"] = "blocked"
                r["reason"] = other["reason"] = "kit_child_double_count"
                for c in PHASE2_COST_COLUMNS:
                    r[c] = other[c] = None
                r["四列合计"] = other["四列合计"] = None
                r["1件成本(不含头程)"] = other["1件成本(不含头程)"] = None

    blocked_reasons = dict(Counter(r["reason"] for r in rows if r["status"] == "blocked"))
    priced = [r for r in rows if r["status"] == "ok"]
    skipped = [r for r in rows if r["status"] == "skipped_ineligible"]
    blocked = [r for r in rows if r["status"] == "blocked"]
    kit_rows = [r for r in rows if r.get("method_source") == "kit_bundle"]
    kit_priced = [r for r in kit_rows if r["status"] == "ok"]
    kit_pending = [r for r in kit_rows if r["status"] == "pending_bundle"]
    kit_method_counts = dict(Counter(r.get("kit_method") or "unresolved" for r in kit_rows))
    kit_reconcile_fail = sum(1 for r in kit_rows if r["status"] == "blocked" and r.get("reason") == "kit_report_mismatch")
    kit_double = sum(1 for r in rows if r.get("reason") == "kit_child_double_count")
    zero_cost = [r for r in rows if r["status"] == "non_product_accessory"]
    absorbed = [r for r in rows if r["status"] == "component_absorbed"]
    pending = [r for r in rows if r["status"] == "pending_bundle"]
    totals = {
        c: round(sum(float(r[c] or 0.0) for r in priced), 6)
        for c in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本", "四列合计")
    }
    method_totals: dict[str, dict] = {}
    for m in METHODS:
        mrows = [r for r in priced if r["method"] == m]
        method_totals[m] = {
            "rows": len(mrows),
            **{
                c: round(sum(float(r[c] or 0.0) for r in mrows), 6)
                for c in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本")
            },
        }
    diff_values = [
        abs(float(r[f"diff_vs_writeback_{c}"]))
        for r in priced for c in WB_COST_COLUMNS
        if r[f"diff_vs_writeback_{c}"] is not None
    ]
    diff_nonzero = sum(
        1 for r in priced for c in WB_COST_COLUMNS
        if r[f"diff_vs_writeback_{c}"] not in (None, 0)
    )

    identity_status = (
        "fail" if identity_violations
        else ("skip" if not priced else "pass")
    )
    integrity_status = (
        "fail" if (blocked or pending)
        else ("skip" if not priced else "pass")
    )
    assertions = [
        Assertion(
            name="BOM 成本完整性",
            status=integrity_status,
            checked=len(rows),
            detail=(
                f"可定价 {len(priced)} 行；阻断 {len(blocked)} 行；跳过 {len(skipped)} 行；"
                f"非商品配件 0 成本 {len(zero_cost)} 行；套件待审 {len(pending)} 行"
                + (f"；阻断原因 {blocked_reasons}" if blocked_reasons else "")
            ),
            violations=[{"reason": k, "rows": v} for k, v in blocked_reasons.items()],
        ),
        Assertion(
            name="EN 1件成本恒等式",
            status=identity_status,
            checked=len(priced),
            detail=(
                f"{len(priced)} 行满足 皮壳+绍兴二次+二次 = BOM 1件成本（不含头程）"
                if not identity_violations
                else f"{len(identity_violations)} 行不满足恒等式"
            ),
            violations=identity_violations[:20],
        ),
        Assertion(
            name="单品后缀成本口径",
            status="fail" if suffix_violations else ("skip" if not priced else "pass"),
            checked=len(priced),
            detail=(
                "-COVER 绍兴二次/二次=0；-FOAM 皮壳=0；-PPCOTTON(皮壳) 皮壳/绍兴二次/头程=0（仅非 FBA）"
                if not suffix_violations
                else f"{len(suffix_violations)} 行违反后缀口径"
            ),
            violations=suffix_violations[:20],
        ),
        Assertion(
            name="写回对账（仅对账）",
            status="skip",
            checked=len(priced),
            detail=(
                f"写回表匹配 {sum(1 for r in priced if (r.get('wb匹配行数') or 0) > 0)} 行；"
                f"非零差异 {diff_nonzero} 项；绝对差合计 {round(sum(diff_values), 6):g}"
                + ("" if wb_index else "；未提供写回表")
            ),
            skipped=len(priced),
            skip_reasons={"仅对账，不采信写回表": len(priced)},
        ),
    ]
    stats = {
        "phase2_rows": len(rows),
        "phase2_priced": len(priced),
        "phase2_blocked": len(blocked),
        "phase2_skipped": len(skipped),
        "phase2_zero_cost": len(zero_cost),
        "phase2_component_absorbed": len(absorbed),
        "phase2_pending_bundle": len(pending),
        "phase2_kit_priced": len(kit_priced),
        "phase2_kit_pending": len(kit_pending),
        "kit_method_counts": kit_method_counts,
        "phase2_kit_reconcile_fail": kit_reconcile_fail,
        "phase2_kit_double_count": kit_double,
        "phase2_blocked_reasons": blocked_reasons,
        "phase2_method_diff_rows": sum(1 for r in rows if r.get("method_diff")),
        "phase2_method_diff_alt_delta": round(
            sum(float(r["method_diff_alt_delta"] or 0.0) for r in rows), 6
        ),
        "phase2_totals": totals,
        "phase2_method_totals": method_totals,
        "phase2_identity_status": identity_status,
        "phase2_integrity_status": integrity_status,
        "phase2_wb_nonzero_diffs": diff_nonzero,
        "phase2_wb_abs_diff": round(sum(diff_values), 6),
        "phase2_wb_rows_matched": sum(1 for r in priced if (r.get("wb匹配行数") or 0) > 0),
        "phase2_assertion_status": {a.name: a.status for a in assertions},
    }
    return Phase2Result(rows=rows, assertions=assertions, stats=stats)


def phase2_diff_breakdown(phase2: Phase2Result) -> list[dict]:
    """写回差异归因：列 × method × 合并/透传 × status × method_diff。"""
    buckets: dict[tuple, dict] = {}
    for row in phase2.rows:
        for col in WB_COST_COLUMNS:
            key = (
                col, row.get("method") or "-",
                "合并" if row.get("merged") else "透传",
                row.get("status") or "-",
                "是" if row.get("method_diff") else "否",
            )
            item = buckets.setdefault(key, {
                "列": col,
                "method": key[1],
                "合并/透传": key[2],
                "status": key[3],
                "method_diff": key[4],
                "行数": 0,
                "我方合计": 0.0,
                "写回合计": 0.0,
                "差异(我方−写回)": 0.0,
                "绝对差": 0.0,
                "可比": True,
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
    out = list(buckets.values())
    for item in out:
        for k in ("我方合计", "写回合计", "差异(我方−写回)", "绝对差"):
            item[k] = round(item[k], 6)
    return sorted(out, key=lambda x: (x["列"], x["method"], x["合并/透传"], x["status"], x["method_diff"]))


def phase2_summary_rows(phase2: Phase2Result) -> list[dict]:
    s = phase2.stats
    totals = s["phase2_totals"]
    return [
        {"指标": "Phase2 可定价行", "值": s["phase2_priced"]},
        {"指标": "Phase2 阻断行", "值": s["phase2_blocked"]},
        {"指标": "Phase2 跳过行（Phase1 不可定价）", "值": s["phase2_skipped"]},
        {"指标": "Phase2 非商品配件 0 成本行", "值": s["phase2_zero_cost"]},
        {"指标": "Phase2 套件待审行", "值": s["phase2_pending_bundle"]},
        {"指标": "Phase2 套件可定价 / 待审", "值": f"{s['phase2_kit_priced']} / {s['phase2_kit_pending']}"},
        {"指标": "Phase2 kit_method 分布", "值": str(s["kit_method_counts"])},
        {"指标": "Phase2 套件报表对账失败 / 双计阻断", "值": f"{s['phase2_kit_reconcile_fail']} / {s['phase2_kit_double_count']}"},
        {"指标": "Phase2 阻断原因", "值": str(s["phase2_blocked_reasons"] or "无")},
        {"指标": "Phase2 BOM/EN method 不一致行（按 EN 定价）", "值": s["phase2_method_diff_rows"]},
        {"指标": "Phase2 若按 BOM method 定价的差异（审计）", "值": s["phase2_method_diff_alt_delta"]},
        {"指标": "Phase2 皮壳成本合计", "值": totals["皮壳成本"]},
        {"指标": "Phase2 头程运费合计", "值": totals["头程运费金额"]},
        {"指标": "Phase2 二次加工合计", "值": totals["二次加工成本"]},
        {"指标": "Phase2 绍兴二次加工合计", "值": totals["绍兴二次加工成本"]},
        {"指标": "Phase2 四列合计", "值": totals["四列合计"]},
        {"指标": "Phase2 写回对账非零差异", "值": f"{s['phase2_wb_nonzero_diffs']} 项；绝对差 {s['phase2_wb_abs_diff']:g}（仅对账）"},
        {"指标": "Phase2 断言", "值": " / ".join(
            f"{k}:{'通过' if v == 'pass' else '阻断' if v == 'fail' else '跳过'}"
            for k, v in s["phase2_assertion_status"].items()
        )},
    ]


def phase2_markdown(phase2: Phase2Result) -> str:
    s = phase2.stats
    totals = s["phase2_totals"]
    lines = [
        "",
        "## Phase 2 — BOM Cost List 单位成本 × 件数",
        "",
        "> 合并组按 pieces、透传行按 qty 乘；写回表四列仅对账、不采信。",
        "",
        f"- 可定价行：{s['phase2_priced']}；阻断：{s['phase2_blocked']}；"
        f"跳过（Phase1 不可定价）：{s['phase2_skipped']}；"
        f"非商品配件 0 成本：{s['phase2_zero_cost']}；套件待审：{s['phase2_pending_bundle']}",
        f"- 四列合计：皮壳 {totals['皮壳成本']:g} / 头程 {totals['头程运费金额']:g} / "
        f"二次加工 {totals['二次加工成本']:g} / 绍兴二次 {totals['绍兴二次加工成本']:g}；"
        f"四列合计 {totals['四列合计']:g}",
        f"- BOM/EN method 不一致：{s['phase2_method_diff_rows']} 行（按 EN method 定价；"
        f"若按 BOM method 审计差异 {s['phase2_method_diff_alt_delta']:g}）",
        f"- 写回对账：非零差异 {s['phase2_wb_nonzero_diffs']} 项；绝对差 {s['phase2_wb_abs_diff']:g}（仅对账）",
        f"- 断言：{' / '.join(f'{k}:{v}' for k, v in s['phase2_assertion_status'].items())}",
        "",
        "| method | 可定价行 | 皮壳成本 | 头程运费 | 二次加工 | 绍兴二次 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in METHODS:
        mt = s["phase2_method_totals"].get(m, {})
        lines.append(
            f"| {m} | {mt.get('rows', 0)} | {mt.get('皮壳成本', 0):g} | "
            f"{mt.get('头程运费金额', 0):g} | {mt.get('二次加工成本', 0):g} | "
            f"{mt.get('绍兴二次加工成本', 0):g} |"
        )
    if s["phase2_blocked_reasons"]:
        lines += ["", "**Phase 2 阻断原因**：" + "；".join(
            f"{k} {v}" for k, v in s["phase2_blocked_reasons"].items()
        )]
    lines.append("")
    return "\n".join(lines)
