"""按地区运行低库存预警（波兰 / 美中+美东），供 Windows 定时任务使用。

地区仓库名放在 Python 源码里（UTF-8），避免 cmd 传中文参数时的编码问题：

    --region poland  -> 波兰-FZHPoland-covers
    --region us      -> 美中-FZH-DANEEY, 美东-CENTRADE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REGIONS = {
    "poland": ["波兰-FZHPoland-covers"],
    "us": ["美中-FZH-DANEEY", "美东-CENTRADE"],
}


def _alert(message: str) -> None:
    try:
        from stock_alert.notify import notify_failure

        notify_failure(message, title="低库存预警任务失败")
        print("[告警] 已推送失败告警到钉钉", file=sys.stderr)
    except Exception as exc:  # 告警本身失败不能盖住主流程
        print(f"[告警] 发送不成功：{exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=sorted(REGIONS), required=True)
    args = parser.parse_args(argv)

    from stock_alert.cli import _load_env, main as cli_main

    try:
        return cli_main(["run", "--notify", "--warehouses", ",".join(REGIONS[args.region])])
    except Exception as exc:
        _load_env()
        _alert(f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
