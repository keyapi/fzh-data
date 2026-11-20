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

from phase3_merge import PublishOptions, run_phase3  # noqa: E402


def _load_corrections(path: str, period: str, policy, *, now=None):
    """读取 corrections 凭据并按政策判定（不写任何表）。"""
    import json

    from correction_policy import PolicyError, build_proposals, evaluate_batch

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    proposals = build_proposals(payload, period=period)
    results = evaluate_batch(proposals, policy, now=now, expected_period=period)
    return proposals, list(results.results)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Colab Phase3 本地移植")
    ap.add_argument("--in", dest="src", required=True, help="核算定稿 xlsx（含 sheet 核算行）")
    ap.add_argument("--bucket", required=True, help="账期YYYYMMDD-YYYYMMDD 桶名")
    ap.add_argument("--exchange-month", required=True, help="汇率/运营人员/附加费/Tax 的 YYYYMM")
    ap.add_argument("--write-gsheet", action="store_true", help="写 Phase3 目标 GSheet")
    ap.add_argument(
        "--write-gsheet-fba",
        action="store_true",
        help="额外写 {期}FBA费用扣减后分类汇总 / FBA费用扣减后收款比例运营人员（只算不写的反向开关）",
    )
    ap.add_argument(
        "--bucket-dir",
        default="",
        help="账期桶目录（生成 FBA 两张表用；默认 LOCAL_NAS_PERIOD_ROOT/<bucket>）",
    )
    ap.add_argument("--repair-dir", default="", help="FBA 源 txt tab 修复缓存目录")
    ap.add_argument(
        "--allow-empty-tax",
        action="store_true",
        help="显式允许 Tax{YYYYMM}/附加费{YYYYMM} 为空或缺必需列（默认直接报错，防止静默少算）",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="有未匹配渠道账号 / 币种未匹配汇率 / Tax 别名未匹配 / 合并重复等 warning 时非 0 退出",
    )
    ap.add_argument(
        "--correction-policy",
        default="",
        help="git 外预授权政策 JSON（R2）：正式发布必须声明；缺/过期/未授权 T2 一律拒绝写入",
    )
    ap.add_argument(
        "--corrections",
        default="",
        help="corrections 凭据 JSON（R2 源链）：正式发布必须声明，可为该期空清单",
    )
    ap.add_argument(
        "--fx",
        default="",
        help="已确认目标月汇率表 JSON/CSV（R1）：正式发布必须声明，缺 FX/币种未确认 writer=0",
    )
    ap.add_argument(
        "--prior-manifest",
        default="",
        help="已批准批次的 manifest（R4）：核对输入与批准源、依赖 hash 与目标基线",
    )
    ap.add_argument(
        "--gspread-auth",
        choices=("sa", "user"),
        default="sa",
        help="sa=服务账号（默认）；user=用户 OAuth（需可刷新，用于 Phase3 写表 + 用用户身份给 SA 授权）",
    )
    ap.add_argument("--out-dir", default="", help="可选：写 run 报告 JSON")
    ap.add_argument("--dry-run", action="store_true", help="只算不写 GSheet（默认与未传 --write-gsheet 相同）")
    args = ap.parse_args()

    writing = (args.write_gsheet or args.write_gsheet_fba) and not args.dry_run
    if writing and not (args.correction_policy and args.corrections and args.fx):
        raise SystemExit(
            "正式发布必须同时声明 --correction-policy / --corrections / --fx"
            "（policy、证据/源链、人民币预算）；缺任一项拒绝写入"
        )

    policy = None
    proposals: list = []
    if args.correction_policy:
        from correction_policy import PolicyError, load_policy

        try:
            policy = load_policy(Path(args.correction_policy))
        except PolicyError as e:
            raise SystemExit(f"修正政策无效（拒绝写入）: {e}") from None
    if args.corrections:
        try:
            proposals, _results = _load_corrections(args.corrections, args.exchange_month, policy)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            raise SystemExit(f"corrections 凭据无效（拒绝写入）: {e}") from None

    fx = None
    if args.fx:
        from correction_policy import BudgetError, load_fx_table

        try:
            fx = load_fx_table(Path(args.fx), month=args.exchange_month)
        except BudgetError as e:
            raise SystemExit(f"汇率表无效（拒绝写入）: {e}") from None

    prior_manifest = None
    approved_input_md5 = None
    prior_runs: list = []
    if args.prior_manifest:
        prior_manifest = json.loads(Path(args.prior_manifest).read_text(encoding="utf-8"))
        approved_input_md5 = prior_manifest.get("input_md5")
        prior_runs = [prior_manifest]
    if writing and not proposals and not approved_input_md5:
        raise SystemExit(
            "正式发布但本批没有任何 corrections：必须用 --prior-manifest 证明批准源=本次输入"
            "（空 proposal 不能当「输入未被修正」的证明）"
        )

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
    bucket_dir = None
    if args.bucket_dir:
        bucket_dir = Path(args.bucket_dir)
    else:
        try:
            from paths import local_nas_period  # noqa: E402

            candidate = local_nas_period() / args.bucket
            bucket_dir = candidate if candidate.is_dir() else None
        except Exception:
            bucket_dir = None
    rep, _frames = run_phase3(
        gc=gc,
        input_xlsx=Path(args.src),
        bucket=args.bucket,
        exchange_month=args.exchange_month,
        bucket_dir=bucket_dir,
        repair_dir=Path(args.repair_dir) if args.repair_dir else None,
        write_gsheet=write,
        write_gsheet_fba=args.write_gsheet_fba and not args.dry_run,
        allow_empty_tax=args.allow_empty_tax,
        write_repairs=not args.dry_run,  # R05：dry-run 不落 tab 修复缓存
        correction_policy=policy,
        correction_proposals=proposals,
        correction_fx=fx,
        approved_input_md5=approved_input_md5,
        prior_runs=prior_runs,
        publish_options=PublishOptions() if write or (args.write_gsheet_fba and not args.dry_run) else None,
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
    if args.strict and rep.warnings:
        print("STRICT 检查未通过:", rep.warnings, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
