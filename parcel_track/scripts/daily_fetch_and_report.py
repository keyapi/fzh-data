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
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / "web_automation"
DOWNLOADS_DIR = WEB_ROOT / "downloads"
INPUT_DIR = REPO_ROOT / "parcel_track_input"
DAYS_BACK = 7

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

    input_dir = Path(args.input_dir)
    start, end = date_range()
    if not args.skip_fetch:
        try:
            fetch(start, end, input_dir)
        except Exception as exc:
            hint = (
                " 若本机 bundled chromium 有头模式不可用，"
                f"请设 {CHANNEL_ENV}=chrome（见 web_automation/docs/reference/browser-launch.md）"
            )
            _alert(f"{type(exc).__name__}: {exc}\n{hint}")

    # 取数失败也要继续：用输入目录里已有的表照常出报表并推送，
    # 否则无人值守时会「什么都没发生」。
    if newest_xlsx(input_dir) is None:
        print(f"[中止] {input_dir} 下没有任何 xlsx，无表可出", file=sys.stderr)
        return 1

    from parcel_track.cli import main as report_main

    out = args.out or str(REPO_ROOT / "parcel_track_output" / f"ops_{start}_{end}.xlsx")
    cmd = ["report", "--tt", str(input_dir), "--out", out]
    if args.notify:
        cmd.append("--notify")
    return report_main(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
