# -*- coding: utf-8 -*-
"""en_live 契约测试：全部离线（HTTP 由伪响应 monkeypatch）。"""

from __future__ import annotations

import json
import math
from datetime import date

import pandas as pd
import pytest

import supply_copilot.en_live as en_live


# --------------------------------------------------------------------------- 测试替身
class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)[:200]

    def json(self):
        return self._payload


class FakeClient:
    """按 doctype 返回预置行，记录调用；忽略 filters/分页细节。"""

    def __init__(self, pages: dict[str, list[dict]] | None = None):
        self.pages = {k: list(v) for k, v in (pages or {}).items()}
        self.calls: list[dict] = []

    def list_page(self, doctype, fields, filters=None, order_by=None,
                  limit_start=0, limit_page_length=1):
        self.calls.append(dict(method="list_page", doctype=doctype, filters=filters,
                               order_by=order_by, limit_start=limit_start,
                               limit_page_length=limit_page_length))
        rows = self.pages.get(doctype, [])
        end = limit_start + limit_page_length if limit_page_length else None
        return [dict(r) for r in rows[limit_start:end]]

    def fetch_all(self, doctype, fields, filters=None, order_by=None,
                  page_size=500, max_pages=400):
        self.calls.append(dict(method="fetch_all", doctype=doctype,
                               filters=filters, order_by=order_by))
        return [dict(r) for r in self.pages.get(doctype, [])]

    def called(self, doctype: str) -> list[dict]:
        return [c for c in self.calls if c["doctype"] == doctype]


def sku_map_fixture(*pairs: tuple[str, str]) -> pd.DataFrame:
    """(tongtool_sku, item_code) → load_sku_map 同形表。"""
    rows = []
    for tongtool_sku, item_code in pairs:
        rows.append({
            "item_code": item_code,
            "tongtool_sku": tongtool_sku,
            "customer_name": "test",
            "item_codes": (item_code,),
            "n_items": 1,
            "mapping_status": "mapped",
        })
    return pd.DataFrame(rows)


WAREHOUSE_CFG = en_live.load_warehouse_config()


def run_row(**overrides) -> dict:
    row = {
        "name": "20261123T051745",
        "run_id": "20261123T051745",
        "job": "stock_snapshot",
        "status": "Success",
        "complete": 1,
        "snapshot_date": "2026-11-23",
        "snapshot_at": "2026-11-23 05:17:45.182167",
        "row_count": 2,
        "warehouse_count": 10,
    }
    row.update(overrides)
    return row


def stock_row(sku="SKU1", warehouse="美东-CENTRADE", **overrides) -> dict:
    row = {
        "stock_key": f"{warehouse}:{sku}",
        "warehouse": warehouse,
        "warehouse_id": "WH1",
        "sku": sku,
        "available": 5.0,
        "intransit": 1.0,
        "waiting_shipment": 2.0,
        "defects": 0.0,
        "snapshot_at": "2026-11-23 05:17:45.182167",
        "run_id": "20261123T051745",
    }
    row.update(overrides)
    return row


def so_row(**overrides) -> dict:
    row = {
        "name": "SO-26-00001",
        "status": "To Deliver and Bill",
        "docstatus": 1,
        "customer": "DANEEY",
        "transaction_date": "2026-11-01",
        "delivery_date": "2026-12-01",
        "set_warehouse": None,
        "item_row": "row1",
        "item_code": "PK#KS1-DM-140",
        "customer_item_code": "TT1",
        "qty": 10.0,
        "delivered_qty": 4.0,
        "stock_uom": "个",
        "uom": "个",
        "warehouse": "半成品仓 - FZH",
        "items.delivery_date": "2026-12-01",
    }
    row.update(overrides)
    return row


