#!/usr/bin/env python3
"""
sellfox_import_warehouse_restock.py
赛狐 海外仓备货单 一键导入 — 自动上传一个或多个备货单文件

用法:
  uv run python sellfox_import_warehouse_restock.py                         # 导入 restock/ 下所有文件
  uv run python sellfox_import_warehouse_restock.py file1.xlsx file2.xlsx    # 导入指定文件
  uv run python sellfox_import_warehouse_restock.py --fresh                  # 强制重新登录

流程: 登录→添加单据→导入海外仓备货单→添加文件→上传→导入→等结果→读结果→关闭→下一个

注意: 单个备货单不超过500条，文件需预拆批次。
"""
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"
DEFAULT_IMPORT_DIR = WEB_ROOT / "restock"

PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/stockOrder/index.html"
LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
LOGIN_TIMEOUT = 300


def wait_for_login(page):
    print(f"\n请在浏览器中登录赛狐（最长等待 {LOGIN_TIMEOUT}s）...")
    for i in range(0, LOGIN_TIMEOUT, 2):
        time.sleep(2)
        url = page.url
        if "login" not in url and url != "about:blank" and "sellfox" in url:
            print(f"✓ 登录成功")
            page.wait_for_timeout(1000)
            return True
        try:
            if page.locator('text=克勇').first.is_visible():
                print("✓ 登录成功")
                return True
        except:
            pass
    return False


def is_logged_in(page):
    """检测是否已登录 — 看页面是否有「添加单据」按钮。"""
    url = page.url
    if "login" in url or url == "about:blank":
        return False
    try:
        return page.locator("button:has-text(\"添加单据\")").first.is_visible(timeout=3000)
    except:
        return False


def _click_by_text(page, text: str, container_sel: str = "button"):
    """用 JS evaluate 点击匹配文字的按钮，绕过 Playwright has_text 的编码问题。"""
    escaped = text.replace("'", "\\'")
    page.evaluate(f"""
        (() => {{
            for (const el of document.querySelectorAll('{container_sel}')) {{
                if (el.textContent && el.textContent.includes('{escaped}')) {{
                    el.click();
                    return;
                }}
            }}
        }})()
    """)


