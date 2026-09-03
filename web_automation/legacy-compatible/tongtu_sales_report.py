#!/usr/bin/env python3
"""
通途销售及库存报表自动导出 + 按仓分表处理

用法:
  uv run python tongtu_sales_report.py                  # 日常导出（依赖 chrome-profile cookie）
  uv run python tongtu_sales_report.py --auto-login      # ddddocr 自动登录（首次/cookie过期）
  uv run python tongtu_sales_report.py --fresh            # 强制重新登录
  uv run python tongtu_sales_report.py --fresh --auto-login  # 清除旧 cookie + 自动登录

流程:
  1. 自动导出「销售及库存报表」统计结果 zip
  2. 解压 → 读取 xlsx（表头 Row 12）→ 按「仓库」列分表
  3. FZH-DANEEY-* 系列仓合并为一个工作表，其余仓库各一个工作表
  4. 输出到 output/ 目录

用法:
  uv run python tongtu_sales_report.py           # 持久化会话，自动导出
  uv run python tongtu_sales_report.py --fresh    # 强制重新登录
"""
import sys, time, io
from pathlib import Path
from datetime import datetime
import subprocess
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SALES_URL = "https://erp102.tongtool.com/statisticsreport/salesandinventory/index.htm"
SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "chrome-profile"
DOWNLOADS_DIR = WEB_ROOT / "downloads"
LOGIN_TIMEOUT_SECS = 300
POLL_INTERVAL_SECS = 5
POLL_TIMEOUT_SECS = 600


def is_logged_in(page):
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
        return "编号：" in body_text
    except:
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


def switch_tab(page, tab_text):
    target = page.locator(f"li:has-text('{tab_text}')").first
    target.wait_for(state="visible", timeout=5000)
    cls = target.get_attribute("class") or ""
    if "active" not in cls:
        print(f"  [操作] 切换到: {tab_text}")
        target.click()
        page.wait_for_timeout(2000)
    else:
        print(f"  [信息] 已在 {tab_text} tab")


def ensure_checkbox(page, checkbox_id, label):
    cb = page.locator(f"#{checkbox_id}")
    cb.wait_for(state="visible", timeout=5000)
    if not cb.is_checked():
        print(f"  [操作] 勾选: {label}")
        cb.check()
        page.wait_for_timeout(1000)
    else:
        print(f"  [信息] 已勾选: {label}")


def get_existing_download_hrefs(page):
    links = page.locator("a:has-text('点击下载统计结果')")
    hrefs = set()
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        if href:
            hrefs.add(href)
    return hrefs


def click_statistic(page):
    btn = page.locator("a#staticBtn")
    btn.wait_for(state="visible", timeout=5000)
    print("  [操作] 点击「统计」按钮...")
    btn.click()
    page.wait_for_timeout(2000)

    modal = page.locator(".ant-modal:visible")
    modal.wait_for(state="visible", timeout=5000)

    body = modal.locator(".ant-modal-body").first
    cond_text = body.inner_text()
    print(f"  [信息] 弹窗统计条件:\n{cond_text}")

    submit_btn = page.locator("#statisSubmitBtn a")
    submit_btn.wait_for(state="visible", timeout=5000)
    print("  [操作] 点击「提交」...")
    submit_btn.click()
    page.wait_for_timeout(2000)

    try:
        modal.wait_for(state="hidden", timeout=10000)
        print("  [OK] 弹窗已关闭，统计任务已提交")
    except:
        print("  [警告] 弹窗未在预期时间内关闭，继续...")


def wait_for_new_download(page, existing_hrefs):
    print(f"\n[信息] 等待统计任务完成（最长 {POLL_TIMEOUT_SECS} 秒）...")
    start_time = time.time()

    while time.time() - start_time < POLL_TIMEOUT_SECS:
        links = page.locator("a:has-text('点击下载统计结果')")
        for i in range(links.count()):
            href = links.nth(i).get_attribute("href")
            if href and href not in existing_hrefs:
                print(f"  [OK] 发现新下载记录！链接: {href}")
                return href

        active_tab = page.locator("li.active").first
        active_text = active_tab.inner_text().strip()

        if "数据查询" in active_text:
            switch_tab(page, "统计导出")
        else:
            switch_tab(page, "数据查询")
            page.wait_for_timeout(1000)
            switch_tab(page, "统计导出")

        elapsed = int(time.time() - start_time)
        if elapsed % 30 < POLL_INTERVAL_SECS:
            print(f"  等待中... ({elapsed}s)")

        time.sleep(POLL_INTERVAL_SECS)

    print("[错误] 等待下载记录超时！")
    return None