def po_row(**overrides) -> dict:
    row = {
        "name": "PO-26-00001",
        "status": "To Receive and Bill",
        "docstatus": 1,
        "supplier": "绍兴泰泽科技有限公司",
        "transaction_date": "2026-11-01",
        "schedule_date": "2026-11-15",
        "set_warehouse": None,
        "item_row": "prow1",
        "item_code": "KS1-DM-140",
        "qty": 100.0,
        "received_qty": 40.0,
        "stock_uom": "个",
        "warehouse": "成品仓 - FZH",
        "items.schedule_date": "2026-11-15",
        "items.expected_delivery_date": None,
        "items.sales_order": None,
    }
    row.update(overrides)
    return row


# --------------------------------------------------------------------------- 客户端
def test_client_retries_429_then_succeeds(monkeypatch):
    calls = []
    responses = [FakeResponse(429, {"exc": "rate limit"}),
                 FakeResponse(200, {"data": [{"name": "A"}]})]

    def fake_request(self, method, url, headers=None, params=None, timeout=None):
        calls.append({"method": method, "url": url, "params": params})
        return responses.pop(0)

    monkeypatch.setattr(en_live.requests.Session, "request", fake_request)
    monkeypatch.setattr(en_live.time, "sleep", lambda *_: None)

    c = en_live.EnLiveClient(api_key="SECRET_KEY_123", api_secret="SECRET_VALUE_456",
                             base_url="https://en.test", min_interval=0)
    rows = c.list_page("Sales Order", ["name"])
    assert rows == [{"name": "A"}]
    assert len(calls) == 2
    assert calls[0]["method"] == "GET"


def test_client_403_fails_without_retry_and_hides_credentials(monkeypatch):
    calls = []

    def fake_request(self, method, url, headers=None, params=None, timeout=None):
        calls.append(url)
        return FakeResponse(403, {"exc": "forbidden"})

    monkeypatch.setattr(en_live.requests.Session, "request", fake_request)
    c = en_live.EnLiveClient(api_key="SECRET_KEY_123", api_secret="SECRET_VALUE_456",
                             base_url="https://en.test", min_interval=0)
    with pytest.raises(en_live.EnLiveError) as exc:
        c.list_page("Sales Order", ["name"])
    assert exc.value.status == 403
    assert len(calls) == 1
    text = str(exc.value)
    assert "SECRET_KEY_123" not in text and "SECRET_VALUE_456" not in text


def test_client_requires_credentials(monkeypatch):
    monkeypatch.setattr(en_live, "load_env", lambda *_a, **_k: {})
    monkeypatch.delenv("ERP_API_KEY", raising=False)
    monkeypatch.delenv("ERP_API_SECRET", raising=False)
    with pytest.raises(en_live.EnLiveError):
        en_live.EnLiveClient(base_url="https://en.test")


def test_client_paginates(monkeypatch):
    calls = []

    def fake_request(self, method, url, headers=None, params=None, timeout=None):
        calls.append(dict(params))
        if params["limit_start"] == 0:
            return FakeResponse(200, {"data": [{"name": "A"}, {"name": "B"}]})
        return FakeResponse(200, {"data": [{"name": "C"}]})

    monkeypatch.setattr(en_live.requests.Session, "request", fake_request)
    monkeypatch.setattr(en_live.time, "sleep", lambda *_: None)
    c = en_live.EnLiveClient(api_key="k", api_secret="s", base_url="https://en.test",
                             min_interval=0)
    rows = c.fetch_all("Sales Order", ["name"], page_size=2)
    assert [r["name"] for r in rows] == ["A", "B", "C"]
    assert calls[0]["limit_start"] == 0 and calls[0]["limit_page_length"] == 2
    assert calls[1]["limit_start"] == 2


def test_client_pagination_budget_is_not_silent(monkeypatch):
    def fake_request(self, method, url, headers=None, params=None, timeout=None):
        return FakeResponse(200, {"data": [{"name": "A"}, {"name": "B"}]})

    monkeypatch.setattr(en_live.requests.Session, "request", fake_request)
    monkeypatch.setattr(en_live.time, "sleep", lambda *_: None)
    c = en_live.EnLiveClient(api_key="k", api_secret="s", base_url="https://en.test",
                             min_interval=0)
    with pytest.raises(en_live.EnLiveError):
        c.fetch_all("Sales Order", ["name"], page_size=2, max_pages=2)


