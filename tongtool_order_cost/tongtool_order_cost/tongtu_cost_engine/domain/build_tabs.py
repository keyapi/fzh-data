# -*- coding: utf-8 -*-
"""Phase 3.8：从原始订单重建 self 166 / FBA 95 / merged 78 三张订单表。

目标：停用 20250409 合并EN成本 Colab。输入全部来自本地快照 / EN / GS：
- self 166：通途原始订单（已删特殊订单）→ 成熟拆单合并（split_merge）
  → BOM 四列成本（bom_cost）→ FX 汇率 + 仓库成本来源映射 → 166 列。
- FBA 95：GS FBA 销量表（业务骨架）→ FBA shadow 78 列（EN FBA 明细 + BOM 成本）
  → 按 `订单数量` 展开 UUID 行（首行承载销量/销售额，其余行仅保留单位成本）。
- merged 78：self 166 + FBA 95 按 78 列合同拼接；附 95↔78 粒度对账。

与旧 Colab 的差异（有意为之）：
- self 行集合 = 成熟合并组 1 行 + 透传行；**不复刻**旧表的“组件行 + 合并展示行”双计。
- 合并行的 发货数量 = 件数（pieces）、售价 = 组内全部组件行售价之和、
  售价*汇率 = 组售价 × 财务汇率、运费 = 组内 `物流商运费` 之和（真实尾程）。
- 商品属性优先取 EN 物料组 / BOM（`品类尺寸面料编码` 写入 EN 物料号）；
  旧表仅作为历史属性/系数的兜底来源，不参与行集合与金额。
"""
from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .bom_cost import Phase2Result, compute_phase2, load_bom_cost
from .fba_shadow import build_fba_shadow, validate_fba_cache
from .phase36_fill import (
    _check_cells,
    _fill_cells,
    _num,
)
from .split_merge import (
    EnResolver,
    MergeShadowResult,
    normalize_sku,
    run_merge_shadow,
    sku_base,
)
from .tab_contracts import FBA95_COLUMNS, MERGED78_COLUMNS, SELF166_COLUMNS

TZ_CN = timezone(timedelta(hours=8))
TOL = 1e-4
UUID_NS = uuid.uuid5(uuid.NAMESPACE_URL, "fzh-data/tongtool/build-order-tabs")


def _text(v: object) -> str:
    s = str(v).strip() if v is not None else ""
    return "" if s.upper() in ("NAN", "NONE", "NULL") else s


def _fmt(v: float | None) -> str:
    if v is None:
        return ""
    return f"{round(v, 6):.6f}".rstrip("0").rstrip(".")


def _source_indices(value: object) -> list[int]:
    out: list[int] = []
    for part in re.split(r"[,;\s]+", _text(value)):
        if part.isdigit():
            out.append(int(part))
    return out


def _uuid_for(month: str, site: str, msku: str, sku: str, idx: int) -> str:
    return str(uuid.uuid5(UUID_NS, f"{month}|{site.upper()}|{msku.upper()}|{sku.upper()}|{idx}"))


@dataclass
class BuildResult:
    month: str
    self_rows: list[dict]
    fba_rows: list[dict]
    merged_rows: list[dict]
    assertions: list[dict]
    stats: dict
    parity: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(a["status"] != "fail" for a in self.assertions)


# ─────────────────────────── 输入 ───────────────────────────


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False)


SPECIAL_ORDER_COL = "通途订单号"

# 第三方/大件云仓：不参与自营成本计算（旧表同样为 0），显式零成本而非阻断。
THIRD_PARTY_WAREHOUSES = {"大件云仓"}


def _merge_alias_overrides(ref_map: Path, overrides: Path, out_dir: Path) -> Path:
    """把本地别名补丁并入 EN 物料表（尚未在 EN 登记的客户物料号）。"""
    base = _read_csv(ref_map)
    extra = _read_csv(overrides).reindex(columns=base.columns)
    merged = pd.concat([base, extra], ignore_index=True)
    dest = out_dir / "ref_map_merged.csv"
    merged.to_csv(dest, index=False, encoding="utf-8-sig")
    return dest


def load_special_order_ids(path: str | Path) -> set[str]:
    """读 `处理特殊订单` 导出清单（fetch_special_orders.py 产出），返回要删除的订单号。"""
    p = Path(path)
    df = _read_csv(p)
    if SPECIAL_ORDER_COL not in df.columns:
        raise ValueError(f"特殊订单清单缺列 {SPECIAL_ORDER_COL}: {p}")
    return {oid for oid in (_text(v) for v in df[SPECIAL_ORDER_COL]) if oid}


def filter_special_orders(
    raw: pd.DataFrame, ids: set[str]
) -> tuple[pd.DataFrame, list[str], int]:
    """按删除清单过滤 raw；返回 (过滤后 df, 命中的订单号, 删除行数)。"""
    if not ids or "订单号" not in raw.columns:
        return raw, [], 0
    hit = raw["订单号"].map(_text).isin(ids)
    removed = sorted(set(raw.loc[hit, "订单号"].map(_text)))
    return raw.loc[~hit].copy(), removed, int(hit.sum())


def _load_fx(path: Path) -> dict[str, float]:
    if not path.exists():
        raise FileNotFoundError(f"汇率表不存在: {path}")
    df = _read_csv(path)
    out: dict[str, float] = {}
    for rec in df.to_dict("records"):
        cur = _text(rec.get("收款币种")).upper()
        rate = _num(rec.get("汇率"))
        if cur and rate is not None:
            out[cur] = rate
    return out


def _load_wh_sources(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, sep="\t", dtype=str, low_memory=False, keep_default_na=False)
    return {_text(r.get("发货仓库")): r for r in df.to_dict("records")}


def _load_attr_master(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, sep="\t", dtype=str, low_memory=False, keep_default_na=False)
    out: dict[tuple[str, str], dict] = {}
    for r in df.to_dict("records"):
        kind = _text(r.get("键类型"))
        key = _text(r.get("键值"))
        if kind and key:
            out[(kind, key)] = r
    # 仅暴露按 SKU 的查询入口（platform 键冲突较多，只作二级兜底）
    return out


def _old_index(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        return {}
    out: dict[str, dict] = {}
    for r in _read_csv(path).to_dict("records"):
        order = _text(r.get("订单号")).upper()
        sku = normalize_sku(r.get("通途SKU"))
        plat = normalize_sku(r.get("平台SKU_统一") or r.get("平台SKU"))
        if order and sku:
            out.setdefault(f"{order}|{sku}", r)
        if order and plat:
            out.setdefault(f"{order}|PT:{plat}", r)
    return out


def _lookup_old(old: Mapping[str, dict], order: object, sku: object, platform: object) -> dict | None:
    o = _text(order).upper()
    if not o:
        return None
    hit = old.get(f"{o}|{normalize_sku(sku)}")
    if hit is None:
        hit = old.get(f"{o}|PT:{normalize_sku(platform)}")
    return hit


def _old_fba_index(path: Path | None) -> dict[str, dict]:
    """旧 FBA 95 表 → {(站点|MSKU|SKU): row}；仅作产品属性/财务列兜底。"""
    if not path or not path.exists():
        return {}
    out: dict[str, dict] = {}
    for r in _read_csv(path).to_dict("records"):
        key = "|".join((_text(r.get("站点")).upper(), normalize_sku(r.get("MSKU")),
                        normalize_sku(r.get("SKU"))))
        if key.strip("|"):
            out.setdefault(key, r)
    return out


# ─────────────────────────── 产品属性 ───────────────────────────

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?(?:\s*[xX×*]\s*\d+(?:\.\d+)?)*)\s*(?:cm|CM)?\s*$")
_DIMS_RE = re.compile(r"(\d+(?:\.\d+)?(?:\s*[*xX×]\s*\d+(?:\.\d+)?){1,3})")


