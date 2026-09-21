#!/usr/bin/env python3
"""
sellfox_import_cost_adjust.py
赛狐 成本补录单 一键导入 — 改「仓库+SKU / 单据+SKU」的采购成本

用法:
  uv run python sellfox_import_cost_adjust.py                     # 导入 cost_adjust/out 下最新一批
  uv run python sellfox_import_cost_adjust.py file1.xlsx          # 导入指定文件
  uv run python sellfox_import_cost_adjust.py --fresh             # 强制重新登录

流程: 激活仓库模块 → 成本补录单页 → 导入成本补录单 → 选模式 → 塞文件 → 导入 → 等结果 → 解析成功/失败

模式按**文件名**判定（生成器输出即带模式）:
  `赛狐_成本补录单_按SKU_导入_*.xlsx`  → 按SKU导入
  `赛狐_成本补录单_按单据_导入_*.xlsx` → 按单据导入（海外仓只能用这个；
                                        按SKU会报「创建类型为按sku时,不能为海外仓」）

注意:
  - 文件必须用官方模板生成（表头不可改、含 data validation），
    由 cost_adjust/build_saihu_cost_adjust.py 产出。
  - 赛狐限制单文件 ≤5000 条，生成器已自动拆批。
  - **导入成功 ≠ 生效**：补录单落库为「待审核」，需在页面点「审核通过」才改库存成本。
  - 页面有「最新活动」「功能上新」弹窗会遮挡按钮，脚本会先关掉。
  - 登录态存在 web_automation/sellfox-profile（与 MCP 共享浏览器无关）。
    配了 SELLFOX_USER/SELLFOX_PASSWORD 会先走 ddddocr 自动登录，否则打开登录页等人工登录(300s)。
"""
import json
import os
import sys
import time
from datetime import datetime
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


def _file_skus(filepath: Path) -> set[str]:
    """读导入文件里出现的 SKU（两种模板列名都是 *SKU）。"""
    try:
        import openpyxl

        wb = openpyxl.load_workbook(filepath, read_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None) or ()
        idx = None
        for i, h in enumerate(header):
            if h is not None and str(h).strip().lstrip("*") == "SKU":
                idx = i
                break
        if idx is None:
            return set()
        return {str(r[idx]).strip() for r in rows if r and len(r) > idx and r[idx]}
    except Exception as e:
        print(f"  [!] 读 SKU 失败（跳过审核定位）: {e}")
        return set()


def _pending_adjustments(page, skus: set[str], since_date: str) -> list[dict]:
    """查「待审核」的成本补录单，返回与本次导入 SKU 有交集的。

    用页面同款私有接口 pageList.json（只读，且与浏览器上下文共享 cookie）。
    这是**读**操作；写操作用 UI 点击完成，符合 contract: ui 的约定。

    坑：`createTimeStart` **只接受日期**（`YYYY-MM-DD`）。带时分秒会返回
    `code=500 系统异常`，看起来像"查不到"。
    """
    def query(body):
        try:
            resp = page.request.post(
                "https://www.sellfox.com/api/fba/cost/adjustment/pageList.json",
                data=json.dumps(body),
                headers={"Content-Type": "application/json"},
                timeout=20000,
            )
            j = resp.json()
            if j.get("code") != 0:
                print(f"  [!] pageList 返回 code={j.get('code')} msg={j.get('msg')}")
                return []
            return (j.get("data") or {}).get("rows") or []
        except Exception as e:
            print(f"  [!] 查待审核补录单失败: {e}")
            return []

    rows = query({"pageNo": 1, "pageSize": 50, "status": "to_audit",
                  "createTimeStart": since_date, "createTimeEnd": "2099-12-31"})
    if not rows:
        # 兜底：不带时间范围（status=待审核 + SKU 交集已足够收敛）
        rows = query({"pageNo": 1, "pageSize": 50, "status": "to_audit"})

    out = []
    for r in rows:
        item_skus = {str(it.get("commoditySku", "")).strip() for it in (r.get("items") or [])}
        if item_skus & skus:
            # 坑：主键字段名是 adjustId（不是 id）；详情页 URL 用 adjustId
            out.append({"adjustSn": r.get("adjustSn"), "id": r.get("adjustId") or r.get("id"),
                        "createTime": r.get("createTime"), "adjustType": r.get("adjustType"),
                        "skus": sorted(item_skus & skus)})
    return out


