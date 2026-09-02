#!/usr/bin/env python3
"""
赛狐库存明细自动导出（演示 + API 双模式）

用法:
  uv run python sellfox_auto_export.py            # 浏览器演示模式（可见点击）
  uv run python sellfox_auto_export.py --api       # API 模式（请求直接调 API）
  uv run python sellfox_auto_export.py --headless  # 浏览器无头模式（后台运行）
  uv run python sellfox_auto_export.py --auto-login  # ddddocr 自动登录（首次/cookie过期）
  uv run python sellfox_auto_export.py --fresh     # 强制重新登录
  uv run python sellfox_auto_export.py --demo-search  # 演示搜索切换 (SKU/品名/精/模)
  uv run python sellfox_auto_export.py --export-cookies  # 导出 cookies 供 API 使用

两种模式对比:
  | 浏览器模式 | 打开可见浏览器，能看到每一步点击          | 适合演示、调试 |
  | API 模式   | 直接调 HTTP API，速度快 10x，不依赖 DOM  | 适合批量生产    |

输出目录:
  downloads/    原始下载的 Excel
  output/       合并后的文件
  sellfox-profile/  持久化登录会话 (gitignore)
"""

import subprocess, sys, time, shutil, json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"
DOWNLOADS_DIR = WEB_ROOT / "downloads"
OUTPUT_DIR = WEB_ROOT / "output"
LOGIN_TIMEOUT = 300

LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/detailed/index.html"
REPORT_URL = "https://www.sellfox.com/amzup-web-main/amzup-web-vue3?amzup-web-vue3=%2Fvue3%2Fweb%2Fv3%2Freport-center%2Findex.html"

EXPORT_API = "https://www.sellfox.com/api/warehouseManage/warehouseItem-export.json"
TASK_LIST_API = "https://www.sellfox.com/api/report/center/task/pageList.json"
DOWNLOAD_API = "https://www.sellfox.com/api/report/center/task/download.json"
PAGE_LIST_API = "https://www.sellfox.com/api/gw/sellfox/sellfox-warehouse/sellfox/warehouse/item/warehouseItemPageList"
PAGE_COUNT_API = "https://www.sellfox.com/api/gw/sellfox/sellfox-warehouse/sellfox/warehouse/item/warehouseItemPageCount"

HEAD_FIELD_API = "https://www.sellfox.com/api/excel/getHeadField.json"


# ─── 工具函数 ───────────────────────────────────────────────

def is_logged_in(page):
    """MCP 实测: 登录后 URL 不再含 'login'，且 stock 页有导出图标"""
    url = page.url
    if "login" in url:
        return False
    try:
        return page.locator(".icon_sf_download").first.is_visible()
    except:
        return "login" not in url  # fallback: URL 变了就算已登录


def wait_for_login(page):
    """MCP 实测: 双重检测 — URL 离开 login + 页面出现用户元素"""
    print(f"\n请在浏览器中登录赛狐（最长等待 {LOGIN_TIMEOUT}s）...")
    print("  登录页: 输入用户名/密码/验证码 → 拼图滑块 → 点登录")
    print("  登录成功后会自动检测并跳转到库存明细页")
    for i in range(0, LOGIN_TIMEOUT, 2):
        time.sleep(2)
        url = page.url
        # 检测1: URL 不再含 login（登录成功后跳转到 dashboard 或其他页）
        if "login" not in url and url != "about:blank" and "sellfox" in url:
            print(f"✓ 检测到登录成功！(跳转到 {url.split('/')[-1].split('?')[0] or 'dashboard'})")
            page.wait_for_timeout(1000)
            return True
        # 检测2: 页面出现用户菜单（可能 AJAX 登录没有跳转）
        try:
            if page.locator('text=克勇').first.is_visible():
                print("✓ 检测到登录成功！(用户菜单可见)")
                return True
        except:
            pass
        if i % 20 == 0 and i > 0:
            print(f"  等待登录中... ({i}/{LOGIN_TIMEOUT}s)")
    return False


