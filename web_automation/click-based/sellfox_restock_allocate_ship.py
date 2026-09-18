#!/usr/bin/env python3
"""
sellfox_restock_allocate_ship.py
赛狐 海外仓备货单 — 分配库存 + 发货（独立脚本，与导入上传分离）

用法:
  uv run python sellfox_restock_allocate_ship.py                    # 处理全部待配货→待发货→待收货
  uv run python sellfox_restock_allocate_ship.py --after 15:30      # 仅处理15:30之后创建的订单
  uv run python sellfox_restock_allocate_ship.py --allocate-only     # 仅分配库存(不发货)
  uv run python sellfox_restock_allocate_ship.py --headless          # 无头模式

流程:
  待配货 → 选中 → 分配库存 → 待发货 → 选中 → 发货 → 确认弹窗 → 待收货
"""

import sys
import time
import re
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"

PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/stockOrder/index.html"
LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
LOGIN_TIMEOUT = 300
WARMUP_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/detailed/index.html"


def wait_for_login(page):
    print(f"\n请在浏览器中登录赛狐（最长等待 {LOGIN_TIMEOUT}s）...")
    for i in range(0, LOGIN_TIMEOUT, 2):
        time.sleep(2)
        url = page.url
        if "login" not in url and url != "about:blank" and "sellfox" in url:
            print("✓ 登录成功")
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
    url = page.url
    if "login" in url or url == "about:blank":
        return False
    try:
        return page.locator("button:has-text(\"添加单据\")").first.is_visible(timeout=3000)
    except:
        return False


def click_side_menu(page, menu_text: str):
    """点击左侧状态菜单。用 .menu_title（MCP验证可切换）。"""
    page.evaluate(f"""
        (() => {{
            const titles = document.querySelectorAll('.menu_title');
            for (const t of titles) {{
                if (t.textContent.trim().startsWith('{menu_text}') && !t.classList.contains('active')) {{
                    t.click(); return;
                }}
            }}
        }})()
    """)
    page.wait_for_timeout(3000)


def get_order_list(page) -> list[dict]:
    """读取当前页面的备货单列表（仅父行，去重）。"""
    orders = page.evaluate("""
        (() => {
            const rows = document.querySelectorAll('.vxe-table--body tbody tr');
            const seen = new Set();
            const orders = [];
            rows.forEach(r => {
                const text = r.textContent;
                const m = text.match(/(OWS\\w+)\\s*收货仓库\\s*(\\w+)\\s*.*创建时间\\s*([\\d-]+\\s*[\\d:]+)/);
                if (m && !seen.has(m[1])) {
                    seen.add(m[1]);
                    orders.push({orderNo: m[1], warehouse: m[2], createTime: m[3].trim()});
                }
            });
            return orders;
        })()
    """)
    return orders


def select_order_checkbox(page, order_no: str) -> bool:
    """在 VXE 表格中勾选指定备货单（父行）。"""
    return page.evaluate(f"""
        (() => {{
            // Find all unchecked checkbox icons in rows containing the order number
            const icons = document.querySelectorAll('.vxe-checkbox--icon.vxe-checkbox--unchecked-icon');
            for (const icon of icons) {{
                const row = icon.closest('tr');
                if (!row) continue;
                // Only parent rows have the full order info (收货仓库, 创建时间)
                const text = row.textContent;
                if (text.includes('{order_no}') && text.includes('收货仓库') && text.includes('创建时间')) {{
                    icon.click();
                    return true;
                }}
            }}
            return false;
        }})()
    """)


def click_toolbar_button(page, button_text: str) -> bool:
    """点击工具栏按钮（Playwright 原生 click 确保事件正确触发）。"""
    try:
        btn = page.locator('button', has_text=button_text).first
        btn.wait_for(state='visible', timeout=5000)
        btn.click()
        return True
    except Exception:
        return False


def confirm_dialog(page) -> bool:
    """在发货确认弹窗点击"确定"。Element UI message-box 对 Playwright 可见性检查不可靠，用 JS evaluate。"""
    try:
        # 等弹窗出现
        page.wait_for_timeout(2000)
        # 用 JS 找到可见的确认弹窗并点击确定
        clicked = page.evaluate("""
            (() => {
                const wrappers = document.querySelectorAll('.el-message-box__wrapper');
                for (const w of wrappers) {
                    if (w.offsetWidth > 0) {
                        const btn = w.querySelector('button.el-button--primary');
                        if (btn && btn.textContent.trim() === '确定') {
                            btn.click(); return true;
                        }
                    }
                }
                return false;
            })()
        """)
        if not clicked:
            return False
        # 等弹窗消失
        page.wait_for_timeout(2000)
        return True
    except Exception:
        return False


def filter_by_time(orders: list[dict], after: str) -> list[dict]:
    """过滤创建时间晚于 after (HH:MM) 的订单。"""
    today = datetime.now().strftime("%Y-%m-%d ")
    threshold = datetime.strptime(today + after, "%Y-%m-%d %H:%M")
    result = []
    for o in orders:
        try:
            ct = datetime.strptime(today + o["createTime"], "%Y-%m-%d %H:%M:%S")
            if ct > threshold:
                result.append(o)
        except ValueError:
            # Time parsing failure → include anyway
            result.append(o)
    return result


