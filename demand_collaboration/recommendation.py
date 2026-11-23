"""Immutable, read-only USNJ replenishment recommendation snapshot.

The pilot workbook is a *recommendation*, not a demand baseline: it combines a
forecast with C stock and E supply.  This module turns one explicit CSV into a
reconciled snapshot that the local workbench can display.  It never edits D5
demand, D6 netting, C inventory or E supply, never writes to EN and never
creates a purchase instruction.

Every source row is accounted for: ``input = accepted + rejected + skipped``.
Unknown numeric cells are preserved as ``None`` and are never coerced to zero.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from datetime import date, timedelta
from pathlib import Path

from .core import DomainError, day, digest, fail, text

SCHEMA = "usnj-recommendation/v1"
UNKNOWN_POLICY = "unknown_is_null_never_zero"
READ_ONLY = True
SERVICE_CERTIFIED = False
REPLENISHMENT_ELIGIBLE = False

# Canonical field -> accepted source headers (compared after normalisation).
ALIASES = {
    "sku": ("sku", "商品sku", "商品编码", "产品编码", "产品id", "product_id", "物料编码",
            "通途sku", "建议sku", "货号", "sku编码", "sku编号", "商品编号", "产品编号",
            "物料号", "item_code", "item", "编码"),
    "customer": ("客户", "客户名称", "customer", "客户简称", "店铺", "账号", "客户名",
                 "客户编码", "buyer", "owner", "current_owner"),
    "warehouse": ("仓", "仓库", "warehouse", "池", "pool", "仓池", "发货仓", "仓库名称",
                  "warehouse_name"),
    "market": ("市场", "market", "分公司", "branch"),
    "physical_form": ("形态", "physical_form", "商品形态", "产品形态", "货型", "form",
                      "物料形态", "产品类型"),
    "uom": ("uom", "单位", "canonical_uom", "计量单位", "销售单位", "基本单位",
            "单位名称", "unit"),
    "period_start": ("期间开始", "开始日期", "起始日期", "period_start", "start", "起日",
                     "start_date"),
    "period_end": ("期间结束", "结束日期", "截止日期", "period_end", "end", "止日",
                   "end_date"),
    "period": ("期间", "period", "窗口", "预测期间", "覆盖期间", "建议期间", "计划期间",
               "起止日期", "日期范围"),
    "week": ("周", "week", "周起始", "week_start"),
    "action": ("建议动作", "动作", "action", "建议", "补货动作", "补货建议", "建议类型",
               "操作", "recommendation", "recommended_action"),
    "qty": ("建议数量", "数量", "建议量", "qty", "quantity", "建议采购量", "补货量",
            "建议补货量", "建议订货量", "补货数量", "订货量", "采购量", "suggested_qty",
            "recommended_qty", "建议量_可编辑"),
    "expedite_qty": ("催已有量", "催货量", "expedite_qty"),
    "new_order_qty": ("新补数量", "新补", "new_order_qty"),
    "coverage": ("覆盖", "覆盖天数", "覆盖率", "coverage", "cover", "可覆盖天数",
                 "覆盖月数", "可售天数", "days_of_supply", "dos"),
    "reason": ("动作原因", "原因", "reason", "说明", "依据", "建议原因", "补货原因",
               "备注说明", "理由_可编辑"),
    "confidence": ("置信度", "confidence", "信心", "把握", "可信度", "confidence_level"),
    "c_qty": ("c", "c可用量", "c可发供给", "c库存", "现货", "可用库存", "inventory",
              "available", "inventory_qty", "c库存量", "当前库存", "现有库存", "on_hand",
              "stock", "c_stock"),
    "e_qty": ("e", "e供给", "已有供给", "在途", "supply", "在途合计", "e_qty", "e在途",
              "在途量", "在途库存", "supply_qty", "open_supply", "e_supply", "到时供给"),
    "forecast": ("预测", "预测值", "forecast", "需求预测", "point_forecast", "需求量",
                 "预测需求", "forecast_qty"),
    "q50": ("q50", "p50", "50分位", "q_50", "p_50"),
    "q90": ("q90", "p90", "90分位", "q_90", "p_90", "q90需求"),
    "q95": ("q95", "p95", "95分位", "q_95", "p_95", "q95需求"),
    "model": ("模型", "model", "预测模型", "算法", "模型名称", "forecast_model", "采用模型"),
    "special": ("特殊品", "special", "特殊", "特殊商品", "是否特殊品", "特殊标记", "特殊产品"),
    "needs_decision": ("需拍板", "需决策", "needs_decision", "待拍板", "人工决策",
                       "是否需拍板", "待决策", "needs_review", "标记"),
    "low_confidence": ("低置信", "低置信度", "low_confidence", "是否低置信"),
    "as_of": ("数据时点", "时点", "as_of", "快照日", "snapshot_date", "数据日期",
              "快照日期", "数据截止日"),
    "source_note": ("来源", "source", "备注", "note"),
}
CANONICAL = tuple(ALIASES)
REQUIRED_HEADERS = ("sku", "uom", "action")

UNKNOWN_TOKENS = {"", "-", "—", "－", "n/a", "na", "none", "null", "nan", "未知",
                  "不详", "待定", "无", "未提供", "未接入"}
TRUE_TOKENS = {"1", "true", "yes", "y", "是", "需", "需要", "要", "✓", "√", "需拍板"}
FALSE_TOKENS = {"0", "false", "no", "n", "否", "不需", "不需要", "不用"}
LOW_TOKENS = {"低", "low", "l", "弱"}
MEDIUM_TOKENS = {"中", "medium", "m", "一般"}
HIGH_TOKENS = {"高", "high", "h", "强"}
KNOWN_ACTIONS = {"补", "新补", "催已有", "不补", "观察", "需拍板", "待定", "无建议"}
NON_USNJ_MARKETS = ("ustx", "美中", "pl", "波兰", "美西", "uswest")


def _header(value):
    return re.sub(r"[\s_\-./]+", "", str(value or "")).strip().lower()


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    if value == "" or (isinstance(value, str) and value.lower() in UNKNOWN_TOKENS):
        return None
    return value


def _text_or_none(value):
    value = _clean(value)
    return None if value is None else str(value).strip()


def _number_or_none(value, field, source_row):
    """Return None for an explicitly unknown cell; reject malformed text."""
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, bool):
        fail("invalid_number", f"{field}必须是数值（源行{source_row}）")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            fail("invalid_number", f"{field}必须是有限数值（源行{source_row}）")
        return value
    raw = str(value).replace(",", "").replace("，", "").strip()
    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", raw)
    if not match:
        fail("invalid_number", f"{field}不是可识别数值：{value}（源行{source_row}）")
    parsed = float(match.group(0))
    if not math.isfinite(parsed):
        fail("invalid_number", f"{field}必须是有限数值（源行{source_row}）")
    return parsed


def _bool_or_none(value):
    value = _clean(value)
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if any(token in str(value) for token in ("待确认", "错", "多", "漏")):
        return True
    if lowered in TRUE_TOKENS:
        return True
    if lowered in FALSE_TOKENS:
        return False
    return None


def _dates(value):
    found = []
    for year, month, day_text in re.findall(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", str(value or "")):
        try:
            found.append(date(int(year), int(month), int(day_text)))
        except ValueError:
            continue
    return found


def _period(raw, source_row):
    start_text, end_text = _clean(raw.get("period_start")), _clean(raw.get("period_end"))
    if start_text is not None or end_text is not None:
        starts, ends = _dates(start_text), _dates(end_text)
        if not starts:
            fail("invalid_period", f"期间开始不是有效日期（源行{source_row}）")
        start = starts[0]
        end = ends[0] if ends else start
        basis = "explicit_start_end" if ends else "single_day_period"
    else:
        values = _dates(raw.get("period"))
        horizon = re.search(r"(\d+)\s*天", str(raw.get("period") or ""))
        if len(values) >= 2:
            start, end, basis = values[0], values[-1], "period_range"
        elif len(values) == 1 and horizon:
            start = values[0]
            end = start + timedelta(days=int(horizon.group(1)) - 1)
            basis = "period_start_horizon"
        elif len(values) == 1:
            start = end = values[0]
            basis = "single_day_period"
        else:
            week = _dates(raw.get("week"))
            if not week:
                fail("invalid_period", f"期间缺失或无法解析（源行{source_row}）")
            start, end, basis = week[0], week[0] + timedelta(days=6), "week"
    if end < start:
        fail("invalid_period", f"期间结束早于开始（源行{source_row}）")
    return start, end, basis


def _confidence(value):
    raw = _text_or_none(value)
    if raw is None:
        return None, None
    lowered = raw.lower()
    if lowered in LOW_TOKENS or "低" in raw or "low" in lowered:
        return "low", None
    if lowered in MEDIUM_TOKENS or "中" in raw or "medium" in lowered:
        return "medium", None
    if lowered in HIGH_TOKENS or "高" in raw or "high" in lowered:
        return "high", None
    try:
        number = float(raw.replace("%", "").replace(",", "").strip())
    except ValueError:
        return None, raw
    if "%" in raw or number > 1:
        number = number / 100
    if not math.isfinite(number):
        return None, raw
    level = "low" if number < 0.6 else "medium" if number < 0.8 else "high"
    return level, number


def _coverage(value, source_row):
    raw = _text_or_none(value)
    if raw is None:
        return None, None, None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", raw.replace(",", "").replace("，", ""))
    if not match:
        return None, raw, None
    unit = "percent" if "%" in raw else "days" if "天" in raw or "日" in raw else None
    return float(match.group(0)), raw, unit


def _market(value):
    raw = _text_or_none(value)
    if raw is None:
        return None, False
    lowered = raw.lower()
    if "usnj" in lowered or "美东" in raw:
        return "USNJ", False
    if any(token in lowered for token in NON_USNJ_MARKETS) or "美中" in raw or "波兰" in raw:
        return raw, True
    return raw, False


def _canonical_rows(path, mapping_overrides=None, default_period=None):
    source = Path(path)
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            content = source_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        fail("invalid_encoding", "无法以UTF-8或GB18030读取源CSV")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    all_rows = list(csv.reader(content.splitlines(), dialect=dialect))
    if not all_rows:
        fail("missing_columns", "源CSV没有表头")
    while len(all_rows) > 1 and not any(_clean(cell) is not None for cell in all_rows[-1]):
        all_rows.pop()
    headers = all_rows[0]
    alias_lookup = {_header(name): field for field, names in ALIASES.items() for name in names}
    if mapping_overrides:
        for field, header in mapping_overrides.items():
            if field not in CANONICAL:
                fail("invalid_mapping", f"不支持的映射字段：{field}")
            alias_lookup[_header(header)] = field
    columns, duplicate = {}, set()
    for index, original in enumerate(headers):
        field = alias_lookup.get(_header(original))
        if not field:
            continue
        if field in columns:
            duplicate.add(field)
        columns[field] = index
    if duplicate:
        fail("duplicate_columns", "多个源列映射到同一字段：" + ",".join(sorted(duplicate)))
    missing = [field for field in REQUIRED_HEADERS if field not in columns]
    has_period = any(field in columns for field in ("period", "period_start", "week"))
    if not has_period and default_period is None:
        missing.append("period")
    if missing:
        fail("missing_columns", "缺少必要列：" + ",".join(sorted(missing)))
    rows, report = [], {"schema": SCHEMA, "source_name": source.name,
                        "source_sha256": source_hash, "input_count": 0,
                        "accepted_count": 0, "skipped_count": 0,
                        "rejected_count": 0, "skipped": [], "rejected": [],
                        "columns": {field: headers[index] for field, index in columns.items()},
                        "unmapped_columns": [name for index, name in enumerate(headers)
                                             if index not in columns.values()],
                        "unknown_policy": UNKNOWN_POLICY,
                        "assumptions": ["recommendation_not_demand_baseline",
                                        "unknown_never_zero_filled",
                                        "read_only_no_order_authority"]}
    candidates = []
    for source_row, values in enumerate(all_rows[1:], start=2):
        raw = {field: (values[index] if index < len(values) else None)
               for field, index in columns.items()}
        if not any(_clean(value) is not None for value in raw.values()):
            # Excel exports often insert a blank line after every data row.
            # Blank physical lines are formatting, not business input rows.
            continue
        extra = {headers[index]: values[index] for index in range(len(headers))
                 if index not in columns.values() and index < len(values)
                 and _clean(values[index]) is not None}
        period_basis_override = None
        if not has_period and default_period is not None:
            raw["period_start"], raw["period_end"] = default_period
            period_basis_override = "explicit_period"
        report["input_count"] += 1
        try:
            market, outside = _market(raw.get("market") or raw.get("warehouse") or raw.get("customer"))
            if outside:
                report["skipped"].append({"source_row": source_row, "reason": "outside_usnj_scope",
                                          "market": market})
                continue
            sku = _text_or_none(raw.get("sku"))
            if sku is None:
                fail("missing_sku", f"SKU缺失（源行{source_row}）")
            uom = _text_or_none(raw.get("uom"))
            if uom is None:
                fail("missing_uom", f"UOM缺失（源行{source_row}）")
            action = _text_or_none(raw.get("action"))
            if action is None:
                fail("missing_action", f"建议动作缺失（源行{source_row}）")
            start, end, period_basis = _period(raw, source_row)
            if period_basis_override:
                period_basis = period_basis_override
            customer = _text_or_none(raw.get("customer"))
            form = _text_or_none(raw.get("physical_form"))
            warehouse = _text_or_none(raw.get("warehouse"))
            if warehouse is None:
                warehouse = {"USNJ": "美东-CENTRADE", "USTX": "美中-FZH-DANEEY",
                             "PL": "波兰-FZHPoland-covers"}.get(str(market or ""))
            qty = _number_or_none(raw.get("qty"), "建议数量", source_row)
            expedite_qty = _number_or_none(raw.get("expedite_qty"), "催已有量", source_row)
            new_order_qty = _number_or_none(raw.get("new_order_qty"), "新补数量", source_row)
            c_qty = _number_or_none(raw.get("c_qty"), "C可用量", source_row)
            e_qty = _number_or_none(raw.get("e_qty"), "E供给", source_row)
            forecast = _number_or_none(raw.get("forecast"), "预测", source_row)
            q50 = _number_or_none(raw.get("q50"), "q50", source_row)
            if forecast is None:
                forecast = q50
            q90 = _number_or_none(raw.get("q90"), "q90", source_row)
            q95 = _number_or_none(raw.get("q95"), "q95", source_row)
            coverage, coverage_text, coverage_unit = _coverage(raw.get("coverage"), source_row)
            coverage_header = headers[columns["coverage"]] if "coverage" in columns else ""
            if coverage is not None and coverage_unit is None and "天数" in str(coverage_header):
                coverage_unit = "days"
            confidence_level, confidence_value = _confidence(raw.get("confidence"))
            key = (sku, customer, warehouse, form, uom, start.isoformat(), end.isoformat())
            ownership_pending = customer is None
            candidate = {
                "row_id": digest(key),
                "ownership_pending": ownership_pending,
                "sku": sku,
                "customer": customer,
                "warehouse": warehouse,
                "market": market,
                "physical_form": form,
                "uom": uom,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "period_basis": period_basis,
                "action": action,
                "action_recognized": action in KNOWN_ACTIONS,
                "qty": qty,
                "expedite_qty": expedite_qty,
                "new_order_qty": new_order_qty,
                "coverage": coverage,
                "coverage_text": coverage_text,
                "coverage_unit": coverage_unit,
                "reason": _text_or_none(raw.get("reason")),
                "confidence": confidence_value,
                "confidence_text": _text_or_none(raw.get("confidence")),
                "confidence_level": confidence_level,
                "c_qty": c_qty,
                "e_qty": e_qty,
                "forecast": forecast,
                "q50": q50,
                "q90": q90,
                "q95": q95,
                "model": _text_or_none(raw.get("model")),
                "source_note": _text_or_none(raw.get("source_note")),
                "source_row": source_row,
                "source_hash": digest({field: (values[index] if index < len(values) else None)
                                       for field, index in columns.items()}),
                "extra": extra,
                "service_certified": SERVICE_CERTIFIED,
                "replenishment_eligible": REPLENISHMENT_ELIGIBLE,
            }
            explicit_decision = _bool_or_none(raw.get("needs_decision"))
            candidate["needs_decision"] = (explicit_decision if explicit_decision is not None
                                           else action in {"需拍板", "待定"})
            explicit_low = _bool_or_none(raw.get("low_confidence"))
            candidate["low_confidence"] = (explicit_low if explicit_low is not None
                                           else (confidence_level == "low" if confidence_level else None))
            supply_columns = "c_qty" in columns or "e_qty" in columns
            candidate["missing_supply"] = ((c_qty is None or e_qty is None)
                                           if supply_columns else None)
            explicit_special = _bool_or_none(raw.get("special"))
            candidate["special"] = (explicit_special if explicit_special is not None
                                    else bool(form and "特殊" in form))
            candidates.append((key, candidate))
        except DomainError as exc:
            report["rejected"].append({"source_row": source_row, "reason": exc.code,
                                       "detail": exc.message, "sku": _text_or_none(raw.get("sku")),
                                       "uom": _text_or_none(raw.get("uom")),
                                       "action": _text_or_none(raw.get("action"))})
    counts = {}
    for key, _ in candidates:
        counts[key] = counts.get(key, 0) + 1
    for key, candidate in candidates:
        if counts[key] > 1:
            report["rejected"].append({"source_row": candidate["source_row"], "reason": "duplicate_identity",
                                       "sku": candidate["sku"], "customer": candidate["customer"],
                                       "warehouse": candidate["warehouse"],
                                       "physical_form": candidate["physical_form"], "uom": candidate["uom"],
                                       "period_start": candidate["period_start"],
                                       "period_end": candidate["period_end"]})
        else:
            rows.append(candidate)
    report["accepted_count"] = len(rows)
    report["skipped_count"] = len(report["skipped"])
    report["rejected_count"] = len(report["rejected"])
    report["reconciled"] = (report["input_count"] == report["accepted_count"]
                            + report["rejected_count"] + report["skipped_count"])
    report["status"] = ("empty" if not rows else
                        "has_rejections" if report["rejected_count"] else "inspected")
    report["unknown_counts"] = {
        "qty": sum(row["qty"] is None for row in rows),
        "c_qty": sum(row["c_qty"] is None for row in rows),
        "e_qty": sum(row["e_qty"] is None for row in rows),
        "forecast": sum(row["forecast"] is None for row in rows),
        "confidence": sum(row["confidence_level"] is None for row in rows),
    }
    report["flag_counts"] = {
        "needs_decision": sum(bool(row["needs_decision"]) for row in rows),
        "low_confidence": sum(bool(row["low_confidence"]) for row in rows),
        "missing_supply": sum(bool(row["missing_supply"]) for row in rows),
        "special": sum(bool(row["special"]) for row in rows),
    }
    return rows, report


SO_SUMMARY_FIELDS = (
    "so_open_qty", "so_open_orders", "so_overdue_days_max",
    "so_recent_open_qty", "so_recent_open_orders", "so_recent_overdue_days_max",
    "so_history_open_qty", "so_history_open_orders", "so_history_overdue_days_max",
    "so_unknown_date_open_qty", "so_unknown_date_open_orders",
    "so_window_start", "so_as_of", "so_source_as_of",
)


def build_snapshot(path, as_of, mapping=None, actor="system", period_start=None, period_end=None,
                   so_evidence=None, so_window_start=None):
    """Build an immutable snapshot payload from one explicit CSV file.

    Sources without a period column must pass ``period_start``/``period_end``;
    the builder never invents a 97-day window from ``as_of``.

    SO evidence is split by creation date into ``recent`` (default six months
    ending at ``as_of``) and ``history`` (older, still open).  Older positive
    balances stay in the snapshot as ``history``; they are never dropped.
    """
    observed = day(as_of)
    default_period = None
    if period_start is not None or period_end is not None:
        if period_start is None or period_end is None:
            fail("invalid_period", "period_start 与 period_end 必须同时提供")
        start = day(period_start)
        end = day(period_end)
        if end < start:
            fail("invalid_period", "period_end 早于 period_start")
        default_period = (start, end)
    rows, report = _canonical_rows(path, mapping, default_period=default_period)
    so_map = {}
    so_window = None
    if so_evidence:
        from .so_evidence import load as load_so, months_before
        so_window = (day(so_window_start).isoformat() if so_window_start is not None
                     else months_before(observed).isoformat())
        so_map = load_so(so_evidence, observed.isoformat(), window_start=so_window)
    sku_to_tt = {}
    sku_map_path = Path("D:/Work/fzh-order-store/sku_map.tsv")
    if sku_map_path.exists():
        import csv as _csv
        with sku_map_path.open(encoding="utf-8") as handle:
            reader = _csv.reader(handle, delimiter="	")
            for parts in reader:
                if len(parts) >= 2 and parts[0].strip():
                    if parts[1].strip():
                        sku_to_tt.setdefault(parts[0].strip(), []).append(parts[1].strip())
    for row in rows:
        row["as_of"] = observed.isoformat()
        aliases = sku_to_tt.get(str(row.get("sku") or ""), [])
        row["tongtool_skus"] = aliases
        row["tongtool_sku"] = aliases[0] if len(aliases) == 1 else None
        branch = str(row.get("market") or "")
        ev = so_map.get((row.get("sku"), branch))
        for key in SO_SUMMARY_FIELDS:
            row[key] = ev.get(key) if ev else None
        row["so_lines"] = ev["so_lines"] if ev else []
        row["so_has_recent"] = bool(ev and ev.get("so_recent_open_qty"))
        row["so_has_history"] = bool(ev and ev.get("so_history_open_qty"))
        row["so_has_unknown_date"] = bool(ev and ev.get("so_unknown_date_open_qty"))
        row["so_included_in_recommendation"] = False
    body = {
        "schema": SCHEMA,
        "source_name": report["source_name"],
        "source_sha256": report["source_sha256"],
        "as_of": observed.isoformat(),
        "columns": report["columns"],
        "unmapped_columns": report["unmapped_columns"],
        "input_count": report["input_count"],
        "accepted_count": report["accepted_count"],
        "rejected_count": report["rejected_count"],
        "skipped_count": report["skipped_count"],
        "reconciled": report["reconciled"],
        "status": report["status"],
        "rows": rows,
        "rejected": report["rejected"],
        "skipped": report["skipped"],
        "unknown_policy": UNKNOWN_POLICY,
        "unknown_counts": report["unknown_counts"],
        "flag_counts": report["flag_counts"],
        "assumptions": report["assumptions"],
        "so_evidence_source": str(so_evidence) if so_evidence else None,
        "so_window_start": so_window,
        "so_window_months": 6 if so_evidence else None,
        "so_window_basis": "transaction_date_within_window" if so_evidence else None,
        "so_history_retained": True if so_evidence else None,
        "service_certified": SERVICE_CERTIFIED,
        "replenishment_eligible": REPLENISHMENT_ELIGIBLE,
        "read_only": READ_ONLY,
    }
    snapshot_id = digest(body)
    snapshot = dict(body, snapshot_id=snapshot_id, sha256=snapshot_id,
                    imported_by=actor, imported_at=None)
    return snapshot, report


def _write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                                     allow_nan=False), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="USNJ 补货建议只读快照导入（不改D5/C/E，不下单）")
    parser.add_argument("--source", required=True, help="USNJ补货建议CSV")
    parser.add_argument("--as-of", required=True, help="数据时点YYYY-MM-DD")
    parser.add_argument("--period-start", default=None, help="无期间列时必须显式提供期间开始YYYY-MM-DD")
    parser.add_argument("--period-end", default=None, help="无期间列时必须显式提供期间结束YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="报告与快照输出目录（私有目录）")
    parser.add_argument("--db", help="可选：装载到本地SQLite台账")
    parser.add_argument("--actor", default="system", help="导入人")
    parser.add_argument("--mapping", help="可选列映射JSON，例如 {\"qty\": \"建议采购量\"}")
    parser.add_argument("--so-evidence", default=None, help="W1 supply_facts_raw.jsonl（只读SO证据层）")
    parser.add_argument("--so-window-start", default=None,
                        help="SO 近期窗口起点YYYY-MM-DD；默认 as_of 前6个月，更老正余额仍保留为历史开放")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8")) if args.mapping else None
        snapshot, report = build_snapshot(args.source, args.as_of, mapping, args.actor,
                                          period_start=args.period_start,
                                          period_end=args.period_end,
                                          so_evidence=args.so_evidence,
                                          so_window_start=args.so_window_start)
        _write(out / "report.json", report)
        _write(out / "snapshot.json", snapshot)
        if args.db:
            from .core import Store
            snapshot = Store(args.db).set_recommendation_snapshot(snapshot, args.actor)
        print(json.dumps({key: report[key] for key in
                          ("status", "input_count", "accepted_count", "rejected_count",
                           "skipped_count", "reconciled", "unknown_counts", "flag_counts")},
                         ensure_ascii=False))
        return 0
    except DomainError as exc:
        _write(out / "last_attempt.json", {"status": "failed", "code": exc.code,
                                           "message": exc.message})
        print(exc.message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
