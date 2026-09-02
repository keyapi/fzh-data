#!/usr/bin/env python3
"""
sellfox_import_other_outbound.py
赛狐 其他出库 导入 + 自验证 + 确认出库

用法:
  uv run python sellfox_import_other_outbound.py file1.xlsx          # 导入指定文件
  uv run python sellfox_import_other_outbound.py --sku test001-white  # 验证+确认该SKU的待确认出库
  uv run python sellfox_import_other_outbound.py --headless           # 无头模式

流程: 导入→自验证(SKU搜索)→确认出库(只点最新)→刷新验证
"""

import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"
DEFAULT_IMPORT_DIR = WEB_ROOT / "outbound"

PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/otherOut/index.html"
LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
LOGIN_TIMEOUT = 300


def wait_for_login(page):
    print(f"\n请在浏览器中登录赛狐（最长等待 {LOGIN_TIMEOUT}s）...")
    for i in range(0, LOGIN_TIMEOUT, 2):
        time.sleep(2)
        url = page.url
        if "login" not in url and url != "about:blank" and "sellfox" in url:
            print("✓ 检测到登录成功！")
            page.wait_for_timeout(1000)
            return True
        try:
            if page.locator('text=克勇').first.is_visible():
                print("✓ 检测到登录成功！")
                return True
        except:
            pass
    return False


def is_logged_in(page):
    url = page.url
    if "login" in url or url == "about:blank":
        return False
    try:
        return page.locator("button:has-text(\"添加单据\")").first.is_visible(timeout=3000)
    except:
        return False


def switch_search_to_sku(page):
    """切换搜索类型为 SKU。"""
    page.evaluate("""
        (() => { const inputs = document.querySelectorAll('input.el-input__inner');
          for (const inp of inputs) { const v = inp.value;
            if (v && ['SKU','识别码','品名','型号','FNSKU','SPU','款名','MSKU','出库单号'].includes(v)) {
              if (v !== 'SKU') { const sel = inp.closest('.el-select'); if (sel) sel.click(); } return; } } })()
    """)
    page.wait_for_timeout(500)
    page.evaluate("""
        (() => { const items = [...document.querySelectorAll('.el-select-dropdown__item')]
          .filter(i => i.getBoundingClientRect().width > 0);
          const m = items.find(i => i.textContent.trim() === 'SKU'); if (m) m.click(); })()
    """)
    page.wait_for_timeout(300)


def search_sku(page, sku: str):
    """搜索指定 SKU。"""
    si = page.locator("input.el-input__inner[placeholder='搜索内容']")
    if si.count() == 0:
        si = page.locator("input[placeholder='搜索内容']").first
    si.fill(sku)
    si.press("Enter")
    page.wait_for_timeout(3000)


