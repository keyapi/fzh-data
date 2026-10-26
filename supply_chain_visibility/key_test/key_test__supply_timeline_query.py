"""Permission- and scope-limited query service for the Supply Timeline report."""
from datetime import date, datetime
import json
from pathlib import Path

import frappe


CONFIG_PATH = Path(__file__).with_name("config") / "supply_timeline_skus.json"
if not CONFIG_PATH.is_file():
    CONFIG_PATH = Path(__file__).with_name("key_test__config__supply_timeline_skus.json")
MAX_SKUS = 9
EXPECTED_WAREHOUSES = 14
MAX_LATEST_ROWS = MAX_SKUS * EXPECTED_WAREHOUSES
HISTORY_LIMIT = 2000
STAGES = ("on_hand", "shipped_in_transit", "unknown")
LATEST_FIELDS = [
    "name", "sku", "warehouse", "warehouse_id", "available", "intransit",
    "waiting_shipment", "defects", "snapshot_at", "run_id",
]
RUN_FIELDS = [
    "name", "run_id", "snapshot_date", "started_at", "finished_at", "status",
    "complete", "warehouse_count", "row_count", "source",
]
BASE_MESSAGE = (
    "当前仅覆盖 Tongtool 库存快照；PO、WO、DN 与真实采购入库未接入。"
    "接通并核验这些来源后才能计算完整可承诺供给。`intransit` 独立展示，不与 PO 在途重复相加。"
)


class TimelineScopeError(ValueError):
    """Requested item scope exceeds the approved nine-SKU sample."""


def _field(row, field, default=None):
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)


def _load_slots():
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        slots = json.load(stream).get("slots", [])
    skus = [slot.get("sku") for slot in slots]
    if len(skus) != MAX_SKUS or any(not sku for sku in skus) or len(set(skus)) != MAX_SKUS:
        raise RuntimeError("supply_timeline_skus.json must contain nine unique nonempty TT SKUs")
    return tuple(slots)


SAMPLE_SLOTS = _load_slots()
SAMPLE_SKUS = tuple(slot["sku"] for slot in SAMPLE_SLOTS)


def _requested_skus(raw):
    if raw is None or raw == "":
        return list(SAMPLE_SKUS)
    selected = ([value.strip() for value in raw.split(",") if value.strip()]
                if isinstance(raw, str) else [str(value).strip() for value in raw if str(value).strip()])
    if not selected:
        return list(SAMPLE_SKUS)
    if len(selected) > MAX_SKUS:
        raise TimelineScopeError("范围超限：一次最多查询已批准的 9 个通途 SKU。")
    if any(sku not in SAMPLE_SKUS for sku in selected):
        raise TimelineScopeError("范围超限：SKU 不在本次批准的 9 个通途样本范围内。")
    return list(dict.fromkeys(selected))


def _snapshot_date(raw):
    value = raw or "latest"
    if value == "latest":
        return value
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise TimelineScopeError("快照日期必须为 latest 或 YYYY-MM-DD。") from exc


def _is_system_manager():
    return "System Manager" in frappe.get_roles()


