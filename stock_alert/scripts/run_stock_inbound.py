"""无人值守包装：跑昨日采购入库汇总并推钉钉，跑挂时推一条失败告警。

用法（定时任务里用）：
    uv run python stock_alert/scripts/run_stock_inbound.py
    uv run python stock_alert/scripts/run_stock_inbound.py -- --date 2026-11-16
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _alert(message: str) -> None:
    try:
        from stock_alert.notify import notify_failure

        notify_failure(message, title="通途入库任务失败")
        print("[告警] 已推送失败告警到钉钉", file=sys.stderr)
    except Exception as exc:  # 告警本身失败不能盖住主流程
        print(f"[告警] 发送不成功：{exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    from stock_alert.cli import _load_env, main as cli_main

    extra = list(argv if argv is not None else sys.argv[1:])
    try:
        return cli_main(["inbound", "--notify", *extra])
    except Exception as exc:
        _load_env()
        _alert(f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
