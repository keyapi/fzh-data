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

from correction_policy import PolicyError, load_policy  # noqa: E402
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
    args = ap.parse_args()

    corrections = load_corrections(Path(args.corrections))
    policy = None
    if args.policy:
        try:
            policy = load_policy(Path(args.policy))
        except PolicyError as e:
            raise SystemExit(f"修正政策无效（拒绝执行）: {e}") from None
    prior_manifest = None
    if args.prior_manifest:
        prior_manifest = json.loads(Path(args.prior_manifest).read_text(encoding="utf-8"))
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
        )
    except RemediationError as e:
        raise SystemExit(f"修正被拒绝（未写任何文件）: {e}") from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
