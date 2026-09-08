#!/usr/bin/env python3
"""
通途「订单详情统计」月度导出（statisticsreport/orderdetail）

仿 tongtu_sales_report.py：登录 → 设发货时间范围（默认全部渠道/账号/销售模式/
是否JIT备货，数据来源=自发货订单，均为页面默认值）→ 切「统计导出」提交统计任务 →
往返 数据查询/统计导出 两 tab 轮询新「点击下载统计结果」→ 下载 zip 到 downloads/。

用法:
  uv run python tongtu_orderdetail_report.py --month 2026-07       # 导出指定月
  uv run python tongtu_orderdetail_report.py                        # 默认当月
  uv run python tongtu_orderdetail_report.py \
      --range-start 2026-07-01 --range-end 2026-07-01               # 小范围验证
  uv run python tongtu_orderdetail_report.py --auto-login           # ddddocr 自动登录
"""
import sys, os, time, io, shutil, calendar
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ORDERDETAIL_URL = "https://erp102.tongtool.com/statisticsreport/orderdetail/index.htm"
SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "chrome-profile"
DOWNLOADS_DIR = WEB_ROOT / "downloads"
LOGIN_TIMEOUT_SECS = 300
POLL_INTERVAL_SECS = 5
POLL_TIMEOUT_SECS = 900  # 全月几十万行统计任务可能较久

# 本页为传统 HTML + My97 日期控件（非 ExtJS），过滤区各下拉默认即 全部/自发货订单，
# 无需额外点选；如需改默认值，改这里。
DATE_FROM = "input[name='shipTimeFrom']"
DATE_TO = "input[name='shipTimeTo']"
QUERY_BTN = "a[onclick='queryInfo()']"
TAB_QUERY = "数据查询"
TAB_EXPORT = "统计导出"
STAT_BTN = "a[onclick='openConfirmWin()']"          # 「统计」按钮
DOWNLOAD_LINK = "a:has-text('点击下载统计结果')"
PREFIX = "订单详情统计"


def is_logged_in(page):
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
        return "编号：" in body_text
    except Exception:
        return False


def wait_for_login(page):
    print(f"\n[信息] 请在浏览器中登录通途...")
    print(f"[信息] 脚本将自动检测登录状态（最长等待 {LOGIN_TIMEOUT_SECS} 秒）")
    for i in range(0, LOGIN_TIMEOUT_SECS, 3):
        time.sleep(3)
        if is_logged_in(page):
            print("[OK] 检测到登录成功！自动继续...")
            page.wait_for_timeout(1000)
            return True
        if i % 15 == 0 and i > 0:
            print(f"  等待登录中... ({i}/{LOGIN_TIMEOUT_SECS}s)")
    return False


def _semi_auto_login(page) -> bool:
    """有 .env 凭据就自动填账号密码，验证码留用户在浏览器输入。"""
    try:
        page.wait_for_selector('input[name="username"]', state="attached", timeout=15000)
    except Exception:
        pass
    try:
        from tongtu_login_ocr import fill_credentials
        if fill_credentials(page):
            print("  已自动填好账号密码（勾选 7 天内自动登录）。")
            print("  请在浏览器窗口输入【图形验证码】并点击登录...")
        else:
            print("  请在浏览器中登录通途（账号 / 密码 / 验证码）...")
    except Exception:
        print("  请在浏览器中登录通途（账号 / 密码 / 验证码）...")
    return wait_for_login(page)


def switch_tab(page, tab_text):
    target = page.locator(f"li:has-text('{tab_text}')").first
    target.wait_for(state="visible", timeout=5000)
    cls = target.get_attribute("class") or ""
    if "active" not in cls:
        print(f"  [操作] 切换到: {tab_text}")
        target.click()
        page.wait_for_timeout(1500)
    else:
        print(f"  [信息] 已在 {tab_text} tab")


def _dismiss_my97(page):
    """fill 后 My97 日历 iframe 会拦住「查询」；Escape + 点页面空白处收起。"""
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        page.locator("body").click(position={"x": 8, "y": 8}, timeout=2000)
    except Exception:
        pass
    page.wait_for_timeout(400)


