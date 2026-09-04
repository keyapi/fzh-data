#!/usr/bin/env python3
"""
通途库存清单自动导出 + 导入文件生成（多仓库版）

用法:
  uv run python tongtu_auto_export.py           # 持久化会话，依次导出所有仓库
  uv run python tongtu_auto_export.py --fresh    # 强制重新登录
  uv run python tongtu_auto_export.py --auto-login  # ddddocr 自动登录（首次/cookie过期）
  uv run python tongtu_auto_export.py --export-cookies  # 导出 cookies 供 MCP 使用

输出目录:
  downloads/   原始库存清单 XLSX（每个仓库一个）
  output/      生成的导入文件 XLSX（每个仓库一个）

MCP 模式经验:
  - MCP Playwright 使用独立浏览器实例，无法共享 chrome-profile
  - 解决方案: 用 --export-cookies 提取 cookie → MCP browser_run_code 注入
  - 但 session cookie (JSESSIONID) 无法持久化，需要 passport 的记住密码 cookie
  - 参考 PROJECT.md "八、MCP 调试记录" 章节了解详情
"""
import re
import subprocess, sys, time, shutil, json
from pathlib import Path
from playwright.sync_api import sync_playwright

from tongtu_warehouses import (
    WAREHOUSES,
    inventory_download_matches_warehouse,
    safe_prefix,
    should_exit_after_export_run,
)

sys.stdout.reconfigure(encoding='utf-8')
import os

def load_env():
    """加载 .env 文件中的环境变量（web_automation 根 + 仓库根）"""
    here = Path(__file__).resolve().parent
    candidates = [here.parent / ".env", here.parent.parent / ".env"]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if key not in os.environ:
                os.environ[key] = val

load_env()

# 检查登录信息
if not os.getenv("TONGTU_USER") or not os.getenv("TONGTU_PASSWORD"):
    print("[提示] 未检测到登录信息。")
    print("  方式1: 在 .env 文件中添加：")
    print("    TONGTU_USER=你的邮箱")
    print("    TONGTU_PASSWORD=你的密码")
    print("  方式2: 设置环境变量 TONGTU_USER 和 TONGTU_PASSWORD")
    print("  方式3: 不带 --auto-login 运行，浏览器打开后手动登录\n")
TONGTU_URL = "https://erp102.tongtool.com/warehouse/goodsbalance/index.htm?warehouse=1&isFirstInto=1"
SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = WEB_ROOT / "chrome-profile"
DOWNLOADS_DIR = WEB_ROOT / "downloads"
OUTPUT_DIR = WEB_ROOT / "output"
LOGIN_TIMEOUT_SECS = 300

# 导出的仓库列表（2026-09-03 通途仓名统一为 美东-/波兰-/美中- 前缀）
# 结构 = 3 分公司主仓 + 3 对应退货仓。皮壳库存已并入「美中-FZH-DANEEY」主仓；
# 成品仓 / 半成品仓 / Wayfair / 星链 / 大件 / 多渠道 已停用或非库存主线，一律不导出。
# 若通途再次改名/加仓：跑 `uv run python tongtu_auto_export.py --list-warehouses` 对照更新 tongtu_warehouses.py。


def _warehouse_toggle(page, name: str):
    pattern = re.compile(rf"^{re.escape(name)}$")
    return page.locator(
        "#warehouseDisableDiv a.toggle_btn, #warehouseDisableDiv a.toggle_btn_down"
    ).filter(has_text=pattern).first


def ensure_ocr() -> tuple[bool, str]:
    """见 tongtu_login_ocr.ensure_ocr（懒惰试装 OCR，幂等、不询问）。"""
    from tongtu_login_ocr import ensure_ocr as _ensure

    return _ensure()


def is_already_logged_in(page):
    try:
        el = page.locator("#warehouseDisableDiv")
        return el.count() > 0 and el.is_visible()
    except:
        return False


