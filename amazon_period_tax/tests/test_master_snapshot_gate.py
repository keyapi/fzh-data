# -*- coding: utf-8 -*-
"""C1 主数据门禁：快照 metadata / live 与 snapshot 投影一致 / 未知别名只报告。

覆盖计划 U-C 的至少 12 个场景：缺 metadata、超 TTL、未来时间、错 source、hash 损坏、
live 不一致、live 不可读、缓存旧版本、空人员、空平台、收款归属 not_applicable、
未知别名（WFUS-Daneey）+ 大小写/零宽冲突。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import channel_canonical
from channel_account_sync import snapshot as snap_mod
from master_data import (
    live_projection,
    projection_differences,
    publish_gate_problems,
    snapshot_projection,
    unknown_alias_candidates,
)
from phase3_merge import load_channel_accounts

WS_TITLE = "渠道账号（20260521起在此维护）"
SPREADSHEET_ID = "1nbMO-wf-Oj7HIuYlPOtrC7F8QtsEPDE80BmXo8G6O3Y"
MONTH = "202610"
HEADER = ["渠道", "渠道账号", "渠道账号别名", f"运营人员{MONTH}"]
ROWS = [
    HEADER,
    ["Amazon", "AMZAAAUS", "AAA,美国站-A", "甲"],
    ["Amazon", "AMZBBBUS", "BBB", "乙"],
]


class _FakeWS:
    def __init__(self, rows):
        self._rows = rows
        self.title = WS_TITLE

    def get_all_values(self):
        return self._rows


class _FakeSh:
    def __init__(self, rows):
        self._rows = rows

    def worksheets(self):
        return [_FakeWS(self._rows)]

    def worksheet(self, name):
        return _FakeWS(self._rows)


class _FakeGc:
    def __init__(self, rows):
        self._rows = rows

    def open_by_key(self, _id):
        return _FakeSh(self._rows)


def _sheet(rows=None, header=None):
    src = rows or ROWS
    rows = [list(r) for r in src]  # 深拷贝：测试里改行不能污染模块级 ROWS
    return {
        "spreadsheet_title": "和运营部共享",
        "spreadsheet_id": SPREADSHEET_ID,
        "target_title": WS_TITLE,
        "target_gid": 763421711,
        "header": list(header) if header else list(rows[0]),
        "rows": rows,
    }


def _snapshot(fetched_at=None, rows=None, months=None):
    return snap_mod.attach_metadata(
        _sheet(rows),
        fetched_at=fetched_at or datetime.now(timezone.utc),
        exchange_months=months if months is not None else [MONTH],
    )


def _live(rows=None):
    acct_view, df_explode = load_channel_accounts(_FakeGc(rows or ROWS), MONTH)
    return acct_view, df_explode


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """不依赖本机 gitignored 快照；缓存清理避免跨测试串味。"""
    channel_canonical.load_account_maps.cache_clear()
    path = tmp_path / "snapshot.json"
    monkeypatch.setenv("CHANNEL_ACCOUNT_SNAPSHOT", str(path))
    yield
    channel_canonical.load_account_maps.cache_clear()


def _write_snapshot(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _gate(snapshot=None, *, acct_view=None, df_explode=None, now=None, ttl=24.0,
          expected_source=None, batch_accounts=None, batch_aliases=None, snapshot_error=None):
    if acct_view is None:
        acct_view, df_explode = _live()
    return publish_gate_problems(
        exchange_month=MONTH,
        acct_view=acct_view,
        df_explode=df_explode,
        snapshot=snapshot,
        snapshot_error=snapshot_error,
        batch_accounts=batch_accounts,
        batch_aliases=batch_aliases,
        now=now,
        ttl_hours=ttl,
        expected_source=expected_source,
    )


def _joined(result):
    return "; ".join(result.problems)


# ------------------------------------------------------------ metadata


def test_missing_metadata_rejected():
    payload = _sheet()  # 无 snapshot 段（旧快照）
    result = _gate(payload)
    assert "缺 metadata" in _joined(result)


def test_snapshot_ttl_boundary():
    now = datetime.now(timezone.utc)
    fresh = _snapshot(now - timedelta(hours=23))
    assert _gate(fresh, now=now, ttl=24.0).problems == []
    stale = _snapshot(now - timedelta(hours=25))
    assert any("已过期" in p for p in _gate(stale, now=now, ttl=24.0).problems)


def test_snapshot_future_fetched_at_rejected():
    now = datetime.now(timezone.utc)
    future = _snapshot(now + timedelta(minutes=30))
    assert any("在未来" in p for p in _gate(future, now=now).problems)


def test_snapshot_wrong_source_rejected():
    payload = _snapshot()
    result = _gate(payload, expected_source={"kind": "google_sheet", "spreadsheet_id": "OTHER"})
    assert any("spreadsheet_id" in p for p in result.problems)


def test_snapshot_content_hash_corruption_rejected():
    payload = _snapshot()
    payload["rows"][1][3] = "丙"  # 改动内容但不改 metadata
    problems = _gate(payload).problems
    assert any("content_hash" in p for p in problems)
    assert any("业务投影 hash" in p for p in problems)


def test_snapshot_missing_month_projection_rejected():
    payload = _snapshot(months=["202609"])  # 只收录上月
    assert any("运营人员202610" in p or "业务投影" in p for p in _gate(payload).problems)


def test_snapshot_rows_truncated_rejected():
    payload = _snapshot()
    payload["rows"] = payload["rows"][:2]
    assert any("行数不符" in p for p in _gate(payload).problems)


def test_require_metadata_raises_for_old_snapshot(tmp_path):
    path = channel_canonical.snapshot_path()
    _write_snapshot(path, _sheet())
    with pytest.raises(ValueError, match="不可用于发布"):
        channel_canonical.load_account_maps(require_metadata=True)


# ------------------------------------------------------------ live vs snapshot


def test_live_and_snapshot_match_no_problems():
    result = _gate(_snapshot())
    assert result.problems == []
    assert result.live_projection == result.snapshot_projection


def test_live_staff_mismatch_fails():
    rows = [r[:] for r in ROWS]
    rows[1][3] = "甲改"
    result = _gate(_snapshot(), acct_view=_live(rows)[0], df_explode=_live(rows)[1])
    assert any("运营人员" in p and "live" in p for p in result.problems)


def test_live_alias_mismatch_fails():
    rows = [r[:] for r in ROWS]
    rows[1][2] = "AAA,美国站-A2"
    acct_view, df_explode = _live(rows)
    result = _gate(_snapshot(), acct_view=acct_view, df_explode=df_explode)
    assert any("别名不一致" in p for p in result.problems)


def test_live_unreadable_blocks_publish():
    result = publish_gate_problems(
        exchange_month=MONTH, acct_view=None, df_explode=None, snapshot=_snapshot()
    )
    assert any("live 渠道主表不可读" in p for p in result.problems)


def test_live_has_account_missing_from_snapshot():
    rows = [r[:] for r in ROWS] + [["Amazon", "AMZCCCUS", "CCC", "丙"]]
    acct_view, df_explode = _live(rows)
    result = _gate(_snapshot(), acct_view=acct_view, df_explode=df_explode)
    assert any("AMZCCCUS" in p for p in result.problems)


# ------------------------------------------------------------ 维度完整性


def test_blank_staff_for_batch_account_fails():
    rows = [r[:] for r in ROWS]
    rows[1][3] = ""
    acct_view, df_explode = _live(rows)
    snap = _snapshot(rows=rows)
    result = _gate(snap, acct_view=acct_view, df_explode=df_explode, batch_accounts=["AMZAAAUS"])
    assert any("AMZAAAUS" in p and "运营人员为空" in p for p in result.problems)


def test_blank_platform_for_batch_account_fails():
    rows = [r[:] for r in ROWS]
    rows[1][0] = ""
    acct_view, df_explode = _live(rows)
    result = _gate(
        _snapshot(rows=rows), acct_view=acct_view, df_explode=df_explode, batch_accounts=["AMZAAAUS"]
    )
    assert any("渠道/平台为空" in p for p in result.problems)


def test_receivable_owner_not_applicable_for_tax():
    """Tax-only 行没有 收款归属；主数据门禁不得因缺该列报错。"""
    result = _gate(_snapshot(), batch_accounts=["AMZAAAUS", "AMZBBBUS"])
    assert not any("收款归属" in p for p in result.problems)


# ------------------------------------------------------------ 未知别名（只报告）


def test_unknown_alias_reported_as_candidate_only():
    result = _gate(_snapshot(), batch_aliases=["WFUS-Daneey"])
    assert [c["alias"] for c in result.unknown_alias_candidates] == ["WFUS-Daneey"]
    assert result.unknown_alias_candidates[0]["candidates"] == []
    assert any("未知别名" in p for p in result.problems)


def test_unknown_alias_candidate_hints():
    out = unknown_alias_candidates(
        ["美国站-A"], known_accounts={"AMZAAAUS"}, known_aliases={"美国站-A"}
    )
    assert out == []  # 已登记
    out = unknown_alias_candidates(
        ["美国站-A2"], known_accounts={"AMZAAAUS"}, known_aliases={"美国站-A"}
    )
    assert out and "美国站-A" in out[0]["candidates"]
    assert out[0]["action"] == "needs_business_owner_approval"


# ------------------------------------------------------------ 投影函数 / 缓存


def test_projection_detects_duplicate_aliases_across_accounts():
    live = [
        {"渠道": "Amazon", "渠道账号": "AMZA", "aliases": ["X"], "运营人员": "甲"},
        {"渠道": "Amazon", "渠道账号": "AMZB", "aliases": ["X"], "运营人员": "乙"},
    ]
    snap = [dict(r) for r in live]
    problems = projection_differences(live, snap)
    assert any("别名 X 指向多个渠道账号" in p for p in problems)


def test_cache_invalidated_by_snapshot_content_change(tmp_path):
    path = channel_canonical.snapshot_path()
    payload_a = _snapshot()
    payload_a["rows"][1][1] = "AMZAAAUS"
    payload_a["rows"][1][2] = "OLDALIAS"
    payload_a = snap_mod.attach_metadata(
        _sheet(payload_a["rows"]), fetched_at=datetime.now(timezone.utc), exchange_months=[MONTH]
    )
    _write_snapshot(path, payload_a)
    assert channel_canonical.canonical_account("OLDALIAS") == "AMZAAAUS"

    payload_b = [r[:] for r in payload_a["rows"]]
    payload_b[1][1] = "AMZNEWUS"
    payload_b = snap_mod.attach_metadata(
        _sheet(payload_b), fetched_at=datetime.now(timezone.utc), exchange_months=[MONTH]
    )
    _write_snapshot(path, payload_b)
    # 同一进程、不清缓存：必须立即读到新 map
    assert channel_canonical.canonical_account("OLDALIAS") == "AMZNEWUS"


def test_zero_width_alias_conflict_is_hard_error(tmp_path):
    path = channel_canonical.snapshot_path()
    rows = [
        ["渠道", "渠道账号", "渠道账号别名", f"运营人员{MONTH}"],
        ["Amazon", "AMZAAAUS", "ALIAS", "甲"],
        ["Amazon", "AMZBBBUS", "ALI​AS", "乙"],
    ]
    _write_snapshot(path, _sheet(rows))
    with pytest.raises(ValueError, match="别名冲突"):
        channel_canonical.load_account_maps()


def test_case_only_alias_conflict_warns(tmp_path, capsys):
    path = channel_canonical.snapshot_path()
    rows = [
        ["渠道", "渠道账号", "渠道账号别名", f"运营人员{MONTH}"],
        ["Amazon", "AMZAAAUS", "ALIAS", "甲"],
        ["Amazon", "amzaaaus", "alias", "甲"],
    ]
    _write_snapshot(path, _sheet(rows))
    channel_canonical.load_account_maps()
    assert "仅大小写" in capsys.readouterr().err


def test_snapshot_projection_shape():
    proj = snapshot_projection(_snapshot(), MONTH)
    assert len(proj) == 2
    assert proj[0]["渠道账号"] == "AMZAAAUS"
    assert proj[0]["aliases"] == ["AAA", "AMZAAAUS", "美国站-A"]
    live = live_projection(*_live())
    assert live == proj


def test_build_metadata_records_source_and_hashes():
    meta = snap_mod.build_metadata(_sheet(), exchange_months=[MONTH])
    assert meta["schema_version"] == snap_mod.SCHEMA_VERSION
    assert meta["source"]["spreadsheet_id"] == SPREADSHEET_ID
    assert meta["source"]["worksheet"] == WS_TITLE
    assert meta["fetched_at"]
    assert meta["content_hash"] and meta["header_hash"]
    assert MONTH in meta["business_projection_hashes"]
    # 同内容重复构造（同一 fetched_at）hash 稳定
    again = snap_mod.build_metadata(
        _sheet(), exchange_months=[MONTH],
        fetched_at=snap_mod.parse_fetched_at(meta["fetched_at"]),
    )
    assert again["content_hash"] == meta["content_hash"]
    assert again["business_projection_hashes"] == meta["business_projection_hashes"]
