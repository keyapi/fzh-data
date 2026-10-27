#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性回填：从已有通途 xlsx 产物登记订单号。

网页版上线新库时，`order_number_usage` 是空的。历史批次已经写进通途的订单号
（裸号 / `-N`）只存在于产物 xlsx 里 —— 不回填的话，首次自动补发可能给出
已经被用过的后缀，通途仍会按重复订单号拒收（2026-10-26 真实踩过）。

用法（容器内，默认只预演）：

    python -m web.backfill_order_numbers
    python -m web.backfill_order_numbers --apply
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from web import storage
from web.config import get_settings
from web.repository import Repository

# 这几种产物的第一列都是通途的订单号（导出时由 build_order_df 生成）。
KINDS = ("tongtool", "tongtool_importable", "tongtool_no_stock")
COLUMN = "PO Number"


def collect_numbers(settings, repo: Repository) -> tuple[dict[str, str], list[str]]:
    """返回 ({完整订单号: job_id}, 警告)。读不了的产物跳过并留警告。"""
    found: dict[str, str] = {}
    warnings: list[str] = []
    for art in repo.artifacts_by_kind(KINDS):
        try:
            path = storage.resolve_artifact_path(settings.artifacts_dir, art["rel_path"])
            df = pd.read_excel(path, dtype=str)
        except Exception as exc:  # noqa: BLE001 - 坏产物不能挡住其余回填
            warnings.append(f"{art['download_name']}：读不了（{type(exc).__name__}）")
            continue
        if COLUMN not in df.columns:
            warnings.append(f"{art['download_name']}：没有 {COLUMN} 列")
            continue
        for value in df[COLUMN].dropna().unique():
            number = str(value).strip()
            if number:
                found.setdefault(number, art["job_id"])
    return found, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m web.backfill_order_numbers")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认只预演）")
    args = parser.parse_args(argv)

    settings = get_settings()
    settings.ensure_dirs()
    repo = Repository(settings.db_path)

    found, warnings = collect_numbers(settings, repo)
    for warning in warnings:
        print(f"⚠️ {warning}")
    print(f"扫到 {len(found)} 个订单号")
    if not args.apply:
        for number in sorted(found)[:20]:
            print(f"  {number}")
        if len(found) > 20:
            print(f"  … 另有 {len(found) - 20} 个")
        print("预演结束；确认无误后加 --apply 写入 order_number_usage")
        return 0

    by_job: dict[str, list[str]] = {}
    for number, job_id in found.items():
        by_job.setdefault(job_id, []).append(number)
    for job_id, numbers in by_job.items():
        repo.record_full_numbers(numbers, job_id, source="backfill")
    print(f"已写入 {len(found)} 个订单号（来自 {len(by_job)} 个任务）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