def _parse_bom_attrs(bom_row: Mapping | None) -> dict:
    """BOM 行 → 品类 / 面料 / 尺寸 / 有无扣 / 带*尺寸 / 尺寸先大后小。"""
    if not bom_row:
        return {}
    raw = _text(bom_row.get("item_zlmb_name")) or _text(bom_row.get("item_fg_name"))
    name = raw.split("#", 1)[-1].strip()
    if not name:
        return {}
    tokens = [t.strip() for t in re.split(r"-", name) if t.strip()]
    size = ""
    if tokens:
        m = _SIZE_RE.search(tokens[-1])
        if m and any(ch.isdigit() for ch in tokens[-1]):
            size = m.group(1).replace(" ", "").replace("×", "x").replace("X", "x").replace("*", "x")
            tokens = tokens[:-1]
    fabric = tokens[-1] if len(tokens) >= 2 else ""
    category = "-".join(tokens[:-1]) if len(tokens) >= 2 else (tokens[0] if tokens else "")
    out = {
        "品类": category,
        "面料提取": fabric,
        "材料名称": fabric,
        "尺寸": size.split("x")[0] if size else "",
    }
    if category.startswith("三角") or "三角靠枕" in category:
        out["有无扣"] = "无扣" if "无扣" in name else "有扣"
    dims = _DIMS_RE.search(_text(bom_row.get("item_fg_name")) or raw)
    if dims:
        parts = re.split(r"[*xX×]", dims.group(1).replace(" ", ""))
        out["带*尺寸"] = "*".join(parts)
        try:
            out["尺寸先大后小"] = "*".join(sorted(parts, key=lambda x: float(x), reverse=True))
        except ValueError:
            pass
    return out


def _parse_name_attrs(name: str) -> dict:
    """原始产品名兜底：尺寸 / 带*尺寸 / 尺寸先大后小 / 有无扣 / 件套。"""
    s = _text(name)
    out: dict[str, str] = {}
    if "无扣" in s:
        out["有无扣"] = "无扣"
    elif "有扣" in s:
        out["有无扣"] = "有扣"
    m = _DIMS_RE.search(s)
    if m:
        parts = re.split(r"[*xX×]", m.group(1).replace(" ", ""))
        out["带*尺寸"] = "*".join(parts)
        try:
            out["尺寸先大后小"] = "*".join(sorted(parts, key=lambda x: float(x), reverse=True))
        except ValueError:
            pass
    m = re.search(r"(\d{2,3})\s*(?:cm|CM)", s)
    if m:
        out["尺寸"] = m.group(1)
    m = re.search(r"SET(\d+)", s, re.IGNORECASE)
    if m:
        out["件套"] = f"SET{int(m.group(1))}"
    return out


def _warehouse_source(wh: str, sources: Mapping[str, dict]) -> dict:
    wh = _text(wh)
    if not wh:
        return {}
    hit = sources.get(wh)
    if hit:
        return dict(hit)
    # 多渠道仓库：按仓库名里的国家粗分（与 Colab cell_056 一致）
    if "多渠道仓库" in wh:
        for key, rec in sources.items():
            if "多渠道仓库" in key and (wh[:2] in key or key[:2] in wh):
                return dict(rec)
    for key, rec in sources.items():
        if key and (key in wh or wh in key):
            return dict(rec)
    return {}


# ─────────────────────────── self 166 ───────────────────────────