def wait_for_login(page):
    print(f"\n[信息] 请在浏览器中登录通途...")
    print(f"[信息] 脚本将自动检测登录状态（最长等待 {LOGIN_TIMEOUT_SECS} 秒）")
    for i in range(0, LOGIN_TIMEOUT_SECS, 3):
        time.sleep(3)
        if is_already_logged_in(page):
            print("[OK] 检测到登录成功！自动继续...")
            page.wait_for_timeout(1000)
            return True
        if i % 15 == 0 and i > 0:
            print(f"  等待登录中... ({i}/{LOGIN_TIMEOUT_SECS}s)")
    return False


def ensure_toggle(page, div_id, label_text, target_class="toggle_btn_down"):
    """确保某个 toggle 按钮已选中（如仓库类型、仓库状态）"""
    try:
        a = page.locator(f"#{div_id} a").first
        a.wait_for(state="visible", timeout=3000)
        cls = a.get_attribute("class") or ""
        if target_class in cls:
            return True
        print(f"  [操作] 选中: {label_text}")
        a.click()
        page.wait_for_timeout(1500)
        return True
    except Exception as e:
        print(f"  [警告] 无法选中 {label_text}: {e}")
        return False


def select_warehouse(page, name, all_warehouses=None):
    """点击指定仓库名称的切换按钮（ExtJS togglebutton 组件）

    通途 Bug 处理: 页面加载时 togglebutton 显示已选中，但 ExtJS 数据表格未实际渲染。
    必须"先切到其他仓库再切回来"才能触发数据加载。"""
    target = _warehouse_toggle(page, name)
    try:
        target.wait_for(state="visible", timeout=5000)
        current_class = target.get_attribute("class") or ""
        if "toggle_btn_down" in current_class:
            # 通途 Bug: 显示选中但数据可能没加载 → 先切走再切回来
            other = _pick_other_warehouse(name, all_warehouses or [])
            print(f"  [操作] 通途 Bug 规避: 先切 {other} 再切回 {name}")
            _warehouse_toggle(page, other).click()
            page.wait_for_timeout(3000)
        else:
            print(f"  [操作] 切换至: {name}")
        target.click()
        page.wait_for_timeout(8000)
        return True
    except Exception as e:
        print(f"  [错误] 选仓库失败 '{name}': {e}")
        return False


def _pick_other_warehouse(current, all_warehouses):
    """从仓库列表中挑一个不是 current 的仓库名"""
    for w in all_warehouses:
        if w != current:
            return w
    return all_warehouses[0] if all_warehouses else current


def list_warehouses_on_page(page):
    """抓取库存结存页仓库区所有可切换仓库名并打印（供对照更新 WAREHOUSES）。

    仓库 toggle 在 `#warehouseDisableDiv` 下，`a.toggle_btn`(未选)/`a.toggle_btn_down`(已选)。
    """
    names = page.eval_on_selector_all(
        "#warehouseDisableDiv a.toggle_btn, #warehouseDisableDiv a.toggle_btn_down",
        "els => els.map(e => e.textContent.trim()).filter(Boolean)",
    )
    print("\n" + "=" * 50)
    print(f"页面仓库清单（{len(names)} 个，含选中态）:")
    print("=" * 50)
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}")
    return names


def click_export(page, warehouse_name):
    """点击导出按钮并等待下载（MCP 实测 click 有效，需确保数据表格已渲染）。

    返回保存的 Path；若 60s 未等到下载（空仓无可导数据等）返回 None，
    由调用方记录跳过而不是炸掉整轮。
    """
    try:
        with page.expect_download(timeout=60000) as download_info:
            page.locator('a[onclick="exportExcelPage()"]').first.click()
            print(f"  [OK] 已点击导出，等待下载...")
    except Exception as e:
        print(f"  [跳过] {warehouse_name}: 导出超时/失败（可能该仓无可导出数据）: {type(e).__name__}")
        return None

    download = download_info.value
    prefix = safe_prefix(warehouse_name)
    # Windows 文件名编码坑: download.suggested_filename 从 GBK 服务器
    # Content-Disposition 解码后可能变成乱码。改用 Python 本地时间构造文件名。
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{prefix}_库存结存清单{ts}.xlsx"
    target = DOWNLOADS_DIR / new_name
    download.save_as(str(target))
    print(f"  [OK] 已保存: {new_name}")
    return target


