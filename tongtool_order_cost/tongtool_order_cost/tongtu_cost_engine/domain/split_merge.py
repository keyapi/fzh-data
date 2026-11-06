# -*- coding: utf-8 -*-
"""Phase 1.2 domain：拆包合并 shadow（只读，不改成本列、不写 GS/EN）。

合并触发 = **结构分组 ∩ EN 同一产品**：
- 结构分组复用 `ustx_cost_compare.group_split_rows`（键 = 订单号公共部分 + 平台SKU）；
- 再加 EN 产品守卫（`通途SKU → customer_code 别名 → Item → 产品`），组内 product_id 必须一致。

定价口径（用户 2026-11-04 明确）：
- **一律以 EN `Tongtool Order` 明细的 `shipping_method`（绍兴发货方式）为准**；
- GS/写回表的 `当月给分公司发货类型` 可能不准，**只作参考、不参与定价**，本模块只原样透传；
- `split_package_cost_factor` 与 EN 存储的 `cost_fg/cost_sxbzbcp/cost_sxbzcp` **只作对账/兜底参考，
  不参与主计算**（aux 表里只展示，不进入成本逻辑）。

EN 作废原单（aux）：
- 从快照 `en_items_all_089.csv` 读 `order_flags.invalid=1` 的原单行；
- 按 `order_common_part + 产品` 关联到合并组，校验件数/金额/产品/method；
- 不一致 → 阻断；组内无明确载体/子单歧义时，用原单的件数/载体兜底；
- **原单行不进入合并明细、不与子单叠加计数**，只做校验与兜底元数据。

铁律：
- **歧义即阻断**：别名命中多个产品 / 组内 method 缺失或混用 / 多个载体候选 /
  载体行身份字段冲突 / aux 不一致 → 不合并、原样透传并进阻断清单；禁止 first/max 兜底。
- **不可定价必须显式标记**：阻断组、未登记、歧义、method 缺失的行输出
  `cost_eligible=False` + `cost_blocked_reason`，Phase 2 不得自动定价。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from ...ustx_cost_compare import group_split_rows, order_common_part
from ...order_side_input import tiktok_platform_body

# ─────────────────────────── 常量 ───────────────────────────

TOL = 1e-6

# 载体形态（仅用于组内挑行 / 单品后缀计价，不代表交付语义）
SHAPE_FINISHED = "finished"
SHAPE_COVER = "cover"
SHAPE_FOAM = "foam"
SHAPE_PPCOTTON = "ppcotton"

# EN shipping_method 的三种交付语义（定价唯一依据）
METHOD_COVER = "皮壳"
METHOD_SEMI = "半成品"
METHOD_FINISHED = "成品"
METHODS: tuple[str, ...] = (METHOD_COVER, METHOD_SEMI, METHOD_FINISHED)

# 非商品配件/耗材（显式零成本，不进待审成本）
ACCESSORY_EXACT: frozenset[str] = frozenset({
    "BUTTONKIT", "BUTTONKIT-PL", "DLZYFX001", "COTTON-EU",
})
_ACCESSORY_PP_RE = re.compile(r"^PP\d+(?:\.\d+)?LB$")


def is_non_product_accessory(sku: object) -> bool:
    s = normalize_sku(sku)
    return bool(s) and (s in ACCESSORY_EXACT or bool(_ACCESSORY_PP_RE.match(s)))

_STATUS_RESOLVED = "resolved"
_STATUS_UNRESOLVED = "unresolved"
_STATUS_AMBIGUOUS = "ambiguous"

_STATUS_CN = {
    _STATUS_RESOLVED: "已覆盖",
    _STATUS_UNRESOLVED: "SKU未登记",
    _STATUS_AMBIGUOUS: "SKU别名歧义",
}

REQUIRED_ORDER_COLUMNS: tuple[str, ...] = (
    "订单号",
    "平台SKU",
    "通途SKU",
    "发货数量",
    "售价",
    "售价(人民币)",
)

REQUIRED_EN_ITEM_COLUMNS: tuple[str, ...] = (
    "order_id_code",
    "tongtool_sku",
    "shipping_method",
)

# 写回表有「运费」；月度 raw 快照没有该列。缺列时跳过该列校验，不补 0 假装有值。
FREIGHT_COLUMN = "运费"

REQUIRED_ITEM_COLUMNS: tuple[str, ...] = ("name", "customer_code", "variant_of")

# TT SKU 末尾 `-1`/`-2` 是拆单/包裹/补发序号（非 TT SKU 的 -N 是尺寸，不能剥）
_TT_PACKAGE_SUFFIX_RE = re.compile(r"-\d{1,2}$")
_COVER_SKU_RE = re.compile(r"COVER")
_FOAM_SKU_RE = re.compile(r"FOAM")

# 载体行身份字段：这些列在同一载体的多张子单间必须一致；不一致 → 阻断。
# 故意排除 订单号/包裹号/产品名称/通途SKU——拆单包裹本来就不同。
IDENTITY_COLUMNS: tuple[str, ...] = (
    "平台SKU",
    "发货仓库",
    "品类",
    "渠道",
    "渠道账号",
    "邮寄方式",
    "解析后SKU",
)

# 合并明细附加列（原行全部列之后追加）
DETAIL_EXTRA_COLUMNS: tuple[str, ...] = (
    "group_id",
    "product_id",
    "order_common",
    "platform_sku",
    "carrier_sku",
    "role",
    "pricing_method",
    "method_source",
    "merged",
    "shipping_method",
    "当月给分公司发货类型",
    "cost_eligible",
    "cost_blocked",
    "cost_blocked_reason",
    "resolution_status",
    "pieces",
    "pieces_source",
    "skus",
    "sub_orders",
    "source_rows",
    "blocked_reason",
)

AUX_COLUMNS: tuple[str, ...] = (
    "原单号",
    "order_common",
    "产品",
    "method",
    "qty",
    "原始组件qty",
    "SKU",
    "关联group_id",
    "关联月",
    "跨月",
    "子单qty",
    "校验结果",
    "原因",
    "是否用于兜底",
    "cost_fg合计(仅对账)",
    "factor(仅对账)",
)

_BLOCK_REASONS = {
    "method_missing": "组件缺 EN shipping_method（交付语义未知）",
    "mixed_methods": "组内 EN shipping_method 不一致",
    "multiple_carrier_skus": "组内多个载体 SKU（无法唯一确定成本载体）",
    "multiple_cover_skus": "组内多个皮壳 SKU（无法唯一确定成本载体）",
    "carrier_identity_conflict": "组内载体行身份字段不一致（平台/仓库/渠道等）",
    "no_carrier": "组内找不到载体行",
    "pieces_zero": "件数为 0",
    "pieces_ambiguous": "成品行只有拆单尾号，件数无法唯一确定",
    "aux_qty_mismatch": "EN 原单件数 ≠ 有效子单之和",
    "aux_method_mismatch": "EN 原单 method ≠ 有效子单 method",
    "aux_ambiguous": "同一原单+产品存在多个 EN 原单条目",
}

# EN ref_code 等价性说明（输出到 Markdown，依据 docs 29 / 20）
REF_CODE_EQUIVALENCE = (
    "**EN 解析依据（customer_code → variant_of）**：源表为 EN `tabItem` 的 "
    "`customer_code`（逗号分隔的通途SKU/客户码别名，并含 Item name 本身），"
    "`variant_of` 指向父产品。`docs/reference/cost-engine-spec/29-review-brief-for-codex.md` §5 "
    "已实证 `importBOMCostList.客户物料号 == 通途SKU == EN Item Customer Detail.ref_code`，"
    "即 EN 侧 ref_code 与 Item 是同一登记体系；本引擎把同一 Item 的多个别名归到 "
    "`variant_of`（无则 name）这一产品粒度，所以「别名→Item→产品」与「ref_code→Item→产品」同构。"
    "**风险**：ref_code 无 DB 唯一约束、保存时校验可能保留旧重复"
    "（`docs/reference/cost-engine-spec/20-codex-round3-corrections.md`），"
    "因此精确命中多个产品一律标记歧义并阻断，不转基码、不取 first；未命中同样不合并，"
    "全部列入「SKU 覆盖」未覆盖清单。"
)

PRICING_BASIS_NOTE = (
    "**定价依据**：一律用 EN `shipping_method`（绍兴发货方式）；"
    "GS/写回表 `当月给分公司发货类型` 只作参考、不参与定价。"
    "`split_package_cost_factor` 与 EN 存储 `cost_fg/cost_sxbzbcp/cost_sxbzcp` "
    "只作对账/兜底参考，不参与主计算。"
)


# ─────────────────────────── SKU 归一化 / 形态 ───────────────────────────


def normalize_sku(sku: object) -> str:
    """SKU 归一化：去全部空白 + 大写。空值/`nan` → 空串。"""
    if sku is None:
        return ""
    s = str(sku)
    if s.strip().lower() in ("", "nan", "none"):
        return ""
    return re.sub(r"\s+", "", s).upper()


def normalize_alias(sku: object) -> str:
    """别名归一化：去空格/连字符/下划线 + 大写（仅用于 customer_code 别名匹配）。"""
    return re.sub(r"[-_]", "", normalize_sku(sku))


def sku_base(sku: object) -> str:
    """去掉 TT SKU 末尾 1–2 位拆单/包裹/补发序号；其他 SKU 原样。"""
    s = normalize_sku(sku)
    if s.startswith("TT"):
        s = _TT_PACKAGE_SUFFIX_RE.sub("", s)
    return s


def sku_shape(sku: object) -> str:
    """SKU 形态：含 COVER→皮壳、含 FOAM→海绵、含 PPCOTTON→PP棉、其余→成品形态。

    注意：这不是交付语义；交付语义一律取 EN `shipping_method`。
    单品后缀计价（EN `order_sync.py:2941-3003`）只对非 FBA、非合并组生效。
    """
    base = sku_base(sku)
    if _COVER_SKU_RE.search(base):
        return SHAPE_COVER
    if _FOAM_SKU_RE.search(base):
        return SHAPE_FOAM
    if "PPCOTTON" in base:
        return SHAPE_PPCOTTON
    return SHAPE_FINISHED


# ─────────────────────────── EN 解析器 ───────────────────────────


@dataclass(frozen=True)
class Resolution:
    sku: str
    status: str
    product_id: str = ""
    item_names: tuple[str, ...] = ()
    products: tuple[str, ...] = ()


class EnResolver:
    """`customer_code` 别名 + Item name → 唯一 EN 产品。

    别名命中：
    - 0 个产品 → `unresolved`；
    - >1 个产品 → `ambiguous`（不猜、不取 first）；
    - 1 个产品 → `resolved`。同一产品的多个 Item（变体）属正常的「多对一」。
    """

    def __init__(
        self,
        alias_map: Mapping[str, Mapping[str, Iterable[str]]],
        product_group: Mapping[str, str] | None = None,
        item_product: Mapping[str, str] | None = None,
        item_group: Mapping[str, str] | None = None,
    ):
        self._alias: dict[str, dict[str, frozenset[str]]] = {
            k: {p: frozenset(names) for p, names in v.items()}
            for k, v in alias_map.items()
        }
        self._alias_items: dict[str, frozenset[str]] = {
            k: frozenset(n for names in v.values() for n in names)
            for k, v in alias_map.items()
        }
        self._product_group = dict(product_group or {})
        self._item_product = dict(item_product or {})
        self._item_group = dict(item_group or {})

    @classmethod
    def from_items_csv(cls, path: str | Path) -> "EnResolver":
        df = pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False)
        missing = [c for c in REQUIRED_ITEM_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"EN 物料表缺列: {missing}")
        group_col = "item_group" if "item_group" in df.columns else None
        alias_map: dict[str, dict[str, set[str]]] = {}
        product_group: dict[str, str] = {}
        item_product: dict[str, str] = {}
        item_group: dict[str, str] = {}
        for rec in df.to_dict("records"):
            name = str(rec.get("name") or "").strip()
            if not name:
                continue
            product = str(rec.get("variant_of") or "").strip() or name
            item_product[name] = product
            if group_col:
                item_group[name] = str(rec.get(group_col) or "").strip()
            if group_col and not product_group.get(product):
                product_group[product] = str(rec.get(group_col) or "").strip()
            aliases = [name] + str(rec.get("customer_code") or "").split(",")
            for alias in aliases:
                key = normalize_alias(alias)
                if not key:
                    continue
                alias_map.setdefault(key, {}).setdefault(product, set()).add(name)
        return cls(alias_map, product_group, item_product, item_group)

    @property
    def alias_count(self) -> int:
        return len(self._alias)

    def item_group_for(self, product_id: str) -> str:
        return self._product_group.get(product_id, "")

    def product_for_item(self, item_code: object) -> str:
        """EN Item 物料号 → 产品（variant_of 优先）；未登记返回空串。"""
        return self._item_product.get(str(item_code or "").strip(), "")

    def item_group_for_item(self, item_code: object) -> str:
        return self._item_group.get(str(item_code or "").strip(), "")

    def items_for_sku(self, sku: object) -> tuple[str, ...]:
        """通途SKU 别名 → 唯一 Item 物料号集合；未登记/多候选由调用方判断。"""
        return tuple(sorted(self._alias_items.get(normalize_alias(sku), ())))

    def resolve(self, sku: object) -> Resolution:
        key = normalize_alias(sku)
        hits = self._alias.get(key)
        if not hits:
            return Resolution(key, _STATUS_UNRESOLVED)
        products = tuple(sorted(hits))
        item_names = tuple(sorted({n for names in hits.values() for n in names}))
        if len(products) > 1:
            return Resolution(key, _STATUS_AMBIGUOUS, item_names=item_names, products=products)
        return Resolution(
            key, _STATUS_RESOLVED, product_id=products[0],
            item_names=item_names, products=products,
        )


# ─────────────────────────── item_group → branch / method 兜底 ───────────────────────────


def load_branch_map(path: str | Path) -> dict[str, dict]:
    """`item_group_branch.tsv` → {name: {"branch":..., "parent":...}}。"""
    out: dict[str, dict] = {}
    for line in Path(path).read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        parts = line.split("	")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        if not name or name == "name":
            continue
        out[name] = {
            "branch": parts[1].strip(),
            "parent": parts[2].strip() if len(parts) > 2 else "",
        }
    return out


def branch_for_group(branch_map: Mapping[str, dict], group: str) -> str:
    """向上找最近非空 branch；无则空串。"""
    current = str(group or "").strip()
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        node = branch_map.get(current)
        if not node:
            return ""
        if node.get("branch"):
            return node["branch"]
        current = node.get("parent", "")
    return ""


def fallback_method(
    resolver: EnResolver,
    branch_map: Mapping[str, dict],
    sku: object,
) -> tuple[str, str]:
    """EN shipping_method 为空时的兜底：SKU→Item→item_group→branch。

    返回 `(method, source)`；source=item_group_fallback / pending。
    """
    items = resolver.items_for_sku(sku)
    if len(items) != 1:
        return "", "pending"
    group = resolver.item_group_for_item(items[0])
    if not group:
        return "", "pending"
    branch = branch_for_group(branch_map, group)
    if branch in METHODS:
        return branch, "item_group_fallback"
    return "", "pending"


# ─────────────────────────── EN shipping_method ───────────────────────────


def load_method_map(en_items_csv: str | Path) -> dict[tuple[str, str], str]:
    """`(order_id_code, 归一化通途SKU) → shipping_method`。

    同一键出现多个不同 method → 记为 `""`（未知，组内会阻断），不取 first。
    """
    df = pd.read_csv(en_items_csv, dtype=str, low_memory=False, keep_default_na=False)
    missing = [c for c in REQUIRED_EN_ITEM_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"EN 订单明细缺列: {missing}")
    seen: dict[tuple[str, str], set[str]] = {}
    for rec in df.to_dict("records"):
        key = (str(rec.get("order_id_code") or "").strip(), normalize_sku(rec.get("tongtool_sku")))
        method = str(rec.get("shipping_method") or "").strip()
        if not key[1]:
            continue
        seen.setdefault(key, set()).add(method)
    return {k: next(iter(v)) if len(v) == 1 else "" for k, v in seen.items()}


def load_en_line_map(en_items_csv: str | Path) -> dict[tuple[str, str], frozenset[str]]:
    """`(order_id_code, 归一化通途SKU) → EN 行 erp_item_code 集合`。

    EN 订单明细行是**行级权威**（单独卖皮壳/海绵/PP棉时，只有 EN 行知道卖的是哪一个物料）。
    同一键出现多个不同 `erp_item_code` 时保留多值，调用方必须阻断，不得取 first。
    列不存在或值为空 → 空集合（回退别名解析）。
    """
    df = pd.read_csv(en_items_csv, dtype=str, low_memory=False, keep_default_na=False)
    if "erp_item_code" not in df.columns:
        return {}
    out: dict[tuple[str, str], set[str]] = {}
    for rec in df.to_dict("records"):
        oid = str(rec.get("order_id_code") or "").strip()
        sku = normalize_sku(rec.get("tongtool_sku"))
        item = str(rec.get("erp_item_code") or "").strip()
        if not oid or not sku or not item or item.upper() in {"NULL", "NONE", "-"}:
            continue
        out.setdefault((oid, sku), set()).add(item)
    return {k: frozenset(v) for k, v in out.items()}


# ─────────────────────────── EN 作废原单（aux） ───────────────────────────


@dataclass(frozen=True)
class AuxRow:
    """EN 作废原单行（只读元数据，不进合并明细）。"""

    order_id: str
    sku: str
    qty: float
    shipping_method: str
    item_code: str
    product_id: str
    cost_fg: float
    factor: float
    raw: dict = field(default_factory=dict)


@dataclass
class AuxEntry:
    """同一 (原单号, 产品) 的 EN 原单行集合。"""

    order_id: str
    product_id: str
    rows: list[AuxRow]

    @property
    def qty(self) -> float:
        return round(sum(r.qty for r in self.rows), 6)

    @property
    def methods(self) -> list[str]:
        return sorted({r.shipping_method for r in self.rows if r.shipping_method})

    @property
    def skus(self) -> list[str]:
        return sorted({r.sku for r in self.rows if r.sku})

    @property
    def cost_fg(self) -> float:
        return round(sum(r.cost_fg for r in self.rows), 6)

    @property
    def factors(self) -> list[float]:
        return sorted({r.factor for r in self.rows})

    @property
    def pieces(self) -> float:
        """原单件数：有 Cover → ΣCover qty；否则成品/整件行取其一（不相加）。"""
        return _pieces_of(self.rows)

    @property
    def duplicate_components(self) -> bool:
        """原单是否存在重复组件行（同一 SKU 出现 ≥2 次）→ qty 合计不可用。"""
        counts: Counter = Counter(r.sku for r in self.rows if r.sku)
        return any(n > 1 for n in counts.values())


def load_aux_original(
    en_items_csv: str | Path,
    invalid_ids: set[str],
    resolver: EnResolver,
) -> list[AuxRow]:
    """从 EN 明细读 `order_flags.invalid=1` 的原单行。"""
    if not invalid_ids:
        return []
    df = pd.read_csv(en_items_csv, dtype=str, low_memory=False, keep_default_na=False)
    missing = [c for c in REQUIRED_EN_ITEM_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"EN 订单明细缺列: {missing}")
    out: list[AuxRow] = []
    for rec in df.to_dict("records"):
        order_id = str(rec.get("order_id_code") or "").strip()
        if order_id not in invalid_ids:
            continue
        sku = normalize_sku(rec.get("tongtool_sku"))
        item_code = str(rec.get("erp_item_code") or "").strip()
        product = resolver.product_for_item(item_code)
        if not product and sku:
            product = resolver.resolve(sku).product_id
        out.append(AuxRow(
            order_id=order_id,
            sku=sku,
            qty=_to_float(rec.get("quantity")),
            shipping_method=str(rec.get("shipping_method") or "").strip(),
            item_code=item_code,
            product_id=product,
            cost_fg=_to_float(rec.get("cost_fg")),
            factor=_to_float(rec.get("split_package_cost_factor")),
            raw=dict(rec),
        ))
    return out


def _pieces_of(rows: Sequence) -> float:
    """统一件数口径：有 Cover 行 → ΣCover qty；否则成品/整件行取其一（不相加）。

    适用于订单子单行与 EN 原单行。`_1/_2` 同产品整件行只取基行，避免把包裹行相加。
    """
    covers = [r for r in rows if sku_shape(r.sku) == SHAPE_COVER]
    if covers:
        return round(sum(r.qty for r in covers), 6)
    whole = [r for r in rows if sku_shape(r.sku) == SHAPE_FINISHED]
    if not whole:
        return 0.0
    exact = [r for r in whole if r.sku == sku_base(r.sku)]
    pool = exact or sorted(whole, key=lambda r: str(r.sku))
    return round(pool[0].qty, 6)


def build_aux_entries(aux_rows: Sequence[AuxRow]) -> list[AuxEntry]:
    buckets: dict[tuple[str, str], list[AuxRow]] = {}
    for row in aux_rows:
        buckets.setdefault((row.order_id, row.product_id), []).append(row)
    return [
        AuxEntry(order_id=key[0], product_id=key[1], rows=rows)
        for key, rows in sorted(buckets.items())
    ]


def _aux_links(order_id: str, common: str) -> bool:
    """原单号与组公共订单号是否指向同一单（含嵌套拆单尾号）。"""
    return (
        order_id == common
        or order_common_part(order_id) == common
        or order_id == order_common_part(common)
    )


def _aux_index(entries: Sequence[AuxEntry]) -> dict[str, list[AuxEntry]]:
    index: dict[str, list[AuxEntry]] = {}
    for entry in entries:
        for key in {entry.order_id, order_common_part(entry.order_id)}:
            if key:
                index.setdefault(key, []).append(entry)
    return index


def load_en_sub_index(
    en_items_csv: str | Path,
    invalid_ids: set[str],
    resolver: EnResolver,
) -> dict[tuple[str, str], set[str]]:
    """完整 EN 明细里的「子单月」索引：`(order_common, product) → {YYYYMM}`。

    用于跨月关联：本月 raw 无子单、但 EN 明细显示子单在另一月时，不记「未关联」。
    排除作废原单自身。
    """
    df = pd.read_csv(en_items_csv, dtype=str, low_memory=False, keep_default_na=False)
    index: dict[tuple[str, str], set[str]] = {}
    for rec in df.to_dict("records"):
        order_id = str(rec.get("order_id_code") or "").strip()
        if not order_id or order_id in invalid_ids:
            continue
        sku = normalize_sku(rec.get("tongtool_sku"))
        item_code = str(rec.get("erp_item_code") or "").strip()
        product = resolver.product_for_item(item_code)
        if not product and sku:
            product = resolver.resolve(sku).product_id
        if not product:
            continue
        raw_month = str(rec.get("despatch_complete_time") or "").strip()[:7].replace("-", "")
        month = raw_month if len(raw_month) == 6 and raw_month.isdigit() else ""
        for key in {order_id, order_common_part(order_id)}:
            index.setdefault((key, product), set()).add(month)
    return index


def lookup_aux(
    index: Mapping[str, list[AuxEntry]],
    common: str,
    product_id: str,
) -> list[AuxEntry]:
    found: dict[tuple[str, str], AuxEntry] = {}
    for key in {common, order_common_part(common)}:
        for entry in index.get(key, []):
            if entry.product_id != product_id:
                continue
            if not _aux_links(entry.order_id, common):
                continue
            found[(entry.order_id, entry.product_id)] = entry
    return list(found.values())


# ─────────────────────────── 订单加载 ───────────────────────────


@dataclass(frozen=True)
class OrderRow:
    """订单行（只读快照行）。`index` 是源文件行序，`raw` 保留原行全部列。"""

    index: int
    order_id: str
    order_common: str
    platform_sku: str
    sku_raw: str
    sku: str
    qty: float
    sale: float
    sale_cny: float
    freight: float | None
    product_id: str
    item_group: str
    resolution_status: str
    shipping_method: str
    method_source: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class LoadResult:
    rows: list[OrderRow]              # 全部非作废行（含未登记/歧义，保证不丢行）
    aux_rows: list[OrderRow]          # invalid=1 且仍出现在 raw 的原单，只作校验
    sku_issues: list[dict]            # 未登记/歧义 SKU 汇总
    en_line_stats: dict = field(default_factory=dict)  # EN 行级身份采用/冲突计数


def _to_float(value: object) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _read_invalid_map(flags_csv: str | Path | None) -> dict[str, bool]:
    if not flags_csv:
        return {}
    path = Path(flags_csv)
    if not path.exists():
        raise FileNotFoundError(f"order_flags 不存在: {path}")
    flags = pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False)
    if "order_id_code" not in flags.columns or "invalid" not in flags.columns:
        raise ValueError("order_flags 需要 order_id_code / invalid 列")
    return {
        str(r["order_id_code"]).strip(): str(r["invalid"]).strip() == "1"
        for r in flags.to_dict("records")
        if str(r["order_id_code"]).strip()
    }


def load_orders(
    orders_csv: str | Path,
    resolver: EnResolver,
    en_items_csv: str | Path,
    flags_csv: str | Path | None = None,
    branch_map: Mapping[str, dict] | None = None,
) -> LoadResult:
    """读订单 CSV → 归一化/解析/带 EN shipping_method/标记作废。"""
    df = pd.read_csv(orders_csv, dtype=str, low_memory=False, keep_default_na=False)
    missing = [c for c in REQUIRED_ORDER_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"订单表缺列: {missing}")

    method_map = load_method_map(en_items_csv)
    en_line_map = load_en_line_map(en_items_csv)
    invalid_map = _read_invalid_map(flags_csv)
    rows: list[OrderRow] = []
    aux_rows: list[OrderRow] = []
    issues: dict[tuple[str, str], dict] = {}
    en_line_stats = {
        "en_line_used": 0, "en_line_override": 0, "alias_en_conflict": 0,
        "en_item_unmapped": 0, "en_item_multi": 0, "en_line_skipped_cover_in_group": 0,
    }
    # 同一原始订单里若同时有 Cover 与 填充行（Foam/PPCotton），Cover 行的 EN 物料号常被
    # 默认成另一条产品线；此时产品身份应以填充行为准（后续 _anchor_same_order 锚定）。
    records = df.to_dict("records")
    order_has_filler: dict[str, bool] = {}
    for rec in records:
        common = order_common_part(str(rec.get("订单号") or "").strip())
        if sku_shape(rec.get("通途SKU")) in (SHAPE_FOAM, SHAPE_PPCOTTON):
            order_has_filler[common] = True

    for index, rec in enumerate(records):
        order_id = str(rec.get("订单号") or "").strip()
        sku_raw = str(rec.get("通途SKU") or "").strip()
        sku = normalize_sku(sku_raw)
        resolution = resolver.resolve(sku_raw)
        anchor_source = ""
        en_item_for_row = ""
        en_items = en_line_map.get((order_id, sku), frozenset())
        cover_in_group = (
            sku_shape(sku_raw) == SHAPE_COVER
            and resolution.status == _STATUS_AMBIGUOUS
            and order_has_filler.get(order_common_part(order_id), False)
        )
        if len(en_items) > 1:
            # EN 行自身给了多个物料：不猜，保持别名结果；若别名也不唯一 → 阻断
            en_line_stats["en_item_multi"] += 1
        elif len(en_items) == 1 and cover_in_group:
            # 拆单组内的 Cover 行：产品身份交给填充行锚定，不采信 Cover 行的 EN 物料号
            en_line_stats["en_line_skipped_cover_in_group"] += 1
        elif len(en_items) == 1:
            en_item = next(iter(en_items))
            en_item_for_row = en_item
            en_product = resolver.product_for_item(en_item)
            if not en_product:
                en_line_stats["en_item_unmapped"] += 1
            else:
                if resolution.status == _STATUS_RESOLVED and resolution.product_id != en_product:
                    en_line_stats["alias_en_conflict"] += 1
                if resolution.status != _STATUS_RESOLVED or resolution.product_id != en_product:
                    anchor_source = "en_line"
                    en_line_stats["en_line_override"] += 1
                resolution = Resolution(
                    sku, _STATUS_RESOLVED, product_id=en_product,
                    item_names=(en_item,), products=(en_product,),
                )
                en_line_stats["en_line_used"] += 1
        method = method_map.get((order_id, sku), "")
        method_source = "en" if method else ""
        if not method:
            if is_non_product_accessory(sku):
                method_source = "non_product_accessory"
            elif branch_map:
                method, src = fallback_method(resolver, branch_map, sku)
                method_source = src if method else "pending"
            else:
                method_source = "pending"
        freight_value = None
        if FREIGHT_COLUMN in df.columns:
            raw_freight = str(rec.get(FREIGHT_COLUMN) or "").strip()
            if raw_freight:
                freight_value = _to_float(raw_freight)
        row = OrderRow(
            index=index,
            order_id=order_id,
            order_common=order_common_part(order_id),
            platform_sku=normalize_sku(rec.get("平台SKU")),
            sku_raw=sku_raw,
            sku=sku,
            qty=_to_float(rec.get("发货数量")),
            sale=_to_float(rec.get("售价")),
            sale_cny=_to_float(rec.get("售价(人民币)")),
            freight=freight_value,
            product_id=resolution.product_id,
            item_group=resolver.item_group_for(resolution.product_id),
            resolution_status=resolution.status,
            shipping_method=method,
            method_source=method_source,
            raw={
                **dict(rec),
                **({"_anchor_source": anchor_source} if anchor_source else {}),
                **({"_en_item": en_item_for_row} if en_item_for_row else {}),
            },
        )
        if invalid_map.get(order_id, False):
            aux_rows.append(row)
            continue
        rows.append(row)

    # TikTok 跨前缀拆单：通途不允许拆单，同事用另一渠道账号手动建单；
    # 同一数字主体、不同前缀的皮壳/填充行先配对，再走正常的结构合并。
    en_line_stats["tiktok_paired"] = _pair_tiktok_cross_prefix(rows)
    # 同订单锚定：Cover 别名同时命中 PPCotton/Foam 两条产品线时，用同订单组件行锁定
    _anchor_same_order(rows, resolver)
    # 组内产品归属：皮壳别名唯一时，皮壳决定产品；共用海绵/PP棉常被单独登记在另一产品上
    en_line_stats["group_cover_override"] = _cover_product_precedence(rows, resolver)

    for row in rows:
        if row.resolution_status == _STATUS_RESOLVED:
            continue
        key = (row.resolution_status, row.sku)
        issue = issues.setdefault(key, {
            "sku": row.sku,
            "status": row.resolution_status,
            "sku_raw": row.sku_raw,
            "rows": 0,
            "products": list(resolver.resolve(row.sku_raw).products),
        })
        issue["rows"] += 1

    issues_list = sorted(issues.values(), key=lambda x: (x["status"], -x["rows"], x["sku"]))
    return LoadResult(
        rows=rows, aux_rows=aux_rows, sku_issues=issues_list,
        en_line_stats=en_line_stats,
    )


_ANCHOR_STOP = {
    "CURVE", "PILLOW", "FOAM", "PPCOTTON", "LINEN", "VELVET",
    "ZIPPERPILLOW", "ET", "COVER", "SET", "CUSHION", "PCS",
}


def _color_tokens(sku: object) -> set[str]:
    """平台 SKU 中的颜色词（去掉品类/面料/兜底词与数字）。"""
    parts = re.split(r"[^A-Za-z]+", str(sku or "").upper())
    return {p for p in parts if len(p) > 1 and not p.isdigit() and p not in _ANCHOR_STOP}


def _material_anchor(row: OrderRow, candidates: set[str], resolver: EnResolver) -> str:
    """平台 SKU 含 PPCotton/Foam → 按候选产品 item_group 的「PP棉/海绵」锁定。"""
    s = str(row.platform_sku or "").upper()
    want = "PP棉" if "PPCOTTON" in s else ("海绵" if "FOAM" in s else "")
    if not want:
        return ""
    hits = [c for c in candidates if want in resolver.item_group_for(c)]
    return hits[0] if len(hits) == 1 else ""


def _color_anchor(row: OrderRow, candidates: set[str], same: Sequence[OrderRow],
                  resolver: EnResolver) -> str:
    """同订单两条线都在时，用 Cover 平台 SKU 的颜色词匹配组件行颜色。"""
    tokens = _color_tokens(row.platform_sku)
    if not tokens:
        return ""
    hits: list[str] = []
    for c in candidates:
        other: set[str] = set()
        for r in same:
            if r.product_id == c:
                other |= _color_tokens(r.platform_sku)
        if tokens & other:
            hits.append(c)
    return hits[0] if len(hits) == 1 else ""


def _pair_tiktok_cross_prefix(rows: list[OrderRow]) -> int:
    """TikTok 跨前缀拆单配对：同数字主体、不同前缀的皮壳/填充行视为同一件成品。

    TikTok 对接通途不允许拆单，需要拆包裹时由同事在另一渠道账号手动建单，
    两半的订单号前缀不同、数字主体相同（TT 前缀 + >=12 位）。配对只改写
    `order_common/platform_sku`，之后仍由正常结构判据合并；不做猜测：
    - 必须恰好 1 个皮壳行、至少 1 个填充行；
    - 皮壳/填充都必须解析到同一非空 product_id；
    - 发货仓库必须一致；
    - 不同订单号。
    """
    groups: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        body = tiktok_platform_body(row.order_id)
        if body:
            groups[body].append(i)
    paired = 0
    for body, idxs in groups.items():
        if len({rows[i].order_id for i in idxs}) < 2:
            continue
        covers = [i for i in idxs if sku_shape(rows[i].sku) == SHAPE_COVER]
        fillers = [
            i for i in idxs if sku_shape(rows[i].sku) in (SHAPE_FOAM, SHAPE_PPCOTTON)
        ]
        if len(covers) != 1 or not fillers:
            continue
        cover = rows[covers[0]]
        if not cover.product_id:
            continue
        for i in fillers:
            row = rows[i]
            if row.order_id == cover.order_id:
                continue
            if not row.product_id or row.product_id != cover.product_id:
                continue
            if str(row.raw.get("发货仓库") or "") != str(cover.raw.get("发货仓库") or ""):
                continue
            rows[i] = replace(
                row,
                order_common=cover.order_common,
                platform_sku=cover.platform_sku,
                raw={**row.raw, "_tiktok_pair": body},
            )
            paired += 1
    return paired


def _cover_product_precedence(rows: list[OrderRow], resolver: EnResolver) -> int:
    """同一 (order_common, 平台SKU) 内，皮壳别名唯一 → 皮壳决定组内产品。

    共用海绵/PP棉常只登记在另一产品上（如 KS0396 方格 vs KS0397 菱形），
    若按填充行取产品，会把整件成本对到错误 BOM。平台 SKU 含逗号（多商品）时不处理。
    """
    by_group: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        if "," in str(row.platform_sku or ""):
            continue
        if sku_shape(row.sku_raw) not in (SHAPE_COVER, SHAPE_FOAM, SHAPE_PPCOTTON):
            continue
        if row.product_id:
            by_group[(row.order_common, row.platform_sku)].append(i)
    changed = 0
    for idxs in by_group.values():
        covers = [
            i for i in idxs
            if sku_shape(rows[i].sku_raw) == SHAPE_COVER
            and rows[i].resolution_status == _STATUS_RESOLVED
        ]
        products = {rows[i].product_id for i in covers}
        if len(products) != 1:
            continue
        # 多颜色皮壳（多个不同 Cover SKU）是「多件不同变体」，不是一件成品的拆包
        if len({sku_base(rows[i].sku) for i in covers}) != 1:
            continue
        product = next(iter(products))
        for i in idxs:
            row = rows[i]
            if sku_shape(row.sku_raw) == SHAPE_COVER or row.product_id == product:
                continue
            raw = {k: v for k, v in row.raw.items() if k != "_en_item"}
            raw["_group_cover_override"] = product
            rows[i] = replace(
                row, product_id=product, item_group=resolver.item_group_for(product),
                raw=raw,
            )
            changed += 1
    return changed


def _anchor_same_order(rows: list[OrderRow], resolver: EnResolver) -> int:
    """歧义行用同订单（优先 order_id，后 order_common）已解析产品锚定；仍不唯一不动。"""
    if not rows:
        return 0
    by_order: dict[str, list[int]] = defaultdict(list)
    by_common: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_order[r.order_id].append(i)
        by_common[r.order_common].append(i)

    anchored = 0
    for i, row in enumerate(rows):
        if row.resolution_status != _STATUS_AMBIGUOUS:
            continue
        candidates = set(resolver.resolve(row.sku_raw).products)
        if not candidates:
            continue
        same = [rows[j] for j in by_order.get(row.order_id, []) if j != i]
        hits = {r.product_id for r in same if r.product_id in candidates}
        if not hits:
            same = [rows[j] for j in by_common.get(row.order_common, []) if j != i]
            hits = {r.product_id for r in same if r.product_id in candidates}
        pick = next(iter(hits)) if len(hits) == 1 else ""
        source = "same_order"
        if not pick:
            pick = _material_anchor(row, candidates, resolver)
            source = "material"
        if not pick:
            pick = _color_anchor(row, candidates, same, resolver)
            source = "color"
        if not pick:
            continue
        rows[i] = replace(
            row, product_id=pick, item_group=resolver.item_group_for(pick),
            resolution_status=_STATUS_RESOLVED,
            raw={**row.raw, "_anchor_source": source},
        )
        anchored += 1
    return anchored


# ─────────────────────────── 分组与载体 ───────────────────────────


@dataclass
class MergeGroup:
    order_common: str
    platform_sku: str
    product_id: str
    item_group: str
    rows: list[OrderRow]
    skus: list[str]
    method: str
    carrier_shape: str
    carrier_sku: str
    pieces: float
    sub_orders: list[str]
    group_id: str = ""
    aux_used: bool = False
    pieces_source: str = "suborder"
    aux_order_ids: list[str] = field(default_factory=list)

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def qty_sum(self) -> float:
        return round(sum(r.qty for r in self.rows), 6)

    @property
    def sale_sum(self) -> float:
        return round(sum(r.sale for r in self.rows), 6)

    @property
    def sale_cny_sum(self) -> float:
        return round(sum(r.sale_cny for r in self.rows), 6)

    @property
    def freight_sum(self) -> float:
        return round(sum(r.freight or 0.0 for r in self.rows), 6)


@dataclass
class BlockedGroup:
    order_common: str
    platform_sku: str
    product_id: str
    item_group: str
    n_rows: int
    skus: list[str]
    reason: str
    sub_orders: list[str]
    rows: list[OrderRow] = field(default_factory=list)
    aux_order_ids: list[str] = field(default_factory=list)


@dataclass
class Assertion:
    name: str
    status: str                    # pass / fail / skip
    checked: int
    detail: str
    violations: list[dict] = field(default_factory=list)
    skipped: int = 0
    skip_reasons: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "pass"


@dataclass
class MergeShadowResult:
    month: str
    rows: list[OrderRow]
    aux_rows: list[OrderRow]
    aux_entries: list[AuxEntry]
    aux_table: list[dict]
    groups: list[MergeGroup]
    blocked: list[BlockedGroup]
    sku_issues: list[dict]
    shadow_rows: list[dict]
    detail_rows: list[dict]
    sku_coverage: list[dict]
    detail_columns: list[str]
    assertions: list[Assertion]
    stats: dict

    @property
    def ok(self) -> bool:
        """有 fail 才算不通过；skip 单列，不算 fail。"""
        return all(a.status != "fail" for a in self.assertions)


def _as_record(row: OrderRow) -> dict:
    """喂给 `group_split_rows` 的记录形态（它只需这几项 + `a`）。"""
    return {
        # 用已算好的 order_common（TikTok 跨前缀配对会改写它），
        # 正常订单与 order_common_part(order_id) 等价。
        "order_no": row.order_common or row.order_id,
        "platform_sku": row.platform_sku,
        "tongtool_sku": row.sku,     # 用归一化 SKU 判「组内多 SKU」
        "qty": row.qty,
        "key": row.product_id,
        "a": {},
        "shell": "",
        "ship_type": "",
        "_row": row,
    }


def _carrier_rows(rows: Sequence, shape: str, sku: str) -> list:
    return [r for r in rows if sku_shape(r.sku) == shape and sku_base(r.sku) == sku]


def _identity_conflicts(rows: Sequence[OrderRow], shape: str, sku: str) -> list[str]:
    """载体行的身份字段是否一致；返回冲突列（空=一致）。"""
    candidates = _carrier_rows(rows, shape, sku)
    conflicts: list[str] = []
    for col in IDENTITY_COLUMNS:
        values = {str(r.raw.get(col, "")).strip() for r in candidates}
        if len(values) > 1:
            conflicts.append(col)
    return conflicts


def _pick_carrier(rows: Sequence) -> tuple[str, str, str, str]:
    """按 EN shipping_method 选唯一载体；返回 `(method, carrier_shape, carrier_sku, reason)`。

    定不了返回 `("", "", "", reason)`，绝不取 first/max。
    - 成品：优先唯一「非皮壳/海绵形态」的成品行；全为部件时取唯一皮壳行。
    - 半成品：Cover + Foam 合成一件，载体取唯一皮壳行；无皮壳时取唯一成品行。
    - 皮壳：载体取唯一皮壳行；无皮壳时取唯一成品行（皮壳产品整件拆分）。
    """
    methods = {r.shipping_method for r in rows}
    if "" in methods:
        return "", "", "", "method_missing"
    if len(methods) > 1:
        # Cover 行与填充行 method 不同（拆包裹订单常态）：以非 Cover 行（填充/成品行）为准；
        # 非 Cover 行仍不一致或无 → 阻断，不猜。
        non_cover = [r for r in rows if sku_shape(r.sku) != SHAPE_COVER]
        nc_methods = {r.shipping_method for r in non_cover}
        if non_cover and len(nc_methods) == 1 and "" not in nc_methods:
            method = next(iter(nc_methods))
        else:
            return "", "", "", "mixed_methods"
    else:
        method = next(iter(methods))
    if method not in METHODS:
        return "", "", "", "method_missing"

    covers = sorted({sku_base(r.sku) for r in rows if sku_shape(r.sku) == SHAPE_COVER})
    non_components = sorted({sku_base(r.sku) for r in rows if sku_shape(r.sku) == SHAPE_FINISHED})

    if method == METHOD_FINISHED and len(non_components) == 1:
        return method, SHAPE_FINISHED, non_components[0], ""
    if method == METHOD_FINISHED and len(non_components) > 1:
        return "", "", "", "multiple_carrier_skus"

    # 成品组全为部件 / 半成品 / 皮壳：优先唯一皮壳行
    if len(covers) == 1:
        return method, SHAPE_COVER, covers[0], ""
    if len(covers) > 1:
        return "", "", "", "multiple_cover_skus"
    if len(non_components) == 1:
        return method, SHAPE_FINISHED, non_components[0], ""
    if len(non_components) > 1:
        return "", "", "", "multiple_carrier_skus"
    return "", "", "", "no_carrier"


def _count_pieces(rows: Sequence, carrier_shape: str, carrier_sku: str) -> tuple[float, str]:
    """件数：皮壳载体按该皮壳 SKU 全部行求和；成品载体只数「无拆单尾号」的基行。

    成品形态载体若只有 `-1/-2` 这类拆单尾号行、没有基行，件数无法唯一确定 → 阻断。
    """
    candidates = _carrier_rows(rows, carrier_shape, carrier_sku)
    if carrier_shape == SHAPE_COVER:
        return round(sum(r.qty for r in candidates), 6), ""
    exact = [r for r in candidates if r.sku == carrier_sku]
    if not exact:
        return 0.0, "pieces_ambiguous"
    return round(sum(r.qty for r in exact), 6), ""


def _aux_validate(
    grow_rows: Sequence[OrderRow],
    aux_here: Sequence[AuxEntry],
) -> tuple[str, list[AuxRow], AuxEntry | None]:
    """校验 aux 的 method（件数在拿到子单 pieces 后校验）。返回 `(reason, rows, entry)`。"""
    if not aux_here:
        return "", [], None
    if len(aux_here) > 1:
        return "aux_ambiguous", [], None
    entry = aux_here[0]
    aux_rows = list(entry.rows)
    aux_methods = set(entry.methods)
    sub_methods = {r.shipping_method for r in grow_rows if r.shipping_method}
    if aux_methods and sub_methods and aux_methods != sub_methods:
        return "aux_method_mismatch", aux_rows, entry
    return "", aux_rows, entry


def find_groups(
    rows: Sequence[OrderRow],
    aux_entries: Sequence[AuxEntry] = (),
) -> tuple[list[MergeGroup], list[BlockedGroup], dict[int, str], list[dict]]:
    """按 `(订单号公共部分, 平台SKU, product_id)` 找拆包候选组。

    返回：可合并组、阻断组、行 index → 阻断原因（仅阻断组）。
    aux（EN 作废原单）参与校验与件数/载体兜底，但**不进入合并行计数**。
    """
    by_product: dict[str, list[OrderRow]] = {}
    for row in rows:
        if row.product_id:
            by_product.setdefault(row.product_id, []).append(row)

    index = _aux_index(aux_entries)
    groups: list[MergeGroup] = []
    blocked: list[BlockedGroup] = []
    row_blocked: dict[int, str] = {}
    split_products: list[dict] = []

    for product_id in sorted(by_product):
        records = [_as_record(r) for r in by_product[product_id]]
        for g in group_split_rows(records):
            grow_rows = [rec["_row"] for rec in g["rows"]]
            skus = sorted({r.sku for r in grow_rows})
            if len(skus) < 2:
                continue
            aux_here = lookup_aux(index, g["common"], product_id)
            aux_reason, aux_rows, aux_entry = _aux_validate(grow_rows, aux_here)

            method, carrier_shape, carrier_sku, reason = _pick_carrier(grow_rows)
            pieces = 0.0
            if not reason:
                pieces, reason = _count_pieces(grow_rows, carrier_shape, carrier_sku)
            if not reason and _identity_conflicts(grow_rows, carrier_shape, carrier_sku):
                reason = "carrier_identity_conflict"
            if not reason and pieces <= 0:
                reason = "pieces_zero"

            aux_used = False
            pieces_source = "suborder"
            aux_qty_failed = False
            if aux_reason:
                reason = aux_reason
            elif aux_entry is not None:
                # 件数统一按 Cover/整件口径比较；组件行 qty 合计不作为件数
                aux_pieces = aux_entry.pieces
                if aux_entry.duplicate_components:
                    # component_sum_error：原单组件行重复，qty 合计不可用 → 按件数锚定，不阻断
                    if aux_pieces > 0 and abs(aux_pieces - pieces) > TOL:
                        pieces = aux_pieces
                        pieces_source = "aux"
                        aux_used = True
                        if reason in ("pieces_ambiguous", "pieces_zero"):
                            reason = ""
                elif pieces > 0 and abs(aux_pieces - pieces) > TOL:
                    reason = "aux_qty_mismatch"
                    aux_qty_failed = True

            # 结构失败（无载体/多载体/method 缺失）时，用 aux 的载体+件数兜底
            if not aux_reason and not aux_qty_failed and reason and aux_rows:
                a_method, a_shape, a_carrier, a_reason = _pick_carrier(aux_rows)
                if not a_reason:
                    a_pieces = _pieces_of(aux_rows)
                    if a_pieces > 0:
                        method, carrier_shape, carrier_sku = a_method, a_shape, a_carrier
                        pieces, reason = a_pieces, ""
                        aux_used = True
                        pieces_source = "aux"

            if reason:
                # 多个“整件成品 SKU”同产品：不是拆包组件，而是多件不同变体 → 分开逐件计价
                split_ok = reason == "multiple_carrier_skus" and all(
                    sku_shape(r.sku) == SHAPE_FINISHED for r in grow_rows
                )
                if reason == "multiple_cover_skus":
                    # 组内全是多颜色皮壳 SKU → 是多件不同变体，逐件计价（共享海绵在别的产品组）
                    split_ok = all(sku_shape(r.sku) == SHAPE_COVER for r in grow_rows)
                if split_ok:
                    split_products.append({
                        "order_common": g["common"],
                        "platform_sku": g["platform_sku"],
                        "product_id": product_id,
                        "skus": skus,
                        "n_rows": len(grow_rows),
                    })
                    continue
                blocked.append(BlockedGroup(
                    order_common=g["common"],
                    platform_sku=g["platform_sku"],
                    product_id=product_id,
                    item_group=grow_rows[0].item_group,
                    n_rows=len(grow_rows),
                    skus=skus,
                    reason=reason,
                    sub_orders=sorted({r.order_id for r in grow_rows}),
                    rows=grow_rows,
                    aux_order_ids=[e.order_id for e in aux_here],
                ))
                for row in grow_rows:
                    row_blocked[row.index] = reason
                continue
            groups.append(MergeGroup(
                order_common=g["common"],
                platform_sku=g["platform_sku"],
                product_id=product_id,
                item_group=grow_rows[0].item_group,
                rows=grow_rows,
                skus=skus,
                method=method,
                carrier_shape=carrier_shape,
                carrier_sku=carrier_sku,
                pieces=pieces,
                sub_orders=sorted({r.order_id for r in grow_rows}),
                aux_used=aux_used,
                pieces_source=pieces_source,
                aux_order_ids=[e.order_id for e in aux_here],
            ))

    groups.sort(key=lambda x: (x.order_common, x.platform_sku, x.product_id))
    blocked.sort(key=lambda x: (x.order_common, x.platform_sku, x.product_id))
    for i, group in enumerate(groups, start=1):
        group.group_id = f"G{i:04d}"
    return groups, blocked, row_blocked, split_products


# ─────────────────────────── aux 校验表 ───────────────────────────


def build_aux_table(
    entries: Sequence[AuxEntry],
    groups: Sequence[MergeGroup],
    blocked: Sequence[BlockedGroup],
    *,
    month: str = "",
    sub_index: Mapping[tuple[str, str], set[str]] | None = None,
) -> list[dict]:
    """每条 EN 原单（原单号+产品）一行；件数按 Cover/整件口径，支持跨月关联。"""
    sub_index = sub_index or {}
    rows: list[dict] = []
    for entry in entries:
        linked = [
            g for g in groups
            if g.product_id == entry.product_id and _aux_links(entry.order_id, g.order_common)
        ]
        linked_blocked = [
            b for b in blocked
            if b.product_id == entry.product_id and _aux_links(entry.order_id, b.order_common)
        ]
        sub_rows = [r for g in linked for r in g.rows] + [
            r for b in linked_blocked for r in b.rows
        ]
        if linked and any(g.pieces_source == "aux" for g in linked):
            # 组件数已由原单锚定（子单本身件数不可确定）→ 用锚定值参与校验
            sub_pieces = round(sum(g.pieces for g in linked), 6)
        else:
            sub_pieces = _pieces_of(sub_rows) if sub_rows else 0.0
        sub_methods = sorted({r.shipping_method for r in sub_rows if r.shipping_method})
        group_ids = [g.group_id for g in linked] + [
            f"BLOCKED:{b.order_common}" for b in linked_blocked
        ]

        months: set[str] = set()
        for key in {(entry.order_id, entry.product_id),
                    (order_common_part(entry.order_id), entry.product_id)}:
            months |= {m for m in sub_index.get(key, set()) if m}
        if sub_rows:
            link_month, cross_month = month, "否"
        elif months:
            link_month, cross_month = ", ".join(sorted(months)), "是"
        else:
            link_month, cross_month = "", "未知"

        aux_pieces = entry.pieces
        method_checked = bool(entry.methods) and bool(sub_methods)
        method_ok = (not method_checked) or set(entry.methods) == set(sub_methods)
        qty_checked = bool(sub_rows) and not entry.duplicate_components
        qty_ok = qty_checked and abs(aux_pieces - sub_pieces) <= TOL

        method_skip_reason = ""
        if not method_checked:
            if not entry.product_id:
                method_skip_reason = "产品未解析（erp_item_code/SKU 未覆盖）"
            elif not sub_rows:
                method_skip_reason = (
                    "跨月（本月无子单）" if cross_month == "是" else "本月无有效子单"
                )
            else:
                method_skip_reason = "method 不可校验（原单或子单一侧为空）"

        if not entry.product_id:
            status, reason = "未关联", "产品未解析（erp_item_code/SKU 未覆盖）"
        elif not sub_rows and cross_month == "是":
            status, reason = "跨月关联", f"本月无子单；EN 子单在 {link_month}"
        elif not sub_rows:
            status, reason = "未关联", "无有效子单记录"
        elif entry.duplicate_components:
            status = "component_sum_error"
            reason = (
                f"原单组件行重复（{len(entry.rows)} 行），组件 qty 合计不可用；"
                f"按 Cover/整件件数 {aux_pieces:g} 锚定"
            )
        elif not qty_ok:
            status, reason = "阻断", f"qty 原单件数 {aux_pieces:g} ≠ 子单件数 {sub_pieces:g}"
        elif not method_ok:
            status, reason = (
                "阻断",
                f"method 原单 {','.join(entry.methods) or '-'} ≠ 子单 {','.join(sub_methods) or '-'}",
            )
        elif not method_checked:
            status, reason = "跳过", "method 不可校验（一侧为空）"
        else:
            status, reason = "通过", ""

        rows.append({
            "原单号": entry.order_id,
            "order_common": order_common_part(entry.order_id),
            "产品": entry.product_id,
            "method": ", ".join(entry.methods),
            "qty": aux_pieces,
            "原始组件qty": entry.qty,
            "SKU": ", ".join(entry.skus),
            "关联group_id": ", ".join(group_ids),
            "关联月": link_month,
            "跨月": cross_month,
            "子单qty": sub_pieces,
            "校验结果": status,
            "原因": reason,
            "是否用于兜底": "是" if any(g.aux_used for g in linked) else "否",
            "cost_fg合计(仅对账)": entry.cost_fg,
            "factor(仅对账)": ", ".join(f"{x:g}" for x in entry.factors),
            "_qty_checked": qty_checked,
            "_qty_ok": qty_ok,
            "_method_checked": method_checked,
            "_method_ok": method_ok,
            "_method_skip_reason": method_skip_reason,
            "_sub_methods": sub_methods,
            "_pieces_mismatch": bool(sub_rows) and abs(aux_pieces - sub_pieces) > TOL,
        })
    return rows


# ─────────────────────────── 断言 ───────────────────────────


def _conserve_fields(rows: Sequence[OrderRow]) -> list[tuple[str, str]]:
    fields = [("qty", "发货数量"), ("sale", "售价"), ("sale_cny", "售价(人民币)")]
    if any(r.freight is not None for r in rows):
        fields.append(("freight", "运费"))
    return fields


def _source_indices(value: object) -> list[int]:
    return [int(x) for x in str(value).split(",") if str(x).strip()]


def _check_qty_conservation(rows: Sequence[OrderRow], shadow_rows: Sequence[dict]) -> Assertion:
    fields = _conserve_fields(rows)
    before = {f: sum((getattr(r, f) or 0.0) for r in rows) for f, _ in fields}
    after = {f: sum(float(s.get(f) or 0.0) for s in shadow_rows) for f, _ in fields}
    diffs = {f: round(after[f] - before[f], 6) for f, _ in fields}
    bad = {f: d for f, d in diffs.items() if abs(d) > TOL}
    detail = "；".join(f"{label} {before[f]:.2f}→{after[f]:.2f}" for f, label in fields)
    if len(fields) < 4:
        detail += "；快照无 运费 列，跳过该列"
    return Assertion(
        name="件数守恒",
        status="fail" if bad else "pass",
        checked=len(fields),
        detail=detail + ("；差异 " + str(bad) if bad else "；累计列总量前后一致"),
        violations=[{"field": f, "diff": d} for f, d in bad.items()],
    )


def _check_piece_method(groups: Sequence[MergeGroup]) -> Assertion:
    """成品件数 = 皮壳件数（按 method 分组）。"""
    per: dict[str, dict] = {
        m: {"groups": 0, "checked": 0, "skipped": 0, "pieces": 0.0, "cover": 0.0}
        for m in METHODS
    }
    violations: list[dict] = []
    for group in groups:
        cover_qty = round(
            sum(r.qty for r in group.rows if sku_shape(r.sku) == SHAPE_COVER), 6
        )
        stat = per[group.method]
        stat["groups"] += 1
        if group.pieces_source == "aux":
            # 件数由 EN 原单锚定（组件行重复/子单歧义），子单侧无法独立验证
            stat["skipped"] += 1
            continue
        if cover_qty <= 0:
            stat["skipped"] += 1
            continue
        stat["checked"] += 1
        stat["pieces"] += group.pieces
        stat["cover"] += cover_qty
        if abs(group.pieces - cover_qty) > TOL:
            violations.append({
                "group_id": group.group_id, "method": group.method,
                "pieces": group.pieces, "cover_qty": cover_qty,
            })
    for method, stat in per.items():
        if stat["checked"] and abs(stat["pieces"] - stat["cover"]) > TOL:
            violations.append({
                "method": method, "pieces": round(stat["pieces"], 6),
                "cover_qty": round(stat["cover"], 6),
            })

    checked = sum(st["checked"] for st in per.values())
    skipped = sum(st["skipped"] for st in per.values())
    detail = "；".join(
        f"{m}: 成品 {st['pieces']:g} = 皮壳 {st['cover']:g}"
        f"（组 {st['checked']}，无皮壳跳过 {st['skipped']}）"
        for m, st in per.items()
    )
    return Assertion(
        name="成品件数=皮壳件数",
        status="fail" if violations else ("skip" if checked == 0 else "pass"),
        checked=checked,
        detail=detail,
        violations=violations,
        skipped=skipped,
        skip_reasons={"无皮壳行（整件拆分）/件数由 EN 原单锚定": skipped} if skipped else {},
    )


def _check_one_cost(
    groups: Sequence[MergeGroup],
    rows: Sequence[OrderRow],
    detail_rows: Sequence[dict],
) -> Assertion:
    """载体调用次数 = 成本行数；成本行唯一；不可定价行不得成为成本行。"""
    violations: list[dict] = []
    cost_rows = [d for d in detail_rows if d.get("cost_eligible")]
    pass_cost = [d for d in cost_rows if not d.get("merged")]
    carrier_calls = len(groups) + len(pass_cost)
    if carrier_calls != len(cost_rows):
        violations.append({
            "reason": "载体调用次数≠成本行数",
            "carrier_calls": carrier_calls, "cost_rows": len(cost_rows),
        })

    for group in groups:
        group_cost = [
            d for d in detail_rows
            if d.get("merged") and d.get("group_id") == group.group_id and d.get("cost_eligible")
        ]
        if len(group_cost) != 1:
            violations.append({
                "group_id": group.group_id, "reason": "合并组成本行数不为 1",
                "cost_rows": len(group_cost),
            })
        if group.method not in METHODS:
            violations.append({"group_id": group.group_id, "reason": "method 无效"})

    keys = [
        f"G:{d['group_id']}" if d.get("merged") else f"R:{tuple(_source_indices(d['source_rows']))}"
        for d in cost_rows
    ]
    if len(keys) != len(set(keys)):
        violations.append({"reason": "成本行键重复", "cost_rows": len(keys), "unique": len(set(keys))})

    for d in cost_rows:
        if d.get("merged"):
            continue
        if d.get("resolution_status") != _STATUS_RESOLVED:
            violations.append({"reason": "未解析行进成本行", "sku": d.get("skus")})
        if d.get("blocked_reason"):
            violations.append({"reason": "阻断行进成本行", "sku": d.get("skus")})
        if not d.get("pricing_method"):
            violations.append({"reason": "method 缺失行进成本行", "sku": d.get("skus")})

    seen: Counter = Counter()
    for d in detail_rows:
        for idx in _source_indices(d["source_rows"]):
            seen[idx] += 1
    expected = {r.index for r in rows}
    if set(seen) != expected:
        violations.append({
            "reason": "源行未完整消费",
            "missing": sorted(expected - set(seen))[:20],
            "unknown": sorted(set(seen) - expected)[:20],
        })
    dup = [idx for idx, n in seen.items() if n > 1]
    if dup:
        violations.append({"reason": "源行被多个成本行消费", "rows": sorted(dup)[:20]})

    return Assertion(
        name="每成品一次成本",
        status="fail" if violations else "pass",
        checked=len(groups) + len(detail_rows),
        detail=(
            f"{len(groups)} 组 + {len(pass_cost)} 条可定价透传 = {carrier_calls} 次载体调用；"
            f"成本行 {len(cost_rows)}（键唯一 {len(keys) == len(set(keys))}）；"
            f"明细 {len(detail_rows)} 行；源行 {len(expected)} 行各消费一次"
        ),
        violations=violations,
    )


def _check_aux_qty(
    rows: Sequence[OrderRow],
    aux_rows: Sequence[OrderRow],
    aux_table: Sequence[dict],
    groups: Sequence[MergeGroup],
    detail_rows: Sequence[dict],
) -> Assertion:
    """原单件数 = 有效子单之和（EN aux + raw 基行/作废原单）。"""
    violations: list[dict] = []
    checked = 0
    skipped = 0
    skip_reasons: Counter = Counter()

    # EN aux：逐条 qty 校验（未覆盖的显式跳过）
    for entry in aux_table:
        if entry["_qty_checked"]:
            checked += 1
            if not entry["_qty_ok"]:
                violations.append({
                    "原单号": entry["原单号"], "product": entry["产品"],
                    "原单qty": entry["qty"], "子单qty": entry["子单qty"],
                })
        else:
            skipped += 1
            skip_reasons[entry["原因"] or "未关联"] += 1

    # raw 基行 / raw 作废原单 vs 子单（未来快照含原单时生效）
    partitions: dict[tuple[str, str, str], list[OrderRow]] = {}
    for row in rows:
        partitions.setdefault((row.order_common, row.platform_sku, row.product_id), []).append(row)
    aux_parts: dict[tuple[str, str, str], list[OrderRow]] = {}
    for row in aux_rows:
        aux_parts.setdefault((row.order_common, row.platform_sku, row.product_id), []).append(row)
    covered_partitions = {
        (entry["原单号"], entry["产品"])
        for entry in aux_table if entry["_qty_checked"]
    }
    for key, prows in sorted(partitions.items()):
        common = key[0]
        subs = [r for r in prows if r.order_id != common]
        if not subs:
            continue
        originals: list[tuple[str, list[OrderRow]]] = []
        base = [r for r in prows if r.order_id == common]
        if base:
            originals.append(("base", base))
        aux = aux_parts.get(key, [])
        if aux:
            originals.append(("invalid_raw", aux))
        if not originals:
            # 没有可校验原单：若已被 EN aux 覆盖则不重复计，否则记「不可校验/跳过」
            covered = any(
                product == key[2] and _aux_links(order_id, common)
                for order_id, product in covered_partitions
            )
            if not covered:
                skipped += 1
                skip_reasons["缺原单基行/作废原单（本分区无原单可校验）"] += 1
            continue
        for label, orig in originals:
            checked += 1
            expected = sum(r.qty for r in subs)
            actual = sum(r.qty for r in orig)
            if abs(actual - expected) > TOL:
                violations.append({
                    "partition": key, "source": label,
                    "original": round(actual, 6), "suborders": round(expected, 6),
                })

    # 合并组分区聚合守恒
    detail_by_group = {d["group_id"]: d for d in detail_rows if d.get("merged")}
    for group in groups:
        out = detail_by_group.get(group.group_id)
        if out is None:
            violations.append({"group_id": group.group_id, "reason": "合并明细行缺失"})
            continue
        expected = sum(r.qty for r in group.rows)
        actual = float(out.get("发货数量") or 0.0)
        if abs(actual - expected) > TOL:
            violations.append({
                "group_id": group.group_id, "field": "发货数量",
                "expected": round(expected, 6), "actual": round(actual, 6),
            })

    status = "fail" if violations else ("skip" if checked == 0 else "pass")
    return Assertion(
        name="原单件数=有效子单之和",
        status=status,
        checked=checked,
        detail=(
            f"EN aux 条目 {len(aux_table)} 个（可校验 {sum(1 for e in aux_table if e['_qty_checked'])}）；"
            f"raw 基行/作废原单校验；合并组聚合 {len(groups)} 个；"
            f"有效校验 {checked} 项；不可校验/跳过 {skipped}"
        ),
        violations=violations,
        skipped=skipped,
        skip_reasons=dict(skip_reasons),
    )


def _check_aux_amount(
    rows: Sequence[OrderRow],
    aux_rows: Sequence[OrderRow],
    aux_table: Sequence[dict],
) -> Assertion:
    """原单金额 = 有效子单之和；EN 原单行无金额字段 → 显式跳过。"""
    violations: list[dict] = []
    checked = 0
    skipped = 0
    skip_reasons: Counter = Counter()

    if aux_table:
        skipped += len(aux_table)
        skip_reasons["EN 原单行无金额字段（cost_fg/factor 只作对账，不参与主计算）"] += len(aux_table)

    # raw 基行/作废原单若含金额，则校验
    partitions: dict[tuple[str, str, str], list[OrderRow]] = {}
    for row in rows:
        partitions.setdefault((row.order_common, row.platform_sku, row.product_id), []).append(row)
    aux_parts: dict[tuple[str, str, str], list[OrderRow]] = {}
    for row in aux_rows:
        aux_parts.setdefault((row.order_common, row.platform_sku, row.product_id), []).append(row)
    for key, prows in sorted(partitions.items()):
        common = key[0]
        subs = [r for r in prows if r.order_id != common]
        if not subs:
            continue
        originals: list[tuple[str, list[OrderRow]]] = []
        base = [r for r in prows if r.order_id == common]
        if base:
            originals.append(("base", base))
        aux = aux_parts.get(key, [])
        if aux:
            originals.append(("invalid_raw", aux))
        for label, orig in originals:
            if all(r.sale_cny == 0 for r in orig):
                skipped += 1
                skip_reasons["原单行无金额（售价=0）"] += 1
                continue
            checked += 1
            expected = sum(r.sale_cny for r in subs)
            actual = sum(r.sale_cny for r in orig)
            if abs(actual - expected) > TOL:
                violations.append({
                    "partition": key, "source": label,
                    "original": round(actual, 6), "suborders": round(expected, 6),
                })

    status = "fail" if violations else ("skip" if checked == 0 else "pass")
    return Assertion(
        name="原单金额=有效子单之和",
        status=status,
        checked=checked,
        detail=f"金额有效校验 {checked} 项；不可校验/跳过 {skipped}（EN 明细无售价字段）",
        violations=violations,
        skipped=skipped,
        skip_reasons=dict(skip_reasons),
    )


def _check_aux_method(
    aux_table: Sequence[dict],
    groups: Sequence[MergeGroup],
    blocked: Sequence[BlockedGroup],
) -> Assertion:
    """原单产品/method 与有效子单一致。"""
    violations: list[dict] = []
    checked = 0
    skipped = 0
    skip_reasons: Counter = Counter()
    for entry in aux_table:
        if not entry["_method_checked"]:
            skipped += 1
            skip_reasons[entry.get("_method_skip_reason") or "method 不可校验"] += 1
            continue
        checked += 1
        if not entry["_method_ok"]:
            violations.append({
                "原单号": entry["原单号"], "product": entry["产品"],
                "原单method": entry["method"],
                "子单method": ", ".join(entry.get("_sub_methods", [])),
            })
    for group in groups:
        if not group.product_id:
            violations.append({"group_id": group.group_id, "reason": "产品为空"})
    status = "fail" if violations else ("skip" if checked == 0 else "pass")
    return Assertion(
        name="原单产品/method一致",
        status=status,
        checked=checked,
        detail=f"方法与产品校验 {checked} 项；不可校验/跳过 {skipped}",
        violations=violations,
        skipped=skipped,
        skip_reasons=dict(skip_reasons),
    )


def _check_keys(groups: Sequence[MergeGroup]) -> Assertion:
    violations: list[dict] = []
    for group in groups:
        if not group.order_common:
            violations.append({"group": group.order_common, "reason": "订单号公共部分为空"})
        # 退化 = 只剩平台前缀（如 OS / PBUS），会把整平台订单塌并
        platform_prefix = re.split(r"[-_]", group.order_common, maxsplit=1)[0]
        if group.order_common == platform_prefix:
            violations.append({"group": group.order_common, "reason": "订单号公共部分退化为平台前缀"})
        if not group.product_id:
            violations.append({"group": group.order_common, "reason": "product_id 为空"})
        if group.product_id and group.product_id == group.platform_sku:
            violations.append({"group": group.order_common, "reason": "键退化为平台 SKU"})
        if not group.carrier_sku:
            violations.append({"group": group.order_common, "reason": "载体 SKU 为空"})
        if group.method not in METHODS:
            violations.append({"group": group.order_common, "reason": "pricing_method 无效"})
        if any(r.product_id != group.product_id for r in group.rows):
            violations.append({"group": group.order_common, "reason": "组内 product_id 不一致"})
        if len(group.skus) < 2:
            violations.append({"group": group.order_common, "reason": "组内少于 2 个不同 SKU"})
    return Assertion(
        name="键不退化",
        status="fail" if violations else "pass",
        checked=len(groups),
        detail=f"{len(groups)} 个合并组的公共订单号/产品/pricing_method/载体 SKU 均非空且未被拼接或降级",
        violations=violations,
    )


# ─────────────────────────── 主流程 ───────────────────────────


def _identity_row(group: MergeGroup) -> OrderRow:
    """合并行身份字段取哪一条：优先无拆单尾号的载体基行，多条时取行序最小。

    这里**不按数量取 max**；多条候选的身份一致性已由 `carrier_identity_conflict` 守住。
    载体由 aux 兜底、不在子单行里时，退到组内行序最小的一行。
    """
    candidates = _carrier_rows(group.rows, group.carrier_shape, group.carrier_sku)
    exact = [r for r in candidates if r.sku == group.carrier_sku]
    pool = exact or candidates or group.rows
    return min(pool, key=lambda r: r.index)


def _merged_raw(group: MergeGroup) -> dict:
    """合并行的原行全部列：身份类取载体行，累加类取组内 sum。"""
    raw = dict(_identity_row(group).raw)
    raw.update({
        "发货数量": f"{group.qty_sum:g}",
        "售价": f"{group.sale_sum:g}",
        "售价(人民币)": f"{group.sale_cny_sum:g}",
    })
    # 快照无运费列/全空时不要伪造 0；保留原行值（可能为空）供写回映射
    if FREIGHT_COLUMN in raw and any(r.freight is not None for r in group.rows):
        raw[FREIGHT_COLUMN] = f"{group.freight_sum:g}"
    return raw


def _pass_eligibility(row: OrderRow, blocked_reason: str) -> tuple[bool, str]:
    """透传行能否自动定价；返回 `(cost_eligible, cost_blocked_reason)`。"""
    if row.resolution_status == _STATUS_UNRESOLVED:
        return False, "SKU未登记（EN customer_code 未覆盖）"
    if row.resolution_status == _STATUS_AMBIGUOUS:
        return False, "SKU别名歧义（一个别名命中多个产品）"
    if blocked_reason:
        return False, _BLOCK_REASONS.get(blocked_reason, blocked_reason)
    if not row.shipping_method:
        return False, "method 缺失（EN shipping_method 为空）"
    return True, ""


def _sku_coverage(rows: Sequence[OrderRow]) -> list[dict]:
    """每个通途SKU 的覆盖情况（未覆盖项要显式输出）。"""
    stats: dict[str, dict] = {}
    for row in rows:
        item = stats.setdefault(row.sku, {
            "SKU": row.sku, "行数": 0, "状态": set(), "产品": set(), "出现method": set(),
        })
        item["行数"] += 1
        item["状态"].add(row.resolution_status)
        if row.product_id:
            item["产品"].add(row.product_id)
        if row.shipping_method:
            item["出现method"].add(row.shipping_method)
    out: list[dict] = []
    for sku in sorted(stats):
        item = stats[sku]
        if _STATUS_AMBIGUOUS in item["状态"]:
            status = _STATUS_AMBIGUOUS
        elif _STATUS_UNRESOLVED in item["状态"]:
            status = _STATUS_UNRESOLVED
        else:
            status = _STATUS_RESOLVED
        out.append({
            "SKU": sku,
            "行数": item["行数"],
            "状态": _STATUS_CN[status],
            "产品": ", ".join(sorted(item["产品"])),
            "出现method": ", ".join(sorted(item["出现method"])),
            "已覆盖": status == _STATUS_RESOLVED,
        })
    return out


def build_merge_shadow(
    rows: Sequence[OrderRow],
    aux_rows: Sequence[OrderRow] = (),
    sku_issues: Sequence[dict] = (),
    *,
    aux_entries: Sequence[AuxEntry] = (),
    en_sub_index: Mapping[tuple[str, str], set[str]] | None = None,
    month: str = "",
) -> MergeShadowResult:
    """构造合并 shadow：合并组 + 合并明细 + EN 原单校验 + 阻断清单 + 覆盖 + 断言。"""
    groups, blocked, row_blocked, split_products = find_groups(rows, aux_entries)
    group_by_row: dict[int, MergeGroup] = {}
    for group in groups:
        for row in group.rows:
            group_by_row[row.index] = group

    shadow_rows: list[dict] = []
    detail_rows: list[dict] = []
    emitted_groups: set[str] = set()
    for row in rows:
        group = group_by_row.get(row.index)
        if group is not None:
            if group.group_id in emitted_groups:
                continue
            emitted_groups.add(group.group_id)
            shadow_rows.append({
                "merged": True,
                "order_common": group.order_common,
                "platform_sku": group.platform_sku,
                "product_id": group.product_id,
                "item_group": group.item_group,
                "method": group.method,
                "sub_orders": group.sub_orders,
                "skus": group.skus,
                "carrier_sku": group.carrier_sku,
                "pieces": group.pieces,
                "qty": group.qty_sum,
                "sale": group.sale_sum,
                "sale_cny": group.sale_cny_sum,
                "freight": group.freight_sum,
                "source_rows": [r.index for r in group.rows],
                "cost_carrier": True,
                "blocked_reason": "",
            })
            detail = _merged_raw(group)
            detail.update({
                "group_id": group.group_id,
                "product_id": group.product_id,
                "order_common": group.order_common,
                "platform_sku": group.platform_sku,
                "carrier_sku": group.carrier_sku,
                "role": group.method,
                "pricing_method": group.method,
                "method_source": group.rows[0].method_source if group.rows else "",
                "merged": True,
                "shipping_method": group.method,
                # GS 参考列：raw 快照没有就留空；绝不拿它定价
                "当月给分公司发货类型": str(detail.get("当月给分公司发货类型") or ""),
                "cost_eligible": True,
                "cost_blocked": False,
                "cost_blocked_reason": "",
                "resolution_status": _STATUS_RESOLVED,
                "pieces": group.pieces,
                "pieces_source": group.pieces_source,
                "skus": ", ".join(group.skus),
                "sub_orders": ", ".join(group.sub_orders),
                "source_rows": ", ".join(str(r.index) for r in group.rows),
                "blocked_reason": "",
            })
            detail_rows.append(detail)
            continue

        # 透传行：未进任何合并组（含未登记/歧义/阻断组）——一户一行，按条件可定价
        blocked_reason = row_blocked.get(row.index, "")
        eligible, blocked_text = _pass_eligibility(row, blocked_reason)
        shadow_rows.append({
            "merged": False,
            "order_common": row.order_common,
            "platform_sku": row.platform_sku,
            "product_id": row.product_id,
            "item_group": row.item_group,
            "method": row.shipping_method,
            "sub_orders": [row.order_id],
            "skus": [row.sku],
            "carrier_sku": sku_base(row.sku),
            "pieces": row.qty,
            "qty": row.qty,
            "sale": row.sale,
            "sale_cny": row.sale_cny,
            "freight": row.freight or 0.0,
            "source_rows": [row.index],
            "cost_carrier": eligible,
            "blocked_reason": blocked_reason,
        })
        detail = dict(row.raw)
        detail.update({
            "group_id": "",
            "product_id": row.product_id,
            "order_common": row.order_common,
            "platform_sku": row.platform_sku,
            "carrier_sku": sku_base(row.sku),
            "role": row.shipping_method,
            "pricing_method": row.shipping_method,
            "method_source": row.method_source,
            "merged": False,
            "shipping_method": row.shipping_method,
            "当月给分公司发货类型": str(detail.get("当月给分公司发货类型") or ""),
            "cost_eligible": eligible,
            "cost_blocked": not eligible,
            "cost_blocked_reason": blocked_text,
            "resolution_status": row.resolution_status,
            "pieces": row.qty,
            "pieces_source": "suborder",
            "skus": row.sku,
            "sub_orders": row.order_id,
            "source_rows": str(row.index),
            "blocked_reason": blocked_reason,
        })
        detail_rows.append(detail)

    aux_table = build_aux_table(
        aux_entries, groups, blocked, month=month, sub_index=en_sub_index,
    )
    assertions = [
        _check_qty_conservation(rows, shadow_rows),
        _check_piece_method(groups),
        _check_one_cost(groups, rows, detail_rows),
        _check_aux_qty(rows, aux_rows, aux_table, groups, detail_rows),
        _check_aux_amount(rows, aux_rows, aux_table),
        _check_aux_method(aux_table, groups, blocked),
        _check_keys(groups),
    ]

    cost_eligible_rows = sum(1 for d in detail_rows if d.get("cost_eligible"))
    cost_blocked = [d for d in detail_rows if not d.get("cost_eligible")]
    blocked_reason_counts = Counter(d.get("cost_blocked_reason", "") for d in cost_blocked)
    coverage = _sku_coverage(rows)
    unresolved_rows = sum(1 for r in rows if r.resolution_status == _STATUS_UNRESOLVED)
    ambiguous_rows = sum(1 for r in rows if r.resolution_status == _STATUS_AMBIGUOUS)
    method_counts = {m: sum(1 for g in groups if g.method == m) for m in METHODS}
    blocked_group_reasons = {
        k: sum(1 for b in blocked if b.reason == k)
        for k in sorted({b.reason for b in blocked})
    }
    qty_assertion = next(a for a in assertions if a.name == "原单件数=有效子单之和")
    amount_assertion = next(a for a in assertions if a.name == "原单金额=有效子单之和")
    method_assertion = next(a for a in assertions if a.name == "原单产品/method一致")
    aux_status_counts = Counter(entry["校验结果"] for entry in aux_table)
    stats = {
        "rows_total": len(rows),
        "rows_aux_original": len(aux_rows),
        "rows_unresolved": unresolved_rows,
        "rows_ambiguous": ambiguous_rows,
        "rows_anchored": sum(1 for r in rows if r.raw.get("_anchor_source")),
        "anchor_sources": dict(Counter(
            r.raw.get("_anchor_source") for r in rows if r.raw.get("_anchor_source")
        )),
        "sku_total": len(coverage),
        "sku_covered": sum(1 for c in coverage if c["已覆盖"]),
        "sku_uncovered": sum(1 for c in coverage if not c["已覆盖"]),
        "sku_unresolved": sum(1 for i in sku_issues if i["status"] == _STATUS_UNRESOLVED),
        "sku_ambiguous": sum(1 for i in sku_issues if i["status"] == _STATUS_AMBIGUOUS),
        "method_fallback_rows": sum(1 for r in rows if r.method_source == "item_group_fallback"),
        "method_pending_rows": sum(1 for r in rows if r.method_source == "pending"),
        "non_product_accessory_rows": sum(1 for r in rows if r.method_source == "non_product_accessory"),
        "split_products_groups": len(split_products),
        "split_products_rows": sum(x["n_rows"] for x in split_products),
        "candidate_groups": len(groups) + len(blocked),
        "merged_groups": len(groups),
        "blocked_groups": len(blocked),
        "blocked_reasons": blocked_group_reasons,
        "method_counts": method_counts,
        "rows_in_groups": sum(g.n_rows for g in groups) + sum(b.n_rows for b in blocked),
        "rows_merged": sum(g.n_rows for g in groups),
        "rows_absorbed": sum(g.n_rows - 1 for g in groups),
        "pieces_merged": round(sum(g.pieces for g in groups), 6),
        "pieces_from_aux": sum(1 for g in groups if g.pieces_source == "aux"),
        "aux_groups": sum(1 for g in groups if g.aux_order_ids)
        + sum(1 for b in blocked if b.aux_order_ids),
        "aux_uncovered_product": sum(1 for e in aux_table if not e["产品"]),
        "aux_cross_month": sum(1 for e in aux_table if e["跨月"] == "是"),
        "aux_component_sum_error": sum(
            1 for e in aux_table if e["校验结果"] == "component_sum_error"
        ),
        "aux_used_groups": sum(1 for g in groups if g.aux_used),
        "aux_entries": len(aux_table),
        "aux_status": dict(aux_status_counts),
        "pieces_shadow": round(sum(float(s["pieces"] or 0.0) for s in shadow_rows), 6),
        "qty_total": round(sum(r.qty for r in rows), 6),
        "qty_shadow": round(sum(float(s["qty"] or 0.0) for s in shadow_rows), 6),
        "rows_shadow": len(shadow_rows),
        "rows_detail": len(detail_rows),
        "cost_eligible_rows": cost_eligible_rows,
        "cost_blocked_rows": len(cost_blocked),
        "cost_blocked_reasons": dict(blocked_reason_counts),
        "original_checked": qty_assertion.checked,
        "original_skipped": qty_assertion.skipped,
        "original_skip_reasons": qty_assertion.skip_reasons,
        "original_status": qty_assertion.status,
        "original_coverage": (
            f"{qty_assertion.checked}/"
            f"{qty_assertion.checked + sum(1 for e in aux_table if not e['产品'])}"
        ),
        "original_amount_status": amount_assertion.status,
        "original_method_status": method_assertion.status,
        "assertion_status": {a.name: a.status for a in assertions},
    }
    detail_columns = (
        list(rows[0].raw.keys()) + list(DETAIL_EXTRA_COLUMNS) if rows else list(DETAIL_EXTRA_COLUMNS)
    )
    return MergeShadowResult(
        month=month,
        rows=list(rows),
        aux_rows=list(aux_rows),
        aux_entries=list(aux_entries),
        aux_table=aux_table,
        groups=groups,
        blocked=blocked,
        sku_issues=list(sku_issues),
        shadow_rows=shadow_rows,
        detail_rows=detail_rows,
        sku_coverage=coverage,
        detail_columns=detail_columns,
        assertions=assertions,
        stats=stats,
    )


def run_merge_shadow(
    orders_csv: str | Path,
    ref_map_csv: str | Path,
    en_items_csv: str | Path,
    flags_csv: str | Path | None = None,
    *,
    branch_map_csv: str | Path | None = None,
    month: str = "",
) -> MergeShadowResult:
    """读快照 CSV + EN 明细（含作废原单）→ shadow 结果。只读，不写任何文件。"""
    resolver = EnResolver.from_items_csv(ref_map_csv)
    branch_map = load_branch_map(branch_map_csv) if branch_map_csv else None
    loaded = load_orders(orders_csv, resolver, en_items_csv, flags_csv, branch_map)
    invalid_ids = {k for k, v in _read_invalid_map(flags_csv).items() if v}
    aux_rows = load_aux_original(en_items_csv, invalid_ids, resolver)
    aux_entries = build_aux_entries(aux_rows)
    en_sub_index = load_en_sub_index(en_items_csv, invalid_ids, resolver)
    result = build_merge_shadow(
        loaded.rows, loaded.aux_rows, loaded.sku_issues,
        aux_entries=aux_entries, en_sub_index=en_sub_index, month=month,
    )
    result.stats.update(loaded.en_line_stats)
    return result


# ─────────────────────────── 报告输出（xlsx / md） ───────────────────────────

_STATUS_TEXT = {"pass": "通过", "fail": "阻断", "skip": "跳过"}


def summary_rows(result: MergeShadowResult) -> list[dict]:
    s = result.stats
    method_text = " / ".join(f"{m} {s['method_counts'].get(m, 0)}" for m in METHODS)
    reason_text = ", ".join(
        f"{_BLOCK_REASONS.get(k, k)} {v}" for k, v in s["blocked_reasons"].items()
    )
    cost_blocked_text = ", ".join(
        f"{k or '(未说明)'} {v}" for k, v in s["cost_blocked_reasons"].items()
    )
    aux_text = ", ".join(f"{k} {v}" for k, v in s["aux_status"].items())
    return [
        {"指标": "月份", "值": result.month or ""},
        {"指标": "定价依据", "值": "EN shipping_method；GS 当月给分公司发货类型仅参考；factor/cost_fg 仅对账"},
        {"指标": "输入有效行", "值": s["rows_total"]},
        {"指标": "raw 作废原单 aux 行", "值": s["rows_aux_original"]},
        {"指标": "EN 作废原单条目", "值": s["aux_entries"]},
        {"指标": "EN aux 校验结果", "值": aux_text or "无"},
        {"指标": "关联 aux 的组（含阻断）", "值": s["aux_groups"]},
        {"指标": "aux 兜底件数/载体组", "值": s["aux_used_groups"]},
        {"指标": "候选组", "值": s["candidate_groups"]},
        {"指标": "合并组", "值": s["merged_groups"]},
        {"指标": "合并组 pricing_method 分布", "值": method_text},
        {"指标": "阻断组", "值": s["blocked_groups"]},
        {"指标": "阻断原因", "值": reason_text or "无"},
        {"指标": "组内行数", "值": s["rows_in_groups"]},
        {"指标": "合并吸收行数", "值": s["rows_absorbed"]},
        {"指标": "合并组件数", "值": s["pieces_merged"]},
        {"指标": "件数来自 EN aux 的组", "值": s["pieces_from_aux"]},
        {"指标": "全月发货数量", "值": s["qty_total"]},
        {"指标": "合并明细行数", "值": s["rows_detail"]},
        {"指标": "可自动定价行 cost_eligible", "值": s["cost_eligible_rows"]},
        {"指标": "不可定价行 cost_blocked", "值": s["cost_blocked_rows"]},
        {"指标": "不可定价原因", "值": cost_blocked_text or "无"},
        {"指标": "原单件数校验", "值": f"{_STATUS_TEXT.get(s['original_status'], s['original_status'])}"
         f"（校验 {s['original_checked']} / 跳过 {s['original_skipped']}；"
         f"原单覆盖 {s['original_coverage']}，未覆盖产品 {s['aux_uncovered_product']}）"},
        {"指标": "原单金额校验", "值": _STATUS_TEXT.get(s["original_amount_status"], s["original_amount_status"])},
        {"指标": "原单产品/method 校验", "值": _STATUS_TEXT.get(s["original_method_status"], s["original_method_status"])},
        {"指标": "SKU 覆盖", "值": f"{s['sku_covered']} / {s['sku_total']}（未覆盖 {s['sku_uncovered']}）"},
        {"指标": "未登记 SKU / 行", "值": f"{s['sku_unresolved']} / {s['rows_unresolved']}"},
        {"指标": "歧义 SKU / 行", "值": f"{s['sku_ambiguous']} / {s['rows_ambiguous']}"},
        {"指标": "同订单锚定行", "值": f"{s['rows_anchored']}（{s['anchor_sources'] or '无'}）"},
        {"指标": "断言结果", "值": " / ".join(
            f"{k}:{_STATUS_TEXT.get(v, v)}" for k, v in s["assertion_status"].items()
        )},
        {"指标": "无阻断（fail=0）", "值": "是" if result.ok else "否"},
    ]


def group_rows(result: MergeShadowResult) -> list[dict]:
    rows = [{
        "group_id": g.group_id,
        "订单号公共部分": g.order_common,
        "平台SKU": g.platform_sku,
        "产品": g.product_id,
        "物料组": g.item_group,
        "子单": ", ".join(g.sub_orders),
        "SKU": ", ".join(g.skus),
        "载体SKU": g.carrier_sku,
        "载体形态": g.carrier_shape,
        "role": g.method,
        "shipping_method": g.method,
        "pricing_method": g.method,
        "cost_eligible": True,
        "aux_used": g.aux_used,
        "pieces_source": g.pieces_source,
        "aux_order_ids": ", ".join(g.aux_order_ids),
        "行数": g.n_rows,
        "件数": g.pieces,
        "发货数量": g.qty_sum,
        "售价": g.sale_sum,
        "售价(人民币)": g.sale_cny_sum,
        "运费": g.freight_sum,
    } for g in result.groups]
    if not any(r.freight is not None for r in result.rows):
        for row in rows:
            row.pop("运费")
    return rows


def blocked_rows(result: MergeShadowResult) -> list[dict]:
    rows = [{
        "类型": "组阻断",
        "订单号公共部分": b.order_common,
        "平台SKU": b.platform_sku,
        "产品": b.product_id,
        "行数": b.n_rows,
        "SKU": ", ".join(b.skus),
        "原因": _BLOCK_REASONS.get(b.reason, b.reason),
        "原因码": b.reason,
        "aux原单号": ", ".join(b.aux_order_ids),
        "cost_eligible": False,
    } for b in result.blocked]
    for issue in result.sku_issues:
        rows.append({
            "类型": _STATUS_CN.get(issue["status"], issue["status"]),
            "订单号公共部分": "",
            "平台SKU": "",
            "产品": ", ".join(issue["products"]),
            "行数": issue["rows"],
            "SKU": issue["sku"],
            "原因": "别名未登记" if issue["status"] == _STATUS_UNRESOLVED else "一个别名命中多个产品",
            "原因码": issue["status"],
            "aux原单号": "",
            "cost_eligible": False,
        })
    return rows


def assertion_rows(result: MergeShadowResult) -> list[dict]:
    return [{
        "断言": a.name,
        "结果": _STATUS_TEXT.get(a.status, a.status),
        "检查数": a.checked,
        "跳过数": a.skipped,
        "跳过原因": "; ".join(f"{k}:{v}" for k, v in a.skip_reasons.items()),
        "说明": a.detail,
        "违规": str(a.violations[:20]) if a.violations else "",
    } for a in result.assertions]


def render_markdown(result: MergeShadowResult, phase2=None) -> str:
    s = result.stats
    method_text = " / ".join(f"{m} {s['method_counts'].get(m, 0)}" for m in METHODS)
    cost_blocked_text = "；".join(
        f"{k or '(未说明)'} {v}" for k, v in s["cost_blocked_reasons"].items()
    ) or "无"
    aux_text = " / ".join(f"{k} {v}" for k, v in s["aux_status"].items()) or "无"
    lines = [
        f"# 拆包合并 shadow — {result.month or '(未标注月份)'}",
        "",
        "> 只读：不改成本列、不写 GS/EN。" + PRICING_BASIS_NOTE,
        "",
        "## 统计",
        "",
        f"- 输入有效行：{s['rows_total']}（raw 作废原单 aux {s['rows_aux_original']} 行）",
        f"- EN 作废原单：{s['aux_entries']} 条（{aux_text}）；"
        f"关联合并组 {s['aux_groups']} 个，兜底件数/载体 {s['aux_used_groups']} 个",
        f"- 候选组：{s['candidate_groups']} = 合并 {s['merged_groups']} + 阻断 {s['blocked_groups']}",
        f"- 合并组 pricing_method：{method_text}",
        f"- 组内行数：{s['rows_in_groups']}；合并吸收 {s['rows_absorbed']} 行",
        f"- 件数：合并组 {s['pieces_merged']:g}（aux 兜底 {s['pieces_from_aux']} 组）；"
        f"合并视图 {s['pieces_shadow']:g}（全月发货数量 {s['qty_total']:g}）",
        f"- 合并明细行数：{s['rows_detail']}；合并视图行数：{s['rows_shadow']}",
        f"- 可自动定价行：{s['cost_eligible_rows']}；不可定价行：{s['cost_blocked_rows']}"
        f"（{cost_blocked_text}）",
        f"- 原单件数校验：{_STATUS_TEXT.get(s['original_status'], s['original_status'])}；"
        f"校验 {s['original_checked']} 项 / 跳过 {s['original_skipped']} 项；"
        f"原单覆盖 {s['original_coverage']}（产品未解析未覆盖 {s['aux_uncovered_product']} 条）",
        f"- 原单金额校验：{_STATUS_TEXT.get(s['original_amount_status'], s['original_amount_status'])}；"
        f"原单产品/method：{_STATUS_TEXT.get(s['original_method_status'], s['original_method_status'])}",
        f"- SKU 覆盖：{s['sku_covered']} / {s['sku_total']}（未覆盖 {s['sku_uncovered']}）；"
        f"未登记 {s['sku_unresolved']} 个 / {s['rows_unresolved']} 行，"
        f"歧义 {s['sku_ambiguous']} 个 / {s['rows_ambiguous']} 行；"
        f"同订单锚定 {s['rows_anchored']} 行（{s['anchor_sources'] or '无'}）",
        f"- 断言：{'无 fail' if result.ok else '**存在 fail，整体阻断**'}",
        "",
        "## 断言",
        "",
        "| 断言 | 结果 | 检查数 | 跳过数 | 说明 |",
        "|---|---|---:|---:|---|",
    ]
    for row in assertion_rows(result):
        lines.append(
            f"| {row['断言']} | {row['结果']} | {row['检查数']} | {row['跳过数']} | {row['说明']} |"
        )
    for assertion in result.assertions:
        if assertion.skip_reasons:
            lines += ["", f"**{assertion.name} 跳过原因**：" + "；".join(
                f"{k} {v}" for k, v in assertion.skip_reasons.items()
            )]

    lines += ["", f"## EN 作废原单（aux）校验（{len(result.aux_table)}）", ""]
    if result.aux_table:
        lines.append(
            "| 原单号 | 产品 | method | qty(件数) | 组件qty | 子单qty | 关联group_id | 关联月 | 跨月 | 结果 | 原因 | 兜底 |"
        )
        lines.append("|---|---|---|---:|---:|---:|---|---|---|---|---|---|")
        for row in result.aux_table:
            lines.append(
                f"| {row['原单号']} | {row['产品']} | {row['method']} | {row['qty']:g} | "
                f"{row['原始组件qty']:g} | {row['子单qty']:g} | {row['关联group_id']} | "
                f"{row['关联月']} | {row['跨月']} | {row['校验结果']} | "
                f"{row['原因']} | {row['是否用于兜底']} |"
            )
        lines.append("")
        lines.append("> `cost_fg`/`factor` 仅列在 xlsx aux 表中作对账参考，不参与主计算。")
    else:
        lines.append("- 无 EN 作废原单行")

    lines += ["", f"## 合并组（{len(result.groups)}）", ""]
    if result.groups:
        lines.append(
            "| group_id | 订单号公共部分 | 平台SKU | 产品 | 子单 | SKU | 载体 | pricing_method | 件数 | 件数来源 | 行数 | 售价(人民币) |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---:|---:|")
        for g in result.groups:
            lines.append(
                f"| {g.group_id} | {g.order_common} | {g.platform_sku} | {g.product_id} | "
                f"{', '.join(g.sub_orders)} | {', '.join(g.skus)} | {g.carrier_sku} | "
                f"{g.method} | {g.pieces:g} | {g.pieces_source} | {g.n_rows} | {g.sale_cny_sum:.2f} |"
            )
    else:
        lines.append("- 无")

    rows = blocked_rows(result)
    lines += ["", f"## 阻断清单（{len(rows)}）", ""]
    if rows:
        lines.append("| 类型 | 订单号公共部分 | 平台SKU | 产品 | 行数 | SKU | 原因 |")
        lines.append("|---|---|---|---|---:|---|---|")
        for r in rows:
            lines.append(
                f"| {r['类型']} | {r['订单号公共部分']} | {r['平台SKU']} | {r['产品']} | "
                f"{r['行数']} | {r['SKU']} | {r['原因']} |"
            )
    else:
        lines.append("- 无")

    uncovered = [c for c in result.sku_coverage if not c["已覆盖"]]
    lines += ["", f"## SKU 覆盖与 EN 解析依据（未覆盖 {len(uncovered)}）", ""]
    lines.append(REF_CODE_EQUIVALENCE)
    lines.append("")
    if uncovered:
        lines.append("| SKU | 行数 | 状态 | 候选产品 | 出现 method |")
        lines.append("|---|---:|---|---|---|")
        for c in uncovered:
            lines.append(
                f"| {c['SKU']} | {c['行数']} | {c['状态']} | {c['产品']} | {c['出现method']} |"
            )
    else:
        lines.append("- 无未覆盖 SKU")
    lines.append("")
    if phase2 is not None:
        from .bom_cost import phase2_markdown
        lines.append(phase2_markdown(phase2))
    return "\n".join(lines)


def write_shadow_xlsx(result: MergeShadowResult, path: str | Path, phase2=None) -> Path:
    """写出 shadow xlsx（汇总/合并明细/合并组/EN原单(aux)/阻断清单/SKU覆盖/Phase2/断言）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    aux_export = [
        {k: v for k, v in row.items() if not k.startswith("_")}
        for row in result.aux_table
    ]
    summary = summary_rows(result)
    if phase2 is not None:
        from .bom_cost import PHASE2_COLUMNS, phase2_diff_breakdown, phase2_summary_rows
        summary = summary + phase2_summary_rows(phase2)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        detail = pd.DataFrame(result.detail_rows)
        if len(detail):
            detail = detail.reindex(columns=result.detail_columns)
        detail.to_excel(writer, sheet_name="合并明细", index=False)
        pd.DataFrame(group_rows(result)).to_excel(writer, sheet_name="合并组", index=False)
        pd.DataFrame(aux_export, columns=list(AUX_COLUMNS)).to_excel(
            writer, sheet_name="EN原单(aux)", index=False,
        )
        pd.DataFrame(blocked_rows(result)).to_excel(writer, sheet_name="阻断清单", index=False)
        pd.DataFrame(result.sku_coverage).to_excel(writer, sheet_name="SKU覆盖", index=False)
        if phase2 is not None:
            pd.DataFrame(phase2.rows).reindex(columns=list(PHASE2_COLUMNS)).to_excel(
                writer, sheet_name="Phase2成本", index=False,
            )
            pd.DataFrame(phase2_diff_breakdown(phase2)).to_excel(
                writer, sheet_name="差异归因", index=False,
            )
        a_rows = assertion_rows(result)
        if phase2 is not None:
            a_rows = a_rows + [{
                "断言": a.name,
                "结果": _STATUS_TEXT.get(a.status, a.status),
                "检查数": a.checked,
                "跳过数": a.skipped,
                "跳过原因": "; ".join(f"{k}:{v}" for k, v in a.skip_reasons.items()),
                "说明": a.detail,
                "违规": str(a.violations[:20]) if a.violations else "",
            } for a in phase2.assertions]
        pd.DataFrame(a_rows).to_excel(writer, sheet_name="断言", index=False)
    return path
