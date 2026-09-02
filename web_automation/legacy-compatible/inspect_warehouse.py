"""
诊断脚本：抓取通途库存结存页面的仓库选择器 DOM 结构
用法: uv run python inspect_warehouse.py
"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

TONGTU_URL = "https://erp102.tongtool.com/warehouse/goodsbalance/index.htm?warehouse=1&isFirstInto=1"
SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent

def dump_elements(page, label_contains):
    """用 JS 抓取所有包含指定文字的可视元素"""
    result = page.evaluate("""
        (searchText) => {
            const results = [];
            document.querySelectorAll('*').forEach(el => {
                if (el.offsetParent === null) return;
                const text = (el.innerText || '').slice(0, 200);
                if (text.includes(searchText)) {
                    // 向上找最近的有意义的容器（最多4层）
                    let container = el;
                    for (let i = 0; i < 4; i++) {
                        const p = container.parentElement;
                        if (!p || p === document.body) break;
                        container = p;
                    }
                    results.push({
                        tag: el.tagName,
                        id: el.id || '',
                        className: (el.className && typeof el.className === 'string') ? el.className : '',
                        text: text,
                        outerHTML: el.outerHTML.slice(0, 500),
                        containerTag: container.tagName,
                        containerClass: (container.className && typeof container.className === 'string') ? container.className : '',
                        visible: el.offsetParent !== null,
                    });
                }
            });
            return results;
        }
    """, label_contains)
    return result


import time

def run():
    with sync_playwright() as p:
        print("[信息] 启动 Chromium...")
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(accept_downloads=True, viewport={"width": 1280, "height": 800})
        page = ctx.new_page()

        print(f"[信息] 打开 {TONGTU_URL}")
        page.goto(TONGTU_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # 第一步：截图登录页
        screenshot_path = SCRIPT_DIR / "debug_screenshot.png"
        page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"[截图] 登录页/当前页 → {screenshot_path}")

        wait_secs = 60
        print(f"\n{'='*50}")
        print(f"请在浏览器中登录通途、选择仓库 FZH-DANEEY-皮壳仓库")
        print(f"脚本将在 {wait_secs} 秒后自动继续...")
        print(f"{'='*50}")
        for i in range(wait_secs, 0, -10):
            print(f"  剩余 {i} 秒...")
            time.sleep(10)

        # 第二步：登录并选仓库后再截图和分析
        print("\n[信息] 开始抓取页面元素...")
        page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"[截图] 已更新: {screenshot_path}")

        # 抓取包含"仓库"的元素
        warehouse_els = dump_elements(page, "仓库")
        out_path = SCRIPT_DIR / "debug_warehouse_elements.json"
        out_path.write_text(json.dumps(warehouse_els, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[DOM] 包含'仓库'的元素: {len(warehouse_els)} 个 → {out_path}")

        # 抓取包含"皮壳"的元素（仓库名可能是这个）
        pike_els = dump_elements(page, "皮壳")
        pike_path = SCRIPT_DIR / "debug_pike_elements.json"
        pike_path.write_text(json.dumps(pike_els, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[DOM] 包含'皮壳'的元素: {len(pike_els)} 个 → {pike_path}")

        # 抓取所有 select/input/dropdown 类元素
        form_els = page.evaluate("""
            () => {
                const results = [];
                const selectors = ['select', 'input', '[role="combobox"]', '[role="listbox"]',
                    '.dropdown', '.select', '.picker', '.chooser', '.combo', '.ant-select',
                    '.el-select', '.mu-select', '[class*="drop"]', '[class*="select"]'];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        if (el.offsetParent === null) return;
                        results.push({
                            selector: sel,
                            tag: el.tagName,
                            id: el.id || '',
                            className: (el.className && typeof el.className === 'string') ? el.className : '',
                            value: el.value || '',
                            placeholder: el.placeholder || '',
                            text: (el.innerText || '').slice(0, 100),
                            outerHTML: el.outerHTML.slice(0, 400),
                        });
                    });
                });
                return results;
            }
        """)
        form_path = SCRIPT_DIR / "debug_form_elements.json"
        form_path.write_text(json.dumps(form_els, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[DOM] 表单/下拉元素: {len(form_els)} 个 → {form_path}")

        # 页面标题和当前URL
        print(f"\n[页面标题] {page.title()}")
        print(f"[当前URL] {page.url}")

        browser.close()
        print("\n[完成] 诊断完成。")

if __name__ == "__main__":
    run()
