#!/usr/bin/env python3
"""
通途库存清单导出脚本（CDP 浏览器版）
使用 computer-use 的 CDP 浏览器导出所有仓库库存
"""
import subprocess, sys, time, shutil
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent
DOWNLOADS_DIR = WEB_ROOT / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

WAREHOUSES = [
    "CENTRADE",
    "FZHPoland-covers",
    "FZH-DANEEY-皮壳仓库",
    "FZH-DANEEY-退货产品仓",
    "FZH-DANEEY-成品仓",
    "FZH-DANEEY-半成品仓",
]

COMPUTER_TOOL = "/root/.codebuddy/skills/computer-use/scripts/computer_tool.py"

def run_tool(action, **kwargs):
    """Run computer_tool.py with given action"""
    cmd = ["python3", COMPUTER_TOOL, f'{{"action": "{action}"' + "," + ",".join(f'"{k}": "{v}"' for k, v in kwargs.items()) + "}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout, result.stderr, result.returncode

def safe_prefix(name):
    return name.replace("/", "-").replace("\\", "-").replace(":", "-")

def get_latest_download():
    """Get the latest xlsx file from Downloads"""
    downloads = Path("/root/Downloads")
    files = sorted(downloads.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def export_warehouse(warehouse_name, idx, total):
    print(f"\n{'='*50}")
    print(f"[{idx}/{total}] 处理仓库: {warehouse_name}")
    print(f"{'='*50}")
    
    # 1. 切换到目标仓库
    print(f"  [操作] 切换至: {warehouse_name}")
    # 使用 evaluate 点击，避免中文/特殊字符在 selector 中的问题
    js_click = f'document.querySelector("#warehouseDisableDiv").querySelectorAll("a").forEach(a => {{ if(a.textContent.trim() === "{warehouse_name}") a.click(); }});'
    stdout, stderr, rc = run_tool("browser_eval", expression=js_click)
    if rc != 0:
        print(f"  [错误] 切换失败: {stderr}")
        return False
    time.sleep(5)  # 等待数据加载
    
    # 2. 点击导出
    print(f"  [操作] 点击导出Excel...")
    stdout, stderr, rc = run_tool("browser_click", selector="a:has-text(\"导出Excel\")")
    if rc != 0:
        print(f"  [错误] 导出失败: {stderr}")
        return False
    time.sleep(3)  # 等待下载
    
    # 3. 复制并重命名文件
    latest = get_latest_download()
    if not latest:
        print(f"  [错误] 未找到下载文件")
        return False
    
    prefix = safe_prefix(warehouse_name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{prefix}_库存结存清单{ts}.xlsx"
    target = DOWNLOADS_DIR / new_name
    shutil.copy(str(latest), str(target))
    print(f"  [OK] 已保存: {new_name} ({target.stat().st_size / 1024:.0f} KB)")
    return True

def main():
    # 已完成的仓库（跳过）
    done = ["CENTRADE", "FZHPoland-covers"]
    remaining = [w for w in WAREHOUSES if w not in done]
    
    total = len(WAREHOUSES)
    current = 3  # 从第3个开始
    
    for wh in remaining:
        export_warehouse(wh, current, total)
        current += 1
        time.sleep(2)
    
    print(f"\n{'='*50}")
    print(f"[完成] 全部 {total} 个仓库已处理！")
    print(f"  下载文件: {DOWNLOADS_DIR}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
