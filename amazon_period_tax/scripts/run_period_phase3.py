# -*- coding: utf-8 -*-
"""本地 Phase3：钉钉 OA 核算定稿 + 附加费/Tax → GSheet「钉钉OA收款费用…」。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "amazon_period_tax"
for p in (_REPO, _REPO / "tongtool_order_cost", _PKG):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from phase3_merge import run_phase3  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Colab Phase3 本地移植")
    ap.add_argument("--in", dest="src", required=True, help="核算定稿 xlsx（含 sheet 核算行）")
    ap.add_argument("--bucket", required=True, help="账期YYYYMMDD-YYYYMMDD 桶名")
    ap.add_argument("--exchange-month", required=True, help="汇率/运营人员/附加费/Tax 的 YYYYMM")
    ap.add_argument("--write-gsheet", action="store_true", help="写 Phase3 目标 GSheet")
    ap.add_argument(
        "--gspread-auth",
        choices=("sa", "user"),
        default="sa",
        help="sa=服务账号（默认）；user=用户 OAuth（需可刷新，用于 Phase3 写表 + 用用户身份给 SA 授权）",
    )
    ap.add_argument("--out-dir", default="", help="可选：写 run 报告 JSON")
    ap.add_argument("--dry-run", action="store_true", help="只算不写 GSheet（默认与未传 --write-gsheet 相同）")
    args = ap.parse_args()

    def _gspread_client():
        if args.gspread_auth == "sa":
            from tongtool_order_cost.gsheets import client as gs_client  # noqa: E402

            return gs_client()
        import gspread
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        sys.path.insert(0, str(_REPO / "google_drive_permissions" / "scripts"))
        from paths import user_oauth_path  # noqa: E402

        path = user_oauth_path()
        # 与 `google_drive_permissions/scripts/*.py` 一致，避免 refresh 因 scope 漂移失败
        scopes = ["https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_authorized_user_file(str(path), scopes=scopes)
        if creds.expired or not creds.token:
            creds.refresh(Request())
        return gspread.authorize(creds)

    gc = _gspread_client()
    write = args.write_gsheet and not args.dry_run
    rep, _frames = run_phase3(
        gc=gc,
        input_xlsx=Path(args.src),
        bucket=args.bucket,
        exchange_month=args.exchange_month,
        write_gsheet=write,
    )
    payload = rep.__dict__
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"phase3_{args.exchange_month}_{ts}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {path}")


if __name__ == "__main__":
    main()
