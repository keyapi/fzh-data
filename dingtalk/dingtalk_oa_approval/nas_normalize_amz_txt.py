# -*- coding: utf-8 -*-
"""账期桶内 Amazon .txt 统一为 {渠道账号}-{YYYY-MM-DD}.txt（仅 NAS FileStation，不改本地同步盘）。

默认 dry-run。加 --apply 才真正 rename_folder。
可用 --local-index 从 LOCAL_NAS_PERIOD_ROOT 只读扫描并生成计划（NAS 路径 = FINANCE_ROOT/桶/相对路径）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_REPO))

from amz_txt_naming import propose_txt_name  # noqa: E402
from nas_admin import ROOT, nas_admin  # noqa: E402
from paths import OA_REPORTS, local_nas_period  # noqa: E402


def index_local_bucket(bucket: str) -> list[dict]:
    root = local_nas_period() / bucket
    out = []
    if not root.is_dir():
        return out
    for p in root.rglob("*.txt"):
        rel = p.relative_to(root)
        person = rel.parts[0] if len(rel.parts) > 1 else ""
        out.append(
            {
                "person": person,
                "name": p.name,
                "rel": str(rel).replace("\\", "/"),
                "local": str(p),
            }
        )
    return out


def nas_path(root: str, bucket: str, rel: str) -> str:
    return f"{root}/{bucket}/{rel}".replace("//", "/")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default="账期20261004-20261103")
    ap.add_argument("--hint-ym", default="2026-10", help="短日期 MMDD 缺年时用的账期月")
    ap.add_argument("--local-index", action="store_true", help="从 LOCAL_NAS_PERIOD_ROOT 列文件")
    ap.add_argument("--apply", action="store_true", help="在 NAS 上执行重命名")
    ap.add_argument("--out", default="", help="报告 json 路径")
    args = ap.parse_args()

    files: list[dict] = []
    if args.local_index:
        for row in index_local_bucket(args.bucket):
            row["nas_path"] = nas_path(str(ROOT), args.bucket, row["rel"])
            files.append(row)
    else:
        nas = nas_admin()
        if not nas.available:
            raise SystemExit("NAS 未连接。请检查 NAS_API/.env 凭证，或加 --local-index 只生成计划。")
        base = f"{ROOT}/{args.bucket}"
        stack = [base]
        while stack:
            folder = stack.pop()
            for it in nas.get_file_list(folder, limit=1000):
                if it.get("is_dir"):
                    stack.append(it["path"])
                elif (it.get("name") or "").lower().endswith(".txt"):
                    rel = (it["path"] or "")[len(str(ROOT)) :].lstrip("/")
                    parts = rel.split("/")
                    files.append(
                        {
                            "person": parts[1] if len(parts) > 2 else "",
                            "name": it.get("name"),
                            "rel": "/".join(parts[1:]) if len(parts) > 1 else it.get("name"),
                            "nas_path": it.get("path"),
                        }
                    )

    plan = []
    for f in files:
        new_name, why = propose_txt_name(f["name"], hint_ym=args.hint_ym)
        rec = {**f, "new_name": new_name, "reason": why}
        if new_name and new_name != f["name"]:
            rec["action"] = "rename"
        else:
            rec["action"] = "skip"
        plan.append(rec)

    renames = [r for r in plan if r["action"] == "rename"]
    print(f"bucket={args.bucket} txt={len(plan)} rename={len(renames)} apply={args.apply}")

    applied = []
    if args.apply and renames:
        nas = nas_admin()
        if not nas.available:
            raise SystemExit("NAS 未连接，无法 --apply")
        for r in renames:
            path = r["nas_path"]
            new_name = r["new_name"]
            resp = nas._fl.rename_folder(path, new_name)
            ok = isinstance(resp, dict) and resp.get("success")
            applied.append({"path": path, "new_name": new_name, "ok": ok, "resp": str(resp)[:300]})
            print(("OK" if ok else "FAIL"), path, "->", new_name)

    out = Path(args.out) if args.out else OA_REPORTS / f"nas_amz_txt_rename_{args.bucket}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "bucket": args.bucket,
        "hint_ym": args.hint_ym,
        "total_txt": len(plan),
        "rename_n": len(renames),
        "applied": args.apply,
        "plan": plan,
        "apply_log": applied,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
