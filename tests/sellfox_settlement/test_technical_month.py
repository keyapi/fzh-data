from pathlib import Path

import pytest
import yaml
from openpyxl import load_workbook

from sellfox_settlement.export_workbook import write_workbook
from sellfox_settlement.finance_rules import load_finance_rules, selected_income_candidate
from sellfox_settlement.run_technical_month import fba_stage, settlement_stage


def test_pending_rules_do_not_select_a_candidate():
    rules = load_finance_rules()
    assert rules["status"] == "pending_ZJ"
    assert selected_income_candidate(rules) is None
    assert set(rules["income_candidates"]) == {"A", "B"}


def test_pending_config_rejects_a_selected_candidate(tmp_path):
    rules = load_finance_rules()
    rules["selected_income_candidate"] = "A"
    path = tmp_path / "finance_rules.yaml"
    path.write_text(yaml.safe_dump(rules, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be selected"):
        load_finance_rules(path)


def test_workbook_stays_outside_git_and_neutralizes_formulas(tmp_path):
    tables = {"sheets": [{"name": "待确认与异常", "headers": ["事项", "状态"],
                          "rows": [["=cmd", "缺输入"]], "note": "候选不是申报数"}]}
    path = write_workbook(tables, tmp_path / "book.xlsx")
    sheet = load_workbook(path).active
    assert sheet["A4"].value == "'=cmd"
    assert sheet["A1"].value == "候选不是申报数"


def test_pln_empty_retry_is_not_a_current_failure():
    stage = settlement_stage(
        {"groups_input": 189, "groups_scoped": 189, "currencies": ["USD"],
         "errors": [{"stage": "details_PLN", "error_type": "ValueError"}]},
        {"errors": [], "details": [{"input_rows": 0}]})
    assert stage["failed"] == 0
    assert stage["skipped"] == 1
    assert "PLN" in stage["unmatched_reason"]
    assert "银行" in stage["unmatched_reason"]


def test_fba_probe_does_not_count_as_a_production_write():
    stage = fba_stage({"api_order_rows": 10, "en_orders_in_api_scope": 8,
                       "order_status": {"matched": 8, "order_unmatched": 2}})
    assert stage["status"] == "probe_reused_no_production_write"
    assert stage["success"] == 8
    assert stage["unmatched"] == 2
    assert stage["skipped"] == 1
