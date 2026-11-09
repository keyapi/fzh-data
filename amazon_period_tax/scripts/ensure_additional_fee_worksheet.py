# -*- coding: utf-8 -*-
"""确保 附加费&Tax / 附加费{YYYYMM} 存在；缺失则按 Tax 渠道账号建零行表并 Colab 排序。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "amazon_period_tax"
for p in (_REPO, _REPO / "tongtool_order_cost", _PKG):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from gsheet_tax import (  # noqa: E402
    additional_fee_worksheet_name_from_yyyymm,
    ensure_zero_additional_fee_worksheet,
    open_additional_fee_tax_spreadsheet,
    sort_additional_fee_tax_tabs,
    tax_worksheet_name,
)


def _tax_channels(gc, bucket: str) -> list[str]:
    ws_name = tax_worksheet_name(bucket)
    sh = open_additional_fee_tax_spreadsheet(gc)
    ws = sh.worksheet(ws_name)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    header = rows[0]
    try:
        i = header.index("渠道账号")
    except ValueError:
        return []
    return [r[i] for r in rows[1:] if i < len(r) and str(r[i]).strip()]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange-month", required=True, help="YYYYMM，如 202610")
    ap.add_argument("--bucket", default="", help="可选；从 Tax{YYYYMM} 读渠道账号列")
    ap.add_argument("--template", default="", help="表头模板 ws，默认上一月 附加费")
    ap.add_argument("--sort-only", action="store_true", help="不新建，只按 Colab 规则重排 tab")
    args = ap.parse_args()

    from tongtool_order_cost.gsheets import client as gs_client  # noqa: E402

    gc = gs_client()
    yyyymm = args.exchange_month.strip()
    target = additional_fee_worksheet_name_from_yyyymm(yyyymm)

    if args.sort_only:
        sort_additional_fee_tax_tabs(gc, pin_worksheet=target)
        print(json.dumps({"worksheet": target, "sorted": True}, ensure_ascii=False))
        return

    channels: list[str] = []
    if args.bucket:
        channels = _tax_channels(gc, args.bucket)
    report = ensure_zero_additional_fee_worksheet(
        gc,
        yyyymm=yyyymm,
        channel_accounts=channels or None,
        template_worksheet=args.template or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