# --------------------------------------------------------------------------- 库存快照
def test_stock_snapshot_contract_and_meta():
    fake = FakeClient({
        en_live.RUN_DOCTYPE: [run_row()],
        en_live.STOCK_DOCTYPE: [stock_row(), stock_row(sku="SKU2", warehouse="美中-FZH-DANEEY")],
    })
    frame, meta = en_live.fetch_stock_snapshot(_client=fake)
    required = {"snapshot_date", "snapshot_at", "run_id", "warehouse_name",
                "sku", "available", "intransit", "waiting_shipment", "defects"}
    assert required.issubset(set(frame.columns))
    assert len(frame) == 2
    assert set(frame["warehouse_name"]) == {"美东-CENTRADE", "美中-FZH-DANEEY"}
    assert set(frame["sku"]) == {"SKU1", "SKU2"}
    assert frame["available"].tolist() == [5.0, 5.0]
    assert set(frame["run_id"]) == {"20261123T051745"}
    assert set(frame["snapshot_date"].astype(str)) == {"2026-11-23"}
    assert meta["run_id"] == "20261123T051745"
    assert meta["rows"] == 2
    assert meta["warehouses"] == ["美东-CENTRADE", "美中-FZH-DANEEY"]
    assert meta["snapshot_at"] == "2026-11-23 05:17:45.182167"


def test_stock_snapshot_http_pagination(monkeypatch):
    stock_rows = [stock_row(sku="A"), stock_row(sku="B"), stock_row(sku="C")]
    calls = []

    def fake_request(self, method, url, headers=None, params=None, timeout=None):
        calls.append((url, dict(params)))
        if "Tongtool%20Stock%20Run" in url or "Tongtool Stock Run" in url:
            return FakeResponse(200, {"data": [run_row(row_count=3)]})
        start = int(params["limit_start"])
        return FakeResponse(200, {"data": stock_rows[start:start + 2]})

    monkeypatch.setattr(en_live.requests.Session, "request", fake_request)
    monkeypatch.setattr(en_live.time, "sleep", lambda *_: None)
    c = en_live.EnLiveClient(api_key="k", api_secret="s", base_url="https://en.test",
                             min_interval=0)
    frame, meta = en_live.fetch_stock_snapshot(_client=c, page_size=2)
    assert list(frame["sku"]) == ["A", "B", "C"]
    stock_calls = [p for u, p in calls if "Stock%20Latest" in u or "Stock Latest" in u]
    assert [p["limit_start"] for p in stock_calls] == [0, 2]


def test_stock_snapshot_row_count_mismatch_is_rejected():
    fake = FakeClient({
        en_live.RUN_DOCTYPE: [run_row(row_count=5)],
        en_live.STOCK_DOCTYPE: [stock_row()],
    })
    with pytest.raises(en_live.EnLiveError):
        en_live.fetch_stock_snapshot(_client=fake)


def test_stock_snapshot_empty_run_is_an_error():
    fake = FakeClient({en_live.RUN_DOCTYPE: []})
    with pytest.raises(en_live.EnLiveError):
        en_live.fetch_stock_snapshot(_client=fake)


def test_stock_snapshot_empty_rows_returns_empty_frame():
    fake = FakeClient({
        en_live.RUN_DOCTYPE: [run_row(row_count=0)],
        en_live.STOCK_DOCTYPE: [],
    })
    frame, meta = en_live.fetch_stock_snapshot(_client=fake)
    assert frame.empty
    assert list(frame.columns) == en_live.STOCK_COLUMNS
    assert meta["rows"] == 0 and meta["warehouses"] == []


