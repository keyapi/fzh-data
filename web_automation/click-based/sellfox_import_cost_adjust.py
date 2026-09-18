#!/usr/bin/env python3
"""
sellfox_import_cost_adjust.py
赛狐 成本补录单 一键导入（按SKU）— 批量改「仓库+SKU」的采购单价

用法:
  uv run python sellfox_import_cost_adjust.py                     # 导入 cost_adjust/ 下所有文件
  uv run python sellfox_import_cost_adjust.py file1.xlsx          # 导入指定文件
  uv run python sellfox_import_cost_adjust.py --fresh             # 强制重新登录

流程: 激活仓库模块 → 成本补录单页 → 导入成本补录单 → 选「按SKU导入」
      → 添加文件 → 导入 → 等结果 → 解析 成功N条/失败N条 → 关闭 → 下一个

注意:
  - 文件必须是「按SKU导入」模板（表头 9 列不可改），由 cost_adjust/build_saihu_cost_adjust.py 生成。
  - 赛狐限制单文件 ≤5000 条，生成器已自动拆批。
  - 页面有「最新活动」「功能上新」弹窗会遮挡按钮，脚本会先关掉。
  - 登录态存在 web_automation/sellfox-profile（与 MCP 共享浏览器无关）。
    配了 SELLFOX_USER/SELLFOX_PASSWORD 会先走 ddddocr 自动登录，否则打开登录页等人工登录(300s)。
"""
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "sellfox-profile"
# 成本补录单导入文件（由 cost_adjust/build_saihu_cost_adjust.py 产出）
DEFAULT_IMPORT_DIR = WEB_ROOT.parent / "cost_adjust" / "out"

PAGE_URL = "https://www.sellfox.com/amzup-web-main/web/fba/adjust/index.html"
WARMUP_URL = "https://www.sellfox.com/amzup-web-main/web/warehouse/detailed/index.html"
LOGIN_URL = "https://www.sellfox.com/amzup-web-main/login.html"
LOGIN_TIMEOUT = 300

# 页面上的干扰弹窗容器
BLOCKING_DIALOG_SEL = ".el-dialog__wrapper.new_announcement_dialog, .el-dialog__wrapper.Activities"


def wait_for_login(page):
    print(f"\n请在浏览器中登录赛狐（最长等待 {LOGIN_TIMEOUT}s）...")
    for _ in range(0, LOGIN_TIMEOUT, 2):
        time.sleep(2)
        url = page.url
        if "login" not in url and url != "about:blank" and "sellfox" in url:
            print("✓ 登录成功")
            page.wait_for_timeout(1000)
            return True
        try:
            if page.locator("text=克勇").first.is_visible():
                print("✓ 登录成功")
                return True
        except Exception:
            pass
    return False


def try_auto_login(page) -> bool:
    """配了 SELLFOX_USER/SELLFOX_PASSWORD 就用 ddddocr 自动登录；否则返回 False 交给手动登录。"""
    if not (os.getenv("SELLFOX_USER") and os.getenv("SELLFOX_PASSWORD")):
        return False
    legacy = SCRIPT_DIR.parent / "legacy-compatible"
    if str(legacy) not in sys.path:
        sys.path.insert(0, str(legacy))
    try:
        import sellfox_login_ocr
    except Exception as e:
        print(f"  [自动登录不可用] {e}")
        return False
    try:
        ok = bool(sellfox_login_ocr.login(page))
        print("✓ 自动登录成功" if ok else "✗ 自动登录失败，转手动登录")
        return ok
    except Exception as e:
        print(f"  [自动登录异常] {e}")
        return False


def is_logged_in(page) -> bool:
    """成本补录单页上能拿到「创建成本补录单」按钮即视为已登录。"""
    url = page.url
    if "login" in url or url == "about:blank":
        return False
    try:
        return page.locator('button:has-text("创建成本补录单")').first.is_visible(timeout=5000)
    except Exception:
        return False


def _dismiss_blocking_dialogs(page):
    """关掉公告/活动弹窗（它们会盖住「导入成本补录单」按钮）。"""
    page.keyboard.press("Escape")
    page.evaluate(
        """(sel) => {
            document.querySelectorAll(sel).forEach(w => { w.style.display = 'none'; });
            document.querySelectorAll('.el-dialog__headerbtn, [class*="close_btn"]').forEach(b => {
                if (b.offsetParent !== null) b.click();
            });
        }""",
        BLOCKING_DIALOG_SEL,
    )


def _js_click_text(page, text: str, selector: str = "button, .el-button, .el-dropdown-menu__item, a, span"):
    """按可见文字点击（JS click，绕过 Playwright has_text 的编码/可见性判定）。"""
    return page.evaluate(
        """([sel, text]) => {
            for (const el of document.querySelectorAll(sel)) {
                if (el.offsetParent === null) continue;
                if ((el.textContent || '').trim().includes(text)) { el.click(); return 'clicked'; }
            }
            return 'not-found';
        }""",
        [selector, text],
    )


