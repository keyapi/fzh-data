#!/usr/bin/env python3
"""
sellfox_restock_api.py
赛狐 海外仓备货单 — API E2E（导入→配货→发货→收货）

用法:
  uv run python sellfox_restock_api.py                           # 默认 --sku=test001-white
  uv run python sellfox_restock_api.py --sku=KS0001-white        # 自定义 SKU
  uv run python sellfox_restock_api.py --headless                # 无头模式
  uv run python sellfox_restock_api.py --import-only             # 仅导入（不配货/发货/收货）
  uv run python sellfox_restock_api.py --dry-run                 # 验证 cookie + API 连通性
  uv run python sellfox_restock_api.py --fresh                   # 强制重新登录

流程:
  生成Excel → 上传导入 → 轮询获取 pickIds → 分配库存 → 发货 → 收货 → 验证

API 端点 (MCP 抓取确认):
  POST /api/v1/excel/import.json          导入 Excel (multipart)
  POST /api/oversea/page.json             列表查询 (含 items 子行)
  POST /api/oversea/allotStock.json       分配库存 ([pickIds])
  POST /api/oversea/batchConfirmShip.json 批量发货 ({"ids": [...]})
  POST /api/oversea/batch/receiveList.json 收货-提交
  POST /api/oversea/batch/receive.json    收货-确认
  GET  /api/oversea/stat.json             侧边栏状态统计
"""

import sys
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import requests
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"
GEN_SCRIPT = WEB_ROOT.parent / "warehouse_restock" / "build_saihu_warehouse_restock.py"

API_BASE = "https://www.sellfox.com/api"
PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/stockOrder/index.html"

# ── Cookie 提取 (复刻 sellfox_auto_export.py) ────────────

def get_api_cookies(headless: bool = True) -> dict | None:
    """从 sellfox-profile 提取 cookies。"""
    if not PROFILE_DIR.exists():
        print(f"✗ Profile 不存在: {PROFILE_DIR}")
        return None
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR), headless=headless)
            cookies = context.cookies()
            context.close()
        sellfox_cookies = {c["name"]: c["value"] for c in cookies
                          if "sellfox" in c.get("domain", "")}
        if not sellfox_cookies:
            print("✗ 未找到 sellfox cookies，请先登录")
            return None
        print(f"  Cookies: {len(sellfox_cookies)} 个")
        return sellfox_cookies
    except Exception as e:
        print(f"✗ 提取 cookies 失败: {e}")
        return None


def build_session(cookies: dict) -> requests.Session:
    """构建带 cookies 的 requests Session。"""
    s = requests.Session()
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".sellfox.com")
    s.headers.update({
        "accept": "application/json",
        "user-agent": "sellfox-api/1.0",
    })
    return s


def api_post(session, path: str, json_data=None, files=None) -> dict:
    """POST API 调用，自动处理错误。"""
    url = f"{API_BASE}{path}"
    kwargs = {}
    if json_data is not None:
        kwargs["json"] = json_data
    if files is not None:
        kwargs["files"] = files
    resp = session.post(url, **kwargs)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"API {path} 返回错误: {data.get('msg', data)}")
    return data


def api_get(session, path: str) -> dict:
    """GET API 调用。"""
    resp = session.get(f"{API_BASE}{path}")
    resp.raise_for_status()
    return resp.json()

# ── 状态映射 ──────────────────────────────────────────────

STATUS_NAMES: dict[int, str] = {}  # 首次调用 stat.json 后填充

def load_status_map(session) -> dict[int, str]:
    """从 stat.json 获取状态码→名称映射。"""
    global STATUS_NAMES
    if STATUS_NAMES:
        return STATUS_NAMES
    data = api_get(session, "/oversea/stat.json")
    for entry in data.get("data", data):
        STATUS_NAMES[entry["status"]] = entry["statusName"]
    print(f"  状态映射: {STATUS_NAMES}")
    return STATUS_NAMES

# ── 步骤 1: 生成 Excel ───────────────────────────────────

