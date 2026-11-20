# -*- coding: utf-8 -*-
"""非 Amazon 附件最小证据（只读）：CSV/XLSX 金额出现性 → 人工签字清单。

    uv run python amazon_period_tax/scripts/audit_oa_attachments.py \
        --items items.json --signatures signed.json --out worklist.json

``items.json``::

    {"items": [
      {"row_id": "202609091225...|2026-09-11|WFUS|123.45",
       "platform": "Walmart", "account": "WFUS", "currency": "USD",
       "amount": "123.45", "attachment": "D:/.../WFUS-2026-09-11.csv",
       "format": {"encoding": "utf-8", "delimiter": ",", "decimal_separator": "."}}
    ]}

- 0 命中 → ``mismatch``，>1 → ``ambiguous``，恰好 1 → ``occurrence_only``（仍需签字）。
- PDF/图片/XLS/ZIP/未知格式 → ``unsupported``，进人工清单，不从分母消失。
- 已签字条目会校验附件 hash / 签字有效期 / 抄录金额；**脚本不会自己填签字字段**。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

_HERE = Path(__file__).resolve()
_PKG = _HERE.parents[1]
_DING = _HERE.parents[2] / "dingtalk" / "dingtalk_oa_approval"
for _p in (_PKG, _DING):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from attachment_evidence import (  # noqa: E402
    AmountFormat,
    ManualEntry,
    build_entry,
    find_amount_occurrences,
    sha256_file,
    worklist_summary,
)


def _load_signatures(path: str) -> dict[str, dict]:
    if not path:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for rec in raw.get("signatures") or raw.get("entries") or []:
        rid = str(rec.get("row_id") or "")
        if rid:
            out[rid] = rec
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True, help="待核附件清单 JSON")
    ap.add_argument("--signatures", default="", help="已签字清单 JSON（可选）")
    ap.add_argument("--out", required=True, help="输出 worklist JSON（只写这里）")
    ap.add_argument("--today", default="", help="覆盖今天（测试/复算用，YYYY-MM-DD）")
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    payload = json.loads(Path(args.items).read_text(encoding="utf-8"))
    signatures = _load_signatures(args.signatures)
    entries: list[ManualEntry] = []
    invalid_signatures: list[dict] = []

    for item in payload.get("items") or []:
        attachment = Path(str(item.get("attachment") or ""))
        row_id = str(item.get("row_id") or "")
        amount = item.get("amount")
        amount_d = None if amount in (None, "") else Decimal(str(amount))
        fmt = AmountFormat(**(item.get("format") or {}))
        if not attachment.is_file():
            entry = build_entry(
                row_id=row_id,
                platform=str(item.get("platform") or ""),
                account=str(item.get("account") or ""),
                currency=str(item.get("currency") or ""),
                oa_amount=amount_d,
                attachment_name=attachment.name,
                attachment_sha256="",
                reason="attachment_missing",
            )
        else:
            result = find_amount_occurrences(attachment, amount_d, fmt=fmt) if amount_d is not None else None
            entry = build_entry(
                row_id=row_id,
                platform=str(item.get("platform") or ""),
                account=str(item.get("account") or ""),
                currency=str(item.get("currency") or ""),
                oa_amount=amount_d,
                attachment_name=attachment.name,
                attachment_sha256=sha256_file(attachment),
                result=result,
            )
        sig = signatures.get(row_id)
        if sig:
            entry.transcribed_value = (
                None if sig.get("transcribed_value") in (None, "") else Decimal(str(sig.get("transcribed_value")))
            )
            entry.transcribed_note = str(sig.get("transcribed_note") or "")
            entry.checker = str(sig.get("checker") or "")
            entry.finance_reviewer = str(sig.get("finance_reviewer") or "")
            entry.approved_at = str(sig.get("approved_at") or "")
            entry.valid_until = str(sig.get("valid_until") or "")
            entry.proposal_hash = str(sig.get("proposal_hash") or "")
            entry.status = str(sig.get("status") or "signed")
            ok, why = entry.is_signed(today=today, observed_sha256=entry.attachment_sha256)
            if not ok:
                invalid_signatures.append({"row_id": row_id, "reason": why})
        entries.append(entry)

    out = {
        "generated_at": f"{today.isoformat()}T00:00:00",
        "summary": worklist_summary(entries, today=today),
        "invalid_signatures": invalid_signatures,
        "entries": [e.to_dict() for e in entries],
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out["summary"], ensure_ascii=False))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
