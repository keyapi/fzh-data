#!/usr/bin/env python3
"""
赛狐商品列表 — 下载导入更新商品模板

MCP 探索验证过的操作流程：
  1. 打开商品列表页（免登录）
  2. 点击"导入"下拉 → 选"导入更新商品"
  3. 弹窗中滚动到"规格信息"，勾选它（自动勾选 7 个子项）
  4. 点击"下载商品模板"
  5. 读取下载的 Excel 模板内容

用法:
  uv run python commodity_import_template.py

关键踩坑:
  Excel 生成必须用 pd.DataFrame() 直接构造（只取表头列名），
  不能用 pd.read_excel(模板) 再改——模板有隐藏 sheet/格式会导致导入失败。
"""

import time, json, requests, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from datetime import datetime
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"
DOWNLOADS_DIR = WEB_ROOT / "downloads"

LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/commodity/index.html"


def is_logged_in(page):
    url = page.url
    if "login" in url or url.rstrip("/") == "https://www.sellfox.com":
        return False
    try:
        return page.locator("text=克勇").first.is_visible()
    except:
        return False


def wait_for_login(page):
    print("请手动登录（最长 300s）...")
    for i in range(0, 300, 2):
        time.sleep(2)
        url = page.url
        if "login" not in url and "sellfox" in url:
            print("  检测到登录成功！")
            return True
        try:
            if page.locator("text=克勇").first.is_visible():
                print("  检测到登录成功！")
                return True
        except:
            pass
    return False


