#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉 aflow「销售收款确认单」单据导出为 Excel（浏览器，持久化登录）。

用法:
  uv run python web_automation/legacy-compatible/dingtalk_aflow_receipt.py \
      --from 2026-07-04 --to 2026-09-09

产出:
  <out>/Amazon&新平台成本 {from}-{to} 销售收款确认单-{导出时间戳}.xlsx

流程（选择器与踩坑详见 web_automation/docs/reference/aflow-receipt-export.md）:
  登录 → 表单名称级联(已启用→销售收款确认单) → 发起时间 → 查询
  → 导出全部(异步任务) → 操作记录/导出记录 轮询 → 下载 → 落盘

约定:
  - 默认 headed：cookie 失效时用户可在窗口里现场登录（脚本会先开 oa.dingtalk.com 触发登录流）。
  - 文件名自构造，不用 download.suggested_filename。
  - 只写 <out>（仓库外）与 gitignore 的 profile 目录，不写仓库内任何目录。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
DEFAULT_PROFILE = WEB_ROOT / "dingtalk-profile"
DEFAULT_OUT = Path(r"D:\Work\王忠于\成本核算")

# 直接开 aflow 未登录会落到一个没有任何登录控件的 error.vm；
# 必须先走 oa.dingtalk.com 才能触发钉钉统一身份认证 + 选组织。
AFLOW_URL = (
    "https://aflow.dingtalk.com/dingtalk/web/query/dashboard"
    "?dinghash=aflowSetting#/aflowSetting/dataManage?tabKey=default"
)
RECORD_URL = (
    "https://aflow.dingtalk.com/dingtalk/web/query/dashboard"
    "?dinghash=aflowSetting#/aflowSetting/dataManage?tab=export&tabKey=record"
)
LOGIN_URL = "https://oa.dingtalk.com/index.htm"
DEFAULT_FORM = "销售收款确认单"
FILE_PREFIX = "Amazon&新平台成本"

LOGIN_HINT = (
    "[信息] 未检测到登录态。已在浏览器里打开钉钉登录页，脚本会自动尝试一键头像授权。\n"
    "       若需要你介入：\n"
    "       1) Chrome 左上角若弹「访问此设备上的其它应用和服务」→ 点【允许】\n"
    "          （原生气泡，脚本点不到；按 profile 只问一次）\n"
    "       2) 头像没出来时改用手机钉钉扫码\n"
    f"       3) 登录态持久化到 {DEFAULT_PROFILE}，之后不再需要\n"
)


def emit_failure(code: str, detail: str = "") -> None:
    if detail:
        print(detail)
    print(f"FAILURE_CODE={code}")


def ymd(s: str) -> str:
    """2026-07-04 -> 20260704"""
    return datetime.strptime(s, "%Y-%m-%d").strftime("%Y%m%d")


def is_logged_in(page: Page) -> bool:
    """登录后才会出现的锚点：筛选表单里的「表单名称」级联。"""
    try:
        return page.locator("text=表单名称").count() > 0 and "error.vm" not in page.url
    except Exception:
        return False


def dismiss_modals(page: Page) -> None:
    """首屏两个弹窗会挡住点击。"""
    for sel in (
        "button.upgrade-guide-button:not(.button-primary)",  # 新增搜索功能 → 稍后升级
        "button.dtd-modal-close",                            # 智能OA试用已过期 → ×
    ):
        try:
            loc = page.locator(sel)
            if loc.count():
                loc.first.click(timeout=3000)
                page.wait_for_timeout(500)
        except Exception:
            pass


def try_avatar_login(page: Page) -> bool:
    """钉钉登录页的「一键头像授权」：勾选自动登录 + 点头像。

    依赖本机钉钉客户端在 127.0.0.1:8441-8443 可达（客户端版本不匹配时不可用，
    页面只剩二维码）→ 返回 False，交由用户扫码。
    另需用户在 Chrome 的「访问此设备上的其它应用和服务」气泡点允许（原生 UI，脚本够不到）。
    """
    try:
        if not page.locator(".app-qr-login-page").count():
            return False
    except Exception:
        return False
    try:
        box = page.locator(".app-qr-login-page .base-comp-check-box-rememberme-box").first
        if box.count() and "checkbox-done" not in (box.get_attribute("class") or ""):
            box.click(timeout=3000)
            page.wait_for_timeout(300)
    except Exception:
        pass
    try:
        av = page.locator(".app-qr-login-page .module-qrcode-user-avatar").first
        if av.count():
            av.click(timeout=5000)
            page.wait_for_timeout(1500)
            return True
    except Exception:
        pass
    return False


def pick_org(page: Page, org: str) -> bool:
    """登录后「选择你管理的组织」页：点目标组织。"""
    try:
        if not page.locator(".app-page-curr").count():
            return False
        target = page.locator(f'.app-page-curr :text-is("{org}")')
        if target.count():
            target.first.click(timeout=5000)
            page.wait_for_timeout(2000)
            print(f"[信息] 已选择组织：{org}")
            return True
    except Exception:
        pass
    return False


