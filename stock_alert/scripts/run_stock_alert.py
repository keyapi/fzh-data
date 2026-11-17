"""无人值守包装：跑通途低库存扫描并推钉钉，跑挂时推一条失败告警。

设计取舍（同 parcel_track）：**失败也要出声**——无人值守时静默退出最难排查。
所以任何异常都会先尽量推一条失败告警，再原样抛出以留下非零退出码。

用法（定时任务里用）：
    uv run python stock_alert/scripts/run_stock_alert.py
    uv run python stock_alert/scripts/run_stock_alert.py -- --warehouses "美中-FZH-DANEEY"
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

        notify_failure(message, title="通途低库存任务失败")
        print("[告警] 已推送失败告警到钉钉", file=sys.stderr)
    except Exception as exc:  # 告警本身失败不能盖住主流程
        print(f"[告警] 发送不成功：{exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    from stock_alert.cli import _load_env, main as cli_main

    extra = list(argv if argv is not None else sys.argv[1:])
    try:
        return cli_main(["run", "--notify", *extra])
    except Exception as exc:
        _load_env()
        _alert(f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