def export_inventory_with_retry(page, warehouse_name, *, attempts: int = 2):
    """Try export up to `attempts` times; None means likely empty warehouse after retries."""
    for attempt in range(1, attempts + 1):
        inv_path = click_export(page, warehouse_name)
        if inv_path is not None:
            return inv_path
        if attempt < attempts:
            print(f"  [重试] {warehouse_name}: 导出超时，再试一次 ({attempt}/{attempts})...")
    return None


def run_generate(inventory_path, warehouse_name):
    """调用 generate_tongtu_import.py 生成导入文件"""
    generate_script = SCRIPT_DIR / "generate_tongtu_import.py"
    prefix = safe_prefix(warehouse_name)
    out_path = OUTPUT_DIR / f"{prefix}_通途导入_头程运费_其他费用.xlsx"
    print(f"  [信息] 生成导入文件 → {out_path.name}")
    result = subprocess.run(
        [sys.executable, str(generate_script), str(inventory_path), str(out_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            if any(kw in line for kw in ("共", "SKU", "校验", "错误", "完成", "OK")):
                try:
                    print(f"    {line.strip()}")
                except UnicodeEncodeError:
                    print(f"    {line.strip().encode('ascii', errors='replace').decode()}")
    if result.returncode != 0:
        print(f"  [错误] 生成失败 (exit={result.returncode})")
        if result.stderr:
            try:
                print(f"    {result.stderr[:500]}")
            except UnicodeEncodeError:
                pass
        return False
    return True


def export_cookies():
    """从 chrome-profile 提取 cookies 供 MCP 注入使用

    这是 MCP 调试后发现的关键功能:
    - MCP Playwright 使用独立浏览器实例，无法直接复用 chrome-profile
    - 但可以通过 context.cookies() 提取持久化的非 session cookie
    - 输出 JSON 可直接用于 MCP 的 browser_run_code → addCookies()
    - 注意: session cookie (JSESSIONID) 无法持久化，但 passport 的
      记住密码 cookie (username/password hash) 可实现自动登录
    """
    if not PROFILE_DIR.exists():
        print("[错误] chrome-profile/ 不存在，请先运行一次脚本登录")
        sys.exit(1)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
        )
        all_cookies = context.cookies()
        context.close()

    tongtu_cookies = [c for c in all_cookies if "tongtool" in c.get("domain", "")]
    output = []
    for c in tongtu_cookies:
        entry = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c["path"],
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        }
        if "expires" in c and c["expires"] > 0:
            entry["expires"] = c["expires"]
        output.append(entry)

    out_path = WEB_ROOT / "mcp_cookies.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[OK] 已导出 {len(output)} 个 cookie → {out_path}")
    print(f"[信息] 在 MCP 会话中使用 browser_run_code 注入这些 cookies:")
    print(f"  await page.context().addCookies(cookies);")
    print(f"[注意] session cookie (JSESSIONID 等) 无法通过此方式持久化，")
    print(f"       但 passport 的记住密码 cookie 可触发自动登录。")


