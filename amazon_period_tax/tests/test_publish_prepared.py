# -*- coding: utf-8 -*-
"""R3 PREPARED / 完整回读 / partial / 恢复。

验收（``reports/t2_hardening_20261120.md`` R3）：
- 首个 clear 前保存目标全集快照、write_set、输入/输出预期、权限与恢复方案；
- 完整回读后 published；任一张表失败 → partial，下一批停线，绝不 published；
- 允许恢复时完整 write_set hash 100% 回到基线；外部并发变化恢复调用 0。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from publish_guard import (
    STATUS_BLOCKED,
    STATUS_PARTIAL,
    STATUS_PUBLISHED,
    WriteItem,
    prepare_publish,
    publish_prepared,
    recover_prepared,
    rows_hash,
)


class FakeGateway:
    """内存工作表：可注入写入失败/写错内容，并记录每次写。"""

    def __init__(self, initial: dict[str, list[list]] | None = None):
        self.data = {k: [list(r) for r in v] for k, v in (initial or {}).items()}
        self.writes: list[str] = []
        self.fail_on: set[str] = set()
        self.corrupt_on: set[str] = set()

    def read_values(self, title: str) -> list[list]:
        return [list(r) for r in self.data.get(title, [])]

    def write_values(self, title: str, rows: list[list]) -> None:
        self.writes.append(title)
        if title in self.fail_on:
            raise RuntimeError(f"boom {title}")
        if title in self.corrupt_on:
            self.data[title] = [["corrupted"]]
            return
        self.data[title] = [list(r) for r in rows]


BASE_A = [["渠道账号", "金额"], ["AMZA", 100]]
BASE_B = [["渠道账号", "金额"], ["AMZB", 200]]


def _items():
    return [
        WriteItem("A", [["渠道账号", "金额"], ["AMZA", 111]]),
        WriteItem("B", [["渠道账号", "金额"], ["AMZB", 222]]),
        WriteItem("C", [["渠道账号", "金额"], ["AMZC", 333]]),
    ]


def _gateway(**kw):
    return FakeGateway({"A": BASE_A, "B": BASE_B}, **kw)


# --------------------------------------------------------------- PREPARED


def test_prepare_snapshots_targets_before_any_write():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(
        gw,
        items,
        run_id="run1",
        inputs={"input_md5": "a" * 32},
        outputs={"rows": 3},
        permission_probe=lambda: {"ok": True},
    )
    assert gw.writes == []  # PREPARED 阶段一次 clear 都没有
    assert prepared["status"] == "prepared"
    assert prepared["permissions"]["status"] == "ok"
    assert prepared["inputs"]["input_md5"] == "a" * 32
    ws = {w["worksheet"]: w for w in prepared["write_set"]}
    assert ws["A"]["baseline_hash"] == rows_hash(BASE_A)
    assert ws["A"]["baseline_row_count"] == 2
    assert ws["C"]["existed"] is False
    plan = {p["worksheet"]: p for p in prepared["recovery_plan"]}
    assert plan["A"]["action"] == "restore_baseline_rows"
    assert plan["C"]["action"] == "clear_to_empty"


# --------------------------------------------------------------- 发布 / 回读


def test_publish_all_tables_is_published_after_readback():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1")
    result = publish_prepared(gw, items, prepared)
    assert result.status == STATUS_PUBLISHED
    assert result.published is True
    assert result.written == ["A", "B", "C"]
    assert all(rb["match"] for rb in result.readback.values())
    assert gw.data["A"] == [["渠道账号", "金额"], ["AMZA", 111]]


def test_second_table_write_failure_is_partial_and_never_published():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1")
    gw.fail_on.add("B")
    result = publish_prepared(gw, items, prepared)
    assert result.status == STATUS_PARTIAL
    assert result.published is False
    assert result.written == ["A"]
    assert result.failed_worksheet == "B"
    # 第 3 张表绝不能再写（下一批停线）
    assert "C" not in gw.writes
    assert "C" not in gw.data


def test_second_table_readback_mismatch_is_partial():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1")
    gw.corrupt_on.add("B")
    result = publish_prepared(gw, items, prepared)
    assert result.status == STATUS_PARTIAL
    assert result.published is False
    assert result.readback["B"]["match"] is False
    assert "C" not in gw.writes


def test_permission_probe_failure_blocks_publish():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1", permission_probe=lambda: 1 / 0)

    def boom():
        raise ZeroDivisionError("no")

    prepared["permissions"] = {"probed": True, "status": "failed", "error": "no"}
    result = publish_prepared(gw, items, prepared)
    assert result.status == STATUS_BLOCKED
    assert gw.writes == []


def test_target_changed_after_prepare_blocks_all_writes():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1")
    gw.data["A"] = [["外部", "改动"]]  # 准备后被外部编辑
    result = publish_prepared(gw, items, prepared)
    assert result.status == STATUS_BLOCKED
    assert gw.writes == []


# --------------------------------------------------------------- 恢复


def test_recovery_restores_full_write_set_to_baseline():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1")
    gw.fail_on.add("C")
    result = publish_prepared(gw, items, prepared)
    assert result.published is False
    recovery = recover_prepared(gw, items, prepared, allow=True)
    assert recovery["recovered"] is True
    assert recovery["attempts"] == 2  # A、B 被写过 → 都恢复
    assert rows_hash(gw.read_values("A")) == rows_hash(BASE_A)
    assert rows_hash(gw.read_values("B")) == rows_hash(BASE_B)
    # 没被写过的 C 仍是空（从未创建），也在基线状态
    assert gw.read_values("C") == []


def test_recovery_refused_with_zero_attempts_on_external_change():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1")
    gw.fail_on.add("C")
    publish_prepared(gw, items, prepared)
    gw.data["A"] = [["外部", "又改了"]]  # 失败后有人动了目标
    recovery = recover_prepared(gw, items, prepared, allow=True)
    assert recovery["recovered"] is False
    assert recovery["refused"] == "external_concurrent_change"
    assert recovery["attempts"] == 0
    assert gw.data["A"] == [["外部", "又改了"]]  # 一个字节都没被覆盖


def test_recovery_refused_when_not_allowed():
    gw = _gateway()
    items = _items()
    prepared = prepare_publish(gw, items, run_id="run1")
    gw.fail_on.add("C")
    publish_prepared(gw, items, prepared)
    recovery = recover_prepared(gw, items, prepared, allow=False)
    assert recovery == {"recovered": False, "refused": "recovery_not_allowed", "attempts": 0}


# --------------------------------------------------------------- run_phase3 接入


def _stub(monkeypatch, tmp_path, gateway):
    import phase3_gsheet
    import phase3_merge as m

    df_row = pd.DataFrame(
        {
            "审批编号": ["A1"],
            "销售账户": ["AMZAUS"],
            "渠道账号": ["AMZAUS"],
            "运营人员": ["甲"],
            "收款归属": ["平台"],
            "选择平台": ["亚马逊"],
            "应收金额": [100.0],
            "销售额": [200.0],
            "汇率": [7.0],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
        }
    )
    df_group = pd.DataFrame(
        {
            "渠道账号": ["AMZAUS"],
            "运营人员": ["甲"],
            "收款归属": ["平台"],
            "应收金额_人民币": [700.0],
            "销售额_人民币": [1400.0],
            "佣金_人民币": [70.0],
            "收款费用累加人民币": [0.0],
        }
    )
    df_tax = pd.DataFrame({"渠道账号": ["AMZAUS"], "Tax amount人民币": [0.0]})
    df_merged = pd.DataFrame(
        {"渠道账号": ["AMZAUS"], "Tax amount人民币": [0.0], "附加费累加人民币": [0.0]}
    )
    master = pd.DataFrame({"渠道": ["Amazon"], "渠道账号": ["AMZAUS"], "运营人员": ["甲"]})

    monkeypatch.setattr(m, "load_oa_dataframe", lambda path, failures_out=None: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(m, "drop_april_resubmit_rows", lambda df, month: (df, 0))
    monkeypatch.setattr(m, "load_exchange_rate_table", lambda gc, month_col: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(m, "load_channel_accounts", lambda gc, month: (master, pd.DataFrame()))
    monkeypatch.setattr(
        m, "build_row_level_df", lambda *a, **k: (df_row, pd.Series([True], index=df_row.index))
    )
    monkeypatch.setattr(m, "build_group_account_cost", lambda *a, **k: df_group)
    monkeypatch.setattr(m, "build_rmb_by_account", lambda df_group: df_group.copy())
    monkeypatch.setattr(m, "load_additional_fee_grouped", lambda *a, **k: (pd.DataFrame(), []))
    monkeypatch.setattr(m, "load_tax_grouped", lambda *a, **k: (df_tax, []))
    monkeypatch.setattr(m, "merge_rmb_tax_additional", lambda *a, **k: df_merged)
    monkeypatch.setattr(m, "phase3_spreadsheet_available", lambda gc: True)
    monkeypatch.setattr(m, "read_worksheet_df", lambda gc, name: pd.DataFrame())
    monkeypatch.setattr(m, "build_fba_summary", lambda *a, **k: (pd.DataFrame(), {"errors": []}))
    monkeypatch.setattr(phase3_gsheet, "sort_phase3_tabs", lambda gc, pin_worksheet: None)
    monkeypatch.setenv("PERIOD_WRITE_MANIFEST_DIR", str(tmp_path / "manifests"))


def test_run_phase3_guarded_partial_never_published(monkeypatch, tmp_path):
    from phase3_merge import PublishOptions, run_phase3

    gw = FakeGateway()
    _stub(monkeypatch, tmp_path, gw)
    gw.fail_on.add("人民币20260804-20260903")  # 第 2 张表失败

    with pytest.raises(RuntimeError, match="未完成"):
        run_phase3(
            gc=None,
            input_xlsx=Path("x.xlsx"),
            bucket="账期20260804-20260903",
            exchange_month="202608",
            bucket_dir=tmp_path,
            write_gsheet=True,
            publish_options=PublishOptions(
                guarded=True, require_policy=False, require_fx=False, require_receipt=False
            ),
            publish_gateway=gw,
        )
    assert "人民币20260804-20260903" not in gw.data  # 第一张写成功，第二张失败

    manifests = list((tmp_path / "manifests").glob("*.json"))
    assert any(p.name.endswith(".prepared.json") for p in manifests)
    import json

    finals = [json.loads(p.read_text(encoding="utf-8")) for p in manifests if not p.name.endswith(".prepared.json")]
    assert finals and all(m.get("status") == "partial" for m in finals)
    assert all(m["publish"]["published"] is False for m in finals)


def test_run_phase3_guarded_success_is_published(monkeypatch, tmp_path):
    from phase3_merge import PublishOptions, run_phase3

    gw = FakeGateway()
    _stub(monkeypatch, tmp_path, gw)
    rep, _ = run_phase3(
        gc=None,
        input_xlsx=Path("x.xlsx"),
        bucket="账期20260804-20260903",
        exchange_month="202608",
        bucket_dir=tmp_path,
        write_gsheet=True,
        publish_options=PublishOptions(
            guarded=True, require_policy=False, require_fx=False, require_receipt=False
        ),
        publish_gateway=gw,
    )
    assert rep.publish_status == STATUS_PUBLISHED
    assert len(rep.worksheets_written) == 5