def set_ship_date_range(page, d_from: str, d_to: str):
    """发货时间起止。日期控件与「查询」只在 数据查询 tab 可见，先切过去；
    My97 文本域直接填值即可，勿按 Enter（会触发整页刷新重置）。
    「查询」失败必须中止：统计条件依赖 queryInfo()，zip 名却用 CLI 月份。"""
    print(f"\n[步骤 1] 设置发货时间范围: {d_from} ~ {d_to}")
    switch_tab(page, TAB_QUERY)
    page.locator(DATE_FROM).wait_for(state="visible", timeout=10000)
    page.locator(DATE_FROM).fill(d_from)
    page.locator(DATE_TO).fill(d_to)
    filled = (
        f"{page.locator(DATE_FROM).input_value()} ~ {page.locator(DATE_TO).input_value()}"
    )
    print(f"  [信息] 起止已填: {filled}")
    _dismiss_my97(page)
    try:
        page.locator(QUERY_BTN).first.click(timeout=5000)
        page.wait_for_timeout(3000)
        print("  [信息] 已点击「查询」")
    except Exception as e:
        print("FAILURE_CODE=QUERY_FAILED")
        print(f"[错误] 点击查询失败（{e}），未提交统计，避免导出错月份")
        sys.exit(1)


def get_existing_download_hrefs(page):
    hrefs = set()
    links = page.locator(DOWNLOAD_LINK)
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        if href:
            hrefs.add(href)
    return hrefs


def _looks_like_mutex(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2000)
    except Exception:
        return False
    return any(s in text for s in ("正在生成", "正在统计", "请稍后再", "任务正在"))


def snapshot_download_hrefs(page):
    """等「统计导出」历史表渲染稳定后再采 href（提交前）。表未加载完时 count 会变化。"""
    switch_tab(page, TAB_EXPORT)
    page.locator(STAT_BTN).wait_for(state="visible", timeout=8000)
    last = -1
    stable = 0
    for _ in range(12):
        n = page.locator(DOWNLOAD_LINK).count()
        if n == last:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
            last = n
        page.wait_for_timeout(400)
    return get_existing_download_hrefs(page)


def submit_statistic(page) -> str:
    """切到统计导出 → 点「统计」→ 弹窗点「提交」。
    返回 'ok' / 'busy'（互斥） / 'submit_failed'（打不开弹窗等）。
    提交链接已可见时不再点「统计」。"""
    print("\n[步骤 2] 切换统计导出并提交统计任务...")
    switch_tab(page, TAB_EXPORT)

    submit_link = page.get_by_role("link", name="提交", exact=True)
    for attempt in range(1, 4):
        try:
            if submit_link.count() and submit_link.first.is_visible():
                print("  [信息] 提交弹窗已打开，不再点「统计」")
                break
            page.locator(STAT_BTN).wait_for(state="visible", timeout=8000)
            print(f"  [操作] 点击「统计」（第 {attempt} 次）...")
            page.locator(STAT_BTN).first.click()
            submit_link.wait_for(state="visible", timeout=8000)
            break
        except Exception as e:
            wait = 10 * attempt
            mutex = _looks_like_mutex(page)
            hint = "，疑似互斥" if mutex else ""
            print(f"  [警告] 未能打开提交弹窗（{e}）{hint}，{wait}s 后重试...")
            time.sleep(wait)
    else:
        return "busy" if _looks_like_mutex(page) else "submit_failed"

    print("  [操作] 点击「提交」...")
    submit_link.click()
    page.wait_for_timeout(2000)
    return "ok"


def wait_for_new_download(page, existing_hrefs):
    print(f"\n[信息] 等待统计任务完成（最长 {POLL_TIMEOUT_SECS} 秒）...")
    start_time = time.time()

    while time.time() - start_time < POLL_TIMEOUT_SECS:
        links = page.locator(DOWNLOAD_LINK)
        for i in range(links.count()):
            href = links.nth(i).get_attribute("href")
            if href and href not in existing_hrefs:
                print(f"  [OK] 发现新下载记录！链接: {href}")
                return href

        # 通途统计页不会自动刷新状态，需往返两 tab 强制刷新
        switch_tab(page, TAB_QUERY)
        page.wait_for_timeout(1000)
        switch_tab(page, TAB_EXPORT)

        elapsed = int(time.time() - start_time)
        if elapsed % 30 < POLL_INTERVAL_SECS:
            print(f"  等待中... ({elapsed}s)")
        time.sleep(POLL_INTERVAL_SECS)

    print("[错误] 等待下载记录超时！")
    return None


def download_file(page, href, stamp: str):
    """点击新下载链接并保存（自带文件名，不信 suggested_filename 的 GBK 乱码）。"""
    target = DOWNLOADS_DIR / f"{PREFIX}_{stamp}.zip"
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  [操作] 下载: {href}")
    with page.expect_download(timeout=300000) as dl_info:
        page.locator(f"a[href='{href}']").first.click()
    download = dl_info.value
    download.save_as(str(target))
    print(f"  [OK] 已保存: {target} ({target.stat().st_size} bytes)")
    return target


