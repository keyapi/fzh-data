#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月度盈利审计 CLI（U1 起）。

子命令
------
list      只读列出目标 workbook 的 worksheet 与角色分类（不落盘）。
snapshot  只读盘点 + 把源整值冻结成本地 CSV + manifest（**只读，无任何写路径**）。

设计：无 apply/write/update 任何标志；本文件不 import 任何月度上传函数。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from tongtool_order_cost.audit_sources import (  # noqa: E402
    ARCHIVE,
    RAW,
    SourceSpec,
    classify_worksheet,
    list_worksheet_titles,
    require_successful,
    snapshot_sources,
    write_manifest,
)


def main_repo_root() -> Path:
    common_dir = subprocess.check_output(
        ["git", "rev-parse", "--git-common-dir"], text=True, encoding="utf-8"
    ).strip()
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = Path.cwd() / common_path
    return common_path.resolve().parent


def _derive_names(month: str) -> tuple[str, str]:
    """'202607' → ('通途订单202607', '2026年7月订单')。"""
    m = str(month).strip()
    if len(m) != 6 or not m.isdigit():
        raise ValueError(f"--month 需 YYYYMM 形式，收到 {month!r}")
    year, mm = m[:4], int(m[4:6])
    return f"通途订单{m}", f"{year}年{mm}月订单"


def _setup_credentials(repo: Path) -> None:
    os.environ.setdefault(
        "GSPREAD_SERVICE_ACCOUNT_FILE",
        str(repo / "secrets" / "gsheets-service-account.json"),
    )


def _reader():
    from tongtool_order_cost import gsheets
    from tongtool_order_cost.audit_sources import GspreadSheetReader

    return GspreadSheetReader(gsheets.client())


def default_specs(month: str, worksheets: list[str], spreadsheet: str) -> list[SourceSpec]:
    """按月度命名 + 动态发现的归档，组装默认快照清单。

    只有原始表 `required=True`：它缺失即阻断；派生的 写回*/检查/归档 允许
    单张失败而不阻断（但仍逐条记账）。
    """
    _, raw_ws = _derive_names(month)
    year = month[:4]
    m = int(month[4:6])

    def ws(name: str) -> bool:
        return name in worksheets

    specs: list[SourceSpec] = [
        SourceSpec("raw", spreadsheet, raw_ws, role=RAW, required=True, required_columns=("订单号", "通途SKU")),
    ]
    optional = {
        "raw_fba": f"{year}年{m}月FBA订单",
        "writeback": f"写回{year}年{m}月订单",
        "writeback_fba": f"写回{year}年{m}月FBA订单",
        "writeback_combined": f"写回{year}年{m}月FBA订单和非FBA订单",
        "check": f"检查运营人员-写回{year}年{m}月FBA订单和非FBA订单",
    }
    for key, title in optional.items():
        if ws(title):
            specs.append(SourceSpec(key, spreadsheet, title))
    # 动态发现该月的归档版本（含"节前提交版"）
    idx = 0
    for title in worksheets:
        if classify_worksheet(title, []) == ARCHIVE and raw_ws in title:
            specs.append(SourceSpec(f"archive_{idx}", spreadsheet, title))
            idx += 1
    return specs


def _extra_specs(raw_specs: list[str]) -> list[SourceSpec]:
    """`--extra KEY=SPREADSHEET::WORKSHEET` → SourceSpec。"""
    out: list[SourceSpec] = []
    for item in raw_specs:
        if "=" not in item or "::" not in item:
            raise ValueError(f"--extra 需 KEY=SPREADSHEET::WORKSHEET 形式，收到 {item!r}")
        key, rest = item.split("=", 1)
        spreadsheet, worksheet = rest.split("::", 1)
        out.append(SourceSpec(key.strip(), spreadsheet.strip(), worksheet.strip()))
    return out