def generate_excel(sku: str) -> Path | None:
    """调用 build_saihu_warehouse_restock.py 生成 Excel。返回第一个生成的文件路径。"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*50}")
    print(f"Step 1: 生成 Excel (SKU={sku})")
    print(f"{'='*50}")

    result = subprocess.run(
        [sys.executable, str(GEN_SCRIPT), f"--sku={sku}", "--fmt=2"],
        cwd=str(GEN_SCRIPT.parent),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"✗ 生成失败:\n{result.stderr[:500]}")
        return None

    # 找最新 out 目录
    out_base = GEN_SCRIPT.parent / "out"
    out_dirs = sorted([d for d in out_base.iterdir() if d.is_dir()], reverse=True)
    if not out_dirs:
        print("✗ 未找到输出目录")
        return None

    # 返回第一个 fmt=2 的 xlsx
    files = list(out_dirs[0].glob("*_2加工并入采购.xlsx"))
    if files:
        print(f"  ✓ 生成: {files[0].name}")
        return files[0]

    # fallback: 任意 xlsx
    files = list(out_dirs[0].glob("*.xlsx"))
    if files:
        print(f"  ✓ 生成: {files[0].name}")
        return files[0]

    print("✗ 未找到生成的 xlsx 文件")
    return None

# ── 步骤 2: 导入 ─────────────────────────────────────────

def import_excel_playwright(filepath: Path, headless: bool = True) -> bool:
    """通过 Playwright 浏览器上传 Excel 导入（需要 el-upload 的 sf-vvv-i 头）。

    赛狐的导入 API (/api/v1/excel/import.json) 需要 sf-vvv-i / sf-vvv-t CSRF 头，
    这些头由前端 el-upload 组件动态生成，无法在纯 requests 中复现。
    因此导入步骤保留 Playwright 浏览器操作。
    """
    print(f"\n{'='*50}")
    print(f"Step 2: 导入 Excel (Playwright)")
    print(f"{'='*50}")
    print(f"  文件: {filepath.name}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=headless)
        page = context.pages[0] if context.pages else context.new_page()

        # SPA warmup
        page.goto("https://www.sellfox.com/amzup-web-main/web/warehouse/detailed/index.html",
                  timeout=30000)
        page.wait_for_timeout(3000)
        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(5000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # 确保在"全部"tab
        page.evaluate("""
            (() => { for (const el of document.querySelectorAll('*')) {
              if (el.childNodes.length===1 && el.childNodes[0].nodeType===3 &&
                  el.textContent.trim()==='全部') {
                el.parentElement.click(); return; } } })()
        """)
        page.wait_for_timeout(2000)

        # 点「重置」清除过滤
        page.evaluate("""
            (() => { for (const el of document.querySelectorAll('*')) {
              if (el.textContent.trim()==='重置' && el.offsetWidth>0) {
                el.click(); return; } } })()
        """)
        page.wait_for_timeout(1000)

        # 打开导入对话框
        page.locator('button:has-text("添加单据")').click()
        page.wait_for_timeout(800)
        page.evaluate("""
            (() => {
                const items = document.querySelectorAll('.el-dropdown-menu__item');
                for (const item of items) {
                    if (item.textContent.includes('导入海外仓备货单') &&
                        item.offsetWidth > 0) { item.click(); return; }
                }
            })()
        """)
        page.wait_for_timeout(2000)

        # 上传文件
        page.locator('.el-dialog input[type="file"]').first.set_input_files(str(filepath))
        page.wait_for_timeout(1000)

        # 点「导入」按钮 (JS, 绕过 Playwright visible check)
        page.evaluate("""
            (() => {
                const dialogs = document.querySelectorAll('.el-dialog');
                for (const d of dialogs) {
                    if (d.offsetWidth > 0 && d.textContent.includes('导入')) {
                        const btns = d.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.textContent.trim()==='导入' && !btn.disabled) {
                                btn.click(); return 'clicked';
                            }
                        }
                    }
                }
                return 'not-found';
            })()
        """)

        # 等导入完成
        for _ in range(60):
            page.wait_for_timeout(2000)
            result = page.evaluate("""
                (() => {
                    const dialogs = document.querySelectorAll('.el-dialog');
                    for (const d of dialogs) {
                        if (d.offsetWidth > 0 && d.textContent.includes('导入完成')) {
                            const text = d.textContent;
                            const m1 = text.match(/成功(\\d+)条/);
                            const m2 = text.match(/失败(\\d+)条/);
                            return {done: true, success: m1?.[1]||'?', fail: m2?.[1]||'?'};
                        }
                    }
                    return {done: false};
                })()
            """)
            if result.get("done"):
                print(f"  ✓ 导入完成: 成功{result['success']}条, 失败{result['fail']}条")
                break
            if _ % 5 == 0:
                print(f"    等待导入... ({_*2}s)")

        # 关闭弹窗
        page.evaluate("""
            (() => {
                const dialogs = document.querySelectorAll('.el-dialog');
                for (const d of dialogs) {
                    if (d.offsetWidth > 0) {
                        const closeBtn = d.querySelector('.el-dialog__headerbtn');
                        if (closeBtn) closeBtn.click();
                    }
                }
            })()
        """)
        page.wait_for_timeout(500)

        context.close()

    return True


def wait_for_new_orders(session, baseline_ids: set[int], sku: str,
                        timeout: int = 120) -> list[dict]:
    """轮询 page.json 直到出现新订单。返回新订单列表（含 items）。"""
    print(f"\n  等待导入完成（最多 {timeout}s）...")
    for i in range(0, timeout, 2):
        time.sleep(2)
        data = api_post(session, "/oversea/page.json", json_data={
            "pageNo": 1, "pageSize": 50, "status": 0,
            "orderField": "createTime", "orderValue": "desc",
        })
        rows = data.get("data", {}).get("rows", [])
        new_orders = [r for r in rows if r["id"] not in baseline_ids]
        if new_orders:
            print(f"  ✓ 发现 {len(new_orders)} 个新订单 ({i}s)")
            return new_orders
        if i % 10 == 0 and i > 0:
            print(f"    等待中... ({i}s)")
    print(f"  ✗ 超时 ({timeout}s)")
    return []

# ── 步骤 3: 分配库存 ─────────────────────────────────────

def allocate_stock(session, pick_ids: list[int]) -> bool:
    """分配库存。"""
    print(f"\n{'='*50}")
    print(f"Step 3: 分配库存 ({len(pick_ids)} 单)")
    print(f"{'='*50}")

    data = api_post(session, "/oversea/allotStock.json", json_data=pick_ids)
    result = data.get("data", {})
    ok = result.get("success", 0)
    fail = result.get("fail", 0)
    print(f"  成功: {ok}, 失败: {fail}")
    return fail == 0

# ── 步骤 4: 发货 ─────────────────────────────────────────

def confirm_ship(session, pick_ids: list[int]) -> bool:
    """批量发货。"""
    print(f"\n{'='*50}")
    print(f"Step 4: 发货 ({len(pick_ids)} 单)")
    print(f"{'='*50}")

    data = api_post(session, "/oversea/batchConfirmShip.json",
                    json_data={"ids": pick_ids})
    result = data.get("data", {})
    ok = result.get("success", 0)
    fail = result.get("fail", 0)
    print(f"  成功: {ok}, 失败: {fail}")
    return fail == 0

# ── 步骤 5: 收货 ─────────────────────────────────────────

def get_pick_items(session, pick_ids: list[int]) -> list[dict]:
    """通过 page.json 获取订单的子项详情（含 arrivalQty）。"""
    # 逐个查询确保获取到所有 items
    all_items = []
    for pid in pick_ids:
        data = api_post(session, "/oversea/page.json", json_data={
            "pageNo": 1, "pageSize": 1,
            "searchValue": str(pid),
        })
        rows = data.get("data", {}).get("rows", [])
        if rows and rows[0].get("items"):
            all_items.append(rows[0])
    return all_items


def receive_orders(session, pick_ids: list[int]) -> bool:
    """两步骤收货。"""
    print(f"\n{'='*50}")
    print(f"Step 5: 收货 ({len(pick_ids)} 单)")
    print(f"{'='*50}")

    # 获取子项详情
    print("  获取子项详情...")
    orders = get_pick_items(session, pick_ids)
    if not orders:
        print("  ✗ 未获取到子项详情")
        return False

    # 构建 receiveList 请求体
    receive_data = []
    for order in orders:
        items = []
        for item in order.get("items", []):
            qty = item.get("quantity", 0)
            signed = item.get("signNum", 0)
            arrival = qty - signed
            if arrival > 0:
                items.append({
                    "id": item["id"],
                    "pickId": item["pickId"],
                    "commodityId": item.get("commodityId"),
                    "commoditySku": item.get("commoditySku"),
                    "quantity": qty,
                    "arrivalQty": arrival,
                    "signNum": signed,
                    "shopId": item.get("shopId", 0),
                    "shopName": item.get("shopName"),
                    "platform": item.get("platform", "OTHER"),
                    "platformName": item.get("platformName"),
                    "fnsku": item.get("fnsku", ""),
                    "exclusiveType": item.get("exclusiveType", 0),
                })
        if items:
            receive_data.append({
                "id": order["id"],
                "pickSn": order["pickSn"],
                "toWarehouse": order["toWarehouse"],
                "toName": order.get("toName", ""),
                "items": items,
            })

    if not receive_data:
        print("  ✗ 没有待收货的子项（arrivalQty 全为 0）")
        return False

    total_items = sum(len(o["items"]) for o in receive_data)
    print(f"  待收货子项: {total_items}")
    print(f"  receive data: {json.dumps(receive_data, ensure_ascii=False)[:500]}")

    # Step 5a: receiveList
    print("  提交 receiveList...")
    data1 = api_post(session, "/oversea/batch/receiveList.json",
                     json_data=receive_data)
    print(f"  ✓ receiveList OK")

    # Step 5b: receive confirm
    print("  确认 receive...")
    data2 = api_post(session, "/oversea/batch/receive.json",
                     json_data=receive_data)
    print(f"  ✓ receive OK")

    return True


def verify_status(session, pick_ids: list[int]) -> list[str]:
    """查询最终状态。"""
    print(f"\n{'='*50}")
    print("验证最终状态")
    print(f"{'='*50}")

    load_status_map(session)
    statuses = []
    for pid in pick_ids:
        data = api_post(session, "/oversea/page.json", json_data={
            "pageNo": 1, "pageSize": 1, "searchValue": str(pid),
        })
        rows = data.get("data", {}).get("rows", [])
        if rows:
            s = rows[0].get("status")
            sn = rows[0].get("pickSn")
            name = STATUS_NAMES.get(s, f"未知({s})")
            statuses.append(f"  {sn}: status={s} ({name})")
    for line in statuses:
        print(line)
    return statuses

# ── Main ─────────────────────────────────────────────────

def main():
    headless = "--headless" in sys.argv
    fresh = "--fresh" in sys.argv
    dry_run = "--dry-run" in sys.argv
    import_only = "--import-only" in sys.argv
    sku = "test001-white"

    for a in sys.argv[1:]:
        if a.startswith("--sku="):
            sku = a.split("=", 1)[1]
        elif a == "--sku":
            idx = sys.argv.index(a)
            if idx + 1 < len(sys.argv):
                sku = sys.argv[idx + 1]

    print(f"\n赛狐 海外仓备货单 — API E2E")
    print(f"SKU: {sku}")
    if dry_run:
        print("模式: dry-run (仅验证连通性)")

    # ── 获取 cookies ──
    print("\n[认证] 提取 cookies...")
    cookies = get_api_cookies(headless=headless or dry_run)
    if not cookies:
        return
    session = build_session(cookies)

    if dry_run:
        try:
            data = api_get(session, "/oversea/stat.json")
            print("✓ API 连通性正常")
            load_status_map(session)
        except Exception as e:
            print(f"✗ API 连通失败: {e}")
        return

    # ── Step 1: 生成 Excel ──
    xlsx_path = generate_excel(sku)
    if not xlsx_path:
        return

    # ── Step 2: 导入 ──
    # 获取导入前已有订单 ID（用于后续比对）
    existing_data = api_post(session, "/oversea/page.json", json_data={
        "pageNo": 1, "pageSize": 5, "status": 0,
        "orderField": "createTime", "orderValue": "desc",
    })
    baseline_ids = {r["id"] for r in existing_data.get("data", {}).get("rows", [])}
    print(f"  导入前已有 {len(baseline_ids)} 个待配货订单")

    task_id = import_excel_playwright(xlsx_path, headless=headless)
    if not task_id:  # Returns bool now
        print("  ⚠ 导入可能未完成")

    # 等新订单出现
    new_orders = wait_for_new_orders(session, baseline_ids, sku)
    if not new_orders:
        print("\n✗ 未检测到新订单（可能导入仍在处理中）")
        return

    pick_ids = [o["id"] for o in new_orders]
    pick_sns = [o["pickSn"] for o in new_orders]
    print(f"\n  新订单:")
    for o in new_orders:
        qty = sum(item.get("quantity", 0) for item in o.get("items", []))
        print(f"    {o['pickSn']} (pickId={o['id']}) 仓库={o.get('toName','?')} 数量={qty}")

    if import_only:
        print(f"\n导入完成 ({len(pick_ids)} 单)，--import-only 模式退出")
        return

    # ── Step 3: 分配库存 ──
    if not allocate_stock(session, pick_ids):
        print("\n⚠ 分配库存部分失败，继续后续步骤...")

    # ── Step 4: 发货 ──
    time.sleep(2)
    if not confirm_ship(session, pick_ids):
        print("\n⚠ 发货部分失败，继续后续步骤...")

    # ── Step 5: 收货 ──
    time.sleep(2)
    if not receive_orders(session, pick_ids):
        print("\n⚠ 收货部分失败")

    # ── 验证 ──
    time.sleep(2)
    verify_status(session, pick_ids)

    # ── 汇总 ──
    print(f"\n{'='*50}")
    print("E2E 完成")
    print(f"{'='*50}")
    print(f"  SKU: {sku}")
    print(f"  订单: {len(pick_ids)} 单")
    for sn in pick_sns:
        print(f"    {sn}")

    session.close()


if __name__ == "__main__":
    main()
