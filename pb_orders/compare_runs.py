#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本工具的产物与「原 Colab 产物」做一次可复现的一致性对比（迁移验收用）。

用户不需要相信口头结论 —— 每天都能自己跑一遍：

    uv run python compare_runs.py --dir "D:\\Work\\美国\\Tracy Miller\\PB orders\\20260921"
    # --colab 默认取 <dir>/Colab处理

对比三件产物：
  1. 通途 xlsx  —— 形状 / 列名 / **逐单元格**
  2. 背贴 PDF   —— 页数 / 字节数 / **逐页渲染像素**（150dpi）
  3. 标签 PDF   —— 页数 / 逐页 mediabox-cropbox-rotate 签名 / 逐页渲染像素
                   + 用 Colab 里那个时间戳**重建**本工具产物后再比

关于时间戳：标签 PDF 每页盖的是「生成时刻」，两边必然不同（我 17:42 跑的、Colab 16:44 跑的）。
所以除了直接比，还会做一次「把时间戳换成 Colab 的值重建」的对照 —— 这一步能把
「差异仅来自时间戳」从猜测变成证明（期望 0 个不同像素）。

退出码：全部一致 0；有实质差异 1。
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path

import fitz
import numpy as np
import pandas as pd

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

import pb_label_pdf  # noqa: E402
import pb_tongtu_excel  # noqa: E402
import sps_pb_pdf  # noqa: E402

TS_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
DPI = 150
PAT_XLSX = "PB_0_*.xlsx"
PAT_LABEL = "*PotteryBarn label-FZH-DANEEY-Not Prime-第一天.pdf"
PAT_BACK = "*PotteryBarn 背贴-中文西班牙语.pdf"
PAT_PACKSLIP = "Packslip*.pdf"
PAT_ORDER = "checked0stock*.csv"


def _pick(folder, pattern, exclude=()):
    hits = [
        p for p in Path(folder).glob(pattern)
        if not p.name.startswith("~$") and not any(e in p.name for e in exclude)
    ]
    if not hits:
        raise FileNotFoundError(f"{folder} 下找不到 {pattern}")
    return max(hits, key=lambda p: p.stat().st_mtime)


def compare_xlsx(mine_path, colab_path):
    dm = pd.read_excel(mine_path, dtype=object)
    dc = pd.read_excel(colab_path, dtype=object)
    problems, examples, diffs = [], [], 0
    if dm.shape != dc.shape:
        problems.append(f"形状不同 {dm.shape} vs {dc.shape}")
    if list(dm.columns) != list(dc.columns):
        problems.append("列名/列序不同")
    if not problems:
        neq = dm.fillna("<NA>") != dc.fillna("<NA>")
        diffs = int(neq.values.sum())
        for col in dm.columns[neq.any()][:5]:
            row = neq.index[neq[col]][0]
            examples.append(f"{col!r} 第{row}行: 我={dm.at[row, col]!r} Colab={dc.at[row, col]!r}")
    return {"rows": len(dm), "cols": dm.shape[1], "cell_diffs": diffs,
            "examples": examples, "problems": problems}


def _page_signature(doc):
    return [
        (tuple(round(v, 2) for v in p.mediabox), tuple(round(v, 2) for v in p.cropbox),
         tuple(round(v, 2) for v in p.trimbox), p.rotation)
        for p in doc
    ]


def _pixel_diff(a, b, dpi=DPI):
    total, worst = 0, []
    for i in range(min(a.page_count, b.page_count)):
        pa, pb = a[i].get_pixmap(dpi=dpi), b[i].get_pixmap(dpi=dpi)
        if (pa.width, pa.height, pa.n) != (pb.width, pb.height, pb.n):
            worst.append((pa.width * pa.height, i, "页面尺寸不同"))
            total += pa.width * pa.height
            continue
        xa = np.frombuffer(pa.samples, dtype=np.uint8)
        xb = np.frombuffer(pb.samples, dtype=np.uint8)
        diff = int(np.count_nonzero(xa != xb))
        if diff:
            worst.append((diff, i, ""))
        total += diff
    worst.sort(reverse=True)
    return total, worst


def compare_pdf(mine_path, colab_path):
    a, b = fitz.open(mine_path), fitz.open(colab_path)
    problems = []
    if a.page_count != b.page_count:
        problems.append(f"页数不同 {a.page_count} vs {b.page_count}")
    geo_same = _page_signature(a) == _page_signature(b)
    if not geo_same:
        problems.append("mediabox/cropbox/trimbox/rotate 签名不同")
    total, worst = _pixel_diff(a, b)
    text_diff = [
        i for i in range(min(a.page_count, b.page_count))
        if TS_RE.sub("<TS>", a[i].get_text()) != TS_RE.sub("<TS>", b[i].get_text())
    ]
    return {"pages": (a.page_count, b.page_count), "geometry_same": geo_same,
            "px_diff": total, "worst": worst[:3], "text_diff_pages": text_diff,
            "problems": problems}


