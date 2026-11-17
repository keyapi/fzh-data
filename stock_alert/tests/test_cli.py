from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

import stock_alert.cli as cli
from stock_alert.cli import main


def test_run_mock_dry_run_lists_details(capsys):
    rc = main(["run", "--mock", "--dry-run", "--warehouses", "美中-FZH-DANEEY,美东-CENTRADE"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "通途低库存提醒" in out
    assert "美中-FZH-DANEEY（1 个）" in out
    assert "美东-CENTRADE（1 个）" in out
    assert "• DEMO-0-A：库存4个" in out
    assert "波兰-FZHPoland-covers" not in out  # 只传了两仓


def test_run_mock_without_notify_does_not_push(capsys, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("未加 --notify 不应推送")

    monkeypatch.setattr(cli, "notify_low_stock", _boom)
    rc = cli.main(["run", "--mock", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    assert "通途低库存提醒" in capsys.readouterr().out


def test_threshold_changes_result(capsys):
    rc = main(["run", "--mock", "--dry-run", "--threshold", "0", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    out = capsys.readouterr().out
    # 合成行：available = -1 / 0 / 10；阈值 0 时只有 -1 < 0 命中（0/0 仍被排除）
    assert "可用库存 < 0" in out
    assert "共 **1** 个 SKU" in out


def test_inbound_mock_dry_run_defaults_to_yesterday(capsys):
    rc = main(["inbound", "--mock", "--dry-run", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    out = capsys.readouterr().out
    yesterday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
    assert f"通途采购入库提醒 · {yesterday}" in out
    assert "• DEMO-IN-0：入库10个" in out


def test_inbound_mock_respects_date(capsys):
    rc = main(["inbound", "--mock", "--dry-run", "--date", "2026-11-16",
               "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "通途采购入库提醒 · 2026-11-16" in out


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
    assert "ARRIVED 产品甲：入库45个" in out.out
    assert '"zero_change": 1' in out.err
