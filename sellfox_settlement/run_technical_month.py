"""Run the technical month steps and write a private workbook.

Finance selections stay unconfirmed. Settlement and FBA probes reuse completed
read-only snapshots. This command does not write Google, EN, Sellfox, or Tongtool.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sellfox_settlement.account_validation import audit
from sellfox_settlement.cost_validation import summarize_coverage, validate_input
from sellfox_settlement.account_cost_bridge import build_bridge
from sellfox_settlement.cost_ledger import build_ledger
from sellfox_settlement.tail_validation import diagnose
from sellfox_settlement.fba_sync_gap_validation import build_gap_report
from sellfox_settlement.export_workbook import write_workbook
from sellfox_settlement.finance_rules import load_finance_rules
from sellfox_settlement.monthly_validation import validate_month
from sellfox_settlement.validation_paths import private_output
from sellfox_settlement.workbook_tables import build_tables


def _stage(phase, name, status, **counts):
    row = {"phase": phase, "name": name, "status": status}
    row.update(counts)
    return row


def settlement_stage(summary, retry):
    currencies = set(summary.get("currencies") or [])
    pln_details = [d for d in (retry or {}).get('details', []) if d.get('currency') == 'PLN']
    pln_empty = False
    if len(pln_details) == 1 and retry.get('errors') == [] and summary.get('start'):
        first = dt.datetime.strptime(summary['start'][:7], '%Y-%m')
        next_month = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        detail = pln_details[0]
        pln_empty = (detail.get('scope_shops', 0) > 0 and detail.get('input_rows') == 0
                     and detail.get('start') == (first - dt.timedelta(days=1)).strftime('%Y-%m-%d')
                     and detail.get('end') == (next_month + dt.timedelta(days=1)).strftime('%Y-%m-%d'))
    stale = [e for e in summary.get("errors") or [] if not (pln_empty and e.get("stage") == "details_PLN")]
    reason = "银行实际到账缺输入"
    if "PLN" not in currencies:
        reason += "；PLN 没有落入本次 V2 结算组"
    if pln_empty:
        reason += "；PLN 原币明细重试结果为 0 行"
    return _stage("7", "settlement_bank_bridge", "reused_snapshot",
                  input=summary.get("groups_input", 0), output=summary.get("groups_scoped", 0),
                  success=summary.get("groups_scoped", 0), skipped=0, failed=len(stale),
                  bank_status='missing_input', bank_missing_inputs=1,
                  unmatched_reason=reason)


def fba_stage(summary):
    return _stage("6", "fba_cost", "probe_reused_no_production_write",
                  input=summary["api_order_rows"], output=summary["en_orders_in_api_scope"],
                  success=summary["order_status"]["matched"],
                  skipped=0, failed=0, unmatched=summary["order_status"]["order_unmatched"],
                  production_write_skipped=True,
                  unmatched_reason="通途 8 月探针已完成；不部署 EN 生产 enrichment；当前 BOM 不是 8 月历史成本")


def verify_fba_snapshot_month(period, month):
    # Query boundaries are evidence; purchase timestamps may have another timezone.
    start, end = period.get('query_start', ''), period.get('query_end', '')
    target = dt.datetime.strptime(month, '%Y-%m')
    next_month = (target.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    expected_end = (next_month - dt.timedelta(days=1)).strftime('%Y-%m-%d') + ' 23:59:59'
    if start != month + '-01 00:00:00' or end != expected_end:
        raise ValueError('FBA snapshot query month missing or incompatible')


def cost_stage(report):
    matched = report['statuses'].get('matched', 0)
    skipped = report['excluded_rows']
    unmatched = report['input_rows'] - matched - skipped
    assert matched + unmatched + skipped == report['input_rows']
    return _stage('5', 'fbm_fba_order_link', 'ran', input=report['input_rows'],
                  output=report['input_rows'], success=matched, skipped=skipped,
                  failed=0, unmatched=unmatched, status_counts=report['statuses'],
                  unmatched_reason='全部未匹配状态保留；成本金额不直接加总')


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_manifest(root):
    names = ['account_sheet.json', 'account_en.json', 'account_shops.json',
             'cost/en_orders.json', 'cost/current_cost_probe_details.json', 'cost/tongtool_fba_august.json',
             'cost/fba_snapshot_period.json', 'cost/fba_month_scope_summary.json',
             'settlement/settlement_validation_summary.json', 'settlement/settlement_groups_scoped.json',
             'settlement/native_pln_retry_summary.json']
    if (root / 'cost/supplemental_en_orders.json').exists():
        names.append('cost/supplemental_en_orders.json')
    names.append('cost/fba_month_scope_details.json')
    if (root / 'cost/current_cost_probe_components.json').exists():
        names.append('cost/current_cost_probe_components.json')
    return [{'path': str((root / name).resolve()), 'sha256': hashlib.sha256((root / name).read_bytes()).hexdigest()} for name in names]


def run_month(input_root, output, month, *, snapshots=None, json_only=False):
    source = Path(input_root)
    output = private_output(output, input_root=source)
    output.mkdir(parents=True, exist_ok=True)
    rules = load_finance_rules()
    stages = [_stage("4", "finance_rules", "loaded_unconfirmed",
                     input=1, output=len(rules["income_candidates"]), success=0, skipped=1, failed=0,
                     unmatched_reason="F03–F08、F10、F12–F13 仍待 ZJ；候选并列，不选定")]

    monthly = validate_month(source, month)
    _write_json(output / "monthly_validation.json", monthly)
    _write_json(output / "source_manifest.json", monthly["source_manifest"])
    rows = monthly["csv_validation"]["rows"]
    _write_json(output / "normalized_transactions.json", rows)
    summary = monthly["summary"]
    if summary["fatal_validation_errors"]:
        raise ValueError("fatal monthly validation errors; see monthly_validation.json")
    snapshot_root = private_output(snapshots) if snapshots is not None else output
    manifest = snapshot_manifest(snapshot_root)
    period = _load(snapshot_root / 'cost' / 'fba_snapshot_period.json')
    verify_fba_snapshot_month(period, month)
    source_hash = hashlib.sha256((snapshot_root / 'cost' / 'tongtool_fba_august.json').read_bytes()).hexdigest()
    if period.get('source_sha256') != source_hash:
        raise ValueError('FBA snapshot period source hash mismatch')
    stages.append(_stage("1", "file_coverage", "ran",
                         input=summary.get("source_files", 0), output=summary.get("pdf_success", 0),
                         input_unit='source_files', output_unit='csv_pdf_pairs',
                         success=summary.get("pdf_success", 0), skipped=0,
                         failed=summary.get("pdf_failed", 0) + len(monthly["csv_validation"]["file_errors"]),
                         unmatched_reason="期间、币种和配对异常留在 monthly_validation.json"))
    stages.append(_stage("3", "pdf_controls", "ran",
                         input=summary.get("comparison_count", 0), output=summary.get("comparison_count", 0),
                         success=summary.get("comparison_status_counts", {}).get("complete", 0),
                         skipped=summary.get("comparison_status_counts", {}).get("partial", 0),
                         failed=summary.get("comparison_status_counts", {}).get("difference", 0),
                         unmatched_reason="Refund.other 保持未分配；空白 PDF 金额不补 0"))

    sheet = _load(snapshot_root / "account_sheet.json")
    en = _load(snapshot_root / "account_en.json")
    shops = _load(snapshot_root / "account_shops.json")
    accounts = audit(source, sheet, en, shops)
    _write_json(output / "account_validation.json", accounts)
    _write_json(output / "additional_shop_scope.json", accounts["supplemental_shop_matches"])
    exact = [{"file": row["file"], "account": row["account_candidate"], **row["shops"][0]}
             for row in accounts["files"] if len(row["shops"]) == 1]
    _write_json(output / "account_shop_scope.json", exact)
    counts = accounts["summary"]
    stages.append(_stage("2", "account_match", "ran_on_saved_master_snapshot",
                         input=counts["files"], output=counts["matched"], success=counts["matched"],
                         skipped=0, supplemental_shop_matches=counts["supplemental_shop_matched_files"],
                         failed=counts["files"] - counts["matched"],
                         unmatched_reason="标准账号未匹配与法人未确认分开保留；未刷新 Google/EN/赛狐"))

    orders_path = snapshot_root / "cost" / "en_orders.json"
    supplemental_path = snapshot_root / "cost" / "supplemental_en_orders.json"
    orders = _load(orders_path)
    supplemental = _load(supplemental_path) if supplemental_path.exists() else []
    validate_input(rows, {"type", "order_id", "sku", "fulfillment", "source_file", "source_line"}, "transactions")
    validate_input(orders, {"name", "platform_order_id", "order_items", "packages"}, "orders")
    upstream = _load(snapshot_root / 'cost' / 'tongtool_fba_august.json')
    bridge = build_bridge(rows, accounts, orders, upstream)
    _write_json(output / 'account_cost_bridge.json', bridge)
    report, details = summarize_coverage(rows, orders, supplemental, account_by_file=bridge['account_by_file'])
    cost_dir = output / "cost"
    cost_dir.mkdir(exist_ok=True)
    _write_json(cost_dir / "cost_coverage_summary.json", report)
    _write_json(cost_dir / "cost_coverage_details.json", details)
    stages.append(cost_stage(report))
    probes = _load(snapshot_root / 'cost' / 'current_cost_probe_details.json')
    component_path = snapshot_root / 'cost/current_cost_probe_components.json'
    component_probes = _load(component_path) if component_path.exists() else None
    ledger = build_ledger(orders, probes, details, component_probes=component_probes)
    _write_json(cost_dir / 'cost_technical_ledger.json', ledger)
    tail = diagnose(orders, details)
    _write_json(cost_dir / 'tail_validation.json', tail)
    stages.append(_stage('5', 'component_ledger', 'diagnostic_only', **ledger['summary']))
    stages.append(_stage('5', 'tail_routing', 'diagnostic_only', **tail['summary']))

    fba_path = snapshot_root / 'cost' / "fba_month_scope_summary.json"
    stages.append(fba_stage(_load(fba_path)))
    channel_accounts = {row['name'] for row in en['accounts']}
    gap_report = build_gap_report(_load(snapshot_root / 'cost/fba_month_scope_details.json'),
                                  upstream, orders, channel_accounts)
    _write_json(cost_dir / 'fba_sync_gap_candidates.json', gap_report)
    stages.append(_stage('6', 'fba_sync_gap_dry_run', 'hold_no_import', **gap_report['summary']))
    settlement_dir = snapshot_root / "settlement"
    stages.append(settlement_stage(
        _load(settlement_dir / "settlement_validation_summary.json"),
        _load(settlement_dir / "native_pln_retry_summary.json")))

    tables = build_tables(output, snapshot_root=snapshot_root)
    if snapshot_manifest(snapshot_root) != manifest:
        raise ValueError('input snapshots changed during validation')
    _write_json(output / "workbook_tables.json", tables)
    workbook = None if json_only else write_workbook(tables, output / f"{month}-technical-workbook.xlsx")
    sheet_rows = {item["name"]: len(item["rows"]) for item in tables["sheets"]}
    stages.append(_stage("8", "workbook", "ran", input=summary.get("candidate_rows", 0),
                         output=sum(sheet_rows.values()), success=len(sheet_rows), skipped=0, failed=0,
                         unmatched_reason="工作簿在仓库外；待确认表保留银行、口径、历史成本和异常",
                         sheets=sheet_rows, workbook_name=workbook.name if workbook else None,
                         export_status='json_only' if json_only else 'exported'))
    result = {"month": month, 'snapshot_manifest': manifest, "finance_status": rules["status"],
              "selected_income_candidate": rules["selected_income_candidate"], "stages": stages}
    _write_json(output / "technical_month_report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument('--snapshots', type=Path, help='Private input snapshots; defaults to output folder')
    parser.add_argument('--json-only', action='store_true', help='Validate and prepare tables without writing XLSX')
    args = parser.parse_args()
    try:
        result = run_month(args.input, args.out, args.month, snapshots=args.snapshots, json_only=args.json_only)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
