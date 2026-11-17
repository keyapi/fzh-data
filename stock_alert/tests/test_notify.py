from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

from stock_alert.client import StockRow
from stock_alert.inbound import InboundSku, aggregate
from stock_alert.notify import (
    DINGTALK_MAX_BYTES,
    build_inbound_messages,
    build_low_stock_messages,
    inbound_line,
    low_stock_line,
    notify_inbound,
    notify_low_stock,
)
from stock_alert.scan import LowSku, apply_names, mark_new, scan


def _result():
    rows = {
        "美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", "A", 0, 8, 0, 0)],
        "美东-CENTRADE": [StockRow("美东-CENTRADE", "B", 9, 0, 0, 0)],
        "波兰-FZHPoland-covers": [StockRow("波兰-FZHPoland-covers", "C", 1, 21, 0, 0)],
    }
    return scan(rows, threshold=5)


def _marked_result():
    result = _result()
    apply_names(result, {"A": "产品甲"})
    mark_new(result, {"美中-FZH-DANEEY": {"A": 8}, "美东-CENTRADE": {}, "波兰-FZHPoland-covers": {"C": 8}},
             threshold=5)
    return result


def _big_result(n: int = 300):
    rows = {"美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", f"S{i:04d}", 0, 1) for i in range(n)]}
    result = scan(rows, threshold=5)
    long_name = "很长的产品名称" * 10  # 70 字，渲染时截到 60
    apply_names(result, {item.sku: long_name for item in result.warehouses[0].low})
    return result


def test_low_stock_line_formats_sku_name_and_available():
    assert low_stock_line(LowSku("A", 3, 0, "产品甲")) == "• A 产品甲：库存3个"
    assert low_stock_line(LowSku("A", 0, 2)) == "• A：库存0个"


def test_low_stock_line_does_not_repeat_sku_as_name():
    assert low_stock_line(LowSku("A", 3, 0, "A")) == "• A：库存3个"


def test_inbound_line_formats_qty():
    assert inbound_line(InboundSku("B", 45, "靠垫乙")) == "• B 靠垫乙：入库45个"
    assert inbound_line(InboundSku("B", 45)) == "• B：入库45个"


def test_build_low_stock_messages_lists_all_and_summary():
    messages = build_low_stock_messages(_marked_result(), when=_dt.date(2026, 11, 17), new_count=1)
    text = "\n".join(messages)
    assert "通途低库存提醒 · 2026-11-17" in text
    assert "共 **2** 个 SKU 可用库存 < 5" in text
    assert "今日新增 **1** 个" in text
    assert "美中-FZH-DANEEY（1 个）" in text
    assert "• A 产品甲：库存0个" in text
    assert "• C：库存1个" in text
    assert "口径：可用库存 < 5" in text


def test_build_low_stock_messages_zero_is_quiet():
    result = scan({"美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", "A", 99, 0)]}, threshold=5)
    messages = build_low_stock_messages(result, when=_dt.date(2026, 11, 17))
    assert len(messages) == 1
    assert "无 SKU 可用库存低于阈值" in messages[0]


def test_build_low_stock_messages_chunks_without_splitting_lines():
    result = _big_result(300)
    messages = build_low_stock_messages(result, when=_dt.date(2026, 11, 17))
    assert len(messages) >= 2
    assert all(len(m.encode("utf-8")) <= DINGTALK_MAX_BYTES for m in messages)
    assert "（第1/" in messages[0]
    assert any("（续）" in m for m in messages[1:])
    detail_lines = [line for m in messages for line in m.splitlines() if line.startswith("• ")]
    assert len(detail_lines) == 300


def test_build_inbound_messages_formats_and_dates():
    result = aggregate({"美中-FZH-DANEEY": [{"sku": "A", "voucher_type": "02", "available_increase": 45}]},
                       names={"A": "产品甲"}, day=_dt.date(2026, 11, 16))
    text = "\n".join(build_inbound_messages(result))
    assert "通途采购入库提醒 · 2026-11-16" in text
    assert "共 **1** 个 SKU 入库 **45** 件" in text
    assert "• A 产品甲：入库45个" in text


def test_build_inbound_messages_zero_says_none():
    result = aggregate({"美中-FZH-DANEEY": []}, day=_dt.date(2026, 11, 16))
    text = "\n".join(build_inbound_messages(result))
    assert "昨日（2026-11-16）无采购入库" in text


def test_notify_low_stock_dry_run_returns_text_and_xlsx(monkeypatch, tmp_path):
    for name in ("DINGTALK_WEBHOOK_STOCK", "DINGTALK_SECRET_STOCK", "DINGTALK_WEBHOOK", "DINGTALK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    resp = notify_low_stock(_marked_result(), when=_dt.date(2026, 11, 17),
                            out_xlsx=tmp_path / "new.xlsx", dry_run=True)
    assert resp["dry_run"] is True
    assert resp["messages"]
    assert Path(resp["xlsx"]).is_file()


