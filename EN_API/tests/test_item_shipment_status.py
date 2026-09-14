"""item_shipment_status 口径单测 —— 不连 ERP。"""
from datetime import date
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import item_shipment_status as iss  # noqa: E402


KS = "KS0001-DM-140-YELLOW"
PK = "PK#KS0001-DM-140-YELLOW"
ND = "ND#KS0001-DM-140-YELLOW"
CODE = "CENKZ1325-Yellow-138"


def test_line_matches_item_code_is_exact_not_substring():
    assert iss.line_matches({"item_code": PK}, [PK], None) is True
    assert iss.line_matches({"item_code": PK}, [KS], None) is False
    assert iss.line_matches({"item_code": ND}, [KS], None) is False
    assert iss.line_matches({"item_code": KS}, [KS], None) is True
    assert iss.line_matches({"item_code": PK.lower()}, [PK], None) is True


def test_line_matches_same_so_nd_sibling_not_pulled_by_pk():
    assert iss.line_matches({"item_code": ND}, [PK], None) is False
    assert iss.line_matches({"item_code": KS}, [PK], None) is False


def test_line_matches_customer_code_still_substring():
    line = {"item_code": PK, "customer_item_code": CODE}
    assert iss.line_matches(line, [], CODE) is True
    assert iss.line_matches({"item_code": PK, "customer_item_code": None}, [], CODE) is False
    # 客户码大小写 / 子串
    assert iss.line_matches(
        {"item_code": "OTHER", "customer_item_code": CODE + "-OLD"}, [], CODE
    ) is True


def test_op_progress_does_not_sum_across_operations():
    wo = {
        "name": "WO-1", "qty": 40, "produced_qty": 0, "status": "Not Started",
        "operations": [
            {"operation": "裁剪", "sequence_id": 1, "status": "Completed"},
            {"operation": "皮壳整件", "sequence_id": 2, "status": "Completed"},
            {"operation": "锁扣眼", "sequence_id": 3, "status": "Completed"},
            {"operation": "拷边", "sequence_id": 4, "status": "Completed"},
        ],
    }
    jcs = []
    for op in ("裁剪", "皮壳整件", "锁扣眼", "拷边"):
        jcs.append({"operation": op, "status": "Completed",
                    "for_quantity": 22, "total_completed_qty": 22})
        jcs.append({"operation": op, "status": "Completed",
                    "for_quantity": 22, "total_completed_qty": 22})
    p = iss.op_progress(wo, jcs)
    assert p["done_qty"] == 44
    assert p["over_plan"] is True


def test_op_progress_prefers_total_completed_qty():
    wo = {
        "qty": 40,
        "operations": [{"operation": "裁剪", "sequence_id": 1, "status": "Completed"}],
    }
    jcs = [{"operation": "裁剪", "status": "Completed",
            "for_quantity": 40, "total_completed_qty": 18}]
    assert iss.op_progress(wo, jcs)["done_qty"] == 18


def test_op_progress_falls_back_to_for_quantity():
    wo = {
        "qty": 40,
        "operations": [{"operation": "裁剪", "sequence_id": 1, "status": "Completed"}],
    }
    jcs = [{"operation": "裁剪", "status": "Completed",
            "for_quantity": 22, "total_completed_qty": 0}]
    assert iss.op_progress(wo, jcs)["done_qty"] == 22


def test_wos_for_line_by_so_and_item_skips_cancelled():
    wos = [
        {"name": "WO-pk", "sales_order": "SO-1", "production_item": PK,
         "docstatus": 1, "status": "Not Started"},
        {"name": "WO-nd", "sales_order": "SO-1", "production_item": ND,
         "docstatus": 1, "status": "In Process"},
        {"name": "WO-can", "sales_order": "SO-1", "production_item": PK,
         "docstatus": 2, "status": "Cancelled"},
        {"name": "WO-other-so", "sales_order": "SO-2", "production_item": PK,
         "docstatus": 1, "status": "In Process"},
    ]
    got = {w["name"] for w in iss.wos_for_line(wos, "SO-1", PK)}
    assert got == {"WO-pk"}


def test_load_credentials_secret_before_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ERP_API_KEY", raising=False)
    monkeypatch.delenv("ERP_API_SECRET", raising=False)
    monkeypatch.delenv("PROD_ERP_API_KEY", raising=False)
    monkeypatch.delenv("PROD_ERP_API_SECRET", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "PROD_ERP_API_SECRET=the-secret\nPROD_ERP_API_KEY=the-key\n",
        encoding="utf-8",
    )
    key, secret = iss.load_credentials("prod", [env])
    assert key == "the-key"
    assert secret == "the-secret"


def test_paginated_get_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(iss, "api_get_status", lambda *a, **k: (500, {"exc": "boom"}))
    with pytest.raises(iss.QueryError):
        iss.paginated_get("Sales Order", "https://x", "k", "s", [], ["name"])


def test_add_months_end_of_month():
    assert iss.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert iss.add_months(date(2026, 8, 17), 3) == date(2026, 11, 17)


def test_classify_over_plan_uses_job_card_qty_not_header():
    wo = {
        "name": "WO-26-02609", "qty": 40, "produced_qty": 0,
        "status": "Not Started", "sales_order": "SO-1",
        "operations": [{"operation": "裁剪", "sequence_id": 1, "status": "Completed"}],
    }
    jcs = [
        {"operation": "裁剪", "status": "Completed", "for_quantity": 22,
         "total_completed_qty": 22},
        {"operation": "裁剪", "status": "Completed", "for_quantity": 22,
         "total_completed_qty": 22},
    ]
    ctx = {
        "so_rows": [{
            "so": "SO-1", "so_status": "To Deliver and Bill", "so_docstatus": 1,
            "qty": 40, "delivered_qty": 0, "open_qty": 40, "draft_dn": 0,
            "item_code": PK, "delivery_date": "2026-08-30",
            "transaction_date": "2026-08-17", "amended_from": None,
            "wos": [wo], "pps": [{"pp": "PP-1"}],
        }],
        "jc_map": {"WO-26-02609": jcs},
        "lead_months": 3, "dup_window": 3,
    }
    iss.classify_anomalies(ctx)
    kinds = {a["kind"] for a in ctx["anomalies"]}
    assert "工序完成量超计划" in kinds
    assert "工单状态未回写" in kinds
