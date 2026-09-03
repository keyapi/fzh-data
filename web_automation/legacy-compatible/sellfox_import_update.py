#!/usr/bin/env python3
"""
赛狐商品导入更新 — 闭环验证版

用法:
  uv run python sellfox_import_update.py

流程:
  1. pd.DataFrame() 生成新 Excel（不复用模板！）
  2. 浏览器点击上传导入
  3. API 搜索 SKU 验证数据是否更新（闭环）

踩坑:
  - Excel 必须 pd.DataFrame() 直接构造，不能用 pd.read_excel(模板)
  - 模板有隐藏 worksheet/格式，读取后会干扰导入
"""

import time, sys
from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"
DOWNLOADS_DIR = WEB_ROOT / "downloads"

LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
PAGE_URL  = "https://www.sellfox.com/amzup-web-main/web/commodity/index.html"

# 规格信息 16 列（含 *SKU）—— 从下载模板 API 验证过的表头
COLUMNS = [
    "*SKU",
    "商品规格长(cm)", "商品规格宽(cm)", "商品规格高(cm)",
    "商品重量", "商品重量单位",
    "箱规长(cm)", "箱规宽(cm)", "箱规高(cm)",
    "单箱重量(kg)", "单箱数量(PCS)",
    "商品包装规格长(cm)", "商品包装规格宽(cm)", "商品包装规格高(cm)",
    "商品包装重量", "商品包装重量单位",
]

SKU = "test001-white"

# ── 登录 ──

def is_logged_in(page):
    try:
        return ("login" not in page.url
                and page.locator("text=克勇").first.is_visible())
    except:
        return False

def wait_for_login(page):
    print("  请在浏览器中手动登录...")
    for _ in range(150):
        time.sleep(2)
        try:
            if page.locator("text=克勇").first.is_visible():
                return True
        except:
            pass
        if "login" not in page.url and "sellfox" in page.url:
            return True
    return False

# ── 生成 Excel ──

def make_import_excel(sku, data_15, path):
    """
    生成导入 Excel —— 不复用模板文件！

    踩坑: sheet 名必须是 '商品'（赛狐模板的默认名），
    不能用 pd.to_excel() 默认的 'Sheet1'
    也不能 pd.read_excel(模板) — 模板有 hidden1/hidden2 隐藏 sheet
    """
    df = pd.DataFrame([[sku] + list(data_15)], columns=COLUMNS)
    with pd.ExcelWriter(path, engine='openpyxl') as w:
        df.to_excel(w, sheet_name='商品', index=False)
    print(f"  Generated: {path.name} ({len(df)} rows)")

# ── 上传导入 ──

def do_import(page, file_path):
    print("  [Import] Opening dialog...")
    page.evaluate("(() => { [...document.querySelectorAll('button')]"
                  ".find(b=>b.textContent.trim()==='导入')?.click(); })()")
    page.wait_for_timeout(800)
    page.evaluate("(() => { [...document.querySelectorAll('.el-dropdown-menu__item')]"
                  ".find(i=>i.textContent.trim()==='导入更新商品')?.click(); })()")
    page.wait_for_timeout(3000)

    print("  [Import] Checking spec-info...")
    page.evaluate("(() => { const b=document.querySelector('.el-dialog__body');"
                  " if(b) b.scrollTop=b.scrollHeight; })()")
    page.wait_for_timeout(300)
    page.locator('.el-checkbox:has(.el-checkbox__label:text-is("规格信息"))').click()
    page.wait_for_timeout(300)

    print(f"  [Import] Uploading: {file_path.name}")
    with page.expect_file_chooser() as fc:
        page.locator('.el-button--primary:has-text("添加文件")').click()
    fc.value.set_files(str(file_path.resolve()))
    page.wait_for_timeout(800)

    print("  [Import] Clicking import...")
    page.get_by_role("button", name="导入", exact=True).click()

    for sec in range(120):
        text = page.evaluate(
            "(() => { const d=[...document.querySelectorAll('.el-dialog__wrapper')]"
            ".find(x=>x.getBoundingClientRect().width>0);"
            "return d?.textContent?.trim()?.substring(0,200)||''; })()")
        if "导入完成" in text:
            print(f"  [OK] {text.strip()}")
            return True
        if sec % 20 == 0 and sec > 0:
            print(f"       waiting... ({sec}s)")
        time.sleep(1)
    print("  [WARN] Timeout 120s")
    return False

def close_dialog(page):
    page.evaluate("(() => { const d=[...document.querySelectorAll('.el-dialog__wrapper')]"
                  ".find(x=>x.getBoundingClientRect().width>0);"
                  "d?.querySelector('.el-dialog__headerbtn')?.click(); })()")

