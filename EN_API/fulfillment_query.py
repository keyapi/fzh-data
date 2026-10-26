#!/usr/bin/env python3
"""统一履约查询入口（多输入 / 阶段 0–3 / 证据分层 / 异常与下一行动）。

实现见 EN_API/fulfillment/；本文件只是入口，保证 `import fulfillment` 与
`import item_shipment_status` 都能解析。

示例:
  uv run python EN_API/fulfillment_query.py --codes CENKZ1325-Yellow-138
  uv run python EN_API/fulfillment_query.py --codes "码A,码B" --json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from fulfillment.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