def allocate_all_pending(page, after: str = None) -> list[str]:
    """分配库存：待配货 → 勾选 → 分配库存。返回处理的单号列表。"""
    print("\n--- 分配库存 ---")
    click_side_menu(page, "待配货")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    orders = get_order_list(page)
    print(f"  待配货订单: {len(orders)}")
    if after:
        orders = filter_by_time(orders, after)
        print(f"  时间过滤后 (>{after}): {len(orders)}")

    if not orders:
        print("  无待处理订单")
        return []

    # 一次性勾选所有目标订单
    selected = 0
    for o in orders:
        if select_order_checkbox(page, o["orderNo"]):
            selected += 1
    print(f"  已勾选: {selected}/{len(orders)}")
    page.wait_for_timeout(300)

    click_toolbar_button(page, "分配库存")
    page.wait_for_timeout(2000)

    processed = [o["orderNo"] for o in orders]
    print(f"  完成: 分配 {len(processed)} 单")
    return processed


def ship_all_pending(page, after: str = None) -> list[str]:
    """发货：全部勾选 → 一次发货 → 确定弹窗。返回处理的单号列表。"""
    print("\n--- 发货 ---")
    click_side_menu(page, "自建仓")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    orders = get_order_list(page)
    print(f"  待发货订单: {len(orders)}")
    if after:
        orders = filter_by_time(orders, after)
        print(f"  时间过滤后 (>{after}): {len(orders)}")

    if not orders:
        print("  无待处理订单")
        return []

    # 一次性勾选所有目标订单
    selected = 0
    for o in orders:
        if select_order_checkbox(page, o["orderNo"]):
            selected += 1
    print(f"  已勾选: {selected}/{len(orders)}")
    page.wait_for_timeout(300)

    if not click_toolbar_button(page, "发货"):
        print("  ✗ 未找到发货按钮")
        return []

    if confirm_dialog(page):
        page.wait_for_timeout(3000)
        print(f"  ✓ 已发货: {[o['orderNo'] for o in orders]}")
        return [o["orderNo"] for o in orders]
    else:
        print("  ✗ 未找到确认弹窗")
        return []


def verify_status(page, menu: str, expected_orders: list[str]) -> bool:
    """验证订单已进入目标状态。"""
    click_side_menu(page, menu)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    current = get_order_list(page)
    current_nos = {o["orderNo"] for o in current}
    missing = [no for no in expected_orders if no not in current_nos]

    if missing:
        print(f"  ⚠ {len(missing)} 单未在'{menu}': {missing}")
        return False
    print(f"  ✓ {len(expected_orders)} 单全部在'{menu}'")
    return True


def main():
    headless = "--headless" in sys.argv
    allocate_only = "--allocate-only" in sys.argv
    after = None

    for a in sys.argv[1:]:
        if a.startswith("--after="):
            after = a.split("=", 1)[1]
        elif a == "--after":
            idx = sys.argv.index(a)
            if idx + 1 < len(sys.argv):
                after = sys.argv[idx + 1]

    print(f"\n赛狐 海外仓备货单 — 分配库存 + 发货")
    if after:
        print(f"时间过滤: > {after}")
    if allocate_only:
        print("模式: 仅分配库存")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=headless)
        page = context.pages[0] if context.pages else context.new_page()

        # SPA 预热（参考 sellfox_import_warehouse_restock.py）
        page.goto(WARMUP_URL, timeout=30000)
        page.wait_for_timeout(5000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(5000)

        # 如果还在 dashboard — 重试
        url = page.evaluate("() => location.href")
        if "dashboard" in url or "warehouse" not in url:
            page.goto(PAGE_URL, timeout=30000)
            page.wait_for_timeout(5000)

        # 确保在"全部"tab
        page.evaluate("""
            (() => { for (const el of document.querySelectorAll('*')) {
              if (el.childNodes.length===1 && el.childNodes[0].nodeType===3 && el.textContent.trim()==='全部') {
                el.parentElement.click(); return; } } })()
        """)
        page.wait_for_timeout(2000)

        if is_logged_in(page):
            print("[OK] 已登录")
        else:
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                context.close()
                return

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # 点「重置」清除过滤条件
        page.evaluate("""
            (() => {
                for (const el of document.querySelectorAll('*')) {
                    if (el.textContent.trim() === '重置' && el.offsetWidth > 0) {
                        el.click(); return;
                    }
                }
            })()
        """)
        page.wait_for_timeout(2000)

        # 记录开始时间（如果未指定 --after，用当前时间）
        start_time = after or datetime.now().strftime("%H:%M")

        # Step 1: 分配库存
        allocated = allocate_all_pending(page, after=after)
        if allocated:
            print(f"\n分配完成: {len(allocated)} 单")

        if allocate_only:
            print(f"\n仅分配模式完成。{len(allocated)} 单已分配库存")
            context.close()
            return

        if allocated:
            verify_status(page, "自建仓", allocated)

        # Step 2: 发货（即使没有新分配的单，也可能有待发货的）
        shipped = ship_all_pending(page, after=start_time)
        if shipped:
            verify_status(page, "待收货", shipped)

        # 汇总
        print(f"\n{'='*50}")
        print("完成")
        print(f"{'='*50}")
        print(f"  分配库存: {len(allocated)} 单")
        print(f"  发货:     {len(shipped)} 单")

        context.close()


if __name__ == "__main__":
    main()
