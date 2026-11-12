# -*- coding: utf-8 -*-
"""Phase 4.FBA：FBA 桥接 + 78 列 FBA/合并 shadow（本地，不写 GS/EN）。

- 成本源：EN FBA 明细定位 exact Item；BOM 成品口径出单位成本；GS FBA 销量表做业务骨架；
  通途 FBA 导出做覆盖校验。
- 桥接：月份 + 国家 + 归一化 SKU（customer_code 别名 → Item）只用于别名解析；
  BOM/成本查找一律用 EN 明细的 exact `erp_item_code`（保留大小写，如 `110x81x25`）。
- 四列（成品口径，method=成品；套件用 kit_method 展开）：
  皮壳=cost_fg；绍兴二次=cost_sxbzcp（含半成品包装；不再用 sx_cost_all−cost_fg，避免缺失时负数）；二次加工=FBA valuation=0；
  头程=BOM 对应 FBA freight；1件=皮壳+绍兴二次+二次（恒等断言 + 绍兴二次必须非零）。
- 缺失/歧义 pending，不静默补值；FBA 与自发货同业务键重复即标记。
- 未登记 SKU：按 Colab 产品名称解析（品类/尺寸/面料/有无扣）匹配 EN Item 出候选；
  同款仅差有无扣时按用户口径自动取 KS0001（`auto_pref=superset`），其余交业务确认。
  仅作用于 FBA 白名单/桥接，不改自发货。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .bom_cost import (
    METHOD_FINISHED,
    SHAPE_FINISHED,
    _bundle_audit,
    _bundle_unit_costs,
    _unit_costs,
    load_bom_cost,
    load_bundles,
    load_kit_report,
)
from .split_merge import EnResolver, normalize_sku

MERGED_COLUMNS: tuple[str, ...] = (
    "订单号", "平台SKU", "通途SKU", "品类orig", "品类", "品类统一名", "面料提取", "材料编码",
    "尺寸", "有无扣", "品类编码", "品类尺寸编码", "品类尺寸面料编码", "产品名称", "售价", "汇率",
    "售价*汇率", "发货数量", "是否皮壳", "皮壳含包装成本", "皮壳不含包装成本", "皮壳成本",
    "皮壳成本*数量", "当月给分公司发货类型", "绍兴二次加工成本", "绍兴二次加工成本*数量",
    "二次加工成本", "二次加工成本*数量", "1件产品成本", "产品成本*数量", "头程运费金额",
    "头程运费*数量", "海外仓成本", "海外仓成本*数量", "运费", "订单总成本", "订单利润", "渠道",
    "渠道账号", "发货仓库", "对应成本工作簿", "成本来源编码", "发货仓分类", "头程运费来源编码",
    "二次加工成本来源编码", "发货区域", "发货仓按销售汇总分类", "带*尺寸", "尺寸先大后小", "件套",
    "美版5尺寸", "材料名称", "品类别名", "绍兴成本系数", "皮壳含包装成本*系数",
    "皮壳不含包装成本*系数", "皮壳成本*系数", "皮壳成本*系数*数量", "绍兴二次加工成本系数",
    "绍兴二次加工成本*系数", "绍兴二次加工成本*系数*数量", "二次加工成本系数",
    "二次加工成本*系数", "二次加工成本*系数*数量", "1件产品成本*系数", "产品成本*系数*数量",
    "订单总成本*系数", "订单利润*系数", "当月是否新品", "运营部当月是否新品", "产品发售日期",
    "图片", "自定义费用", "产品名称去除品类", "EN绍兴包装半成品成本", "EN绍兴包装成品成本",
    "海外仓成本_USHWC", "平台SKU-渠道账号&实际运营人员",
)

EXTRA_COLUMNS: tuple[str, ...] = (
    "fulfillment", "source_key", "business_key", "bridge_status", "bridge_reason",
    "canonical_sku", "gs_sku", "gs_msku", "site", "country", "en_rows", "gs_share",
    "duplicate_flag", "product_id", "bundle_item", "bundle_version",
    "en_item_code", "kit_method", "unique_key", "pending_flag", "auto_pref", "en_month",
)

SITE_COUNTRY_RE = re.compile(r"(US|DE|FR|IT|ES|NL|BE|UK|CA|JP)$", re.IGNORECASE)
WHITELIST_COLUMNS: tuple[str, ...] = (
    "month", "site", "country", "msku", "sku", "product_name", "qty",
    "en_rows", "en_qty", "en_item_code", "en_item_status",
    "candidate_count", "candidate_items", "candidate_basis",
    "status", "auto_pref", "approved_item_code", "approved_by", "approved_at", "note",
)
PENDING_COLUMNS: tuple[str, ...] = (
    "month", "site", "msku", "sku", "product_name", "canonical_sku", "qty", "reason",
)
UNMATCHED_EN_COLUMNS: tuple[str, ...] = ("month", "country", "canonical_sku", "en_qty", "en_rows")
CROSS_MONTH_COLUMNS: tuple[str, ...] = (
    "month", "country", "canonical_sku", "site", "msku", "sku", "gs_qty",
    "en_month", "en_rows_used", "en_qty_used", "en_month_total_qty", "qty_diff",
)
WH_COUNTRY = {
    "美国FBA": "US", "德国FBA": "DE", "法国FBA": "FR", "意大利FBA": "IT",
    "西班牙FBA": "ES", "荷兰FBA": "NL", "比利时FBA": "BE", "英国FBA": "UK",
    "加拿大FBA": "CA", "日本FBA": "JP",
}
FBA_LABELS = {
    "US": "9rr7m7g3aj", "CA": "9rr7m7g3aj", "DE": "88hko2ad7l", "FR": "88hko2ad7l",
    "IT": "88hko2ad7l", "ES": "88hko2ad7l", "NL": "88hko2ad7l", "BE": "88hko2ad7l",
    "UK": "0hn57vpr4u", "JP": "3s2n1bnpbj",
}


def _num(v) -> float | None:
    s = str(v).strip() if v is not None else ""
    if s in ("", "nan", "None", "NULL"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _text(v) -> str:
    s = str(v).strip() if v is not None else ""
    return "" if s.upper() in ("NULL", "NAN", "NONE") else s


def site_country(site: str) -> str:
    m = SITE_COUNTRY_RE.search(site or "")
    return m.group(1).upper() if m else ""


def wh_country(warehouse: str) -> str:
    for key, c in WH_COUNTRY.items():
        if key in (warehouse or ""):
            return c
    return ""


def _fba_bucket(country: str) -> str:
    return "USFBA" if country in ("US", "CA") else (
        "UKFBA" if country == "UK" else "JPFBA" if country == "JP" else "DEFBA"
    )


def _cost_codes(country: str) -> tuple[str, str]:
    if country in ("US", "CA"):
        return "COST-USFBA", "HEAD-USFBA"
    if country == "UK":
        return "COST-UKFBA", "HEAD-UKFBA"
    if country == "JP":
        return "COST-JPFBA", "HEAD-JPFBA"
    return "COST-EUFBA", "HEAD-EUFBA"


def _month_of(value: str) -> str:
    s = _text(value)
    return s[:7].replace("-", "") if len(s) >= 7 else ""


# ─────────────── 未登记 SKU：商品名称解析（Colab 思路）+ 候选/自动映射 ───────────────
#
# 参考 docs/reference/cost-engine-spec/14-colab-key-derivation-chain.md 的 4.2/4.7.2：
#   产品名称 → 品类（白名单按长度优先 + 弧形/带圆柱改写）→ 尺寸（去品类/清噪声/首数/多段取大）
#   → 面料（长度优先，海绵排末位）→ 有无扣（有扣|无扣，仅三角品类）。
# 区别：Colab 拼「品类尺寸面料编码」查成本表；这里用来匹配 **EN Item**（item_group + item_fg_name）。

_GROUP_SUFFIXES = ("-拉链款", "-圆柱", "无扣", "有扣", "靠枕", "抱枕", "枕头", "枕", "靠垫", "垫")


def _base_group(group: object) -> str:
    """EN item_group → 品类基名：三角靠枕无扣→三角、平条靠枕→平条、弧形PP棉靠枕→弧形PP棉。"""
    g = str(group or "").strip()
    changed = True
    while changed and g:
        changed = False
        for suf in _GROUP_SUFFIXES:
            if g.endswith(suf) and len(g) > len(suf):
                g = g[: -len(suf)].strip()
                changed = True
                break
    return g


def _extract_size(name: str, category: str = "") -> float | None:
    """Colab 尺寸链：去品类 → 清噪声 → 多段取最大 → 首个数字（排除件套）→ 三角 138→140。"""
    s = str(name or "")
    if category:
        s = s.replace(category, "")
    s = re.sub(r"^\d+\.", "", s)
    s = re.sub(r";\s*\d+\.\b", "", s)
    s = re.sub(r"\d{5,}", "", s)
    m = re.search(r"\d+(?:\.\d+)?(?:\s*[*x×]\s*\d+(?:\.\d+)?)+", s)
    if m:
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(0))]
        size = max(nums) if nums else None
    else:
        m2 = re.search(r"(\d+(?:\.\d+)?)(?!\s*件套)", s)
        size = float(m2.group(1)) if m2 else None
    if size == 138 and category == "三角":  # Colab：三角新面料 138→140
        size = 140
    return size


def _norm_size(value: object) -> float | None:
    """BOM 尺寸段 → 数值（多段取最大，与产品名口径一致）。"""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(value or ""))]
    return max(nums) if nums else None


def _bom_name_index(
    bom_index: Mapping[str, list[dict]],
    group_of: Mapping[str, str] | None = None,
) -> list[tuple[str, str, str, str, str, str, str]]:
    """BOM item_fg_name → (item, 前缀, 面料, 尺寸, 颜色, item_group, 品类基名)。"""
    group_of = group_of or {}
    parsed: list[tuple[str, str, str, str, str, str, str]] = []
    for item, rows in bom_index.items():
        if not rows:
            continue
        name = str(rows[0].get("item_fg_name") or "").strip()
        parts = [p.strip() for p in name.split("-") if p.strip()]
        if len(parts) < 3:
            continue
        prefix, fabric, size = parts[0], parts[1], parts[2]
        color = "-".join(parts[3:]) if len(parts) > 3 else ""
        group = str(group_of.get(item) or "")
        parsed.append((item, prefix, fabric, size, color, group, _base_group(group)))
    return parsed


def _category_vocab(parsed: Sequence[tuple[str, str, str, str, str, str, str]]) -> list[str]:
    """品类基名词表（长度降序，长名优先命中）。"""
    bases = {p[6] for p in parsed if p[6]}
    return sorted(bases, key=len, reverse=True)


def _extract_category(name: str, bases: Sequence[str]) -> str:
    """Colab 品类提取：弧形特例 → 带圆柱 → 长度优先白名单。"""
    s = str(name or "")
    if "弧形" in s:
        if "海绵" in s and "弧形海绵" in bases:
            return "弧形海绵"
        if "弧形PP棉" in bases:
            return "弧形PP棉"
    if "带圆柱" in s:
        for b in bases:
            if "带圆柱" in b:
                return b
    for b in bases:
        if b and b in s:
            return b
    return ""


def _fabric_vocab(parsed: Sequence[tuple[str, str, str, str, str, str, str]]) -> list[str]:
    """面料词表（长度降序；海绵排末位，避免「面料没提取先提海绵」）。"""
    group_words = {p[6] for p in parsed if p[6]} | {p[1] for p in parsed if p[1]}
    vocab = {
        p[2] for p in parsed
        if p[2] and not re.search(r"\d", p[2])
        and not any(p[2] in g or g in p[2] for g in group_words)
    }
    ordered = sorted(vocab, key=len, reverse=True)
    if "海绵" in ordered:
        ordered.remove("海绵")
        ordered.append("海绵")
    return ordered


def _extract_fabric(name: str, vocab: Sequence[str]) -> str:
    for tok in vocab:
        if tok and tok in name:
            return tok
    return ""


def _parse_product_name(name: str, bases: Sequence[str], fabrics: Sequence[str]) -> dict:
    """产品名称 → 品类 / 尺寸 / 面料 / 有无扣（Colab 4.2/4.7.2 口径）。"""
    s = str(name or "")
    category = _extract_category(s, bases)
    size = _extract_size(s, category)
    fabric = _extract_fabric(s, fabrics)
    buttons = "无扣" if "无扣" in s else ("有扣" if "有扣" in s else "")
    if category != "三角":
        buttons = ""  # Colab：有无扣只对三角品类有意义
    return {"category": category, "size": size, "fabric": fabric, "buttons": buttons}


def _match_candidates(
    fields: Mapping,
    name: str,
    parsed: Sequence[tuple[str, str, str, str, str, str, str]],
    limit: int = 5,
) -> tuple[list[tuple[str, str, str, str, str, str, str]], str, int]:
    """按 品类+尺寸+面料 过滤 EN Item，颜色做偏好；逐级放宽。"""
    cat, size, fabric = fields["category"], fields["size"], fields["fabric"]
    buttons = fields["buttons"]
    tiers = [
        (cat, size, fabric, "品类+尺寸+面料"),
        (cat, None, fabric, "尺寸未命中；品类+面料"),
        (cat, size, None, "面料未命中；品类+尺寸"),
        (cat, None, None, "尺寸/面料未命中；仅品类"),
    ]
    for use_cat, use_size, use_fabric, basis in tiers:
        if (use_size and size is None) or (use_fabric and not fabric):
            continue
        cands = []
        for p in parsed:
            item, prefix, f, s, c, group, base = p
            if use_cat and cat and base != cat:
                continue
            if use_size and _norm_size(s) != size:
                continue
            if use_fabric and (not f or (fabric not in f and f not in fabric)):
                continue
            cands.append(p)
        color_hits = [p for p in cands if p[4] and p[4] in name]
        if color_hits:
            cands = color_hits
            basis += "+颜色"
        if not cands:
            continue
        ranked = []
        for p in cands:
            score = 1
            if buttons and (
                (buttons == "无扣" and "无扣" in p[1])
                or (buttons == "有扣" and "有扣" not in p[1])
            ):
                score += 2
            ranked.append((score, p))
        ranked.sort(key=lambda x: (-x[0], x[1][0]))
        basis = f"品类={cat or '?'} 尺寸={size if size is not None else '?'} 面料={fabric or '?'}（{basis}）"
        if buttons:
            basis += f" 扣={buttons}"
        return [p for _, p in ranked[:limit]], basis, len(ranked)
    return [], "", 0


def _auto_pick(
    candidates: Sequence[tuple[str, str, str, str, str, str, str]],
) -> str:
    """同款只差「有无扣」→ 优先 KS0001（更全/superset）；否则空串（交业务确认）。"""
    by_suffix: dict[str, list[tuple]] = defaultdict(list)
    for p in candidates:
        suffix = p[0].split("-", 1)[1] if "-" in p[0] else p[0]
        by_suffix[suffix].append(p)
    picks: set[str] = set()
    for group in by_suffix.values():
        ks1 = [p[0] for p in group if p[0].startswith("KS0001-")]
        wu = [p for p in group if "无扣" in p[1]]
        if ks1 and wu:
            picks.add(ks1[0])
    return picks.pop() if len(picks) == 1 else ""


def _direct_purchase(rows: Sequence[dict]) -> bool:
    """直采成品：cost_fg == sx_cost_all 且 cost_sxbzcp == 0（绍兴无二次加工）。"""
    if not rows:
        return False
    for bom in rows:
        fg = _num(bom.get("cost_fg"))
        sx_all = _num(bom.get("sx_cost_all"))
        sxbzcp = _num(bom.get("cost_sxbzcp"))
        if fg is None or sx_all is None or sxbzcp is None:
            return False
        if abs(fg - sx_all) > 1e-6 or sxbzcp != 0:
            return False
    return True


@dataclass
class FbaShadowResult:
    month: str
    fba_rows: list[dict]
    merged_rows: list[dict]
    bridge_rows: list[dict]
    recon_rows: list[dict]
    pending_rows: list[dict]
    stats: dict


def _en_items_path(month: str, root: Path) -> Path:
    """优先当月 EN 明细快照；老月份回落 08/09 合并导出。"""
    cand = root / "out" / "snapshots" / month / f"en_items_all_{month}.csv"
    return cand if cand.exists() else root / "out" / "en_items_all_089.csv"


def _load_fba_tables(month: str, root: Path):
    gs = pd.read_csv(root / "out" / f"raw_fba_{month}.csv", dtype=str, low_memory=False, keep_default_na=False)
    tt_path = root / "out" / f"fba_export_{month}.csv"
    # 通途 FBA 导出只用于 GS↔TT 对账，不参与成本取数；缺失时按空表处理（recon 标记 tt_missing）
    tt = (pd.read_csv(tt_path, dtype=str, low_memory=False, keep_default_na=False)
          if tt_path.exists() else pd.DataFrame())
    en = pd.read_csv(_en_items_path(month, root), dtype=str, low_memory=False, keep_default_na=False)
    en = en[en["warehouse_name"].str.contains("FBA", case=False, na=False)].copy()
    en["month"] = en["despatch_complete_time"].map(_month_of)
    # 保留全部月份：同月优先，找不到时用 ±1 月窗口跨月桥接
    return gs, tt, en


def _shift_month(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[4:6])
    mon += delta
    while mon < 1:
        mon += 12
        year -= 1
    while mon > 12:
        mon -= 12
        year += 1
    return f"{year:04d}{mon:02d}"


def _canonical(sku: str, resolver: EnResolver, en_keys: set[str]) -> tuple[str, str]:
    key = normalize_sku(sku)
    items = resolver.items_for_sku(sku)
    if len(items) == 1:
        return normalize_sku(items[0]), "item"
    if key in en_keys:
        return key, "en_sku"
    return "", "unresolved"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fba_input_paths(
    month: str,
    root: str | Path,
    *,
    bom_csv: str | Path | None = None,
    ref_map_csv: str | Path | None = None,
    bundle_csv: str | Path | None = None,
    kit_report_csv: str | Path | None = None,
) -> dict[str, Path]:
    """FBA shadow 的输入文件清单（缓存版本校验用）。"""
    root = Path(root)
    out = root / "out"
    return {
        "bom": Path(bom_csv or out / "bom_cost_product_with_kits.csv"),
        "ref_map": Path(ref_map_csv or out / "item_refcode.csv"),
        "bundle": Path(bundle_csv or out / "product_bundles.csv"),
        "kit_report": Path(kit_report_csv or out / "bom_cost_product_with_kits.csv"),
        "raw_fba": out / f"raw_fba_{month}.csv",
        "fba_export": out / f"fba_export_{month}.csv",
        "en_items": _en_items_path(month, root),
    }


def fba_cache_key(month: str, paths: Mapping[str, Path]) -> str:
    """输入版本 key：文件路径 + 内容 sha256；缺失文件的标记。"""
    h = hashlib.sha256()
    h.update(f"fba-shadow-v1|{month}".encode())
    for name in sorted(paths):
        path = Path(paths[name])
        h.update(f"|{name}|{path}".encode())
        if path.exists():
            h.update(b"|" + _sha256_file(path).encode())
        else:
            h.update(b"|missing")
    return h.hexdigest()


def fba_manifest_path(out_dir: str | Path, month: str) -> Path:
    return Path(out_dir) / f"fba_shadow_{month}.manifest.json"


def validate_fba_cache(
    shadow_csv: str | Path,
    month: str,
    *,
    root: str | Path,
    bom_csv: str | Path | None = None,
    ref_map_csv: str | Path | None = None,
    bundle_csv: str | Path | None = None,
    kit_report_csv: str | Path | None = None,
) -> tuple[bool, str]:
    """校验现有 shadow 是否由当前输入生成；返回 (ok, reason)。"""
    shadow_csv = Path(shadow_csv)
    if not shadow_csv.exists():
        return False, "shadow_missing"
    manifest_path = fba_manifest_path(shadow_csv.parent, month)
    if not manifest_path.exists():
        return False, "manifest_missing"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "manifest_unreadable"
    paths = fba_input_paths(
        month, root, bom_csv=bom_csv, ref_map_csv=ref_map_csv,
        bundle_csv=bundle_csv, kit_report_csv=kit_report_csv,
    )
    expected = fba_cache_key(month, paths)
    actual = str(manifest.get("cache_key") or "")
    if actual != expected:
        changed = [
            name for name, path in paths.items()
            if str((manifest.get("inputs") or {}).get(name, {}).get("sha256") or "")
            != (_sha256_file(path) if path.exists() else "")
        ]
        return False, f"cache_key_mismatch changed={changed or 'unknown'}"
    return True, "ok"


def build_fba_shadow(
    *,
    month: str,
    root: str | Path,
    nonfba_csv: str | Path | None = None,
    bom_csv: str | Path | None = None,
    ref_map_csv: str | Path | None = None,
    bundle_csv: str | Path | None = None,
    kit_report_csv: str | Path | None = None,
    out_dir: str | Path | None = None,
) -> FbaShadowResult:
    root = Path(root)
    bom_csv = Path(bom_csv or root / "out" / "bom_cost_product_with_kits.csv")
    ref_map_csv = Path(ref_map_csv or root / "out" / "item_refcode.csv")
    bundle_csv = Path(bundle_csv or root / "out" / "product_bundles.csv")
    kit_report_csv = Path(kit_report_csv or root / "out" / "bom_cost_product_with_kits.csv")
    gs, tt, en = _load_fba_tables(month, root)
    bom_index = load_bom_cost(bom_csv)
    resolver = EnResolver.from_items_csv(ref_map_csv)
    bom_names = _bom_name_index(bom_index, {i: resolver.item_group_for_item(i) for i in bom_index})
    bases = _category_vocab(bom_names)
    fabrics = _fabric_vocab(bom_names)
    bundles = load_bundles(bundle_csv)
    kit_report = load_kit_report(kit_report_csv)

    # EN FBA rows → canonical + country
    en_rows = []
    for rec in en.to_dict("records"):
        country = wh_country(_text(rec.get("warehouse_name")))
        exact = _text(rec.get("erp_item_code"))
        if exact:
            canonical = normalize_sku(exact)
        else:
            items = resolver.items_for_sku(rec.get("tongtool_sku"))
            canonical = normalize_sku(items[0]) if len(items) == 1 else normalize_sku(rec.get("tongtool_sku"))
        en_rows.append({**rec, "country": country, "canonical": canonical, "exact_item": exact})
    en_keys = {r["canonical"] for r in en_rows if r["canonical"]}
    en_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in en_rows:
        en_groups[(r["month"], r["country"], r["canonical"])].append(r)

    # GS rows → canonical/country
    gs_rows = []
    for rec in gs.to_dict("records"):
        country = site_country(_text(rec.get("站点")))
        canonical, how = _canonical(_text(rec.get("SKU")), resolver, en_keys)
        gs_rows.append({**rec, "country": country, "canonical": canonical, "canonical_how": how})
    gs_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in gs_rows:
        gs_groups[(r["country"], r["canonical"])].append(r)

    # 未登记组预解析：Colab 商品名 → 候选 EN Item；同款仅差有无扣 → KS0001 自动映射（superset）
    # 注意：同月无 EN 行的组也要解析（跨月桥接 / BOM 兜底需要产品唯一性）
    auto_prep: dict[str, dict] = {}
    for gkey, grows in gs_groups.items():
        country, canonical = gkey
        if not canonical:
            continue
        egroups = en_groups.get((month, country, canonical), [])
        if any(_text(r.get("exact_item")) for r in egroups):
            continue
        name = _text(grows[0].get("产品名称"))
        gs_sku = _text(grows[0].get("SKU"))
        fields = _parse_product_name(name, bases, fabrics)
        cands, basis, count = _match_candidates(fields, name, bom_names)
        # 已登记别名（归一化：去空格/连字符/下划线 + 大写）直接命中 → 优先于候选推断
        # 不按 BOM 存在性过滤：别名命中但缺 BOM 应报 bom_missing，而不是产品歧义
        alias_items = list(resolver.items_for_sku(gs_sku))
        pick = ""
        auto_pref = ""
        if len(alias_items) == 1:
            pick = alias_items[0]
            auto_pref = "alias"
        else:
            pick = _auto_pick(cands)
            auto_pref = "superset" if pick else ""
            if not pick and count == 1 and "尺寸+面料+颜色" in basis:
                # 强依据（品类+尺寸+面料+颜色 全命中且唯一候选）→ 自动映射
                pick = cands[0][0]
                auto_pref = "single_candidate"
        auto_prep[canonical] = {
            "item": pick,
            "auto_pref": auto_pref,
            "candidates": [p[0] for p in cands],
            "basis": basis,
            "count": count,
            "fields": fields,
        }

    fba_rows: list[dict] = []
    bridge_rows: list[dict] = []
    pending: list[dict] = []
    whitelist_rows: list[dict] = []
    cross_month_recon: list[dict] = []
    used_en: set[int] = set()
    cost_identity_violations = 0
    direct_purchase_zero_rows = 0
    for gkey, grows in sorted(gs_groups.items()):
        country, canonical = gkey
        gqty = sum(_num(r.get("销量")) or 0.0 for r in grows)
        egroups = en_groups.get((month, country, canonical), []) if canonical else []
        en_month_used = month
        bridge_kind = ""
        # 同月无 EN FBA 行 → ±1 月窗口找同产品行（按 GS 数量逐行分配，已用行不重复计）
        if canonical and not egroups:
            for adj in (_shift_month(month, -1), _shift_month(month, 1)):
                cand = [r for r in en_groups.get((adj, country, canonical), [])
                        if id(r) not in used_en]
                if not cand:
                    continue
                picked: list[dict] = []
                acc = 0.0
                for rr in cand:
                    picked.append(rr)
                    acc += _num(rr.get("quantity")) or 0.0
                    if acc >= gqty:
                        break
                egroups = picked
                en_month_used = adj
                bridge_kind = "cross_month_bridge"
                break
            if not egroups:
                bridge_kind = "gs_only_bom_fallback"
                en_month_used = ""
        exact_items = {_text(r.get("exact_item")) for r in egroups if _text(r.get("exact_item"))}
        exact_item = next(iter(exact_items), "")
        if not canonical:
            status, reason = "pending", "gs_sku_unresolved"
        elif len(exact_items) > 1:
            status, reason = "pending", "en_item_ambiguous"
        elif gqty <= 0:
            status, reason = "pending", "gs_qty_zero"
        else:
            status, reason = "ok", bridge_kind
        en_qty = sum(_num(r.get("quantity")) or 0.0 for r in egroups)
        if status == "ok" and en_month_used == month and egroups and en_qty <= 0:
            status, reason = "pending", "en_qty_zero"
        # 成品口径单位成本（BOM exact 查表）
        unit_costs = None
        kit_method = ""
        direct_rows: list[dict] = []
        is_direct = False
        auto_info = auto_prep.get(canonical) if canonical else None
        auto_pref = ""
        if status == "ok":
            bucket = _fba_bucket(country)
            if not exact_item and auto_info and auto_info["item"]:
                exact_item = auto_info["item"]
                auto_pref = auto_info["auto_pref"]
            if not exact_item:
                status, reason = "pending", "en_item_missing"
            elif exact_item in bundles:
                audit = _bundle_audit(bundles[exact_item].components, bom_index, bucket)
                methods = [m for m in audit["methods"] if m]
                if len(methods) != len(audit["methods"]) or not methods:
                    status, reason = "pending", "kit_method_missing"
                elif len(set(methods)) > 1:
                    status, reason = "pending", "kit_method_mixed"
                else:
                    kit_method = methods[0]
                    hcosts, hreason = _bundle_unit_costs(bundles[exact_item].components, bom_index, bucket)
                    if hreason:
                        status, reason = "pending", f"bom_kit:{hreason}"
                    else:
                        unit_costs = hcosts
                        comp_rows = [bom_index.get(c) or [] for c, _ in bundles[exact_item].components]
                        if all(len(x) == 1 for x in comp_rows):
                            direct_rows = [x[0] for x in comp_rows]
            else:
                rows_b = bom_index.get(exact_item) or []
                if len(rows_b) != 1:
                    status, reason = "pending", "bom_missing" if not rows_b else "bom_ambiguous"
                else:
                    costs, creason = _unit_costs(rows_b[0], bucket, METHOD_FINISHED, SHAPE_FINISHED)
                    if creason:
                        status, reason = "pending", f"bom_cost:{creason}"
                    else:
                        unit_costs = costs
                        direct_rows = rows_b
            if status == "ok" and unit_costs is not None and unit_costs["sx"] <= 0:
                # 直采成品（cost_fg == sx_cost_all 且 cost_sxbzcp == 0）允许绍兴二次=0
                if _direct_purchase(direct_rows):
                    is_direct = True
                    if not reason:
                        reason = "direct_purchase_zero"
                else:
                    status, reason = "pending", "sx_zero"
        if status == "ok" and bridge_kind == "cross_month_bridge":
            group_all = en_groups.get((en_month_used, country, canonical), [])
            used_qty = sum(_num(x.get("quantity")) or 0.0 for x in egroups)
            cross_month_recon.append({
                "month": month, "country": country, "canonical_sku": canonical,
                "site": _text(grows[0].get("站点")), "msku": _text(grows[0].get("MSKU")),
                "sku": _text(grows[0].get("SKU")), "gs_qty": round(gqty, 6),
                "en_month": en_month_used, "en_rows_used": len(egroups),
                "en_qty_used": round(used_qty, 6),
                "en_month_total_qty": round(sum(_num(x.get("quantity")) or 0.0 for x in group_all), 6),
                "qty_diff": round(gqty - used_qty, 6),
            })
        product_id = resolver.product_for_item(exact_item or canonical) if canonical else ""
        bundle_item = exact_item if exact_item in bundles else ""
        bundle_version = bundles[bundle_item].version if bundle_item else ""
        gs_share_total = gqty
        for r in grows:
            qty = _num(r.get("销量")) or 0.0
            share = (qty / gs_share_total) if gs_share_total else 0.0
            if status == "ok":
                shell = unit_costs["shell"] * qty
                sx = unit_costs["sx"] * qty
                process = unit_costs["processing"] * qty
                head = unit_costs["freight"] * qty
                one = shell + sx + process
                for rr in egroups:
                    used_en.add(id(rr))
            else:
                shell = process = head = sx = one = None
            if status == "ok":
                cost_code, head_code = _cost_codes(country)
                warehouse = next((_text(x.get("warehouse_name")) for x in egroups if _text(x.get("warehouse_name"))), "")
            else:
                cost_code = head_code = warehouse = ""
            fba = {c: "" for c in (*MERGED_COLUMNS, *EXTRA_COLUMNS)}
            fba.update({
                "订单号": f"FBA|{month}|{_text(r.get('站点'))}|{_text(r.get('MSKU'))}",
                "平台SKU": _text(r.get("MSKU")),
                "通途SKU": _text(r.get("SKU")),
                "品类orig": _text(r.get("品类")),
                "品类": _text(r.get("品类")),
                "品类统一名": _text(r.get("品类")),
                "产品名称": _text(r.get("产品名称")),
                "售价": _num(r.get("销售额")),
                "售价*汇率": _num(r.get("销售额")),
                "发货数量": qty,
                "是否皮壳": "皮壳" if any(_text(x.get("shipping_method")) == "皮壳" for x in egroups) else "否",
                "当月给分公司发货类型": next((_text(x.get("shipping_method")) for x in egroups if _text(x.get("shipping_method"))), ""),
                "发货仓库": warehouse,
                "渠道": "亚马逊",
                "渠道账号": _text(r.get("站点")),
                "成本来源编码": cost_code,
                "发货仓分类": "FBA",
                "头程运费来源编码": head_code,
                "发货区域": country,
                "发货仓按销售汇总分类": "FBA",
                "fulfillment": "FBA",
                "source_key": f"FBA|{month}|{_text(r.get('站点'))}|{_text(r.get('MSKU'))}|{_text(r.get('SKU'))}",
                "business_key": "|".join((month, normalize_sku(r.get("MSKU")), normalize_sku(r.get("SKU")))),
                "bridge_status": status,
                "bridge_reason": reason,
                "canonical_sku": canonical,
                "gs_sku": _text(r.get("SKU")),
                "gs_msku": _text(r.get("MSKU")),
                "site": _text(r.get("站点")),
                "country": country,
                "en_rows": len(egroups),
                "gs_share": round(share, 6),
                "duplicate_flag": False,
                "product_id": product_id,
                "bundle_item": bundle_item,
                "bundle_version": bundle_version,
                "en_item_code": exact_item,
                "kit_method": kit_method,
                "auto_pref": auto_pref,
                "en_month": en_month_used,
            })
            if status == "ok":
                units = qty or 1.0
                unit_shell = round(shell / units, 6)
                unit_sx = round(sx / units, 6)
                unit_process = round(process / units, 6)
                unit_one = round(one / units, 6)
                if abs(unit_shell + unit_sx + unit_process - unit_one) > 1e-6:
                    cost_identity_violations += 1
                    status, reason = "pending", "cost_identity_broken"
                    fba["bridge_status"], fba["bridge_reason"] = status, reason
                else:
                    if is_direct:
                        direct_purchase_zero_rows += 1
                    fba.update({
                        "皮壳成本": unit_shell,
                        "皮壳成本*数量": round(shell, 6),
                        "绍兴二次加工成本": unit_sx,
                        "绍兴二次加工成本*数量": round(sx, 6),
                        "二次加工成本": unit_process,
                        "二次加工成本*数量": round(process, 6),
                        "1件产品成本": unit_one,
                        "产品成本*数量": round(one, 6),
                        "头程运费金额": round(head / units, 6),
                        "头程运费*数量": round(head, 6),
                        "订单总成本": round(shell + sx + process + head, 6),
                        "订单利润": round((_num(r.get("销售额")) or 0.0) - (shell + sx + process + head), 6),
                    })
            fba_rows.append(fba)
            bridge_rows.append({
                "month": month, "country": country, "canonical_sku": canonical,
                "site": _text(r.get("站点")), "msku": _text(r.get("MSKU")),
                "gs_sku": _text(r.get("SKU")), "gs_qty": qty,
                "en_qty": en_qty, "en_rows": len(egroups), "en_month": en_month_used,
                "share": share, "status": status, "reason": reason,
            })
            if status != "ok":
                pending.append({
                    "month": month, "site": _text(r.get("站点")), "msku": _text(r.get("MSKU")),
                    "sku": _text(r.get("SKU")), "product_name": _text(r.get("产品名称")),
                    "canonical_sku": canonical,
                    "qty": qty, "reason": reason,
                })
            if auto_info is not None:
                # 未登记口径的来源行全部进白名单（含已自动映射行，便于审计）
                whitelist_rows.append({
                    "month": month, "site": _text(r.get("站点")), "country": country,
                    "msku": _text(r.get("MSKU")), "sku": _text(r.get("SKU")),
                    "product_name": _text(r.get("产品名称")), "qty": qty,
                    "en_rows": len(egroups), "en_qty": en_qty,
                    "en_item_code": auto_info["item"] or "NULL",
                    "en_item_status": "erp_item_code=NULL" if egroups else "no_en_rows",
                    "auto_pref": auto_info["auto_pref"],
                    "_canonical": canonical,
                })

    # 未登记 SKU 白名单模板：候选供业务确认；superset 已自动映射
    for w in whitelist_rows:
        info = auto_prep.get(w.get("_canonical") or normalize_sku(w["sku"]), {})
        pref = info.get("auto_pref", "")
        if pref == "alias":
            note = "已登记别名（去空格/连字符/下划线后）直接命中；自动映射仅用于 FBA shadow"
        elif pref == "superset":
            note = "同款仅差有无扣，按用户口径取 KS0001（更全）；自动映射仅用于 FBA shadow"
        elif pref == "single_candidate":
            note = "唯一候选且尺寸+面料+颜色全命中（强依据）自动映射；仅用于 FBA shadow"
        else:
            note = "候选仅供参考，未自动映射；业务确认后登记 customer_code"
        w.update({
            "candidate_count": info.get("count", 0),
            "candidate_items": ";".join(info.get("candidates", [])),
            "candidate_basis": info.get("basis", ""),
            "status": (
                "auto_mapped" if info.get("item")
                else "needs_business_confirmation" if info.get("count")
                else "no_candidate"
            ),
            "approved_item_code": info.get("item", ""),
            "approved_by": f"auto:{pref}" if info.get("item") else "",
            "approved_at": "",
            "note": note,
        })

    # EN 未覆盖（仅当月；跨月借用行不计入当月未匹配）
    unmatched_en = []
    for (m, country, canonical), rows in en_groups.items():
        if m != month:
            continue
        if any(id(r) in used_en for r in rows):
            continue
        unmatched_en.append({
            "month": month, "country": country, "canonical_sku": canonical,
            "en_qty": sum(_num(r.get("quantity")) or 0.0 for r in rows),
            "en_rows": len(rows),
        })

    # 三方对账（GS vs TT；EN vs GS）
    tt_norm = []
    for rec in tt.to_dict("records"):
        tt_norm.append({**rec, "key": (_text(rec.get("站点")), normalize_sku(rec.get("MSKU")), normalize_sku(rec.get("SKU")))})
    tt_by_key = {r["key"]: r for r in tt_norm}
    recon = []
    for r in gs_rows:
        key = (_text(r.get("站点")), normalize_sku(r.get("MSKU")), normalize_sku(r.get("SKU")))
        t = tt_by_key.get(key)
        recon.append({
            "month": month, "site": key[0], "msku": key[1], "sku": key[2],
            "gs_qty": _num(r.get("销量")), "tt_qty": _num(t.get("销量")) if t else None,
            "qty_diff": round((_num(r.get("销量")) or 0) - ((_num(t.get("销量")) if t else 0) or 0), 6),
            "gs_sales": _num(r.get("销售额")), "tt_sales": _num(t.get("销售额")) if t else None,
            "gs_cost": _num(r.get("成本")), "tt_cost": _num(t.get("成本")) if t else None,
            "gs_head": _num(r.get("头程费用")), "tt_head": _num(t.get("头程费用")) if t else None,
            "tt_missing": t is None,
        })
    # EN vs GS by country/canonical（当月）
    for (country, canonical), grows in gs_groups.items():
        egroups = en_groups.get((month, country, canonical), [])
        if not egroups:
            continue
        en_qty = sum(_num(x.get("quantity")) or 0.0 for x in egroups)
        gs_qty = sum(_num(x.get("销量")) or 0.0 for x in grows)
        en_cost = sum(_num(x.get("cost_fg")) or 0.0 for x in egroups)
        gs_cost = sum(_num(x.get("成本")) or 0.0 for x in grows)
        recon.append({
            "month": month, "site": f"{country}:{canonical}", "msku": "", "sku": canonical,
            "gs_qty": gs_qty, "tt_qty": en_qty, "qty_diff": round(gs_qty - en_qty, 6),
            "gs_sales": None, "tt_sales": None,
            "gs_cost": gs_cost, "tt_cost": en_cost,
            "gs_head": sum(_num(x.get("头程费用")) or 0.0 for x in grows),
            "tt_head": None, "tt_missing": False,
        })

    # 78 列非 FBA 投影
    merged_rows = []
    if nonfba_csv and Path(nonfba_csv).exists():
        nf = pd.read_csv(nonfba_csv, dtype=str, low_memory=False, keep_default_na=False)
        for rec in nf.to_dict("records"):
            row = {c: _text(rec.get(c)) for c in MERGED_COLUMNS}
            row.update({
                "fulfillment": "SELF", "source_key": f"SELF|{month}|{_text(rec.get('订单号'))}|{_text(rec.get('通途SKU'))}",
                "business_key": "|".join((month, normalize_sku(rec.get("平台SKU_统一") or rec.get("平台SKU")), normalize_sku(rec.get("通途SKU")))),
                "bridge_status": "ok", "bridge_reason": "", "duplicate_flag": False,
                "pending_flag": False,
            })
            merged_rows.append(row)
    merged_rows += fba_rows
    # 行级唯一键：source_key 重复时追加 #n，保证 self+FBA 并表可追溯
    key_seen: Counter = Counter()
    for r in merged_rows:
        base = str(r.get("source_key") or "")
        key_seen[base] += 1
        r["unique_key"] = base if key_seen[base] == 1 else f"{base}#{key_seen[base]}"
        r["pending_flag"] = r.get("bridge_status") != "ok"
    # 重复检测：同 business_key 同时存在 FBA/SELF
    by_key: dict[str, list[dict]] = defaultdict(list)
    for r in merged_rows:
        by_key[r["business_key"]].append(r)
    duplicate_count = 0
    for key, rows in by_key.items():
        kinds = {r["fulfillment"] for r in rows}
        if len(kinds) > 1:
            duplicate_count += len(rows)
            for r in rows:
                r["duplicate_flag"] = True
    unique_keys = {r["unique_key"] for r in merged_rows}
    pending_rows_merged = sum(1 for r in merged_rows if r["pending_flag"])

    priced_qty = sum(float(r.get("发货数量") or 0.0) for r in fba_rows if r["bridge_status"] == "ok")
    gs_qty = sum(_num(r.get("销量")) or 0.0 for r in gs_rows)
    en_qty_all = sum(_num(r.get("quantity")) or 0.0 for r in en_rows if r.get("month") == month)
    tt_qty_all = sum(_num(r.get("销量")) or 0.0 for r in tt_norm)
    pending_reasons = dict(Counter(r["reason"] for r in pending))
    recon_top = sorted(
        recon,
        key=lambda x: -max(abs(x.get("qty_diff") or 0.0), abs((x.get("gs_cost") or 0) - (x.get("tt_cost") or 0))),
    )[:20]
    gs_cost_total = round(sum(_num(r.get("成本")) or 0.0 for r in gs_rows), 6)
    tt_cost_total = round(sum(_num(r.get("成本")) or 0.0 for r in tt_norm), 6)
    gs_head_total = round(sum(_num(r.get("头程费用")) or 0.0 for r in gs_rows), 6)
    tt_head_total = round(sum(_num(r.get("头程费用")) or 0.0 for r in tt_norm), 6)
    stats = {
        "fba_rows": len(fba_rows),
        "fba_priced": sum(1 for r in fba_rows if r["bridge_status"] == "ok"),
        "fba_pending": sum(1 for r in fba_rows if r["bridge_status"] != "ok"),
        "merged_rows": len(merged_rows),
        "duplicate_rows": duplicate_count,
        "unmatched_en": len(unmatched_en),
        "gs_rows": len(gs_rows),
        "gs_qty": round(gs_qty, 6),
        "en_qty": round(en_qty_all, 6),
        "tt_qty": round(tt_qty_all, 6),
        "fba_priced_qty": round(priced_qty, 6),
        "qty_coverage_gs_priced": round(priced_qty / gs_qty, 6) if gs_qty else 0.0,
        "en_qty_coverage_gs": round(gs_qty / en_qty_all, 6) if en_qty_all else 0.0,
        "tt_qty_coverage_gs": round(gs_qty / tt_qty_all, 6) if tt_qty_all else 0.0,
        "pending_reasons": pending_reasons,
        "cross_month_rows": sum(1 for r in fba_rows if r.get("bridge_reason") == "cross_month_bridge"),
        "cross_month_qty": round(sum(
            float(r.get("发货数量") or 0.0) for r in fba_rows
            if r.get("bridge_reason") == "cross_month_bridge"), 6),
        "gs_only_rows": sum(1 for r in fba_rows if r.get("bridge_reason") == "gs_only_bom_fallback"),
        "gs_only_qty": round(sum(
            float(r.get("发货数量") or 0.0) for r in fba_rows
            if r.get("bridge_reason") == "gs_only_bom_fallback"), 6),
        "cost_identity_violations": cost_identity_violations,
        "direct_purchase_zero_rows": direct_purchase_zero_rows,
        "whitelist_rows": len(whitelist_rows),
        "whitelist_skus": len({w["sku"] for w in whitelist_rows}),
        "whitelist_qty": round(sum(float(w["qty"] or 0.0) for w in whitelist_rows), 6),
        "auto_mapped_rows": sum(1 for w in whitelist_rows if w["status"] == "auto_mapped"),
        "auto_mapped_skus": len({w["sku"] for w in whitelist_rows if w["status"] == "auto_mapped"}),
        "auto_superset_skus": len({w["sku"] for w in whitelist_rows if w["auto_pref"] == "superset"}),
        "auto_alias_skus": len({w["sku"] for w in whitelist_rows if w["auto_pref"] == "alias"}),
        "auto_single_candidate_skus": len(
            {w["sku"] for w in whitelist_rows if w["auto_pref"] == "single_candidate"}
        ),
        "whitelist_pending_rows": sum(1 for w in whitelist_rows if w["status"] != "auto_mapped"),
        "whitelist_pending_skus": len({w["sku"] for w in whitelist_rows if w["status"] != "auto_mapped"}),
        "merged_unique_keys": len(unique_keys),
        "merged_unique_key_dupes": len(merged_rows) - len(unique_keys),
        "merged_pending_rows": pending_rows_merged,
        "fba_sx_nonzero_rows": sum(
            1 for r in fba_rows
            if r["bridge_status"] == "ok" and (_num(r.get("绍兴二次加工成本*数量")) or 0.0) > 0
        ),
        "recon_top": recon_top,
        "gs_cost_total": gs_cost_total, "tt_cost_total": tt_cost_total,
        "gs_head_total": gs_head_total, "tt_head_total": tt_head_total,
        "gs_tt_cost_diff": round(gs_cost_total - tt_cost_total, 6),
        "gs_tt_head_diff": round(gs_head_total - tt_head_total, 6),
        "fba_totals": {
            c: round(sum(float(r.get(c) or 0.0) for r in fba_rows if r["bridge_status"] == "ok" and r.get(c) not in ("", None)), 6)
            for c in ("皮壳成本*数量", "头程运费*数量", "二次加工成本*数量", "绍兴二次加工成本*数量")
        },
    }
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(fba_rows).to_csv(out_dir / f"fba_shadow_{month}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(merged_rows).to_csv(out_dir / f"merged_shadow_{month}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(bridge_rows).to_csv(out_dir / f"fba_bridge_{month}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(recon).to_csv(out_dir / f"fba_recon_{month}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(pending, columns=list(PENDING_COLUMNS)).to_csv(
            out_dir / f"fba_pending_{month}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(unmatched_en, columns=list(UNMATCHED_EN_COLUMNS)).to_csv(
            out_dir / f"fba_unmatched_en_{month}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(cross_month_recon, columns=list(CROSS_MONTH_COLUMNS)).to_csv(
            out_dir / f"fba_cross_month_{month}.csv", index=False, encoding="utf-8-sig")
        wl_df = pd.DataFrame(whitelist_rows, columns=list(WHITELIST_COLUMNS))
        wl_df.to_csv(out_dir / f"fba_whitelist_{month}.csv", index=False, encoding="utf-8-sig")
        # 合并模板：按月覆盖，保留其它月份已有登记
        template = out_dir.parent / "fba_whitelist_template.csv"
        if template.exists():
            old = pd.read_csv(template, dtype=str, keep_default_na=False)
            old = old[old["month"] != month]
            template_df = pd.concat([old, wl_df.astype(str)], ignore_index=True)
        else:
            template_df = wl_df.astype(str)
        if list(template_df.columns) == list(WHITELIST_COLUMNS):
            template_df = template_df.sort_values(["month", "sku", "site"], kind="stable")
            template_df.to_csv(template, index=False, encoding="utf-8-sig")
            # SKU 级汇总（业务按 SKU 登记别名；一行一个未登记 SKU）
            summary_df = template_df.copy()
            summary_df["qty_num"] = pd.to_numeric(summary_df["qty"], errors="coerce").fillna(0.0)
            summary_df["en_rows_num"] = pd.to_numeric(summary_df["en_rows"], errors="coerce").fillna(0)
            sku_df = summary_df.groupby(["sku", "product_name"], as_index=False).agg(
                months=("month", lambda s: ",".join(sorted(set(s)))),
                sites=("site", lambda s: ",".join(sorted(set(s)))),
                msku_count=("msku", "nunique"),
                qty=("qty_num", "sum"),
                en_rows=("en_rows_num", "sum"),
                en_item_status=("en_item_status", "first"),
                candidate_count=("candidate_count", "first"),
                candidate_items=("candidate_items", "first"),
                candidate_basis=("candidate_basis", "first"),
                status=("status", "first"),
                auto_pref=("auto_pref", "first"),
                approved_item_code=("approved_item_code", "first"),
                approved_by=("approved_by", "first"),
                approved_at=("approved_at", "first"),
                note=("note", "first"),
            )
            sku_df.to_csv(template.parent / "fba_whitelist_skus.csv", index=False, encoding="utf-8-sig")
        with pd.ExcelWriter(out_dir / f"fba_shadow_{month}.xlsx", engine="openpyxl") as w:
            summary = [{ "指标": k, "值": v} for k, v in stats.items() if k != "fba_totals"]
            summary += [{"指标": f"FBA 四列合计 {k}", "值": v} for k, v in stats["fba_totals"].items()]
            pd.DataFrame(summary).to_excel(w, sheet_name="汇总", index=False)
            pd.DataFrame(fba_rows).to_excel(w, sheet_name="FBA行", index=False)
            pd.DataFrame(merged_rows).to_excel(w, sheet_name="合并行", index=False)
            pd.DataFrame(bridge_rows).to_excel(w, sheet_name="桥接", index=False)
            pd.DataFrame(recon).to_excel(w, sheet_name="三方对账", index=False)
            pd.DataFrame(pending).to_excel(w, sheet_name="待审", index=False)
            pd.DataFrame(unmatched_en).to_excel(w, sheet_name="EN未匹配", index=False)
            pd.DataFrame(cross_month_recon).to_excel(w, sheet_name="跨月桥接", index=False)
            pd.DataFrame(recon_top).to_excel(w, sheet_name="对账Top", index=False)
            wl_df.to_excel(w, sheet_name="未登记SKU", index=False)
        lines = [
            f"# FBA shadow — {month}", "",
            f"- FBA 行: {stats['fba_rows']}；可定价 {stats['fba_priced']}；待审 {stats['fba_pending']}",
            f"- 合并行: {stats['merged_rows']}；唯一键 {stats['merged_unique_keys']}（重复 0）；"
            f"pending 行 {stats['merged_pending_rows']}；业务键重复行 {stats['duplicate_rows']}；EN 未匹配 {stats['unmatched_en']}",
            f"- 数量: GS {stats['gs_qty']:g} / EN {stats['en_qty']:g} / TT {stats['tt_qty']:g}；"
            f"priced 覆盖 GS {stats['qty_coverage_gs_priced']:.2%}；GS/EN {stats['en_qty_coverage_gs']:.2%}；"
            f"GS/TT {stats['tt_qty_coverage_gs']:.2%}",
            f"- 待审原因: {stats['pending_reasons']}",
            f"- 跨月桥接: {stats['cross_month_rows']} 行 / {stats['cross_month_qty']:g} 件；"
            f"BOM 兜底: {stats['gs_only_rows']} 行 / {stats['gs_only_qty']:g} 件",
            f"- 未登记白名单: {stats['whitelist_skus']} SKU / {stats['whitelist_rows']} 行 / {stats['whitelist_qty']:g} 件；"
            f"自动映射 {stats['auto_mapped_skus']} SKU（alias {stats['auto_alias_skus']} + "
            f"superset {stats['auto_superset_skus']} + single {stats['auto_single_candidate_skus']}）；"
            f"仍待确认 {stats['whitelist_pending_skus']} SKU / "
            f"{stats['whitelist_pending_rows']} 行",
            f"- 金额对账: GS 成本 {stats['gs_cost_total']:g} vs TT {stats['tt_cost_total']:g}"
            f"（差 {stats['gs_tt_cost_diff']:g}）；GS 头程 {stats['gs_head_total']:g} vs TT {stats['tt_head_total']:g}"
            f"（差 {stats['gs_tt_head_diff']:g}）",
            f"- 四列合计: {stats['fba_totals']}",
            f"- 成品口径: 绍兴二次非零行 {stats['fba_sx_nonzero_rows']}/{stats['fba_priced']}；"
            f"直采成品绍兴二次=0 行 {stats['direct_purchase_zero_rows']}；"
            f"皮壳+绍兴二次+二次≠1件 违例 {stats['cost_identity_violations']}", "",
        ]
        (out_dir / f"fba_shadow_{month}.md").write_text("\n".join(lines), encoding="utf-8")
        # 缓存版本 manifest：BOM/EN/GS 等输入变化后，build-order-tabs 必须重建
        paths = fba_input_paths(
            month, root, bom_csv=bom_csv, ref_map_csv=ref_map_csv,
            bundle_csv=bundle_csv, kit_report_csv=kit_report_csv,
        )
        manifest = {
            "month": month,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cache_key": fba_cache_key(month, paths),
            "inputs": {
                name: {"path": str(p), "sha256": (_sha256_file(p) if p.exists() else "")}
                for name, p in paths.items()
            },
            "missing_inputs": [name for name, p in paths.items() if not p.exists()],
            "rows": stats.get("fba_rows"),
            "priced": stats.get("fba_priced"),
            "pending": stats.get("fba_pending"),
            "cost_identity_violations": stats.get("cost_identity_violations"),
        }
        fba_manifest_path(out_dir, month).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return FbaShadowResult(month=month, fba_rows=fba_rows, merged_rows=merged_rows,
                           bridge_rows=bridge_rows, recon_rows=recon,
                           pending_rows=pending, stats=stats)