def wait_for_login(page: Page, timeout_s: int, org: str) -> bool:
    """开 oa.dingtalk.com 触发统一身份认证，自动尝试一键头像；失败则等用户扫码。"""
    if is_logged_in(page):
        return True
    print(LOGIN_HINT)
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(3000)
    waited = 0
    avatar_done = False
    while waited < timeout_s:
        if page.url.startswith("https://oa.dingtalk.com/index.htm") and "welcome" in page.url:
            break
        if "login.dingtalk.com" in page.url:
            if not avatar_done and try_avatar_login(page):
                avatar_done = True
                print("[信息] 已勾选自动登录并点击头像，等待授权…")
            pick_org(page, org)
        page.wait_for_timeout(2000)
        waited += 2
    try:
        page.goto(AFLOW_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(4000)
    return is_logged_in(page)


def current_form(page: Page) -> str:
    """当前已选的表单名（aflow 按账号记住上次选择，可能是「已启用 / 销售收款确认单」）。"""
    try:
        el = page.locator(".ant-select-selection-item").first
        if not el.count():
            return ""
        return (el.get_attribute("title") or el.inner_text() or "").strip()
    except Exception:
        return ""


def select_form(page: Page, form: str) -> bool:
    """表单名称是二级级联：先状态，再表单。必须精确匹配（有多个近似名）。

    幂等：已经选好就直接跳过——否则显示已选值的 span 会挡住输入框。
    """
    want = f"已启用 / {form}"
    if current_form(page) == want:
        print(f"[信息] 表单已是「{want}」，跳过选择")
        return True
    try:
        # 点容器本身，不要点内层 search input（会被 selection-item 拦截）
        page.locator(".ant-select.ant-cascader").first.click(timeout=10000)
        page.wait_for_timeout(800)
        page.locator('.ant-cascader-menu-item:has-text("已启用")').first.click()
        page.wait_for_timeout(800)
        page.locator(f'.ant-cascader-menu :text-is("{form}")').first.click()
        page.wait_for_timeout(800)
        got = current_form(page)
        if got != want:
            print(f"[错误] 表单选择未生效: 期望「{want}」，实际「{got}」")
            return False
        return True
    except Exception as e:
        print(f"[错误] 选表单失败: {e}")
        return False


def set_date_range(page: Page, d_from: str, d_to: str) -> bool:
    """发起时间用的是 dtd RangePicker，input 是 readOnly，只能走日历面板。"""
    try:
        cur_from = page.locator('input[placeholder="开始日期"]').first.input_value()
        cur_to = page.locator('input[placeholder="结束日期"]').first.input_value()
        if cur_from == d_from and cur_to == d_to:
            print(f"[信息] 发起时间已是 {d_from}~{d_to}，跳过设置")
            return True
        page.locator('input[placeholder="开始日期"]').first.click()
        page.wait_for_timeout(1000)
        target = datetime.strptime(d_from, "%Y-%m-%d")
        # 面板一次显示两个月，翻到包含起始月为止
        for _ in range(60):
            headers = page.locator(".dtd-picker-header-view:visible").all_inner_texts()
            if not headers:
                break
            m = re.search(r"(\d{4})年(\d{1,2})月", headers[0])
            if m and (int(m.group(1)), int(m.group(2))) >= (target.year, target.month):
                break
            page.locator(".dtd-picker-header-next-btn:visible").first.click()
            page.wait_for_timeout(300)
        page.locator(f'[title="{d_from}"]').first.click()
        page.wait_for_timeout(800)
        page.locator(f'[title="{d_to}"]').first.click()
        page.wait_for_timeout(800)
        got_from = page.locator('input[placeholder="开始日期"]').first.input_value()
        got_to = page.locator('input[placeholder="结束日期"]').first.input_value()
        if got_from != d_from or got_to != d_to:
            print(f"[错误] 日期未生效: 期望 {d_from}~{d_to}，实际 {got_from}~{got_to}")
            return False
        return True
    except Exception as e:
        print(f"[错误] 设置发起时间失败: {e}")
        return False


def list_export_rows(page: Page) -> list[str]:
    """操作记录里每行的导出文件名（第 1 列）。"""
    out: list[str] = []
    for tr in page.locator("tr:visible").all():
        try:
            first = tr.locator("td").first
            if first.count():
                t = (first.inner_text() or "").strip()
                if t and t != "导出文件名称":
                    out.append(t)
        except Exception:
            continue
    return out


def goto_records(page: Page) -> None:
    # 注意：只改 hash 的 goto 在 SPA 里不是重载，必须 reload 才能拿到最新进度
    page.goto(RECORD_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(4000)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="钉钉 aflow 销售收款确认单导出")
    ap.add_argument("--mode", default="excel", choices=["excel", "attachments"])
    ap.add_argument("--from", dest="d_from", default="2026-07-04")
    ap.add_argument("--to", dest="d_to", default="2026-09-09")
    ap.add_argument("--form", default=DEFAULT_FORM)
    ap.add_argument("--org", default="方州汇国际", help="登录后要选择的组织名")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE))
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--login-timeout", type=int, default=300)
    ap.add_argument("--export-timeout", type=int, default=600)
    ap.add_argument("--auto-login", action="store_true",
                    help="仅为 dispatcher/CLI 对齐保留；钉钉网页是扫码/SSO，非图形验证码，本参数是 no-op")
    args = ap.parse_args()

    if args.mode != "excel":
        # 附件批量导出的产物进钉盘、aflow 侧取不回本地 —— 见参考文档
        emit_failure(
            "ATTACHMENT_MANUAL_REQUIRED",
            "[错误] aflow 未提供可取回本地的批量附件下载：产物落【云盘-团队文件】且无入口。\n"
            "       请改用 dingtalk/dingtalk_oa_approval/fetch_attachments.py（API），"
            "离职发起人走 previewAttachments 深链。",
        )
        return 1
    if args.auto_login:
        print("[信息] --auto-login 对钉钉无意义（非验证码登录），已忽略")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(args.profile)
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=args.headless,
            accept_downloads=True,
            viewport={"width": 1500, "height": 950},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(AFLOW_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            if not is_logged_in(page) and not wait_for_login(page, args.login_timeout, args.org):
                emit_failure("LOGIN_TIMEOUT", "[错误] 登录未完成，请手动登录后重试")
                return 1

            dismiss_modals(page)

            if not select_form(page, args.form):
                emit_failure("FORM_NOT_FOUND", f"[错误] 未找到表单：{args.form}")
                return 1
            if not set_date_range(page, args.d_from, args.d_to):
                emit_failure("INVALID_ARGUMENT", "[错误] 发起时间未设置成功，中止以免导出默认区间")
                return 1

            page.locator('button.dtd-btn-primary:has-text("查询")').first.click()
            page.wait_for_timeout(4000)
            rows_now = list_export_rows(page)
            if page.locator("text=暂无数据").count():
                print("[信息] 查询结果为空，仍继续尝试导出（导出全部按当前筛选）")

            # 先记下已有导出记录，用于锚定本次新任务
            goto_records(page)
            before = set(list_export_rows(page))
            page.goto(AFLOW_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)
            dismiss_modals(page)
            select_form(page, args.form)
            set_date_range(page, args.d_from, args.d_to)
            page.locator('button.dtd-btn-primary:has-text("查询")').first.click()
            page.wait_for_timeout(3000)

            # 导出全部：点按钮本体直接触发（没有下拉菜单）
            page.locator('button:has-text("导出全部")').first.click()
            page.wait_for_timeout(2500)
            # 弹窗「数据正在导出…」
            if page.locator('button:has-text("查看进度")').count():
                page.locator('button:has-text("查看进度")').first.click()
                page.wait_for_timeout(3000)

            # 轮询：本次新出现的「销售收款确认单-*.xlsx」且 已完成
            bench_ts = datetime.now().strftime("%Y%m%d%H%M%S")
            print(f"[信息] 已提交导出，本次基准时间 {bench_ts}，开始轮询…")
            target_name = ""
            row_prefix = f"{args.form}-"
            waited = 0
            while waited < args.export_timeout:
                goto_records(page)
                names = list_export_rows(page)
                new = [n for n in names if n not in before and n.startswith(row_prefix)]
                if new:
                    target_name = new[0]
                    tr = page.locator("tr:visible").filter(has_text=target_name).first
                    txt = (tr.inner_text() or "").replace("\n", " ")
                    if "已完成" in txt:
                        print(f"[信息] 任务完成: {target_name}")
                        break
                    print(f"[信息] {waited}s 进度: {txt.strip()[:80]}")
                waited += 10
                page.wait_for_timeout(10000)
            else:
                emit_failure("EXPORT_TIMEOUT", f"[错误] 等 {args.export_timeout}s 仍未完成")
                return 1

            m = re.search(r"-(\d{14})\.xlsx$", target_name)
            stamp = m.group(1) if m else bench_ts
            final = out_dir / f"{FILE_PREFIX} {ymd(args.d_from)}-{ymd(args.d_to)} {args.form}-{stamp}.xlsx"

            tr = page.locator("tr:visible").filter(has_text=target_name).first
            with page.expect_download(timeout=120000) as dl_info:
                tr.locator("a.export-file-download").first.click()
            download = dl_info.value
            download.save_as(str(final))

            size_kb = final.stat().st_size / 1024
            print(f"[完成] {final}")
            print(f"[汇总] 单据导出 1 个文件，{size_kb:.0f} KB，来源任务 {target_name}")
            return 0
        except PWTimeout as e:
            emit_failure("EXPORT_TIMEOUT", f"[错误] 超时: {e}")
            return 1
        except Exception as e:
            emit_failure("UNCLASSIFIED_FAILURE", f"[错误] {type(e).__name__}: {e}")
            return 1
        finally:
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