def ustx_cost_specs(spreadsheet: str) -> list[SourceSpec]:
    """美中 USTX 三方案对比所需成本源（plan Task 2）。

    同一 worksheet 分别冻结「显示值」与「公式」：B1/B2 重建要靠公式证据，
    公式等价校验要靠显示值。列名合同由 `ustx_cost_compare.validate_formula_contract`
    在 Task 4 校验，此处只做源级 required 约束。
    """
    return [
        SourceSpec("sx_processing_values", spreadsheet, "绍兴二次加工成本", required=True),
        SourceSpec(
            "sx_processing_formulas",
            spreadsheet,
            "绍兴二次加工成本",
            required=True,
            render_option="formulas",
        ),
        SourceSpec("ustx_estimate_values", spreadsheet, "测算 美中USTX二次加工成本", required=True),
        SourceSpec(
            "ustx_estimate_formulas",
            spreadsheet,
            "测算 美中USTX二次加工成本",
            required=True,
            render_option="formulas",
        ),
        # 美东测算仅作结构旁证，缺失不阻断
        SourceSpec("usnj_estimate_values", spreadsheet, "测算 美东USNJ二次加工成本"),
        SourceSpec("shell_cost_import_values", spreadsheet, "import皮壳成本", required=True),
        SourceSpec("bom_cost_import_values", spreadsheet, "importBOMCostList", required=True),
    ]


def cmd_list(args) -> int:
    reader = _reader()
    spreadsheet = args.spreadsheet or _derive_names(args.month)[0]
    titles = list_worksheet_titles(reader, spreadsheet)
    for title in titles:
        role = classify_worksheet(title, [])
        print(f"{role:18s} {title}")
    print(f"\n共 {len(titles)} 张 worksheet（spreadsheet={spreadsheet}）")
    return 0


def cmd_snapshot(args) -> int:
    reader = _reader()
    spreadsheet = args.spreadsheet or _derive_names(args.month)[0]
    titles = list_worksheet_titles(reader, spreadsheet)

    specs = default_specs(args.month, titles, spreadsheet)
    if args.with_finance:
        fin = args.finance_spreadsheet
        specs += [
            SourceSpec(
                "rules_170",
                fin,
                args.rule_worksheet,
                required_columns=(
                    "运营人员",
                    "发货区域",
                    "通途SKU",
                    "渠道账号",
                    "发货仓按销售汇总分类",
                ),
            ),
            SourceSpec("warehouse_cost_source", fin, "订单发货仓库对应成本来源"),
            SourceSpec("fx", fin, "汇率"),
        ]
        specs += ustx_cost_specs(args.cost_spreadsheet)
    specs += _extra_specs(args.extra)

    out_dir = Path(args.out) if args.out else (
        MODULE_ROOT / "out" / "profitability_audit" / _derive_names(args.month)[1]
    )
    manifest = snapshot_sources(reader, specs, out_dir, known_worksheets=None)
    path = write_manifest(manifest, out_dir)

    ok = sum(1 for r in manifest.sources if r.status == "ok")
    print(json.dumps(
        {
            "out_dir": str(out_dir),
            "sources_ok": ok,
            "sources_total": len(manifest.sources),
            "failures": manifest.failures,
        },
        ensure_ascii=False,
        indent=2,
    ))
    print(f"manifest: {path}")
    require_successful(manifest)
    print("必需源全部就绪。")
    return 0


