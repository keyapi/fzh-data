from __future__ import annotations

from stock_alert.cli import main


def test_run_mock_dry_run_prints_summary(capsys):
    rc = main(["run", "--mock", "--dry-run", "--warehouses", "美中-FZH-DANEEY,美东-CENTRADE"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "通途低库存提醒" in out
    assert "美中-FZH-DANEEY" in out
    assert "美东-CENTRADE" in out
    assert "波兰-FZHPoland-covers" not in out  # 只传了两仓


def test_run_mock_without_notify_does_not_push(capsys, monkeypatch):
    import stock_alert.cli as cli

    def _boom(*a, **k):
        raise AssertionError("未加 --notify 不应推送")

    monkeypatch.setattr(cli, "notify", _boom)
    rc = cli.main(["run", "--mock", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    assert "通途低库存提醒" in capsys.readouterr().out


def test_threshold_changes_result(capsys):
    rc = main(["run", "--mock", "--dry-run", "--threshold", "0", "--warehouses", "美中-FZH-DANEEY"])
    assert rc == 0
    out = capsys.readouterr().out
    # 合成行：available = -1 / 0 / 10；阈值 0 时只有 -1 < 0 命中
    assert "可用库存 < 0" in out
    assert "共 **1** 个 SKU" in out
