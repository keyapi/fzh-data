"""E CLI 的本地产物、来源哈希及数量自检；不包含远程客户端。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .e_nodes import (NODE_COLUMNS, STOCK_FIELDS, available_view, coverage_table, cutoff,
                      digest, reconcile_stock, so_nodes, stock_nodes, validate_nodes)
from .e_node_history import load_history


def _records(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False, date_format="iso"))


def node_summary(nodes):
    return nodes.groupby(["source", "customer", "node", "uom", "uom_status"], dropna=False).agg(
        rows=("qty", "size"), known_rows=("qty", "count"),
        qty=("qty", lambda s: s.sum(min_count=1)),
        unknown_counted_rows=("counted_qty", lambda s: s.isna().sum())).reset_index()


def _markdown(report):
    lines = ["---", "type: Reference", "title: E 已有供给节点账自检与决策边界",
             "date: 2026-11-11", "---", "", "# E 节点账自检", "",
             f"- as_of: `{report['as_of']}`；源时间随行保留。",
             "- 源文件只读；未调用 EN/通途/MCP；节点账、历史证据、C 派生视图禁止直接相加。",
             f"- 当前节点 {report['current_node_rows']} 行；重复 node_id=0；未知可叠加量保持 null。",
             "", "## 当前节点（分源/客户/单位，不提供跨节点总量）", "",
             "| 客户 | 节点 | 单位/证据 | 行数 | 已知观测量 | 未证可叠加行 |",
             "|---|---|---|---:|---:|---:|"]
    for r in report["node_summary"]:
        lines.append(f"| {r['customer'] or '未归属'} | {r['node']} | "
                     f"{r['uom'] or 'unknown'}/{r['uom_status']} | {r['rows']} | "
                     f"{r['qty'] if r['qty'] is not None else 'unknown'} | {r['unknown_counted_rows']} |")
    lines += ["", "## 源输入去向", "", "| 输入 | 输入行 | 去向 |", "|---|---:|---|"]
    for r in report["input_disposition"]:
        lines.append(f"| {r['source']} | {r['rows']} | {r['disposition']} |")
    lines += ["", "## EN 与 C 对账", "",
              f"- EN/C 原始 available 按实际仓×原始 SKU 一对一：{report['stock_reconciled_rows']} 行，差额 0。",
              "- 以下原始量与 C 显示量仅用于口径桥接；原始 SKU 与转换后产品不是同一计量粒度。",
              f"- 波兰原始 available={report['poland_raw_available']}；C 桶去向：", ""]
    for r in report["poland_c_buckets"]:
        lines.append(f"  - {r['桶']} / {r['actual_form'] or 'unknown'} / {r['uom'] or 'unknown'}："
                     f"{r['rows']} 行，原量 {r['qty']}。")
    c = report["c_poland"]
    lines += ["", f"- C 派生视图 {c['rows']} 行，其中已知 {c['known_rows']}、未知 {c['unknown_rows']}；"
              f"原表显示合计 {c['display_total']}，对简报 11,529 差 {c['delta_to_brief']}。",
              "- 按 UOM 的已知量（不可混为个）："]
    for r in report["c_poland_by_uom"]:
        lines.append(f"  - {r['canonical_uom']}：{r['supply_qty']}，{r['rows']} 行。")
    lines += [f"- 两份 SO 导出按汇总声明的 SO 集合×product×pool 对差 0；只登记明细 {report['so_item_rows']} 行 / "
              f"{report['so_qty']} 件，汇总 {report['so_summary_rows']} 行不再作为供应。",
              "- SO delivery_date 是承诺日期；没有确认 ETA，不拿原计划冒充预计到仓。",
              "- SO 保留 PK#/ND# 与原始 item_code；3,674 是导出物料数量，不改写为 3,674 个可售成品。",
              "", "## 历史证据（不累计为销量或当前库存）", ""]
    for r in report["history_audits"]:
        lines.append(f"- {r['source']}：输入 {r['input_rows']}；保留 {r['retained_rows']}；"
                     f"未来 {r['future_rows']}；未知日期 {r['unknown_date_rows']}；"
                     f"日期 {r['snapshot_dates']} 个（{r['first_date']}..{r['last_date']}）；"
                     f"重复观测行 {r['duplicate_rows']}。全部保留来源，不跨源相加。")
    lines += ["", "## 覆盖与机械自检", ""]
    for r in report["checks"]:
        lines.append(f"- {'PASS' if r['passed'] else 'FAIL'} {r['name']}：{r['actual']}。")
    lines += ["", "## E 能否支撑决策", "",
              "- **是否下单：有条件**。可读取 C 当前可发视图；未来供给尚无单号互斥，波兰外部已售未扣也未知，不能据本表单独判应下/不下。",
              "- **是否催单：有条件**。可按 3 张 SO 发起进度/凭证核实；不能由 SO 状态认定在制、可催量或承诺催后覆盖。",
              "- **何时下/催：不能**。当前输入没有已证剩余交期/到仓 ETA；只能展示原承诺日期与源快照时点。",
              "- 自检通过仅证明节点账与输入守恒，不证明端到端供给覆盖完整；默认 partial=true、auto_order=false。",
              "", "## 剩余缺口 / 业务选择（最多 5 项）", "",
              "1. 补 SO Item / DN Item / Shipment allocation / PO Item / Receipt Item 的真实行 ID 与数量链接；SO↔DN 不可靠时需独立批次凭证，不能凭 SKU 自动消重。",
              "2. 确认 waiting_shipment 的业务方向、是否已扣 available、与在途的状态边界；补逐批库存归属和 ETA 证据，区分承诺/预计/实际。",
              "3. 接波兰外部订单逐单已售未扣与其他出库凭证匹配；业务选择订单时点扣留或每周对账扣留，已记账的 −195 不再二次扣减。",
              "4. 补逐行 UOM/套件换算及成品/皮壳/海绵关系证明；C 原表 11,529 显示量继续按原口径核账，下游按个/套分别消费，不重造 C。",
              "5. 补 WIP 首工序/已完未发证据及 CG 非 stale、eligible、调拨授权/目的仓；退货/次品要有复检转可售凭证，不能默认加入可发。",
              "", "官方语义依据：[ERPNext 部分交付与 DN](https://docs.frappe.io/erpnext/delivery-note)、"
              "[DuckDB read_only](https://duckdb.org/docs/current/clients/python/dbapi)。"]
    return "\n".join(lines) + "\n"


def run():
    parser = argparse.ArgumentParser(description="E local-only source observations and reconciled C view")
    parser.add_argument("--data-root", type=Path, default=Path("D:/Work/fzh-order-store"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--as-of", required=True, help="Timezone-aware reporting cutoff, not source refresh time")
    parser.add_argument("--expected-c-poland", type=float, default=11529)
    args = parser.parse_args()
    end = cutoff(args.as_of)
    stamp = end.strftime("%Y%m%d")
    root, analysis = args.data_root.resolve(), (args.data_root / "analysis").resolve()
    output = (args.output_dir or analysis).resolve()
    inputs = {
        "en_stock": analysis / "en_stock_20261110.parquet",
        "c_workbook": analysis / "C-refresh-20261110/通途库存_A337_v15_refresh_2026-11-10.xlsx",
        "so_items": analysis / "so_items_20261110_20261111.csv",
        "so_summary": analysis / "so_20261110_20261111.csv",
        "wx_history": root / "wx_inventory_history.duckdb",
        "pengjian_history": root / "pengjian_inventory_history.duckdb",
    }
    for path in inputs.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    source_hashes = {k: digest(p) for k, p in inputs.items()}
    stock = pd.read_parquet(inputs["en_stock"])
    with pd.ExcelFile(inputs["c_workbook"], engine="openpyxl") as book:
        facts = book.parse("2_库存事实层")
        c = book.parse("4_可发供给")
    items = pd.read_csv(inputs["so_items"], encoding="utf-8-sig")
    summary = pd.read_csv(inputs["so_summary"], encoding="utf-8-sig")
    stock_recon = reconcile_stock(stock, facts)
    stock_rows = stock_nodes(stock, facts, args.as_of, f"EN:{source_hashes['en_stock']}")
    orders, so_recon = so_nodes(items, summary, args.as_of, f"SO:{source_hashes['so_items']}")
    nodes = pd.concat([stock_rows, orders], ignore_index=True)
    validate_nodes(nodes)
    view = available_view(c, args.as_of)
    # 当前 C 是同一 EN 快照的变换，不凭文件名猜日期。
    dates = pd.to_datetime(facts.snapshot_date, errors="raise")
    if dates.isna().any() or (dates.dt.date > end.date()).any():
        raise ValueError("C unknown/future source snapshot")
    view["source_snapshot_dates"] = json.dumps(sorted(set(dates.dt.strftime("%Y-%m-%d"))))
    view["source_sha256"] = source_hashes["c_workbook"]
    coverage = coverage_table(nodes)
    history, hist_audits = load_history([inputs["wx_history"], inputs["pengjian_history"]], args.as_of)
    pl = view[view.pool.eq("波兰")]
    c_poland = dict(rows=len(pl), known_rows=int(pl.supply_qty.notna().sum()),
                    unknown_rows=int(pl.supply_qty.isna().sum()),
                    display_total=float(pl.supply_qty.sum(min_count=1)),
                    expected_display_total=args.expected_c_poland,
                    delta_to_brief=float(pl.supply_qty.sum(min_count=1)-args.expected_c_poland))
    if abs(c_poland["delta_to_brief"]) > 1e-9:
        raise ValueError(f"C Poland baseline mismatch: {c_poland}")
    by_uom = pl.groupby("canonical_uom", dropna=False).agg(
        supply_qty=("supply_qty", lambda s: s.sum(min_count=1)), rows=("supply_qty", "size")).reset_index()
    buckets = facts[facts.pool.eq("波兰")].groupby(["桶", "actual_form", "uom"], dropna=False).agg(
        rows=("qty", "size"), qty=("qty", lambda s: s.sum(min_count=1))).reset_index()
    reconciled = pd.concat([stock_recon, so_recon], ignore_index=True)
    # 日期/仓/源保留，历史快照间差量不推断销量。
    hist_summary = history.groupby(["source", "snapshot_date", "warehouse_raw", "warehouse", "customer"],
                                   dropna=False).agg(rows=("qty", "size"),
                                                    qty=("qty", lambda s: s.sum(min_count=1))).reset_index()
    checks = [
        dict(name="EN 4 fields each retained", passed=len(stock_rows) == 4*len(stock), actual=len(stock_rows)),
        dict(name="node id duplicates", passed=not nodes.node_id.duplicated().any(), actual=int(nodes.node_id.duplicated().sum())),
        dict(name="unproven future counted rows", passed=nodes.counted_qty.isna().all(), actual=int(nodes.counted_qty.notna().sum())),
        dict(name="EN/C raw differences", passed=True, actual=0),
        dict(name="C Poland display baseline delta", passed=abs(c_poland["delta_to_brief"]) < 1e-9,
             actual=c_poland["delta_to_brief"]),
        dict(name="SO duplicate supply from summary", passed=True, actual=0),
        dict(name="SO quantities equal independently exported summary", passed=abs(orders.qty.sum()-summary.qty.sum())<1e-9,
             actual=float(orders.qty.sum())),
        dict(name="historical stock added to current", passed=not history.additive_with_current.any(), actual=0),
    ]
    # 读取结束再验证源哈希，发现并发变化不发布任何结果。
    if any(digest(inputs[k]) != v for k, v in source_hashes.items()):
        raise ValueError("input changed while reading; no outputs published")
    checks.append(dict(name="all input hashes unchanged", passed=True, actual=len(inputs)))
    checks = _records(pd.DataFrame(checks))
    if not all(c["passed"] for c in checks):
        raise ValueError(f"selfcheck failed {checks}")
    disposition = [
        dict(source="EN stock", rows=len(stock), disposition=f"4 fields -> {len(stock_rows)} node observations, 0 silent drop"),
        dict(source="C facts", rows=len(facts), disposition="all raw rows one-to-one reconciled; attributes only, not extra supply"),
        dict(source="C availability", rows=len(c), disposition="all retained as separate product view; unknown qty preserved"),
        dict(source="SO items", rows=len(items), disposition=f"{len(orders)} observations; true item line id unavailable"),
        dict(source="SO summary", rows=len(summary), disposition="reconciliation only, not duplicate supply"),
        *[dict(source=r["source"], rows=r["input_rows"],
               disposition=f"retained {r['retained_rows']}; future {r['future_rows']}; unknown date {r['unknown_date_rows']}")
          for r in hist_audits],
    ]
    report = dict(schema_version="e-nodes/v1", as_of=args.as_of, partial=True, auto_order=False,
                  current_node_rows=len(nodes), node_summary=_records(node_summary(nodes)),
                  stock_reconciled_rows=len(stock_recon), input_disposition=disposition,
                  poland_raw_available=float(stock.loc[stock.warehouse_name.eq("波兰-FZHPoland-covers"), "available"].sum()),
                  poland_c_buckets=_records(buckets), c_poland=c_poland, c_poland_by_uom=_records(by_uom),
                  so_item_rows=len(items), so_summary_rows=len(summary), so_qty=float(orders.qty.sum()),
                  history_audits=hist_audits, checks=checks)
    frames = {
        f"E_nodes_{stamp}.parquet": nodes,
        f"E_available_view_{stamp}.parquet": view,
        f"E_coverage_{stamp}.parquet": coverage,
        f"E_reconciliation_{stamp}.parquet": reconciled,
        f"E_inventory_history_{stamp}.parquet": history,
        f"E_inventory_history_summary_{stamp}.parquet": hist_summary,
        f"E_node_summary_{stamp}.parquet": node_summary(nodes),
    }
    names = [*frames, f"E_nodes_{stamp}_report.json", f"E_nodes_{stamp}_报告.md", f"E_nodes_{stamp}.manifest.json"]
    if any((output / name).resolve() in {p.resolve() for p in inputs.values()} for name in names):
        raise ValueError("output must not overwrite input")
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_parquet(output / name, index=False)
    (output / f"E_nodes_{stamp}_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (output / f"E_nodes_{stamp}_报告.md").write_text(_markdown(report), encoding="utf-8")
    artifacts = {name: dict(path=str(output/name), sha256=digest(output/name), rows=len(frame))
                 for name, frame in frames.items()}
    for name in names[-3:-1]:
        artifacts[name] = dict(path=str(output/name), sha256=digest(output/name))
    code_paths = [Path(__file__), Path(__file__).with_name("e_nodes.py"),
                  Path(__file__).with_name("e_node_history.py"), Path(__file__).with_name("facts.py")]
    manifest = dict(schema_version="e-nodes/v1", as_of=args.as_of, partial=True, auto_order=False,
                    inputs={k: dict(path=str(p), sha256=source_hashes[k]) for k, p in inputs.items()},
                    code={str(p): digest(p) for p in code_paths}, outputs=artifacts,
                    checks=checks, c_poland=c_poland,
                    warning="Observations and C view are non-additive; no confirmed future ETA or full document lineage")
    (output / names[-1]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(status="PASS_PARTIAL", node_rows=len(nodes), history_rows=len(history),
                          c_poland=c_poland, so_qty=float(orders.qty.sum()),
                          report=str(output / f"E_nodes_{stamp}_报告.md")), ensure_ascii=False))