def _resolve_range(args):
    """返回 (from_str, to_str)，格式 yyyy-MM-dd HH:mm:ss。"""
    if args.range_start or args.range_end:
        if not (args.range_start and args.range_end):
            raise ValueError("--range-start 与 --range-end 必须同时使用")
        d1 = datetime.strptime(args.range_start, "%Y-%m-%d").date()
        d2 = datetime.strptime(args.range_end, "%Y-%m-%d").date()
        if d1 > d2:
            raise ValueError("--range-start 不能晚于 --range-end")
        return f"{d1} 00:00:00", f"{d2} 23:59:59"
    ym = args.month or datetime.now().strftime("%Y-%m")
    y, m = (int(x) for x in ym.split("-"))
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01 00:00:00", f"{y:04d}-{m:02d}-{last:02d} 23:59:59"


def run(args):
    d_from, d_to = _resolve_range(args)
    ym = d_from[:7].replace("-", "")
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = f"{ym}_{run_ts}"
    print("=" * 50)
    print(f"[通途] 订单详情统计导出  {d_from[:10]} ~ {d_to[:10]}")
    print("=" * 50)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        print(f"[信息] 打开订单详情统计页面...")
        page.goto(ORDERDETAIL_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        if is_logged_in(page):
            print("[OK] 检测到已登录会话，自动继续...")
        elif not (_semi_auto_login(page) if not args.auto_login else _auto_login(page)):
            print("[错误] 登录超时，请重试")
            context.close()
            sys.exit(1)

        # 登录跳转会离开订单详情页，确保停留在报表页再设筛选
        if "orderdetail" not in page.url:
            print("[信息] 重新打开订单详情统计页面...")
            page.goto(ORDERDETAIL_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

        set_ship_date_range(page, d_from, d_to)

        print("\n[步骤 3] 提交统计任务...")
        existing_hrefs = snapshot_download_hrefs(page)
        print(f"  [信息] 提交前已有 {len(existing_hrefs)} 条下载记录")
        submit_code = submit_statistic(page)
        if submit_code != "ok":
            code = "BUSY" if submit_code == "busy" else "SUBMIT_FAILED"
            print(f"FAILURE_CODE={code}")
            print("[错误] 统计任务无法提交，请稍后重试")
            context.close()
            sys.exit(1)

        print("\n[步骤 4] 等待统计完成...")

        download_url = wait_for_new_download(page, existing_hrefs)
        if not download_url:
            print("FAILURE_CODE=DOWNLOAD_TIMEOUT")
            context.close()
            sys.exit(1)

        print("\n[步骤 5] 下载结果文件...")
        zip_result = download_file(page, download_url, tag)
        context.close()

    print(f"\n{'=' * 50}")
    print(f"[完成] 导出成功！")
    print(f"  文件: {zip_result}")
    print(f"{'=' * 50}")


def _auto_login(page) -> bool:
    """ddddocr 全自动登录（需 --auto-login 且子环境已装 OCR 组）。"""
    from tongtu_login_ocr import ensure_ocr, login as ocr_login
    ok, reason = ensure_ocr()
    if not ok:
        print(f"[信息] OCR 不可用（{reason}），降级半自动登录")
        return _semi_auto_login(page)
    if not (os.getenv("TONGTU_USER") and os.getenv("TONGTU_PASSWORD")):
        print("[信息] OCR 自动登录需要 TONGTU_USER/TONGTU_PASSWORD，降级半自动登录")
        return _semi_auto_login(page)
    if ocr_login(page):
        print("[OK] OCR 自动登录成功")
        return True
    print("[信息] OCR 识别多次失败，降级半自动登录")
    return _semi_auto_login(page)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="通途订单详情统计月度导出")
    parser.add_argument("--month", help="目标月份 YYYY-MM（默认当月）")
    parser.add_argument("--range-start", help="起 yyyy-MM-dd（与 --range-end 同用，覆盖 --month）")
    parser.add_argument("--range-end", help="止 yyyy-MM-dd")
    parser.add_argument("--fresh", action="store_true", help="清除旧登录会话")
    parser.add_argument("--auto-login", action="store_true", help="ddddocr 自动登录")
    args = parser.parse_args()
    if bool(args.range_start) != bool(args.range_end):
        parser.error("--range-start 与 --range-end 必须同时使用")

    if args.fresh and PROFILE_DIR.exists():
        print("[信息] --fresh: 清除旧的登录会话...")
        shutil.rmtree(PROFILE_DIR)
    run(args)