def _build_self_rows(
    shadow: MergeShadowResult,
    phase2: Phase2Result,
    raw: pd.DataFrame,
    fx: Mapping[str, float],
    wh_sources: Mapping[str, dict],
    resolver: EnResolver,
    bom_index: Mapping[str, list[dict]],
    old: Mapping[str, dict],
    attr_master: Mapping[tuple[str, str], dict],
) -> tuple[list[dict], list[dict], dict]:
    if len(shadow.detail_rows) != len(phase2.rows):
        raise ValueError(
            f"Phase1 明细 {len(shadow.detail_rows)} 与 Phase2 行 {len(phase2.rows)} 不一致"
        )
    records = raw.to_dict("records")
    rows: list[dict] = []
    checks: list[dict] = []
    unmapped_wh: Counter = Counter()
    attr_misses: Counter = Counter()
    fx_misses: Counter = Counter()

    for detail, p2 in zip(shadow.detail_rows, phase2.rows):
        out = {c: "" for c in SELF166_COLUMNS}
        merged = bool(detail.get("merged"))
        src_idx = _source_indices(detail.get("source_rows"))
        src_rows = [records[i] for i in src_idx if 0 <= i < len(records)]
        cost_qty = _num(detail.get("pieces")) if merged else _num(detail.get("发货数量")) or 0.0
        cost_qty = cost_qty or 0.0

        # 原始列直接透传（detail 已含 raw 全列）
        for col in SELF166_COLUMNS:
            if col in detail and _text(detail.get(col)):
                out[col] = _text(detail.get(col))
        # raw 列名映射
        out["品类orig"] = _text(detail.get("品类"))
        out["头程运费tongtool"] = _text(detail.get("头程运费"))

        # 金额/数量
        if merged:
            out["发货数量"] = _fmt(cost_qty)
            out["售价"] = _text(detail.get("售价")) or _fmt(
                sum(_num(r.get("售价")) or 0.0 for r in src_rows))
            out["售价(人民币)"] = _text(detail.get("售价(人民币)")) or _fmt(
                sum(_num(r.get("售价(人民币)")) or 0.0 for r in src_rows))
        else:
            out["发货数量"] = _text(detail.get("发货数量"))
            out["售价"] = _text(detail.get("售价"))
            out["售价(人民币)"] = _text(detail.get("售价(人民币)"))

        sale = _num(out.get("售价")) or 0.0
        cur = _text(detail.get("收款币种")).upper()
        rate = fx.get(cur)
        if rate is None:
            implied = None
            cny = _num(out.get("售价(人民币)"))
            if cny is not None and sale:
                implied = cny / sale
            rate = implied if implied is not None else 1.0
            fx_misses[cur or "(空)"] += 1
        out["汇率"] = _fmt(rate) if rate is not None else ""
        sales_cny_fx = sale * (rate or 1.0) if rate is not None else None
        out["售价*汇率"] = _fmt(sales_cny_fx)

        # 真实尾程：物流商运费（组内求和）
        freight_values = [_num(r.get("物流商运费")) for r in src_rows]
        freight_values = [v for v in freight_values if v is not None]
        freight = round(sum(freight_values), 6) if freight_values else 0.0
        out["运费"] = _fmt(freight)
        out["包裹总运费"] = _text(detail.get("包裹总运费"))

        # 仓库 → 成本来源映射
        wh = _text(detail.get("发货仓库"))
        wsrc = _warehouse_source(wh, wh_sources)
        if wsrc:
            for col in ("对应成本工作簿", "成本来源编码", "发货仓分类", "头程运费来源编码",
                        "二次加工成本来源编码", "发货区域", "发货仓按销售汇总分类"):
                out[col] = _text(wsrc.get(col))
        else:
            unmapped_wh[wh] += 1

        method = (_text(p2.get("method"))
                  or _text(detail.get("pricing_method"))
                  or _text(detail.get("shipping_method")))
        out["是否皮壳"] = "皮壳" if method == "皮壳" else "否"
        out["当月给分公司发货类型"] = method if out.get("发货仓分类") == "分公司" else ""
        out["_method"] = method

        # 产品属性：EN 物料组 / BOM 优先
        old_row = _lookup_old(old, detail.get("订单号"), detail.get("通途SKU"),
                              detail.get("平台SKU"))
        item_fg = _text(p2.get("item_fg"))
        product_id = _text(detail.get("product_id"))
        group = resolver.item_group_for(product_id) or resolver.item_group_for_item(item_fg)
        attrs: dict[str, str] = {}
        bom_rows = bom_index.get(item_fg) or []
        if len(bom_rows) == 1:
            attrs.update({k: v for k, v in _parse_bom_attrs(bom_rows[0]).items() if v})
        name_attrs = _parse_name_attrs(_text(detail.get("产品名称")))
        for k, v in name_attrs.items():
            attrs.setdefault(k, v)

        out["品类"] = group or attrs.get("品类") or out.get("品类orig", "")
        out["品类统一名"] = out["品类"]
        out["品类别名"] = out["品类"]
        for col in ("面料提取", "材料名称", "尺寸", "有无扣", "带*尺寸", "尺寸先大后小", "件套"):
            if attrs.get(col):
                out[col] = attrs[col]
        out["品类尺寸面料编码"] = item_fg

        # 历史属性兜底（旧表 = 产品主数据 + 财务列；不参与行集合/金额）
        sku_key = normalize_sku(detail.get("通途SKU"))
        plat_key = normalize_sku(detail.get("平台SKU_统一") or detail.get("平台SKU"))
        master = attr_master.get(("sku", sku_key)) or attr_master.get(("platform", plat_key)) or {}
        for col in ("品类编码", "品类尺寸编码", "材料编码", "件套", "美版5尺寸"):
            if not out.get(col):
                val = _text((old_row or {}).get(col)) or _text(master.get(col))
                if val:
                    out[col] = val
        for col in ("产品名称去除品类", "当月是否新品", "产品发售日期",
                    "平台SKU-渠道账号&实际运营人员", "美国分区", "海外仓成本_USHWC"):
            val = _text((old_row or {}).get(col)) or _text(master.get(col))
            if val:
                out[col] = val
        if not out.get("产品名称去除品类"):
            out["产品名称去除品类"] = _text(detail.get("产品名称"))
        if not out.get("件套"):
            m = re.search(r"SET(\d+)", _text(detail.get("产品名称")), re.IGNORECASE)
            if m:
                out["件套"] = f"SET{int(m.group(1))}"
        for col in ("品类编码", "品类尺寸编码", "材料编码", "美版5尺寸", "当月是否新品",
                    "产品发售日期", "平台SKU-渠道账号&实际运营人员"):
            if not out.get(col):
                attr_misses[col] += 1

        out["美国邮编前3位"] = (
            _text(detail.get("邮编"))[:3]
            if _text(detail.get("国家/地区")).upper() == "US" else ""
        )

        # 合并元数据
        platform = _text(detail.get("平台SKU"))
        out["订单号_公共部分"] = _text(detail.get("order_common"))
        out["平台SKU_统一"] = normalize_sku(platform)
        out["需要合并"] = "TRUE" if merged else "FALSE"
        out["包含包裹"] = "TRUE" if merged else "FALSE"
        out["merge_group"] = _text(detail.get("group_id")) if merged else ""
        out["通途SKU_公共部分"] = sku_base(_text(detail.get("通途SKU")))
        out["sku_base"] = sku_base(_text(detail.get("通途SKU")))
        if not out.get("suffix"):
            m = re.search(r"-(\d{1,3})$", platform)
            if m:
                out["suffix"] = m.group(1)

        # EN 绍兴包装成本（单位成本，来自 BOM）
        if len(bom_rows) == 1:
            out["EN绍兴包装半成品成本"] = _fmt(_num(bom_rows[0].get("cost_sxbzbcp")))
            out["EN绍兴包装成品成本"] = _fmt(_num(bom_rows[0].get("cost_sxbzcp")))

        # 系数 / 海外仓单位成本：旧表继承
        kc = _text((old_row or {}).get("绍兴成本系数")) or "1"
        k2 = _text((old_row or {}).get("二次加工成本系数")) or "1"
        ksx = _text((old_row or {}).get("绍兴二次加工成本系数")) or "1"
        overseas = _num((old_row or {}).get("海外仓成本"))
        if overseas is None:
            overseas = _num(out.get("海外仓成本"))

        # 四列成本
        status = _text(p2.get("status"))
        reason = _text(p2.get("reason"))
        if status != "ok" and _text(out.get("发货仓库")) in THIRD_PARTY_WAREHOUSES:
            # 第三方大件云仓：不属自营成本口径，显式零成本（旧表同为 0），不按未登记阻断
            cells = _fill_cells(
                shell=0.0, shell_in=0.0, shell_out=0.0, sx2=0.0, proc=0.0, head=0.0,
                qty=cost_qty, sales=sales_cny_fx, freight=freight, overseas=0.0,
                kc=kc, k2=k2, ksx=ksx, status="ok", reason="third_party_warehouse",
            )
            cells["cost_reason"] = "third_party_warehouse"
        elif status == "non_product_accessory":
            cells = _fill_cells(
                shell=0.0, shell_in=0.0, shell_out=0.0, sx2=0.0, proc=0.0, head=0.0,
                qty=cost_qty, sales=sales_cny_fx, freight=freight, overseas=overseas or 0.0,
                kc=kc, k2=k2, ksx=ksx, status="ok", reason=status,
            )
            cells["cost_reason"] = status
        elif status == "ok" and cost_qty > 0:
            unit = {}
            ok_units = True
            for col in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本"):
                total = _num(p2.get(col))
                if total is None:
                    ok_units = False
                    reason = f"{col}:phase2缺失"
                    break
                unit[col] = total / cost_qty
            if ok_units:
                shell = unit["皮壳成本"]
                # 新引擎只有 BOM cost_fg 一个皮壳口径；含/不含包装两列统一写当前值，
                # 不再继承旧写回的历史皮壳（否则 76.961 与 53.939 并存）。
                cells = _fill_cells(
                    shell=shell, shell_in=shell, shell_out=shell,
                    sx2=unit["绍兴二次加工成本"], proc=unit["二次加工成本"],
                    head=unit["头程运费金额"], qty=cost_qty, sales=sales_cny_fx,
                    freight=freight, overseas=overseas or 0.0,
                    kc=kc, k2=k2, ksx=ksx, status="ok",
                )
            else:
                cells = _fill_cells(
                    shell=None, shell_in=None, shell_out=None, sx2=None, proc=None, head=None,
                    qty=cost_qty, sales=None, freight=None, overseas=None,
                    kc=kc, k2=k2, ksx=ksx, status="blocked", reason=reason,
                )
        else:
            cells = _fill_cells(
                shell=None, shell_in=None, shell_out=None, sx2=None, proc=None, head=None,
                qty=cost_qty, sales=None, freight=None, overseas=None,
                kc=kc, k2=k2, ksx=ksx,
                status="blocked" if status == "blocked" else "skipped",
                reason=reason or status or "cost_unavailable",
            )
        out.update(cells)
        if cells.get("cost_status") != "ok":
            # 成本阻断时四列留空，但真实尾程运费仍要保留（否则运费守恒断言失真）
            out["运费"] = _fmt(freight)
        rows.append(out)

        fails = _check_cells(cells, cost_qty, sales_cny_fx)
        if fails:
            checks.append({
                "订单号": out.get("订单号"), "通途SKU": out.get("通途SKU"),
                "group": out.get("merge_group"), "fails": fails,
            })

    stats = {
        "rows": len(rows),
        "merged_rows": sum(1 for r in rows if r.get("需要合并") == "TRUE"),
        "unmapped_warehouses": dict(unmapped_wh),
        "fx_misses": dict(fx_misses),
        "attr_misses": dict(attr_misses),
        "cost_blocked": sum(1 for r in rows if not r.get("cost_status") == "ok"),
    }
    return rows, checks, stats


