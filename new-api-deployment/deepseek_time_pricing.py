#!/usr/bin/env python3
"""
DeepSeek 峰谷分时定价自动切换脚本

new-api 的 ModelRatio 是静态值，不支持按时间自动切换。
本脚本由 cron 在时段边界准点触发，把 DeepSeek 两个模型的
定价切换到当前时段（高峰/空闲）对应的值。

部署:
  /opt/new-api/deepseek_time_pricing.py

cron（准点触发，幂等）:
  # 周一至周五 9:00 切高峰 / 12:00 切空闲 / 14:00 切高峰 / 18:00 切空闲
  0 9  * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
  0 12 * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
  0 14 * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
  0 18 * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
  # 周末保险: 00:00 确保空闲价
  0 0  * * 0,6  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1

价格来源: 内置常量，从 https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ 拷贝。
2026-08-17 峰谷计价生效；2026-09-10 12:00 起 flash 系列降价（pro 不变）；
2026-09-14 12:00 起 V4 Pro 下线，请求路由到 V4.1 Flash 并按 V4.1 Flash 计费
（V4.1 Flash 单价未单独公布，暂按 flash 系列价目处理，待账单核对）。
DeepSeek 官方调价时只需改 PRICING / PRO_EOL。

幂等: 只有当前值与期望值不一致时才写入 options 表，否则零副作用。

测试参数:
  --simulate peak|off       强制指定时段（会写库）
  --at "YYYY-MM-DD HH:MM"   覆盖当前时间，只打印不写库，用于演练 9/14 Pro 下线分支
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# ========== 配置区 ==========
QUOTA_PER_UNIT = 500000   # $1 = 500,000 额度
USD_RATE = 7.3             # 1 USD = 7.3 RMB

# DeepSeek 官方定价（元/1M tokens）— 2026-09-10 12:00 起生效
# peak=高峰(周一至周五 9-12,14-18), off=空闲(其余)
# flash-vision-exp 与 flash 同价
PRICING = {
    "deepseek-v4-flash": {
        "peak": {"input": 2.0,  "output": 8.0,  "cache": 0.04},
        "off":  {"input": 1.0,  "output": 4.0,  "cache": 0.02},
    },
    "deepseek-v4-flash-vision-exp": {
        "peak": {"input": 2.0,  "output": 8.0,  "cache": 0.04},
        "off":  {"input": 1.0,  "output": 4.0,  "cache": 0.02},
    },
    "deepseek-v4-pro": {
        "peak": {"input": 9.0,  "output": 27.0, "cache": 0.30},
        "off":  {"input": 4.5,  "output": 13.5, "cache": 0.15},
    },
}

# V4 Pro 下线（2026-09-14 12:00）：此后 pro 请求路由到 V4.1 Flash，按其价目计费。
# V4.1 Flash 单价官方未单独公布，暂等同 flash 系列；9/14 后用真实账单核对。
PRO_ROUTES_TO = "deepseek-v4-flash"

# MySQL root 密码不硬编码：从环境变量 MYSQL_ROOT_PASSWORD 或 /opt/new-api/.secrets.env 读取
SECRETS_FILE = Path("/opt/new-api/.secrets.env")

TZ = ZoneInfo("Asia/Shanghai")

PRO_EOL = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
# ============================


def _mysql_password() -> str:
    pwd = os.environ.get("MYSQL_ROOT_PASSWORD", "").strip()
    if pwd:
        return pwd
    if SECRETS_FILE.is_file():
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MYSQL_ROOT_PASSWORD="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("MYSQL_ROOT_PASSWORD 未配置：请设环境变量或写 /opt/new-api/.secrets.env")


def run_mysql(query: str) -> str:
    cmd = [
        "docker", "exec", "-e", f"MYSQL_PWD={_mysql_password()}",
        "-i", "new-api-mysql",
        "mysql", "-uroot", "new_api", "-N", "-B",
        "-e", query,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"MySQL error: {proc.stderr}")
    return proc.stdout.strip()


def get_option(key: str) -> dict:
    out = run_mysql(f"SELECT value FROM options WHERE `key`='{key}'")
    if not out:
        raise RuntimeError(f"option '{key}' not found")
    return json.loads(out)


def set_option(key: str, value: dict) -> None:
    val = json.dumps(value, ensure_ascii=False)
    # value 是 JSON 字符串，不含单引号，可安全嵌入单引号 SQL 字符串
    run_mysql(f"UPDATE options SET value='{val}' WHERE `key`='{key}'")


def is_peak_hour(now: datetime) -> bool:
    """北京时间 周一至周五 9:00-12:00 / 14:00-18:00 为高峰，其余为空闲。"""
    if now.weekday() >= 5:  # 周六日
        return False
    h = now.hour
    return (9 <= h < 12) or (14 <= h < 18)


def calc_ratios(price: dict) -> dict:
    """由官方价格（元/1M）计算 new-api 的 ratios（6 位精度以匹配 DB 存储格式）。"""
    model_ratio = round(price["input"] * QUOTA_PER_UNIT / (1_000_000 * USD_RATE), 6)
    completion_ratio = round(price["output"] / price["input"], 6)
    cache_ratio = round(price["cache"] / price["input"], 6)
    return {
        "model_ratio": model_ratio,
        "completion_ratio": completion_ratio,
        "cache_ratio": cache_ratio,
    }


def _patch_models(current: dict, expected: dict) -> bool:
    """把 expected 的模型值写入 current，返回是否发生变化。"""
    changed = False
    for model, val in expected.items():
        old = current.get(model)
        if old is None or abs(float(old) - float(val)) > 1e-9:
            current[model] = val
            changed = True
    return changed


def main() -> int:
    args = [a for a in sys.argv[1:]]

    # --simulate peak|off 强制指定时段（用于测试）
    period = None
    if "--simulate" in args:
        idx = args.index("--simulate")
        if idx + 1 < len(args):
            period = args[idx + 1]

    # --at "YYYY-MM-DD HH:MM" 覆盖当前时间，仅演练不写库（用于验证 9/14 Pro 下线分支）
    now = datetime.now(TZ)
    dry_run = False
    if "--at" in args:
        idx = args.index("--at")
        if idx + 1 < len(args):
            try:
                now = datetime.strptime(args[idx + 1], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
            except ValueError:
                print(f"  [ERROR] --at 格式应为 'YYYY-MM-DD HH:MM': {args[idx + 1]}")
                return 1
            dry_run = True
        else:
            print("  [ERROR] --at 需要一个时间参数")
            return 1

    if period is None:
        period = "peak" if is_peak_hour(now) else "off"

    print(f"[{now:%Y-%m-%d %H:%M:%S %Z}] 时段: {period}{'（演练，不写库）' if dry_run else ''}")

    # V4 Pro 已于 PRO_EOL 下线，此后路由到 V4.1 Flash 并按其价目计费
    pricing = dict(PRICING)
    if now >= PRO_EOL:
        pricing["deepseek-v4-pro"] = PRICING[PRO_ROUTES_TO]
        print(f"  V4 Pro 已下线(>= {PRO_EOL:%Y-%m-%d %H:%M})，按 {PRO_ROUTES_TO} 价目计费")

    # 计算期望 ratios
    expected = {key: {} for key in ("ModelRatio", "CompletionRatio", "CacheRatio")}
    for model, prices in pricing.items():
        r = calc_ratios(prices[period])
        expected["ModelRatio"][model] = r["model_ratio"]
        expected["CompletionRatio"][model] = r["completion_ratio"]
        expected["CacheRatio"][model] = r["cache_ratio"]

    any_changed = False
    for key in ("ModelRatio", "CompletionRatio", "CacheRatio"):
        try:
            current = get_option(key)
        except RuntimeError as e:
            print(f"  [ERROR] {e}")
            return 1
        if _patch_models(current, expected[key]):
            if dry_run:
                print(f"  {key} 将更新 -> {json.dumps(expected[key], ensure_ascii=False)}")
            else:
                set_option(key, current)
                print(f"  {key} 已更新 -> {json.dumps(expected[key], ensure_ascii=False)}")
            any_changed = True
        else:
            print(f"  {key} 无需变更 ({json.dumps(expected[key], ensure_ascii=False)})")

    if dry_run:
        print("  演练完成（未写库）")
    elif any_changed:
        print("  切换完成")
    else:
        print("  无变更")
    return 0


if __name__ == "__main__":
    sys.exit(main())
