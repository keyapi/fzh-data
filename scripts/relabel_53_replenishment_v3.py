"""53 补单逐键分类 v3：纯文字修正（不改数字、不改分类归属）。

v3 变化（相对 v2，对应 v2 复审 accept-with-findings）：
1. 分类名限定为「可补单—待定量（当前缓存范围内证据闭环）」——PO 导出仅
   2026-08-26..10-26、SO 缓存 as_of 10-27，窗口外旧 PO 不能排除，执行前须再核；
   「补证 = 0」限定为「本轮查询范围内无另列补证」。
2. 修正 3 行「证据结论」里与数值列矛盾的「本仓库存 0」：
   CMKTR-140-WHITE 同仓可发 5、PR-183-GINGER 2、CMPR-194-GINGER 2。
3. 其余与 v2 相同：新增「近端兜底」列；采购量表述改为「待系统按 L+R=97/157 天重算」。

输入用 v1 原始分类 CSV，输出 _v3；不改任何数量/日期列。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

NEAR_END_CUTOFF = "2026-11-16"
NEAR_END_LABEL = "调拨/加急/接受缺货（待定）"
OLD_CATEGORY = "可执行补单"
NEW_CATEGORY = "可补单—待定量（当前缓存范围内证据闭环）"
NEW_UNKNOWN_TEXT = "采购量待系统按 L+R=97/157 天重算，人只确认外部事实与例外（旧 35 天参考量仅作参考）"
NEW_ACTION_TEXT = (
    "可补单但采购量待定：数量待系统按 L+R=97/157 天重算；"
    "近端缺口见「近端兜底」列（新单赶不上首次缺口）"
)

# 只改文字：把与「当前可发」数值列矛盾的说法改成实际同仓可发
EVIDENCE_TEXT = {
    "KS0001-CMKTR-140-WHITE": "同仓可发 5（期初 8）、无可抵扣的 SO/PO/在途",
    "KS0001-PR-183-GINGER": "同仓可发 2（期初 5）、无可抵扣的 SO/PO/在途",
    "KS0002-CMPR-194-GINGER": "同仓可发 2；同区域内他仓另有 2 可调（美中-FZH-DANEEY 2）；"
                              "首次缺口 2026-11-02→2026-11-09（end 排他）",
}


def gap_start(value) -> str:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", str(value))
    return match.group(1) if match else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28.csv")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/53补单逐键分类_2026-10-28_v3.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.src, encoding="utf-8-sig")
    before = df["分类"].value_counts().to_dict()

    df["分类"] = df["分类"].replace({OLD_CATEGORY: NEW_CATEGORY})

    starts = df["首次缺口周"].map(gap_start)
    late = df["新单是否晚于首次缺口"].astype(str).str.strip() == "是"
    near = (starts < NEAR_END_CUTOFF) & late
    df["近端兜底"] = "无"
    df.loc[near, "近端兜底"] = NEAR_END_LABEL

    for sku, text in EVIDENCE_TEXT.items():
        df.loc[df["SKU"] == sku, "证据结论"] = text

    if "未知项" in df.columns:
        df.loc[df["未知项"].astype(str).str.contains("采购量", na=False), "未知项"] = NEW_UNKNOWN_TEXT
    if "建议动作" in df.columns:
        df.loc[df["分类"] == NEW_CATEGORY, "建议动作"] = NEW_ACTION_TEXT

    cols = list(df.columns)
    cols.remove("近端兜底")
    cols.insert(cols.index("分类") + 1, "近端兜底")
    df = df[cols]

    out = Path(args.out)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    after = df["分类"].value_counts().to_dict()
    print(f"rows={len(df)} out={out}")
    print("分类（改前）:", before)
    print("分类（改后）:", after)
    print("可执行补单（数量+到仓日+查重都闭环）= 0")
    print("近端兜底:", df["近端兜底"].value_counts().to_dict())
    print("证据结论修正:")
    for sku in EVIDENCE_TEXT:
        print(" ", sku, "->", df.loc[df["SKU"] == sku, "证据结论"].iloc[0])


if __name__ == "__main__":
    main()