def test_notify_low_stock_sends_text_then_card(monkeypatch, tmp_path):
    monkeypatch.setenv("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=xxx")
    monkeypatch.setenv("DINGTALK_SECRET", "SECtest")
    order: list[str] = []

    class _FakeSend:
        @staticmethod
        def send_markdown(text, title="通知", *, webhook=None, secret=None):
            order.append("text")
            return {"errcode": 0}

    class _FakeCard:
        @staticmethod
        def send_file_to_dingtalk(path, title=None, text=None, *, webhook=None, secret=None):
            order.append("card")
            return {"errcode": 0}

    import stock_alert.notify as notify_mod

    monkeypatch.setattr(notify_mod, "_robot_path", lambda: "")
    monkeypatch.setitem(sys.modules, "send_dingtalk", _FakeSend)
    monkeypatch.setitem(sys.modules, "send_file_card", _FakeCard)

    resp = notify_mod.notify_low_stock(_marked_result(), when=_dt.date(2026, 11, 17),
                                       out_xlsx=tmp_path / "new.xlsx")
    assert resp["errcode"] == 0
    assert order[-1] == "card"
    assert order.count("text") == resp["total"] >= 1
    assert resp["xlsx"].endswith("new.xlsx")


def test_notify_low_stock_card_failure_does_not_drop_text(monkeypatch, tmp_path):
    monkeypatch.setenv("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=xxx")
    monkeypatch.setenv("DINGTALK_SECRET", "SECtest")

    class _FakeSend:
        @staticmethod
        def send_markdown(text, title="通知", *, webhook=None, secret=None):
            return {"errcode": 0}

    class _FakeCard:
        @staticmethod
        def send_file_to_dingtalk(*a, **k):
            raise RuntimeError("upload down")

    import stock_alert.notify as notify_mod

    monkeypatch.setattr(notify_mod, "_robot_path", lambda: "")
    monkeypatch.setitem(sys.modules, "send_dingtalk", _FakeSend)
    monkeypatch.setitem(sys.modules, "send_file_card", _FakeCard)

    resp = notify_mod.notify_low_stock(_marked_result(), when=_dt.date(2026, 11, 17),
                                       out_xlsx=tmp_path / "new.xlsx")
    assert resp["sent"] == resp["total"]
    assert resp["card"]["errcode"] == -1
    assert resp["errcode"] == 1


def test_notify_inbound_dry_run_and_send(monkeypatch):
    result = aggregate({"美中-FZH-DANEEY": [{"sku": "A", "voucher_type": "02", "available_increase": 45}]},
                       day=_dt.date(2026, 11, 16))
    dry = notify_inbound(result, dry_run=True)
    assert dry["dry_run"] is True
    assert "入库" in "\n".join(dry["messages"])

    monkeypatch.setenv("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=xxx")
    monkeypatch.setenv("DINGTALK_SECRET", "SECtest")

    class _FakeSend:
        @staticmethod
        def send_markdown(text, title="通知", *, webhook=None, secret=None):
            return {"errcode": 0}

    import stock_alert.notify as notify_mod

    monkeypatch.setattr(notify_mod, "_robot_path", lambda: "")
    monkeypatch.setitem(sys.modules, "send_dingtalk", _FakeSend)
    resp = notify_mod.notify_inbound(result)
    assert resp["errcode"] == 0


def test_failure_body_524_adds_ip_and_hint():
    from stock_alert.notify import failure_body

    body = failure_body("业务码 524：unknown不在白名单列表里", egress_ip="1.2.3.4")
    assert "1.2.3.4" in body
    assert "白名单" in body


def test_failure_body_other_unchanged():
    from stock_alert.notify import failure_body

    assert failure_body("boom", egress_ip="1.2.3.4") == "boom"


def test_excel_write_failure_still_sends_details(monkeypatch, tmp_path):
    import stock_alert.notify as mod
    import stock_alert.excel as excel
    monkeypatch.setattr(mod, "_resolve_creds", lambda: ("webhook", "secret"))
    monkeypatch.setattr(mod, "_robot_path", lambda: "")
    sent = []
    def send(messages, *args):
        sent.extend(messages)
        return [{"errcode": 0} for _ in messages]
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(mod, "_send_markdowns", send)
    monkeypatch.setattr(excel, "write_low_stock_workbook", fail)
    result = mod.notify_low_stock(_marked_result(), out_xlsx=tmp_path / "new.xlsx")
    assert sent
    assert result["errcode"] == 1
    assert "disk full" in result["card"]["errmsg"]


def test_oversized_single_line_is_rejected_before_send():
    import pytest
    result = scan({"W": [StockRow("W", "长" * 10000, 1, 0)]})
    with pytest.raises(ValueError, match="字节"):
        build_low_stock_messages(result)