def _adjustment_status(page, adjust_sn: str) -> str | None:
    """查单张补录单当前状态（用于审核后复核）。"""
    try:
        resp = page.request.post(
            "https://www.sellfox.com/api/fba/cost/adjustment/pageList.json",
            data=json.dumps({"pageNo": 1, "pageSize": 50, "status": ""}),
            headers={"Content-Type": "application/json"},
            timeout=20000,
        )
        for r in ((resp.json().get("data") or {}).get("rows") or []):
            if r.get("adjustSn") == adjust_sn:
                return r.get("status")
    except Exception:
        pass
    return None


def approve_adjustment(page, adj: dict) -> tuple[bool, str | None]:
    """打开补录单详情 → 审核通过 → 确定 → 复核状态。返回 (是否点成功, 最终状态)。"""
    detail_url = ("https://www.sellfox.com/amzup-web-main/web/fba/adjust/DetailCostSupplement/index.html"
                  f"?user=isShowDetail&pageName=Adjustment&pageFrom=Adjustment&id={adj['id']}")
    page.goto(detail_url, timeout=30000)
    page.wait_for_timeout(5000)
    _dismiss_blocking_dialogs(page)

    clicked = page.evaluate(
        """() => {
            for (const b of document.querySelectorAll('button,.el-button')) {
                if (b.getBoundingClientRect().width > 0 && (b.innerText||'').trim() === '审核通过') {
                    b.click(); return 'clicked';
                }
            }
            return 'audit-button-not-found';
        }"""
    )
    if clicked != "clicked":
        print(f"    [!] 未找到「审核通过」按钮: {clicked}")
        return False, None
    page.wait_for_timeout(2500)

    # 确认弹窗「确认审核通过?」—— Element UI message-box 必须真实点击
    try:
        confirm = page.locator(".el-message-box:visible button:has-text('确定')").first
        if confirm.count():
            confirm.click(timeout=8000)
        else:
            print("    [!] 未见确认弹窗")
            return False, None
    except Exception as e:
        print(f"    [!] 点确定失败: {e}")
        return False, None
    page.wait_for_timeout(4000)

    status = _adjustment_status(page, adj["adjustSn"])
    return True, status


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

    # Step 2: 按文件名选模式（必须在加文件之前选，决定用哪套模板解析）
    #   生成器输出命名: 赛狐_成本补录单_按SKU_导入_*.xlsx / 赛狐_成本补录单_按单据_导入_*.xlsx
    #   海外仓只能用「按单据」（按SKU会报「创建类型为按sku时,不能为海外仓」）
    mode = "按单据导入" if "按单据" in filepath.name else "按SKU导入"
    print(f"    模式: {mode}")
    r = page.evaluate(
        """(modeText) => {
            const wrappers = document.querySelectorAll('.el-dialog__wrapper');
            for (const d of wrappers) {
                const rect = d.getBoundingClientRect();
                if (window.getComputedStyle(d).display === 'none' || rect.width === 0) continue;
                if (!(d.textContent || '').includes('批量导入成本补录')) continue;
                const radios = d.querySelectorAll('input[type=radio]');
                for (const rb of radios) {
                    const label = (rb.closest('label') || {}).innerText || '';
                    if (label.trim() === modeText) {
                        // Element UI radio 必须真实点击其 label；JS click input 不改变 Vue 状态
                        (rb.closest('label') || rb.parentElement).click();
                        return rb.checked ? 'clicked' : 'clicked-unverified';
                    }
                }
                return 'radio-not-found';
            }
            return 'dialog-not-found';
        }""",
        mode,
    )
    print(f"    选择「{mode}」=> {r}")
    if not str(r).startswith("clicked"):
        print("FAILURE_CODE=BUSINESS_VALIDATION")
        return {"file": filepath.name, "success": 0, "fail": f"无法切到{mode}模式: {r}"}
    page.wait_for_timeout(1200)

    # 复核选中态
    verified = page.evaluate(
        """(modeText) => {
            for (const d of document.querySelectorAll('.el-dialog__wrapper')) {
                const rect = d.getBoundingClientRect();
                if (window.getComputedStyle(d).display === 'none' || rect.width === 0) continue;
                if (!(d.textContent || '').includes('批量导入成本补录')) continue;
                for (const rb of d.querySelectorAll('input[type=radio]')) {
                    const label = ((rb.closest('label') || {}).innerText || '').trim();
                    if (label === modeText) return rb.checked;
                }
            }
            return null;
        }""",
        mode,
    )
    if verified is not True:
        print(f"    [!] 模式复核未通过: {verified}")
        print("FAILURE_CODE=BUSINESS_VALIDATION")
        return {"file": filepath.name, "success": 0, "fail": f"{mode} 未选中"}

    # Step 3: 添加文件 —— 直接给弹窗内的隐藏 input[type=file] 塞文件
    # （比点「添加文件」触发原生选择器更稳，也不依赖可见性）
    print(f"  上传: {filepath.name}")
    file_input = page.locator(
        ".el-dialog__wrapper[style*='display: block'] input[type='file'], "
        ".el-dialog__wrapper:visible input[type='file']"
    ).first
    try:
        file_input.set_input_files(str(filepath), timeout=15000)
    except Exception as e:
        print("FAILURE_CODE=ELEMENT_NOT_FOUND")
        return {"file": filepath.name, "success": 0, "fail": f"添加文件失败: {e}"}
    page.wait_for_timeout(1500)

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