def import_one_file(page, filepath: Path) -> dict:
    """导入一个备货单文件。返回 {file, success_count, fail_count, error_file}。"""
    print(f"\n{'='*50}")
    print(f"导入: {filepath.name}")
    print(f"{'='*50}")

    # 导航到海外仓备货单页面 — SPA 需要先激活仓库模块
    print("  导航到海外仓备货单页...")
    # 先通过侧边栏点击"仓库"激活模块
    page.goto("https://www.sellfox.com/amzup-web-main/web/warehouse/detailed/index.html", timeout=30000)
    page.wait_for_timeout(5000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # 再导航到海外仓备货单
    page.goto(PAGE_URL, timeout=30000)
    page.wait_for_timeout(5000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    url = page.evaluate("() => location.href")
    print(f"    当前URL: {url[:80]}")

    # 如果还是 dashboard — 再刷一次
    if "dashboard" in url or "warehouse" not in url:
        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(5000)

    # 确保在"全部"tab（否则"添加单据"按钮可能不显示）
    page.evaluate("""
        (() => { for (const el of document.querySelectorAll('*')) {
          if (el.childNodes.length===1 && el.childNodes[0].nodeType===3 && el.textContent.trim()==='全部') {
            el.parentElement.click(); return; } } })()
    """)
    page.wait_for_timeout(2000)

    # 关闭公告弹窗 + 等待「添加单据」按钮 → 检测到立即点击
    print("  等待页面渲染 + 点击添加单据...")
    for attempt in range(30):
        time.sleep(1)
        page.keyboard.press("Escape")
        result = page.evaluate("""
            (() => {
                // Close all announcement dialogs first
                document.querySelectorAll('.el-dialog__headerbtn, [class*="close_btn"]').forEach(b => {
                    if (b.offsetParent !== null) b.click();
                });
                // Find and click 添加单据
                for (const el of document.querySelectorAll('button')) {
                    if ((el.textContent || '').includes('添加单据') && el.offsetParent !== null) {
                        el.click();
                        return 'clicked';
                    }
                }
                return 'waiting';
            })()
        """)
        if result == 'clicked':
            print(f"    已点击添加单据 (第{attempt+1}s)")
            break
    page.wait_for_timeout(800)

    # Step 2: 点击"导入海外仓备货单"
    print("  导入海外仓备货单...")
    page.wait_for_timeout(500)
    r2 = page.evaluate("""
        (() => {
            const items = document.querySelectorAll('.el-dropdown-menu__item');
            for (const item of items) {
                if ((item.textContent || '').includes('导入海外仓备货单')) {
                    item.click();
                    return 'clicked';
                }
            }
            return 'not found. items count: ' + items.length;
        })()
    """)
    print(f"    => {r2}")
    page.wait_for_timeout(1500)

    # Step 3: 确认弹窗打开 + 用原生 click 触发 file chooser
    print("  添加文件...")
    dialog_ok = page.evaluate("""
        (() => {
            const wrappers = document.querySelectorAll('.el-dialog__wrapper');
            for (const d of wrappers) {
                if (window.getComputedStyle(d).display !== 'none') {
                    const btns = d.querySelectorAll('button');
                    for (const btn of btns) {
                        if ((btn.textContent || '').includes('添加文件')) return true;
                    }
                    return 'button not in dialog: ' + [...btns].map(b => b.textContent.trim()).filter(Boolean).slice(0,5).join(', ');
                }
            }
            return 'no dialog';
        })()
    """)
    if dialog_ok is not True:
        raise Exception(f"弹窗异常: {dialog_ok}")
    # 必须用 Playwright 原生 click 触发文件选择器
    # 先注册 file chooser 监听，再点击
    add_file = page.locator("button").filter(has_text="添加文件").first
    with page.expect_file_chooser(timeout=10000) as fc_info:
        add_file.click(timeout=5000)
    file_chooser = fc_info.value
    page.wait_for_timeout(500)

    # Step 4: 上传文件
    print(f"  上传: {filepath.name}")
    file_chooser.set_files(str(filepath))
    page.wait_for_timeout(1000)

    # Step 5: 点击"导入"
    print("  导入中...")
    page.evaluate("""
        (() => {
            const wrappers = document.querySelectorAll('.el-dialog__wrapper');
            for (const d of wrappers) {
                if (window.getComputedStyle(d).display !== 'none') {
                    for (const btn of d.querySelectorAll('button')) {
                        if (btn.textContent.trim() === '导入' && !btn.disabled) {
                            btn.click();
                            return;
                        }
                    }
                }
            }
        })()
    """)

    # Step 6: 轮询导入结果
    result_text = None
    for attempt in range(120):  # 大文件可能需要60s+
        time.sleep(2)
        result = page.evaluate("""
            (() => {
                const wrappers = document.querySelectorAll('.el-dialog__wrapper');
                for (const d of wrappers) {
                    if (window.getComputedStyle(d).display !== 'none') {
                        const t = d.textContent || '';
                        if (t.includes('导入完成')) return t;
                    }
                }
                return null;
            })()
        """)
        if result:
            result_text = result
            break

    if not result_text:
        print("  [!] 超时未收到导入结果（可能弹窗已自动关闭）")
        return {"file": filepath.name, "success": "unknown", "fail": 0}

    # Step 7: 解析结果
    import re
    success_match = re.search(r'成功(\d+)条', result_text)
    fail_match = re.search(r'失败(\d+)条', result_text)
    success_count = int(success_match.group(1)) if success_match else 0
    fail_count = int(fail_match.group(1)) if fail_match else 0

    error_file = None
    if fail_count > 0:
        print(f"  [!] 成功{success_count}条, 失败{fail_count}条 — 下载错误报告...")
        page.evaluate("""
            (() => {
                for (const el of document.querySelectorAll('*')) {
                    if (el.textContent.trim() === '下载查看失败原因') {
                        el.click();
                        return;
                    }
                }
            })()
        """)
        page.wait_for_timeout(2000)
        # Check downloads dir for latest error file
        downloads = sorted(Path(DEFAULT_IMPORT_DIR).parent.glob(".playwright-mcp/导入失败记录*.xlsx"),
                          key=lambda f: f.stat().st_mtime)
        if downloads:
            error_file = str(downloads[-1])
    else:
        print(f"  [OK] 成功{success_count}条")

    # Step 8: 关闭弹窗
    page.evaluate("""
        document.querySelectorAll('.el-dialog__wrapper button').forEach(btn => {
            if (btn.textContent.trim() === '关闭') btn.click();
        });
    """)
    page.wait_for_timeout(500)

    return {
        "file": filepath.name,
        "success": success_count,
        "fail": fail_count,
        "error_file": error_file,
    }


def main():
    fresh = "--fresh" in sys.argv
    headless = "--headless" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--fresh", "--headless")]

    files = []
    if args and not args[0].startswith("--"):
        files = [Path(a).resolve() for a in args]
    else:
        files = sorted(
            f for f in DEFAULT_IMPORT_DIR.glob("*.xlsx")
            if not f.name.startswith("~$")
        )

    if not files:
        print("未找到要导入的 xlsx 文件。")
        print("用法: uv run python sellfox_import_warehouse_restock.py [file1.xlsx ...]")
        print("     或放入 restock/ 目录下自动选取")
        return

    print(f"\n赛狐 海外仓备货单 一键导入")
    print(f"文件数: {len(files)}")
    for f in files:
        print(f"  - {f.name}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
        )
        page = context.pages[0] if context.pages else context.new_page()

        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(3000)

        if fresh:
            print("\n[fresh] 强制重新登录...")
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                print("[失败] 登录超时")
                context.close()
                return
        elif is_logged_in(page):
            print("\n[OK] 已登录，跳过登录步骤")
            page.goto(PAGE_URL, timeout=30000)
            page.wait_for_timeout(3000)
        else:
            print("\n[!] 未登录 → 打开登录页")
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                context.close()
                return

        results = []
        for fp in files:
            if not fp.exists():
                print(f"\n[跳过] 文件不存在: {fp}")
                results.append({"file": fp.name, "success": 0, "fail": "not found"})
                continue
            r = import_one_file(page, fp)
            results.append(r)

        print(f"\n{'='*50}")
        print("导入汇总")
        print(f"{'='*50}")
        total_success = 0
        total_fail = 0
        for r in results:
            status = f"✓ 成功{r['success']}" if not isinstance(r.get('fail'), int) or r['fail'] == 0 else f"✗ 失败{r['fail']}"
            print(f"  {status}  {r['file']}")
            if isinstance(r.get('success'), int):
                total_success += r['success']
            if isinstance(r.get('fail'), int):
                total_fail += r['fail']
        print(f"\n合计: 成功{total_success}条, 失败{total_fail}条")
        if any(r.get('error_file') for r in results):
            print(f"错误报告已下载到 .playwright-mcp/ 目录")
        print(f"\n关闭浏览器...")
        context.close()


if __name__ == "__main__":
    main()