# ─────────────────────────── FBA 95 ───────────────────────────


def _fba_shadow_index(shadow: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in shadow.to_dict("records"):
        key = "|".join((
            _text(r.get("site")).upper(),
            normalize_sku(r.get("gs_msku") or r.get("平台SKU")),
            normalize_sku(r.get("gs_sku") or r.get("通途SKU")),
        ))
        out.setdefault(key, r)
    return out


def _build_fba_rows(
    month: str,
    gs: pd.DataFrame,
    shadow: pd.DataFrame,
    *,
    resolver: EnResolver | None = None,
    bom_index: Mapping[str, list[dict]] | None = None,
    wh_sources: Mapping[str, dict] | None = None,
    attr_master: Mapping[tuple[str, str], dict] | None = None,
    old: Mapping[str, dict] | None = None,
) -> tuple[list[dict], list[dict], dict]:
    shadow_idx = _fba_shadow_index(shadow)
    bom_index = bom_index or {}
    wh_sources = wh_sources or {}
    attr_master = attr_master or {}
    old = old or {}
    rows: list[dict] = []
    checks: list[dict] = []
    miss: list[dict] = []
    for rec in gs.to_dict("records"):
        site = _text(rec.get("站点"))
        msku = _text(rec.get("MSKU"))
        sku = _text(rec.get("SKU"))
        key = "|".join((site.upper(), normalize_sku(msku), normalize_sku(sku)))
        s = shadow_idx.get(key)
        n = int(_num(rec.get("订单数量")) or 0)
        n = max(n, 1)
        qty = _num(rec.get("销量")) or 0.0
        sales = _num(rec.get("销售额")) or 0.0
        if s is None:
            miss.append({"站点": site, "MSKU": msku, "SKU": sku, "原因": "shadow_missing"})
            unit = {}
        else:
            unit = {
                "皮壳成本": _num(s.get("皮壳成本")),
                "绍兴二次加工成本": _num(s.get("绍兴二次加工成本")),
                "二次加工成本": _num(s.get("二次加工成本")),
                "头程运费金额": _num(s.get("头程运费金额")),
            }
            if str(s.get("bridge_status")) != "ok":
                miss.append({"站点": site, "MSKU": msku, "SKU": sku,
                             "原因": f"shadow_{s.get('bridge_status')}"})
        kc = _text((s or {}).get("绍兴成本系数")) or "1"
        k2 = _text((s or {}).get("二次加工成本系数")) or "1"
        ksx = _text((s or {}).get("绍兴二次加工成本系数")) or "1"

        # 产品属性富化：EN 物料组 / BOM / 仓库映射 / 旧 FBA 表兜底
        item = _text((s or {}).get("en_item_code")) or _text((s or {}).get("canonical_sku"))
        if not item and resolver is not None:
            items = resolver.items_for_sku(sku)
            item = items[0] if len(items) == 1 else ""
        group = ""
        if resolver is not None and item:
            group = resolver.item_group_for_item(item) or resolver.item_group_for(item)
        group = group or _text((s or {}).get("品类统一名")) or _text((s or {}).get("品类"))
        bom_rows = bom_index.get(item) or []
        attrs: dict[str, str] = {}
        if len(bom_rows) == 1:
            attrs.update({k: v for k, v in _parse_bom_attrs(bom_rows[0]).items() if v})
        for k, v in _parse_name_attrs(_text(rec.get("产品名称"))).items():
            attrs.setdefault(k, v)
        old2 = (old.get("|".join((site.upper(), normalize_sku(msku), normalize_sku(sku))))
                if old else None)
        master = (attr_master.get(("sku", normalize_sku(sku)))
                  or attr_master.get(("platform", normalize_sku(msku))) or {})
        wsrc = _warehouse_source(
            _text((s or {}).get("发货仓库")) or _text(rec.get("发货仓库")), wh_sources)

        for idx in range(n):
            global_idx = len(rows)
            out = {c: "" for c in FBA95_COLUMNS}
            # GS 业务骨架（逐行重复；销量类首行承载）
            for col in ("图片", "MSKU", "SKU", "产品名称", "站点", "开发人员",
                        "上期销售额", "销售额环比", "销售额占比", "成本", "订单费用",
                        "头程费用", "自定义费用", "利润", "上期利润", "利润环比",
                        "利润占比", "利润率"):
                out[col] = _text(rec.get(col))
            out["订单数量"] = "1"
            out["销量"] = _fmt(qty) if idx == 0 else "0"
            out["上期销量"] = _text(rec.get("上期销量")) if idx == 0 else "0"
            out["销量环比"] = _text(rec.get("销量环比"))
            out["销量占比"] = _text(rec.get("销量占比"))
            out["销售额"] = _fmt(sales) if idx == 0 else "0"
            out["售价*汇率"] = _fmt(sales) if idx == 0 else "0"
            out["发货数量"] = _fmt(qty) if idx == 0 else "0"
            out["订单号"] = _uuid_for(month, site, msku, sku, global_idx)
            out["index_col"] = str(global_idx)

            # 78 列 shadow 属性（逐行重复）
            if s is not None:
                for col in MERGED78_COLUMNS:
                    if col in ("订单号", "平台SKU", "通途SKU", "售价", "汇率",
                               "售价*汇率", "发货数量"):
                        continue
                    if col in FBA95_COLUMNS and col in s:
                        out[col] = _text(s.get(col))
            # 78→95 映射补漏
            out["品类orig"] = _text(rec.get("品类")) or out.get("品类orig")
            out["是否皮壳"] = out.get("是否皮壳") or ""
            out["当月给分公司发货类型"] = ""

            # 产品属性富化：EN 物料组 / BOM / 仓库映射 / 历史兜底
            if group:
                out["品类"] = group
                out["品类统一名"] = group
                out["品类别名"] = group
            for col in ("面料提取", "材料名称", "尺寸", "有无扣", "带*尺寸",
                        "尺寸先大后小", "件套"):
                if attrs.get(col):
                    out[col] = attrs[col]
            if item:
                out["品类尺寸面料编码"] = item
            for col in ("品类编码", "品类尺寸编码", "材料编码", "件套", "美版5尺寸"):
                if not out.get(col):
                    val = _text((old2 or {}).get(col)) or _text(master.get(col))
                    if val:
                        out[col] = val
            for col in ("当月是否新品", "产品发售日期",
                        "平台SKU-渠道账号&实际运营人员", "海外仓成本_USHWC"):
                val = _text((old2 or {}).get(col)) or _text(master.get(col))
                if val:
                    out[col] = val
            if len(bom_rows) == 1:
                out["EN绍兴包装半成品成本"] = _fmt(_num(bom_rows[0].get("cost_sxbzbcp")))
                out["EN绍兴包装成品成本"] = _fmt(_num(bom_rows[0].get("cost_sxbzcp")))
            if wsrc:
                for col in ("对应成本工作簿", "成本来源编码", "发货仓分类",
                            "头程运费来源编码", "二次加工成本来源编码",
                            "发货区域", "发货仓按销售汇总分类"):
                    if _text(wsrc.get(col)):
                        out[col] = _text(wsrc.get(col))
            if not out.get("二次加工成本来源编码") and out.get("发货仓分类") == "FBA":
                out["二次加工成本来源编码"] = "2CJG-SX"

            # 单位成本（逐行重复）
            for col in ("皮壳成本", "绍兴二次加工成本", "二次加工成本", "头程运费金额",
                        "皮壳不含包装成本", "皮壳含包装成本", "海外仓成本"):
                if s is not None and col in s:
                    out[col] = _text(s.get(col))
            out["运费"] = _text((s or {}).get("运费")) or "0"

            q = qty if idx == 0 else 0.0
            sales_for_fill = sales if idx == 0 else 0.0
            if not unit or any(v is None for v in unit.values()):
                cells = _fill_cells(
                    shell=None, shell_in=None, shell_out=None, sx2=None, proc=None, head=None,
                    qty=q, sales=None, freight=None, overseas=None, kc=kc, k2=k2, ksx=ksx,
                    status="blocked", reason="fba_shadow_missing",
                )
            else:
                cells = _fill_cells(
                    shell=unit["皮壳成本"],
                    shell_in=_num(out.get("皮壳含包装成本")) or unit["皮壳成本"],
                    shell_out=_num(out.get("皮壳不含包装成本")) or unit["皮壳成本"],
                    sx2=unit["绍兴二次加工成本"], proc=unit["二次加工成本"],
                    head=unit["头程运费金额"], qty=q, sales=sales_for_fill,
                    freight=_num(out.get("运费")) or 0.0,
                    overseas=_num(out.get("海外仓成本")) or 0.0,
                    kc=kc, k2=k2, ksx=ksx, status="ok",
                )
            out.update(cells)
            rows.append(out)
            if idx == 0:
                fails = _check_cells(cells, q, sales_for_fill)
                if fails:
                    checks.append({"站点": site, "MSKU": msku, "SKU": sku, "fails": fails})
    blocked = sum(1 for r in rows if str(r.get("cost_status")) != "ok")
    stats = {"rows": len(rows), "skus": len(gs), "missing_shadow": len(miss),
             "cost_blocked": blocked}
    return rows, checks, {**stats, "missing": miss}


# ─────────────────────────── merged 78 ───────────────────────────


def _self_to_merged(row: Mapping) -> dict:
    out = {}
    for col in MERGED78_COLUMNS:
        if col in ("运营部当月是否新品", "图片"):
            out[col] = ""
        else:
            out[col] = _text(row.get(col))
    return out


def _fba_to_merged(row: Mapping) -> dict:
    out = {col: "" for col in MERGED78_COLUMNS}
    for col in MERGED78_COLUMNS:
        if col == "平台SKU":
            out[col] = _text(row.get("MSKU"))
        elif col == "通途SKU":
            out[col] = _text(row.get("SKU"))
        elif col in ("售价", "汇率", "运营部当月是否新品"):
            out[col] = ""
        elif col == "售价*汇率":
            out[col] = _text(row.get("售价*汇率")) or _text(row.get("销售额"))
        elif col in row:
            out[col] = _text(row.get(col))
    return out


def _recon_95_78(fba_rows: Sequence[dict], merged_rows: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    metrics = ("发货数量", "售价*汇率", "皮壳成本", "绍兴二次加工成本", "二次加工成本",
               "头程运费金额", "皮壳成本*数量", "绍兴二次加工成本*数量",
               "二次加工成本*数量", "头程运费*数量", "1件产品成本", "产品成本*数量",
               "订单总成本", "订单利润")

    def group(rows: Sequence[dict], site: str, msku: str, sku: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in rows:
            key = "|".join((_text(r.get(site)).upper(), normalize_sku(r.get(msku)),
                            normalize_sku(r.get(sku))))
            acc = out.setdefault(key, {c: 0.0 for c in metrics})
            for c in metrics:
                acc[c] += _num(r.get(c)) or 0.0
        return out

    g95 = group(fba_rows, "站点", "MSKU", "SKU")
    merged_fba = merged_rows[len(merged_rows) - len(fba_rows):] if fba_rows else []
    g78 = group(merged_fba, "渠道账号", "平台SKU", "通途SKU")
    key_rows: list[dict] = []
    for key in sorted(set(g95) | set(g78)):
        a, b = g95.get(key, {}), g78.get(key, {})
        diffs = {c: round((b.get(c, 0.0) or 0.0) - (a.get(c, 0.0) or 0.0), 6) for c in metrics}
        bad = {c: v for c, v in diffs.items() if abs(v) > TOL}
        if bad or key not in g95 or key not in g78:
            key_rows.append({"key": key, "in_95": key in g95, "in_78": key in g78,
                             "diff_cols": len(bad), **{f"diff_{c}": v for c, v in diffs.items()}})
    totals = []
    for c in metrics:
        a = sum(v[c] for v in g95.values())
        b = sum(v[c] for v in g78.values())
        totals.append({"metric": c, "fba95": round(a, 6), "merged78": round(b, 6),
                       "diff": round(b - a, 6)})
    return key_rows, totals


# ─────────────────────────── 对拍 ───────────────────────────


def _sum(df: pd.DataFrame, col: str) -> float:
    if col not in df.columns:
        return 0.0
    return round(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum(), 4)


def _parity(month: str, out: Path, self_rows: list[dict], fba_rows: list[dict],
            merged_rows: list[dict]) -> dict:
    result: dict = {"month": month, "self": {}, "fba": {}, "merged": {}}
    gs_ready = out / "phase36" / month / "gs_ready"

    def _old(name: str) -> Path:
        cand = gs_ready / name
        return cand if cand.exists() else out / name

    new_self = pd.DataFrame(self_rows)
    old_self_p = _old(f"wb_fresh_{month}.csv")
    if old_self_p.exists():
        old = _read_csv(old_self_p)
        metrics = ("发货数量", "售价", "售价(人民币)", "售价*汇率", "运费", "皮壳成本",
                   "绍兴二次加工成本", "二次加工成本", "头程运费金额", "1件产品成本",
                   "产品成本*数量", "订单总成本", "订单利润")
        rows = []
        for c in metrics:
            rows.append({"metric": c, "old": _sum(old, c), "new": _sum(new_self, c),
                         "diff": round(_sum(new_self, c) - _sum(old, c), 4)})
        old_freight = pd.to_numeric(old["运费"], errors="coerce").fillna(0.0)
        new_freight = pd.to_numeric(new_self["运费"], errors="coerce").fillna(0.0)
        result["self"] = {
            "old_path": str(old_self_p),
            "old_rows": len(old), "new_rows": len(new_self),
            "old_keys": len(old.drop_duplicates(["订单号", "通途SKU"])),
            "new_keys": len(new_self.drop_duplicates(["订单号", "通途SKU"])),
            "old_freight_nonzero": int((old_freight > 0).sum()),
            "new_freight_nonzero": int((new_freight > 0).sum()),
            "metrics": rows,
        }
    old_fba_p = _old(f"wb_fba_{month}.csv")
    new_fba = pd.DataFrame(fba_rows)
    if old_fba_p.exists():
        old = _read_csv(old_fba_p)
        metrics = ("销量", "销售额", "发货数量", "皮壳成本", "绍兴二次加工成本",
                   "二次加工成本", "头程运费金额", "产品成本*数量", "订单总成本",
                   "订单利润")
        rows = []
        for c in metrics:
            rows.append({"metric": c, "old": _sum(old, c), "new": _sum(new_fba, c),
                         "diff": round(_sum(new_fba, c) - _sum(old, c), 4)})
        result["fba"] = {"old_path": str(old_fba_p), "old_rows": len(old),
                         "new_rows": len(new_fba),
                         "old_keys": len(old.drop_duplicates(["站点", "MSKU", "SKU"])),
                         "new_keys": len(new_fba.drop_duplicates(["站点", "MSKU", "SKU"])),
                         "metrics": rows}
    old_merged_p = _old(f"merged_{month}.csv")
    new_merged = pd.DataFrame(merged_rows)
    if old_merged_p.exists():
        old = _read_csv(old_merged_p)
        metrics = ("售价*汇率", "发货数量", "皮壳成本", "绍兴二次加工成本", "二次加工成本",
                   "头程运费金额", "产品成本*数量", "订单总成本", "订单利润")
        rows = []
        for c in metrics:
            rows.append({"metric": c, "old": _sum(old, c), "new": _sum(new_merged, c),
                         "diff": round(_sum(new_merged, c) - _sum(old, c), 4)})
        result["merged"] = {"old_path": str(old_merged_p), "old_rows": len(old),
                            "new_rows": len(new_merged),
                            "metrics": rows}
    return result


def _render_parity(parity: Mapping, stats: Mapping) -> str:
    lines = [f"# build-order-tabs 对拍 — {parity.get('month', '')}", "",
             "> 旧表优先取 `out/phase36/<月>/gs_ready/`（= Colab 行结构 + 已写回 GS 的成本），",
             "> 没有时退回 Colab 模板 `wb_fresh_*`。新表 = 本地成熟合并 + 当前 BOM + 真实尾程。",
             "> 行数差异来自旧表的「组件行 + 合并展示行」；金额差异逐项列出。", ""]
    for key, title in (("self", "self 166"), ("fba", "FBA 95"), ("merged", "merged 78")):
        block = parity.get(key) or {}
        if not block:
            continue
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"- 对照文件：`{block.get('old_path')}`")
        lines.append(f"- 行数：旧 {block.get('old_rows')} → 新 {block.get('new_rows')}"
                     + (f"；键数 旧 {block.get('old_keys')} → 新 {block.get('new_keys')}"
                        if "old_keys" in block else ""))
        if "old_freight_nonzero" in block:
            lines.append(f"- 运费非零行：旧 {block['old_freight_nonzero']} → "
                         f"新 {block['new_freight_nonzero']}（旧表生成时尾程尚未补齐会导致这个差异）")
        lines.append("")
        lines.append("| 指标 | 旧 | 新 | 差异 |")
        lines.append("|---|---:|---:|---:|")
        for m in block.get("metrics", []):
            lines.append(f"| {m['metric']} | {m['old']:,.2f} | {m['new']:,.2f} | {m['diff']:+,.2f} |")
        lines.append("")
    lines.append("## self 构建统计")
    lines.append("")
    lines.append(f"- 行数 {stats.get('self', {}).get('rows')}；合并组 "
                 f"{stats.get('self', {}).get('merged_rows')}；成本阻断 "
                 f"{stats.get('self', {}).get('cost_blocked')}")
    for k in ("unmapped_warehouses", "fx_misses"):
        if stats.get("self", {}).get(k):
            lines.append(f"- {k}: {stats['self'][k]}")
    miss = stats.get("self", {}).get("attr_misses") or {}
    if miss:
        lines.append("- 属性缺失（保留空值，待后续补主数据）: "
                     + ", ".join(f"{k} {v}" for k, v in sorted(miss.items())))
    lines.append("")
    lines.append("## FBA 构建统计")
    lines.append("")
    lines.append(f"- 行数 {stats.get('fba', {}).get('rows')}；SKU 组 "
                 f"{stats.get('fba', {}).get('skus')}；shadow 缺失/阻断 "
                 f"{stats.get('fba', {}).get('missing_shadow')}")
    lines.append("")
    return "\n".join(lines)


# ─────────────────────────── 主流程 ───────────────────────────


def _cost_gates(self_stats: Mapping, fba_stats: Mapping) -> list[dict]:
    """成本/缓存门禁：阻断或 shadow 缺失必须让整体失败，不能静默返回成功。"""
    def gate(name: str, ok: bool, detail: str) -> dict:
        return {"name": name, "status": "pass" if ok else "fail", "detail": detail}

    self_blocked = int(self_stats.get("cost_blocked", 0) or 0)
    fba_blocked = int(fba_stats.get("cost_blocked", 0) or 0)
    fba_missing = int(fba_stats.get("missing_shadow", 0) or 0)
    return [
        gate("self 成本阻断=0", self_blocked == 0,
             f"cost_status≠ok {self_blocked} 行"),
        gate("FBA 成本阻断=0", fba_blocked == 0,
             f"cost_status≠ok {fba_blocked} 行；shadow 缺失 {fba_missing} 组"),
        gate("FBA shadow 已校验", fba_missing == 0,
             f"缺失/阻断组 {fba_missing}"),
    ]


def build_order_tabs(
    *,
    month: str,
    root: str | Path = ".",
    out_dir: str | Path | None = None,
    raw_csv: str | Path | None = None,
    ref_map_csv: str | Path | None = None,
    en_items_csv: str | Path | None = None,
    flags_csv: str | Path | None = None,
    branch_map_csv: str | Path | None = None,
    bom_csv: str | Path | None = None,
    wh_map_tsv: str | Path | None = None,
    fx_csv: str | Path | None = None,
    wh_sources_tsv: str | Path | None = None,
    attr_master_tsv: str | Path | None = None,
    old_writeback: str | Path | None = None,
    fba_shadow_csv: str | Path | None = None,
    special_orders_csv: str | Path | None = None,
    require_special_orders: bool = False,
) -> BuildResult:
    root = Path(root)
    out = root / "out"
    out_dir = Path(out_dir or out / "build_tabs" / month)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _pick(explicit, *candidates: Path) -> Path:
        if explicit:
            return Path(explicit)
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]

    raw_path = _pick(
        raw_csv,
        out / "snapshots" / month / f"raw_{month}_filtered.csv",
        out / "snapshots" / month / f"raw_{month}.csv",
        out / f"raw_{month}.csv",
    )
    if not raw_path.exists():
        raise FileNotFoundError(raw_path)

    # 4.1.0.1 特殊订单：默认读 out/special_orders_<月>.csv（fetch_special_orders.py 产出），
    # 命中即从 raw 删除并落盘 filtered 文件；清单缺失时默认告警，--require 则失败。
    special_path = (Path(special_orders_csv) if special_orders_csv
                    else out / f"special_orders_{month}.csv")
    if special_orders_csv and not special_path.exists():
        raise FileNotFoundError(f"指定的特殊订单清单不存在: {special_path}")
    special_stats: dict = {"file": None, "listed": 0, "removed_rows": 0, "removed_orders": 0}
    if special_path.exists():
        ids = load_special_order_ids(special_path)
        raw_all = _read_csv(raw_path)
        filtered, removed_orders, removed_rows = filter_special_orders(raw_all, ids)
        if removed_rows:
            filtered_path = out / "snapshots" / month / f"raw_{month}_filtered.csv"
            filtered_path.parent.mkdir(parents=True, exist_ok=True)
            filtered.to_csv(filtered_path, index=False, encoding="utf-8-sig")
            raw_path = filtered_path
        special_stats = {
            "file": str(special_path), "listed": len(ids),
            "removed_rows": removed_rows, "removed_orders": len(removed_orders),
            "orders": removed_orders,
        }
    elif require_special_orders:
        raise FileNotFoundError(
            f"缺少特殊订单清单 {special_path}；先运行 "
            f"scripts/fetch_special_orders.py --book 通途订单{month}")
    ref_map = _pick(ref_map_csv, out / "item_refcode.csv")
    overrides = root / "config" / "item_alias_overrides.csv"
    if overrides.exists():
        ref_map = _merge_alias_overrides(ref_map, overrides, out_dir)
    en_items = _pick(en_items_csv, out / "en_items_all_089.csv",
                     out / "snapshots" / month / "en_items_all_089.csv")
    flags = _pick(flags_csv, out / "snapshots" / month / "order_flags.csv")
    branch = _pick(branch_map_csv, out / "item_group_branch.tsv")
    bom = _pick(bom_csv, out / "bom_cost_product_with_disabled.csv",
                out / "bom_cost_product_with_kits.csv")
    wh_map = _pick(wh_map_tsv, out / "snapshots" / month / "wh_map.tsv", out / "wh_map.tsv")
    fx_path = _pick(fx_csv, out / f"fx_{month}.csv")
    wh_sources = _pick(wh_sources_tsv, out / "warehouse_cost_sources.tsv")
    attr_master = _pick(attr_master_tsv, out / "product_attributes.tsv")
    old_wb = Path(old_writeback) if old_writeback else out / f"writeback_{month}.csv"

    fx = _load_fx(fx_path)
    sources = _load_wh_sources(wh_sources)
    master = _load_attr_master(attr_master)
    old = _old_index(old_wb if old_wb.exists() else None)
    resolver = EnResolver.from_items_csv(ref_map)
    bom_index = load_bom_cost(bom)

    # ── self ──
    shadow = run_merge_shadow(
        raw_path, ref_map, en_items, flags if flags.exists() else None,
        branch_map_csv=branch if branch.exists() else None,
        bom_method_csv=bom,
        month=month,
    )
    phase2 = compute_phase2(
        shadow, bom, ref_map, wh_map,
        old_wb if old_wb.exists() else None,
        bundle_map_csv=out / "product_bundles.csv" if (out / "product_bundles.csv").exists() else None,
        kit_report_csv=out / "bom_cost_product_with_kits.csv"
        if (out / "bom_cost_product_with_kits.csv").exists() else None,
    )
    raw = _read_csv(raw_path)
    self_rows, self_checks, self_stats = _build_self_rows(
        shadow, phase2, raw, fx, sources, resolver, bom_index, old, master,
    )
    self_df = pd.DataFrame(self_rows, columns=list(SELF166_COLUMNS))
    self_csv = out_dir / f"self_build_{month}.csv"
    self_df.to_csv(self_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame([{
        "订单号": r.get("订单号"), "平台SKU": r.get("平台SKU"),
        "通途SKU": r.get("通途SKU"), "merge_group": r.get("merge_group"),
        "cost_status": r.get("cost_status"), "cost_reason": r.get("cost_reason"),
    } for r in self_rows]).to_csv(out_dir / "self_cost_audit.csv",
                                  index=False, encoding="utf-8-sig")

    # 方法/仓库口径审计：EN 订单行 method vs BOM master method、raw vs EN 仓库
    en_idx: dict[str, dict] = {}
    if en_items.exists():
        for rec in _read_csv(en_items).to_dict("records"):
            oid = _text(rec.get("order_id_code"))
            if oid:
                en_idx.setdefault(oid, {
                    "warehouse": _text(rec.get("warehouse_name")),
                    "method": _text(rec.get("shipping_method")),
                    "item": _text(rec.get("erp_item_code")),
                })
    audit_rows: list[dict] = []
    method_pairs: Counter = Counter()
    wh_diff = 0
    for r in self_rows:
        item = _text(r.get("品类尺寸面料编码"))
        bom_rows = bom_index.get(item) or []
        bom_method = _text(bom_rows[0].get("shipping_method")) if len(bom_rows) == 1 else ""
        oid = _text(r.get("订单号"))
        en = en_idx.get(oid) or en_idx.get(re.sub(r"_\d+$", "", oid)) or {}
        en_method = _text(en.get("method"))
        en_wh = _text(en.get("warehouse"))
        raw_wh = _text(r.get("发货仓库"))
        bad_method = bool(en_method and bom_method and en_method != bom_method)
        bad_wh = bool(en_wh and raw_wh and en_wh != raw_wh)
        if bad_method or bad_wh:
            if bad_method:
                method_pairs[(en_method, bom_method)] += 1
            if bad_wh:
                wh_diff += 1
            audit_rows.append({
                "订单号": oid, "平台SKU": r.get("平台SKU"), "通途SKU": r.get("通途SKU"),
                "raw发货仓库": raw_wh, "EN发货仓库": en_wh,
                "EN_method": en_method, "BOM_method": bom_method,
                "实际计价method": _text(r.get("_method")),
                "item_fg": item, "merge_group": r.get("merge_group"),
                "cost_status": r.get("cost_status"),
                "issue": "|".join(x for x in (
                    "method_diff" if bad_method else "",
                    "wh_diff" if bad_wh else "",
                ) if x),
            })
    pd.DataFrame(audit_rows).to_csv(out_dir / "self_method_warehouse_audit.csv",
                                    index=False, encoding="utf-8-sig")
    self_stats["method_diff_rows"] = sum(
        1 for a in audit_rows if "method_diff" in a["issue"])
    self_stats["bom_override_rows"] = sum(
        1 for a in audit_rows
        if a["EN_method"] == "皮壳" and a["BOM_method"] in ("半成品", "成品")
        and a["实际计价method"] == a["BOM_method"])
    self_stats["warehouse_diff_rows"] = wh_diff
    self_stats["method_pairs"] = {f"{a}->{b}": n for (a, b), n in method_pairs.items()}

    # ── FBA 95 ──
    gs_path = out / f"raw_fba_{month}.csv"
    if not gs_path.exists():
        raise FileNotFoundError(gs_path)
    gs = _read_csv(gs_path)
    bundle_csv = out / "product_bundles.csv"
    kit_csv = out / "bom_cost_product_with_kits.csv"
    shadow_path = Path(fba_shadow_csv) if fba_shadow_csv else (
        out / "fba_shadow" / month / f"fba_shadow_{month}.csv"
    )
    cache_args = dict(
        root=root, bom_csv=bom, ref_map_csv=ref_map,
        bundle_csv=bundle_csv if bundle_csv.exists() else None,
        kit_report_csv=kit_csv if kit_csv.exists() else None,
    )
    ok, reason = validate_fba_cache(shadow_path, month, **cache_args)
    if fba_shadow_csv:
        # 显式指定 shadow：只校验，不擅自重建
        if not ok:
            raise ValueError(
                f"FBA shadow 缓存与当前输入不一致: {shadow_path}（{reason}）；"
                "请先运行 fba-shadow 重新生成"
            )
    elif not ok:
        print(f"FBA shadow 缓存失效（{reason}），按当前 BOM/EN/GS 重建: {shadow_path}")
        build_fba_shadow(
            month=month, root=root, out_dir=shadow_path.parent,
            bom_csv=bom, ref_map_csv=ref_map,
            bundle_csv=cache_args["bundle_csv"], kit_report_csv=cache_args["kit_report_csv"],
        )
        ok, reason = validate_fba_cache(shadow_path, month, **cache_args)
        if not ok:
            raise ValueError(f"FBA shadow 重建后仍无法校验: {shadow_path}（{reason}）")
    fba_shadow_df = _read_csv(shadow_path)
    old_fba_p = out / "phase36" / month / "gs_ready" / f"wb_fba_{month}.csv"
    if not old_fba_p.exists():
        old_fba_p = out / f"wb_fba_{month}.csv"
    fba_rows, fba_checks, fba_stats = _build_fba_rows(
        month, gs, fba_shadow_df,
        resolver=resolver, bom_index=bom_index, wh_sources=sources,
        attr_master=master, old=_old_fba_index(old_fba_p),
    )
    fba_df = pd.DataFrame(fba_rows, columns=list(FBA95_COLUMNS))
    fba_csv = out_dir / f"fba_build_{month}.csv"
    fba_df.to_csv(fba_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame([{
        "订单号": r.get("订单号"), "站点": r.get("站点"), "MSKU": r.get("MSKU"),
        "SKU": r.get("SKU"), "index_col": r.get("index_col"),
        "cost_status": r.get("cost_status"), "cost_reason": r.get("cost_reason"),
    } for r in fba_rows]).to_csv(out_dir / "fba_cost_audit.csv",
                                 index=False, encoding="utf-8-sig")

    # ── merged 78 ──
    merged_rows = [_self_to_merged(r) for r in self_rows]
    merged_rows += [_fba_to_merged(r) for r in fba_rows]
    merged_df = pd.DataFrame(merged_rows, columns=list(MERGED78_COLUMNS))
    merged_csv = out_dir / f"merged_build_{month}.csv"
    merged_df.to_csv(merged_csv, index=False, encoding="utf-8-sig")
    recon_rows, recon_totals = _recon_95_78(fba_rows, merged_rows)
    pd.DataFrame(recon_rows).to_csv(out_dir / "recon_95_78.csv", index=False,
                                    encoding="utf-8-sig")
    pd.DataFrame(recon_totals).to_csv(out_dir / "recon_95_78_totals.csv", index=False,
                                      encoding="utf-8-sig")

    # ── 断言 ──
    assertions: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        assertions.append({"name": name, "status": "pass" if ok else "fail", "detail": detail})

    add("行集合=Phase1 明细", len(self_rows) == len(shadow.detail_rows),
        f"self {len(self_rows)} / Phase1 {len(shadow.detail_rows)}")
    # 销量/运费守恒：新表合计 == 过滤后原始订单合计
    raw_sale = round(pd.to_numeric(raw["售价"], errors="coerce").fillna(0).sum(), 4)
    raw_cny = round(pd.to_numeric(raw["售价(人民币)"], errors="coerce").fillna(0).sum(), 4)
    raw_freight = round(pd.to_numeric(raw["物流商运费"], errors="coerce").fillna(0).sum(), 4)
    add("销售额守恒（售价）", abs(_sum(self_df, "售价") - raw_sale) <= 0.02,
        f"raw {raw_sale:,.2f} → self {_sum(self_df, '售价'):,.2f}")
    add("销售额守恒（售价人民币）", abs(_sum(self_df, "售价(人民币)") - raw_cny) <= 0.02,
        f"raw {raw_cny:,.2f} → self {_sum(self_df, '售价(人民币)'):,.2f}")
    add("尾程运费守恒（物流商运费）", abs(_sum(self_df, "运费") - raw_freight) <= 0.02,
        f"raw {raw_freight:,.2f} → self {_sum(self_df, '运费'):,.2f}")
    add("成本恒等（1件=皮壳+绍兴二次+二次）", not self_checks,
        f"{len(self_rows)} 行；违例 {len(self_checks)}")
    assertions.extend(_cost_gates(self_stats, fba_stats))
    assertions.append({
        "name": "特殊订单清单已应用",
        "status": "pass" if special_stats["file"] else "warn",
        "detail": (f"{special_stats['file']}；删除 {special_stats['removed_rows']} 行 / "
                   f"{special_stats['removed_orders']} 单"
                   if special_stats["file"] else
                   f"未找到 out/special_orders_{month}.csv，按原始 raw 构建"),
    })
    add("FBA 行数=Σ订单数量", len(fba_rows) == int(
        pd.to_numeric(gs["订单数量"], errors="coerce").fillna(0).sum()),
        f"FBA {len(fba_rows)} / Σ订单数量 "
        f"{int(pd.to_numeric(gs['订单数量'], errors='coerce').fillna(0).sum())}")
    add("merged 行数=self+FBA", len(merged_rows) == len(self_rows) + len(fba_rows),
        f"{len(merged_rows)} = {len(self_rows)} + {len(fba_rows)}")
    add("95↔78 总计一致", all(abs(r["diff"]) <= TOL for r in recon_totals),
        f"指标差异 {sum(1 for r in recon_totals if abs(r['diff']) > TOL)} / {len(recon_totals)}")
    add("FBA 成本恒等", not fba_checks, f"违例 {len(fba_checks)}")

    stats = {"self": self_stats, "fba": fba_stats,
             "special_orders": special_stats,
             "inputs": {k: str(v) for k, v in {
                 "raw": raw_path, "ref_map": ref_map, "en_items": en_items,
                 "flags": flags, "branch_map": branch, "bom": bom,
                 "wh_map": wh_map, "fx": fx_path, "wh_sources": wh_sources,
                 "attr_master": attr_master, "old_writeback": old_wb,
                 "fba_gs": gs_path, "fba_shadow": shadow_path,
             }.items()}}
    parity = _parity(month, out, self_rows, fba_rows, merged_rows)

    manifest = {
        "month": month,
        "created_at": datetime.now(TZ_CN).isoformat(),
        "rows": {"self": len(self_rows), "fba": len(fba_rows), "merged": len(merged_rows)},
        "stats": stats,
        "assertions": assertions,
        "parity": parity,
        "recon_95_78_totals": recon_totals,
        "outputs": {"self": str(self_csv), "fba": str(fba_csv), "merged": str(merged_csv)},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2,
                   default=lambda o: o.item() if hasattr(o, "item") else str(o)),
        encoding="utf-8")
    (out_dir / f"parity_{month}.md").write_text(
        _render_parity(parity, stats), encoding="utf-8")

    return BuildResult(
        month=month, self_rows=self_rows, fba_rows=fba_rows, merged_rows=merged_rows,
        assertions=assertions, stats=manifest, parity=parity,
    )