# ── 闭环验证 ──

def verify_sku(page, sku):
    """
    闭环验证: 搜索 SKU → 点进详情 → 查规格 tab 数据

    MCP 验证的选择器:
    - 搜索框: getByPlaceholder('搜索内容').first
    - SKU 链接: .vxe-body--row span.f_blue.pointer (或 getByText(sku))
    - 详情弹窗: el-dialog__wrapper.m-dialog, 标题"普通商品详情"
    - 规格tab: getByRole('tab', { name: '规格信息' })
    """
    page.wait_for_timeout(2000)

    # 1. 搜索 SKU
    search_box = page.get_by_placeholder('搜索内容').first
    search_box.click()
    search_box.fill('')
    search_box.fill(sku)
    page.keyboard.press('Enter')
    page.wait_for_timeout(3000)

    # 2. 确认找到
    total = page.evaluate(
        "() => { const p = document.querySelector('.el-pagination');"
        " return p?.textContent?.match(/共\\s*(\\d+)\\s*条/)?.[1] || '0'; }"
    )
    if total == '0':
        print(f"  [FAIL] SKU '{sku}' not found")
        return False
    print(f"  [OK] '{sku}' found ({total} results)")

    # 3. 点 SKU 链接打开详情弹窗
    page.locator(f'span:has-text("{sku}")').first.click()
    page.wait_for_timeout(2000)

    # 4. 点规格信息 tab
    page.get_by_role('tab', name='规格信息').click()
    page.wait_for_timeout(1000)

    # 5. 从弹窗文本提取规格数据
    spec_text = page.evaluate("""
      (() => { const dialogs = [...document.querySelectorAll('.el-dialog__wrapper')]
        .filter(d => d.getBoundingClientRect().width > 200);
        return dialogs[0]?.innerText || ''; })()
    """)
    import re
    patterns = {
        'spec_l': r'商品规格\s*\n\s*(\d+)\s*\*',
        'spec_w': r'商品规格\s*\n\s*\d+\s*\*\s*(\d+)\s*\*',
        'spec_h': r'商品规格\s*\n\s*\d+\s*\*\s*\d+\s*\*\s*(\d+)\s*cm',
        'weight_g': r'商品重量\s*\n\s*([\d.]+)g',
        'weight_kg': r'商品重量[\s\S]*?\n\s*([\d.]+)kg',
    }
    result = {}
    for key, pat in patterns.items():
        m = re.search(pat, spec_text)
        result[key] = m.group(1) if m else 'N/A'

    print(f"    spec: {result.get('spec_l')}x{result.get('spec_w')}x{result.get('spec_h')} cm")
    print(f"    weight: {result.get('weight_g')}g = {result.get('weight_kg')}kg")
    ok = (result.get('spec_l')=='62' and result.get('spec_w')=='52'
      and result.get('spec_h')=='47' and result.get('weight_kg')=='2.8')
    print(f"  => {'ALL MATCH' if ok else 'MISMATCH'}")

    return True


# ── main ──

def main():
    DOWNLOADS_DIR.mkdir(exist_ok=True)

    # 测试数据 — 每次改数字以验证真正更新
    test_data = [
        62, 52, 47,         # 规格长/宽/高(cm) — 改过
        2.8, 'kg',          # 重量 + 单位 — 改过
        68, 58, 52,         # 箱规 — 改过
        14.8, 6,            # 单箱重量(kg) + 数量 — 改过
        17, 14, 3,          # 包装规格 — 改过
        0.24, 'kg'          # 包装重量 + 单位 — 改过
    ]
    ts = datetime.now().strftime("%H%M%S")
    file_path = DOWNLOADS_DIR / f"import_{SKU}_{ts}.xlsx"

    print("[1] Generate Excel (pd.DataFrame, no template)")
    make_import_excel(SKU, test_data, file_path)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False, accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[2] Login check...")
        page.goto(PAGE_URL, timeout=60000)
        page.wait_for_timeout(5000)
        if is_logged_in(page):
            print("     Already logged in")
        else:
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                ctx.close(); sys.exit(1)
            page.goto(PAGE_URL, timeout=60000)
            page.wait_for_timeout(8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        print("[3] Upload & Import")
        ok = do_import(page, file_path)
        close_dialog(page)

        print("[4] Verify (closed loop)")
        page.goto(PAGE_URL, timeout=60000)
        page.wait_for_timeout(5000)
        page.keyboard.press("Escape")
        verify_sku(page, SKU)
        ctx.close()

    print("\nDone — closed loop completed")

if __name__ == "__main__":
    main()
