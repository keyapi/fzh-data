from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

import pytest

import stock_alert.cli as cli
from stock_alert.cli import main


@pytest.fixture(autouse=True)
def _isolate_output(monkeypatch, tmp_path):
    """CLI 测试不写真实 stock_alert_output，也不渲染图片卡片。"""
    monkeypatch.setenv("STOCK_ALERT_CARD_MODE", "text")
    import stock_alert.notify as notify_mod
    monkeypatch.setattr(notify_mod, "_OUT_DIR", tmp_path)


def test_run_mock_dry_run_shows_single_warehouse_summary(capsys):
    rc = main(["run", "--mock", "--dry-run", "--warehouses", "美中-FZH-DANEEY,美东-CENTRADE"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "低库存预警" in out
    assert "### 美中-FZH-DANEEY" in out
    assert "### 美东-CENTRADE" in out
    assert "今日新增：**2**" in out
    assert "今日新增：**1**" in out
    assert "低库存：" not in out
    assert out.count("## 低库存预警") == 1
    assert "波兰-FZHPoland-covers" not in out  # 只传了两仓


def test_run_mock_without_notify_does_not_push(capsys, monkeypatch):
    def _preview(*a, **k):
        assert k["dry_run"] is True
        return {"errcode": 0, "messages": ["低库存预警"], "files": [], "file_errors": []}

    monkeypatch.setattr(cli, "notify_low_stock", _preview)
    rc = cli.main(["run", "--mock", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    assert "低库存预警" in capsys.readouterr().out


def test_threshold_changes_result(capsys):
    rc = main(["run", "--mock", "--dry-run", "--threshold", "0", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    out = capsys.readouterr().out
    # 合成行：available = -1 / 0 / 10；阈值 0 时只有 -1 < 0 命中（0/0 仍被排除）
    assert "可用库存 < 0" in out
    assert "今日新增：**1**" in out


def test_inbound_mock_dry_run_defaults_to_yesterday(capsys):
    rc = main(["inbound", "--mock", "--dry-run", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    out = capsys.readouterr().out
    yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    assert "通途采购入库提醒" in out and "美中-FZH-DANEEY" in out and yesterday in out
    assert "• DEMO-IN-0：入库10个" in out


def test_inbound_mock_respects_date(capsys):
    rc = main(["inbound", "--mock", "--dry-run", "--date", "2026-11-16",
               "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2026-11-16" in out and "美中-FZH-DANEEY" in out


def test_inbound_mock_today_labels_window(capsys):
    rc = main(["inbound", "--mock", "--dry-run", "--today", "--source", "tongtool",
               "--warehouses", "W"])
    assert rc == 0
    out = capsys.readouterr().out
    assert _dt.date.today().isoformat() in out
    assert "截至" in out


def test_tongtool_intraday_uses_last_checked_state(monkeypatch, tmp_path, capsys):
    state_path = tmp_path / "inbound_state.json"
    state_path.write_text(
        '{"day": "%s", "last_checked_at": "%sT10:00:00"}' %
        (_dt.date.today().isoformat(), _dt.date.today().isoformat()),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "INBOUND_STATE", state_path)
    captured = {}

    def fake_collect(warehouses, since, until, **kwargs):
        captured["since"] = since
        captured["until"] = until
        return {}

    monkeypatch.setattr(cli, "collect_tongtool_inbound", fake_collect)
    rc = main(["inbound", "--dry-run", "--today", "--source", "tongtool", "--warehouses", "W"])
    assert rc == 0
    assert captured["since"] == _dt.datetime.combine(_dt.date.today(), _dt.time(10, 0))
    capsys.readouterr()
    # dry-run 不推进状态
    assert "T10:00:00" in state_path.read_text(encoding="utf-8")


def test_resolve_names_degrades_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "OUT_DIR", tmp_path)

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no cache")

    monkeypatch.setattr(cli, "NameCache", _Boom)
    names = cli._resolve_names(["A", "B"], SimpleNamespace(min_interval=13.0))
    assert not names or all(v == "" for v in names.values())


def test_inbound_only_resolves_names_for_real_receipts(monkeypatch, capsys):
    class En:
        def stock_changes(self, *args, **kwargs):
            return [{"sku": "CREATED", "voucher_type": "02", "available_increase": 0},
                    {"sku": "ARRIVED", "voucher_type": "02", "available_increase": 45}]
    monkeypatch.setattr(cli, "_make_en", lambda args: En())
    wanted = []
    def names(skus, args):
        wanted.extend(skus)
        return {"ARRIVED": "产品甲"}
    monkeypatch.setattr(cli, "_resolve_names", names)
    assert main(["inbound", "--dry-run", "--warehouses", "W"]) == 0
    assert wanted == ["ARRIVED"]
    out = capsys.readouterr()
    assert "• ARRIVED 产品甲：入库45个" in out.out
    assert '"zero_change": 1' in out.err


def test_inbound_sends_one_merged_card(monkeypatch, capsys):
    calls = []

    def fake(result, dry_run=False):
        calls.append([wh.warehouse for wh in result.warehouses])
        return {"errcode": 0, "messages": [], "files": [], "file_errors": [], "dry_run": True}

    monkeypatch.setattr(cli, "notify_inbound", fake)
    rc = main(["inbound", "--mock", "--dry-run", "--warehouses", "W1,W2,W3"])
    assert rc == 0
    assert calls == [["W1", "W2", "W3"]]
    capsys.readouterr()


def test_inbound_skips_empty_warehouses(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "INBOUND_STATE", tmp_path / "state.json")
    monkeypatch.setattr(cli, "collect_tongtool_inbound", lambda *a, **k: {"W1": [], "W2": []})
    calls = []

    def fake(result, dry_run=False):
        calls.append(result.warehouses[0].warehouse)
        return {"errcode": 0, "messages": [], "files": [], "file_errors": []}

    monkeypatch.setattr(cli, "notify_inbound", fake)
    rc = main(["inbound", "--dry-run", "--today", "--source", "tongtool", "--warehouses", "W1,W2"])
    assert rc == 0
    assert calls == []
    capsys.readouterr()
