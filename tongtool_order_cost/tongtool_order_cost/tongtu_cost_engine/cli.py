# -*- coding: utf-8 -*-
"""Phase 0 CLI：快照冻结、配置审计、SKU 审计、列合同校验。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters.en_snapshot import freeze_snapshot, verify_snapshot
from .audit.config_coverage import audit_warehouse_map
from .audit.ref_code import audit_skus
from .domain.bom_cost import compute_phase2
from .domain.split_merge import render_markdown, run_merge_shadow, write_shadow_xlsx
from .domain.fba_shadow import build_fba_shadow
from .domain.run_package import build_run_package
from .domain.writeback_rehearsal import (
    build_writeback_rehearsal,
    render_markdown as render_writeback_markdown,
    write_csv as write_writeback_csv,
    write_xlsx as write_writeback_xlsx,
)
from .writeback.contract import ContractError, validate_header


def _read_header(path: Path) -> list[str]:
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return next(csv.reader(fh))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tongtu_cost_engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="冻结月度快照")
    s.add_argument("--month", required=True)
    s.add_argument("--out-root", required=True)
    s.add_argument("--file", action="append", required=True, help="逻辑名=路径")

    c = sub.add_parser("audit-config", help="仓库配置覆盖审计")
    c.add_argument("--wh-tsv", required=True)
    c.add_argument("--out", required=True)

    r = sub.add_parser("audit-skus", help="SKU/ref_code 审计")
    r.add_argument("--items", required=True)
    r.add_argument("--flags", required=True)
    r.add_argument("--groups", required=True)
    r.add_argument("--ref-map", default=None)
    r.add_argument("--month", default=None)
    r.add_argument("--out", required=True)

    v = sub.add_parser("verify-header", help="写回表列合同校验")
    v.add_argument("--csv", required=True)

    vs = sub.add_parser("verify-snapshot", help="快照 manifest 校验")
    vs.add_argument("--dir", required=True)

    ms = sub.add_parser("merge-shadow", help="拆包合并 shadow（只读，不改成本列）")
    ms.add_argument("--orders", required=True, help="月度快照订单 CSV（raw_YYYYMM.csv）")
    ms.add_argument("--ref-map", required=True, help="Item_ref_code 导出（name/customer_code/variant_of）")
    ms.add_argument("--en-items", default=None, help="EN 订单明细（缺省取订单同目录 en_items_all_089.csv）")
    ms.add_argument("--flags", default=None, help="order_flags.csv（缺省取订单同目录）")
    ms.add_argument("--branch-map", default=None, help="item_group_branch.tsv（缺省取 out/item_group_branch.tsv）")
    ms.add_argument("--bom-cost", default=None,
                    help="BOM Cost List CSV（缺省取 out/bom_cost_product_with_disabled.csv）")
    ms.add_argument("--wh-map", default=None, help="仓库分类映射 TSV（缺省取订单同目录 wh_map.tsv）")
    ms.add_argument("--writeback", default=None, help="写回表 CSV（仅对账；缺省取 out/writeback_YYYYMM.csv）")
    ms.add_argument("--month", required=True)
    ms.add_argument("--out-dir", required=True)

    wr = sub.add_parser("writeback-rehearsal", help="Phase3 写回演练（本地，不写 GS）")
    wr.add_argument("--orders", required=True)
    wr.add_argument("--ref-map", required=True)
    wr.add_argument("--en-items", default=None)
    wr.add_argument("--flags", default=None)
    wr.add_argument("--branch-map", default=None)
    wr.add_argument("--bom-cost", default=None)
    wr.add_argument("--wh-map", default=None)
    wr.add_argument("--writeback", required=True, help="现有写回表（166 列模板 + 映射来源）")
    wr.add_argument("--disabled-items", default=None)
    wr.add_argument("--month", required=True)
    wr.add_argument("--out-dir", required=True)

    pr = sub.add_parser("writeback-run", help="Phase4 canary run 包（本地，不写 GS）")
    pr.add_argument("--orders", required=True)
    pr.add_argument("--ref-map", required=True)
    pr.add_argument("--en-items", default=None)
    pr.add_argument("--flags", default=None)
    pr.add_argument("--branch-map", default=None)
    pr.add_argument("--bom-cost", default=None)
    pr.add_argument("--wh-map", default=None)
    pr.add_argument("--writeback", required=True)
    pr.add_argument("--kit-report", default=None)
    pr.add_argument("--bundle-map", default=None)
    pr.add_argument("--month", required=True)
    pr.add_argument("--runs-root", default=None)
    pr.add_argument("--bucket", default=None)
    pr.add_argument("--allow-duplicate", action="store_true")

    fs = sub.add_parser("fba-shadow", help="FBA 桥接 + 78 列 shadow（本地，不写 GS）")
    fs.add_argument("--month", required=True)
    fs.add_argument("--root", default=".")
    fs.add_argument("--nonfba-csv", default=None)
    fs.add_argument("--bom-cost", default=None)
    fs.add_argument("--ref-map", default=None)
    fs.add_argument("--bundle-map", default=None)
    fs.add_argument("--kit-report", default=None)
    fs.add_argument("--out-dir", default=None)

    fc = sub.add_parser("fba-canary", help="FBA 最小站点桶 canary run 包（本地，不写 GS）")
    fc.add_argument("--month", required=True)
    fc.add_argument("--root", default=".")
    fc.add_argument("--bucket", default=None)
    fc.add_argument("--exclude-sku", action="append", default=None)
    fc.add_argument("--runs-root", default=None)
    fc.add_argument("--allow-duplicate", action="store_true")

    ad = sub.add_parser("fba-alias-dryrun", help="EN alias 登记 dry-run（不写 EN/GS）")
    ad.add_argument("--root", default=".")
    ad.add_argument("--month", action="append", default=None)
    ad.add_argument("--out-root", default=None)

    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        sources = {}
        for item in args.file:
            name, _, path = item.partition("=")
            if not path:
                raise SystemExit(f"--file 需要 逻辑名=路径: {item}")
            sources[name] = Path(path)
        dest = freeze_snapshot(args.month, sources, Path(args.out_root))
        print(dest)
        return 0

    if args.cmd == "audit-config":
        text = audit_warehouse_map(Path(args.wh_tsv))
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
        return 0

    if args.cmd == "audit-skus":
        text = audit_skus(
            Path(args.items), Path(args.flags), Path(args.groups),
            Path(args.ref_map) if args.ref_map else None,
            args.month,
        )
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
        return 0

    if args.cmd == "verify-header":
        try:
            validate_header(_read_header(Path(args.csv)))
        except ContractError as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return 1
        print(json.dumps({"ok": True}, ensure_ascii=False))
        return 0

    if args.cmd == "fba-shadow":
        root = Path(args.root)
        nonfba = Path(args.nonfba_csv) if args.nonfba_csv else (
            root / "out" / "writeback_rehearsal" / args.month / f"writeback_new_{args.month}.csv"
        )
        res = build_fba_shadow(
            month=args.month, root=root,
            nonfba_csv=nonfba if nonfba.exists() else None,
            bom_csv=args.bom_cost, ref_map_csv=args.ref_map,
            bundle_csv=args.bundle_map, kit_report_csv=args.kit_report,
            out_dir=Path(args.out_dir) if args.out_dir else root / "out" / "fba_shadow" / args.month,
        )
        print(json.dumps({"ok": True, **res.stats}, ensure_ascii=False))
        return 0

    if args.cmd == "fba-canary":
        from .domain.fba_run_package import build_fba_run_package

        exclude = args.exclude_sku or ["OSKBG-RSUS-FBA"]
        pkg = build_fba_run_package(
            month=args.month, root=Path(args.root), bucket=args.bucket,
            exclude_skus=exclude,
            runs_root=Path(args.runs_root) if args.runs_root else None,
            allow_duplicate=args.allow_duplicate,
        )
        print(json.dumps({
            "ok": pkg.ok, "run_id": pkg.run_id, "run_dir": str(pkg.run_dir),
            "bucket": pkg.summary["bucket"], "rows": pkg.summary["rows"],
            "totals": pkg.summary["totals"], "status_counts": pkg.summary["status_counts"],
            "diff_totals": pkg.summary["diff_totals"],
            "gates": {g["gate"]: g["status"] for g in pkg.gates},
            "readback": {c["check"]: c["status"] for c in pkg.readback},
        }, ensure_ascii=False))
        return 0

    if args.cmd == "fba-alias-dryrun":
        from .domain.alias_dryrun import build_alias_dryrun

        res = build_alias_dryrun(
            root=Path(args.root),
            months=tuple(args.month or ("202608", "202609")),
            out_root=Path(args.out_root) if args.out_root else None,
        )
        print(json.dumps({"ok": True, **res["summary"], "run_dir": res["run_dir"]},
                         ensure_ascii=False))
        return 0

    if args.cmd == "writeback-run":
        flags = args.flags
        if not flags:
            sibling = Path(args.orders).parent / "order_flags.csv"
            flags = str(sibling) if sibling.exists() else None
        en_items = args.en_items
        if not en_items:
            sibling = Path(args.orders).parent / "en_items_all_089.csv"
            if not sibling.exists():
                raise SystemExit(f"EN 订单明细不存在: {sibling}")
            en_items = str(sibling)
        orders_path = Path(args.orders)
        out_root = orders_path.parents[2] if len(orders_path.parents) > 2 else orders_path.parent
        bom_csv = Path(args.bom_cost) if args.bom_cost else out_root / "bom_cost_product_with_disabled.csv"
        wh_tsv = Path(args.wh_map) if args.wh_map else orders_path.parent / "wh_map.tsv"
        branch_map = Path(args.branch_map) if args.branch_map else out_root / "item_group_branch.tsv"
        bundle_map = Path(args.bundle_map) if args.bundle_map else out_root / "product_bundles.csv"
        kit_report = Path(args.kit_report) if args.kit_report else out_root / "bom_cost_product_with_kits.csv"
        if not bom_csv.exists() or not wh_tsv.exists():
            raise SystemExit("BOM 或仓库映射不存在")
        result = run_merge_shadow(
            args.orders, args.ref_map, en_items, flags,
            branch_map_csv=branch_map if branch_map.exists() else None,
            month=args.month,
        )
        phase2 = compute_phase2(
            result, bom_csv, args.ref_map, wh_tsv, args.writeback,
            bundle_map_csv=bundle_map if bundle_map.exists() else None,
            kit_report_csv=kit_report if kit_report.exists() else None,
        )
        rehearsal = build_writeback_rehearsal(
            result, phase2, args.writeback, month=args.month,
        )
        runs_root = Path(args.runs_root) if args.runs_root else out_root / "runs"
        input_paths = {
            "orders": Path(args.orders), "en_items": Path(en_items),
            "bom_kits": bom_csv, "product_bundles": bundle_map,
            "wh_map": wh_tsv, "item_refcode": Path(args.ref_map),
            "old_writeback": Path(args.writeback),
            "kit_report": kit_report, "branch_map": branch_map,
        }
        if flags:
            input_paths["flags"] = Path(flags)
        prev_bom = out_root / "importBOMCostList_now.csv"
        if prev_bom.exists():
            input_paths["import_bom_prev"] = prev_bom
        disabled = out_root / "bom_disabled_items.txt"
        if disabled.exists():
            input_paths["disabled_items"] = disabled
        package = build_run_package(
            result, phase2, rehearsal,
            input_paths=input_paths,
            runs_root=runs_root, month=args.month, bucket=args.bucket,
            old_writeback_csv=args.writeback, allow_duplicate=args.allow_duplicate,
        )
        payload = {"ok": package.ok, "run_id": package.run_id,
                   "run_dir": str(package.run_dir), **package.summary}
        print(json.dumps(payload, ensure_ascii=False))
        print(package.run_dir / package.summary["canary_file"])
        print(package.run_dir / "diff.xlsx")
        return 0 if package.ok else 1

    if args.cmd == "writeback-rehearsal":
        flags = args.flags
        if not flags:
            sibling = Path(args.orders).parent / "order_flags.csv"
            flags = str(sibling) if sibling.exists() else None
        en_items = args.en_items
        if not en_items:
            sibling = Path(args.orders).parent / "en_items_all_089.csv"
            if not sibling.exists():
                raise SystemExit(f"EN 订单明细不存在，请用 --en-items 指定: {sibling}")
            en_items = str(sibling)
        orders_path = Path(args.orders)
        out_root = orders_path.parents[2] if len(orders_path.parents) > 2 else orders_path.parent
        bom_csv = Path(args.bom_cost) if args.bom_cost else out_root / "bom_cost_product_with_disabled.csv"
        wh_tsv = Path(args.wh_map) if args.wh_map else orders_path.parent / "wh_map.tsv"
        if not bom_csv.exists():
            raise SystemExit(f"BOM Cost List 不存在: {bom_csv}")
        if not wh_tsv.exists():
            raise SystemExit(f"仓库分类映射不存在: {wh_tsv}")
        branch_map = Path(args.branch_map) if args.branch_map else out_root / "item_group_branch.tsv"
        result = run_merge_shadow(
            args.orders, args.ref_map, en_items, flags,
            branch_map_csv=branch_map if branch_map.exists() else None,
            month=args.month,
        )
        bundle_map = out_root / "product_bundles.csv"
        kit_report = out_root / "bom_cost_product_with_kits.csv"
        phase2 = compute_phase2(
            result, bom_csv, args.ref_map, wh_tsv, args.writeback,
            bundle_map_csv=bundle_map if bundle_map.exists() else None,
            kit_report_csv=kit_report if kit_report.exists() else None,
        )
        disabled_path = (
            Path(args.disabled_items) if args.disabled_items
            else out_root / "bom_disabled_items.txt"
        )
        disabled = set()
        if disabled_path.exists():
            disabled = {
                line.strip() for line in disabled_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        rehearsal = build_writeback_rehearsal(
            result, phase2, args.writeback, month=args.month, disabled_items=disabled,
        )
        out_dir = Path(args.out_dir)
        csv = write_writeback_csv(rehearsal, out_dir / f"writeback_new_{args.month}.csv")
        xlsx = write_writeback_xlsx(rehearsal, out_dir / f"writeback_new_{args.month}.xlsx")
        md = out_dir / f"writeback_new_{args.month}.md"
        md.write_text(render_writeback_markdown(rehearsal), encoding="utf-8")
        payload = {"ok": rehearsal.ok, **rehearsal.stats}
        print(json.dumps(payload, ensure_ascii=False))
        print(csv)
        print(xlsx)
        print(md)
        return 0 if rehearsal.ok else 1

    if args.cmd == "verify-snapshot":
        errors = verify_snapshot(Path(args.dir))
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 1

    if args.cmd == "merge-shadow":
        flags = args.flags
        if not flags:
            sibling = Path(args.orders).parent / "order_flags.csv"
            flags = str(sibling) if sibling.exists() else None
        en_items = args.en_items
        if not en_items:
            sibling = Path(args.orders).parent / "en_items_all_089.csv"
            if not sibling.exists():
                raise SystemExit(f"EN 订单明细不存在，请用 --en-items 指定: {sibling}")
            en_items = str(sibling)
        orders_path = Path(args.orders)
        out_root = orders_path.parents[2] if len(orders_path.parents) > 2 else orders_path.parent
        branch_map = Path(args.branch_map) if args.branch_map else out_root / "item_group_branch.tsv"
        result = run_merge_shadow(
            args.orders, args.ref_map, en_items, flags,
            branch_map_csv=branch_map if branch_map.exists() else None,
            month=args.month,
        )
        bom_csv = (
            Path(args.bom_cost) if args.bom_cost
            else out_root / "bom_cost_product_with_disabled.csv"
        )
        wh_tsv = Path(args.wh_map) if args.wh_map else orders_path.parent / "wh_map.tsv"
        wb_csv = Path(args.writeback) if args.writeback else out_root / f"writeback_{args.month}.csv"
        if not bom_csv.exists():
            raise SystemExit(f"BOM Cost List 不存在: {bom_csv}")
        if not wh_tsv.exists():
            raise SystemExit(f"仓库分类映射不存在: {wh_tsv}")
        bundle_map = out_root / "product_bundles.csv"
        kit_report = out_root / "bom_cost_product_with_kits.csv"
        phase2 = compute_phase2(
            result, bom_csv, args.ref_map, wh_tsv,
            wb_csv if wb_csv.exists() else None,
            bundle_map_csv=bundle_map if bundle_map.exists() else None,
            kit_report_csv=kit_report if kit_report.exists() else None,
        )

        out_dir = Path(args.out_dir)
        xlsx = write_shadow_xlsx(result, out_dir / f"merge_shadow_{args.month}.xlsx", phase2)
        md = out_dir / f"merge_shadow_{args.month}.md"
        md.write_text(render_markdown(result, phase2), encoding="utf-8")
        payload = {"ok": result.ok and phase2.ok, **result.stats, **phase2.stats}
        print(json.dumps(payload, ensure_ascii=False))
        print(xlsx)
        print(md)
        return 0 if (result.ok and phase2.ok) else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