# --------------------------------------------------------------------------- 开放 SO
def test_open_so_filters_closed_zero_and_maps_canonical():
    fake = FakeClient({en_live.SO_DOCTYPE: [
        so_row(name="SO-CLOSED", status="Closed", qty=10, delivered_qty=0),
        so_row(name="SO-ZERO", qty=10, delivered_qty=10),
        so_row(name="SO-OPEN"),  # qty 10 - delivered 4 = 6
        so_row(name="SO-UNKNOWN", customer="未知客户", customer_item_code="",
               item_code="RAW1", stock_uom="", uom="", qty=3, delivered_qty=0),
    ]})
    frame, meta = en_live.fetch_open_so(
        _client=fake, sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
        warehouse_cfg=WAREHOUSE_CFG)
    assert set(frame["document_key"]) == {"SO-OPEN", "SO-UNKNOWN"}
    opened = frame.set_index("document_key").loc["SO-OPEN"]
    assert opened["canonical_sku"] == "KS1-DM-140"
    assert opened["canonical_warehouse"] == "美中-FZH-DANEEY"
    assert opened["canonical_uom"] == "个"
    assert opened["quantity"] == 6.0
    assert opened["branch"] == "USTX"
    unknown = frame.set_index("document_key").loc["SO-UNKNOWN"]
    assert unknown["canonical_sku"] == "RAW1"
    assert unknown["canonical_warehouse"] == ""
    assert unknown["canonical_uom"] == ""
    assert meta["rows"] == 2
    assert meta["quantity"] == 9.0
    assert meta["skipped"] == dict(status_closed=1, zero_open=1,
                                   missing_quantity=0, branch_mismatch=0)
    assert meta["empty_warehouse"] == 1 and meta["empty_uom"] == 1


def test_open_so_branch_filter():
    fake = FakeClient({en_live.SO_DOCTYPE: [
        so_row(name="SO-U", customer="CENTRADE"),
        so_row(name="SO-T", customer="DANEEY"),
        so_row(name="SO-FBA", customer="美国FBA仓"),
    ]})
    frame, meta = en_live.fetch_open_so(
        "USNJ", _client=fake, sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
        warehouse_cfg=WAREHOUSE_CFG)
    assert list(frame["document_key"]) == ["SO-U"]
    assert frame.iloc[0]["canonical_warehouse"] == "美东-CENTRADE"
    assert meta["skipped"]["branch_mismatch"] == 2


def test_open_so_requires_quantity():
    fake = FakeClient({en_live.SO_DOCTYPE: [so_row(qty=None, delivered_qty=0)]})
    frame, meta = en_live.fetch_open_so(
        _client=fake, sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
        warehouse_cfg=WAREHOUSE_CFG)
    assert frame.empty
    assert list(frame.columns) == en_live.SO_COLUMNS
    assert meta["skipped"]["missing_quantity"] == 1


def test_open_so_malformed_delivered_is_not_guessed():
    fake = FakeClient({en_live.SO_DOCTYPE: [so_row(delivered_qty="bad")]})
    frame, meta = en_live.fetch_open_so(
        _client=fake, sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
        warehouse_cfg=WAREHOUSE_CFG)
    assert frame.empty
    assert meta["skipped"]["missing_quantity"] == 1


def test_open_so_rejects_unknown_branch():
    with pytest.raises(ValueError):
        en_live.fetch_open_so("NOPE", _client=FakeClient({}),
                              sku_map=sku_map_fixture(), warehouse_cfg=WAREHOUSE_CFG)


def test_open_so_empty_table():
    frame, meta = en_live.fetch_open_so(
        _client=FakeClient({}), sku_map=sku_map_fixture(),
        warehouse_cfg=WAREHOUSE_CFG)
    assert frame.empty
    assert list(frame.columns) == en_live.SO_COLUMNS
    assert meta["rows"] == 0 and meta["quantity"] == 0.0


# --------------------------------------------------------------------------- 开放 PO
def test_open_po_contract_and_filters():
    fake = FakeClient({en_live.PO_DOCTYPE: [
        po_row(),  # open 60
        po_row(name="PO-CLOSED", status="Closed"),
        po_row(name="PO-FULL", qty=10, received_qty=10),
        po_row(name="PO-NOETA", **{"items.expected_delivery_date": None}),
    ]})
    frame, meta = en_live.fetch_open_po(_client=fake)
    required = {"document_key", "sku", "ordered", "open_qty", "warehouse"}
    assert required.issubset(set(frame.columns))
    assert set(frame["document_key"]) == {"PO-26-00001", "PO-NOETA"}
    first = frame.set_index("document_key").loc["PO-26-00001"]
    assert first["sku"] == "KS1-DM-140"
    assert first["ordered"] == 100.0
    assert first["open_qty"] == 60.0
    assert first["warehouse"] == "成品仓 - FZH"
    assert first["eta"] == ""
    assert meta["rows"] == 2
    assert meta["quantity"] == 120.0
    assert meta["skipped"] == dict(status_closed=1, zero_open=1, missing_quantity=0)
    assert meta["empty_eta"] == 2