def _visible_dialog(page):
    """返回当前可见弹窗的 text（无则 None）。赛狐页面有 20+ 隐藏的 el-dialog__wrapper。"""
    return page.evaluate(
        """() => {
            const wrappers = document.querySelectorAll('.el-dialog__wrapper');
            for (const d of wrappers) {
                const r = d.getBoundingClientRect();
                if (window.getComputedStyle(d).display === 'none' || r.width === 0) continue;
                if ((d.textContent || '').includes('批量导入成本补录')) return d.textContent || '';
            }
            return null;
        }"""
    )


def _goto_adjust_page(page):
    """SPA 需要先激活「仓库」模块，再进成本补录单页。"""
    page.goto(WARMUP_URL, timeout=30000)
    page.wait_for_timeout(4000)
    _dismiss_blocking_dialogs(page)

    page.goto(PAGE_URL, timeout=30000)
    page.wait_for_timeout(5000)
    _dismiss_blocking_dialogs(page)

    if "adjust" not in page.evaluate("() => location.href"):
        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(5000)


def import_one_file(page, filepath: Path) -> dict:
    print(f"\n{'=' * 50}")
    print(f"导入: {filepath.name}")
    print(f"{'=' * 50}")

    _goto_adjust_page(page)

    # Step 1: 等「导入成本补录单」按钮出现并点击
    print("  打开「导入成本补录单」...")
    opened = False
    for attempt in range(30):
        time.sleep(1)
        _dismiss_blocking_dialogs(page)
        if _js_click_text(page, "导入成本补录单") == "clicked":
            print(f"    已点击 (第{attempt + 1}s)")
            opened = True
            break
    if not opened:
        print("FAILURE_CODE=ELEMENT_NOT_FOUND")
        return {"file": filepath.name, "success": 0, "fail": "未找到「导入成本补录单」按钮"}

    page.wait_for_timeout(1500)

    # Step 2: 选「按SKU导入」模式（必须在加文件之前选，决定用哪套模板解析）
    r = page.evaluate(
        """() => {
            const wrappers = document.querySelectorAll('.el-dialog__wrapper');
            for (const d of wrappers) {
                const rect = d.getBoundingClientRect();
                if (window.getComputedStyle(d).display === 'none' || rect.width === 0) continue;
                if (!(d.textContent || '').includes('批量导入成本补录')) continue;
                for (const el of d.querySelectorAll('*')) {
                    if (el.children.length === 0 && (el.textContent || '').trim() === '按SKU导入') {
                        el.click(); return 'clicked';
                    }
                }
                return 'radio-not-found';
            }
            return 'dialog-not-found';
        }"""
    )
    print(f"    选择「按SKU导入」=> {r}")
    if r != "clicked":
        print("FAILURE_CODE=BUSINESS_VALIDATION")
        return {"file": filepath.name, "success": 0, "fail": f"无法切到按SKU导入模式: {r}"}
    page.wait_for_timeout(800)

    # Step 3: 添加文件（必须 Playwright 原生 click 才能触发 file chooser）
    print(f"  上传: {filepath.name}")
    add_file = page.locator("button").filter(has_text="添加文件").first
    try:
        with page.expect_file_chooser(timeout=10000) as fc_info:
            add_file.click(timeout=5000)
    except Exception as e:
        print("FAILURE_CODE=ELEMENT_NOT_FOUND")
        return {"file": filepath.name, "success": 0, "fail": f"添加文件失败: {e}"}
    fc_info.value.set_files(str(filepath))
    page.wait_for_timeout(1200)

    # Step 4: 点「导入」
    print("  导入中...")
    r = page.evaluate(
        """() => {
            const wrappers = document.querySelectorAll('.el-dialog__wrapper');
            for (const d of wrappers) {
                const rect = d.getBoundingClientRect();
                if (window.getComputedStyle(d).display === 'none' || rect.width === 0) continue;
                for (const btn of d.querySelectorAll('button')) {
                    if ((btn.textContent || '').trim() === '导入' && !btn.disabled) { btn.click(); return 'clicked'; }
                }
            }
            return 'import-button-not-found';
        }"""
    )
    if r != "clicked":
        print("FAILURE_CODE=ELEMENT_NOT_FOUND")
        return {"file": filepath.name, "success": 0, "fail": f"未找到「导入」按钮: {r}"}

    # Step 5: 轮询导入结果
    result_text, fail_text = None, None
    for _ in range(120):
        time.sleep(2)
        res = page.evaluate(
            """() => {
                const wrappers = document.querySelectorAll('.el-dialog__wrapper');
                for (const d of wrappers) {
                    const rect = d.getBoundingClientRect();
                    if (window.getComputedStyle(d).display === 'none' || rect.width === 0) continue;
                    const t = d.textContent || '';
                    if (t.includes('导入完成')) return {kind: 'done', text: t};
                    if (t.includes('导入失败') || t.includes('失败原因')) return {kind: 'failed', text: t};
                }
                return null;
            }"""
        )
        if res:
            result_text, fail_text = res["text"], (None if res["kind"] == "done" else res["text"])
            break

    if not result_text:
        print("  [!] 超时未收到导入结果（可能弹窗已自动关闭）")
        print("FAILURE_CODE=SERVICE_UNAVAILABLE")
        return {"file": filepath.name, "success": "unknown", "fail": 0}

    if fail_text:
        print(f"  [!] 导入被拒: {fail_text[-300:]}")
        print("FAILURE_CODE=BUSINESS_VALIDATION")
        return {"file": filepath.name, "success": 0, "fail": fail_text[-200:]}

    import re

    m_ok = re.search(r"成功(\d+)条", result_text)
    m_fail = re.search(r"失败(\d+)条", result_text)
    success_count = int(m_ok.group(1)) if m_ok else 0
    fail_count = int(m_fail.group(1)) if m_fail else 0

    if fail_count > 0:
        print(f"  [!] 成功{success_count}条, 失败{fail_count}条 — 尝试下载失败原因")
        _js_click_text(page, "下载查看失败原因")
        page.wait_for_timeout(2500)
        out_dir = Path(DEFAULT_IMPORT_DIR)
    else:
        out_dir = None
        print(f"  [OK] 成功{success_count}条")

    # Step 6: 关闭弹窗
    page.evaluate(
        """() => {
            document.querySelectorAll('.el-dialog__wrapper button').forEach(btn => {
                if ((btn.textContent || '').trim() === '关闭' && btn.offsetParent !== null) btn.click();
            });
        }"""
    )
    page.wait_for_timeout(800)

    if fail_count > 0:
        print(f"  失败明细已下载到 {out_dir}（如有）")

    return {"file": filepath.name, "success": success_count, "fail": fail_count}