def _semi_auto_login(page, *, show_expired: bool = False) -> bool:
    """半自动登录：有 .env 凭据就自动填账号+勾 7 天，验证码留给用户在浏览器输入。

    无凭据则纯手动（现状）。返回登录是否成功。
    """
    if show_expired:
        print("[信息] 登录会话已过期，请重新登录")
    from tongtu_login_ocr import fill_credentials

    try:
        page.wait_for_selector('input[name="username"]', state="attached", timeout=15000)
    except Exception:
        pass  # 已登录或被其它跳转接管，交由 wait_for_login 判定
    if fill_credentials(page):
        print("  已自动填好账号密码（勾选 7 天内自动登录）。")
        print("  请在浏览器窗口输入【图形验证码】并点击登录...")
    else:
        print("  请在浏览器中登录通途（账号 / 密码 / 验证码）...")
    return wait_for_login(page)


def _try_login(page, auto_login: bool, *, show_expired: bool = False) -> bool:
    """未登录时的分层登录：用户要全自动 → 试装 OCR 识别；不可用即降级半自动。

    用户主权：绝不问"要不要装 ddddocr/onnxruntime"，只在用户已表达"全自动登录"
    （--auto-login）时自动试装，装不上自动落到人工输码。
    """
    if auto_login:
        ocr_ok, reason = ensure_ocr()
        if ocr_ok:
            if not (os.getenv("TONGTU_USER") and os.getenv("TONGTU_PASSWORD")):
                print("[信息] OCR 自动登录需要账号密码：请在 web_automation/.env 配置")
                print("       TONGTU_USER / TONGTU_PASSWORD，否则只能人工输码登录")
            else:
                print("[信息] 尝试 OCR 自动识别验证码登录...")
                try:
                    from tongtu_login_ocr import login as ocr_login
                    if ocr_login(page):
                        print("[OK] OCR 自动登录成功")
                        return True
                    print("[信息] OCR 识别多次失败，降级人工输码")
                except ImportError:
                    pass
        else:
            print(f"[信息] OCR 不可用（{reason}），改人工登录")
    return _semi_auto_login(page, show_expired=show_expired)


def run():
    # --export-cookies: 提取 cookies 供 MCP 注入使用
    if "--export-cookies" in sys.argv:
        export_cookies()
        return

    fresh = "--fresh" in sys.argv
    auto_login = "--auto-login" in sys.argv

    if fresh and PROFILE_DIR.exists():
        print("[信息] --fresh: 清除旧的登录会话...")
        shutil.rmtree(PROFILE_DIR)

    first_run = not PROFILE_DIR.exists()
    if first_run:
        print("[信息] 首次运行，将创建持久化浏览器会话")

    # 确保输出目录存在
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        print("[信息] 打开库存结存页面...")
        page.goto(TONGTU_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)

        if is_already_logged_in(page):
            print("[OK] 检测到已登录会话，自动继续...")
        elif not _try_login(page, auto_login=auto_login, show_expired=not first_run):
            print("[错误] 登录超时，请重试")
            context.close()
            sys.exit(1)

        # 确保筛选项正确
        print("\n[信息] 确认筛选条件...")
        ensure_toggle(page, "allWarehouseTypeBtn", "全部(非FBA)")
        ensure_toggle(page, "statusBtn", "已启用")

        # --list-warehouses: 只列页面仓库，供对照更新 WAREHOUSES
        if "--list-warehouses" in sys.argv:
            list_warehouses_on_page(page)
            context.close()
            return

        # 依次导出每个仓库
        total = len(WAREHOUSES)
        failed_warehouses: list[str] = []
        skipped_empty: list[str] = []
        for idx, wh in enumerate(WAREHOUSES, 1):
            print(f"\n{'='*50}")
            print(f"[{idx}/{total}] 处理仓库: {wh}")
            print(f"{'='*50}")

            # 选仓失败绝不能继续导出——否则会导出"当前仍选中"的上一仓库，
            # 却冠以目标仓库文件名，静默混入合并清单（2026-09-03 实测踩中）。
            # ExtJS toggle 渲染慢会 5s 超时，先重试一次再判定失败。
            selected = select_warehouse(page, wh, WAREHOUSES)
            if not selected:
                print(f"  [重试] {wh}: 首次选仓失败，再试一次...")
                selected = select_warehouse(page, wh, WAREHOUSES)
            if not selected:
                print(f"  [跳过] {wh}: 两次选仓均失败，本次不导出该仓（避免串仓错数据）")
                failed_warehouses.append(wh)
                continue
            inv_path = export_inventory_with_retry(page, wh)
            if inv_path is None:
                skipped_empty.append(f"{wh}（可能空仓/无导出文件）")
                continue
            if not run_generate(inv_path, wh):
                failed_warehouses.append(f"{wh}（生成导入文件失败）")
                continue

        context.close()

    if skipped_empty:
        print(f"\n[信息] 以下仓库可能空仓已跳过（不计入失败）: {', '.join(skipped_empty)}")

    if should_exit_after_export_run(failed_warehouses):
        print(f"\n[警告] 以下仓库导出失败: {', '.join(failed_warehouses)}")
        print("        请人工确认其库存，避免合并清单缺仓或串仓。")
        merge_all_inventory()
        ok = total - len(failed_warehouses) - len(skipped_empty)
        print(
            f"\n[失败] 成功 {ok}/{total} 个仓库"
            f"（跳过可能空仓 {len(skipped_empty)}），退出码 1（定时任务可据此告警）"
        )
        sys.exit(1)

    print(f"\n{'='*50}")
    if skipped_empty:
        ok = total - len(skipped_empty)
        print(f"[完成] {ok}/{total} 个仓库已导出，{len(skipped_empty)} 个可能空仓已跳过")
    else:
        print(f"[完成] 全部 {total} 个仓库已处理！")
    print(f"  下载文件: {DOWNLOADS_DIR}")
    print(f"  导入文件: {OUTPUT_DIR}")

    # 合并多仓原始清单
    merge_all_inventory()