def test_open_po_missing_quantity_and_empty_table():
    fake = FakeClient({en_live.PO_DOCTYPE: [po_row(qty=None, received_qty=0)]})
    frame, meta = en_live.fetch_open_po(_client=fake)
    assert frame.empty and meta["skipped"]["missing_quantity"] == 1

    fake = FakeClient({en_live.PO_DOCTYPE: [po_row(received_qty="bad")]})
    frame, meta = en_live.fetch_open_po(_client=fake)
    assert frame.empty and meta["skipped"]["missing_quantity"] == 1

    frame, meta = en_live.fetch_open_po(_client=FakeClient({}))
    assert frame.empty
    assert list(frame.columns) == en_live.PO_COLUMNS
    assert meta["rows"] == 0 and meta["quantity"] == 0.0


# --------------------------------------------------------------------------- 证据链
def test_chain_links_and_marks_unlinked():
    fake = FakeClient({
        en_live.SO_DOCTYPE: [so_row(name="SO-1", transaction_date=date.today().isoformat())],
        en_live.WO_DOCTYPE: [{
            "name": "WO-1", "status": "In Process", "docstatus": 1,
            "production_item": "PK#KS1-DM-140", "qty": 10.0, "produced_qty": 3.0,
            "sales_order": "SO-1", "fg_warehouse": "半成品仓 - FZH",
            "planned_start_date": "2026-11-10", "actual_end_date": None,
        }],
        en_live.DN_DOCTYPE: [{
            "name": "DN-1", "status": "To Bill", "docstatus": 1, "customer": "DANEEY",
            "posting_date": "2026-11-12", "lr_no": "TRACK1", "item_row": "drow1",
            "item_code": "PK#KS1-DM-140", "qty": 4.0, "warehouse": "成品仓 - FZH",
            "against_sales_order": "SO-1",
        }],
        en_live.PO_DOCTYPE: [po_row(name="PO-1", **{"items.sales_order": ""})],
        en_live.PACKAGE_DOCTYPE: [{
            "name": "P1", "package_id": "P1", "tracking_number": "TRACK1",
            "status": "Synced", "warehouse": "FZH-DANEEY-皮壳仓库",
            "order_id": "CUS-112-0000000-0000000",
        }],
    })
    frame = en_live.fetch_chain(
        "TT1", _client=fake, sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
        warehouse_cfg=WAREHOUSE_CFG)
    nodes = frame.set_index("node")
    assert nodes.loc["SO", "linked"] == True  # noqa: E712
    assert nodes.loc["WO", "linked"] == True  # noqa: E712
    assert nodes.loc["DN", "linked"] == True  # noqa: E712
    assert nodes.loc["PO", "linked"] == False  # noqa: E712
    assert nodes.loc["PO", "reason"] == "missing_sales_order"
    assert nodes.loc["PACKAGE", "linked"] == True  # noqa: E712
    assert nodes.loc["PACKAGE", "link_basis"] == "dn.lr_no=tracking"
    assert frame.attrs["meta"]["canonical_codes"] == ["KS1-DM-140"]
    # 关联键是带前缀的皮壳 → 需标注转换假设
    assert "conversion_assumed" in nodes.loc["SO", "link_basis"]


