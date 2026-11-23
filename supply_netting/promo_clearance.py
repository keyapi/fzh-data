# -*- coding: utf-8 -*-
"""PROMO-CLEARANCE：把 9 月销量异常拆成可解释的类别，并标出不能混入正常需求的销量。

数据现状（先说清，避免虚构）
- 候选 26 个 SKU 来自 `september_spike_candidates_20261027.csv`，其中已含
  月度销量、`price_prior` / `price_chg`（单价变化）、`available` / `on_order`（库存与在途）、
  `aug_zero`（8 月零库存天数）、`cover`、`in_rule` 与一版 `cause`。
- **`isPromotion` 在本机数据里不可得**：`gs_orders.parquet`、EN 订单 parquet 都没有该字段，
  赛狐订单级 `isPromotion` 是事后标记且本轮没有拉取。因此本表**不使用 isPromotion**，
  只用「单价变化 + 断货证据 + 在途」做规则判定，并显式标 `promotion_evidence=unavailable`。
- 这是**证据组合下的分类/嫌疑**，不是因果结论：降价后销量上升也可能来自季节、竞品、流量。
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
CATEGORIES = ("断货回补+有补货", "回补后降价清库存", "回补未补货", "非价格因素", "其他/需确认")
CATEGORY_NOTES = {
    "断货回补+有补货": "8 月有零库存、9 月回补且有在途 → 正常补货节奏，销量可进训练",
    "回补后降价清库存": "有断货证据 + 降价 + 无在途 → **清库存嫌疑**，9 月销量不得当正常需求",
    "回补未补货": "有断货证据、无在途、未见降价 → 回补但没补货，销量需观察",
    "非价格因素": "无断货证据且单价基本没动 → 非价格因素（季节/流量/竞品等），不归因",
    "其他/需确认": "证据不足或互相矛盾 → 需人工确认，不硬分类",
}


def _price_bucket(change: float) -> str:
    if pd.isna(change):
        return "unknown"
    if change <= PRICE_DOWN:
        return "down"
    if change >= PRICE_UP:
        return "up"
    return "flat"


def classify(frame: pd.DataFrame) -> pd.DataFrame:
    """按「断货证据 × 在途 × 单价变化」给类别；与候选表原有 cause 只做对照、不照抄。"""
    out = frame.copy()
    out["stockout"] = pd.to_numeric(out["aug_zero"], errors="coerce").fillna(0) > 0
    out["on_order"] = pd.to_numeric(out["on_order"], errors="coerce").fillna(0)
    out["price_bucket"] = out["price_chg"].map(_price_bucket)

    labels, clearance, reasons = [], [], []
    for row in out.itertuples(index=False):
        stockout = bool(getattr(row, "stockout"))
        has_on_order = float(getattr(row, "on_order")) > 0
        bucket = getattr(row, "price_bucket")
        if stockout and has_on_order:
            label, suspect = "断货回补+有补货", False
        elif stockout and bucket == "down" and not has_on_order:
            label, suspect = "回补后降价清库存", True
        elif stockout and not has_on_order:
            label, suspect = "回补未补货", False
        elif (not stockout) and bucket == "down":
            label, suspect = "回补后降价清库存", True
        elif (not stockout) and bucket in ("flat", "up"):
            label, suspect = "非价格因素", False
        else:
            label, suspect = "其他/需确认", False
        labels.append(label)
        clearance.append(suspect)
        reasons.append(
            f"aug_zero={getattr(row, 'aug_zero')}, on_order={getattr(row, 'on_order'):g}, "
            f"price_chg={getattr(row, 'price_chg'):+.2%}, ratio={getattr(row, 'ratio'):.2f}"
        )

    out["category"] = labels
    out["clearance_suspect"] = clearance
    out["evidence"] = reasons
    out["category_note"] = [CATEGORY_NOTES[c] for c in labels]
    out["promotion_evidence"] = "unavailable（本机无 isPromotion 字段）"
    if "cause" in out.columns:
        out["cause_original"] = out["cause"]
        out["agree_with_original"] = [
            bool(a == b or (a == "回补后降价清库存"
                            and str(b) in ("断货回补后降价清库存嫌疑", "降价清库存嫌疑")))
            for a, b in zip(out["category"], out["cause"])]
    out["demand_exclusion"] = [
        "排除 2026-09 销量（清库存嫌疑，不得当正常需求）" if s else ""
        for s in clearance
    ]
    out["sept_share_of_year"] = (
        pd.to_numeric(out["2026-09"], errors="coerce")
        / out[[c for c in out.columns if str(c).startswith("2026-")]].apply(
            pd.to_numeric, errors="coerce").sum(axis=1)).round(4)
    return out


def summarise(frame: pd.DataFrame) -> dict:
    total = len(frame)
    by_cat = frame["category"].value_counts().to_dict()
    clearance = frame[frame["clearance_suspect"]]
    return dict(
        candidates=int(total),
        by_category={k: int(v) for k, v in by_cat.items()},
        by_category_share={k: round(v / total * 100, 1) for k, v in by_cat.items()},
        clearance_skus=int(len(clearance)),
        clearance_sept_qty=float(pd.to_numeric(clearance["2026-09"], errors="coerce").sum()),
        all_sept_qty=float(pd.to_numeric(frame["2026-09"], errors="coerce").sum()),
        clearance_sept_share=round(
            float(pd.to_numeric(clearance["2026-09"], errors="coerce").sum()
                  / pd.to_numeric(frame["2026-09"], errors="coerce").sum() * 100), 1),
        with_on_order=int((frame["on_order"] > 0).sum()),
        promo_evidence="unavailable",
        agreement_with_original=(round(float(frame["agree_with_original"].mean() * 100), 1)
                                 if "agree_with_original" in frame.columns else None),
        note="分类是证据组合下的嫌疑，不是因果结论；清库存销量不得混入正常需求",
    )


def write_report(path: Path, frame: pd.DataFrame, summary: dict, generated_at: str,
                 sources: dict) -> None:
    lines = [
        "# 9 月异常拆分与清库存标记（PROMO-CLEARANCE）",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 先说边界",
        "",
        "- **isPromotion 不可得**：`gs_orders.parquet` 与 EN 订单 parquet 都没有促销字段，"
        "赛狐订单级 `isPromotion` 是事后标记且本轮未拉取 → 分类只用「单价变化 + 断货证据 + 在途」；",
        "- **不虚构因果**：这是证据组合下的分类/嫌疑，降价后销量上升也可能来自季节、竞品、流量；",
        "- **不建促销日历**（EN 下一阶段），本表不改任何预测数字，只给「是否可进训练」的标记。",
        "",
        "## 分类结果（26 个候选）",
        "",
        "| 类别 | SKU 数 | 占比 | 含义 |",
        "|---|---:|---:|---|",
    ]
    for cat in CATEGORIES:
        count = summary["by_category"].get(cat, 0)
        share = summary["by_category_share"].get(cat, 0.0)
        lines.append(f"| {cat} | {count} | {share}% | {CATEGORY_NOTES[cat]} |")
    lines += [
        "",
        f"- **清库存嫌疑 {summary['clearance_skus']} 个 SKU**，9 月销量 "
        f"{summary['clearance_sept_qty']:,.0f} 件，占 26 个候选 9 月销量的 "
        f"{summary['clearance_sept_share']}%；",
        f"- 有在途的候选 {summary['with_on_order']} 个（回补有货可跟）；",
        f"- 与候选表原有 `cause` 标签的一致性：**{summary.get('agreement_with_original')}%**"
        "（原表把「回补后降价」与「纯降价」分开记，本表统一并入「回补后降价清库存」）；",
        "",
        "## 与原标签的差异",
        "",
        f"本表规则与候选表原有 `cause` 的一致性 **{summary.get('agreement_with_original')}%**，差异都来自"
        "「用同一套证据重新判定」，不是凭空改：",
        "",
        "- 原「断货回补后降价清库存嫌疑」+「降价清库存嫌疑」→ 本表统一并入「回补后降价清库存」；",
        "- 原「非价格因素」里有单价跌幅超 1% 的，改判「回补后降价清库存」（有价格证据就不叫非价格）；",
        "- 原「其他/需确认」按证据落到具体类：单价明显下跌→清库存嫌疑；单价上涨/不动→非价格因素；",
        "- 原「断货回补(未补货)」里同时降价的改判清库存嫌疑，其余保持「回补未补货」。",
        "",
        "## 对预测与政策的影响",
        "",
        "1. **预测**：`clearance_suspect=true` 的 SKU，其 2026-09 销量**不得当正常需求**"
        "（见 `demand_exclusion` 列）——要么排除 9 月、要么标删失，不得直接喂给模型；",
        "2. **政策**：这些 SKU 的服务档不应因 9 月冲高而上调；"
        "分型里的形态（正常/慢销/长尾）也不该用冲高后的销量重算；",
        "3. **补货**：`断货回补+有补货` 的 SKU 属于正常节奏，可按现有政策继续；"
        "`回补未补货` 需要确认是否漏补；`其他/需确认` 需要人工看单品。",
        "",
        "## 逐 SKU 明细（摘要）",
        "",
        "| SKU | 8月 | 9月 | 倍数 | 单价变化 | 在途 | 零库存天 | 类别 | 清库存嫌疑 |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in frame.sort_values("clearance_suspect", ascending=False).to_dict("records"):
        mark = "是" if row["clearance_suspect"] else ""
        lines.append(
            f"| {row['sku']} | {row['2026-08']:g} | {row['2026-09']:g} | {row['ratio']:.2f} | "
            f"{row['price_chg']:+.2%} | {row['on_order']:g} | {row['aug_zero']:g} | "
            f"{row['category']} | {mark} |")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="9 月异常拆分与清库存标记")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    raw = pd.read_csv(args.candidates)
    frame = classify(raw)
    summary = summarise(frame)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_dir / "promo_clearance_skus.csv", index=False, encoding="utf-8-sig")
    frame[frame["clearance_suspect"]].to_csv(
        out_dir / "clearance_suspects.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{"类别": k, "SKU数": v, "占比%": summary["by_category_share"].get(k, 0)}
                  for k, v in summary["by_category"].items()]).to_csv(
        out_dir / "summary_by_category.csv", index=False, encoding="utf-8-sig")
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    write_report(out_dir / "report.md", frame, summary, generated_at,
                 dict(candidates=str(args.candidates)))
    (out_dir / "summary.json").write_text(json.dumps(
        dict(generated_at=generated_at, **summary), ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
