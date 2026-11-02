"""53 补单逐键分类 v2：只改标签/表述，不改数字。

变化（用户 2026-10-28 指示）：
1. 「可执行补单」→「可补单—待定量（证据闭环）」；「可执行补单」重新定义为
   「数量 + 到仓日 + 查重都闭环」，本批 0 行（报告里写明）。
2. 新增「近端兜底」列：首次缺口早于 2026-11-16 且 10/29 新单赶不上 →
   「调拨/加急/接受缺货（待定）」；其余「无」。
3. 未知项/建议动作里「采购量由业务决定」改为「采购量待系统按 L+R=97/157 天重算，
   人只确认外部事实与例外」。

只读输入，输出 _v2 CSV；不改原文件。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

NEAR_END_CUTOFF = "2026-11-16"
NEAR_END_LABEL = "调拨/加急/接受缺货（待定）"
OLD_CATEGORY = "可执行补单"
NEW_CATEGORY = "可补单—待定量（证据闭环）"
NEW_UNKNOWN_TEXT = "采购量待系统按 L+R=97/157 天重算，人只确认外部事实与例外（旧 35 天参考量仅作参考）"
NEW_ACTION_TEXT = (
    "可补单但采购量待定：数量待系统按 L+R=97/157 天重算；"
    "近端缺口见「近端兜底」列（新单赶不上首次缺口）"
)


def gap_start(value) -> str:
    text = str(value)
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28.csv")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28_v2.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.src, encoding="utf-8-sig")
    before_counts = df["分类"].value_counts().to_dict()

    df["分类"] = df["分类"].replace({OLD_CATEGORY: NEW_CATEGORY})

    starts = df["首次缺口周"].map(gap_start)
    late = df["新单是否晚于首次缺口"].astype(str).str.strip() == "是"
    near = (starts < NEAR_END_CUTOFF) & late
    df["近端兜底"] = "无"
    df.loc[near, "近端兜底"] = NEAR_END_LABEL

    # 只改表述，不改任何数量列
    if "未知项" in df.columns:
        df.loc[df["未知项"].astype(str).str.contains("采购量", na=False), "未知项"] = NEW_UNKNOWN_TEXT
    if "建议动作" in df.columns:
        mask = df["分类"] == NEW_CATEGORY
        df.loc[mask, "建议动作"] = NEW_ACTION_TEXT

    # 把「近端兜底」放在「分类」后面，便于阅读
    cols = list(df.columns)
    cols.remove("近端兜底")
    cols.insert(cols.index("分类") + 1, "近端兜底")
    df = df[cols]

    out = Path(args.out)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    after_counts = df["分类"].value_counts().to_dict()
    print(f"rows={len(df)}  out={out}")
    print("分类（改前）:", before_counts)
    print("分类（改后）:", after_counts)
    print("可执行补单（数量+到仓日+查重都闭环）: 0")
    print("近端兜底 =", int(near.sum()), "行；无 =", int((~near).sum()), "行")
    print("近端兜底明细：")
    print(df.loc[near, ["SKU", "仓库", "分类", "首次缺口周"]].to_string(index=False))


if __name__ == "__main__":
    main()
