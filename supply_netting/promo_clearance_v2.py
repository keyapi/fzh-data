# -*- coding: utf-8 -*-
"""PROMO-CLEARANCE v2（按复审 reject 返修）。

v1 被拒的三处，逐条返修：

- **F1**：v1 把「无零库存观测但降价」也并进「回补后降价清库存」，于是 15 个里只有
  10 个真有 `aug_zero>0`，另外 5 个共 66 个原始数量**没有任何零库存观测**。
  v2 把缺断货证据的 5 个降为「其他/需确认」，5 类含义与实现逐条对上；
- **F2**：v1 把「嫌疑」直接写成「排除 2026-09 销量」，又把「有在途」写成
  「销量可进训练」。v2 撤回这两条：**没有任何 SKU 被自动排除**（`auto_exclusion`
  全 False），`clearance_confirmed` 全 False（无促销/清仓业务确认），最高只到
  「低置信线索」，训练处置一律「待核 / 敏感性分支」；
- **F3**：v1 的 312、30.3% 混了未证单位。`PP10LB` 的 `canonical_uom` 是
  `unknown`（`unmapped:PP10LB`，EN Item not found），其余 25 个已证为「个」。
  v2 补 `uom` / `uom_evidence`，**按 UOM 分组统计、未证单位单列、不跨单位合计**。

仍然保留 v1 的三条边界（复审第 3 项通过，不改）：
isPromotion 不可得、不虚构因果、不建促销日历。

数据现状（避免虚构）
- 候选 26 个 SKU 来自 `september_spike_candidates_20261027.csv`；
- 单位证据来自 `demand_line_disposition.parquet`，按 `tongtool_sku` 大写键连接，
  取该键所有行 `canonical_uom` 的唯一值；不唯一或查不到即为 `unknown`；
- `on_order` 只是**输入快照值**：候选/输出都没有该快照的 as_of、逐笔在途或 ETA，
  `on_order=0` 不能升级成「9 月无补货」「以后也不补货」；
- `aug_zero` 只是零库存**观测计数**，不能独立证明连续断货时长。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

PRICE_DOWN = -0.01          # 单价跌幅超过 1% 视为「降价」
PRICE_UP = 0.01
UOM_PROVEN_PIECE = "个"
UOM_UNKNOWN = "unknown"

CATEGORIES = ("断货回补+有在途", "回补后降价线索", "回补未补货", "非价格因素", "其他/需确认")
# v1 的类别名（只用于跨版本对照列 `v1_category`，不参与 v2 判定）
V1_CATEGORIES = ("断货回补+有补货", "回补后降价清库存", "回补未补货", "非价格因素", "其他/需确认")
# v1 类名 → v2 类名 的等价关系（判定没动、只是换了不宣称未证事实的说法）
V1_TO_V2_SAME = {
    "断货回补+有补货": "断货回补+有在途",
    "回补后降价清库存": "回补后降价线索",
    "回补未补货": "回补未补货",
    "非价格因素": "非价格因素",
    "其他/需确认": "其他/需确认",
}
CATEGORY_NOTES = {
    "断货回补+有在途": "8 月有零库存观测、输入快照有在途；在途只是快照事实，"
                     "不等于已排除清仓/促销/恢复供给",
    "回补后降价线索": "有零库存观测 + 降价 + 快照无在途的三字段组合**线索**；"
                    "未证清仓，也未证连续断货",
    "回补未补货": "有零库存观测、快照无在途、未见降价；只说明该快照无在途",
    "非价格因素": "无零库存观测且单价未跌；价格证据缺失，可能是季节/流量/竞品，不归因",
    "其他/需确认": "证据不足（如降价但无零库存观测）或互相矛盾；需人工复核，不硬分类",
}

# 原候选 `cause` → v2 类别，仅用于一致性对照（不是照抄规则）
CAUSE_ALIAS = {
    "断货回补+有补货": "断货回补+有在途",
    "断货回补后降价清库存嫌疑": "回补后降价线索",
    "降价清库存嫌疑": "回补后降价线索",
    "断货回补(未补货)": "回补未补货",
    "非价格因素": "非价格因素",
    "其他/需确认": "其他/需确认",
}

# v2 撤回的 v1 说法（写进 manifest，供复盘对照）
WITHDRAWN = (
    "嫌疑即整月排除 2026-09 销量",
    "有在途即可正常训练",
    "回补后降价清库存（对无零库存观测者）",
    "312 件 / 30.3% 的统一件数占比",
)


def _price_bucket(change: float) -> str:
    if pd.isna(change):
        return "unknown"
    if change <= PRICE_DOWN:
        return "down"
    if change >= PRICE_UP:
        return "up"
    return "flat"


def v1_label(aug_zero, on_order, bucket: str) -> str:
    """复刻 `promo_clearance.classify`（v1）的判定，**只**用于生成 `v1_category` 对照列。

    v1 用 `fillna(0)` 处理缺值，这里照样保留，才能与 v1 产物逐个对得上。
    与 v1 的等价性由 `test_promo_clearance_v2.py` 直接对拍 v1 的 `classify` 锁住。
    """
    stockout = (0 if pd.isna(aug_zero) else aug_zero) > 0
    has_on_order = (0 if pd.isna(on_order) else on_order) > 0
    if stockout and has_on_order:
        return "断货回补+有补货"
    if stockout and bucket == "down" and not has_on_order:
        return "回补后降价清库存"
    if stockout and not has_on_order:
        return "回补未补货"
    if (not stockout) and bucket == "down":
        return "回补后降价清库存"
    if (not stockout) and bucket in ("flat", "up"):
        return "非价格因素"
    return "其他/需确认"


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_uom_map(disposition_path: str | None) -> dict[str, dict]:
    """按 `tongtool_sku` 大写键取唯一 `canonical_uom`；不唯一/查不到即 unknown。"""
    if not disposition_path or not Path(disposition_path).exists():
        return {}
    d = pd.read_parquet(disposition_path)
    key = d["tongtool_sku"].astype(str).str.upper()
    grouped = d.assign(_sku_key=key).groupby("_sku_key")["canonical_uom"]
    out: dict[str, dict] = {}
    for sku, values in grouped:
        known = {str(v) for v in values.dropna()}
        known = {v for v in known if v not in ("", "nan", "None", "<unknown>", "unknown")}
        if len(known) == 1:
            out[sku] = dict(uom=known.pop(), evidence="demand_line_disposition: tongtool_sku 全部行"
                                                   " canonical_uom 唯一")
        elif len(known) > 1:
            out[sku] = dict(uom=UOM_UNKNOWN, evidence=f"unit conflict: {sorted(known)}")
        else:
            out[sku] = dict(uom=UOM_UNKNOWN, evidence="EN Item not found（unmapped），"
                                                     "canonical_uom=<unknown>")
    return out


def classify(frame: pd.DataFrame, uom_map: dict[str, dict] | None = None) -> pd.DataFrame:
    """按「零库存观测 × 快照在途 × 单价变化」给类别；只给线索，不给确认。"""
    uom_map = uom_map or {}
    out = frame.copy()

    aug_zero = pd.to_numeric(out["aug_zero"], errors="coerce")
    on_order = pd.to_numeric(out["on_order"], errors="coerce")
    out["price_chg"] = pd.to_numeric(out["price_chg"], errors="coerce")
    out["price_bucket"] = out["price_chg"].map(_price_bucket)
    # 缺值保持 unknown：**不** fillna(0)——「未知」不等于「无库存 / 无在途」
    out["aug_zero_known"] = aug_zero.notna()
    out["on_order_known"] = on_order.notna()
    out["price_known"] = out["price_bucket"] != "unknown"
    out["zero_stock_observed"] = aug_zero > 0
    out["on_order_snapshot"] = on_order
    out["price_drop"] = out["price_bucket"] == "down"

    uoms, uom_ev, uom_proven = [], [], []
    for sku in out["sku"].astype(str):
        hit = uom_map.get(sku.upper())
        if hit is None:
            uoms.append(UOM_UNKNOWN)
            uom_ev.append("uom source unavailable / SKU not in disposition")
            uom_proven.append(False)
        else:
            uoms.append(hit["uom"])
            uom_ev.append(hit["evidence"])
            uom_proven.append(hit["uom"] != UOM_UNKNOWN)
    out["uom"] = uoms
    out["uom_evidence"] = uom_ev
    out["uom_proven"] = uom_proven

    labels, leads, reasons = [], [], []
    for row in out.itertuples(index=False):
        bucket = row.price_bucket
        missing = [name for name, ok in (
            ("price_chg", row.price_known),
            ("aug_zero", row.aug_zero_known),
            ("on_order", row.on_order_known)) if not ok]
        on_order_txt = "unknown" if pd.isna(row.on_order_snapshot) else f"{row.on_order_snapshot:g}"
        if missing:
            # 输入缺失 → 不猜「无库存 / 无在途」，直接进需确认
            label, lead = "其他/需确认", False
        else:
            stockout = bool(row.zero_stock_observed)
            has_on_order = float(row.on_order_snapshot) > 0
            if stockout and has_on_order:
                label, lead = "断货回补+有在途", False
            elif stockout and bucket == "down":
                label, lead = "回补后降价线索", True
            elif stockout:
                label, lead = "回补未补货", False
            elif bucket == "down":
                # 缺断货证据的降价 → 不再叫清库存，降为需确认
                label, lead = "其他/需确认", False
            elif bucket in ("flat", "up"):
                label, lead = "非价格因素", False
            else:
                label, lead = "其他/需确认", False
        labels.append(label)
        leads.append(lead)
        reasons.append(
            f"aug_zero={getattr(row, 'aug_zero')}, on_order={on_order_txt}, "
            f"price_chg={row.price_chg:+.2%}, ratio={row.ratio:.2f}"
            + (f"; missing={','.join(missing)}" if missing else ""))

    out["category"] = labels
    out["clearance_lead"] = leads
    # 跨版本对照列：v1 实际给的类（那 5 个降级者在 v1 里是「回补后降价清库存」）
    out["v1_category"] = [
        v1_label(a, o, b)
        for a, o, b in zip(out["aug_zero"], out["on_order"], out["price_bucket"])]
    # 只算「真改类」：纯改名的等价关系（有补货→有在途、清库存→线索）不算变
    out["category_changed_from_v1"] = [
        V1_TO_V2_SAME.get(v1_cat, v1_cat) != v2_cat
        for v1_cat, v2_cat in zip(out["v1_category"], out["category"])]
    out["clearance_confirmed"] = False          # 无促销/清仓业务确认，v2 一律 False
    out["evidence_state"] = ["lead" if s else "observed_only" for s in leads]
    out["evidence"] = reasons
    out["category_note"] = [CATEGORY_NOTES[c] for c in labels]
    out["promotion_evidence"] = "unavailable（本机无 isPromotion 字段）"
    # 与候选表原有 cause 的对照（先把原标签归一化到 v2 类别，再比；只作对照，不照抄）
    if "cause" in out.columns:
        out["cause_original"] = out["cause"]
        normalized = out["cause"].map(lambda c: CAUSE_ALIAS.get(str(c), str(c)))
        out["cause_normalized"] = normalized
        out["agree_with_original"] = (normalized == out["category"]).astype(bool)

    # 训练处置：线索只给「待核 / 敏感性分支」，绝不自动删除
    out["also_price_down"] = out["price_drop"] & (out["category"] == "断货回补+有在途")
    out["training_treatment"] = [
        "待核：9 月为敏感性别支输入，不得自动整月排除" if s else "未判定（非线索）"
        for s in leads]
    out["auto_exclusion"] = False
    # 有在途但同时降价者也要人看：在途不能排除清仓/促销，不能据此放行
    out["manual_review_required"] = out["category"].isin(
        ["回补后降价线索", "其他/需确认"]) | out["also_price_down"]
    out["snapshot_caveat"] = ("on_order 仅输入快照值，无 as_of / 逐笔在途 / ETA；"
                              "aug_zero 仅观测计数，不证连续断货")

    month_cols = [c for c in out.columns if str(c).startswith("2026-")]
    out["sept_share_of_year"] = (
        pd.to_numeric(out["2026-09"], errors="coerce")
        / out[month_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1)).round(4)
    return out


def _crosstab(frame: pd.DataFrame) -> dict:
    """v1 类 × v2 类 的件数交叉表，保证跨版本可比（不改任何分类结果）。"""
    out: dict[str, dict[str, int]] = {}
    for v1_cat, v2_cat in zip(frame["v1_category"], frame["category"]):
        out.setdefault(str(v1_cat), {}).setdefault(str(v2_cat), 0)
        out[str(v1_cat)][str(v2_cat)] += 1
    return out


def summarise(frame: pd.DataFrame) -> dict:
    total = len(frame)
    by_cat = frame["category"].value_counts().to_dict()
    leads = frame[frame["clearance_lead"]]

    by_uom: dict[str, dict] = {}
    for uom, group in frame.groupby("uom", sort=False):
        g_leads = group[group["clearance_lead"]]
        g_qty = float(pd.to_numeric(group["2026-09"], errors="coerce").sum())
        lead_qty = float(pd.to_numeric(g_leads["2026-09"], errors="coerce").sum())
        by_uom[str(uom)] = dict(
            candidates=int(len(group)),
            sept_qty=g_qty,
            leads=int(len(g_leads)),
            lead_sept_qty=lead_qty,
            lead_share_within_uom=(round(lead_qty / g_qty * 100, 1) if g_qty else None),
        )

    return dict(
        candidates=int(total),
        by_category={k: int(v) for k, v in by_cat.items()},
        by_category_share={k: round(v / total * 100, 1) for k, v in by_cat.items()},
        by_uom=by_uom,
        no_cross_uom_total=True,
        clearance_leads=int(len(leads)),
        clearance_confirmed=0,
        auto_excluded=0,
        with_on_order=int((frame["on_order_snapshot"] > 0).sum()),
        rows_with_missing_inputs=int((~frame["aug_zero_known"]
                                      | ~frame["on_order_known"]
                                      | ~frame["price_known"]).sum()),
        on_order_also_price_down=int(frame["also_price_down"].sum()),
        manual_review=int(frame["manual_review_required"].sum()),
        promo_evidence="unavailable",
        class_changes_from_v1=int(frame["category_changed_from_v1"].sum()),
        v1_v2_crosstab=_crosstab(frame),
        v1_category_available=True,
        agreement_with_original=(round(float(frame["agree_with_original"].mean() * 100), 1)
                                 if "agree_with_original" in frame.columns else None),
        withdrawn=list(WITHDRAWN),
        note=("清库存全部未确认：本表最高只到低置信线索，不触发任何自动排除；"
              "已确认的清库存销量仍不得当正常需求（既有原则不变）"),
    )


def write_report(path: Path, frame: pd.DataFrame, summary: dict, generated_at: str,
                 sources: dict) -> None:
    uom_rows = summary["by_uom"]
    proven = uom_rows.get(UOM_PROVEN_PIECE)
    unknown = uom_rows.get(UOM_UNKNOWN)

    lines = [
        "# 9 月异常拆分与清库存线索（PROMO-CLEARANCE v2）",
        "",
        f"生成时间：{generated_at}",
        "",
        "> v2 是 v1 被独立复审 reject 后的返修版。**核心变化：撤回「嫌疑即整月排除」"
        "与「有在途即可正常训练」，单位分列，缺断货证据者降级。**",
        "",
        "## 先说边界",
        "",
        "- **isPromotion 不可得**：`gs_orders.parquet` 与 EN 订单 parquet 都没有促销字段，"
        "赛狐订单级 `isPromotion` 是事后标记且本轮未拉取 → 只用「单价变化 + 零库存观测 + 在途快照」，"
        "`promotion_evidence` 26 行全为 unavailable；",
        "- **不虚构因果**：降价后销量上升也可能来自季节、竞品、流量；本表只给证据组合线索；",
        "- **不建促销日历**（EN 下一阶段），本表不改任何预测数字；",
        "- **快照有限**：`on_order` 只是输入快照值（无 as_of / 逐笔在途 / ETA），"
        "`aug_zero` 只是零库存观测计数（不证连续断货）。因此 `on_order=0` 不能读成"
        "「9 月无补货」，`aug_zero>0` 也不能读成「持续断货」；",
        f"- **缺值不猜**：本轮候选 {summary['candidates']} 行三字段齐备（缺失 "
        f"{summary['rows_with_missing_inputs']} 行）；实现**不做 fillna(0)**——"
        "任一字段缺失即落「其他/需确认」，不把「未知」当成「无库存 / 无在途」；"
        "观测时间：候选表只有月度汇总，没有 as_of，逐日价格/可售状态也未提供。",
        "",
        "## 分类结果（26 个候选）",
        "",
        "| 类别 | SKU 数 | 占比 | 含义（与实现一致） |",
        "|---|---:|---:|---|",
    ]
    for cat in CATEGORIES:
        count = summary["by_category"].get(cat, 0)
        share = summary["by_category_share"].get(cat, 0.0)
        lines.append(f"| {cat} | {count} | {share}% | {CATEGORY_NOTES[cat]} |")

    lines += [
        "",
        f"- **低置信线索 {summary['clearance_leads']} 个 SKU**（清库存**未确认**："
        f"`clearance_confirmed=0`）；",
        f"- **自动排除数 = {summary['auto_excluded']}**：本表不给任何 SKU 打硬删除指令，"
        "全部走「待核 / 敏感性别支」；",
        f"- 需人工复核 {summary['manual_review']} 个（线索 + 其他/需确认 + 有在途但同时降价者）；"
        f"输入快照有在途的候选 {summary['with_on_order']} 个，其中 "
        f"{summary['on_order_also_price_down']} 个同时单价下降（在途≠已排除清仓）；",
        f"- 与候选表原有 `cause` 标签的一致性：**{summary.get('agreement_with_original')}%**"
        "（只作对照，不照抄；原表把「回补后降价」与「纯降价」分开记）。",
        "",
        "## 单位（UOM）分列 —— 不跨单位合计",
        "",
        "单位口径依据 `UOM-CANONICAL`：未知单位不合计、不用默认「个」冒充已证。"
        "按 `tongtool_sku` 连接 `demand_line_disposition.parquet` 的 `canonical_uom`：",
        "",
        "| 单位 | 候选 SKU | 候选 9 月数量 | 线索 SKU | 线索 9 月数量 | 线索占本单位 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    uom_label = {UOM_PROVEN_PIECE: "个（已证）", UOM_UNKNOWN: "未证（单列，不进合计）"}
    for uom, row in uom_rows.items():
        share = row["lead_share_within_uom"]
        lines.append(
            f"| {uom_label.get(uom, uom)} | {row['candidates']} | {row['sept_qty']:,.0f} | "
            f"{row['leads']} | {row['lead_sept_qty']:,.0f} | "
            f"{'—' if share is None else f'{share}%'} |")

    if proven and unknown:
        lines += [
            "",
            f"- 已证「个」：候选 {proven['candidates']} 个 / {proven['sept_qty']:,.0f}，"
            f"线索 {proven['leads']} 个 / {proven['lead_sept_qty']:,.0f}，"
            f"**单位内**占比 {proven['lead_share_within_uom']}%；",
            f"- `PP10LB`：`canonical_uom=unknown`（`unmapped:PP10LB`，EN Item not found），"
            f"原始数量 {unknown['sept_qty']:,.0f}，**单列待证，不并入「个」合计**；",
            "- 因此 v2 **不给出 312 「件」或 30.3% 这类跨单位合计**——v1 的该数字含未证单位，已撤回；"
            "需要「个」口径的比例只看上一行。",
        ]

    # 「有在途但同时降价」这一组：由数据算，不写死 SKU 名
    on_order_down = frame[frame["also_price_down"]]
    if len(on_order_down):
        names = "、".join(on_order_down["sku"].astype(str))
        qty = float(pd.to_numeric(on_order_down["2026-09"], errors="coerce").sum())
        on_order_down_line = (
            f"2. **有在途不等于可训练**：`断货回补+有在途` 的 "
            f"{summary['with_on_order']} 个里，{len(on_order_down)} 个同时单价下降"
            f"（{names}，9 月合计 {qty:,.0f}）——在途不能排除清仓/促销/恢复供给；"
            "v2 不再写「销量可进训练」，这些也进人工复核；")
    else:
        on_order_down_line = (
            "2. **有在途不等于可训练**：在途只是快照事实，不能排除清仓/促销/恢复供给；"
            "v2 不再写「销量可进训练」。")

    lines += [
        "",
        "## 与 v1 类别的对照（跨版本可比）",
        "",
        f"输出保留了 `v1_category` 列（v1 实际给的类，复刻 v1 规则生成）与 "
        f"`category_changed_from_v1` 标记，便于逐 SKU 比对历史产物。"
        f"本版改类 **{summary['class_changes_from_v1']} 个**：",
        "",
        "| v1 类别 | v2 类别 | SKU 数 |",
        "|---|---|---:|",
    ]
    for v1_cat, targets in summary["v1_v2_crosstab"].items():
        for v2_cat, count in targets.items():
            if v1_cat == v2_cat:
                mark = "（不变）"
            elif V1_TO_V2_SAME.get(v1_cat, v1_cat) == v2_cat:
                mark = "（仅改名）"
            else:
                mark = "← **改类**"
            lines.append(f"| {v1_cat} | {v2_cat} {mark} | {count} |")

    lines += [
        "",
        "行内 v1/v2 类名不同但标「（仅改名）」的，判定没动：v2 只是把「有补货」改成"
        "「有在途」、「清库存」改成「线索」，不再宣称没证据的事实。",
        "",
        "## 证据等级与训练处置（v2 的核心返修）",
        "",
        "| 层级 | v2 是否到 | 说明 |",
        "|---|---|---|",
        "| 观测 | 是 | `aug_zero`、`price_chg`、`on_order` 三个输入字段值（含快照局限） |",
        f"| 线索 | 是（{summary['clearance_leads']} 个） | 三字段组合可疑，`evidence_state=lead` |",
        "| 确认 | **否** | 无促销/清仓业务确认、无事件起止日、无逐日价格与可售状态 → "
        "`clearance_confirmed` 全 False |",
        "",
        "训练处置规则：",
        "",
        "1. **不自动排除**：`auto_exclusion` 26 行全 False。线索 SKU 只标「待核 / 敏感性别支」"
        "（`training_treatment`），由人确认后再决定是否剔除受影响日期；"
        "**不得为省事把整月销量改成 0**，也不得把补出来的需求当真值；",
        on_order_down_line,
        "3. **既有原则不变**：真的确认了清库存之后，那部分销量仍不得当正常需求——"
        "v2 只是不给「嫌疑」发确认书；",
        "4. **防前视**：若日后改用更晚的快照或事后促销标记来分类，必须按当时的可得信息重跑，"
        "不得把未来信息回填进 9 月的标记里。",
        "",
        "## 与 v1 的差异 / 撤回的结论",
        "",
        "| v1 说法 | v2 处置 |",
        "|---|---|",
        "| 5 个无零库存观测者也算「回补后降价清库存」 | 降为「其他/需确认」（降价异常、"
        "未见零库存观测），进人工复核队列 |",
        "| 线索 SKU「排除 2026-09 销量 / 标删失」 | 撤回；改「待核 / 敏感性别支」，`auto_exclusion=False` |",
        "| 「断货回补+有补货 → 销量可进训练」 | 撤回；有在途只是快照事实，候选仍待核 |",
        "| 312 件、30.3%（跨单位合计） | 撤回；按 UOM 分列，`PP10LB` 未证单位单列 |",
        "",
        "## 逐 SKU 明细（摘要）",
        "",
        "| SKU | 单位 | 8月 | 9月 | 倍数 | 单价变化 | 在途(快照) | 零库存天 | v1 类别 | 类别 | 线索 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in frame.sort_values(["clearance_lead", "category"], ascending=[False, True]) \
            .to_dict("records"):
        mark = "是（待核）" if row["clearance_lead"] else ""
        on_order_txt = ("unknown" if pd.isna(row["on_order_snapshot"])
                        else f"{row['on_order_snapshot']:g}")
        lines.append(
            f"| {row['sku']} | {row['uom']} | {row['2026-08']:g} | {row['2026-09']:g} | "
            f"{row['ratio']:.2f} | {row['price_chg']:+.2%} | {on_order_txt} | "
            f"{row['aug_zero']:g} | {row['v1_category']} | {row['category']} | {mark} |")

    lines += [
        "",
        "## 来源",
        "",
    ]
    for name, info in sources.items():
        lines.append(f"- {name}: `{info['path']}`（sha256 `{info['sha256']}`）")
    path.write_text("\n".join(lines), encoding="utf-8")


def build(candidates: str, out_dir: str, disposition: str | None = None) -> dict:
    raw = pd.read_csv(candidates)
    uom_map = load_uom_map(disposition)
    frame = classify(raw, uom_map)
    summary = summarise(frame)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "promo_clearance_skus.csv", index=False, encoding="utf-8-sig")
    frame[frame["clearance_lead"]].to_csv(
        out / "clearance_leads.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"类别": k, "SKU数": v, "占比%": summary["by_category_share"].get(k, 0)}
                  for k, v in summary["by_category"].items()]).to_csv(
        out / "summary_by_category.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"单位": uom, **row} for uom, row in summary["by_uom"].items()]).to_csv(
        out / "summary_by_uom.csv", index=False, encoding="utf-8-sig")

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    sources = dict(candidates=dict(path=str(candidates), sha256=_sha256(Path(candidates))))
    if disposition and Path(disposition).exists():
        sources["demand_line_disposition"] = dict(
            path=str(disposition), sha256=_sha256(Path(disposition)))

    write_report(out / "report.md", frame, summary, generated_at, sources)
    (out / "summary.json").write_text(json.dumps(
        dict(generated_at=generated_at, **summary), ensure_ascii=False, indent=1),
        encoding="utf-8")

    # 输出身份：逐个文件记 sha256，便于跨版本比对时确认读到的是哪一版
    outputs = {
        name: dict(path=str(out / name), sha256=_sha256(out / name),
                   bytes=(out / name).stat().st_size)
        for name in ("promo_clearance_skus.csv", "clearance_leads.csv",
                     "summary_by_category.csv", "summary_by_uom.csv",
                     "report.md", "summary.json")
    }

    manifest = dict(
        generated_at=generated_at,
        status="pending",
        fixes=dict(
            F1="5 个无零库存观测者降为「其他/需确认」，5 类含义与实现逐条对齐",
            F2="撤回整月排除与「有在途即可正常训练」；auto_exclusion 全 False，"
               "clearance_confirmed 全 False",
            F3="补 uom/uom_evidence，按 UOM 分列、未证单位单列、不跨单位合计",
            F4="保守类名保留，另加 v1_category / category_changed_from_v1 列 + 交叉表，"
               "保证跨版本可比；分类结果不变",
        ),
        category_mapping=dict(
            v1_categories=list(V1_CATEGORIES),
            v2_categories=list(CATEGORIES),
            equivalent=V1_TO_V2_SAME,
            changed_rule="v1「无零库存观测 + 降价」→ v2「其他/需确认」",
            crosstab=summary["v1_v2_crosstab"],
            changed_skus=int(summary["class_changes_from_v1"]),
        ),
        withdrawn=list(WITHDRAWN),
        sources=sources,
        outputs=outputs,
        summary=summary,
    )
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="9 月异常拆分与清库存线索 v2")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--disposition",
                        default="D:/Work/fzh-order-store/en-demand-v1/canonical/"
                                "demand_line_disposition.parquet")
    args = parser.parse_args(argv)

    manifest = build(args.candidates, args.out, args.disposition)
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=1))
    print("输出：", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
