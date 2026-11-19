# -*- coding: utf-8 -*-
"""账期硬关卡：只读核对 Tax{YYYYMM} / Phase3 五张表，PASS/FAIL 表 + 非 0 退出码。

    uv run python amazon_period_tax/scripts/verify_period.py --bucket 账期20260804-20260903
    uv run python amazon_period_tax/scripts/verify_period.py --bucket 20260804-20260903 --tax-only
    uv run python amazon_period_tax/scripts/verify_period.py --bucket ... --phase3-only

默认两项都查；Tax 需要本地桶目录（默认 LOCAL_NAS_PERIOD_ROOT/<bucket>）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "amazon_period_tax"
for p in (_REPO, _REPO / "tongtool_order_cost", _PKG, _REPO / "dingtalk" / "dingtalk_oa_approval"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from verify_period import run_checks  # noqa: E402


def _client(auth: str):
    if auth == "sa":
        from tongtool_order_cost.gsheets import client as gs_client

        return gs_client()
    import gspread
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    sys.path.insert(0, str(_REPO / "google_drive_permissions" / "scripts"))
    from paths import user_oauth_path  # noqa: E402

    creds = Credentials.from_authorized_user_file(
        str(user_oauth_path()), scopes=["https://www.googleapis.com/auth/drive"]
    )
    if creds.expired or not creds.token:
        creds.refresh(Request())
    return gspread.authorize(creds)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Tax/Phase3 对账硬关卡（只读）")
    ap.add_argument("--bucket", required=True, help="账期YYYYMMDD-YYYYMMDD（可省略「账期」）")
    ap.add_argument("--bucket-dir", default="", help="本地账期桶目录（默认 LOCAL_NAS_PERIOD_ROOT/<bucket>）")
    ap.add_argument("--exchange-month", default="", help="汇率列 YYYYMM（默认桶起始月）")
    ap.add_argument("--repair-dir", default="")
    ap.add_argument("--tax-only", action="store_true")
    ap.add_argument("--phase3-only", action="store_true")
    ap.add_argument("--gspread-auth", choices=("sa", "user"), default="sa")
    args = ap.parse_args()

    bucket = args.bucket if args.bucket.startswith("账期") else f"账期{args.bucket}"
    bucket_dir = Path(args.bucket_dir) if args.bucket_dir else None
    if bucket_dir is None:
        try:
            from paths import local_nas_period  # noqa: E402

            candidate = local_nas_period() / bucket
            bucket_dir = candidate if candidate.is_dir() else None
        except Exception:
            bucket_dir = None

    do_tax = not args.phase3_only
    do_phase3 = not args.tax_only
    checks = run_checks(
        _client(args.gspread_auth),
        bucket=bucket,
        bucket_dir=bucket_dir,
        exchange_month=args.exchange_month,
        repair_dir=Path(args.repair_dir) if args.repair_dir else None,
        do_tax=do_tax,
        do_phase3=do_phase3,
    )
    failed = [c for c in checks if not c.ok]
    print(f"bucket={bucket} checks={len(checks)} failed={len(failed)}")
    for c in checks:
        print(c.line())
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