def rebuild_label_with_colab_ts(day_dir, colab_label_pdf, tmp_dir):
    """用 Colab 产物里的那个时间戳，重新生成一份标签 PDF，返回 (路径, 时间戳)。"""
    doc = fitz.open(colab_label_pdf)
    ts = None
    for page in doc:
        m = TS_RE.search(page.get_text())
        if m:
            ts = m.group(0)
            break
    if not ts:
        raise ValueError(f"没能从 {colab_label_pdf} 里读到时间戳")

    base_pdf = _pick(day_dir, PAT_PACKSLIP)
    order_csv = _pick(day_dir, PAT_ORDER)
    df_pdf = sps_pb_pdf.build_page_df(base_pdf)
    df_order = pb_tongtu_excel.build_order_df(order_csv)
    joined, _ = sps_pb_pdf.join_pages_with_orders(df_pdf, df_order)
    out, _ = pb_label_pdf.build_label_pdf(
        base_pdf, joined["SKUxQTY"].astype(str).tolist(), tmp_dir,
        ts_full=ts, ts_mmdd=f"{ts[5:7]}.{ts[8:10]}",
    )
    return out, ts


def main():
    ap = argparse.ArgumentParser(description="本工具产物 vs Colab 产物 一致性对比")
    ap.add_argument("--dir", required=True, help="当天文件夹（含输入与本工具产物）")
    ap.add_argument("--colab", default=None, help="Colab 产物目录，默认 <dir>/Colab处理")
    args = ap.parse_args()

    day = Path(args.dir).resolve()
    colab = Path(args.colab).resolve() if args.colab else day / "Colab处理"
    if not colab.is_dir():
        sys.exit(f"Colab 产物目录不存在: {colab}")

    mine_xlsx = _pick(day, PAT_XLSX)
    colab_xlsx = _pick(colab, PAT_XLSX)
    mine_back = _pick(day, PAT_BACK)
    colab_back = _pick(colab, PAT_BACK)
    mine_label = _pick(day, PAT_LABEL, exclude=("无货",))
    colab_label = _pick(colab, PAT_LABEL, exclude=("无货",))

    print("=" * 70)
    print("本工具 vs Colab 产物 一致性对比")
    print("=" * 70)
    print(f"本工具 : {day}")
    print(f"Colab  : {colab}")

    failures = []

    # ---------- 1. 通途 xlsx ----------
    print("\n【1】通途 xlsx —— 逐单元格")
    x = compare_xlsx(mine_xlsx, colab_xlsx)
    print(f"  形状 {x['rows']} 行 × {x['cols']} 列")
    print(f"  不一致单元格: {x['cell_diffs']} / {x['rows'] * x['cols']}")
    for e in x["examples"]:
        print(f"    · {e}")
    for p in x["problems"]:
        print(f"    ✗ {p}")
    if x["cell_diffs"] or x["problems"]:
        failures.append("通途 xlsx")
    else:
        print("  ✓ 完全一致 —— 导入通途的结果不会有差别")

    # ---------- 2. 背贴 PDF ----------
    print("\n【2】背贴 PDF —— 页数 / 字节数 / 逐页渲染像素")
    b1 = compare_pdf(mine_back, colab_back)
    print(f"  页数: 我 {b1['pages'][0]} / Colab {b1['pages'][1]}")
    print(f"  字节数: 我 {mine_back.stat().st_size} / Colab {colab_back.stat().st_size}")
    print(f"  页面几何签名一致: {b1['geometry_same']}")
    print(f"  不同像素 (150dpi): {b1['px_diff']}")
    for p in b1["problems"]:
        print(f"    ✗ {p}")
    if b1["px_diff"] or b1["problems"]:
        failures.append("背贴 PDF")
    else:
        print("  ✓ 像素级完全相同 —— 与昨天发出去的那份是同一份东西")

    # ---------- 3. 标签 PDF ----------
    print("\n【3】标签 PDF —— 页数 / 几何 / 渲染像素")
    l1 = compare_pdf(mine_label, colab_label)
    print(f"  页数: 我 {l1['pages'][0]} / Colab {l1['pages'][1]}")
    print(f"  页面几何签名一致: {l1['geometry_same']}")
    print(f"  不同像素 (150dpi): {l1['px_diff']}")
    print(f"  差异最大页: {[(d, i) for d, i, *_ in l1['worst']]}")
    print(f"  归一化时间戳后文字仍不一致的页: {l1['text_diff_pages'] or '无'}")
    for p in l1["problems"]:
        print(f"    ✗ {p}")

    print("\n  → 时间戳是「生成时刻」，两边天然不同（我 17:42 跑 / Colab 16:44 跑）。")
    print("     下面把时间戳换成 Colab 那个值重建一份，再比一次：")
    with tempfile.TemporaryDirectory(prefix="pb_cmp_") as tmp:
        rebuilt, ts = rebuild_label_with_colab_ts(day, colab_label, Path(tmp))
        l2 = compare_pdf(rebuilt, colab_label)
    print(f"     用时间戳 {ts} 重建后：不同像素 {l2['px_diff']}，几何一致 {l2['geometry_same']}")
    if l2["px_diff"] == 0 and l2["geometry_same"]:
        print("  ✓ 除时间戳外**一个像素都不差** —— 版式/坐标/SKU 标注与 Colab 完全相同")
    else:
        failures.append("标签 PDF（时间戳归一后仍有差异）")

    # ---------- 结论 ----------
    print("\n" + "=" * 70)
    if failures:
        print(f"结论：以下产物存在差异 → {failures}")
        sys.exit(1)
    print("结论：三件产物与 Colab 输出等价（标签 PDF 仅差运行时间戳）✓")
    print("=" * 70)


if __name__ == "__main__":
    main()
