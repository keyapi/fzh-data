# -*- coding: utf-8 -*-
"""Excel 报告生成工具。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def generate_match_report(
    results: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    stats: dict[str, Any],
    out_dir: Path,
    dry_run: bool = True,
) -> Path:
    """生成匹配结果报告 Excel。

    Args:
        results: 匹配成功列表 [{handle, url, tt_sku, item_name, item_group, title}]
        unmatched: 未匹配列表 [{handle, url, tt_sku, title}]
        stats: 汇总统计
        out_dir: 输出目录
        dry_run: 是否为 dry-run 模式

    Returns:
        输出文件路径
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "预览" if dry_run else "执行"
    path = out_dir / f"独立站链接匹配结果_{tag}_{ts}.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # ── 摘要 ──
        summary_rows = [
            {"指标": k, "数值": str(v)}
            for k, v in sorted(stats.items())
        ]
        pd.DataFrame(summary_rows).to_excel(
            writer, sheet_name="汇总", index=False)

        # ── 匹配成功 ──
        if results:
            df_ok = pd.DataFrame(results)
            # 按物料组排序
            if "item_group" in df_ok.columns:
                df_ok = df_ok.sort_values("item_group")
            df_ok.to_excel(writer, sheet_name="匹配成功", index=False)

        # ── 未匹配 ──
        if unmatched:
            df_no = pd.DataFrame(unmatched)
            df_no.to_excel(writer, sheet_name="未匹配", index=False)

        # ── 按物料组合并的产品列表 ──
        if results:
            from collections import defaultdict
            by_group: dict[str, list[dict]] = defaultdict(list)
            for r in results:
                g = r.get("item_group", "(未知)")
                by_group[g].append(r)

            merge_rows = []
            for g, items in sorted(by_group.items()):
                urls = "\n".join(
                    f"{i.get('title','?')}: {i.get('url','')}"
                    for i in items
                )
                skus = ", ".join(i.get("tt_sku", "") for i in items)
                merge_rows.append({
                    "物料组": g,
                    "关联产品数": len(items),
                    "产品链接列表": urls,
                    "SKU列表": skus,
                })
            pd.DataFrame(merge_rows).to_excel(
                writer, sheet_name="按物料组汇总", index=False)

    print(f"  [OK] 报告已生成: {path}")
    return path
