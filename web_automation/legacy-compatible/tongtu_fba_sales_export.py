#!/usr/bin/env python3
"""通途「FBA销量分析报表」月度导出。

流程（与人工一致）：统计报表 → FBA销量分析报表 →
  付款时间=自定义 + 起止整月；亚马逊账号=全部（默认）；
  查询 → 稍等 → 导出（exportExcelWithPic）→ 下载 zip。

用法：
  uv run python tongtu_fba_sales_export.py --month 202610 --auto-login
  uv run python tongtu_fba_sales_export.py --month 2026-10
输出：downloads/通途FBA销量分析报表导出_YYYYMM_<ts>.zip（内含 25 列 xlsx，表头第 1 行）
"""
import sys, io, time, calendar, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_launch import launch_persistent
from tongtu_orderdetail_report import _auto_login, _semi_auto_login, _dismiss_password_warning

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

FBA_URL = "https://erp102.tongtool.com/statisticsreport/fbasalesanalysis/index.htm"
SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "chrome-profile"
DOWNLOADS_DIR = WEB_ROOT / "downloads"


def resolve_month(month: str | None):
    """→ (from 'YYYY-MM-01 00:00:00', to 'YYYY-MM-<last> 23:59:59', ym 'YYYYMM')"""
    if month:
        m = month.replace("-", "")
        y, mo = int(m[:4]), int(m[4:6])
    else:
        t = datetime.datetime.now()
        y, mo = t.year, t.month
    if not (1 <= mo <= 12):
        raise SystemExit(f"月份非法: {month}")
    last = calendar.monthrange(y, mo)[1]
    return (f"{y:04d}-{mo:02d}-01 00:00:00",
            f"{y:04d}-{mo:02d}-{last:02d} 23:59:59",
            f"{y:04d}{mo:02d}")


def _logged_in(page) -> bool:
    try:
        return page.locator("#timeRange_text").count() > 0 and "付款时间" in page.inner_text("body")
    except Exception:
        return False


def _click_visible(page, selector: str):
    loc = page.locator(selector)
    for i in range(loc.count()):
        if loc.nth(i).is_visible():
            loc.nth(i).click()
            return True
    return False


def run(args) -> int:
    d_from, d_to, ym = resolve_month(args.month)
    print("=" * 50)
    print(f"[通途] FBA销量分析报表导出  付款时间 {d_from[:10]} ~ {d_to[:10]}")
    print("=" * 50)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = launch_persistent(
            p, PROFILE_DIR, headless=False, accept_downloads=True,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(FBA_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        if _logged_in(page):
            print("[OK] 检测到已登录会话")
        elif not (_semi_auto_login(page) if not args.auto_login else _auto_login(page)):
            print("FAILURE_CODE=NEED_LOGIN")
            ctx.close()
            return 1
        if "fbasalesanalysis" not in page.url or not _logged_in(page):
            page.goto(FBA_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
        _dismiss_password_warning(page)

        print("[步骤 1] 付款时间=自定义，填起止...")
        page.locator("#timeRange_text").click()
        page.wait_for_timeout(800)
        page.get_by_text("自定义", exact=True).last.click()
        page.wait_for_timeout(1200)
        fr = page.locator("input[name=statisticsTimeFrom]")
        to = page.locator("input[name=statisticsTimeTo]")
        fr.click(); fr.fill(d_from)
        to.click(); to.fill(d_to)
        print(f"  {fr.input_value()} ~ {to.input_value()}")

        print("[步骤 2] 亚马逊账号=全部（默认）→ 查询...")
        if not _click_visible(page, "a:has-text('查询')"):
            print("FAILURE_CODE=QUERY_BTN_NOT_FOUND")
            ctx.close()
            return 1
        page.wait_for_timeout(args.wait_secs * 1000)

        print("[步骤 3] 导出并下载...")
        exp = page.locator("a[onclick='exportExcelWithPic()']")
        if not exp.count():
            print("FAILURE_CODE=EXPORT_BTN_NOT_FOUND")
            ctx.close()
            return 1
        with page.expect_download(timeout=args.download_timeout * 1000) as di:
            exp.first.click()
        d = di.value
        fn = d.suggested_filename
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M")
        suffix = Path(fn).suffix or ".zip"
        save = DOWNLOADS_DIR / f"通途FBA销量分析报表导出_{ym}_{ts}{suffix}"
        d.save_as(str(save))
        ctx.close()

    print("=" * 50)
    print("[完成] 导出成功！")
    print(f"  文件: {save}  ({save.stat().st_size} bytes)")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="通途 FBA销量分析报表月度导出")
    ap.add_argument("--month", help="目标月份 YYYYMM 或 YYYY-MM（默认当月）")
    ap.add_argument("--auto-login", action="store_true", help="ddddocr 自动登录")
    ap.add_argument("--wait-secs", type=int, default=12, help="查询后等待秒数（默认 12）")
    ap.add_argument("--download-timeout", type=int, default=300, help="导出下载超时秒数（默认 300）")
    a = ap.parse_args()
    sys.exit(run(a))
