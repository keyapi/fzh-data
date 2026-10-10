"""Run the technical month steps and write a private workbook.

Finance selections stay unconfirmed. Settlement and FBA probes reuse completed
read-only snapshots. This command does not write Google, EN, Sellfox, or Tongtool.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sellfox_settlement.account_validation import audit
from sellfox_settlement.cost_validation import summarize_coverage, validate_input
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
    pln_details = (retry or {}).get("details") or []
    pln_empty = bool(retry) and retry.get("errors") == [] and pln_details and pln_details[0].get("input_rows") == 0
    stale = [e for e in summary.get("errors") or [] if not (pln_empty and e.get("stage") == "details_PLN")]
    reason = "银行实际到账缺输入"
    if "PLN" not in currencies:
        reason += "；PLN 没有落入本次 V2 结算组"
    if pln_empty:
        reason += "；PLN 原币明细重试结果为 0 行"
    return _stage("7", "settlement_bank_bridge", "reused_snapshot",
                  input=summary.get("groups_input", 0), output=summary.get("groups_scoped", 0),
                  success=summary.get("groups_scoped", 0), skipped=1, failed=len(stale),
                  unmatched_reason=reason)


def fba_stage(summary):
    return _stage("6", "fba_cost", "probe_reused_no_production_write",
                  input=summary["api_order_rows"], output=summary["en_orders_in_api_scope"],
                  success=summary["order_status"]["matched"],
                  skipped=1, failed=0, unmatched=summary["order_status"]["order_unmatched"],
                  unmatched_reason="通途 8 月探针已完成；不部署 EN 生产 enrichment；当前 BOM 不是 8 月历史成本")


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_month(input_root, output, month):
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
    stages.append(_stage("1", "file_coverage", "ran",
                         input=summary.get("source_files", 0), output=summary.get("pdf_success", 0),
                         success=summary.get("pdf_success", 0), skipped=0,
                         failed=summary.get("pdf_failed", 0) + len(monthly["csv_validation"]["file_errors"]),
                         unmatched_reason="期间、币种和配对异常留在 monthly_validation.json"))
    stages.append(_stage("3", "pdf_controls", "ran",
                         input=summary.get("comparison_count", 0), output=summary.get("comparison_count", 0),
                         success=summary.get("comparison_status_counts", {}).get("complete", 0),
                         skipped=summary.get("comparison_status_counts", {}).get("partial", 0),
                         failed=summary.get("comparison_status_counts", {}).get("difference", 0),
                         unmatched_reason="Refund.other 保持未分配；空白 PDF 金额不补 0"))

    sheet = _load(output / "account_sheet.json")
    en = _load(output / "account_en.json")
    shops = _load(output / "account_shops.json")
    accounts = audit(source, sheet, en, shops)
    _write_json(output / "account_validation.json", accounts)
    _write_json(output / "additional_shop_scope.json", accounts["supplemental_shop_matches"])
    exact = [{"file": row["file"], "account": row["account_candidate"], **row["shops"][0]}
             for row in accounts["files"] if len(row["shops"]) == 1]
    _write_json(output / "account_shop_scope.json", exact)
    counts = accounts["summary"]
    stages.append(_stage("2", "account_match", "ran_on_saved_master_snapshot",
                         input=counts["files"], output=counts["matched"], success=counts["matched"],
                         skipped=counts["supplemental_shop_matched_files"],
                         failed=counts["files"] - counts["matched"],
                         unmatched_reason="标准账号未匹配与法人未确认分开保留；未刷新 Google/EN/赛狐"))

    orders_path = output / "cost" / "en_orders.json"
    supplemental_path = output / "cost" / "supplemental_en_orders.json"
    orders = _load(orders_path)
    supplemental = _load(supplemental_path) if supplemental_path.exists() else []
    validate_input(rows, {"type", "order_id", "sku", "fulfillment", "source_file", "source_line"}, "transactions")
    validate_input(orders, {"name", "platform_order_id", "order_items", "packages"}, "orders")
    report, details = summarize_coverage(rows, orders, supplemental)
    cost_dir = output / "cost"
    cost_dir.mkdir(exist_ok=True)
    _write_json(cost_dir / "cost_coverage_summary.json", report)
    _write_json(cost_dir / "cost_coverage_details.json", details)
    stages.append(_stage("5", "fbm_fba_order_link", "ran",
                         input=report["input_rows"], output=report["eligible_rows"],
                         success=report["statuses"].get("matched", 0),
                         skipped=report["statuses"].get("excluded_non_order_or_missing_id", 0),
                         failed=report["statuses"].get("order_unmatched", 0) + report["statuses"].get("sku_unmatched", 0),
                         unmatched=report["statuses"].get("ambiguous_parent_child", 0),
                         unmatched_reason="父子单歧义、缺单、SKU 不符分行保留；未汇总成本金额"))

    fba_path = cost_dir / "fba_month_scope_summary.json"
    stages.append(fba_stage(_load(fba_path)))
    settlement_dir = output / "settlement"
    stages.append(settlement_stage(
        _load(settlement_dir / "settlement_validation_summary.json"),
        _load(settlement_dir / "native_pln_retry_summary.json")))

    tables = build_tables(output)
    _write_json(output / "workbook_tables.json", tables)
    workbook = write_workbook(tables, output / f"{month}-technical-workbook.xlsx")
    sheet_rows = {item["name"]: len(item["rows"]) for item in tables["sheets"]}
    stages.append(_stage("8", "workbook", "ran", input=summary.get("candidate_rows", 0),
                         output=sum(sheet_rows.values()), success=len(sheet_rows), skipped=0, failed=0,
                         unmatched_reason="工作簿在仓库外；待确认表保留银行、口径、历史成本和异常",
                         sheets=sheet_rows, workbook_name=workbook.name))
    result = {"month": month, "finance_status": rules["status"],
              "selected_income_candidate": rules["selected_income_candidate"], "stages": stages}
    _write_json(output / "technical_month_report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--month", required=True)
    args = parser.parse_args()
    try:
        result = run_month(args.input, args.out, args.month)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
