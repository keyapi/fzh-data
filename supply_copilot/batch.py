"""Reproducible whole-branch refresh snapshot — read-only, auditable.

The single-SKU entry point (``refresh.refresh_sku``) stays as the legacy
exploration path.  This module is the *batch* entry: it walks every D6 row of
one pool, states the period basis it used, keeps W1 SO evidence in its own
stage (never added to proven supply), and writes two immutable-audit artifacts:

* ``refresh_<branch>_<as_of>_<hash>.json`` — the snapshot (deterministic);
* ``report.json`` — the reconciliation report (input = accepted + rejected + skipped).

Nothing is written to EN; the only network call is a read-only GET of the live
stock overlay (or an offline snapshot passed with ``--live-snapshot``).
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from demand_collaboration.so_evidence import load_deduped

from .paths import load_manifest
from .period import resolve_period
from .recommend import BRANCH, D6_FILES, _need_columns, _path
from .refresh import _tt_skus
from .so_stage import load_stage_balances

SCHEMA_SNAPSHOT = "supply-copilot-refresh-snapshot/v1"
SCHEMA_REPORT = "supply-copilot-refresh-report/v1"
WAREHOUSE = {"美东USNJ": "美东-CENTRADE", "美中USTX": "美中-FZH-DANEEY",
             "波兰": "波兰-FZHPoland-covers"}
POOL_BRANCH = {"美东USNJ": "USNJ", "美中USTX": "USTX", "波兰": "PL"}
ACTION_NOW = "暂不能判断"
PROVEN_STAGES = ("on_hand", "in_transit", "to_ship")
LIVE_FIELDS = {"on_hand": "available", "in_transit": "intransit",
               "to_ship": "waiting_shipment"}

FIELD_DICTIONARY = {
    "period.basis": "full_period=D5 整期（97/157 天）；explicit_period=调用方显式声明",
    "period.determinate": "true 才允许给出确定建议；false 时 action=暂不能判断",
    "period.start/end": "本次建议覆盖的日期区间（含首尾）",
    "demand.q95": "D5 整期 q95 需求；缺失保持 null，不补 0",
    "supply.proven": "已证供给 = on_hand + in_transit + to_ship（同一 EN 快照、单别名匹配）",
    "supply.stages[].counts_as_proven": "仅 on_hand/in_transit/to_ship 计入 proven",
    "so.open_qty": "W1 SO 开放量（qty-delivered），按 (so, so_line) 去重后只计一次",
    "so.recent/history/unknown_date_open_qty": "按创建日三段，合计等于 open_qty",
    "so.included_in_proven_supply": "恒为 false：SO 是工厂交付阶段，不是海外可发供给",
    "so.stage_balances": "W1 阶段余额（完工/在产/在途/未排产/未知…），与世界开放量不同度量，不可相加",
    "pipeline": "PO/CG 等未证管线量；不进入 proven，未知保持 null",
    "net_requirement": "q95 − proven；期间不确定或证据缺失时为 null",
    "decision.action": "补 / 催已有/待核 / 不补 / 暂不能判断",
}


def _text(value):
    if value is None or isinstance(value, bool):
        return None if value is None else str(value)
    try:
        if pd.isna(value) is True:
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, 6)


def _jsonable(value):
    if value is None:
        return None
    try:
        if pd.isna(value) is True:
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, (str, int, bool)):
        return value
    return str(value)


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- live

def load_live(env_file=None, snapshot_path=None, rows=None):
    """Read the live EN overlay once (or an offline snapshot); never writes."""
    if rows is not None:
        return {"status": "ok" if rows else "unavailable", "rows": list(rows),
                "run_id": _first(rows, "run_id"), "snapshot_at": _first(rows, "snapshot_at"),
                "source": "injected_rows", "source_path": None, "error": None}
    if snapshot_path:
        path = Path(snapshot_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        got = data.get("rows") if isinstance(data, dict) else data
        got = got or []
        return {"status": "ok" if got else "unavailable", "rows": got,
                "run_id": (data.get("run_id") if isinstance(data, dict) else None)
                          or _first(got, "run_id"),
                "snapshot_at": (data.get("snapshot_at") if isinstance(data, dict) else None)
                               or _first(got, "snapshot_at"),
                "source": "snapshot_file", "source_path": str(path),
                "error": None if got else "离线快照没有 rows"}
    from .live_stock_adapter import read_live
    try:
        got = read_live(env_file=env_file)
    except Exception as exc:  # noqa: BLE001 - report, never guess
        return {"status": "unavailable", "rows": [], "run_id": None, "snapshot_at": None,
                "source": "en_live_stock", "source_path": None,
                "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok" if got else "unavailable", "rows": got,
            "run_id": _first(got, "run_id"), "snapshot_at": _first(got, "snapshot_at"),
            "source": "en_live_stock", "source_path": None,
            "error": None if got else "EN 实时库存返回空"}


def _first(rows, field):
    for row in rows or []:
        if row.get(field) not in (None, ""):
            return row.get(field)
    return None


def live_index(rows):
    """{(sku.lower(), warehouse.lower()): (quantities, row)} + conflicting keys."""
    index, conflicts = {}, set()
    for row in rows or []:
        sku, warehouse = _text(row.get("sku")), _text(row.get("warehouse"))
        if not sku or not warehouse:
            continue
        key = (sku.lower(), warehouse.lower())
        quantities = tuple(_num(row.get(LIVE_FIELDS[field])) for field in PROVEN_STAGES)
        if key in index and index[key][0] != quantities:
            conflicts.add(key)
            continue
        index.setdefault(key, (quantities, row))
    return index, conflicts


def lookup_live(live, index, conflicts, aliases, warehouse):
    aliases = sorted({str(a).strip() for a in aliases if str(a).strip()})
    out = {"status": None, "aliases": aliases, "matched_aliases": [],
           "missing_aliases": [], "rows": [], "quantities": None,
           "run_id": live.get("run_id"), "snapshot_at": live.get("snapshot_at"),
           "error": None}
    if live.get("status") != "ok":
        out["status"] = "unavailable"
        out["error"] = live.get("error") or "EN 实时库存不可用"
        return out
    if not aliases:
        out["status"] = "no_alias"
        out["error"] = "sku_map.tsv 未登记该商品的通途 SKU"
        return out
    for alias in aliases:
        key = (alias.lower(), str(warehouse).lower())
        if key in conflicts:
            out["status"] = "conflict"
            out["error"] = f"同一 (SKU, 仓) 出现数量冲突：{alias} @ {warehouse}"
            return out
        if key in index:
            out["matched_aliases"].append(alias)
            out["rows"].append(index[key][1])
        else:
            out["missing_aliases"].append(alias)
    if not out["matched_aliases"]:
        out["status"] = "not_found"
        out["error"] = f"EN 快照里没有该 SKU 在 {warehouse} 的行"
    elif out["missing_aliases"]:
        out["status"] = "partial"
        out["error"] = "部分别名未匹配，合计会漏数"
    elif len(out["matched_aliases"]) > 1:
        out["status"] = "multi_alias"
        out["error"] = "多个别名同时匹配，直接相加可能重复计数"
    else:
        quantities = index[(out["matched_aliases"][0].lower(),
                            str(warehouse).lower())][0]
        if any(value is None for value in quantities):
            out["status"] = "partial_fields"
            out["error"] = "EN 行存在未知数量字段"
        else:
            out["status"] = "matched"
            out["quantities"] = dict(zip(PROVEN_STAGES, quantities))
    return out


# --------------------------------------------------------------------------- core

def _row_payload(row, d5, so_map, stage_map, live, index, conflicts, tt_skus,
                 params, row_index):
    pool = _text(row.get("池"))
    pid = _text(row.get("product_id"))
    form, uom = _text(row.get("形态")), _text(row.get("UOM"))
    warehouse = WAREHOUSE.get(pool or "")
    branch_code = POOL_BRANCH.get(pool or "")
    warnings = []

    demand_row = d5.get((pid, pool, form, uom))
    horizon_days = _num(demand_row.get("horizon_days")) if demand_row else None
    q95 = _num(demand_row.get("q95")) if demand_row else None
    q50 = _num(demand_row.get("p50")) if demand_row else None
    q90 = _num(demand_row.get("q90")) if demand_row else None
    if demand_row is None:
        warnings.append("D5 该键无预测行（demand 全部 null，不作 0）")

    period = resolve_period(
        horizon_days=horizon_days if horizon_days else params["horizon"],
        pack_as_of=params["pack_as_of"], as_of=params["as_of"],
        period_start=params["period_start"], period_end=params["period_end"])

    live_out = lookup_live(live, index, conflicts, tt_skus.get(pid, []), warehouse)
    if live_out["status"] != "matched":
        warnings.append(f"实时库存不可用于合计：{live_out['status']} — {live_out['error']}")
    elif live_out["snapshot_at"] is None:
        warnings.append("EN 快照缺少 snapshot_at（时点不明）")
    elif _text(live_out["snapshot_at"])[:10] != params["as_of"]:
        warnings.append(
            f"EN 库存快照 {_text(live_out['snapshot_at'])} 与 as_of {params['as_of']} 不同日，"
            "库存不是 as_of 当刻")

    proven = None
    stages = []
    unknown_supply = []
    if live_out["quantities"] is not None:
        for stage in PROVEN_STAGES:
            stages.append({"stage": stage, "qty": live_out["quantities"][stage],
                           "known": True, "counts_as_proven": True,
                           "source": f"EN live stock ({live_out['run_id']})",
                           "evidence": "live_snapshot"})
        proven = round(sum(live_out["quantities"].values()), 6)
    else:
        for stage in PROVEN_STAGES:
            stages.append({"stage": stage, "qty": None, "known": False,
                           "counts_as_proven": True, "source": "EN live stock",
                           "evidence": "missing"})
            unknown_supply.append({"stage": stage, "qty": None,
                                   "reason": live_out["error"]})

    po_open = _num(row.get("PO追加(去重)"))
    cg_open = _num(row.get("CG可调拨抵扣"))
    d6_so = _num(row.get("SO已下"))
    if po_open is not None:
        stages.append({"stage": "po_open", "qty": po_open, "known": True,
                       "counts_as_proven": False, "source": "D6 PO追加(去重)",
                       "evidence": "pack_column"})
    else:
        unknown_supply.append({"stage": "po_open", "qty": None,
                               "reason": "D6 PO追加(去重) 为空"})
    if cg_open is not None:
        stages.append({"stage": "cg_transfer", "qty": cg_open, "known": True,
                       "counts_as_proven": False, "source": "D6 CG可调拨抵扣",
                       "evidence": "pack_column"})

    so_summary, so_stage = _so_block(pid, branch_code, so_map, stage_map, d6_so,
                                     params["so_loaded"])
    if so_summary["open_qty"] is not None:
        stages.append({"stage": "so_open", "qty": so_summary["open_qty"], "known": True,
                       "counts_as_proven": False,
                       "source": "W1 SO lines（(so, so_line) 去重）",
                       "evidence": "pack_evidence"})
    if so_summary["open_qty"] is None:
        unknown_supply.append({"stage": "so_open", "qty": None,
                               "reason": so_summary["error"]})
    for stage, qty in (so_stage or {}).get("so_stage_qty", {}).items():
        stages.append({"stage": f"w1_stage:{stage}", "qty": qty, "known": True,
                       "counts_as_proven": False,
                       "source": "W1 stage_balances（与开放量不同度量，不可相加）",
                       "evidence": "pack_evidence"})

    decision = _decide(period=period, q95=q95, proven=proven, live_out=live_out,
                       po_open=po_open, cg_open=cg_open,
                       so_open=so_summary["open_qty"],
                       so_evidence_loaded=so_summary["evidence_loaded"])

    return {
        "key": f"{branch_code}|{pid}|{form}|{uom}",
        "product_id": pid, "branch": branch_code, "pool": pool,
        "form": form, "uom": uom, "warehouse": warehouse,
        "period": period,
        "demand": {"q50": q50, "q90": q90, "q95": q95,
                   "horizon": _num(demand_row.get("horizon")) if demand_row else None,
                   "horizon_days": horizon_days,
                   "model": _text(demand_row.get("model")) if demand_row else None,
                   "source": params["d5_file"] if demand_row else None},
        "supply": {"proven": proven,
                   "proven_definition": "on_hand + in_transit + to_ship（EN 单快照、单别名）",
                   "stages": stages, "unknown": unknown_supply,
                   "included_in_proven_supply": list(PROVEN_STAGES)},
        "so": so_summary,
        "so_stage": so_stage,
        "pipeline": {"po_open": po_open, "cg_transfer": cg_open},
        "decision": decision,
        "live": {"status": live_out["status"], "source": live.get("source"),
                 "run_id": live_out["run_id"], "snapshot_at": live_out["snapshot_at"],
                 "matched_aliases": live_out["matched_aliases"],
                 "missing_aliases": live_out["missing_aliases"],
                 "error": live_out["error"]},
        "d6_replay": {name: _jsonable(row.get(name)) for name in (
            "q95", "C可发供给", "en_stock在途+待发", "PO追加(去重)", "SO已下",
            "CG可调拨抵扣", "净需求95", "建议动作", "新补数量", "催已有量",
            "需要日", "下单日", "路线状态")},
        "warnings": warnings,
        "provenance": {"row_index": row_index, "d6_file": params["d6_file"],
                       "d5_file": params["d5_file"], "sku_map_file": "sku_map.tsv",
                       "so_evidence_file": params["so_file"],
                       "live_source": live.get("source"),
                       "live_run_id": live.get("run_id"),
                       "pack_version": params["pack_version"],
                       "pack_as_of": params["pack_as_of"],
                       "as_of": params["as_of"]},
    }


def _so_block(pid, branch_code, so_map, stage_map, d6_so, evidence_loaded):
    summary = so_map.get((pid, branch_code)) if branch_code else None
    stage = stage_map.get((pid, branch_code)) if branch_code else None
    if summary is None:
        block = {"matched": False, "open_qty": 0.0 if evidence_loaded else None,
                 "recent_open_qty": 0.0 if evidence_loaded else None,
                 "history_open_qty": 0.0 if evidence_loaded else None,
                 "unknown_date_open_qty": 0.0 if evidence_loaded else None,
                 "recent_open_orders": 0, "history_open_orders": 0,
                 "unknown_date_open_orders": 0, "lines_count": 0,
                 "duplicate_lines_collapsed": 0,
                 "stage_counts": {}, "stage_status": "unknown",
                 "included_in_proven_supply": False,
                 "evidence_loaded": evidence_loaded,
                 "coverage": "no_open_line_observed" if evidence_loaded else "evidence_missing",
                 "error": None if evidence_loaded else "W1 SO 证据不可用"}
    else:
        duplicated = summary.get("so_duplicate_lines", 0)
        bucket_sum = round(summary["so_recent_open_qty"] + summary["so_history_open_qty"]
                           + summary["so_unknown_date_open_qty"], 6)
        stage_counts = {}
        for line in summary["so_lines"]:
            name = _text(line.get("stage")) or "unknown"
            stage_counts[name] = round(stage_counts.get(name, 0.0) + line["open_qty"], 6)
        placed = [name for name in stage_counts if name != "unknown"]
        stage_status = ("unknown" if not placed
                        else ("mixed" if "unknown" in stage_counts else "known"))
        block = {"matched": True, "open_qty": round(summary["so_open_qty"], 6),
                 "recent_open_qty": round(summary["so_recent_open_qty"], 6),
                 "history_open_qty": round(summary["so_history_open_qty"], 6),
                 "unknown_date_open_qty": round(summary["so_unknown_date_open_qty"], 6),
                 "recent_open_orders": summary["so_recent_open_orders"],
                 "history_open_orders": summary["so_history_open_orders"],
                 "unknown_date_open_orders": summary["so_unknown_date_open_orders"],
                 "lines_count": len(summary["so_lines"]),
                 "duplicate_lines_collapsed": duplicated,
                 "stage_counts": stage_counts, "stage_status": stage_status,
                 "included_in_proven_supply": False, "evidence_loaded": True,
                 "coverage": "observed", "error": None,
                 "three_bucket_sum_equals_open":
                     abs(bucket_sum - round(summary["so_open_qty"], 6)) < 1e-6,
                 "window_start": summary["so_window_start"],
                 "source_as_of": summary.get("so_source_as_of")}
    block["d6_so_open"] = d6_so
    if d6_so is not None and block["open_qty"] is not None:
        block["w1_minus_d6"] = round(block["open_qty"] - d6_so, 6)
    else:
        block["w1_minus_d6"] = None
    return block, stage


def _decide(*, period, q95, proven, live_out, po_open, cg_open, so_open,
            so_evidence_loaded):
    reasons = []
    if not period["determinate"]:
        reasons.append(period["reason"])
    if q95 is None:
        reasons.append("D5 q95 缺失或不可解析（未知不补 0）")
    if live_out["status"] != "matched":
        reasons.append(f"已证供给不可用：{live_out['status']}（{live_out['error']}）")
    elif _text(live_out["snapshot_at"]) is None:
        reasons.append("EN 快照时点不明（snapshot_at 缺失）")
    if reasons:
        return {"action": ACTION_NOW, "reason": "；".join(r for r in reasons if r),
                "net_requirement": None, "net_formula": None,
                "so_included_in_supply": False}

    net = round(q95 - proven, 6)
    if net <= 0:
        return {"action": "不补", "reason": f"q95 {q95:g} ≤ 已证供给 {proven:g}",
                "net_requirement": net, "net_formula": "q95 - proven",
                "so_included_in_supply": False}
    pipeline_unknown = [name for name, value in
                        (("PO", po_open), ("CG", cg_open),
                         ("SO", so_open if so_evidence_loaded else None))
                        if value is None]
    pipeline_positive = [name for name, value in
                         (("PO", po_open), ("CG", cg_open), ("SO", so_open))
                         if value is not None and value > 0]
    if pipeline_unknown:
        action = "催已有/待核"
        reason = (f"净需求 {net:g} > 0，但管线量（{'/'.join(pipeline_unknown)}）未知，"
                  "不得当 0 也不得计入已证供给；先核实")
    elif pipeline_positive:
        action = "催已有/待核"
        reason = (f"净需求 {net:g} > 0；存在未证管线段（{'/'.join(pipeline_positive)}），"
                  "不得相加成已证供给；先核实进度")
    else:
        action = "补"
        reason = f"净需求 {net:g} > 0 且无未证管线可催"
    return {"action": action, "reason": reason, "net_requirement": net,
            "net_formula": "q95 - proven", "so_included_in_supply": False}


# --------------------------------------------------------------------------- run

def refresh_pool(data_root, branch, as_of=None, period_start=None, period_end=None,
                 sku=None, d6_version="v6_22", horizon=97, env_file=None,
                 live_snapshot=None, live_rows=None, manifest=None):
    """Return ``{"snapshot": {...}, "report": {...}}`` for one branch pool."""
    root = Path(data_root)
    manifest = manifest or load_manifest()
    pack_as_of = _text(manifest.get("as_of"))
    as_of = _text(as_of) or pack_as_of
    pool = BRANCH.get(str(branch), str(branch))
    d6_name = D6_FILES.get(d6_version, D6_FILES["v6_22"])
    d5_name = "D5_v6_8.xlsx"
    so_name = "W1_SO.jsonl"

    d6 = pd.read_excel(_path(root, d6_name), sheet_name="1_全量动作")
    d5 = pd.read_excel(_path(root, d5_name), sheet_name="1_预测")
    _need_columns(d6, ["product_id", "池", "形态", "UOM"], "D6")
    _need_columns(d5, ["product_id", "pool", "physical_form", "canonical_uom",
                       "horizon", "horizon_days", "p50", "q90", "q95", "model"], "D5")

    frame = d6[d6["池"].astype(str) == pool].copy()
    if sku:
        frame = frame[frame["product_id"].astype(str).str.upper()
                      == str(sku).upper()]
    input_rows = len(frame)

    d5_rows = d5[d5["horizon"].astype(str) == str(horizon)]
    d5_map, d5_duplicates = {}, 0
    for _, row in d5_rows.iterrows():
        key = (_text(row.get("product_id")), _text(row.get("pool")),
               _text(row.get("physical_form")), _text(row.get("canonical_uom")))
        if key in d5_map:
            d5_duplicates += 1
            continue
        d5_map[key] = {name: row.get(name) for name in
                       ("p50", "q90", "q95", "model", "horizon", "horizon_days")}

    tt_skus = _tt_skus(root)
    so_path = root / "data" / so_name
    so_loaded = so_path.exists()
    if so_loaded:
        so_map, so_stats = load_deduped(so_path, as_of=as_of, dedupe=True)
    else:
        so_map, so_stats = {}, {"error": f"SO 证据文件不存在：{so_path}", "keys": 0}
    stage_map, stage_stats = load_stage_balances(so_path)
    so_source_as_of = next((summary.get("so_source_as_of")
                            for summary in so_map.values()
                            if summary.get("so_source_as_of")), None)

    live = load_live(env_file=env_file, snapshot_path=live_snapshot, rows=live_rows)
    index, conflicts = live_index(live["rows"])

    params = {"as_of": as_of, "pack_as_of": pack_as_of, "d6_file": d6_name,
              "d5_file": d5_name, "so_file": so_name, "d6_version": d6_version,
              "horizon": horizon, "period_start": period_start,
              "period_end": period_end, "pack_version": manifest.get("version"),
              "so_loaded": so_loaded}

    rows_out, rejected, skipped, seen = [], [], [], set()
    for position, (_, row) in enumerate(frame.iterrows()):
        source_row = {str(k): _jsonable(v) for k, v in row.items()}
        pid = _text(row.get("product_id"))
        form, uom = _text(row.get("形态")), _text(row.get("UOM"))
        if not pid:
            rejected.append({"row_index": position, "product_id": None,
                             "pool": _text(row.get("池")), "form": form, "uom": uom,
                             "reason": "missing_product_id", "source_row": source_row})
            continue
        if form is None or uom is None:
            rejected.append({"row_index": position, "product_id": pid,
                             "pool": _text(row.get("池")), "form": form, "uom": uom,
                             "reason": "incomplete_identity（形态/UOM 缺失）",
                             "source_row": source_row})
            continue
        key = (pid, form, uom)
        if key in seen:
            skipped.append({"row_index": position, "product_id": pid,
                            "pool": _text(row.get("池")), "form": form, "uom": uom,
                            "reason": "duplicate_key_in_d6（(product_id, 形态, UOM) 重复）",
                            "source_row": source_row})
            continue
        seen.add(key)
        rows_out.append(_row_payload(row, d5_map, so_map, stage_map, live, index,
                                     conflicts, tt_skus, params, position))

    rows_out.sort(key=lambda r: (r["product_id"] or "", r["form"] or "",
                                 r["uom"] or "", r["key"]))
    rows_sha = _sha(canonical(rows_out))

    body = {
        "schema": SCHEMA_SNAPSHOT,
        "branch": POOL_BRANCH.get(pool, str(branch)), "pool": pool,
        "as_of": as_of, "pack_version": manifest.get("version"),
        "pack_as_of": pack_as_of,
        "params": {"d6_version": d6_version, "d6_file": d6_name, "d5_file": d5_name,
                   "horizon": horizon, "period_start": period_start,
                   "period_end": period_end},
        "sources": _source_hashes(root, manifest, (d5_name, d6_name, "sku_map.tsv",
                                                   so_name)),
        "live": {name: _jsonable(live.get(name)) for name in
                 ("source", "source_path", "status", "run_id", "snapshot_at")},
        "so_evidence": {**{name: _jsonable(so_stats.get(name)) for name in
                           ("lines_read", "unique_lines", "duplicate_lines",
                            "duplicate_open_qty", "skipped_no_sku_or_branch",
                            "skipped_bad_qty", "skipped_not_open", "keys")},
                        "source_as_of": so_source_as_of},
        "so_evidence_error": so_stats.get("error"),
        "so_stage_evidence": {name: _jsonable(stage_stats.get(name)) for name in
                              ("records", "rows_read", "unique_rows", "duplicate_rows",
                               "skipped_no_branch", "skipped_no_sku", "keys",
                               "stage_totals", "stage_unknown_qty_rows", "scope_fba_qty")},
        "so_stage_error": stage_stats.get("error"),
        "row_count": len(rows_out),
        "rows": rows_out,
        "field_dictionary": FIELD_DICTIONARY,
    }
    snapshot = {**body, "rows_sha256": rows_sha,
                "snapshot_sha256": _sha(canonical(body))}
    report = _build_report(snapshot, input_rows, rows_out, rejected, skipped,
                          so_stats, stage_stats, d5_duplicates)
    return {"snapshot": snapshot, "report": report}


def _source_hashes(root, manifest, names):
    out, mismatch = {}, []
    declared = {item["path"].split("/")[-1]: item["sha256"]
                for item in manifest.get("files", []) if item.get("path")}
    for name in names:
        path = root / "data" / name
        if not path.exists():
            out[name] = None
            continue
        digest = file_sha256(path)
        out[name] = digest
        if name in declared and declared[name] and declared[name] != digest:
            mismatch.append({"file": name, "manifest": declared[name], "actual": digest})
    return {"files": out, "manifest_mismatch": mismatch}


def _build_report(snapshot, input_rows, rows_out, rejected, skipped, so_stats,
                  stage_stats, d5_duplicates):
    actions, bases, live_status = {}, {}, {}
    for row in rows_out:
        action = row["decision"]["action"]
        actions[action] = actions.get(action, 0) + 1
        basis = row["period"]["basis"]
        bases[basis] = bases.get(basis, 0) + 1
        status = row["live"]["status"]
        live_status[status] = live_status.get(status, 0) + 1
    balanced = input_rows == len(rows_out) + len(rejected) + len(skipped)
    so_three_way = {"open_total": 0.0, "recent": 0.0, "history": 0.0, "unknown": 0.0,
                    "balanced": True}
    so_stage_unknown = 0.0
    for row in rows_out:
        so = row["so"]
        for field, target in (("recent_open_qty", "recent"),
                              ("history_open_qty", "history"),
                              ("unknown_date_open_qty", "unknown")):
            value = so.get(field)
            if value is not None:
                so_three_way[target] = round(so_three_way[target] + value, 6)
        if so.get("open_qty") is not None:
            so_three_way["open_total"] = round(so_three_way["open_total"] + so["open_qty"], 6)
        if not so.get("three_bucket_sum_equals_open", True):
            so_three_way["balanced"] = False
        stage_block = row.get("so_stage") or {}
        so_stage_unknown = round(so_stage_unknown
                                 + (stage_block.get("so_stage_qty") or {}).get("unknown", 0.0), 6)
    so_three_way["sum_of_buckets"] = round(so_three_way["recent"]
                                           + so_three_way["history"]
                                           + so_three_way["unknown"], 6)
    so_three_way["balanced"] = bool(
        so_three_way["balanced"]
        and abs(so_three_way["sum_of_buckets"] - so_three_way["open_total"]) < 1e-6)
    return {
        "schema": SCHEMA_REPORT,
        "branch": snapshot["branch"], "pool": snapshot["pool"],
        "as_of": snapshot["as_of"], "pack_version": snapshot["pack_version"],
        "pack_as_of": snapshot["pack_as_of"],
        "params": snapshot["params"],
        "snapshot": {"sha256": snapshot["snapshot_sha256"],
                     "rows_sha256": snapshot["rows_sha256"],
                     "row_count": snapshot["row_count"],
                     "file": f"refresh_{snapshot['branch']}_{snapshot['as_of']}_"
                             f"{snapshot['snapshot_sha256'][:12]}.json"},
        "bankers": {"input_rows": input_rows, "accepted": len(rows_out),
                    "rejected": len(rejected), "skipped": len(skipped),
                    "balanced": balanced,
                    "definition": "输入行(D6 选取行) = 接收(入快照) + 拒收 + 跳过"},
        "accepted_by_action": actions,
        "accepted_by_period_basis": bases,
        "live_status_counts": live_status,
        "rejected": rejected,
        "skipped": skipped,
        "so_dedupe": {"dedupe_key": ["so", "so_line"], "scope": "W1 lines 开放量",
                      **{name: _jsonable(so_stats.get(name)) for name in
                         ("lines_read", "unique_lines", "duplicate_lines",
                          "duplicate_open_qty", "skipped_no_sku_or_branch",
                          "skipped_bad_qty", "skipped_not_open", "keys")},
                      "error": so_stats.get("error")},
        "so_three_way": so_three_way,
        "so_stage": {"scope": "W1 stage_balances（in_house）",
                     "not_additive_with_open_qty": True,
                     "included_in_proven_supply": False,
                     "unknown_stage_qty": so_stage_unknown,
                     **{name: _jsonable(stage_stats.get(name)) for name in
                        ("records", "rows_read", "unique_rows", "duplicate_rows",
                         "stage_totals", "stage_unknown_qty_rows", "scope_fba_qty")},
                     "error": stage_stats.get("error")},
        "d5_duplicate_keys": d5_duplicates,
        "source_hashes": snapshot["sources"],
        "live": snapshot["live"],
        "warnings": _report_warnings(snapshot, rows_out, so_stats),
        "field_dictionary": FIELD_DICTIONARY,
    }


def _report_warnings(snapshot, rows_out, so_stats):
    out = []
    if snapshot["sources"]["manifest_mismatch"]:
        out.append("数据文件哈希与 manifest 不一致：包可能被本地修改")
    if so_stats.get("error"):
        out.append(f"SO 证据不可用：{so_stats['error']}")
    if so_stats.get("duplicate_lines"):
        out.append(f"W1 SO 行 (so, so_line) 重复 {so_stats['duplicate_lines']} 条，"
                   f"开放量重复 {so_stats['duplicate_open_qty']:g} 已只计一次")
    source_as_of = (snapshot.get("so_evidence") or {}).get("source_as_of")
    if source_as_of and source_as_of != snapshot["as_of"]:
        out.append(f"W1 SO 证据 as_of={source_as_of}，与刷新 as_of={snapshot['as_of']} 不同")
    if snapshot["live"].get("snapshot_at") and \
            str(snapshot["live"]["snapshot_at"])[:10] != snapshot["as_of"]:
        out.append(f"EN 实时库存快照 {snapshot['live']['snapshot_at']} ≠ as_of "
                   f"{snapshot['as_of']}：库存不是 as_of 当刻")
    if snapshot["rows"] and all(not r["period"]["determinate"] for r in snapshot["rows"]):
        out.append("全部行 period_basis=full_period 且无显式期间：整期需求不得当剩余期，"
                   "故全部标暂不能判断（可用 --period-start/--period-end 声明等长期间）")
    unknown_q95 = sum(1 for r in rows_out if r["demand"]["q95"] is None)
    if unknown_q95:
        out.append(f"{unknown_q95} 行 D5 q95 缺失，保持 null 并拒绝确定建议")
    return out


# --------------------------------------------------------------------------- output

def write_outputs(out_dir, result):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    snapshot = result["snapshot"]
    report = result["report"]
    name = report["snapshot"]["file"]
    path = out / name
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("snapshot_sha256") != snapshot["snapshot_sha256"]:
            raise SystemExit(f"快照已存在且内容不同，拒绝覆盖：{path}")
    else:
        path.write_text(text, encoding="utf-8", newline="\n")
    report_path = out / "report.json"
    report_text = json.dumps(report, ensure_ascii=False, indent=2)
    report_path.write_text(report_text, encoding="utf-8", newline="\n")
    return {"snapshot_path": str(path),
            "snapshot_file_sha256": file_sha256(path),
            "report_path": str(report_path),
            "report_file_sha256": file_sha256(report_path)}


def summary_text(result, paths=None):
    report = result["report"]
    bankers = report["bankers"]
    lines = [
        f"{report['branch']} 刷新 {report['as_of']}（pack {report['pack_version']}，"
        f"as_of {report['pack_as_of']}）",
        f"期间：{report['params']['period_start'] or '未声明'} ~ "
        f"{report['params']['period_end'] or '未声明'}；"
        f"basis={report['accepted_by_period_basis']}",
        f"输入 {bankers['input_rows']} = 接收 {bankers['accepted']} + "
        f"拒收 {bankers['rejected']} + 跳过 {bankers['skipped']}"
        f"（{'对平' if bankers['balanced'] else '未对平'}）",
        f"动作：{report['accepted_by_action']}",
        f"SO 去重：唯一 {report['so_dedupe']['unique_lines']} 行，"
        f"重复 {report['so_dedupe']['duplicate_lines']} 行；"
        f"三段合计 {report['so_three_way']['sum_of_buckets']:g} = "
        f"开放 {report['so_three_way']['open_total']:g}"
        f"（{'守恒' if report['so_three_way']['balanced'] else '不守恒'}），未计入已证供给",
        f"EN 快照：{report['live'].get('snapshot_at')}（{report['live'].get('status')}）",
    ]
    for warning in report["warnings"]:
        lines.append(f"⚠️ {warning}")
    if paths:
        lines.append(f"快照：{paths['snapshot_path']}  sha256={paths['snapshot_file_sha256']}")
        lines.append(f"报告：{paths['report_path']}  sha256={paths['report_file_sha256']}")
    return "\n".join(lines)