def main():
    fresh = "--fresh" in sys.argv
    headless = "--headless" in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--fresh", "--headless")]

    if args and not args[0].startswith("--"):
        files = [Path(a).resolve() for a in args]
    else:
        if not DEFAULT_IMPORT_DIR.exists():
            print(f"未找到导入目录: {DEFAULT_IMPORT_DIR}")
            return
        files = sorted(
            (f for f in DEFAULT_IMPORT_DIR.rglob("*.xlsx") if not f.name.startswith("~$")),
            key=lambda f: f.stat().st_mtime,
        )
        # 只取最新一批（同一 stamp 目录）
        if files:
            latest_dir = files[-1].parent
            files = [f for f in files if f.parent == latest_dir]

    if not files:
        print("未找到要导入的 xlsx 文件。")
        print("先跑: uv run python ../cost_adjust/build_saihu_cost_adjust.py")
        return

    print("\n赛狐 成本补录单 一键导入（按SKU）")
    print(f"文件数: {len(files)}")
    for f in files:
        print(f"  - {f}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=headless
        )
        page = context.pages[0] if context.pages else context.new_page()

        page.goto(PAGE_URL, timeout=30000)
        page.wait_for_timeout(3000)

        if fresh or not is_logged_in(page):
            print("\n[!] 未登录 → 打开登录页")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_timeout(2000)
            if not try_auto_login(page) and not wait_for_login(page):
                print("FAILURE_CODE=AUTH_FAILED")
                context.close()
                return
        else:
            print("\n[OK] 已登录，跳过登录步骤")

        results = []
        for fp in files:
            if not fp.exists():
                print(f"\n[跳过] 文件不存在: {fp}")
                results.append({"file": fp.name, "success": 0, "fail": "not found"})
                continue
            results.append(import_one_file(page, fp))

        print(f"\n{'=' * 50}")
        print("导入汇总")
        print(f"{'=' * 50}")
        total_ok = total_fail = 0
        for r in results:
            if isinstance(r.get("success"), int) and isinstance(r.get("fail"), int) and r["fail"] == 0:
                print(f"  ✓ 成功{r['success']}条  {r['file']}")
            else:
                print(f"  ✗ {r['file']}: 成功{r.get('success')} / {r.get('fail')}")
            if isinstance(r.get("success"), int):
                total_ok += r["success"]
            if isinstance(r.get("fail"), int):
                total_fail += r["fail"]
        print(f"\n合计: 成功{total_ok}条, 失败{total_fail}条")
        print("\n关闭浏览器...")
        context.close()


if __name__ == "__main__":
    main()
