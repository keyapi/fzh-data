# -*- coding: utf-8 -*-
"""离线 fixture 测试：不联网、不写生产。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from self_fulfilled_demand import config
from self_fulfilled_demand.consumer import build_demand, load_gs_orders, reconcile_overlap
from self_fulfilled_demand.en_reader import EnBudgetExhausted, EnReadOnlyClient
from self_fulfilled_demand.ingest import _head_window
from self_fulfilled_demand.normalize import normalize_order, split_order_id
from self_fulfilled_demand.store import IncompleteSnapshotError, ParquetStore

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def ingest_fixture(
    store: ParquetStore,
    name: str,
    run_id: str,
    started_at: str,
    ingest_scope: str = "sale_window",
) -> dict:
    data = load_fixture(name)
    run = {
        "run_id": run_id,
        "started_at": started_at,
        "ingest_scope": ingest_scope,
        "coverage_status": "complete",
    }
    records = [
        normalize_order(o["head"], o["items"], o["packages"], run) for o in data["orders"]
    ]
    return store.ingest(records, run)


@pytest.fixture()
def store(tmp_path: Path) -> ParquetStore:
    return ParquetStore(tmp_path / "en-demand-v1")


# ---------------------------------------------------------------------------
# 存储：幂等、行身份、拆单、更新/取消
# ---------------------------------------------------------------------------


def test_rerun_is_idempotent(store: ParquetStore):
    first = ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    orders_1 = store.load_orders()
    lines_1 = store.load_lines()
    events_1 = store.load_events()

    second = ingest_fixture(store, "orders_batch1.json", "run-2", "2026-10-27T11:00:00+08:00")
    orders_2 = store.load_orders()
    lines_2 = store.load_lines()
    events_2 = store.load_events()

    assert first["new_orders"] == len(orders_1) == 11
    assert second["new_orders"] == 0
    assert second["updated_orders"] == 0
    assert second["unchanged_orders"] == 11
    assert len(orders_2) == len(orders_1) == 11
    assert len(lines_2) == len(lines_1) == 13  # EN-002 两行 + EN-010 两行
    assert len(events_2) == len(events_1) == 11  # 只有 created，重跑不新增
    assert orders_2["en_doc_name"].is_unique
    assert lines_2["line_key"].is_unique


def test_same_order_same_sku_lines_are_not_collapsed(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    lines = store.load_lines()
    dup = lines[lines["en_doc_name"] == "EN-002"]
    assert len(dup) == 2
    assert dup["line_key"].nunique() == 2
    assert set(dup["source_line_id"].dropna())
    assert sorted(dup["idx"].tolist()) == [1, 2]


def test_split_orders_keep_base_but_not_merge(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    orders = store.load_orders().set_index("en_doc_name")
    assert {"EN-003_1", "EN-003_2"} <= set(orders.index)
    assert orders.loc["EN-003_1", "base_order_id"] == "EN-003"
    assert orders.loc["EN-003_2", "base_order_id"] == "EN-003"
    assert int(orders.loc["EN-003_1", "split_index"]) == 1
    assert int(orders.loc["EN-003_2", "split_index"]) == 2
    assert split_order_id("NO-SPLIT", "NO-SPLIT")["split_basis"] == "none"


def test_update_and_cancel_semantics(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    ingest_fixture(store, "orders_batch2.json", "run-2", "2026-10-28T10:00:00+08:00")

    orders = store.load_orders().set_index("en_doc_name")
    assert orders.loc["EN-001", "order_status"] == "已发货"
    assert orders.loc["EN-001", "despatch_complete_time"] == "2026-10-07 09:00:00"
    assert orders.loc["EN-006", "lifecycle_state"] == "cancelled_invalid"
    assert orders.loc["EN-006", "invalid"] == 1
    assert "EN-011" in orders.index

    events = store.load_events()
    en001 = events[events["en_doc_name"] == "EN-001"]
    assert len(en001) == 2
    assert "status_changed" in en001.iloc[-1]["event_types"]
    assert "despatch_changed" in en001.iloc[-1]["event_types"]
    en002 = events[events["en_doc_name"] == "EN-002"]
    assert len(en002) == 2
    assert "lines_changed" in en002.iloc[-1]["event_types"]
    assert len(events[events["en_doc_name"] == "EN-006"]) == 1


def test_scope_classification_and_conflict(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    orders = store.load_orders().set_index("en_doc_name")
    assert orders.loc["EN-001", "fulfillment_scope"] == config.SCOPE_SELF
    assert orders.loc["EN-004", "fulfillment_scope"] == config.SCOPE_FBA
    assert orders.loc["EN-005", "fulfillment_scope"] == config.SCOPE_THIRD_PARTY
    assert orders.loc["EN-007", "fulfillment_scope"] == config.SCOPE_UNKNOWN
    assert orders.loc["EN-008", "fulfillment_scope"] == config.SCOPE_UNKNOWN
    assert orders.loc["EN-008", "scope_conflict"] == "order_type_self_but_warehouse_fba"
    assert "order_type=自发货" in orders.loc["EN-001", "scope_evidence"]


def test_missing_quantity_is_preserved_not_zero(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    lines = store.load_lines().set_index("line_key")
    en009 = lines[lines["en_doc_name"] == "EN-009"].iloc[0]
    assert pd.isna(en009["quantity"])
    assert bool(en009["quantity_missing"]) is True
    assert en009["demand_kind"] == config.DSHIP_UNKNOWN


# ---------------------------------------------------------------------------
# 消费：履约类型 × 需求有效性分离
# ---------------------------------------------------------------------------


def test_demand_series_and_quarantine(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    frames = build_demand(store.root, FIXTURES / "gs_orders_small.csv", "2026-09-01", "2026-10-31")
    demand = frames["demand"]
    quarantine = frames["quarantine"]
    deferred = frames["deferred"]

    assert {"EN-001", "EN-002", "EN-003_1", "EN-003_2"} <= set(demand["order_key"])
    assert "EN-012" in set(demand["order_key"])  # GS-only 保留

    # FBA 单独一张表，不进 quarantine 也不进 demand
    assert {"EN-004", "EN-013"} <= set(frames["fba"]["order_key"])
    assert "EN-004" not in set(quarantine["order_key"])

    # 取消 / 数量缺失 / 嵌入组件 → quarantine（有效性维度）
    for doc in ("EN-006", "EN-009", "EN-010"):
        assert doc in set(quarantine["order_key"])
    roles = quarantine.set_index("order_key")["row_role"].to_dict()
    assert roles["EN-006"] == "cancelled"
    assert roles["EN-009"] == "qty_missing"
    assert roles["EN-010"] == "embedded_component"

    # 代发 / unknown 是有效需求，只是不在默认主建议口径 → deferred，不是 quarantine
    assert {"EN-005", "EN-007", "EN-008", "EN-014"} <= set(deferred["order_key"])
    reasons = deferred.set_index(["order_key", "source"])["scope_reason"].to_dict()
    assert reasons[("EN-005", "en_incremental")] == "third_party_outside_default_scope"
    assert reasons[("EN-007", "en_incremental")] == "scope_unknown_responsibility_pending"
    assert "EN-005" not in set(quarantine["order_key"])
    assert set(frames["demand_non_fba"]["in_main_series"].unique()) == {True, False}

    # 皮壳行按 cover 计入，嵌入组件不计
    assert "EN-010" in set(demand["order_key"])
    assert "TT-FOAM-1" not in set(demand["sku_key"])
    en010 = frames["demand_by_day_sku"]
    assert set(en010[en010["sku_key"] == "TT-SKU-K"]["demand_kind"]) == {config.DSHIP_COVER}
    assert en010[en010["sku_key"] == "TT-SKU-K"]["quantity"].sum() == 1
    # UOM 证据未知但保留，不猜
    assert set(en010["uom_status"]) == {"unknown"}
    assert en010["uom"].isna().all()


def test_third_party_can_be_included_on_request(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    default = build_demand(store.root, FIXTURES / "gs_orders_small.csv", "2026-10-01", "2026-10-31")
    assert "EN-005" not in set(default["demand"]["order_key"])
    assert "EN-005" in set(default["deferred"]["order_key"])

    widened = build_demand(
        store.root,
        FIXTURES / "gs_orders_small.csv",
        "2026-10-01",
        "2026-10-31",
        scopes=(config.SCOPE_SELF, config.SCOPE_THIRD_PARTY),
    )
    assert "EN-005" in set(widened["demand"]["order_key"])
    reasons = widened["demand_non_fba"].set_index("order_key")["scope_reason"].to_dict()
    assert reasons["EN-005"] == "included_third_party"
    # unknown 仍然待定，不被放宽口径吞掉
    assert "EN-007" in set(widened["deferred"]["order_key"])


def test_warehouse_aggregation_and_uom_gap(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    frames = build_demand(store.root, FIXTURES / "gs_orders_small.csv", "2026-10-01", "2026-10-31")
    wh = frames["demand_by_day_sku_warehouse"]
    assert {"warehouse_name", "uom", "uom_status", "sku_key", "demand_kind"} <= set(wh.columns)
    assert wh["warehouse_name"].notna().all()
    assert wh["uom"].isna().all()
    assert wh["quantity"].sum() == frames["demand"]["quantity"].sum()


# ---------------------------------------------------------------------------
# 消费：GS 发货口径 + EN 补洞/覆盖
# ---------------------------------------------------------------------------


def test_gs_overlap_is_line_level_and_keeps_rows(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    frames = build_demand(store.root, FIXTURES / "gs_orders_small.csv", "2026-09-01", "2026-10-31")
    overlap = frames["overlap"]
    states = {(r.order_key, r.source): r.overlap_state for r in overlap.itertuples()}
    assert states[("EN-003_1", "gs_legacy")] == "en_match"
    assert states[("EN-003_2", "gs_legacy")] == "en_match"
    assert states[("EN-012", "gs_legacy")] == "gs_only_en_gap"
    # EN-001：同订单同 SKU 同量（1），但 GS sale=9/29、EN sale=10/5 跨切点 →
    # 必须按业务行身份只算一次，GS 行被替代但保留在 overlap 审计
    assert states[("EN-001", "gs_legacy")] == "superseded_cross_cutover"
    en001 = frames["demand"][frames["demand"]["order_key"] == "EN-001"]
    assert en001["quantity"].sum() == 1
    assert en001["source"].iloc[0] == "en_incremental"
    summary = frames["summary"].iloc[0]
    assert summary["en_match"] == 2
    assert summary["gs_only_en_gap"] == 3
    assert summary["superseded_cross_cutover"] == 1
    assert summary["superseded_qty_change"] == 0
    assert frames["demand"]["quantity"].sum() == 9  # EN-001(1)+EN-002(2)+EN-003_1/2(2)+EN-010(1)+GS EN-012(3)


def test_cross_cutover_multiline_is_not_double_counted(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    frames = build_demand(store.root, FIXTURES / "gs_orders_multiline.csv", "2026-09-01", "2026-10-31")
    overlap = frames["overlap"]
    gs_b = overlap[(overlap["order_key"] == "EN-002") & (overlap["source"] == "gs_legacy")]
    assert len(gs_b) == 2  # 两个包裹行都在，未被整单覆盖丢失
    assert set(gs_b["overlap_state"]) == {"superseded_cross_cutover"}
    en_b = frames["demand"][frames["demand"]["order_key"] == "EN-002"]
    assert len(en_b) == 2  # EN 的两行同 SKU 也保留
    assert en_b["quantity"].sum() == 2  # 不是 1+1(GS)+1+1(EN)=4
    summary = frames["summary"].iloc[0]
    assert summary["superseded_cross_cutover"] == 2


def test_legacy_cancel_qty_override_and_late_legacy(store: ParquetStore):
    ingest_fixture(
        store,
        "orders_edge_cases.json",
        "run-edge",
        "2026-10-27T10:00:00+08:00",
        ingest_scope="modified_window",
    )
    frames = build_demand(store.root, FIXTURES / "gs_orders_edge_cases.csv", "2026-09-01", "2026-10-31")
    demand = frames["demand"]
    overlap = frames["overlap"]
    states = {(r.order_key, r.source): r for r in overlap.itertuples()}

    # 9 月下单、10 月发货：GS 没有 → EN 补进历史段
    assert "EN-020" in set(demand["order_key"])
    row = states[("EN-020", "en_late_legacy")]
    assert row.overlap_state == "en_only_gs_gap"

    # 旧单取消：GS 旧 qty 被抑制，需求里没有
    assert "EN-021" not in set(demand["order_key"])
    cancel_row = states[("EN-021", "gs_legacy")]
    assert cancel_row.overlap_state == "superseded_cancelled"
    assert float(cancel_row.gs_quantity) == 1.0
    assert "EN-021" in set(frames["quarantine"]["order_key"])
    assert frames["quarantine"].set_index("order_key").loc["EN-021", "row_role"] == "cancelled"

    # 旧单数量修改：用 EN 的 3，不用 GS 的 1
    qty_row = states[("EN-022", "gs_legacy")]
    assert qty_row.overlap_state == "superseded_qty_change"
    assert float(qty_row.gs_quantity) == 1.0
    assert float(qty_row.en_quantity) == 3.0
    assert demand[demand["order_key"] == "EN-022"]["quantity"].sum() == 3

    summary = frames["summary"].iloc[0]
    assert summary["en_late_legacy_rows"] == 1
    assert summary["en_override_rows"] == 2
    assert summary["superseded_cancelled"] >= 1
    assert summary["superseded_qty_change"] >= 1


def test_date_unknown_rows_are_kept(store: ParquetStore):
    ingest_fixture(
        store,
        "orders_edge_cases.json",
        "run-edge",
        "2026-10-27T10:00:00+08:00",
        ingest_scope="modified_window",
    )
    frames = build_demand(store.root, FIXTURES / "gs_orders_edge_cases.csv", "2026-09-01", "2026-10-31")
    unknown = frames["date_unknown"]
    assert {"EN-023", "EN-024"} <= set(unknown["order_key"])
    assert set(unknown["scope_reason"]) == {"sale_date_missing"}
    assert "EN-023" not in set(frames["demand"]["order_key"])
    summary = frames["summary"].iloc[0]
    assert summary["date_unknown_rows"] == 2
    assert summary["date_unknown_qty"] == 6.0  # 2 + 4


def test_empty_history_window_does_not_raise(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    frames = build_demand(store.root, FIXTURES / "gs_orders_small.csv", "2026-10-15", "2026-10-31")
    assert len(frames["demand"]) == 0  # 窗口内没有 10/15 之后的销售
    assert len(frames["overlap"]) == 0
    assert frames["summary"].iloc[0]["gs_only_en_gap"] == 0


def test_reconcile_overlap_sample(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    result = reconcile_overlap(store, FIXTURES / "gs_orders_small.csv", "2026-09-20", "2026-10-01")
    assert result["status"] == "ok"
    assert result["matched_lines"] == 2
    assert result["gs_only_lines"] == 4
    assert "sample" in result["note"]


# ---------------------------------------------------------------------------
# 分页预算与同时间戳完整性
# ---------------------------------------------------------------------------


class FakeReader(EnReadOnlyClient):
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.calls = 0
        self.request_count = 0

    def get_list(self, doctype, fields, filters=None, order_by=None, limit_start=0, limit_page_length=0):
        self.calls += 1
        cursor = None
        until = None
        for f in filters or []:
            if f[2] == ">=":
                cursor = f[3]
            elif f[2] == "<=":
                until = f[3]
        rows = [
            r
            for r in self.rows
            if (cursor is None or r["modified"] >= cursor) and (until is None or r["modified"] <= until)
        ]
        rows = sorted(rows, key=lambda r: (r["modified"], r["name"]))
        start = limit_start or 0
        end = start + (limit_page_length or len(rows))
        return rows[start:end]


def _fake_rows(n: int, same_ts: bool = False) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "name": f"R{i}",
                "modified": "2026-10-01 00:00:00" if same_ts else f"2026-10-01 00:00:{i:02d}",
                "sale_time": "2026-10-01 00:00:00",
            }
        )
    return rows


def test_pagination_budget_raises_explicitly():
    reader = FakeReader(_fake_rows(8))
    got: list[str] = []
    with pytest.raises(EnBudgetExhausted):
        for page in reader.iter_order_heads(
            cursor_field="modified",
            cursor_start="2026-10-01 00:00:00",
            until="2026-10-02 00:00:00",
            page_size=3,
            max_orders=100,
            max_pages=2,
        ):
            got.extend(r["name"] for r in page)
    assert len(got) == 6  # 不静默：预算耗尽必须抛错，调用方标 partial
    assert len(set(got)) == 6


def test_same_timestamp_rows_are_all_fetched_once():
    reader = FakeReader(_fake_rows(7, same_ts=True))
    got: list[str] = []
    for page in reader.iter_order_heads(
        cursor_field="modified",
        cursor_start="2026-10-01 00:00:00",
        until="2026-10-02 00:00:00",
        page_size=3,
        max_orders=100,
        max_pages=20,
    ):
        got.extend(r["name"] for r in page)
    assert sorted(got) == [f"R{i}" for i in range(1, 8)]
    assert len(got) == len(set(got)) == 7


def test_head_window_marks_budget_exhaustion_partial():
    reader = FakeReader(_fake_rows(8))
    heads, stats = _head_window(
        reader,
        cursor_field="modified",
        start="2026-10-01 00:00:00",
        until="2026-10-02 00:00:00",
        extra_filters=None,
        page_size=3,
        max_orders=100,
        max_pages=2,
    )
    assert len(heads) == 6
    assert stats["truncated"] is True
    assert stats["capped"] is True
    assert stats["errors"]


# ---------------------------------------------------------------------------
# 快照一致性：未提交/失败批次不能冒充成功
# ---------------------------------------------------------------------------


def test_incomplete_snapshot_is_rejected(store: ParquetStore):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    current = store.read_current()
    src = store.snapshots_dir / current["commit_id"]
    broken = store.snapshots_dir / "broken"
    broken.mkdir()
    (broken / "en_orders.parquet").write_bytes((src / "en_orders.parquet").read_bytes())
    (broken / "commit.json").write_text("{}", encoding="utf-8")
    store.current_path.write_text(
        json.dumps({"commit_id": "broken", "status": "success"}), encoding="utf-8"
    )
    with pytest.raises(IncompleteSnapshotError):
        store.load_orders()


def test_write_failure_keeps_previous_snapshot(store: ParquetStore, monkeypatch):
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    before = store.load_orders().set_index("en_doc_name")
    commit_before = store.read_current()["commit_id"]

    store.begin("run-broken")
    original_write = store._write

    def failing_write(key, df, columns):
        if key == "lines":
            raise OSError("simulated lines write failure")
        return original_write(key, df, columns)

    monkeypatch.setattr(store, "_write", failing_write)
    with pytest.raises(OSError):
        ingest_fixture(
            store,
            "orders_batch2.json",
            "run-broken",
            "2026-10-28T10:00:00+08:00",
        )
    store.abort("simulated failure")
    monkeypatch.undo()

    assert store.read_current()["commit_id"] == commit_before
    after = store.load_orders().set_index("en_doc_name")
    # 头仍是旧快照（EN-001 等待配货），不会出现「头新行旧」的半截状态
    assert after.loc["EN-001", "order_status"] == "等待配货"
    lines = store.load_lines()
    assert lines[lines["en_doc_name"] == "EN-001"]["quantity"].sum() == 1
    assert len(lines) == 13


def test_manifest_and_watermarks(tmp_path: Path):
    store = ParquetStore(tmp_path / "en-demand-v1")
    ingest_fixture(store, "orders_batch1.json", "run-1", "2026-10-27T10:00:00+08:00")
    report = {
        "run_id": "run-1",
        "status": "partial",
        "watermarks": {"modified_max": None, "sale_time_max": "2026-10-26 23:00:00"},
        "source_coverage": {"en": {"partial": True}},
        "store": {"totals_after": {"orders": 11, "lines": 13, "packages": 1, "events": 11}},
        "caveats": ["fixture"],
    }
    store.write_manifest(report)
    manifest = store.read_manifest()
    assert manifest["schema_version"] == "en-demand-v1"
    assert manifest["counts"]["orders"] == 11
    assert manifest["partial"] is True
    assert manifest["source_coverage"]["en"]["partial"] is True
    assert manifest["files"]["en_orders.parquet"]["sha256"]
    assert manifest["commit_status"] == "success"


def test_gs_missing_required_columns_raises(tmp_path: Path):
    bad = tmp_path / "bad_gs.csv"
    pd.DataFrame({"order_id": ["X"], "sku_tongtool": ["S"]}).to_csv(bad, index=False)
    with pytest.raises(ValueError, match="缺少必需列"):
        load_gs_orders(bad)
