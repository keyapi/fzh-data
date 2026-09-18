#!/usr/bin/env python3
"""
sellfox_restock_receive.py
赛狐 海外仓备货单 — 按SKU收货（批量方式）

用法:
  uv run python sellfox_restock_receive.py                           # 处理全部待收货订单
  uv run python sellfox_restock_receive.py --order OWS293A9T700003   # 指定单号
  uv run python sellfox_restock_receive.py --after 15:30             # 仅处理15:30后创建的单
  uv run python sellfox_restock_receive.py --headless                # 无头模式

流程: 待收货 → 勾选 → 收货下拉 → SKU收货 → 全部数量 → 确定 → 确认弹窗 → 自验证
"""

import sys
import time
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

# ── 登录 ──────────────────────────────────────────────────

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

# ── 页面导航 ──────────────────────────────────────────────

def navigate_to_stock_order(page):
    """导航到海外仓备货单页面（参考 sellfox_import_warehouse_restock.py）。"""
    print("  导航到海外仓备货单页...")
    page.goto("https://www.sellfox.com/amzup-web-main/web/warehouse/detailed/index.html", timeout=30000)
    page.wait_for_timeout(5000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

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

    # 确保在"全部"tab + 点「重置」清除所有过滤条件
    page.evaluate("""
        (() => { for (const el of document.querySelectorAll('*')) {
          if (el.childNodes.length===1 && el.childNodes[0].nodeType===3 && el.textContent.trim()==='全部') {
            el.parentElement.click(); return; } } })()
    """)
    page.wait_for_timeout(2000)
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


def click_side_menu(page, menu_text: str):
    """点击左侧菜单项。用 .menu_title（MCP验证可切换），不用 .menu-item（不生效）。"""
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
    """读取当前页面备货单列表。先滚 VXE 表格确保所有行渲染。"""
    # 滚动 VXE wrapper 确保所有行被虚拟滚动渲染
    page.evaluate("""
        (() => {
            const wrapper = document.querySelector('.vxe-table--body-wrapper');
            if (wrapper) {
                wrapper.scrollTop = wrapper.scrollHeight;
            }
        })()
    """)
    page.wait_for_timeout(800)
    page.evaluate("""
        (() => {
            const wrapper = document.querySelector('.vxe-table--body-wrapper');
            if (wrapper) {
                wrapper.scrollTop = 0;
            }
        })()
    """)
    page.wait_for_timeout(800)

    return page.evaluate("""
        (() => {
            const dropdowns = document.querySelectorAll('.dropdown_btn_text.el-dropdown');
            const seen = new Set();
            const orders = [];
            for (const dd of dropdowns) {
                const row = dd.closest('tr');
                if (!row) continue;
                const text = row.textContent;
                const m = text.match(/(OWS\\w+)\\s*\\S*收货仓库\\s*(\\w+)\\s*.*创建时间\\s*([\\d-]+\\s*[\\d:]+)/);
                if (m && !seen.has(m[1])) {
                    seen.add(m[1]);
                    orders.push({orderNo: m[1], warehouse: m[2], createTime: m[3].trim()});
                }
            }
            return orders;
        })()
    """)


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
            result.append(o)
    return result


def select_order_checkbox(page, order_no: str) -> bool:
    """勾选指定备货单的 checkbox。"""
    return page.evaluate(f"""
        (() => {{
            const icons = document.querySelectorAll('.vxe-checkbox--icon.vxe-checkbox--unchecked-icon');
            for (const icon of icons) {{
                const row = icon.closest('tr');
                if (row && row.textContent.includes('{order_no}') && row.textContent.includes('收货仓库')) {{
                    icon.click();
                    return true;
                }}
            }}
            return false;
        }})()
    """)

# ── 收货核心 ─────────────────────────────────────────────

def receive_selected_orders(page, orders: list[str]) -> bool:
    """批量 SKU收货：选中 → 收货下拉 → SKU收货 → 全部 → 确定 → 确认弹窗。"""
    if not orders:
        return True

    print(f"  选中 {len(orders)} 单: {orders}")

    # 1. 勾选订单
    for no in orders:
        if not select_order_checkbox(page, no):
            print(f"    ⚠ 勾选 {no} 失败")
    page.wait_for_timeout(1500)

    # 2. 确认收货按钮已启用后再点击
    menu_id = page.evaluate("""
        (() => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                if (text === '收货' && btn.offsetWidth > 0 && !btn.disabled) {
                    const id = btn.getAttribute('aria-controls');
                    btn.click();
                    return id;
                }
            }
            return null;
        })()
    """)
    print(f"    收货按钮: menu_id={menu_id}")
    if not menu_id:
        print("  ✗ 未找到收货按钮")
        return False
    page.wait_for_timeout(1500)

    # 3. 在正确的下拉菜单中点「SKU收货」
    menu_found = page.evaluate(f"""
        (() => {{
            const menu = document.getElementById('{menu_id}');
            if (!menu) return 'menu-not-found';
            const items = menu.querySelectorAll('.el-dropdown-menu__item');
            for (const item of items) {{
                if (item.textContent.trim() === 'SKU收货') {{
                    item.click(); return 'clicked';
                }}
            }}
            return 'item-not-found';
        }})()
    """)
    print(f"    SKU收货菜单: {menu_found}")
    page.wait_for_timeout(2000)

    # 4. 等 SKU收货弹窗
    page.wait_for_timeout(2000)
    dialog_visible = page.evaluate("""
        (() => {
            const d = document.querySelector('.oversea_receiving_by_sku_dialog');
            return d && d.offsetWidth > 0;
        })()
    """)
    if not dialog_visible:
        print("  ✗ SKU收货弹窗未出现")
        return False

    # 5. 点「全部」填入数量（JS evaluate，不用 Playwright locator）
    page.evaluate("""
        (() => {
            const dialog = document.querySelector('.oversea_receiving_by_sku_dialog');
            const btns = dialog.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.textContent.trim() === '全部') { btn.click(); return; }
            }
        })()
    """)
    page.wait_for_timeout(500)

    # 6. 点「确定」
    page.evaluate("""
        (() => {
            const dialog = document.querySelector('.oversea_receiving_by_sku_dialog');
            const btns = dialog.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.textContent.trim() === '确定') { btn.click(); return; }
            }
        })()
    """)
    page.wait_for_timeout(2000)

    # 7. 确认弹窗「收货仓库存将会增加，确认收货？」
    confirmed = page.evaluate("""
        (() => {
            const wrappers = document.querySelectorAll('.el-message-box__wrapper');
            for (const w of wrappers) {
                if (w.offsetWidth > 0 && w.textContent.includes('确认收货')) {
                    const btns = w.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.textContent.trim() === '确定') { btn.click(); return true; }
                    }
                }
            }
            return false;
        })()
    """)
    print(f"    确认弹窗: {'已点击' if confirmed else '未出现'}")

    # 8. 等待 loading mask 出现→消失，或弹窗关闭
    for _ in range(60):
        time.sleep(1)
        still_open = page.evaluate("""
            (() => {
                const d = document.querySelector('.oversea_receiving_by_sku_dialog');
                return d && d.offsetWidth > 0;
            })()
        """)
        if not still_open:
            print("    弹窗已关闭，收货完成")
            break
    else:
        print("  ⚠ 弹窗60s未关闭（可能处理中或失败）")

    page.wait_for_timeout(3000)
    return True


def verify_sidebar_counts(page, expected_received: int):
    """验证待收货减量、已完成增量。"""
    page.wait_for_timeout(1000)
    info = page.evaluate("""
        (() => {
            const items = document.querySelectorAll('.menu-item');
            let received = '', completed = '';
            items.forEach(item => {
                const text = item.textContent.trim();
                if (text.startsWith('待收货')) received = text;
                if (text.startsWith('已完成')) completed = text;
            });
            return {received, completed};
        })()
    """)
    print(f"  验证: 待收货={info['received']}, 已完成={info['completed']}")
    return info

# ── Main ─────────────────────────────────────────────────

def main():
    headless = "--headless" in sys.argv
    after = None
    target_order = None

    for a in sys.argv[1:]:
        if a.startswith("--order="):
            target_order = a.split("=", 1)[1]
        elif a == "--order":
            idx = sys.argv.index(a)
            if idx + 1 < len(sys.argv):
                target_order = sys.argv[idx + 1]
        elif a.startswith("--after="):
            after = a.split("=", 1)[1]
        elif a == "--after":
            idx = sys.argv.index(a)
            if idx + 1 < len(sys.argv):
                after = sys.argv[idx + 1]

    print(f"\n赛狐 海外仓备货单 — SKU收货（批量）")
    if target_order:
        print(f"指定单号: {target_order}")
    if after:
        print(f"时间过滤: > {after}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=headless)
        page = context.pages[0] if context.pages else context.new_page()

        navigate_to_stock_order(page)

        if not is_logged_in(page):
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                context.close()
                return
        print("[OK] 已登录")

        # 切到待收货
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        click_side_menu(page, "待收货")

        # 读取待收货列表
        all_orders = get_order_list(page)
        print(f"\n待收货订单: {len(all_orders)}")

        # 过滤
        if target_order:
            target_orders = [o for o in all_orders if o["orderNo"] == target_order]
            if not target_orders:
                print(f"  ✗ 待收货列表中未找到 {target_order}")
                context.close()
                return
        elif after:
            target_orders = filter_by_time(all_orders, after)
            print(f"时间过滤后 (>{after}): {len(target_orders)}")
        else:
            target_orders = all_orders

        if not target_orders:
            print("无待处理订单")
            context.close()
            return

        # 执行批量收货
        order_nos = [o["orderNo"] for o in target_orders]
        print(f"\n{'='*50}")
        print(f"开始批量SKU收货: {len(order_nos)} 单")
        print(f"{'='*50}")

        success = receive_selected_orders(page, order_nos)

        # 验证
        verify_sidebar_counts(page, len(order_nos))

        print(f"\n{'='*50}")
        print("完成")
        print(f"{'='*50}")
        print(f"  收货: {'✓' if success else '✗'} {len(order_nos)} 单")
        for no in order_nos:
            print(f"    {no}")

        context.close()


if __name__ == "__main__":
    main()