def approve_for_file(page, filepath: Path, since_date: str, do_approve: bool) -> dict:
    """导入成功后，把本次产生的补录单审核通过（导入 ≠ 生效，必须审核）。"""
    if not do_approve:
        return {"approve": "skipped"}
    skus = _file_skus(filepath)
    if not skus:
        return {"approve": "no-sku"}
    pending = _pending_adjustments(page, skus, since_date)
    if not pending:
        print("  审核: 没有找到本次导入的「待审核」补录单")
        return {"approve": "not-found"}
    approved, failed = [], []
    for adj in pending:
        print(f"  审核: {adj['adjustSn']} (id={adj['id']}, {','.join(adj['skus'])}) ...")
        ok, status = approve_adjustment(page, adj)
        if ok and status == "has_passed":
            print(f"    [OK] {adj['adjustSn']} 已审核通过（status={status}）")
            approved.append(adj["adjustSn"])
        else:
            print(f"    [!] {adj['adjustSn']} 审核未生效（点击ok={ok}, status={status}）")
            failed.append(adj["adjustSn"])
    if approved and not failed:
        return {"approve": approved}
    return {"approve": f"approved={approved} failed={failed}"}


def main():
    fresh = "--fresh" in sys.argv
    headless = "--headless" in sys.argv
    do_approve = "--no-approve" not in sys.argv
    args = [a for a in sys.argv[1:] if a not in ("--fresh", "--headless", "--no-approve")]

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
            # 记录导入日期，用于定位本次产生的「待审核」补录单
            # （坑：pageList 的 createTimeStart 只接受日期，带时分秒会 code=500）
            started_date = datetime.now().strftime("%Y-%m-%d")
            r = import_one_file(page, fp)
            if isinstance(r.get("success"), int) and r["success"] > 0:
                r.update(approve_for_file(page, fp, started_date, do_approve))
            elif r.get("success") != "unknown":
                r["approve"] = "skipped-no-success"
            results.append(r)

        print(f"\n{'=' * 50}")
        print("导入汇总")
        print(f"{'=' * 50}")
        total_ok = total_fail = 0
        for r in results:
            ap = r.get("approve")
            if isinstance(ap, list):
                ap_txt = f" 已审核通过 {', '.join(ap)}"
            elif ap == "skipped":
                ap_txt = " (未审核: --no-approve)"
            elif ap == "not-found":
                ap_txt = " (未找到待审核补录单)"
            elif ap == "skipped-no-success":
                ap_txt = ""
            elif ap:
                ap_txt = f" (审核: {ap})"
            else:
                ap_txt = ""
            if isinstance(r.get("success"), int) and isinstance(r.get("fail"), int) and r["fail"] == 0:
                print(f"  ✓ 成功{r['success']}条{ap_txt}  {r['file']}")
            else:
                print(f"  ✗ {r['file']}: 成功{r.get('success')} / {r.get('fail')}{ap_txt}")
            if isinstance(r.get("success"), int):
                total_ok += r["success"]
            if isinstance(r.get("fail"), int):
                total_fail += r["fail"]
        print(f"\n合计: 成功{total_ok}条, 失败{total_fail}条")
        if not do_approve:
            print("[提醒] 用了 --no-approve：补录单停在「待审核」，不会改库存成本。")
        print("\n关闭浏览器...")
        context.close()


if __name__ == "__main__":
    main()
