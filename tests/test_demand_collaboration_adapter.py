import json
from datetime import date

import pytest
from openpyxl import Workbook

from demand_collaboration.adapter import inspect_d5, make_baseline, main
from demand_collaboration.core import DomainError, Store


HEAD = ["product_id","pool","physical_form","canonical_uom","horizon","horizon_days","point_forecast"]


def workbook(tmp_path,rows,headers=HEAD):
    path = tmp_path / "d5.xlsx"
    w = Workbook()
    s = w.active
    s.title = "1_预测"
    s.append(headers)
    for r in rows:
        s.append(r)
    w.save(path)
    w.close()
    return path


def row(product="KS1",pool="美东USNJ",h=97,qty=10):
    return [product,pool,"成品","个",h,h,qty]


def test_inspect_preserves_horizon_identity_and_full_accounting(tmp_path):
    p = workbook(tmp_path,[row(),row("KS2","美中USTX"),row("KS3","波兰"),row("KS1",h=157)])
    rows,r = inspect_d5(p)
    assert [x["branch"] for x in rows] == ["USNJ","USTX","PL"]
    assert rows[0]["name"] == "KS1（名称未接入）"
    assert rows[0]["sku"] == "EN:KS1"
    assert rows[0]["inventory_qty"] is None
    assert "history" not in rows[0]
    assert r["input_count"] == 4
    assert r["selected_count"] == r["accepted_count"] == 3
    assert r["skipped_count"] == 1
    assert r["rejected_count"] == 0
    assert r["out_of_scope_count"] == 0
    assert r["missing_forecast_count"] == 0
    assert len(r["source_sha256"]) == 64


def test_duplicate_physical_keys_all_rejected_not_first_wins(tmp_path):
    p = workbook(tmp_path,[row(),row(qty=25)])
    rows,r = inspect_d5(p)
    assert rows == []
    assert r["rejected_count"] == 2
    assert {x["reason"] for x in r["rejected"]} == {"duplicate_physical_target"}
    with pytest.raises(DomainError):
        make_baseline(p,"2026-11-11","2026-11-11")


def test_unknown_pool_is_out_of_scope_not_rejected(tmp_path):
    p=workbook(tmp_path,[row(product="KS-CG",pool="CG")])
    rows,report=inspect_d5(p)
    assert rows == []
    assert report["out_of_scope"][0]["product_id"] == "KS-CG"
    assert report["out_of_scope"][0]["pool"] == "CG"
    assert report["rejected_count"] == 0
    assert report["out_of_scope_count"] == 1
    assert report["reconciled"] is True


@pytest.mark.parametrize("bad",[row(qty=-1),row(qty="NaN"),["KS1","波兰","成品","个",97,157,10]])
def test_invalid_rows_rejected_and_fail_baseline(tmp_path,bad):
    p = workbook(tmp_path,[bad])
    rows,r = inspect_d5(p)
    assert not rows and r["rejected_count"] == 1
    with pytest.raises(DomainError):
        make_baseline(p,"2026-11-11","2026-11-11")


def test_unknown_pool_is_skipped_and_no_rows_still_blocks(tmp_path):
    p = workbook(tmp_path,[row(pool="未知")])
    rows,r = inspect_d5(p)
    assert not rows and r["rejected_count"] == 0 and r["out_of_scope_count"] == 1
    with pytest.raises(DomainError):
        make_baseline(p,"2026-11-11","2026-11-11")


def test_missing_forecast_is_reported_and_excluded_only_with_flag(tmp_path):
    p = workbook(tmp_path,[row(),row(product="KS2",qty=None)])
    rows,r = inspect_d5(p)
    assert len(rows) == 1 and r["missing_forecast_count"] == 1 and r["rejected_count"] == 0
    with pytest.raises(DomainError):
        make_baseline(p,"2026-11-11","2026-11-11")
    b,r2 = make_baseline(p,"2026-11-11","2026-11-11",allow_missing=True)
    assert len(b["rows"]) == 1 and r2["status"] == "converted_with_missing"


def test_missing_column_fail_closed(tmp_path):
    p=workbook(tmp_path,[],headers=HEAD[:-1])
    with pytest.raises(DomainError) as e:
        inspect_d5(p)
    assert e.value.code == "missing_columns"


def test_explicit_dates_and_97_day_total_compatible_with_store(tmp_path):
    p=workbook(tmp_path,[row()])
    b,r=make_baseline(p,"2026-11-11","2026-11-11")
    assert b["rows"][0]["week"] == "2026-11-11"
    assert b["rows"][0]["period_end"] == "2027-02-15"
    assert b["rows"][0]["baseline_qty"] == 10
    assert b["demo"] is False
    Store(tmp_path/"db.sqlite").set_baseline(b)
    b2,_=make_baseline(p,"2026-11-12","2026-11-11")
    assert b2["version"] != b["version"]
    with pytest.raises(DomainError):
        make_baseline(p,None,"2026-11-11")


def test_cli_inspect_only_saves_report_without_invented_baseline(tmp_path):
    p=workbook(tmp_path,[row()])
    out=tmp_path/"out"
    assert main(["--source",str(p),"--inspect","--out",str(out)]) == 0
    assert (out/"report.json").exists()
    assert not (out/"baseline.json").exists()
    assert json.loads((out/"report.json").read_text(encoding="utf-8"))["accepted_count"] == 1
