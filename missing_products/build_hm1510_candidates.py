# -*- coding: utf-8 -*-
"""Build a read-only HM1510 foam registration cross-check workbook.

Compares the 25 in-stock foam Tongtu SKUs against HM1510 customer_items
(historical rows are prefixed with 删除). No production write is performed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
sys.path.insert(0, str(HERE))

from tongtu_data import latest_file, latest_mainline_audit_path, norm

DELETE_PREFIX = "\u5220\u9664"  # 删除


def load_history() -> tuple[pd.DataFrame, Path]:
    path = latest_file(OUT, "PK_HM1510客户物料号只读调查_*.json")
    if not path:
        raise FileNotFoundError("未找到 PK_HM1510 只读调查 JSON")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload.get("rows") or []), path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    audit = latest_mainline_audit_path()
    foam = pd.read_excel(audit, sheet_name=4, dtype=str)
    history, history_path = load_history()

    hist_codes = {norm(r.get("ref_code")) for _, r in history.iterrows()}
    hist_without_prefix = set()
    for code in hist_codes:
        if code.startswith(DELETE_PREFIX):
            hist_without_prefix.add(code[len(DELETE_PREFIX):])

    rows = []
    for _, r in foam.iterrows():
        sku = norm(r.get("通途SKU"))
        products = norm(r.get("EN精确登记产品"))
        present = sku in hist_without_prefix
        rows.append(
            {
                "通途SKU": sku,
                "EN产品": products,
                "HM1510历史登记": "已存在(删除前缀)" if present else "缺失",
                "建议": "无需新增" if present else "需补齐（确认前缀与目标物料）",
            }
        )
    df = pd.DataFrame(rows)
    missing = df[df["HM1510历史登记"] == "缺失"].copy()

    missing_rows = []
    for _, r in missing.iterrows():
        sku = norm(r.get("通途SKU"))
        target = ""
        if sku == "Curve-Pillow-50-Foam":
            target = "HM1510-YD2-LLK50x22x55-WHITE（历史同码挂在 LLK 与 50x22x55 两个物料）"
        missing_rows.append(
            {
                "通途SKU": sku,
                "EN产品": norm(r.get("EN产品")),
                "候选HM1510": target,
                "推荐前缀": DELETE_PREFIX,
                "说明": "历史同码可参考；写入前需用户确认" if target else "无历史目标，需人工确认 HM1510 物料",
            }
        )
    missing_df = pd.DataFrame(missing_rows)

    notes = [
        ("前缀结论", f"历史 HM1510 客户码使用“{DELETE_PREFIX}”前缀，不是“已删除”；新增建议沿用“{DELETE_PREFIX}”。"),
        ("覆盖情况", "25 条有库存海绵 SKU 中 23 条已在 HM1510 存在删除前缀客户码，2 条缺失。"),
        ("缺失1", "Curve-Pillow-50-Foam：历史 HM1510 码为“删除Curve-Pillow-Foam-50”（顺序不同），挂在 LLK 与 50x22x55 两个物料。"),
        ("缺失2", "TT0031247K0064095-Foam：HM1510 历史无对应码，需先确认目标 HM1510 物料。"),
        ("写入边界", "本工作簿只读；是否补齐、用哪个前缀、挂哪个 HM1510 物料，需用户确认后再写入 EN。"),
        ("REST校验", "生产 EN 校验：客户物料号只能添加到 产品/套件# 物料组及其子孙物料组；HM1510 物料组不属于该范围，API 写入会被 417 拒绝。历史删除前缀码为存量数据，如需新增需评估 SSH/frappe 方式或调整业务校验。"),
    ]

    summary = pd.DataFrame(
        [
            ("有库存海绵 SKU", len(df)),
            ("HM1510 已有删除前缀登记", int((df["HM1510历史登记"] == "已存在(删除前缀)").sum())),
            ("缺失", len(missing_df)),
            ("历史登记来源", history_path.name),
            ("审计底表", audit.name),
            ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ],
        columns=["指标", "值"],
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (OUT / f"海绵HM1510登记候选_{stamp}.xlsx")
    OUT.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="汇总", index=False)
        df.to_excel(writer, sheet_name="25条对照", index=False)
        missing_df.to_excel(writer, sheet_name="待补", index=False)
        history.to_excel(writer, sheet_name="HM1510历史登记参考", index=False)
        pd.DataFrame(notes, columns=["项目", "说明"]).to_excel(writer, sheet_name="业务说明", index=False)

    print(f"已生成: {out_path}")
    print(f"25条={len(df)} 已存在={int((df['HM1510历史登记'] == '已存在(删除前缀)').sum())} 缺失={len(missing_df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
