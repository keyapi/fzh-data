from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime
from pathlib import Path
from .paths import data_root, load_manifest
from .download import pull
from .history import pull_history, status as history_status
from .recommend import recommend, to_report, meta
from .refresh import refresh_sku
from . import decide as decide_mod
from . import en_live


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
    for name in ("doctor", "pull", "recommend", "batch", "refresh", "history", "pull-history",
                 "supply", "decide"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", default=None)
        p.add_argument("--manifest", default=None)
        if name in ("supply", "decide"):
            p.add_argument("--branch", required=True)
        if name == "supply":
            p.add_argument("--out", default=None)
        if name == "decide":
            p.add_argument("--as-of", default=None)
            p.add_argument("--stock", default=None)
            p.add_argument("--backlog", default=None)
            p.add_argument("--po", default=None)
            p.add_argument("--po-tongtool", default=None)
            p.add_argument("--forecast-root", default=None)
            p.add_argument("--demand-netting", default=None)
            p.add_argument("--snapshot-date", default=None)
            p.add_argument("--json", action="store_true")
        if name == "pull":
            p.add_argument("--env-file", default=None)
            p.add_argument("--base", default="https://erpnext.vilavi.cn")
        if name == "pull-history":
            p.add_argument("--env-file", default=None)
            p.add_argument("--base", default="https://erpnext.vilavi.cn")
            p.add_argument("--version", default=None)
            p.add_argument("--names", default=None, help="逗号分隔，只取部分文件")
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
            p.add_argument("--sku", required=True)
            p.add_argument("--env-file", default=None)
    args = parser.parse_args(argv)
    return {"doctor": doctor, "pull": command_pull, "recommend": command_recommend,
            "batch": command_batch, "refresh": command_refresh,
            "history": command_history,
            "pull-history": command_pull_history,
            "supply": command_supply,
            "decide": command_decide}[args.command](args)


def command_refresh(args):
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


def command_history(args):
    root = data_root(args.data_root)
    info = history_status(root)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info["status"] == "ok" else 1


def command_pull_history(args):
    root = data_root(args.data_root, create=True)
    names = [x.strip() for x in (args.names or "").split(",") if x.strip()] or None
    info = pull_history(root, version=args.version, env_file=args.env_file,
                        base=args.base, names=names)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def command_supply(args):
    """抓取实时库存/开放 SO/开放 PO 到 <data-root>/live/，供 decide 使用。"""
    root = data_root(args.data_root, create=True)
    out = Path(args.out) if args.out else Path(root) / "live"
    out.mkdir(parents=True, exist_ok=True)
    from self_fulfilled_demand.canonical import load_sku_map, load_warehouse_config
    sku_path = next((p for p in (Path(root) / "data" / "sku_map.tsv",
                                 Path(root) / "sku_map.tsv") if p.exists()), None)
    sku_map = load_sku_map(sku_path) if sku_path else None
    result = {"out": str(out)}
    stock, stock_meta = en_live.fetch_stock_snapshot()
    stock.to_parquet(out / "stock.parquet", index=False)
    result["stock"] = stock_meta
    try:
        so, so_meta = en_live.fetch_open_so(args.branch, sku_map=sku_map,
                                            warehouse_cfg=load_warehouse_config())
        so[["canonical_sku", "canonical_warehouse", "canonical_uom", "quantity"]].to_csv(
            out / "backlog.csv", index=False)
        result["so"] = so_meta
    except Exception as exc:  # noqa: BLE001 - 失败保留未知，不阻断库存
        result["so"] = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        po, po_meta = en_live.fetch_open_po()
        po[["document_key", "sku", "ordered", "open_qty", "warehouse"]].to_csv(
            out / "po_open.tsv", sep="\t", header=None, index=False)
        result["po"] = po_meta
    except Exception as exc:  # noqa: BLE001
        result["po"] = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_decide(args):
    root = data_root(args.data_root)
    live = Path(root) / "live"
    stock = Path(args.stock) if args.stock else live / "stock.parquet"
    backlog = Path(args.backlog) if args.backlog else live / "backlog.csv"
    po = Path(args.po) if args.po else live / "po_open.tsv"
    as_of = args.as_of or datetime.now().astimezone().replace(microsecond=0).isoformat()
    frame, info = decide_mod.run(
        root, args.branch, as_of,
        stock_path=stock if stock.exists() else None,
        backlog_path=backlog if backlog.exists() else None,
        po_path=po if po.exists() else None,
        po_tongtool_path=Path(args.po_tongtool) if args.po_tongtool else None,
        forecast_root=args.forecast_root,
        demand_netting=args.demand_netting,
        snapshot_date=args.snapshot_date,
        pack_manifest=args.manifest,
    )
    if args.json:
        print(json.dumps({"meta": info,
                          "rows": json.loads(frame.to_json(orient="records", force_ascii=False))},
                         ensure_ascii=False, indent=2))
    else:
        print(decide_mod.to_report(frame, info))
    return 0
