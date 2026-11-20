# -*- coding: utf-8 -*-
"""把 corrections.v1.json 应用到定稿原件，生成 corrected 副本（不覆盖原件）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO, _REPO / "amazon_period_tax"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from correction_policy import BudgetError, PolicyError, load_fx_table, load_policy  # noqa: E402
from remediation import RemediationError, apply_corrections, load_corrections  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrections", required=True)
    ap.add_argument("--period", required=True, help="YYYYMM")
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--evidence-root",
        required=True,
        help="附件根目录（evidence.attachment 相对此目录解析并核验 md5）",
    )
    ap.add_argument("--preview", action="store_true", help="只列出将改哪些格，不写任何文件")
    ap.add_argument(
        "--policy",
        default="",
        help="git 外预授权政策 JSON（F 批）：T1 自动 / T2 窄通道；缺失或过期直接拒绝",
    )
    ap.add_argument(
        "--prior-manifest",
        default="",
        help="上次发布 manifest；输入/政策/proposal hash 变化时旧 PASS 失效并拒绝复用",
    )
    ap.add_argument(
        "--fx",
        default="",
        help="已确认目标月汇率表 JSON/CSV（R1）：正式写 corrected 副本必须声明",
    )
    ap.add_argument(
        "--idempotent",
        action="store_true",
        help="R4 幂等：同一 correction 重复运行只经济应用一次（格值已是 after 视为已应用）",
    )
    ap.add_argument(
        "--approved-input-md5",
        default="",
        help="R2 批准源 hash；与当前输入不符即拒绝（空 proposal 也不能绕过）",
    )
    args = ap.parse_args()

    corrections = load_corrections(Path(args.corrections))
    policy = None
    if args.policy:
        try:
            policy = load_policy(Path(args.policy))
        except PolicyError as e:
            raise SystemExit(f"修正政策无效（拒绝执行）: {e}") from None
    fx = None
    if args.fx:
        try:
            fx = load_fx_table(Path(args.fx), month=args.period)
        except BudgetError as e:
            raise SystemExit(f"汇率表无效（拒绝执行）: {e}") from None
    prior_manifest = None
    if args.prior_manifest:
        prior_manifest = json.loads(Path(args.prior_manifest).read_text(encoding="utf-8"))
    # R2：正式写 corrected 副本（非 preview）必须同时声明 policy + FX。
    if not args.preview and (policy is None or fx is None):
        raise SystemExit(
            "正式生成 corrected 副本必须声明 --policy 与 --fx（policy/证据/源链 + 人民币预算）"
        )
    try:
        result = apply_corrections(
            src=Path(args.src),
            corrections=corrections,
            period=args.period,
            out=Path(args.out),
            evidence_root=Path(args.evidence_root),
            preview=args.preview,
            policy=policy,
            prior_manifest=prior_manifest,
            fx=fx,
            require_fx=not args.preview,
            require_receipt=not args.preview,
            approved_input_md5=args.approved_input_md5 or None,
            idempotent=args.idempotent,
        )
    except RemediationError as e:
        raise SystemExit(f"修正被拒绝（未写任何文件）: {e}") from None
    print(json.dumps(result, ensure_ascii=False, indent=2))



if __name__ == "__main__":
    main()