def test_chain_filter_shapes_parent_vs_child_table():
    """父单字段必须三元组；子表字段必须四元组（否则 Frappe 把首项当 doctype → 404）。"""
    fake = FakeClient({
        en_live.SO_DOCTYPE: [so_row(name="SO-1", transaction_date=date.today().isoformat())],
        en_live.WO_DOCTYPE: [{
            "name": "WO-1", "production_item": "PK#KS1-DM-140", "sales_order": "SO-1",
        }],
        en_live.DN_DOCTYPE: [{
            "name": "DN-1", "item_row": "d1", "item_code": "PK#KS1-DM-140",
            "against_sales_order": "SO-1",
        }],
        en_live.PO_DOCTYPE: [po_row(name="PO-1", **{"items.sales_order": "SO-1"})],
    })
    en_live.fetch_chain("TT1", _client=fake,
                        sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
                        warehouse_cfg=WAREHOUSE_CFG)
    parent_filters = [f for call in fake.called(en_live.WO_DOCTYPE)
                      for f in call["filters"] if f[0] == "sales_order"]
    assert parent_filters and all(len(f) == 3 for f in parent_filters)
    for doctype, table in ((en_live.DN_DOCTYPE, "Delivery Note Item"),
                           (en_live.PO_DOCTYPE, "Purchase Order Item")):
        child_filters = [f for call in fake.called(doctype)
                         for f in call["filters"] if len(f) == 4]
        assert child_filters and all(f[0] == table for f in child_filters)


def test_chain_package_without_keys_never_scans():
    fake = FakeClient({
        en_live.SO_DOCTYPE: [so_row(name="SO-1", transaction_date=date.today().isoformat())],
    })
    frame = en_live.fetch_chain(
        "TT1", _client=fake, sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
        warehouse_cfg=WAREHOUSE_CFG)
    packages = frame[frame["node"] == "PACKAGE"]
    assert len(packages) == 1
    assert packages.iloc[0]["linked"] == False  # noqa: E712
    assert packages.iloc[0]["reason"] == "no_order_or_tracking_key"
    assert fake.called(en_live.PACKAGE_DOCTYPE) == []


def test_chain_branch_filter_and_unknown_branch():
    fake = FakeClient({
        en_live.SO_DOCTYPE: [
            so_row(name="SO-U", customer="CENTRADE", transaction_date=date.today().isoformat()),
            so_row(name="SO-T", customer="DANEEY", transaction_date=date.today().isoformat()),
        ],
    })
    frame = en_live.fetch_chain(
        "TT1", branch="USNJ", _client=fake,
        sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
        warehouse_cfg=WAREHOUSE_CFG)
    assert list(frame[frame["node"] == "SO"]["document"]) == ["SO-U"]
    with pytest.raises(ValueError):
        en_live.fetch_chain("TT1", branch="NOPE", _client=fake,
                            sku_map=sku_map_fixture(("TT1", "KS1-DM-140")),
                            warehouse_cfg=WAREHOUSE_CFG)


def test_open_so_ambiguous_and_unmapped_sku_are_not_collapsed():
    mapping = pd.DataFrame([
        {"item_code": "A", "tongtool_sku": "AMB", "customer_name": "x",
         "item_codes": ("A", "B"), "n_items": 2, "mapping_status": "ambiguous"},
    ])
    fake = FakeClient({en_live.SO_DOCTYPE: [
        so_row(name="SO-A", customer_item_code="AMB", item_code="PK#A"),
        so_row(name="SO-U", customer_item_code="UNKNOWN", item_code="PK#A"),
    ]})
    frame, _ = en_live.fetch_open_so(_client=fake, sku_map=mapping,
                                     warehouse_cfg=WAREHOUSE_CFG)
    values = dict(zip(frame["document_key"], frame["canonical_sku"]))
    assert values["SO-A"] == "ambiguous:AMB"
    assert values["SO-U"] == "unmapped:UNKNOWN"


def test_no_nan_quantity_leaks_into_contracts():
    frame, _ = en_live.fetch_open_so(
        _client=FakeClient({en_live.SO_DOCTYPE: [so_row()]}),
        sku_map=sku_map_fixture(("TT1", "KS1-DM-140")), warehouse_cfg=WAREHOUSE_CFG)
    assert all(math.isfinite(v) for v in frame["quantity"])
