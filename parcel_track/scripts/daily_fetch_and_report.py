"""每日编排：导通途订单 → 解压 → 出运营异常表 → 推钉钉。

日期范围固定「近 7 天、**截止昨天**」——通途不接受「发货时间」的截止日期为当天
（实测报错），所以不能写成 `<今天-7> ~ <今天>`。

设计取舍：**取数失败不中断**。无人值守场景里，拿不到新数据时更要出声——
这里会先推一条失败告警，再退回用 `parcel_track_input/` 里已有的表继续出报表，
而不是静默退出（静默失败正是这套东西最容易犯的错）。

用法：
    uv run python parcel_track/scripts/daily_fetch_and_report.py
    uv run python parcel_track/scripts/daily_fetch_and_report.py --skip-fetch   # 只跑报表
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web_automation"
DOWNLOADS_DIR = WEB_ROOT / "downloads"
INPUT_DIR = REPO_ROOT / "parcel_track_input"
DAYS_BACK = 7
# 登录页偶发 15s 内渲染不出来（实测 2026-11-05 09:07 一次）——失败后等一会重试一次，
# 避免一次瞬时故障就让当天退回旧数据。
FETCH_ATTEMPTS = 2
FETCH_RETRY_WAIT_SECS = 60

# 本机 bundled chromium 有头模式起不来（详见 web_automation/docs/reference/browser-launch.md）；
# 定时包装里会设这个变量切系统 Chrome。这里只读，不擅自默认。
CHANNEL_ENV = "WEB_AUTOMATION_BROWSER_CHANNEL"


def date_range(today: _dt.date | None = None, days_back: int = DAYS_BACK) -> tuple[str, str]:
    """返回 (起, 止) 的 `YYYY-MM-DD`。止 = 昨天——通途不接受截止为当天。"""
    today = today or _dt.date.today()
    return (today - _dt.timedelta(days=days_back)).isoformat(), (today - _dt.timedelta(days=1)).isoformat()


def newest(paths) -> Path | None:
    items = [p for p in paths if p.is_file() and not p.name.startswith("~$")]
    return max(items, key=lambda p: p.stat().st_mtime) if items else None


def newest_zip(downloads_dir: Path = DOWNLOADS_DIR) -> Path | None:
    return newest(downloads_dir.glob("*.zip")) if downloads_dir.is_dir() else None


def newest_xlsx(folder: Path) -> Path | None:
    return newest(folder.glob("*.xlsx")) if folder.is_dir() else None


def input_range(path: Path) -> tuple[str, str] | None:
    """输入表实际覆盖的发货日期区间。先看文件名（导出按 `_起_止` 命名），读不到再读表。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", path.stem)
    if m:
        return m.group(1), m.group(2)
    try:
        import pandas as pd

        from parcel_track.ingest import read_tongtu_sheet

        df = read_tongtu_sheet(str(path))
        col = next((c for c in df.columns if "发货日期" in str(c)), None)
        if col is None:
            return None
        s = pd.to_datetime(df[col], errors="coerce")
        if s.notna().any():
            return s.min().date().isoformat(), s.max().date().isoformat()
    except Exception:
        return None
    return None