def ensure_page_ready(page):
    """等待页面 JS 渲染完成，关闭残留弹窗"""
    page.wait_for_timeout(5000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)


# ─── 搜索切换（MCP 验证的选择器）─────────────────────────────

def get_search_type(page):
    """读取当前搜索类型 — 通过 value 属性而非位置"""
    return page.evaluate("""
      (() => { const inputs = document.querySelectorAll('input.el-input__inner');
        for (const inp of inputs) {
          const v = inp.value; if (!v) continue;
          if (['SKU','识别码','品名','型号','FNSKU','SPU','款名','MSKU'].includes(v))
            return v;
        }
        return '?'; })()
    """)


def get_search_mode(page):
    """读取当前搜索模式: 'fuzzy' | 'exact'"""
    return page.evaluate("() => document.querySelector('.icon_sf_fuzzy') ? 'fuzzy' : 'exact'")


def switch_search_type(page, target):
    """切换搜索类型: SKU / 品名 / 识别码 / 型号 / FNSKU / SPU / 款名 / MSKU"""
    current = get_search_type(page)
    if current == target:
        print(f"      搜索类型已是 {target}")
        return

    print(f"      切换: {current} → {target}")
    # 先关掉任何残留弹窗
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    # evaluate 点击 el-select（绕过 Playwright visible check）
    page.evaluate("""
      (() => { const inputs = document.querySelectorAll('input.el-input__inner');
        for (const inp of inputs) {
          if (inp.value === 'SKU' || inp.value === '识别码' || inp.value === '品名'
           || inp.value === '型号' || inp.value === 'FNSKU' || inp.value === 'SPU'
           || inp.value === '款名' || inp.value === 'MSKU') {
            const sel = inp.closest('.el-select');
            if (sel) { sel.click(); return; }
          }
        }
      })()
    """)
    page.wait_for_timeout(500)
    # click 可见的下拉选项
    page.evaluate(f"""
      (() => {{ const items = [...document.querySelectorAll('.el-select-dropdown__item')]
        .filter(i => i.getBoundingClientRect().width > 0);
        const m = items.find(i => i.textContent.trim() === '{target}');
        if (m) m.click(); }})()
    """)
    page.wait_for_timeout(500)
    print(f"      结果: {get_search_type(page)}")


def toggle_search_mode(page, target):
    """切换搜索模式: exact(精) / fuzzy(模)"""
    current = get_search_mode(page)
    if current == target:
        print(f"      搜索模式已是 {target}")
        return
    print(f"      切换: {current} → {target}")
    page.locator(".search_type_btn").first.click()
    page.wait_for_timeout(300)
    print(f"      结果: {get_search_mode(page)}")


def search_keyword(page, keyword):
    """在搜索框输入关键词并回车"""
    inp = page.locator("input[placeholder='双击可批量搜索内容'], input[placeholder='搜索内容']").first
    inp.click()
    inp.fill("")
    inp.fill(keyword)
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)


def get_result_count(page):
    """读取搜索结果总数"""
    text = page.evaluate("() => { const p = document.querySelector('.el-pagination'); return p ? p.textContent.trim() : '0条'; }")
    # "共 XXXX 条..." 提取数字
    import re
    m = re.search(r'共\s*(\d+)\s*条', text)
    return int(m.group(1)) if m else 0


def demo_search_switching(page):
    """演示搜索切换: SKU模糊 → SKU精确 → 品名模糊"""
    print("\n" + "=" * 50)
    print("搜索切换演示（MCP 验证的选择器）")
    print("=" * 50)

    keyword = "KS0001"

    # Test 1: SKU + 模糊
    print(f"\n[测试1] SKU + 模糊搜索: {keyword}")
    switch_search_type(page, "SKU")
    toggle_search_mode(page, "fuzzy")
    search_keyword(page, keyword)
    count = get_result_count(page)
    print(f"  → 结果: {count} 条（模糊匹配 KS0001-xxx-xxx）")

    # Test 2: SKU + 精确
    print(f"\n[测试2] SKU + 精确搜索: {keyword}")
    toggle_search_mode(page, "exact")
    search_keyword(page, keyword)
    count = get_result_count(page)
    print(f"  → 结果: {count} 条（精确匹配，不存在恰好叫 KS0001 的 SKU）")

    # Test 3: 品名 + 模糊
    keyword2 = "三角靠枕"
    print(f"\n[测试3] 品名 + 模糊搜索: {keyword2}")
    switch_search_type(page, "品名")
    toggle_search_mode(page, "fuzzy")
    search_keyword(page, keyword2)
    count = get_result_count(page)
    print(f"  → 结果: {count} 条（品名含'三角靠枕'的全部 SKU）")

    print("\n" + "=" * 50)


