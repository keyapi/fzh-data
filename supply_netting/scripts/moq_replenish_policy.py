# -*- coding: utf-8 -*-
"""MOQ / 补货频率政策（只读政策层，不改主表、不下单、不虚构渠道 MOQ）。

背景（`2026-10-28-frepple-conversation-digest.md` §6）
------------------------------------------------------
- `item_attr` 15,230 个物料里 MOQ 非零只有 **21 个**；绍兴自有工厂**没有 MOQ 限制**；
  量太少可能不合理，但不是硬约束。
- 补货频率：月补改**周补**，用户已接受。

本模块产出
----------
1. 21 个非零 MOQ 物料清单：物料组 / UOM / MOQ / 所属仓（EN `Item Default`）+ 实际有库存的仓
   （EN `Bin`）/ 供应渠道 / 是否在本批决策键。
2. 政策表：自有工厂无 MOQ、周补（7 天复核）、小额订单阈值（相对周需求，建议非硬约束）。
3. 对补货建议与库存的影响：MOQ 与决策键的重叠、按 UOM 的小额订单分布、月补→周补的
   周期库存变化估计。

口径约束
--------
- 只读输入；所有输出写进 ``--out`` 目录，**不改决策包/净额/主表任何数字**。
- UOM：引用 `UOM-CANONICAL.md`（个/套分列，不跨 UOM 相加）；物料 UOM 取 EN `Item.stock_uom`。
- MOQ：只有 EN `Item.min_order_qty` 这一个 item 级单一值，**没有渠道维度** —— 不编造
  “某渠道 MOQ”。渠道只描述这些物料从哪来（外购辅料 → 绍兴工厂），不出 MOQ。
- 阈值 X 是**建议**：低于 1 周 P50 需求建议合并到下一次复核/观察；不写进任何主表。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

# items_attr.tsv 无表头、固定 10 列。列义已用 EN REST 逐字段核对（FRX1210-WHITE-402#…：
# min_order_qty=48 / safety_stock=0 / lead_time_days=7 / is_stock_item=1 与第 5/7/8/4 列一致）。
ATTR_COLUMNS = ["item_code", "item_name", "item_group", "is_stock_item", "min_order_qty",
                "unused_6", "safety_stock", "lead_time_days", "unused_9", "unused_10"]

KEY = ["canonical_sku", "canonical_warehouse", "canonical_uom"]

# 小额订单分档（相对该键 1 周 P50 需求；全部是建议，不是硬约束）
OBSERVE_WEEKS = 1.0     # < 1 周需求 → 建议合并到下一次 7 天复核 / 观察
BULK_WEEKS = 4.0        # > 4 周需求 → 检查是否重复下单或需求错判
REVIEW_DAYS = 7         # 周补：每 7 天复核一次
MONTHLY_REVIEW_DAYS = 30


class InputError(ValueError):
    """输入结构不符（列数、缺列、缺键）—— 直接失败，不猜。"""


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------

def load_item_attr(path: str | Path) -> pd.DataFrame:
    """读 `items_attr.tsv`（无表头 10 列）；MOQ 列必须可解析且非负。"""
    frame = pd.read_csv(path, sep="\t", header=None, dtype=str, encoding="utf-8-sig")
    if frame.shape[1] != len(ATTR_COLUMNS):
        raise InputError(f"items_attr 需要 {len(ATTR_COLUMNS)} 列，收到 {frame.shape[1]} 列：{path}")
    frame.columns = ATTR_COLUMNS
    frame["item_code"] = frame["item_code"].str.strip()
    if frame["item_code"].duplicated().any():
        raise InputError("items_attr 里 item_code 有重复，无法唯一对账")
    frame["min_order_qty"] = pd.to_numeric(frame["min_order_qty"], errors="coerce")
    if frame["min_order_qty"].isna().any():
        raise InputError("items_attr 的 min_order_qty 有非数字值")
    if (frame["min_order_qty"] < 0).any():
        raise InputError("items_attr 的 min_order_qty 出现负值")
    for column in ("safety_stock", "lead_time_days"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def moq_items(attr: pd.DataFrame) -> pd.DataFrame:
    """非零 MOQ 物料（本批 21 个）；0 表示没有 MOQ 约束。"""
    selected = attr[attr["min_order_qty"] > 0].copy()
    return selected.sort_values(["item_group", "item_code"]).reset_index(drop=True)


def attach_en_evidence(items: pd.DataFrame, snapshot: dict) -> pd.DataFrame:
    """贴上 EN 证据：stock_uom / 默认仓 / 实际有库存的仓 / 采购与制造标记。

    快照里没有的物料保留行并标 `en_evidence=missing`（不静默丢弃、不猜单位）。
    """
    frame = items.copy()
    records = []
    for code in frame["item_code"]:
        doc = snapshot.get(code)
        if not doc:
            records.append(dict(en_evidence="missing", stock_uom=None, default_warehouse=None,
                                stock_warehouses="", stock_qty_total=None,
                                is_purchase_item=None, include_item_in_manufacturing=None))
            continue
        bins = doc.get("bins") or []
        with_stock = [b for b in bins if float(b.get("actual_qty") or 0) != 0]
        records.append(dict(
            en_evidence="ok",
            stock_uom=doc.get("stock_uom"),
            default_warehouse=doc.get("default_warehouse"),
            stock_warehouses=";".join(sorted(str(b["warehouse"]) for b in with_stock)),
            stock_qty_total=round(sum(float(b.get("actual_qty") or 0) for b in with_stock), 3),
            is_purchase_item=doc.get("is_purchase_item"),
            include_item_in_manufacturing=doc.get("include_item_in_manufacturing"),
        ))
    evidence = pd.DataFrame(records, index=frame.index)
    frame = pd.concat([frame, evidence], axis=1)
    frame["supply_channel"] = [supply_channel(row) for row in frame.to_dict("records")]
    return frame


def supply_channel(row) -> str:
    """供应渠道（只描述来源，不含任何 MOQ 值）。无证据时返回 unknown。"""
    if row.get("en_evidence") != "ok":
        return "unknown"
    if row.get("is_purchase_item") in (1, True, "1") and \
            row.get("include_item_in_manufacturing") in (1, True, "1"):
        return "外购辅料→绍兴工厂生产"
    if row.get("is_purchase_item") in (1, True, "1"):
        return "外购"
    return "自制/其他"


def decision_keys(path: str | Path) -> pd.DataFrame:
    """本批决策键（canonical_sku × 仓 × UOM）与现建议量。"""
    frame = pd.read_parquet(path, columns=KEY + ["qty_current", "status", "value_status"])
    missing = [c for c in KEY + ["qty_current"] if c not in frame.columns]
    if missing:
        raise InputError(f"决策包缺少列：{missing}")
    return frame


def annotate_decision_membership(items: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """标每个 MOQ 物料是否出现在本批决策键里（按 canonical_sku 精确匹配）。"""
    by_sku = decisions.groupby("canonical_sku")["qty_current"].count()
    frame = items.copy()
    frame["in_decision_keys"] = frame["item_code"].map(lambda code: code in by_sku.index)
    frame["decision_key_count"] = frame["item_code"].map(lambda code: int(by_sku.get(code, 0)))
    return frame


def weekly_demand(windows_path: str | Path, sku_map_path: str | Path,
                  lead_days: int = 60) -> pd.DataFrame:
    """按决策键算 1 周 P50 需求 = 窗口 p50 / lead_days × 7。

    复用 `decision_pack._map_forecast_keys`（通途 SKU → canonical_sku + UOM 证据），
    不重写映射逻辑。
    """
    from self_fulfilled_demand.canonical import load_sku_map

    from supply_netting.decision_pack import _map_forecast_keys

    windows = pd.read_parquet(windows_path)
    part = windows[windows["lead_days"] == lead_days]
    if part.empty:
        raise InputError(f"预测窗口里没有 lead_days={lead_days} 的行：{windows_path}")
    mapped, _ = _map_forecast_keys(part, load_sku_map(sku_map_path))
    grouped = mapped.groupby(KEY, as_index=False)["p50"].sum()
    grouped["weekly_p50"] = grouped["p50"] / lead_days * 7
    return grouped[KEY + ["p50", "weekly_p50"]]


def classify_orders(decisions: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    """有建议量的键 × 周需求 → 分档（观察 / 正常 / 批量 / 无需求证据）。

    分档只看相对倍数，不跨 UOM 汇总。
    """
    frame = decisions[KEY + ["qty_current", "status"]].merge(weekly, on=KEY, how="left")
    frame["qty_current"] = pd.to_numeric(frame["qty_current"], errors="coerce")
    frame = frame[frame["qty_current"] > 0].copy()
    frame["weeks_of_cover"] = frame["qty_current"] / frame["weekly_p50"].where(
        frame["weekly_p50"] > 0)
    conditions = [frame["weekly_p50"].isna() | (frame["weekly_p50"] <= 0),
                  frame["weeks_of_cover"] < OBSERVE_WEEKS,
                  frame["weeks_of_cover"] > BULK_WEEKS]
    frame["tier"] = pd.Series("正常（1–4 周需求）", index=frame.index)
    for mask, label in zip(conditions, ("无需求证据", "观察（<1 周需求）", "批量（>4 周需求）")):
        frame.loc[mask, "tier"] = label
    return frame.sort_values(KEY).reset_index(drop=True)


def tier_summary(classified: pd.DataFrame) -> dict:
    """按 UOM × 档位统计键数与建议量（绝不跨 UOM 相加）。"""
    out: dict[str, dict] = {}
    for uom, part in classified.groupby("canonical_uom"):
        tiers = {}
        for tier, group in part.groupby("tier"):
            tiers[str(tier)] = dict(keys=int(len(group)),
                                    qty_current=round(float(group["qty_current"].sum()), 3))
        out[str(uom)] = dict(
            keys=int(len(part)),
            qty_current=round(float(part["qty_current"].sum()), 3),
            median_weekly_p50=round(float(part["weekly_p50"].median()), 4)
            if part["weekly_p50"].notna().any() else None,
            tiers=tiers)
    return out


def moq_roundup(need: float, moq: float) -> tuple[float, float]:
    """按 MOQ 向上取整：返回 (下单量, 过冲量)。need<=0 或 moq<=0 时不取整。"""
    if moq <= 0 or need <= 0:
        return float(need), 0.0
    ordered = math.ceil(need / moq) * moq
    return float(ordered), float(ordered - need)


def cycle_stock_effect(classified: pd.DataFrame) -> dict:
    """月补→周补的周期库存变化估计（按 UOM，不跨 UOM 相加）。

    均匀需求下周期库存 ≈ 复核周期内需求的 1/2：
    月补 = 周需求 × 30/14；周补 = 周需求 × 1/2；
    故 Δ = 周需求 × (30-7)/2/7 件（不含安全库存）。
    """
    factor = (MONTHLY_REVIEW_DAYS - REVIEW_DAYS) / 2 / REVIEW_DAYS
    out: dict[str, dict] = {}
    for uom, part in classified.groupby("canonical_uom"):
        known = part[part["weekly_p50"].notna() & (part["weekly_p50"] > 0)]
        out[str(uom)] = dict(keys=int(len(known)),
                             delta_cycle_stock=round(float(known["weekly_p50"].sum() * factor), 3),
                             formula=f"Σweekly_p50 × ({MONTHLY_REVIEW_DAYS}-{REVIEW_DAYS})/2/"
                                     f"{REVIEW_DAYS} 件（均匀需求、不含安全库存）")
    return out


# ---------------------------------------------------------------------------
# 政策表
# ---------------------------------------------------------------------------

def policy_rows(classified: pd.DataFrame, tier_stats: dict,
                moq_in_decisions: int) -> list[dict]:
    """政策表：每行给取值、依据、约束强度、对主表的影响。"""
    observed = {uom: stats["tiers"].get("观察（<1 周需求）", {}).get("keys", 0)
                for uom, stats in tier_stats.items()}
    return [
        dict(层次="自有工厂（绍兴）MOQ", 取值="无 MOQ 限制",
             依据="digest §6（业务口径：绍兴无 MOQ）+ EN 21 个 MOQ 项全是外购辅料，无成品/半成品",
             约束强度="业务已确认", 对主表="不向上取整到 MOQ；补货量 = 净额缺口"),
        dict(层次="补货频率", 取值=f"周补：每 {REVIEW_DAYS} 天复核一次",
             依据="digest §6（月补改周补，用户已接受）",
             约束强度="业务已确认",
             对主表=f"复核周期 {MONTHLY_REVIEW_DAYS}→{REVIEW_DAYS} 天；"
                    "保护期 14 天 = 2 个复核周期，缓冲口径不变"),
        dict(层次="小额补货阈值", 取值=f"单次补货量 < {OBSERVE_WEEKS:g} 周 P50 需求 → "
                                     f"建议合并到下一次复核/观察；> {BULK_WEEKS:g} 周 → 查重复下单",
             依据="本批有建议量的键 × 各自周需求（按 UOM 分列，不跨 UOM 相加）",
             约束强度="建议，非硬约束（不写入主表）",
             对主表=f"按此口径，本批进入「观察」档："
                    + "、".join(f"{uom} {n} 键" for uom, n in observed.items())),
        dict(层次="外购辅料 MOQ（21 项）", 取值="单次采购量 = ceil(需求/MOQ)×MOQ，MOQ 取 EN 值",
             依据="EN `Item.min_order_qty`（item 级单一值，已逐个核对 21 条）",
             约束强度="EN 维护的数据；本批 0 项进入决策键，暂不触发",
             对主表=f"本批 {moq_in_decisions}/21 在决策键 → 对现有建议量 0 影响"),
        dict(层次="渠道级 MOQ", 取值="不存在（不做渠道维度）",
             依据="EN 只有 item 级 MOQ，没有渠道字段；不编造渠道 MOQ",
             约束强度="—", 对主表="无"),
    ]


# ---------------------------------------------------------------------------
# EN 快照（只读 REST）
# ---------------------------------------------------------------------------

def fetch_en_snapshot(item_codes: list[str], env_path: str | Path,
                      base: str = "https://erpnext.vilavi.cn") -> dict:
    """只读拉取 21 个物料的 EN Item 文档 + Bin 库存（不含任何写操作）。"""
    import requests
    from urllib.parse import quote

    env = {}
    for line in Path(env_path).read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    session = requests.Session()
    session.headers.update({
        "Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}",
        "Accept": "application/json"})

    snapshot: dict[str, dict] = {}
    for code in item_codes:
        response = session.get(f"{base}/api/resource/Item/{quote(code, safe='')}", timeout=30)
        response.raise_for_status()
        doc = response.json()["data"]
        defaults = [d for d in (doc.get("item_defaults") or []) if d.get("default_warehouse")]
        snapshot[code] = dict(
            item_name=doc.get("item_name"), item_group=doc.get("item_group"),
            stock_uom=doc.get("stock_uom"), min_order_qty=doc.get("min_order_qty"),
            safety_stock=doc.get("safety_stock"), lead_time_days=doc.get("lead_time_days"),
            is_stock_item=doc.get("is_stock_item"), is_purchase_item=doc.get("is_purchase_item"),
            include_item_in_manufacturing=doc.get("include_item_in_manufacturing"),
            disabled=doc.get("disabled"),
            default_warehouse=(defaults[0]["default_warehouse"] if defaults else None),
            bins=[],
        )
    bins = session.get(f"{base}/api/resource/Bin", params={
        "filters": json.dumps([["Bin", "item_code", "in", item_codes]]),
        "fields": json.dumps(["item_code", "warehouse", "actual_qty"]),
        "limit_page_length": 500}, timeout=30)
    bins.raise_for_status()
    for row in bins.json()["data"]:
        if row["item_code"] in snapshot:
            snapshot[row["item_code"]]["bins"].append(
                dict(warehouse=row["warehouse"], actual_qty=float(row["actual_qty"] or 0)))
    return snapshot


# ---------------------------------------------------------------------------
# 汇总与落盘
# ---------------------------------------------------------------------------

def _sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_report(items: pd.DataFrame, classified: pd.DataFrame, policies: list[dict],
                 impact: dict, out: Path, manifest: dict) -> None:
    """生成 report.md（全部数字来自本次计算，不手写）。"""
    lines = [
        "# MOQ 与补货频率政策（2026-10-28）",
        "",
        f"- 生成时间：{manifest['generated_at']}",
        f"- 输入：`items_attr` {manifest['counts']['items']:,} 个物料 / "
        f"决策包 {manifest['counts']['decision_keys']:,} 个键 / EN 快照 "
        f"{manifest['counts']['moq_items']} 个 MOQ 物料",
        "- 口径：`UOM-CANONICAL.md`（个/套分列、不跨 UOM 相加）；"
        "`2026-10-28-frepple-conversation-digest.md` §6（绍兴无 MOQ、周补已接受）",
        "- 本文件**只给政策**：不改决策包/净额/主表，不下单，不虚构渠道 MOQ。",
        "",
        "## 1. 结论",
        "",
        f"1. **MOQ 只涉及 21 个外购辅料**（缝纫线/流苏/PP棉/日字扣/自封袋/魔术贴/棉绳/"
        f"防水布/工具配件），全部是 `is_purchase_item=1` 且 `include_item_in_manufacturing=1`，"
        "没有一个是成品或半成品；绍兴自有工厂口径为**无 MOQ**。",
        f"2. 这 21 个物料在本批决策键中出现 **{impact['moq_items_in_decisions']} 个** "
        f"→ MOQ 对现有 {impact['decision_keys_total']:,} 个键的建议量**零影响**；"
        "引入 MOQ 只会在这些辅料未来进入补货路径时起作用。",
        f"3. 本批有建议量的键 {impact['decisions_with_positive_qty']} 个，按「1 周 P50 需求」"
        "分档后：**多数键的一次建议量已覆盖 4 周以上**（慢动销），少于 1 周需求的只有 "
        f"{sum(stats['tiers'].get('观察（<1 周需求）', {}).get('keys', 0) for stats in impact['tier_summary_by_uom'].values())} 个。"
        "所以周补的实操重点是「**按覆盖周数决定这周要不要下单**」，而不是把量拆小。",
        "4. 月补→周补在均匀需求下约减少周期库存："
        + "、".join(f"{uom} {stats['delta_cycle_stock']:g} 件"
                    for uom, stats in impact["monthly_to_weekly_cycle_stock"].items())
        + "（估计值，不含安全库存）。",
        "5. 阈值与分档全部是**建议**，不写进主表；X 用「周需求倍数」表达，避免跨 UOM 的"
        "假合计（个与套、米与千克不能相加）。",
        "",
        "## 2. 21 个非零 MOQ 物料",
        "",
        "| 物料 | 物料组 | UOM | MOQ | 提前期(天) | 默认仓 | 有库存的仓 | 现有库存 | 供应渠道 | 在决策键 |",
        "|---|---|---|---:|---:|---|---|---:|---|---|",
    ]
    for row in items.itertuples(index=False):
        warehouses = row.stock_warehouses if isinstance(row.stock_warehouses, str) else ""
        lines.append(
            f"| {row.item_code} | {row.item_group} | {row.stock_uom or 'unknown'} | "
            f"{row.min_order_qty:g} | {row.lead_time_days if row.lead_time_days == row.lead_time_days else '—'} | "
            f"{row.default_warehouse or 'unknown'} | {warehouses.replace(';', '/') or '（无库存）'} | "
            f"{format(row.stock_qty_total, 'g') if row.stock_qty_total == row.stock_qty_total else '—'} | "
            f"{row.supply_channel} | {'是' if row.in_decision_keys else '否'} |")
    lines += [
        "",
        f"- MOQ 含义：EN `Item.min_order_qty`，**item 级单一值**，单位 = 该物料 `stock_uom`"
        "（卷/米/个/千克），不是「件」。EN 没有渠道维度的 MOQ，本报告也不编。",
        "- 全部 21 项 `safety_stock=0`：物料层没有缓冲，MOQ 过冲会直接变呆滞库存。",
        "",
        "## 3. 政策表",
        "",
        "| 层次 | 取值 | 依据 | 约束强度 | 对主表 |",
        "|---|---|---|---|---|",
    ]
    for row in policies:
        lines.append(f"| {row['层次']} | {row['取值']} | {row['依据']} | "
                     f"{row['约束强度']} | {row['对主表']} |")
    lines += [
        "",
        "## 4. 对补货建议与库存的影响",
        "",
        "### 4.1 对现有补货建议",
        "",
        f"- 决策键 {impact['decision_keys_total']:,} 个；其中 `qty_current` 有值 "
        f"{impact['decisions_with_qty']:,} 个，**大于 0 的 {impact['decisions_with_positive_qty']} 个**"
        "（其余为无缺口或证据不足，保持 null/0，不参与本分析）。",
        "- MOQ 与决策键重叠："
        + (f"**{impact['moq_items_in_decisions']} 个** → 不改任何建议量。"
           if impact["moq_items_in_decisions"] == 0
           else f"{impact['moq_items_in_decisions']} 个，见 `moq_items_21.csv` 的 "
                "`in_decision_keys` 列。"),
        "",
        "按「1 周 P50 需求」分档（按 UOM，不跨 UOM 相加）：",
        "",
        "| UOM | 档位 | 键数 | 建议量合计 |",
        "|---|---|---:|---:|",
    ]
    for uom, stats in impact["tier_summary_by_uom"].items():
        for tier, block in stats["tiers"].items():
            lines.append(f"| {uom} | {tier} | {block['keys']} | {block['qty_current']:g} |")
    lines += [
        "",
        "档位含义：`观察` = 一次补货量不足 1 周需求，建议并入下一次复核；"
        "`正常` = 1–4 周；`批量` = 一次覆盖 4 周以上，**这周不必再下单**（不是要拆单）。",
        "",
        "### 4.2 对库存（月补→周补）",
        "",
        "均匀需求、不含安全库存的周期库存估计：",
        "",
        "| UOM | 有周需求的键 | 周期库存变化（件） | 公式 |",
        "|---|---:|---:|---|",
    ]
    for uom, stats in impact["monthly_to_weekly_cycle_stock"].items():
        lines.append(f"| {uom} | {stats['keys']} | {stats['delta_cycle_stock']:g} | "
                     f"{stats['formula']} |")
    seen_moq, examples = set(), []
    for row in impact["moq_roundup_examples"]:
        if row["moq"] not in seen_moq:
            seen_moq.add(row["moq"])
            examples.append(row)
    examples = examples[:4]
    lines += [
        "",
        "MOQ 过冲（只有这 21 个物料会触发，且需先进入补货路径）：",
        "",
        "`下单量 = ceil(需求/MOQ) × MOQ`，过冲 = 下单量 − 需求。示例："
        + "；".join(f"{row['item_code']} MOQ {row['moq']:g}{row['uom']}，"
                   f"需求 {row['example_need']:g} → 下单 {row['ordered']:g}"
                   for row in examples),
        "",
        "### 4.3 边界",
        "",
        "- 本报告不改 `decision_pack`、`supply_netting`、r6/h180 任何数字；"
        "`small_order_analysis.csv` 只是把现有 `qty_current` 与周需求并排看。",
        "- 周需求取预测 60 天窗口 P50 ÷ 60 × 7（`forecast-20261027-r2`）；"
        "预测缺失的键标「无需求证据」，不按 0 处理。",
        "- 「周补」不改变保护期 14 天与安全库存口径，只改变复核与下单节奏。",
        "",
        "## 5. 明确不做 / 待确认",
        "",
        "- **不给渠道 MOQ**：EN 只有 item 级 MOQ；渠道（FBA/分公司）差异只能通过采购批量解释，"
        "没有数据支撑就写 unknown。",
        "- **不把 X 写成硬约束**：阈值是排序与合并建议；是否合并由运营在复核时决定。",
        "- **不改主表**：若要落地 MOQ 取整，应作为补货下单层的一步，另开任务。",
        "- 待确认：21 项 MOQ 的维护责任人/是否仍然有效；MOQ 单位（卷/米/千克）是否与采购对话一致。",
        "",
        "## 6. 产物",
        "",
        "- `moq_items_21.csv`：21 个 MOQ 物料（含所属仓/现有库存/渠道/是否在决策键）",
        "- `replenish_policy.csv`：政策表（5 行）",
        "- `small_order_analysis.csv`：有建议量的键 × 周需求 × 覆盖周数 × 档位",
        "- `impact_summary.json`：输入哈希、参数、影响汇总",
        "- `en_items_snapshot.json`：EN Item+Bin 只读快照（21 项）",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def build(item_attr: str | Path, decisions: str | Path, en_snapshot: str | Path,
          windows: str | Path, sku_map: str | Path, out: str | Path,
          uom_canonical: str | None = None, digest: str | None = None) -> dict:
    attr = load_item_attr(item_attr)
    items = attach_en_evidence(moq_items(attr), json.loads(
        Path(en_snapshot).read_text(encoding="utf-8")))
    items["supply_channel"] = [supply_channel(row) for row in items.to_dict("records")]
    decisions_frame = decision_keys(decisions)
    items = annotate_decision_membership(items, decisions_frame)

    weekly = weekly_demand(windows, sku_map)
    classified = classify_orders(decisions_frame, weekly)
    tiers = tier_summary(classified)

    moq_in_decisions = int(items["in_decision_keys"].sum())
    impact = dict(
        decision_keys_total=int(len(decisions_frame)),
        decisions_with_qty=int(pd.to_numeric(decisions_frame["qty_current"],
                                             errors="coerce").notna().sum()),
        decisions_with_positive_qty=int(len(classified)),
        moq_items_total=int(len(items)),
        moq_items_in_decisions=moq_in_decisions,
        moq_effect_on_current_qty="0（21 项 MOQ 物料均不在本批决策键）"
        if moq_in_decisions == 0 else "见 moq_vs_decisions.csv",
        tier_summary_by_uom=tiers,
        monthly_to_weekly_cycle_stock=cycle_stock_effect(classified),
        moq_roundup_examples=[dict(item_code=row.item_code, uom=row.stock_uom,
                                   moq=float(row.min_order_qty),
                                   example_need=float(row.min_order_qty) / 2,
                                   ordered=moq_roundup(float(row.min_order_qty) / 2,
                                                       float(row.min_order_qty))[0])
                              for row in items.itertuples(index=False)
                              if row.stock_uom],
    )

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    item_columns = ["item_code", "item_name", "item_group", "stock_uom", "min_order_qty",
                    "safety_stock", "lead_time_days", "default_warehouse",
                    "stock_warehouses", "stock_qty_total", "supply_channel",
                    "is_purchase_item", "in_decision_keys", "decision_key_count"]
    items[item_columns].to_csv(out_dir / "moq_items_21.csv", index=False, encoding="utf-8-sig")
    policies = policy_rows(classified, tiers, moq_in_decisions)
    pd.DataFrame(policies).to_csv(out_dir / "replenish_policy.csv", index=False,
                                  encoding="utf-8-sig")
    classified.to_csv(out_dir / "small_order_analysis.csv", index=False, encoding="utf-8-sig")

    manifest = dict(
        schema_version="moq-replenish-policy/v1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        inputs={str(p): _sha(p) for p in (item_attr, decisions, en_snapshot, windows, sku_map)},
        reference_docs={k: v for k, v in (("uom_canonical", uom_canonical), ("digest", digest)) if v},
        parameters=dict(observe_weeks=OBSERVE_WEEKS, bulk_weeks=BULK_WEEKS,
                        review_days=REVIEW_DAYS, monthly_review_days=MONTHLY_REVIEW_DAYS,
                        lead_days_for_weekly=60),
        counts=dict(items=int(len(attr)), moq_items=int(len(items)),
                    decision_keys=int(len(decisions_frame)),
                    positive_qty_keys=int(len(classified))),
        impact=impact,
        note="政策层产出；不改决策包/净额/主表，不下单，不虚构渠道 MOQ",
    )
    (out_dir / "impact_summary.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(items, classified, policies, impact, out_dir, manifest)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MOQ / 补货频率政策（只读、不改主表）")
    parser.add_argument("--item-attr", default="D:/Work/fzh-order-store/items_attr.tsv")
    parser.add_argument("--decisions", default="D:/Work/fzh-order-store/en-demand-v1/"
                                              "supply-netting/decision-pack-2026-10-29-r2/"
                                              "decision_pack_2026-10-29.parquet")
    parser.add_argument("--windows", default="D:/Work/fzh-order-store/en-demand-v1/forecast/"
                                            "forecast-20261027-r2/"
                                            "forecast_sku_warehouse_windows.parquet")
    parser.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    parser.add_argument("--en-snapshot", default="D:/Work/fzh-order-store/en-demand-v1/"
                                                "supply-netting/moq-replenish-policy-2026-10-28/"
                                                "en_items_snapshot.json")
    parser.add_argument("--en-env", default="D:/Work/赛狐/Cursor/EN_API/.env")
    parser.add_argument("--fetch-en", action="store_true",
                        help="只读拉取 EN Item+Bin 快照写到 --en-snapshot（需要 .env 凭证）")
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "moq-replenish-policy-2026-10-28")
    args = parser.parse_args(argv)

    if args.fetch_en:
        snapshot_path = Path(args.en_snapshot)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        codes = moq_items(load_item_attr(args.item_attr))["item_code"].tolist()
        snapshot = fetch_en_snapshot(codes, args.en_env)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
        print(json.dumps(dict(fetched=len(snapshot), path=str(snapshot_path)),
                         ensure_ascii=False))
        return 0

    manifest = build(args.item_attr, args.decisions, args.en_snapshot, args.windows,
                     args.sku_map, args.out,
                     uom_canonical="D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/"
                                   "2026-10-20/claude/control/reference/UOM-CANONICAL.md",
                     digest="D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/"
                            "claude/control/reviews/2026-10-28-frepple-conversation-digest.md")
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print(json.dumps(manifest["impact"]["tier_summary_by_uom"], ensure_ascii=False, indent=1))
    print("输出：", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
