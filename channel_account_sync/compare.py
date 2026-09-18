# -*- coding: utf-8 -*-
"""Compare Google Sheet 渠道账号 vs EN Channel Account; write a change-only plan."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from channel_account_sync.plan import build_plan

OUT = Path(__file__).resolve().parent / "out"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", type=Path, default=OUT / "channel_account_gsheet.json")
    parser.add_argument("--en", type=Path, default=OUT / "channel_account_en.json")
    args = parser.parse_args()
    sheet = json.loads(args.sheet.read_text(encoding="utf-8"))
    en = json.loads(args.en.read_text(encoding="utf-8"))
    plan = build_plan(sheet, en)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "channel_account_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("sheet", plan["n_sheet"], "en", plan["n_en"])
    print("existing need insert", plan["n_existing_need_insert"], "rows", plan["n_owner_rows_existing"])
    print("new accounts", plan["n_new_accounts"], "rows", plan["n_owner_rows_new"])
    print("alias gaps", plan["n_alias_gaps"], "skip", plan["skip"], "forbidden", plan["forbidden"])
    print("new", [x["en_name"] for x in plan["new_accounts"]])


if __name__ == "__main__":
    main()