def cmd_analyze(args) -> int:
    """从**已冻结快照**离线分析（不联网），产出 JSON + Excel + 管理摘要。"""
    from tongtool_order_cost import profitability_audit as P
    from tongtool_order_cost import profitability_report as R

    snap = Path(args.snapshot)
    if not snap.exists():
        raise SystemExit(f"快照目录不存在: {snap}（先跑 snapshot）")
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    by_key = {s["key"]: s for s in manifest["sources"]}

    def load(key, sheet_name, key_columns=P.DEFAULT_BUSINESS_KEYS):
        rec = by_key.get(key)
        if not rec or rec["status"] != "ok":
            return []
        headers, rows = P.load_snapshot_csv(snap / rec["path"])
        return P.build_source_rows(headers, rows, sheet_name, key_columns)

    wb = load("writeback", "写回2026年7月订单")
    raw = load("raw", "2026年7月订单")
    fba = load("writeback_fba", "写回2026年7月FBA订单", P.FBA_BUSINESS_KEYS)

    metrics = P.metric_matrix(wb, P.default_metric_specs()) if wb else []
    findings = []
    if wb:
        findings += P.classify_product_cost(wb)
        findings += P.classify_freight(wb, observed_col="运费")
        findings += P.zero_column_evidence(wb, P.FEE_COLUMNS)
    if raw:
        findings += P.find_repeated_package_freight(raw)
        findings += P.classify_freight(raw)

    rev = sum(P._to_float(r.get("售价*汇率")) for r in wb)
    cost = sum(P._to_float(r.get("订单总成本")) for r in wb)
    profit = sum(P._to_float(r.get("订单利润")) for r in wb)
    coeff_profit = sum(P._to_float(r.get("订单利润*系数")) for r in wb)
    tc = P.flag_track_confusion(profit, coeff_profit)
    if tc:
        findings.append(tc)

    # 规则轨差异：**只用表内两套列**（已验证口径；不用会跑偏的独立重放）
    rule_events = P.rule_track_delta(wb) if wb else []
    findings += rule_events

    # 仓库口径体检：非绍兴发货却借用 2CJG-SX
    wh_check = P.warehouse_cost_source_check(wb) if wb else []
    findings += wh_check

    cons = P.row_conservation(wb).to_dict() if wb else {}
    gates = R.reconcile_gates(
        row_conservation=cons,
        revenue_ordinary=rev, cost_ordinary=cost, profit_ordinary=profit,
        reported_profit_ordinary=profit,
    )

    cohorts = {"by_account": P.cohort_summary(wb, key_col="渠道账号")} if wb else {}
    cohorts["rule_events"] = [f.to_dict() for f in rule_events]
    inversions = P.find_profit_inversions(cohorts.get("by_account", []))
    findings += inversions

    # FBA / 非 FBA 分开列示
    def _tot(rows, col):
        return round(sum(P._to_float(r.get(col)) for r in rows), 2)

    fba_scope = []
    if wb:
        fba_scope.append({"scope": "non_fba", "rows": len(wb),
                          "revenue": _tot(wb, "售价*汇率"), "freight": _tot(wb, "运费"),
                          "total_cost": _tot(wb, "订单总成本"), "profit": _tot(wb, "订单利润")})
    if fba:
        fba_scope.append({"scope": "fba", "rows": len(fba),
                          "revenue": _tot(fba, "售价*汇率"), "freight": _tot(fba, "运费"),
                          "total_cost": _tot(fba, "订单总成本"), "profit": _tot(fba, "订单利润")})
    cohorts["fba_scope"] = fba_scope

    # 未匹配/异常行级记录（不只是计数）：空 SKU 占位行 + 成本全缺订单
    exceptions = []
    if raw:
        for r in raw:
            if not r.key.tongtool_sku:
                exceptions.append({
                    "kind": "blank_sku_placeholder", "source_sheet": r.source_sheet,
                    "source_row": r.row_number, "order_id": r.key.order_id,
                    "package_id": r.key.package_id, "note": "占位行：保留血缘、不计件数"})
    gap_orders = []
    if wb:
        for r in wb:
            if P._to_float(r.get("订单总成本")) == 0 and P._to_float(r.get("售价*汇率")) > 0:
                gap_orders.append({
                    "kind": "cost_missing", "source_sheet": r.source_sheet,
                    "source_row": r.row_number, "order_id": r.key.order_id,
                    "tongtool_sku": r.key.tongtool_sku, "渠道账号": r.get("渠道账号"),
                    "发货仓库": r.get("发货仓库"), "发货区域": r.get("发货区域"),
                    "售价*汇率": P._to_float(r.get("售价*汇率"))})
    exceptions += gap_orders
    cohorts["exceptions"] = exceptions

    # 行级血缘样本（保留原始行身份，可下钻）
    cohorts["lineage"] = [
        {"source_sheet": r.source_sheet, "source_row": r.row_number,
         "occurrence_index": r.key.occurrence_index, "order_id": r.key.order_id,
         "base_order_id": r.key.base_order_id, "package_id": r.key.package_id,
         "tongtool_sku": r.key.tongtool_sku, "platform_sku": r.key.platform_sku,
         "ambiguous": r.key.ambiguous, "incomplete": r.key.incomplete}
        for r in wb[:2000]
    ]

    questions = {
        "product_cost": "见 01_指标口径 / 08_产品成本异常（行均 vs 数量加权 vs 订单均）",
        "freight": "见 09_运费异常（物流商运费=实收；通途运费=估算；包裹总运费口径更低）",
        "profit_inversion": (f"倒挂队列 {len(inversions)} 个，最高 "
                             f"{inversions[0].key if inversions else '—'}；"
                             f"成本全缺 {len(gap_orders)} 行（见 15 + 成本全缺清单.xlsx）"),
    }

    report = R.build_report(
        run_id=manifest["run_id"], sources=manifest["sources"], metrics=metrics,
        row_conservation={"conservation": cons}, findings=findings,
        cohorts=cohorts, gates=gates, questions=questions,
        extra={"revenue_ordinary": round(rev, 2), "cost_ordinary": round(cost, 2),
               "profit_ordinary": round(profit, 2), "profit_coefficient": round(coeff_profit, 2),
               "rows_writeback": len(wb), "rows_raw": len(raw), "rows_fba": len(fba)},
    )
    out_dir = R.new_run_dir(args.out_root, "analyze")
    written = R.write_all(report, out_dir)

    # 独立可交接清单：成本全缺行（给运营/主数据直接看）
    if gap_orders:
        import pandas as pd

        gap_path = out_dir / "成本全缺清单.xlsx"
        pd.DataFrame(gap_orders).to_excel(gap_path, index=False)
        written["cost_gap_xlsx"] = str(gap_path)

    print(json.dumps({
        "conclusions_blocked": report.conclusions_blocked,
        "gates": [g.to_dict() for g in gates],
        "findings": len(report.findings),
        "cost_gap_rows": len(gap_orders),
        "warehouse_asymmetry": len(wh_check),
        "out": written,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_ustx_compare(args) -> int:
    """从已冻结快照离线做美中 USTX 三方案对比（不联网、不写任何外部系统）。"""
    from datetime import datetime

    from tongtool_order_cost import profitability_audit as P
    from tongtool_order_cost import ustx_cost_compare as U

    snap = Path(args.snapshot)
    if not snap.exists():
        raise SystemExit(f"快照目录不存在: {snap}（先跑 snapshot --with-finance）")
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    by_key = {s["key"]: s for s in manifest["sources"]}

    def load(key: str) -> tuple[list[str], list[list[str]]]:
        rec = by_key.get(key)
        if not rec or rec["status"] != "ok":
            raise SystemExit(f"快照缺必需源: {key}（重跑 snapshot --with-finance）")
        return P.load_snapshot_csv(snap / rec["path"])

    sh, sr = load("shell_cost_import_values")
    bh, br = load("bom_cost_import_values")
    b1h, b1r = load("ustx_estimate_values")
    whh, whr = load("warehouse_cost_source")
    wbh, wbr = load("writeback")

    contract = U.validate_formula_contract(sh, bh, b1h)
    ustx_wh = U.ustx_warehouses(whh, whr)
    if not ustx_wh:
        raise SystemExit("仓库映射表里没有 USTX分公司 行，无法判定美中范围")

    order_rows = P.build_source_rows(wbh, wbr, "写回2026年7月订单", P.DEFAULT_BUSINESS_KEYS)
    raw_rows = []
    raw_rec = by_key.get("raw")
    if raw_rec and raw_rec["status"] == "ok":
        rawh, rawr = P.load_snapshot_csv(snap / raw_rec["path"])
        raw_rows = P.build_source_rows(rawh, rawr, "2026年7月订单", P.DEFAULT_BUSINESS_KEYS)

    # 键集必须与 compare 阶段一致（按美中行取，不过滤空键）——空键会被记为 unmatched
    ustx_keys = sorted({
        r.get(U.KEY_COL) for r in order_rows
        if r.get(U.WAREHOUSE_COL) in ustx_wh
    })
    shell_idx, shell_dups = U.build_shell_weight_index(sh, sr)
    bom_idx = U.build_bom_index(bh, br)
    b2 = U.build_b2_catalog(shell_idx, bom_idx, keys=ustx_keys,
                            ambiguous_keys=[d["key"] for d in shell_dups])
    b1 = U.build_b1_catalog(U.b1_key_values(b1h, b1r), b2, keys=ustx_keys)

    # 头程（改造目标：按绍兴发货方式取，皮壳兜底）——缺这张表则 B2 头程保留 A
    head_index = None
    head_rec = by_key.get("en_bom_cost")
    if head_rec and head_rec["status"] == "ok":
        eh, er = P.load_snapshot_csv(snap / head_rec["path"])
        head_index = U.build_head_freight_index(eh, er)

    result = U.compare_monthly_costs(
        order_rows, raw_rows, ustx_warehouse_names=ustx_wh,
        b1_catalog=b1, b2_catalog=b2, contract=contract, head_index=head_index,
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else (snap.parent / f"{snap.name}_ustx_compare_{stamp}")
    written = U.write_outputs(result, out_dir, run_id=manifest["run_id"], sources=manifest["sources"])

    print(json.dumps({
        "conclusions_blocked": result.conclusions_blocked,
        "counts": {
            "rows_total": len(result.rows),
            "rows_ustx": len(result.ustx_rows),
            "b1_measured": sum(1 for r in result.ustx_rows if r["b1_source"] == U.SRC_MEASURED),
            "b1_formula_filled": sum(1 for r in result.ustx_rows if r["b1_source"] == U.SRC_FORMULA_FILLED),
            "b1_unmatched": sum(1 for r in result.ustx_rows if r["b1_source"] == U.SRC_UNMATCHED),
            "b2_import": sum(1 for r in result.ustx_rows if r["b2_source"] == U.SRC_IMPORT),
            "b2_unmatched": sum(1 for r in result.ustx_rows if r["b2_source"] == U.SRC_UNMATCHED),
        },
        "component_waterfall": result.component_waterfall,
        "head_shell_sensitivity": result.head_shell_sensitivity,
        "gates": result.gates,
        "blocked_reasons": result.blocked_reasons,
        "notes": result.notes,
        "out": written,
    }, ensure_ascii=False, indent=2))
    return 1 if result.conclusions_blocked else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="月度通途订单盈利审计（只读）")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="只读列出 worksheet 与角色")
    pl.add_argument("--month", required=True)
    pl.add_argument("--spreadsheet", default="")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("snapshot", help="只读盘点 + 冻结本地快照 + manifest")
    ps.add_argument("--month", required=True)
    ps.add_argument("--spreadsheet", default="")
    ps.add_argument("--out", default="")
    ps.add_argument("--with-finance", action="store_true", help="同时冻结和财务部共享的规则/仓库映射/汇率")
    ps.add_argument("--finance-spreadsheet", default="和财务部共享")
    ps.add_argument("--rule-worksheet", default="Jeck特殊规则-订单改销售额成本")
    ps.add_argument("--cost-spreadsheet", default="二次加工成本2022", help="二次加工成本源所在 workbook")
    ps.add_argument("--extra", action="append", default=[], help="额外源 KEY=SPREADSHEET::WORKSHEET")
    ps.set_defaults(func=cmd_snapshot)

    pa = sub.add_parser("analyze", help="从已冻结快照离线分析（不联网）")
    pa.add_argument("--snapshot", required=True, help="snapshot 产出的目录")
    pa.add_argument("--out-root", default=str(MODULE_ROOT / "out" / "profitability_audit"))
    pa.set_defaults(func=cmd_analyze)

    pu = sub.add_parser("ustx-compare", help="美中 USTX 三方案成本对比（从已冻结快照离线，不联网）")
    pu.add_argument("--snapshot", required=True, help="snapshot 产出的目录（需 --with-finance）")
    pu.add_argument("--out", default="", help="输出目录；默认在快照同级带时间戳")
    pu.set_defaults(func=cmd_ustx_compare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_credentials(main_repo_root())
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
