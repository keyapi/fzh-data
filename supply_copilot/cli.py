from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from .paths import data_root, load_manifest
from .download import pull
from .recommend import recommend, to_report, meta
from .refresh import refresh_sku

def doctor(args):
    root = data_root(args.data_root)
    manifest = load_manifest(args.manifest)
    missing = [f["path"] for f in manifest["files"] if not (root / f["path"]).exists()]
    print(json.dumps({"data_root": str(root), "pack_version": manifest.get("version"),
                      "as_of": manifest.get("as_of"), "missing_files": missing,
                      "status": "ok" if not missing else "incomplete"}, ensure_ascii=False, indent=2))
    return 0 if not missing else 1


def command_pull(args):
    root = data_root(args.data_root, create=True)
    manifest = load_manifest(args.manifest)
    pull(manifest, root, env_file=args.env_file, base=args.base)
    print(f"已下载并校验 {manifest['version']} -> {root}")
    return 0


def command_recommend(args):
    root = data_root(args.data_root)
    manifest = load_manifest(args.manifest)
    frame = recommend(root, args.branch, args.sku, args.limit,
                      d6_version=args.d6_version, like=args.like)
    if args.json:
        print(json.dumps({"meta": meta(frame, args.branch, manifest.get("as_of"),
                                      manifest.get("version")),
                          "rows": json.loads(frame.to_json(orient="records", force_ascii=False))},
                         ensure_ascii=False, indent=2))
    else:
        print(to_report(frame, args.branch, manifest.get("as_of"), manifest.get("version")))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="supply_copilot", description="供应链 A/B/C/D/E 决策 Copilot（只读回放）")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "pull", "recommend", "batch", "refresh"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", default=None)
        p.add_argument("--manifest", default=None)
        if name == "pull":
            p.add_argument("--env-file", default=None)
            p.add_argument("--base", default="https://erpnext.vilavi.cn")
        if name == "recommend":
            p.add_argument("--branch", required=True)
            p.add_argument("--sku", default=None)
            p.add_argument("--limit", type=int, default=None,
                           help="可选取前 N 行；默认全部，不静默截断")
            p.add_argument("--d6-version", choices=["v6_22", "v6_24"], default="v6_22")
            p.add_argument("--like", action="store_true", help="模糊匹配；默认精确 SKU")
            p.add_argument("--json", action="store_true")
        if name == "batch":
            p.add_argument("--branch", required=True)
        if name == "refresh":
            p.add_argument("--branch", required=True)
            p.add_argument("--sku", default=None, help="单 SKU；与 --all 互斥")
            p.add_argument("--all", action="store_true", dest="all_rows",
                           help="遍历该分公司池的全部 D6 行")
            p.add_argument("--as-of", default=None, help="刷新时点；默认取包清单 as_of")
            p.add_argument("--out", default=None,
                           help="私有输出目录（快照 JSON + report.json）；给定时走批量口径")
            p.add_argument("--period-start", default=None,
                           help="显式期间起点 YYYY-MM-DD（与 --period-end 同时给）")
            p.add_argument("--period-end", default=None,
                           help="显式期间终点 YYYY-MM-DD")
            p.add_argument("--d6-version", choices=["v6_22", "v6_24"], default="v6_22")
            p.add_argument("--horizon", type=int, choices=[97, 157], default=97,
                           help="D5 预测期（整期）天数；默认 97")
            p.add_argument("--live-snapshot", default=None,
                           help="离线 EN 库存快照 JSON（免网络，便于复跑）")
            p.add_argument("--env-file", default=None)
            p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    return {"doctor": doctor, "pull": command_pull, "recommend": command_recommend,
            "batch": command_batch, "refresh": command_refresh}[args.command](args)


def command_refresh(args):
    if args.all_rows and args.sku:
        raise SystemExit("--all 与 --sku 互斥，请只给一个")
    if not args.all_rows and not args.sku:
        raise SystemExit("需要 --sku 或 --all")
    if args.out:
        from .batch import refresh_pool, summary_text, write_outputs
        root = data_root(args.data_root)
        result = refresh_pool(
            root, args.branch, as_of=args.as_of,
            period_start=args.period_start, period_end=args.period_end,
            sku=None if args.all_rows else args.sku,
            d6_version=args.d6_version, horizon=args.horizon,
            env_file=args.env_file, live_snapshot=args.live_snapshot,
            manifest=load_manifest(args.manifest))
        paths = write_outputs(args.out, result)
        if args.json:
            print(json.dumps(result["report"], ensure_ascii=False, indent=2))
        else:
            print(summary_text(result, paths))
        return 0
    if args.all_rows:
        raise SystemExit("--all 需要 --out 私有输出目录（快照 + report.json），"
                         "避免把全量结果丢到临时目录")
    root = data_root(args.data_root)
    rows = refresh_sku(root, args.branch, args.sku, env_file=args.env_file)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def command_batch(args):
    root = data_root(args.data_root)
    frame = recommend(root, args.branch, None, None)
    info = meta(frame, args.branch, load_manifest(args.manifest).get("as_of"),
                load_manifest(args.manifest).get("version"))
    print(json.dumps(info, ensure_ascii=False))
    counts = frame.groupby("建议动作").agg(键数=("product_id", "count"),
                                          新补=("新补数量", "sum"),
                                          催已有=("催已有量", "sum")).reset_index()
    print(counts.to_string(index=False))
    print(f"总计 {len(frame)} 行（全部返回，未截断）")
    return 0
