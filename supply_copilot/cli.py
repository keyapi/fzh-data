from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from .paths import data_root, load_manifest
from .download import pull
from .recommend import recommend, to_report


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
    frame = recommend(root, args.branch, args.sku, args.limit)
    if args.json:
        print(frame.to_json(orient="records", force_ascii=False, indent=2))
    else:
        print(to_report(frame, args.branch, manifest.get("as_of"), manifest.get("version")))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="supply_copilot", description="供应链 A/B/C/D/E 决策 Copilot（只读回放）")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "pull", "recommend"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", default=None)
        p.add_argument("--manifest", default=None)
        if name == "pull":
            p.add_argument("--env-file", default=None)
            p.add_argument("--base", default="https://erpnext.vilavi.cn")
        if name == "recommend":
            p.add_argument("--branch", required=True)
            p.add_argument("--sku", default=None)
            p.add_argument("--limit", type=int, default=50)
            p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    return {"doctor": doctor, "pull": command_pull, "recommend": command_recommend}[args.command](args)
