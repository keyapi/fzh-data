from __future__ import annotations

import datetime as _dt
from pathlib import Path

from stock_alert.client import StockRow
from stock_alert.notify import build_body, notify, summarize
from stock_alert.scan import scan


def _result():
    rows = {
        "美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", "A", 0, 8, 0, 0)],
        "美东-CENTRADE": [StockRow("美东-CENTRADE", "B", 9, 0, 0, 0)],
        "波兰-FZHPoland-covers": [StockRow("波兰-FZHPoland-covers", "C", 1, 21, 0, 0)],
    }
    return scan(rows, threshold=5)


def test_summarize_lists_counts_and_intransit():
    text = summarize(_result(), when=_dt.date(2026, 10, 13))
    assert "通途低库存提醒 · 2026-10-13" in text
    assert "共 **2** 个 SKU" in text                 # 美中 1 + 波兰 1
    assert "美中-FZH-DANEEY：**1** 个（在途合计 8 件）" in text
    assert "美东-CENTRADE：**0** 个（在途合计 0 件）" in text
    assert "波兰-FZHPoland-covers：**1** 个（在途合计 21 件）" in text
    assert "口径：可用库存 < 5" in text


def test_summarize_zero_is_quiet():
    result = scan({"美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", "A", 99, 0, 0, 0)]}, threshold=5)
    text = summarize(result, when=_dt.date(2026, 10, 13))
    assert "无 SKU 可用库存低于阈值" in text


def test_notify_dry_run_returns_text_without_network(monkeypatch):
    # 明确不设凭证，dry_run 不应去读 —— 若读了会 KeyError
    monkeypatch.delenv("DINGTALK_WEBHOOK_STOCK", raising=False)
    monkeypatch.delenv("DINGTALK_SECRET_STOCK", raising=False)
    resp = notify(_result(), dry_run=True, when=_dt.date(2026, 10, 13))
    assert resp["dry_run"] is True
    assert resp["errcode"] == 0
    assert "通途低库存提醒" in resp["text"]
    assert resp["title"] == "通途低库存提醒 · 2026-10-13"


def test_notify_requires_credentials_when_sending(monkeypatch):
    for name in ("DINGTALK_WEBHOOK_STOCK", "DINGTALK_SECRET_STOCK", "DINGTALK_WEBHOOK", "DINGTALK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    try:
        notify(_result(), when=_dt.date(2026, 10, 13))
    except KeyError as exc:
        assert "DINGTALK_WEBHOOK_STOCK" in str(exc) or "DINGTALK_WEBHOOK" in str(exc)
    else:
        raise AssertionError("缺凭证时应报错")


def test_notify_falls_back_to_default_robot(monkeypatch):
    """未设 STOCK 专用键时，应复用默认机器人（原群）。"""
    monkeypatch.delenv("DINGTALK_WEBHOOK_STOCK", raising=False)
    monkeypatch.delenv("DINGTALK_SECRET_STOCK", raising=False)
    monkeypatch.setenv("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=xxx")
    monkeypatch.setenv("DINGTALK_SECRET", "SECtest")

    captured = {}

    class _FakeSend:
        @staticmethod
        def send_markdown(text, title="通知", *, webhook=None, secret=None):
            captured["webhook"] = webhook
            captured["secret"] = secret
            return {"errcode": 0}

    import stock_alert.notify as notify_mod

    monkeypatch.setattr(notify_mod, "_robot_path", lambda: "")
    import sys

    monkeypatch.setitem(sys.modules, "send_dingtalk", _FakeSend)

    resp = notify_mod.notify(_result(), when=_dt.date(2026, 10, 13))
    assert resp["errcode"] == 0
    assert captured["webhook"].endswith("access_token=xxx")
    assert captured["secret"] == "SECtest"


def _big_result(n: int = 20):
    rows = {"美中-FZH-DANEEY": [StockRow("美中-FZH-DANEEY", f"S{i}", 0, i + 1) for i in range(n)]}
    return scan(rows, threshold=5)


def test_build_body_small_inlines_details():
    text, need_file = build_body(_result(), when=_dt.date(2026, 10, 14), small_threshold=10)
    assert need_file is False
    assert "可用 0　在途 8" in text  # 明细行内联


def test_build_body_large_uses_file():
    text, need_file = build_body(_big_result(20), when=_dt.date(2026, 10, 14), small_threshold=10)
    assert need_file is True
    assert "共 **20** 个 SKU" in text
    assert "可用 0　在途 0" not in text  # 大样本不内联明细


def test_notify_dry_run_file_mode_writes_xlsx(tmp_path):
    resp = notify(_big_result(20), dry_run=True, when=_dt.date(2026, 10, 14),
                  out_xlsx=tmp_path / "o.xlsx", small_threshold=10)
    assert resp["mode"] == "file"
    assert Path(resp["xlsx"]).is_file()
    assert "共 **20** 个 SKU" in resp["text"]


def test_notify_file_mode_calls_send_file_card(monkeypatch, tmp_path):
    monkeypatch.delenv("DINGTALK_WEBHOOK_STOCK", raising=False)
    monkeypatch.delenv("DINGTALK_SECRET_STOCK", raising=False)
    monkeypatch.setenv("DINGTALK_WEBHOOK", "https://oapi.dingtalk.com/robot/send?access_token=xxx")
    monkeypatch.setenv("DINGTALK_SECRET", "SECtest")

    captured = {}

    class _FakeCard:
        @staticmethod
        def send_file_to_dingtalk(path, title=None, text=None, *, webhook=None, secret=None):
            captured.update(path=str(path), title=title, text=text, webhook=webhook, secret=secret)
            return {"errcode": 0}

    import sys

    import stock_alert.notify as notify_mod

    monkeypatch.setattr(notify_mod, "_robot_path", lambda: "")
    monkeypatch.setitem(sys.modules, "send_file_card", _FakeCard)

    resp = notify_mod.notify(_big_result(20), when=_dt.date(2026, 10, 14),
                             out_xlsx=tmp_path / "o.xlsx", small_threshold=10)
    assert resp["errcode"] == 0
    assert captured["path"].endswith("o.xlsx")
    assert captured["webhook"].endswith("access_token=xxx")
    assert captured["secret"] == "SECtest"
    assert "共 **20** 个 SKU" in captured["text"]