# ─── 浏览器模式 ─────────────────────────────────────────────

def browser_export_flow(page):
    """MCP 实测: 点击导出图标 → 弹窗确定 → 等通知 → 立即下载"""
    # 1. 点击导出图标 (同 MCP: browser_click .icon_sf_download)
    print("  1. 点击导出图标...")
    page.locator(".icon_sf_download.f_18").first.click()
    page.wait_for_timeout(2000)

    # 2. 弹窗出现 → 点击确定（MCP: getByRole last + browser_evaluate click）
    print("  2. 弹窗出现 → 点确定（导出 44 字段）")
    page.evaluate("""(() => { const btns = document.querySelectorAll('.el-dialog__footer button, .dcm button');
      const ok = [...btns].find(b => b.textContent.trim() === '确定' && b.offsetParent);
      if (ok) ok.click(); })()""")
    page.wait_for_timeout(3000)

    # 3. 等待后台生成 → 通知出现 → 立即下载 (同 MCP)
    for _ in range(60):
        try:
            dl_btn = page.locator('button:has-text("立即下载")')
            if dl_btn.count() > 0:
                print("  3. 文件已生成 → 点击立即下载")
                # MCP: waitForEvent('download') + click 立即下载
                with page.expect_download(timeout=30000) as dl_info:
                    page.evaluate("""(() => { const btns = document.querySelectorAll('button');
                      const dl = [...btns].find(b => b.textContent.includes('立即下载'));
                      if (dl) dl.click(); })()""")
                download = dl_info.value
                suggested = download.suggested_filename
                target = DOWNLOADS_DIR / suggested
                download.save_as(str(target))
                print(f"  4. 下载完成: {suggested} ({target.stat().st_size / 1024:.0f} KB)")
                return target
        except:
            pass
        time.sleep(2)

    print("  [失败] 导出超时（文件未在 120s 内生成）")
    return None