def get_template_via_api(cookies):
    """通过 API 直接下载模板（更稳定，不依赖下载事件）"""
    fields = "sku,size,originalWeight,cartonRule,cartonWeight,cartonNum,wrapSize,wrapWeight"
    session = requests.Session()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="www.sellfox.com")

    r = session.post(
        "https://www.sellfox.com/api/commodity/exportTemplate.json",
        data=f"fields={requests.utils.quote(fields)}",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    if r.status_code != 200 or r.json().get("code") != 0:
        print(f"  [失败] API 错误: {r.text[:200]}")
        return None

    url = r.json()["data"]
    r2 = requests.get(url)
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    path = DOWNLOADS_DIR / f"商品导入模板_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    path.write_bytes(r2.content)
    return path


def read_template(path):
    """读取下载的 Excel 模板"""
    import pandas as pd
    df = pd.read_excel(path)
    print(f"\n模板内容: {len(df)} 行 × {len(df.columns)} 列")
    print(f"列名: {list(df.columns)}")
    if len(df) > 0:
        print(f"第1行示例: {dict(df.iloc[0])}")
    return df


def main():
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    first_run = not PROFILE_DIR.exists()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        # ─── 1. 登录 ───────────────────────────────────
        page.goto(PAGE_URL, timeout=60000)
        page.wait_for_timeout(5000)

        if is_logged_in(page):
            print("[1/6] 已登录，跳过登录步骤")
        else:
            print("[1/6] 未登录 → 跳转登录页")
            page.goto(LOGIN_URL, timeout=30000)
            if not wait_for_login(page):
                context.close()
                return

        # 回到商品列表页
        page.goto(PAGE_URL, timeout=60000)
        page.wait_for_timeout(8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ─── 2. 点击导入下拉 ──────────────────────────
        print("[2/6] 点击导入下拉菜单...")
        # 导入按钮是 el-button.el-dropdown，用 evaluate 找到并点击（MCP 验证）
        page.evaluate("""
          (() => { const btns = [...document.querySelectorAll('button')];
            const b = btns.find(x => x.textContent.trim() === '导入');
            if (b) b.click(); })()
        """)
        page.wait_for_timeout(800)

        # ─── 3. 选择"导入更新商品" ────────────────────
        print("[3/6] 选择 导入更新商品...")
        # 先确认下拉菜单展开了
        page.wait_for_timeout(500)
        item_found = page.evaluate("""
          (() => { const items = document.querySelectorAll('.el-dropdown-menu__item');
            const target = [...items].find(i => i.textContent.trim() === '导入更新商品');
            if (target) { target.click(); return true; }
            return false; })()
        """)
        page.wait_for_timeout(3000)  # 等弹窗动画

        # 确认弹窗打开
        page.wait_for_timeout(500)
        title_visible = page.evaluate("""
          (() => { const t = document.querySelector('.el-dialog__title');
            return t && t.textContent.includes('导入更新商品'); })()
        """)
        if title_visible:
            print("  弹窗: 导入更新商品")
        else:
            print("  [警告] 弹窗未检测到，尝试继续...")

        # ─── 4. 滚动 + 勾选"规格信息" ──────────────────
        print("[4/6] 滚动到规格信息并勾选...")

        # 滚动弹窗 body
        page.evaluate("""
          (() => { const body = document.querySelector('.el-dialog__body');
            if (body) { body.scrollTop = body.scrollHeight; } })()
        """)
        page.wait_for_timeout(500)

        # 勾选"规格信息" — MCP 验证：必须 Playwright 真实点击整个 el-checkbox 组件
        # 先用 evaluate 检查是否存在，再 Playwright 点击
        exists = page.evaluate("""
          (() => { const cb = [...document.querySelectorAll('.el-checkbox')].find(
            c => c.querySelector('.el-checkbox__label')?.textContent?.trim() === '规格信息');
            return !!cb; })()
        """)
        if exists:
            page.locator(
                '.el-dialog__body .el-checkbox:has(.el-checkbox__label:text-is("规格信息"))'
            ).click(timeout=3000)
            page.wait_for_timeout(500)
        else:
            print("  [警告] 未找到规格信息 checkbox")

        # 验证勾选
        is_checked = page.evaluate("""
          (() => { const cb = [...document.querySelectorAll('.el-checkbox')].find(
            c => c.querySelector('.el-checkbox__label')?.textContent?.trim() === '规格信息');
            return cb ? cb.classList.contains('is-checked') : false; })()
        """)
        if is_checked:
            print("  [OK] 规格信息已勾选")
        else:
            print("  [警告] 规格信息未成功勾选")
            # 再试一次
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            spec_checkbox.click()
            page.wait_for_timeout(500)

        # ─── 5. 获取 cookie 用于 API 下载 ────────────
        print("[5/6] 下载商品模板...")
        cookies = {c["name"]: c["value"]
                   for c in context.cookies() if "sellfox" in c.get("domain", "")}

        path = get_template_via_api(cookies)
        if not path:
            print("  [备用方案] 通过浏览器下载...")
            # 备用：点击"下载商品模板"按钮
            dl_btn = page.get_by_role("button", name="下载商品模板").first
            with page.expect_download(timeout=30000) as dl_info:
                page.evaluate("""
                  (() => { const btns = [...document.querySelectorAll('button')];
                    const b = btns.find(x => x.textContent.trim() === '下载商品模板' && x.offsetParent);
                    if (b) b.click(); })()
                """)
            download = dl_info.value
            suggested = download.suggested_filename
            path = DOWNLOADS_DIR / suggested
            download.save_as(str(path))
        print(f"  模板已下载: {path} ({path.stat().st_size / 1024:.0f} KB)")

        context.close()

    # ─── 6. 读取模板 ────────────────────────────────
    print("[6/6] 读取模板内容...")
    read_template(path)
    print("\n完成！")


def create_import_excel(sku, spec_data, output_path):
    """
    创建赛狐导入 Excel — 只取表头，用 DataFrame 直接构造

    ⚠️ 关键: 不能 pd.read_excel(模板) 再改——模板有隐藏 sheet/格式！
    已验证: 弹窗显示"成功1条，失败0条"
    """
    columns = [
        "*SKU",
        "商品规格长(cm)", "商品规格宽(cm)", "商品规格高(cm)",
        "商品重量", "商品重量单位",
        "箱规长(cm)", "箱规宽(cm)", "箱规高(cm)",
        "单箱重量(kg)", "单箱数量(PCS)",
        "商品包装规格长(cm)", "商品包装规格宽(cm)", "商品包装规格高(cm)",
        "商品包装重量", "商品包装重量单位",
    ]
    row = [sku, *spec_data] if len(spec_data) == len(columns) - 1 else [sku] + spec_data[:15]
    df = pd.DataFrame([row], columns=columns)
    df.to_excel(output_path, index=False)
    print(f"导入文件已生成: {output_path}")
    return output_path


if __name__ == "__main__":
    main()