def _date_text(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat() if isinstance(value, date) else str(value)[:10] if value else None


def _unknown_row(sku, warehouse, warehouse_id, snapshot_date, run_id, reason,
                 coverage, evidence_qty=None, source_field="availability", snapshot_at=None,
                 run_started_at=None, run_finished_at=None, query_as_of=None):
    source_key = f"TongtoolStock:{run_id or 'unknown'}:{sku}:{warehouse or 'unknown'}:{source_field}"
    bucket = {"available": "stock_available", "intransit": "stock_intransit"}.get(source_field, "unknown")
    return {
        "sku": sku, "warehouse": warehouse, "warehouse_id": warehouse_id,
        "stage": "unknown", "snapshot_date": snapshot_date, "batch": run_id,
        "snapshot_at": snapshot_at, "run_started_at": run_started_at,
        "run_finished_at": run_finished_at, "query_as_of": query_as_of,
        "source_key": source_key, "qty": None, "evidence_qty": evidence_qty,
        "uom": None, "uom_confidence": "unknown", "date_confidence": "unknown",
        "snapshot_confidence": "evidence_only" if coverage == "historical_evidence_only" else "unknown",
        "available_date": None, "source_bucket": bucket, "ledger": bucket,
        "overlap_status": "unproven", "counted": False,
        "source_coverage": coverage, "reason": reason,
    }


def _unknown_stock_rows(row, run, reason, coverage, query_as_of):
    return [
        _unknown_row(
            row.sku, row.warehouse, row.warehouse_id, _date_text(row.snapshot_at), row.run_id,
            reason, coverage, getattr(row, field, None), field, row.snapshot_at,
            _field(run, "started_at") if run else None,
            _field(run, "finished_at") if run else None, query_as_of,
        )
        for field in ("available", "intransit")
    ]


def _uncovered_chain_row(row, run, query_as_of):
    sku, warehouse, run_id = row.sku, row.warehouse, row.run_id
    return {
        "sku": sku, "warehouse": warehouse, "warehouse_id": row.warehouse_id,
        "stage": "unknown", "snapshot_date": _date_text(row.snapshot_at), "batch": run_id,
        "snapshot_at": row.snapshot_at,
        "run_started_at": _field(run, "started_at") if run else None,
        "run_finished_at": _field(run, "finished_at") if run else None,
        "query_as_of": query_as_of,
        "source_key": f"uncovered:{run_id or 'unknown'}:{sku}:{warehouse}",
        "qty": None, "evidence_qty": None, "uom": None, "uom_confidence": "unknown",
        "date_confidence": "unknown", "snapshot_confidence": "unknown", "available_date": None,
        "source_bucket": "uncovered_chain", "ledger": "uncovered_chain",
        "overlap_status": "unproven", "counted": False, "source_coverage": "not_connected",
        "reason": "PO、WO、DN 与真实采购入库链尚未接入",
    }


def _unreported_sku_row(sku, warehouse, reason, query_as_of=None, coverage="not_reported"):
    return _unknown_row(
        sku, warehouse, None, None, None, reason, coverage, None, "no_latest_row",
        query_as_of=query_as_of,
    )


def _complete_run(run, visible_row_count):
    return bool(
        run
        and _field(run, "complete") in (1, True, "1")
        and _field(run, "status") == "Success"
        and _field(run, "warehouse_count") == EXPECTED_WAREHOUSES
        and _field(run, "row_count") == visible_row_count
    )


def _normal_latest_rows(row, run, query_as_of):
    output = []
    for stage, field in (("on_hand", "available"), ("shipped_in_transit", "intransit")):
        quantity = _field(row, field)
        if quantity is None:
            output.append(_unknown_row(
                row.sku, row.warehouse, row.warehouse_id, _date_text(row.snapshot_at),
                row.run_id, f"库存字段 {field} 缺失", "missing_quantity", None, field,
                row.snapshot_at, _field(run, "started_at"), _field(run, "finished_at"), query_as_of,
            ))
            continue
        output.append({
            "sku": row.sku, "warehouse": row.warehouse, "warehouse_id": row.warehouse_id,
            "stage": stage, "snapshot_date": _date_text(row.snapshot_at), "batch": row.run_id,
            "snapshot_at": row.snapshot_at, "run_started_at": _field(run, "started_at"),
            "run_finished_at": _field(run, "finished_at"), "query_as_of": query_as_of,
            "source_key": f"Tongtool Stock Latest:{row.run_id}:{row.sku}:{row.warehouse}:{field}",
            "qty": None, "evidence_qty": quantity, "uom": None, "uom_confidence": "unknown",
            "date_confidence": "confirmed" if stage == "on_hand" else "unknown",
            "snapshot_confidence": "run_verified",
            "available_date": _date_text(row.snapshot_at) if stage == "on_hand" else None,
            "source_bucket": "stock_available" if stage == "on_hand" else "stock_intransit",
            "ledger": "stock_available" if stage == "on_hand" else "stock_intransit",
            "overlap_status": "unproven", "counted": False,
            "source_coverage": "complete_stock_snapshot" if stage == "on_hand" else "intransit_field_only",
            "reason": ("单位未提供，数量仅作为库存快照证据。" if stage == "on_hand" else
                       "通途 intransit 字段未证明 ETA 或真实 Shipment；不与 PO/DN 重复计入。"),
        })
    return output


def _latest_rows(skus, warehouse_filter):
    if not _is_system_manager():
        return [], "当前仅 System Manager 可读取 Tongtool 快照；尚未确认通途 SKU/仓库字段具备逐行授权。"
    if not frappe.db.exists("DocType", "Tongtool Stock Latest"):
        return [], "当前站点尚未部署 Tongtool Stock Latest，快照来源不可用。"
    query_as_of = frappe.utils.now_datetime()
    filters = {"sku": ["in", skus]}
    if warehouse_filter:
        filters["warehouse"] = warehouse_filter
    rows = frappe.get_list(
        "Tongtool Stock Latest", filters=filters, fields=LATEST_FIELDS,
        limit_page_length=MAX_LATEST_ROWS + 1,
    )
    if len(rows) > MAX_LATEST_ROWS:
        return [], f"快照行数超过样本范围上限 {MAX_LATEST_ROWS}，已拒绝显示截断结果。"
    if not rows:
        reason = "无仓库筛选，无法从空源确认仓库范围" if not warehouse_filter else "所选通途 SKU/仓库在 Latest 中未上报"
        return [_unreported_sku_row(sku, warehouse_filter, reason, query_as_of) for sku in skus], "Tongtool Stock Latest 当前范围无行，已标记为未上报。"

    run_ids = list(dict.fromkeys(_field(row, "run_id") for row in rows if _field(row, "run_id")))
    runs = []
    if run_ids and frappe.db.exists("DocType", "Tongtool Stock Run"):
        runs = frappe.get_list(
            "Tongtool Stock Run", filters={"run_id": ["in", run_ids]}, fields=RUN_FIELDS,
            limit_page_length=len(run_ids),
        )
    run_by_id = {_field(run, "run_id"): run for run in runs}
    count_by_run, warehouses_by_run = {}, {}
    for run_id in run_ids:
        # get_list remains the only reader of Latest; count mismatch is unknown.
        count_rows = frappe.get_list(
            "Tongtool Stock Latest", filters={"run_id": run_id}, fields=["name", "warehouse"],
            limit_page_length=0,
        )
        count_by_run[run_id] = len(count_rows)
        warehouses_by_run[run_id] = {
            _field(item, "warehouse") for item in count_rows if _field(item, "warehouse")
        }

    today = str(frappe.utils.today())[:10]
    output, reported_pairs = [], set()
    for row in rows:
        sku, run_id = row.sku, row.run_id
        reported_pairs.add((sku, row.warehouse))
        run = run_by_id.get(run_id)
        snapshot_date = _date_text(_field(run, "snapshot_date")) if run else None
        row_date = _date_text(row.snapshot_at)
        if not row.snapshot_at or not snapshot_date:
            output.extend(_unknown_stock_rows(row, run, "快照日期缺失", "unknown_snapshot_date", query_as_of))
        elif not run or not _complete_run(run, count_by_run.get(run_id, -1)):
            output.extend(_unknown_stock_rows(row, run, "批次范围或完成状态未通过完整性核验", "incomplete_run", query_as_of))
        elif snapshot_date != row_date:
            output.extend(_unknown_stock_rows(row, run, "快照日期与运行批次不一致", "stale_snapshot", query_as_of))
        elif snapshot_date > today:
            output.extend(_unknown_stock_rows(row, run, "Latest 快照日期晚于站点当前日期", "future_snapshot", query_as_of))
        elif snapshot_date < today:
            output.extend(_unknown_stock_rows(row, run, "Latest 快照日期已过期", "stale_snapshot", query_as_of))
        else:
            output.extend(_normal_latest_rows(row, run, query_as_of))
        output.append(_uncovered_chain_row(row, run, query_as_of))

    verified_scope = bool(run_ids) and all(
        _complete_run(run_by_id.get(run_id), count_by_run.get(run_id, -1))
        and len(warehouses_by_run.get(run_id, set())) == EXPECTED_WAREHOUSES
        for run_id in run_ids
    )
    if warehouse_filter:
        expected_warehouses = {warehouse_filter}
        warehouse_scope_known = True
    else:
        expected_warehouses = set().union(*(warehouses_by_run.values())) if warehouses_by_run else set()
        warehouse_scope_known = verified_scope and bool(expected_warehouses)
        if not expected_warehouses:
            expected_warehouses = {row.warehouse for row in rows if row.warehouse}
    for sku in skus:
        for warehouse in expected_warehouses:
            if (sku, warehouse) not in reported_pairs:
                output.append(_unreported_sku_row(
                    sku, warehouse, "该 SKU×通途仓在可读 Latest 行中未上报；不代表库存为零。", query_as_of,
                ))
    if not warehouse_scope_known:
        for sku in skus:
            output.append(_unreported_sku_row(
                sku, None, "无法证明可读 Latest 包含完整仓库范围；未列出的仓库仍未知。",
                query_as_of, "warehouse_scope_unknown",
            ))
        return output, "无法证明本批完整仓库范围；未上报的 SKU×仓库已标未知，不代表为零。"
    return output, ""


def _historical_rows(snapshot_date, skus, warehouse_filter):
    if not _is_system_manager():
        return [], "历史 stock.parquet 无行权限，仅 System Manager 可查。"
    if not frappe.db.exists("DocType", "Tongtool Stock Latest"):
        return [], "当前站点尚未部署 Tongtool Stock Latest，历史快照来源不可用。"
    if not frappe.has_permission("Tongtool Stock Latest", "read"):
        return [], "历史快照需要 Tongtool Stock Latest 读取权限。"
    try:
        directory = frappe.get_single("Tongtool Settings").stock_snapshot_dir or "/home/frappe/fzh-inventory"
        parquet_path = Path(directory) / "stock.parquet"
    except Exception:
        return [], "历史快照路径未配置，来源不可用。"
    if not parquet_path.is_file():
        return [], "历史 stock.parquet 不存在，来源不可用。"
    try:
        import duckdb
    except ImportError:
        return [], "当前环境未安装 DuckDB，历史快照来源不可用。"

    query_as_of = frappe.utils.now_datetime()
    sku_marks = ", ".join("?" for _ in skus)
    where = ["CAST(snapshot_date AS DATE) = CAST(? AS DATE)", f"sku IN ({sku_marks})"]
    params = [str(parquet_path), snapshot_date, *skus]
    if warehouse_filter:
        where.append("warehouse_name = ?")
        params.append(warehouse_filter)
    sql = f"""SELECT snapshot_date, snapshot_at, warehouse_name, warehouse_id, sku, available,
                     intransit, source, run_id
              FROM read_parquet(?) WHERE {' AND '.join(where)} LIMIT ?"""
    params.append(HISTORY_LIMIT + 1)
    connection = duckdb.connect(database=":memory:", read_only=False)
    try:
        records = connection.execute(sql, params).fetchall()
    except Exception:
        return [], "历史快照读取失败，未返回部分结果。"
    finally:
        connection.close()
    if len(records) > HISTORY_LIMIT:
        return [], f"历史快照超过 {HISTORY_LIMIT} 行上限，已拒绝显示截断结果。"

    output, reported_pairs = [], set()
    for snap_date, snapshot_at, warehouse, warehouse_id, sku, available, intransit, source, run_id in records:
        reported_pairs.add((sku, warehouse))
        for evidence, source_field in ((available, "available"), (intransit, "intransit")):
            output.append(_unknown_row(
                sku, warehouse, warehouse_id, _date_text(snap_date), run_id,
                f"历史 {source_field} 数量仅作证据，不能代表当前可用供给。",
                "historical_evidence_only", evidence, source_field, snapshot_at,
                query_as_of=query_as_of,
            ))
        output.append({
            "sku": sku, "warehouse": warehouse, "warehouse_id": warehouse_id,
            "stage": "unknown", "snapshot_date": _date_text(snap_date), "batch": run_id,
            "snapshot_at": snapshot_at, "run_started_at": None, "run_finished_at": None,
            "query_as_of": query_as_of,
            "source_key": f"uncovered:{run_id or 'unknown'}:{sku}:{warehouse}",
            "qty": None, "evidence_qty": None, "uom": None, "uom_confidence": "unknown",
            "date_confidence": "unknown", "snapshot_confidence": "unknown", "available_date": None,
            "source_bucket": "uncovered_chain", "ledger": "uncovered_chain",
            "overlap_status": "unproven", "counted": False, "source_coverage": "not_connected",
            "reason": "PO、WO、DN 与真实采购入库链尚未接入",
        })
    expected_warehouses = {warehouse_filter} if warehouse_filter else {record[2] for record in records if record[2]}
    for sku in skus:
        for warehouse in expected_warehouses:
            if (sku, warehouse) not in reported_pairs:
                output.append(_unreported_sku_row(
                    sku, warehouse, "该 SKU×通途仓在所选历史日期未上报；不代表库存为零。", query_as_of,
                ))
        if not expected_warehouses:
            output.append(_unreported_sku_row(
                sku, None, "所选历史日期无可读仓库行，仓库范围未知。", query_as_of,
                "warehouse_scope_unknown",
            ))
    return output, ""


def get_report_data(filters=None):
    filters = filters or {}
    skus = _requested_skus(filters.get("sku"))
    snapshot_date = _snapshot_date(filters.get("snapshot_date"))
    stage = filters.get("stage") or ""
    if stage and stage not in STAGES:
        raise TimelineScopeError("阶段必须为 on_hand、shipped_in_transit 或 unknown。")
    warehouse_filter = (filters.get("warehouse_name") or "").strip() or None
    if snapshot_date == "latest":
        rows, detail = _latest_rows(skus, warehouse_filter)
    else:
        rows, detail = _historical_rows(snapshot_date, skus, warehouse_filter)
    if stage:
        rows = [row for row in rows if row["stage"] == stage]
    return rows, " ".join(part for part in (BASE_MESSAGE, detail) if part)