def extract_newest_xlsx(zip_path: Path, dest_dir: Path, name: str) -> Path:
    """把 zip 里最新的 xlsx 解到 dest_dir/name。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / name
    with zipfile.ZipFile(zip_path) as zf:
        inner = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
        if not inner:
            raise ValueError(f"{zip_path} 里没有 xlsx")
        with zf.open(inner[0]) as src, open(target, "wb") as dst:
            dst.write(src.read())
    return target


def fetch(start: str, end: str, input_dir: Path = INPUT_DIR) -> Path:
    """跑通途导出并解压到输入目录；失败抛异常。"""
    cmd = [
        "uv", "run", "python", str(WEB_ROOT / "scripts" / "dispatch.py"),
        "tongtu.orderdetail.export", "--",
        "--range-start", start, "--range-end", end, "--auto-login",
    ]
    print(f"[取数] {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"通途导出失败（exit={proc.returncode}）")
    zip_path = newest_zip()
    if zip_path is None:
        raise RuntimeError(f"{DOWNLOADS_DIR} 下没有新的 zip")
    target = extract_newest_xlsx(zip_path, input_dir, f"通途订单详情统计_{start}_{end}.xlsx")
    print(f"[取数] 已就绪: {target}（来自 {zip_path.name}）", flush=True)
    return target


def _alert(message: str) -> None:
    try:
        from parcel_track.notify import notify_failure

        notify_failure(message, title="尾程日报：取数失败")
        print("[告警] 已推送失败告警到钉钉", file=sys.stderr)
    except Exception as exc:  # 告警本身失败不能盖住主流程
        print(f"[告警] 发送不成功：{exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="每日：通途取数 → 尾程报表 → 钉钉")
    ap.add_argument("--skip-fetch", action="store_true", help="跳过通途导出，直接用输入目录里已有的表")
    ap.add_argument("--notify", action="store_true", help="跑完推钉钉")
    ap.add_argument("--input-dir", default=str(INPUT_DIR), help="输入目录，默认 parcel_track_input/")
    ap.add_argument("--out", help="输出 Excel，默认 parcel_track_output/ops_<起>_<止>.xlsx")
    args = ap.parse_args(argv)

    # 取数失败时 _alert 也要能发钉钉；.env 必须在取数/告警之前加载
    # （原先只在 report_main 里加载，导致告警 KeyError: 'DINGTALK_SECRET'）。
    from parcel_track.cli import _load_env, main as report_main

    _load_env()

    input_dir = Path(args.input_dir)
    start, end = date_range()
    if not args.skip_fetch:
        last_exc: Exception | None = None
        for attempt in range(1, FETCH_ATTEMPTS + 1):
            try:
                fetch(start, end, input_dir)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt < FETCH_ATTEMPTS:
                    print(
                        f"[取数] 第 {attempt} 次失败：{type(exc).__name__}: {exc}；"
                        f"{FETCH_RETRY_WAIT_SECS}s 后重试",
                        file=sys.stderr,
                    )
                    time.sleep(FETCH_RETRY_WAIT_SECS)
        if last_exc is not None:
            hint = (
                " 若本机 bundled chromium 有头模式不可用，"
                f"请设 {CHANNEL_ENV}=chrome（见 web_automation/docs/reference/browser-launch.md）"
            )
            _alert(f"{type(last_exc).__name__}: {last_exc}\n{hint}")

    # 取数失败也要继续：用输入目录里已有的表照常出报表并推送，
    # 否则无人值守时会「什么都没发生」。
    chosen = newest_xlsx(input_dir)
    if chosen is None:
        print(f"[中止] {input_dir} 下没有任何 xlsx，无表可出", file=sys.stderr)
        return 1

    # 新鲜度闸门：取数失败会退回旧输入，绝不能让它冒充当天数据。
    # 区间不符时，输出名与卡片标题都写明**真实**数据区间。
    got = input_range(chosen)
    if got == (start, end):
        out = args.out or str(REPO_ROOT / "parcel_track_output" / f"ops_{start}_{end}.xlsx")
        extra: list[str] = []
    else:
        got_label = f"{got[0]}~{got[1]}" if got else "未知"
        print(f"[陈旧] 最新输入 {chosen.name} 覆盖 {got_label}，期望 {start}~{end}", file=sys.stderr)
        suffix = f"{got[0]}_{got[1]}_stale" if got else "stale"
        out = args.out or str(REPO_ROOT / "parcel_track_output" / f"ops_{suffix}.xlsx")
        extra = [
            "--title",
            f"尾程运营异常 · {_dt.date.today().isoformat()} ｜ ⚠️ 数据区间 {got_label}（今日取数失败）",
        ]

    cmd = ["report", "--tt", str(chosen), "--out", out, *extra]
    if args.notify:
        cmd.append("--notify")
    return report_main(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