def download_file(page, href):
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    filename = f"销售及库存报表_{ts}.zip"
    target = DOWNLOADS_DIR / filename
    DOWNLOADS_DIR.mkdir(exist_ok=True)

    print(f"  [操作] 下载: {href}")
    with page.expect_download(timeout=120000) as dl_info:
        download_link = page.locator(f"a[href='{href}']").first
        download_link.click()

    download = dl_info.value
    download.save_as(str(target))
    file_size = target.stat().st_size
    print(f"  [OK] 已保存: {target} ({file_size} bytes)")
    return target


def run_process(zip_path):
    """调用 process_sales_report.py 处理 zip"""
    print(f"\n{'=' * 50}")
    print("[后处理] 按仓库分表...")
    proc_script = SCRIPT_DIR / "process_sales_report.py"
    result = subprocess.run(
        [sys.executable, str(proc_script), str(zip_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode == 0:
        print(result.stdout)
    else:
        print("[警告] 后处理失败:")
        print(result.stderr)


def run(first_run=False, auto_login=False):
    """主入口"""
    print("=" * 50)
    print("[通途] 销售及库存报表自动导出 + 按仓分表")
    print("=" * 50)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        print("[信息] 打开销售及库存报表页面...")
        page.goto(SALES_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        if is_logged_in(page):
            print("[OK] 检测到已登录会话，自动继续...")
        elif auto_login:
            print("[信息] 尝试 ddddocr 自动登录...")
            try:
                from tongtu_login_ocr import login as auto_login_fn
                if auto_login_fn(page):
                    print("[OK] ddddocr 自动登录成功")
                else:
                    print("[信息] 自动登录失败，切换到手动登录...")
                    if not wait_for_login(page):
                        print("[错误] 登录超时，请重试")
                        context.close()
                        sys.exit(1)
            except ImportError:
                print("[信息] ddddocr 未安装，切换到手动登录...")
                print("[提示] 安装后可自动登录: uv add ddddocr onnxruntime")
                if not wait_for_login(page):
                    print("[错误] 登录超时，请重试")
                    context.close()
                    sys.exit(1)
        else:
            if not first_run:
                print("[信息] 登录会话已过期，请重新登录")
            if not wait_for_login(page):
                print("[错误] 登录超时，请重试")
                context.close()
                sys.exit(1)

        print("\n[步骤 1] 设置筛选条件...")
        ensure_checkbox(page, "isHideStockEmpty", "隐藏所有库存为0的货品")
        ensure_checkbox(page, "hideDeleteSku", "隐藏已删除的货品")

        print("\n[步骤 2] 切换到统计导出...")
        switch_tab(page, "统计导出")
        existing_hrefs = get_existing_download_hrefs(page)
        print(f"  [信息] 提交前已有 {len(existing_hrefs)} 条下载记录")

        print("\n[步骤 3] 提交统计任务...")
        click_statistic(page)

        print("\n[步骤 4] 等待统计完成...")
        download_url = wait_for_new_download(page, existing_hrefs)
        if not download_url:
            print("[错误] 未能获取下载链接，请手动检查页面")
            input("按 Enter 退出...")
            context.close()
            sys.exit(1)

        print("\n[步骤 5] 下载结果文件...")
        zip_result = download_file(page, download_url)

        context.close()

    # 后处理：按仓库分表
    run_process(zip_result)

    print(f"\n{'=' * 50}")
    print(f"[完成] 全部流程结束！")
    print(f"  zip: {zip_result}")
    print(f"  分表: output/ 目录")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    fresh = "--fresh" in sys.argv
    auto_login = "--auto-login" in sys.argv
    if fresh and PROFILE_DIR.exists():
        print("[信息] --fresh: 清除旧的登录会话...")
        shutil.rmtree(PROFILE_DIR)
    run(first_run=fresh, auto_login=auto_login)