def confirm_all_outbound(page) -> int:
    """确认页面上所有待确认的出库单（每确认一笔刷新页面检查）。"""
    print("  确认全部待确认出库单...")
    confirmed = 0
    for attempt in range(20):
        # 刷新页面获取最新状态
        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(5000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # 清除 loading mask
        page.evaluate("document.querySelectorAll('.el-loading-mask').forEach(m => m.remove())")
        page.wait_for_timeout(500)

        # 用 JS 查找并点击可见的确认出库按钮（跳过 Playwright 的 loading mask 限制）
        clicked = page.evaluate("""
            (() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.trim() === '确认出库' && btn.offsetParent !== null) {
                        btn.click();
                        return 'clicked';
                    }
                }
                return 'not found';
            })()
        """)
        if clicked != 'clicked':
            break
        confirmed += 1
        print(f"    ✓ 已确认第{confirmed}笔")

        # 等待服务器处理完成（loading mask 出现→消失）
        page.wait_for_timeout(2000)
        try:
            mask = page.locator('.el-loading-mask').first
            mask.wait_for(state='attached', timeout=10000)
            mask.wait_for(state='hidden', timeout=120000)
        except:
            page.wait_for_timeout(10000)

    print(f"  确认完成: {confirmed} 笔")
    return confirmed


def import_one_file(page, filepath: Path, sku: str = None) -> dict:
    """导入一个出库文件 + 自验证 + 确认出库。"""
    print(f"\n{'='*50}")
    print(f"导入: {filepath.name}")
    print(f"{'='*50}")

    # 导航
    page.goto(PAGE_URL, timeout=30000)
    page.wait_for_timeout(5000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # 添加单据 → 导入出库单
    page.evaluate("""
        (() => { for (const el of document.querySelectorAll('button')) {
          if ((el.textContent||'').includes('添加单据') && el.offsetParent!==null) { el.click(); break; } } })()
    """)
    page.wait_for_timeout(600)
    page.evaluate("""
        (() => { for (const item of document.querySelectorAll('.el-dropdown-menu__item')) {
          if ((item.textContent||'').includes('导入出库单')) { item.click(); return; } } })()
    """)
    page.wait_for_timeout(1500)

    # 上传
    add_file_btn = page.locator('.el-dialog button', has_text="添加文件").first
    add_file_btn.wait_for(state="visible", timeout=5000)
    with page.expect_file_chooser(timeout=10000) as fc_info:
        add_file_btn.click(timeout=5000)
    fc_info.value.set_files(str(filepath))
    page.wait_for_timeout(1000)

    # 导入
    page.evaluate("""
        (() => { const wrappers = document.querySelectorAll('.el-dialog__wrapper');
          for (const d of wrappers) { if (window.getComputedStyle(d).display!=='none') {
            for (const btn of d.querySelectorAll('button')) {
              if (btn.textContent.trim()==='导入' && !btn.disabled) { btn.click(); return; } } } } })()
    """)

    # 等结果
    result_text = None
    for _ in range(40):
        time.sleep(2)
        r = page.evaluate("""
            (() => { const wrappers = document.querySelectorAll('.el-dialog__wrapper');
              for (const d of wrappers) { if (window.getComputedStyle(d).display!=='none') {
                const t = d.textContent||''; if (t.includes('导入完成')) return t; } } return null; })()
        """)
        if r:
            result_text = r
            break

    if not result_text:
        print("  [!] 超时未收到导入结果")
        return {"success": False, "error": "timeout"}

    import re
    s_ok = re.search(r'成功(\d+)条', result_text)
    s_fail = re.search(r'失败(\d+)条', result_text)
    print(f"  导入: 成功{int(s_ok.group(1)) if s_ok else 0}条, 失败{int(s_fail.group(1)) if s_fail else 0}条")

    # 关闭弹窗
    page.evaluate("""
        document.querySelectorAll('.el-dialog__wrapper button').forEach(btn => {
          if (btn.textContent.trim()==='关闭') btn.click(); });""")
    page.wait_for_timeout(500)

    # 确认出库：先刷新页面让新记录出现
    print("  刷新页面...")
    page.goto(PAGE_URL, timeout=30000)
    page.wait_for_timeout(5000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    confirmed = confirm_all_outbound(page)

    # 自验证
    verified = False
    if sku:
        print(f"  自验证: 搜索 SKU={sku}...")
        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(5000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        switch_search_to_sku(page)
        search_sku(page, sku)

        v = page.evaluate(f"""
            (() => {{ let c=0; document.querySelectorAll('.vxe-table--body tbody tr').forEach(r => {{
              if (r.textContent.includes('{sku}')) c++; }}); return c>0; }})()""")
        verified = bool(v)
        print(f"  {'✓' if verified else '✗'} SKU {'找到' if verified else '未找到'}")

    return {"success": True, "verified": verified, "confirmed": confirmed}


def main():
    headless = "--headless" in sys.argv
    fresh = "--fresh" in sys.argv
    sku = None
    file_args = []

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--sku" and i + 1 < len(args):
            sku = args[i + 1]; i += 2
        elif args[i] in ("--headless", "--fresh"):
            i += 1
        else:
            file_args.append(args[i]); i += 1

    files = [Path(a).resolve() for a in file_args] if file_args else sorted(
        f for f in DEFAULT_IMPORT_DIR.glob("*.xlsx") if not f.name.startswith("~$"))

    if not files:
        if sku:
            print(f"仅验证+确认模式: SKU={sku}")
        else:
            print("未找到要导入的 xlsx 文件")
            return

    print(f"\n赛狐 其他出库 导入{' + 确认' if sku else ''}")
    if files:
        for f in files:
            print(f"  - {f.name}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=headless)
        page = context.pages[0] if context.pages else context.new_page()

        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(3000)

        if is_logged_in(page):
            print("[OK] 已登录")
        elif fresh:
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                context.close(); return
        else:
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                context.close(); return

        for fp in files:
            if not fp.exists():
                print(f"\n[跳过] 文件不存在: {fp}")
                continue
            r = import_one_file(page, fp, sku=sku)
            print(f"  结果: 导入={'✓' if r['success'] else '✗'}, "
                  f"验证={'✓' if r.get('verified') else '✗'}, "
                  f"确认={r.get('confirmed', 0)}条")

        context.close()


if __name__ == "__main__":
    main()