def merge_all_inventory():
    """将 downloads/ 下所有仓库的原始清单合并为一个 Excel"""
    try:
        import pandas as pd
    except ImportError:
        print("[跳过] 合并步骤需 pandas（已在 pyproject.toml 中声明）")
        return

    all_dfs = []
    for wh in WAREHOUSES:
        prefix = safe_prefix(wh)
        # Windows 文件名编码坑:
        # Playwright download.suggested_filename 在 GBK 环境下可能返回乱码，
        # 导致磁盘上的中文文件名变为 mojibake（如 "¿â´æ½á´æÇåµ¥"）。
        # 因此不能用中文关键词匹配，改为前缀 + .xlsx 后缀匹配。
        all_files = list(DOWNLOADS_DIR.iterdir())
        files = sorted(
            [f for f in all_files if inventory_download_matches_warehouse(f.name, wh)],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            print(f"  [跳过] {wh}: 未找到下载文件")
            continue
        path = files[0]
        print(f"  [合并] {wh}  →  {path.name}")

        df = pd.read_excel(path, header=None)
        header_mask = df.iloc[:, 0].astype(str).str.strip() == "SKU"
        if header_mask.sum() == 0:
            print(f"    [警告] 未找到 SKU 表头，跳过")
            continue
        header_idx = header_mask[header_mask].index[0]
        df.columns = df.iloc[header_idx].astype(str).str.replace("\n", "").str.strip()
        df = df.iloc[header_idx + 1:]
        sku_col = df.columns[0]
        df = df[~df[sku_col].astype(str).str.strip().isin(["数量总计", "金额总计", "", "nan"])]
        df = df[df[sku_col].notna()]
        all_dfs.append(df)

    if not all_dfs:
        print("[警告] 没有可合并的数据")
        return

    merged = pd.concat(all_dfs, ignore_index=True)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    merged_path = OUTPUT_DIR / f"通途合并库存结存清单 {ts}.xlsx"
    merged.to_excel(merged_path, index=False, sheet_name="合并库存")
    print(f"  [OK] 合并完成: {len(merged)} 行 → {merged_path}")


if __name__ == "__main__":
    run()
