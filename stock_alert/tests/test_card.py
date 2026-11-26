from __future__ import annotations

import datetime as _dt

import pytest

from stock_alert import card
from stock_alert.client import StockRow
from stock_alert.inbound import aggregate
from stock_alert.scan import apply_names, mark_new, scan

_CARD_ENV = {
    "DINGTALK_CLIENT_ID": "cid",
    "DINGTALK_CLIENT_SECRET": "secret",
    "DINGTALK_ROBOT_CODE": "robot",
    "DINGTALK_OPEN_CONVERSATION_ID": "cid-conv==",
    "DINGTALK_LOW_STOCK_TEMPLATE_ID": "low-tpl",
    "DINGTALK_INBOUND_TEMPLATE_ID": "in-tpl",
    "DINGTALK_OPERATOR_ID": "op-1",
}


def _low_result():
    rows = {
        "美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", "A", 0, 3)],
        "美东-CENTRADE": [],
    }
    result = scan(rows, threshold=5)
    apply_names(result, {"A": "靠垫甲"})
    mark_new(result, {"美中-FZH-DANEEY": {"A": 8}, "美东-CENTRADE": {}}, threshold=5)
    return result


def _inbound_result():
    return aggregate({"美中-FZH-DANEEY": [{"sku": "A", "voucher_type": "02", "available_increase": 45}],
                      "美东-CENTRADE": []},
                     names={"A": "靠垫甲"}, day=_dt.date(2026, 11, 16))


def test_config_requires_all_keys(monkeypatch):
    for key in _CARD_ENV:
        monkeypatch.delenv(key, raising=False)
    assert card.config("low") is None
    assert card.interactive_available("low") is False
    monkeypatch.setenv("DINGTALK_CLIENT_ID", "cid")
    monkeypatch.setenv("DINGTALK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("DINGTALK_OPEN_CONVERSATION_ID", "conv")
    monkeypatch.setenv("DINGTALK_LOW_STOCK_TEMPLATE_ID", "tpl")
    cfg = card.config("low")
    assert cfg and cfg["robot_code"] == "cid"  # 默认 = Client ID
    assert card.interactive_available("low") is True
    assert card.interactive_available("inbound") is False


def test_low_stock_params_are_strings_and_have_buttons():
    params = card.low_stock_params(
        _low_result(), when=_dt.date(2026, 11, 17), new_count=1,
        buttons=[("下载新增", "https://x/new"), ("下载全部", "https://x/all")],
    )
    assert params["title"] == "低库存预警"
    assert params["subtitle"] == "2026-11-17"
    assert "今日新增 **1** 个" in params["overview"]
    assert "美中-FZH-DANEEY" in params["body"]
    assert "低库存：" not in params["body"]
    assert params["btn1Title"] == "下载新增" and params["btn1Url"] == "https://x/new"
    assert params["btn2Title"] == "下载全部" and params["btn2Url"] == "https://x/all"
    assert all(isinstance(v, str) for v in params.values())


def test_inbound_params_include_products_and_empty_warehouse():
    params = card.inbound_params(_inbound_result(),
                                 buttons=[("下载明细", "https://x/in")])
    assert params["title"] == "通途采购入库提醒"
    assert params["subtitle"] == "2026-11-16 · 昨日入库"
    assert "共 **1** 个 SKU" in params["overview"]
    assert "**靠垫甲**" in params["body"] and "SKU：A" in params["body"]
    assert "昨日无采购入库" in params["body"]
    assert params["btn1Title"] == "下载明细"
    assert all(isinstance(v, str) for v in params.values())


def test_send_card_payload(monkeypatch):
    calls = []

    def fake_http(method, url, *, body=None, token=None, timeout=30):
        calls.append({"method": method, "url": url, "body": body, "token": token})
        if url.endswith("/oauth2/accessToken"):
            return 200, {"accessToken": "tok"}
        return 200, {"success": True, "result": {"outTrackId": "x"}}

    monkeypatch.setattr(card, "_http_json", fake_http)
    monkeypatch.setattr(card, "get_access_token", lambda cfg: "tok")
    resp = card.send_card(card.config("low"), {"title": "t", "body": "b"}, out_track_id="track-1")
    assert resp["mode"] == "interactive"
    send = calls[-1]
    assert send["url"].endswith("/v1.0/card/instances/createAndDeliver")
    assert send["token"] == "tok"
    assert send["body"]["openSpaceId"] == "cid-conv=="
    assert send["body"]["imGroupOpenDeliverModel"]["robotCode"] == "robot"
    assert send["body"]["cardData"]["cardParamMap"] == {"title": "t", "body": "b"}
    assert send["body"]["userId"] == "op-1"
    assert send["body"]["outTrackId"] == "track-1"


def test_send_card_raises_on_api_error(monkeypatch):
    monkeypatch.setattr(card, "get_access_token", lambda cfg: "tok")
    monkeypatch.setattr(card, "_http_json", lambda *a, **k: (400, {"code": "param.error"}))
    with pytest.raises(card.InteractiveCardError):
        card.send_card(card.config("low"), {"title": "t"})


def test_send_low_stock_requires_config(monkeypatch):
    for key in _CARD_ENV:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(card.InteractiveCardError):
        card.send_low_stock(_low_result())


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key, value in _CARD_ENV.items():
        monkeypatch.setenv(key, value)