def run_browser(headless=False, demo_search=False, auto_login=False):
    """浏览器模式：先登录页 → 用户登录 → 仓库页 → 导出。MCP 实测流程。"""
    first_run = not PROFILE_DIR.exists()
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        print(f"[启动] 浏览器持久化目录: {PROFILE_DIR}")
        print(f"[启动] {'首次运行' if first_run else '已有会话(免登录)'}")

        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Step 1: 先到仓库页，看是否需要登录
        print("[1/4] 导航到库存明细页...")
        page.goto(PAGE_URL, timeout=60000)
        page.wait_for_timeout(5000)
        print(f"      当前URL: {page.url[:80]}")

        if is_logged_in(page):
            print("[OK] 已登录，跳过登录步骤\n")
        elif auto_login:
            print("[信息] 尝试 ddddocr 自动登录...")
            try:
                from sellfox_login_ocr import login as auto_login_fn
                if auto_login_fn(page):
                    print("[OK] ddddocr 自动登录成功")
                else:
                    print("[信息] 自动登录失败，切换到手动登录...")
                    if not wait_for_login(page):
                        context.close()
                        return False
            except ImportError:
                print("[信息] ddddocr 未安装，切换到手动登录...")
                print("[提示] 安装后可自动登录: uv add ddddocr onnxruntime")
                if not wait_for_login(page):
                    context.close()
                    return False
        else:
            print(f"[!] 未登录 (URL={page.url[:60]}) → 打开登录页")
            page.goto(LOGIN_URL, timeout=30000)
            print(f"      登录页已打开，请登录...")
            if not wait_for_login(page):
                context.close()
                return False
            print(f"    cookie 已自动保存 → 下次免登录！")

        # Step 2: 确保在仓库页（登录后可能停在 dashboard）
        current = page.url
        if "detailed" not in current:
            print(f"[2/4] 当前在 dashboard → 跳转库存明细页...")
            page.goto(PAGE_URL, timeout=60000)
        else:
            print(f"[2/4] 已在库存明细页")
        print(f"      URL: {page.url[:80]}")
        print(f"      URL: {page.url[:80]}")
        print(f"      等待 SPA 渲染 (8s)...")
        page.wait_for_timeout(8000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        print(f"      渲染完成")

        # 如果只是演示搜索切换，不走导出
        if demo_search:
            demo_search_switching(page)
            context.close()
            return True

        # 确保导出全部库存（含零库存）：取消"隐藏0数据记录"勾选
        print("[2.5] 检测隐藏0数据状态...")
        total = int(page.evaluate(
            "() => { const p = document.querySelector('.el-pagination');"
            " return p ? (p.textContent.match(/共\\s*(\\d+)\\s*条/) || ['','0'])[1] : '0'; }"
        ))
        print(f"      当前共 {total} 条")
        if total < 2000:
            print(f"      隐藏0数据已勾选 → 取消勾选（导出全部库存）")
            page.locator('span:text-is("隐藏0数据记录")').first.click()
            page.wait_for_timeout(3000)
            total_after = int(page.evaluate(
                "() => { const p = document.querySelector('.el-pagination');"
                " return p ? (p.textContent.match(/共\\s*(\\d+)\\s*条/) || ['','0'])[1] : '0'; }"
            ))
            print(f"      更新后共 {total_after} 条")

        # Step 3: 导出
        print("[3/4] 开始导出...")
        result = browser_export_flow(page)

        context.close()

        if result:
            print(f"[4/4] 完成! 文件: {result}")
        return bool(result)


# ─── API 模式 ───────────────────────────────────────────────

def get_api_cookies():
    """从 sellfox-profile 提取 cookies 用于 API 调用"""
    if not PROFILE_DIR.exists():
        print("sellfox-profile/ 不存在，请先用浏览器模式登录一次")
        return None

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
        )
        cookies = context.cookies()
        context.close()

    sellfox_cookies = [c for c in cookies if "sellfox" in c.get("domain", "")]
    if not sellfox_cookies:
        print("未找到 sellfox cookies，请先用浏览器模式登录")
        return None

    result = {}
    for c in sellfox_cookies:
        result[c["name"]] = c["value"]

    print(f"提取到 {len(result)} 个 sellfox cookies")
    return result


def api_export_flow(cookies):
    """通过 HTTP API 完成导出（不打开浏览器）"""
    import requests

    ts = datetime.now().strftime("%Y-%m-%d")
    session = requests.Session()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="www.sellfox.com")

    # Step 1: 使用已知的 44 个默认导出字段（MCP 探索验证）
    print("  1. 使用默认 44 个导出字段...")
    fields = [
        "commodityName","commoditySku","fnSku","mskuList","spu","spuName",
        "identificationCode","brandName","fullName","stateName",
        "commodityAttr","commodityAttrCn","model","platform","shopName",
        "shopNames","country","warehouse","productDevNames","commodityDevName",
        "shelfInfos","cartonQty","cartonNum","stockPlan","stockWait",
        "stockInspect","waitUpShelfNum","stockProcessing","stockOccupyAll",
        "stockAvailable","expectedAvailableQuantity","stockDefective",
        "stockAllNum","safeStock","perPurchase","perFee","perInventoryCost",
        "onWayPurchase","onWayFee","totalOnWayCostStock","totalPurchase",
        "totalFee","inventoryCost","totalCostStockSum","updateTime"
    ]
    print(f"     {len(fields)} 个字段")

    # Step 2: 触发导出
    print("  2. 触发异步导出...")
    export_body = {
        "orderField": "", "orderValue": "", "warehouseIds": "",
        "fullCid": "", "commodityAttrValueIds": "", "isExclusive": "",
        "attributeValue": None, "labelQuery": 0, "labelIdList": [],
        "searchType": "fuzzy", "searchField": "", "searchValue": "",
        "productDevIds": "", "commodityDevIds": "", "tableType": "1",
        "commodityCategories": "", "brandIds": [], "state": "",
        "shopInfoList": [], "includeList": fields, "isHidden": False,
        "dangerStock": False, "pageNo": 1, "pageSize": 20,
    }
    r = session.post(EXPORT_API, json=export_body,
                     headers={"content-type": "application/json"})
    if r.json().get("code") != 0:
        print(f"  [失败] {r.json()}")
        return None
    print(f"     OK")

    # Step 3: 轮询任务列表
    print("  3. 等待后台生成文件...")
    task_id = None
    for attempt in range(60):
        r = session.post(TASK_LIST_API, json={
            "status": "", "dateType": "createTime", "reportName": "",
            "createTimeStart": ts, "createTimeEnd": ts,
            "pageSize": 5, "pageNo": 1, "tabs": 1,
        })
        tasks = r.json().get("data", {}).get("rows", [])
        for t in tasks:
            if "仓库" in t.get("module", "") and t.get("status") == "COMPLETE":
                task_id = t["id"]
                break
        if task_id:
            print(f"     taskId={task_id}, 耗时 ~{attempt * 2}s")
            break
        time.sleep(2)

    if not task_id:
        print("  [失败] 任务未完成")
        return None

    # Step 4: 下载
    print("  4. 获取下载链接...")
    r = session.post(DOWNLOAD_API, json={"ids": [task_id]})
    cos_url = r.json().get("data", [None])[0]
    if not cos_url:
        print("  [失败] 无下载链接")
        return None

    print("  5. 下载文件...")
    r = requests.get(cos_url)
    filename = f"WarehouseItem_{ts}.xlsx"
    output_path = DOWNLOADS_DIR / filename
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    output_path.write_bytes(r.content)
    print(f"  [OK] {filename} ({len(r.content) / 1024:.0f} KB)")
    return output_path


def run_api():
    """API 模式：不打开浏览器"""
    cookies = get_api_cookies()
    if not cookies:
        print("请先用浏览器模式登录: uv run python sellfox_auto_export.py")
        return False

    print("API 模式：直接调接口...")
    result = api_export_flow(cookies)
    if result:
        print(f"\n文件: {result}")
    return bool(result)


# ─── Cookie 导出 ────────────────────────────────────────────

def export_cookies_cmd():
    """导出 sellfox cookies 为 JSON"""
    cookies = get_api_cookies()
    if not cookies:
        return

    out_path = WEB_ROOT / "sellfox_cookies.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)
    print(f"已导出 {len(cookies)} 个 cookie → {out_path}")


# ─── 主入口 ─────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if "--export-cookies" in args:
        export_cookies_cmd()
        return

    if "--demo-search" in args:
        run_browser(headless=False, demo_search=True)
        return

    fresh = "--fresh" in args
    auto_login = "--auto-login" in args
    use_api = "--api" in args
    headless = "--headless" in args

    if fresh and PROFILE_DIR.exists():
        print("--fresh: 清除旧登录会话...")
        shutil.rmtree(PROFILE_DIR)

    if use_api:
        print("=" * 50)
        print("赛狐库存导出 — API 模式")
        print("=" * 50)
        success = run_api()
    else:
        print("=" * 50)
        mode = "无头" if headless else "演示"
        print(f"赛狐库存导出 — 浏览器{mode}模式")
        print("=" * 50)
        success = run_browser(headless=headless, auto_login=auto_login)

    if success:
        print("\n完成！")
    else:
        print("\n失败，请检查日志。")
        sys.exit(1)


if __name__ == "__main__":
    main()
