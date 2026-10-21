#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1b 窄范围 DN/WO/JC/SE 关联与数量守恒（离线复用已有快照）。

输入是 `g1b_en_extract.py` 已经落盘的客户码快照（SO/DN/WO/JC/SE 行）。
默认**不联网**：只读快照，逐行给去向，并按同 UOM 校验守恒。

允许的有界 EN 只读（必须显式开启）：
  --enrich-se        补齐快照里缺 line 级明细的 Stock Entry（按单据名逐单 GET）
  --probe-mismatch-wos N
                     对 produced_qty != SE 完工量的 WO，补查 WO 详情与该 WO 的全部
                     Stock Entry 清单（用于解释差异，不写生产）

守恒口径（只在**同一 UOM**内求和，跨 UOM 一律不出合计）：
  C1 SO 行 delivered_qty == 该行链接的已提交 DN 净量（非退货 - 退货）
  C2 WO produced_qty == 该 WO 已提交 Manufacture SE 完工行数量（需 line 级证据）
  C3 单个 SE 的 finished 行合计 == SE.finished_qty
  C4 行账：读入行数 == 逐行去向数，且每个去向恰好一条
  JC 不是守恒账：工序卡按工序批量开卡、返工卡会重复累加，只作进度证据。

用法：
  uv run python g1b_dn_wo_jc_se.py \
    --snapshot out/g1b_en_top_1.json --snapshot out/g1b_en_top_9.json \
    --snapshot out/g1b_en_rr2.json --out-dir out/dn_wo_jc_se
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "EN_API" / "item_shipment_status.py").exists()),
    Path(__file__).resolve().parents[7],
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import EN_API.item_shipment_status as iss  # noqa: E402

SCHEMA = "dn_wo_jc_se_association/1"
RULE = "dn-wo-jc-se-association/1"
SITE = iss.ENV_URLS["prod"]
PRODUCER = {"name": "g1b_dn_wo_jc_se.py", "version": "1.0.0"}
EPS = 1e-6
ROWTYPES = ("so_line", "dn_line", "wo", "jc_operation", "se", "se_line")


class InputError(RuntimeError):
    """输入/契约错误：必须 exit 2，不能产出“成功”证据。"""


# ── 小工具 ────────────────────────────────────────────
def num(v: Any) -> float | None:
    """严格数值解析；布尔不当数值。None/空串 -> None。NaN/Inf/非数字 -> None。"""
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def flag01(v: Any) -> int | None:
    """严格 0/1 解析（EN 常返回 int 1/0、字符串 '0'/'1'/'true'/'false'）。"""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not math.isfinite(float(v)):
            return None
        return int(v) if float(v) in (0.0, 1.0) else None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("0", "1"):
            return int(s)
        if s in ("true", "false"):
            return 1 if s == "true" else 0
    return None


def docstatus(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    n = num(v)
    if n is None or n not in (0.0, 1.0, 2.0):
        return None
    return int(n)


def close(a: float | None, b: float | None, tol: float = EPS) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def r2(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def date_part(v: Any) -> str | None:
    s = str(v or "").strip()
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else None


def in_window(d: str | None, window: tuple[str | None, str | None]) -> bool | None:
    lo, hi = window
    if d is None or not lo or not hi:
        return None
    return lo <= d <= hi


# ── 快照装载 ──────────────────────────────────────────
REQUIRED_SNAPSHOT_KEYS = ("query", "generated_at", "so_rows", "dn_rows", "wos",
                          "jc_summary", "se_rows")


def load_snapshot(path: Path) -> dict:
    if not path.is_file():
        raise InputError(f"快照不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InputError(f"快照不可读/非法 JSON: {path}: {e}") from e
    if not isinstance(data, dict):
        raise InputError(f"快照顶层必须是对象: {path}")
    missing = [k for k in REQUIRED_SNAPSHOT_KEYS if k not in data]
    if missing:
        raise InputError(f"快照缺字段 {missing}: {path}")
    q = data.get("query") or {}
    scope = q.get("customer_code") or q.get("item")
    if not scope:
        raise InputError(f"快照 query 没有 customer_code/item: {path}")
    data["_scope"] = scope
    data["_path"] = str(path)
    data["_sha256"] = sha256_file(path)
    return data


def index_rows(rows: list[dict], key_fn, label: str) -> tuple[dict, list[dict]]:
    """按业务键建索引；重复键不静默覆盖，返回冲突清单。"""
    idx: dict[Any, dict] = {}
    dup: list[dict] = []
    for r in rows:
        try:
            k = key_fn(r)
        except Exception as e:  # noqa: BLE001 - 坏行要留证，不中断整批
            dup.append({"label": label, "key": None, "error": f"{type(e).__name__}: {e}"})
            continue
        if k is None:
            dup.append({"label": label, "key": None, "error": "missing_key"})
        elif k in idx:
            dup.append({"label": label, "key": k, "error": "duplicate_key"})
        else:
            idx[k] = r
    return idx, dup


# ── 关联与守恒 ────────────────────────────────────────
def build_scope(snap: dict, se_details: dict, window: tuple[str | None, str | None],
                basis: str) -> dict:
    """单快照：建索引、连边、逐行去向、守恒检查。"""
    scope = snap["_scope"]
    so_rows = [r for r in snap["so_rows"] if isinstance(r, dict)]
    dn_rows = [r for r in snap["dn_rows"] if isinstance(r, dict)]
    wos = [r for r in snap["wos"] if isinstance(r, dict)]
    se_rows = [r for r in snap["se_rows"] or [] if isinstance(r, dict)]
    jc_map = snap.get("jc_summary") or {}
    as_of = date_part(snap.get("generated_at"))

    # 行键：SO 行 = so + line_id；DN 行 = dn + dn_line_id；SE = 单据名
    so_idx, so_dup = index_rows(so_rows, lambda r: (r.get("so"), r.get("line_id"))
                                if r.get("so") and r.get("line_id") else None, "so_line")
    dn_idx, dn_dup = index_rows(dn_rows, lambda r: (r.get("dn"), r.get("dn_line_id"))
                                if r.get("dn") and r.get("dn_line_id") else None, "dn_line")
    wo_idx, wo_dup = index_rows(wos, lambda r: r.get("name") or None, "wo")
    se_idx, se_dup = index_rows(se_rows, lambda r: r.get("se") or None, "se")

    so_by_so: dict[str, list[dict]] = defaultdict(list)
    for r in so_rows:
        so_by_so[r.get("so")].append(r)
    so_names = set(so_by_so)

    out_rows: list[dict] = []

    def emit(scope_: str, row_type: str, row_key: Any, link: dict, qty: dict,
             uom: Any, disposition: str, reason_code: str,
             reason_detail: str = "", in_win: bool | None = None,
             dates: dict | None = None) -> None:
        out_rows.append({
            "scope": scope_, "row_type": row_type, "row_key": row_key,
            "link": link, "qty": qty, "uom": uom,
            "in_window": in_win, "dates": dates or {},
            "disposition": disposition, "reason_code": reason_code,
            "reason_detail": reason_detail,
        })

    # ── 1. DN 行：先归属到 SO 行（精确 so_line_id；缺失才按 so+item 唯一匹配）──
    dn_net: dict[tuple, float] = defaultdict(float)     # (so, line_id) -> 已提交净量
    dn_ret: dict[tuple, float] = defaultdict(float)
    dn_draft: dict[tuple, float] = defaultdict(float)
    dn_by_line: dict[tuple, list[dict]] = defaultdict(list)
    dn_unlinked: list[dict] = []
    for d in dn_rows:
        so, sl = d.get("so"), d.get("so_line_id")
        key = None
        link_mode = None
        if so and sl and (so, sl) in so_idx:
            key, link_mode = (so, sl), "so_line_id"
        elif so:
            cands = [r for r in so_by_so.get(so, []) if r.get("item_code") == d.get("item_code")]
            if len(cands) == 1:
                key = (cands[0].get("so"), cands[0].get("line_id"))
                link_mode = "so_item_unique"
        ds = docstatus(d.get("dn_docstatus"))
        is_ret = flag01(d.get("is_return"))
        q = num(d.get("qty"))
        d_date = date_part(d.get("dn_date"))
        in_win = in_window(d_date, window)
        if key is None:
            dn_unlinked.append(d)
            emit(scope, "dn_line", f"{d.get('dn')}::{d.get('dn_line_id')}",
                 {"so": so, "so_line_id": sl, "dn": d.get("dn"),
                  "dn_line_id": d.get("dn_line_id")},
                 {"qty": q}, d.get("uom"), "unlinked", "dn_unlinked_so_line",
                 "DN 行的 so_line_id 不在本快照 SO 行内，且按 so+item 无法唯一归属",
                 in_win, {"dn_date": d.get("dn_date")})
            continue
        dn_by_line[key].append(d)
        line = so_idx[key]
        line_uom = line.get("uom")
        dn_uom = d.get("uom")
        if q is None or q < 0:
            code, detail = "dn_qty_invalid", "DN 行数量缺失/为负/非有限数"
        elif is_ret is None:
            code, detail = "dn_return_flag_invalid", f"is_return 非 0/1: {d.get('is_return')!r}"
        elif dn_uom and line_uom and dn_uom != line_uom:
            code, detail = "dn_uom_mismatch", f"DN {dn_uom} != SO {line_uom}"
        else:
            code, detail = "", ""
        if not code:
            if ds == 1:
                if is_ret:
                    dn_ret[key] += q
                    code = "dn_return_submitted"
                else:
                    dn_net[key] += q
                    code = "dn_submitted"
            elif ds == 0:
                dn_draft[key] += q
                code = "dn_draft"
            elif ds == 2:
                code = "dn_cancelled"
            else:
                code = "dn_docstatus_invalid"
                detail = f"docstatus={d.get('dn_docstatus')!r}"
        disp = "linked" if code in ("dn_submitted", "dn_return_submitted") else "excluded"
        emit(scope, "dn_line", f"{d.get('dn')}::{d.get('dn_line_id')}",
             {"so": so, "so_line_id": sl, "so_line_key": f"{key[0]}::{key[1]}",
              "dn": d.get("dn"), "dn_line_id": d.get("dn_line_id"),
              "link_mode": link_mode},
             {"qty": q}, dn_uom, disp, code or "dn_linked", detail, in_win,
             {"dn_date": d.get("dn_date")})

    # ── 2. WO → SO 行（sales_order + production_item 精确；多行则歧义不摊量）──
    wo_link: dict[str, dict] = {}
    for w in wos:
        name = w.get("name")
        so = w.get("sales_order") or ""
        item = w.get("production_item") or ""
        ds = docstatus(w.get("docstatus"))
        q, prod = num(w.get("qty")), num(w.get("produced_qty"))
        cands = [r for r in so_by_so.get(so, []) if r.get("item_code") == item] if so else []
        link: dict[str, Any] = {"so": so or None, "production_item": item or None,
                                "work_order": name}
        if ds == 2:
            disp, code = "excluded", "wo_cancelled"
        elif not so:
            disp, code = "unlinked", "wo_no_sales_order"
        elif so not in so_names:
            disp, code = "unlinked", "wo_sales_order_out_of_snapshot"
        elif not cands:
            disp, code = "unlinked", "wo_so_line_item_mismatch"
        elif len(cands) > 1:
            disp, code = "ambiguous", "wo_so_line_ambiguous"
            link["candidate_lines"] = [f"{c.get('so')}::{c.get('line_id')}" for c in cands]
        else:
            disp, code = "linked", "wo_linked_to_so_line"
            link["so_line_key"] = f"{cands[0].get('so')}::{cands[0].get('line_id')}"
            link["so_line_uom"] = cands[0].get("uom")
        wo_link[name] = {"link": link, "disposition": disp, "reason_code": code,
                         "qty": q, "produced_qty": prod}

    # ── 3. SE：归属 WO；行级同单位校验（有 line 证据时）──
    se_line_uoms: dict[str, set] = defaultdict(set)
    se_finished_by_wo: dict[str, float] = defaultdict(float)
    se_unverified_wo: set[str] = set()   # 有 SE 但行级证据不足以求值
    se_rows_out: list[dict] = []

    def se_lines_of(s: dict) -> list[dict] | None:
        if isinstance(s.get("lines"), list):
            return s["lines"]
        det = (se_details.get("by_se") or {}).get(s.get("se") or "")
        if det and det.get("ok") and isinstance(det.get("lines"), list):
            return det["lines"]
        return None

    for s in se_rows:
        name = s.get("se")
        wo = s.get("work_order") or ""
        ds = docstatus(s.get("docstatus"))
        s_date = date_part(s.get("posting_date"))
        in_win = in_window(s_date, window)
        lines = se_lines_of(s)
        sources = "snapshot" if isinstance(s.get("lines"), list) else (
            "en_get" if lines is not None else "absent")
        finished_lines = s.get("finished_lines")
        wo_item = (wo_idx.get(wo) or {}).get("production_item")
        wo_known = wo in wo_idx
        # 行级：同 UOM + 身份
        line_rows = []
        for i, ln in enumerate(lines or []):
            q = num(ln.get("qty"))
            uom, suom = ln.get("uom"), ln.get("stock_uom")
            is_fin = flag01(ln.get("is_finished_item"))
            if is_fin == 1:
                if not wo_known:
                    code, disp = "se_line_parent_wo_out_of_snapshot", "unverified"
                elif not uom or not suom or uom != suom:
                    code, disp = "se_line_finished_uom_mismatch", "unverified"
                elif wo_item and ln.get("item_code") != wo_item:
                    code, disp = "se_line_item_mismatch", "mismatch"
                elif q is None:
                    code, disp = "se_line_qty_invalid", "unverified"
                else:
                    code, disp = "se_line_finished_same_unit", "conserved"
            elif is_fin == 0:
                code, disp = "se_line_not_finished", "excluded"
            else:
                code, disp = "se_line_finished_flag_invalid", "unverified"
            rec = {"scope": scope, "row_type": "se_line",
                   "row_key": f"{name}::{ln.get('line') or i}",
                   "link": {"se": name, "se_line_id": ln.get("line"), "work_order": wo or None},
                   "qty": {"qty": q}, "uom": uom, "in_window": in_win,
                   "is_finished": is_fin,
                   "dates": {"posting_date": s.get("posting_date")},
                   "disposition": disp, "reason_code": code,
                   "reason_detail": "" if disp == "conserved" else
                   f"uom={uom} stock_uom={suom} item={ln.get('item_code')} wo_item={wo_item}"}
            se_rows_out.append(rec)
            line_rows.append(rec)
        fin_rows = [r for r in line_rows if r.get("is_finished") == 1]
        fin_bad_item = any(r["reason_code"] == "se_line_item_mismatch" for r in fin_rows)
        fin_ok = all(r["reason_code"] == "se_line_finished_same_unit" for r in fin_rows)
        fin_qty = (sum(float(r["qty"]["qty"]) for r in fin_rows) if fin_rows and fin_ok
                   else None)
        if lines is not None and not fin_ok:
            se_unverified_wo.add(wo)
        # 文档级去向
        if ds == 2:
            disp, code = "excluded", "se_cancelled"
        elif not wo:
            disp, code = "unlinked", "se_unlinked_work_order"
        elif not wo_known:
            disp, code = "unlinked", "se_work_order_out_of_snapshot"
        elif lines is None:
            disp, code = "unverified", "se_detail_absent"
        elif not fin_rows:
            disp, code = "unverified", "se_no_finished_line"
        elif fin_bad_item:
            disp, code = "mismatch", "se_finished_item_mismatch"
        elif fin_qty is None:
            disp, code = "unverified", "se_finished_lines_unverified"
        elif not close(num(s.get("finished_qty")), fin_qty):
            disp, code = "mismatch", "se_internal_sum_mismatch"
        elif ds != 1:
            disp, code = "excluded", f"se_docstatus_{ds}"
        else:
            disp, code = "conserved", "se_finished_conserved"
        se_uom = None
        if fin_qty is not None:
            us = sorted({r["uom"] for r in fin_rows if r["reason_code"] == "se_line_finished_same_unit"})
            se_uom = us[0] if len(us) == 1 else None
        if ds == 1 and wo_known and fin_qty is not None and disp != "mismatch":
            se_finished_by_wo[wo] += fin_qty
            if se_uom:
                se_line_uoms[wo].add(se_uom)
        emit(scope, "se", f"{name}", {"se": name, "work_order": wo or None,
                                      "wo_key": wo or None, "detail_source": sources},
             {"finished_qty": r2(num(s.get("finished_qty"))),
              "finished_lines_sum": r2(fin_qty),
              "declared_finished_lines": finished_lines},
             se_uom, disp, code,
             "" if disp == "conserved" else f"lines={0 if lines is None else len(lines)}",
             in_win, {"posting_date": s.get("posting_date")})
    out_rows.extend(se_rows_out)

    # ── 4. WO 行：produced_qty vs SE 完工量；JC 进度证据 ──
    wo_rows_out: list[dict] = []
    wo_summary: dict[str, dict] = {}
    for w in wos:
        name = w.get("name")
        info = wo_link[name]
        ds = docstatus(w.get("docstatus"))
        q, prod = info["qty"], info["produced_qty"]
        se_q = se_finished_by_wo.get(name)
        uoms = se_line_uoms.get(name) or set()
        uom = sorted(uoms)[0] if len(uoms) == 1 else None
        link_status, link_code = info["disposition"], info["reason_code"]
        codes = []
        wo_status = str(w.get("status") or "")
        not_started = ((prod is None or prod == 0) and se_q is None
                       and wo_status in ("Not Started", "Draft", "Pending", "Open"))
        if ds == 2:
            disp, code = "excluded", "wo_cancelled"
        elif not_started:
            disp, code = "open", "wo_not_started"
        elif uom is None:
            disp, code = "unverified", "wo_uom_unresolved"
        elif name in se_unverified_wo:
            disp, code = "unverified", "wo_se_partially_unverified"
        elif se_q is None:
            disp, code = "unverified", "wo_se_missing"
        elif close(prod, se_q):
            disp, code = "conserved", "wo_production_conserved"
        else:
            disp, code = "mismatch", "wo_se_qty_mismatch"
        if prod is not None and q is not None and prod > q + EPS:
            codes.append("wo_over_produced")
        if se_q is not None and q is not None and se_q - q > EPS:
            codes.append("wo_se_exceeds_wo_qty")
        jc = jc_map.get(name) or {}
        ops = jc.get("operations") or {}
        op_sums = {op: num(v.get("sum_qty")) for op, v in ops.items() if isinstance(v, dict)}
        numeric = {k: v for k, v in op_sums.items() if v is not None}
        max_op = max(numeric, key=numeric.get) if numeric else None
        jc_flags = []
        if not jc:
            jc_flags.append("jc_missing")
        elif not numeric:
            jc_flags.append("jc_zero_completed")
        elif jc.get("last_operation") not in numeric or (
                numeric[jc["last_operation"]] < numeric[max_op] - EPS):
            jc_flags.append("jc_routing_final_op_not_completion")
        wo_summary[name] = {
            "qty": r2(q), "produced_qty": r2(prod), "se_finished_qty": r2(se_q),
            "uom": uom, "disposition": disp, "reason_code": code,
            "link_status": link_status, "link_reason_code": link_code,
            "jc_cards": jc.get("cards"), "jc_ops": len(ops),
            "jc_max_op": max_op, "jc_max_qty": r2(numeric.get(max_op)),
            "jc_last_op": jc.get("last_operation"),
            "jc_last_op_qty": r2(numeric.get(jc.get("last_operation"))),
            "jc_flags": jc_flags,
        }
        rec = {"scope": scope, "row_type": "wo", "row_key": name,
               "link": dict(info["link"]),
               "qty": {"qty": r2(q), "produced_qty": r2(prod),
                       "se_finished_qty": r2(se_q),
                       "produced_pending": r2(prod - se_q) if prod is not None and se_q is not None else None},
               "uom": uom, "in_window": None,
               "dates": {"planned_start": w.get("planned_start_date"),
                         "planned_end": w.get("planned_end_date")},
               "disposition": disp, "reason_code": code,
               "link_status": link_status, "link_reason_code": link_code,
               "reason_detail": ";".join(codes + jc_flags)}
        wo_rows_out.append(rec)
        # JC 工序行（每工序一条；只作进度证据）
        for op, v in ops.items():
            emit(scope, "jc_operation", f"{name}::{op}",
                 {"work_order": name, "operation": op,
                  "jc_ids": (v or {}).get("jc_ids") or [],
                  "so_line_key": info["link"].get("so_line_key")},
                 {"sum_qty": r2(num((v or {}).get("sum_qty"))),
                  "cards": (v or {}).get("cards")},
                 None, "progress", "jc_progress_evidence_only",
                 "工序卡按批量/返工重复开卡，不作数量守恒",
                 None, {})
    out_rows.extend(wo_rows_out)

    # ── 5. SO 行：delivered vs DN 净量；窗口与开单状态 ──
    so_out: list[dict] = []
    for r in so_rows:
        so, sl = r.get("so"), r.get("line_id")
        key = (so, sl)
        q, delivered, open_q = num(r.get("qty")), num(r.get("delivered_qty")), num(r.get("open_qty"))
        ds = docstatus(r.get("so_docstatus"))
        d_date = date_part(r.get("so_delivery_date") if basis == "delivery" else r.get("transaction_date"))
        in_win = in_window(d_date, window)
        net = dn_net.get(key, 0.0) - dn_ret.get(key, 0.0)
        linked_dns = dn_by_line.get(key, [])
        line_uom = r.get("uom")
        dn_uom_bad = any(d.get("uom") and line_uom and d.get("uom") != line_uom
                         for d in linked_dns)
        codes = []
        if ds == 2 or (r.get("so_status") or "") == "Cancelled":
            disp, code = "excluded", "so_line_voided"
        elif q is None or delivered is None:
            disp, code = "unverified", "so_line_qty_invalid"
        elif dn_uom_bad:
            disp, code = "unverified", "so_line_dn_uom_mismatch"
        elif not linked_dns and abs(delivered) <= EPS:
            disp, code = "conserved", "so_line_no_dn"
        elif close(delivered, net):
            disp, code = "conserved", "so_line_dn_conserved"
        else:
            disp, code = "mismatch", "so_line_dn_mismatch"
        if q is not None and open_q is not None and not close(q, delivered + open_q):
            codes.append("so_line_open_identity_mismatch")
        if open_q is not None and open_q < 0:
            codes.append("so_line_over_delivered")
        if in_win is None:
            codes.append("so_line_date_missing")
        rec = {"scope": scope, "row_type": "so_line", "row_key": f"{so}::{sl}",
               "link": {"so": so, "so_line_id": sl, "item_code": r.get("item_code"),
                        "work_orders": [w.get("name") if isinstance(w, dict) else w
                                        for w in (r.get("wos") or [])],
                        "dn_keys": [f"{d.get('dn')}::{d.get('dn_line_id')}" for d in linked_dns]},
               "qty": {"qty": r2(q), "delivered_qty": r2(delivered),
                       "open_qty": r2(open_q), "dn_net": r2(net),
                       "dn_return": r2(dn_ret.get(key)), "dn_draft": r2(dn_draft.get(key))},
               "uom": r.get("uom"), "in_window": in_win,
               "dates": {"delivery": r.get("so_delivery_date"),
                         "transaction": r.get("transaction_date")},
               "disposition": disp, "reason_code": code,
               "reason_detail": ";".join(codes)}
        so_out.append(rec)
    out_rows = so_out + out_rows   # 输出顺序：SO 行锚点在前

    # ── 守恒检查 ──
    checks = conservation_checks(scope, so_out, out_rows, wo_summary)
    counts = Counter(r["row_type"] for r in out_rows)
    disp_counts = Counter(f"{r['row_type']}:{r['disposition']}" for r in out_rows)
    link_counts = Counter(f"{r['row_type']}:{r.get('link_status')}" for r in out_rows
                          if r.get("link_status"))
    # 关联覆盖：工单量按关联状态、SO 行有无工单
    wo_by_link, wo_qty_by_link = Counter(), defaultdict(float)
    for r in out_rows:
        if r["row_type"] != "wo":
            continue
        k = "linked" if r.get("link_status") == "linked" else (r.get("link_reason_code") or "?")
        wo_by_link[k] += 1
        wo_qty_by_link[k] += r["qty"]["qty"] or 0
    so_with_wo = [r for r in so_out if r["link"].get("work_orders")]
    association = {
        "wo_by_link": dict(sorted(wo_by_link.items())),
        "wo_qty_by_link": {k: r2(v) for k, v in sorted(wo_qty_by_link.items())},
        "so_lines": len(so_out),
        "so_lines_with_work_order": len(so_with_wo),
        "so_qty_with_work_order": r2(sum(r["qty"]["qty"] or 0 for r in so_with_wo)),
        "so_qty_total": r2(sum(r["qty"]["qty"] or 0 for r in so_out)),
    }

    return {
        "scope": scope,
        "snapshot": {"path": snap["_path"], "sha256": snap["_sha256"],
                     "generated_at": snap.get("generated_at"),
                     "as_of_date": as_of,
                     "query": snap.get("query")},
        "rows": out_rows,
        "wo_summary": wo_summary,
        "checks": checks,
        "counts": dict(sorted(counts.items())),
        "disposition_counts": dict(sorted(disp_counts.items())),
        "link_counts": dict(sorted(link_counts.items())),
        "association": association,
        "dup_keys": so_dup + dn_dup + wo_dup + se_dup,
        "inputs": {"so_rows": len(so_rows), "dn_rows": len(dn_rows), "wos": len(wos),
                   "se_rows": len(se_rows)},
        "unlinked_dn": len(dn_unlinked),
        "se_unlinked": sum(1 for r in out_rows if r["row_type"] == "se"
                           and r["reason_code"].startswith("se_unlinked")),
    }


def conservation_checks(scope: str, so_out: list[dict], all_rows: list[dict],
                        wo_summary: dict) -> dict:
    """C1 SO↔DN、C2 WO↔SE、C3 SE 内部、C4 行账；跨 UOM 只按 UOM 分组求和。"""
    # C1：按 UOM 分组；只对同 UOM 的 SO 行与 DN 行求和
    c1: dict[str, dict] = defaultdict(lambda: {"so_delivered": 0.0, "dn_net": 0.0,
                                               "lines": 0, "uoms_observed": set(),
                                               "skipped_uom": 0})
    for r in so_out:
        if r["disposition"] == "excluded" or r["qty"]["delivered_qty"] is None:
            continue
        uom = r["uom"] or "unknown"
        c1[uom]["uoms_observed"].add(uom)
        c1[uom]["so_delivered"] += r["qty"]["delivered_qty"]
        c1[uom]["dn_net"] += r["qty"]["dn_net"] or 0.0
        c1[uom]["lines"] += 1
    c1_out = []
    for uom, v in sorted(c1.items()):
        delta = round(v["so_delivered"] - v["dn_net"], 2)
        c1_out.append({"uom": uom, "lines": v["lines"],
                       "so_delivered": round(v["so_delivered"], 2),
                       "dn_net": round(v["dn_net"], 2), "delta": delta,
                       "pass": abs(delta) <= EPS})

    # C2：WO produced_qty vs SE 完工量（只对已求值的 WO 计 pass/mismatch）
    compared = [w for w in wo_summary.values() if w["disposition"] in ("conserved", "mismatch")]
    c2 = {"wo_total": len(wo_summary), "compared": len(compared),
          "pass": sum(1 for w in compared if w["disposition"] == "conserved"),
          "mismatch": sum(1 for w in compared if w["disposition"] == "mismatch"),
          "open": sum(1 for w in wo_summary.values() if w["disposition"] == "open"),
          "unverified": sum(1 for w in wo_summary.values()
                            if w["disposition"] not in ("conserved", "mismatch",
                                                        "excluded", "open"))}

    # C3：单 SE 内部行合计 == finished_qty
    se_rows = [r for r in all_rows if r["row_type"] == "se"]
    se_eval = [r for r in se_rows if r["reason_code"] != "se_detail_absent"]
    c3 = {"se_total": len(se_rows), "evaluated": len(se_eval),
          "pass": sum(1 for r in se_eval if r["disposition"] == "conserved"),
          "mismatch": sum(1 for r in se_eval if r["disposition"] == "mismatch"),
          "unverified": sum(1 for r in se_eval if r["disposition"] == "unverified")}

    # C4：行账由 build_manifest 统一核对（读入 row_type == 输出 row_type）
    emitted = Counter(r["row_type"] for r in all_rows)
    c4 = {"emitted": dict(sorted(emitted.items()))}
    return {"C1_so_dn": c1_out, "C2_wo_se": c2, "C3_se_internal": c3, "C4_rows": c4}


# ── EN 有界只读：SE 明细 + 异常 WO 探针 ────────────────
def enrich_se_details(snaps: list[dict], out_dir: Path, budget: int, sleep_s: float,
                      reuse_path: Path | None, env_file: str | None = None) -> dict:
    """按单据名 GET 补齐 SE 行明细；只读、单并发、限预算。"""
    env_files = [Path(env_file)] if env_file else iss.resolve_env_files()
    key, secret = iss.load_credentials("prod", env_files)
    if not key or not secret:
        raise InputError("EN 生产凭证未配置（EN_API/.env）")
    existing: dict = {}
    if reuse_path and reuse_path.is_file():
        try:
            existing = json.loads(reuse_path.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
    by_se: dict = dict(existing.get("by_se") or {})
    need: list[str] = []
    for snap in snaps:
        for s in snap.get("se_rows") or []:
            n = s.get("se")
            if not n or isinstance(s.get("lines"), list):
                continue
            if n not in by_se and n not in need:
                need.append(n)
    prev_log = existing.get("log") or {}
    log = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "site": SITE, "requested": len(need), "http": 0, "ok": 0, "failed": 0,
           "status_codes": {}, "budget": budget, "budget_exceeded": False,
           "kept_from_previous": len(by_se),
           "previous_requested": int(prev_log.get("requested") or 0)}
    for i, name in enumerate(need):
        if log["http"] >= budget:
            log["budget_exceeded"] = True
            break
        path = "/api/resource/Stock%20Entry/" + urllib.parse.quote(str(name), safe="")
        status, body = iss.api_get_status(path, SITE, key, secret)
        log["http"] += 1
        log["status_codes"][str(status)] = log["status_codes"].get(str(status), 0) + 1
        d = (body or {}).get("data") or {}
        if status == 200 and d:
            lines = []
            for ln in d.get("items") or []:
                lines.append({
                    "line": ln.get("name"),
                    "item_code": ln.get("item_code"),
                    "qty": num(ln.get("qty")),
                    "uom": ln.get("uom"),
                    "stock_uom": ln.get("stock_uom"),
                    "is_finished_item": flag01(ln.get("is_finished_item")),
                    "target_warehouse": ln.get("t_warehouse"),
                    "source_warehouse": ln.get("s_warehouse"),
                })
            by_se[name] = {
                "ok": True, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "se": name, "stock_entry_type": d.get("stock_entry_type"),
                "docstatus": docstatus(d.get("docstatus")),
                "posting_date": d.get("posting_date"),
                "work_order": d.get("work_order"),
                "from_warehouse": d.get("from_warehouse"),
                "to_warehouse": d.get("to_warehouse"),
                "lines": lines,
            }
            log["ok"] += 1
        else:
            by_se[name] = {"ok": False, "fetched_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"), "se": name, "http_status": status, "lines": None}
            log["failed"] += 1
        if i + 1 < len(need):
            time.sleep(sleep_s)
    log["detail_records"] = len(by_se)
    log["detail_records_ok"] = sum(1 for v in by_se.values() if v.get("ok"))
    stamps = sorted(v.get("fetched_at") for v in by_se.values() if v.get("fetched_at"))
    log["fetched_at_range"] = [stamps[0], stamps[-1]] if stamps else []
    log["note"] = ("每条 detail 记录来自一次成功的按单据 GET；本次 requested=0 "
                   "表示全部命中本地缓存，不代表历史未取数")
    log["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {"schema": "dn_wo_jc_se_se_details/1", "site": SITE, "log": log,
               "by_se": dict(sorted(by_se.items()))}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "se_details.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


def probe_wo_mismatches(scopes: list[dict], out_dir: Path, limit: int, sleep_s: float,
                        env_file: str | None = None) -> dict:
    """对 produced_qty != SE 的 WO，补查 WO 详情与该 WO 的全部 SE 清单（有界）。"""
    targets: list[tuple[str, str]] = []
    for sc in scopes:
        for name, w in sc["wo_summary"].items():
            if w["reason_code"] == "wo_se_qty_mismatch" and (sc["scope"], name) not in targets:
                targets.append((sc["scope"], name))
    targets = targets[:limit]
    if not targets:
        return {"schema": "dn_wo_jc_se_wo_probe/1", "targets": [], "probes": {}}
    env_files = [Path(env_file)] if env_file else iss.resolve_env_files()
    key, secret = iss.load_credentials("prod", env_files)
    if not key or not secret:
        raise InputError("EN 生产凭证未配置（EN_API/.env）")
    probes: dict = {}
    log = {"http": 0, "errors": []}
    for i, (scope, wo) in enumerate(targets):
        rec: dict = {"scope": scope, "work_order": wo}
        try:
            wd = iss.get_single("Work Order", wo, SITE, key, secret)
            log["http"] += 1
            rec["wo_detail"] = {k: wd.get(k) for k in
                                ("name", "status", "docstatus", "qty", "produced_qty",
                                 "material_transferred_for_manufacturing",
                                 "total_produced_qty", "skip_transfer",
                                 "sales_order", "production_item", "bom_no")}
            ses = iss.paginated_get(
                "Stock Entry", SITE, key, secret,
                [["Stock Entry", "work_order", "=", wo], ["Stock Entry", "docstatus", "<", 2]],
                ["name", "stock_entry_type", "docstatus", "posting_date", "work_order"],
                label="SE(probe)")
            log["http"] += 1
            rec["stock_entries"] = ses
            rec["by_type"] = dict(Counter(s.get("stock_entry_type") for s in ses))
            rec["ok"] = True
        except Exception as e:  # noqa: BLE001 - 探针失败要留证
            rec["ok"] = False
            rec["error"] = f"{type(e).__name__}: {e}"
            log["errors"].append({"work_order": wo, "error": rec["error"]})
        probes[wo] = rec
        if i + 1 < len(targets):
            time.sleep(sleep_s)
    payload = {"schema": "dn_wo_jc_se_wo_probe/1", "site": SITE, "log": log,
               "probes": probes}
    (out_dir / "wo_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


# ── 汇总写盘 ──────────────────────────────────────────
def window_summary(so_out: list[dict]) -> dict:
    inw = [r for r in so_out if r["in_window"] is True]
    outw = [r for r in so_out if r["in_window"] is False]
    unk = [r for r in so_out if r["in_window"] is None]
    def agg(rows):
        return {"lines": len(rows),
                "qty": r2(sum(r["qty"]["qty"] or 0 for r in rows)),
                "delivered": r2(sum(r["qty"]["delivered_qty"] or 0 for r in rows)),
                "open": r2(sum(r["qty"]["open_qty"] or 0 for r in rows)),
                "dispositions": dict(sorted(Counter(r["disposition"] for r in rows).items()))}
    return {"in_window": agg(inw), "out_of_window": agg(outw), "date_unknown": agg(unk)}


def build_manifest(scopes: list[dict], window: tuple[str | None, str | None], basis: str,
                   se_details: dict | None, probe: dict | None, run_id: str) -> dict:
    row_type_read = Counter()
    for sc in scopes:
        i = sc["inputs"]
        row_type_read["so_line"] += i["so_rows"]
        row_type_read["dn_line"] += i["dn_rows"]
        row_type_read["wo"] += i["wos"]
        row_type_read["se"] += i["se_rows"]
    emitted = Counter()
    for sc in scopes:
        emitted.update(r["row_type"] for r in sc["rows"])
    accounting = {}
    # SO/DN/WO/SE 行账：读入 == 输出（JC 工序与 SE 行是派生子行，单独计）
    ok_all = True
    for t in ("so_line", "dn_line", "wo", "se"):
        ok = row_type_read[t] == emitted[t]
        ok_all &= ok
        accounting[t] = {"read": row_type_read[t], "emitted": emitted[t], "match": ok}
    accounting["jc_operation"] = {"derived": emitted["jc_operation"]}
    accounting["se_line"] = {"derived": emitted["se_line"]}
    c1 = [x for sc in scopes for x in sc["checks"]["C1_so_dn"]]
    # 跨 scope 的 C1 不直接加总（同一 DN 可能跨快照重复），这里只汇总 pass 状态
    c1_pass = all(x["pass"] for x in c1)
    c3 = [sc["checks"]["C3_se_internal"] for sc in scopes]
    c3_no_mismatch = all(x["mismatch"] == 0 for x in c3)
    c3_unverified = sum(x["unverified"] for x in c3) + sum(
        x["se_total"] - x["evaluated"] for x in c3)
    dup = [d for sc in scopes for d in sc["dup_keys"]]
    audit_ok = bool(ok_all and c1_pass and c3_no_mismatch and not dup)
    evidence_complete = bool(c3_unverified == 0)

    probe_by_wo = (probe or {}).get("probes") or {}
    findings = []
    for sc in scopes:
        for name, w in sc["wo_summary"].items():
            if w["reason_code"] in ("wo_se_qty_mismatch", "wo_uom_unresolved",
                                    "wo_se_partially_unverified", "wo_se_missing"):
                item = {"scope": sc["scope"], "work_order": name,
                        "reason_code": w["reason_code"],
                        "qty": w["qty"], "produced_qty": w["produced_qty"],
                        "se_finished_qty": w["se_finished_qty"]}
                p = probe_by_wo.get(name)
                if p and p.get("ok"):
                    ses = p.get("stock_entries") or []
                    man = [s for s in ses if s.get("stock_entry_type") == "Manufacture"
                           and docstatus(s.get("docstatus")) == 1]
                    item["probe"] = {
                        "by_type": p.get("by_type"),
                        "submitted_manufacture_se": len(man),
                        "submitted_manufacture_se_names": [s.get("name") for s in man],
                        "wo_status": (p.get("wo_detail") or {}).get("status"),
                        "skip_transfer": (p.get("wo_detail") or {}).get("skip_transfer"),
                        "material_transferred_for_manufacturing":
                            (p.get("wo_detail") or {}).get("material_transferred_for_manufacturing"),
                        "verdict": "produced_qty_not_explained_by_visible_se",
                    }
                findings.append(item)
    unlinked_wo = defaultdict(int)
    for sc in scopes:
        for r in sc["rows"]:
            if r["row_type"] == "wo" and r.get("link_status") != "linked":
                unlinked_wo[r.get("link_reason_code") or "unknown"] += 1

    manifest = {
        "schema_version": SCHEMA,
        "rule_version": RULE,
        "producer": PRODUCER,
        "source": SITE,
        "site": SITE,
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id,
        "window": {"from": window[0], "to": window[1], "basis": basis,
                   "logic": "report_partition_not_filter"},
        "scopes": [{"scope": sc["scope"], "snapshot": sc["snapshot"],
                    "inputs": sc["inputs"], "counts": sc["counts"],
                    "disposition_counts": sc["disposition_counts"],
                    "link_counts": sc["link_counts"],
                    "association": sc["association"],
                    "checks": sc["checks"],
                    "window": window_summary([r for r in sc["rows"]
                                              if r["row_type"] == "so_line"]),
                    "unlinked_dn": sc["unlinked_dn"]}
                   for sc in scopes],
        "row_accounting": accounting,
        "audit_ok": audit_ok,
        "evidence_complete": evidence_complete,
        "conservation": {
            "C1_so_dn": {"pass": c1_pass, "per_scope": c1},
            "C2_wo_se": [sc["checks"]["C2_wo_se"] | {"scope": sc["scope"]} for sc in scopes],
            "C3_se_internal": {"pass": c3_no_mismatch,
                               "unverified": c3_unverified,
                               "per_scope": [dict(x) | {"scope": sc["scope"]}
                                             for x, sc in zip(c3, scopes)]},
            "JC": {"status": "progress_evidence_only",
                   "note": "工序卡不是数量守恒账：返工卡/批量卡会重复累加；"
                           "routing 末道可能是返工工艺，不能当完工量"},
        },
        "association": {
            "wo_unlinked_by_reason": dict(sorted(unlinked_wo.items())),
            "note": "WO→SO 行只认 sales_order + production_item 精确匹配；"
                    "无 SO 的备货工单与指向快照外 SO 的工单不摊量",
        },
        "wo_produced_qty": {
            "mismatch_count": sum(1 for f in findings
                                  if f["reason_code"] == "wo_se_qty_mismatch"),
            "mismatch_work_orders": [f["work_order"] for f in findings
                                     if f["reason_code"] == "wo_se_qty_mismatch"],
            "note": "WO.produced_qty 在本部署不能当完工账：样本内出现 produced_qty "
                    "远超 qty 且可见已提交 Manufacture SE 无法解释的情况；"
                    "完工量以 SE finished 行合计为准",
        },
        "se_evidence": {
            "detail_source_counts": dict(Counter(
                r["link"].get("detail_source") for sc in scopes for r in sc["rows"]
                if r["row_type"] == "se")),
            "enrichment": (se_details or {}).get("log"),
        },
        "wo_probe": (probe or {}).get("log"),
        "findings": findings,
        "notes": [
            "本文件只做 DN/WO/JC/SE 关联与数量守恒，不是 G1 验收、不是需求/补货结论。",
            "C1 只在同一 UOM 内求和；跨 UOM 不出合计。",
            "JC 仅进度证据，不进入守恒。",
            "C2 只对已取得 line 级证据的 WO 求值；缺失记 unverified。",
            "WO.produced_qty 不作完工真值；SE finished 行合计才是守恒锚点。",
        ],
    }
    manifest["payload_sha256"] = canonical_sha(manifest)
    return manifest


def stable_hash(manifest: dict) -> str:
    """去掉 run_id/as_of/在线探针等易变字段后的稳定摘要，用于两次回放比对。"""
    payload = {k: v for k, v in manifest.items()
               if k not in ("run_id", "as_of", "payload_sha256", "wo_probe",
                            "stable_sha256")}
    payload["findings"] = [{k: v for k, v in f.items() if k != "probe"}
                           for f in payload.get("findings") or []]
    if isinstance(payload.get("se_evidence"), dict):
        payload["se_evidence"] = {k: v for k, v in payload["se_evidence"].items()
                                  if k != "enrichment"}
    return canonical_sha(payload)


# ── main ─────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G1b 窄范围 DN/WO/JC/SE 关联与数量守恒（只读）")
    ap.add_argument("--snapshot", action="append", required=True,
                    help="g1b_en_extract.py 产出的快照 JSON；可重复")
    ap.add_argument("--out-dir", default=str(BASE / "out" / "dn_wo_jc_se"))
    ap.add_argument("--window-from", default="2026-04-01")
    ap.add_argument("--window-to", default="2026-09-30")
    ap.add_argument("--date-basis", choices=("delivery", "transaction"), default="delivery")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--enrich-se", action="store_true",
                    help="有界 EN 只读：补齐缺 line 明细的 SE（需凭证）")
    ap.add_argument("--reuse-se-details", action="store_true",
                    help="复用 out-dir/se_details.json 里已有的 SE 明细")
    ap.add_argument("--max-http", type=int, default=500)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--env-file", default="",
                    help="EN 凭证 .env 路径（worktree 里没有 .env 时指向主仓库）")
    ap.add_argument("--probe-mismatch-wos", type=int, default=0,
                    help="对 N 个 WO produced/se 不一致补查 WO 详情与全部 SE 清单")
    args = ap.parse_args(argv)

    try:
        snaps = [load_snapshot(Path(p)) for p in args.snapshot]
    except InputError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or datetime.now().strftime("%Y%m%dT%H%M%S")
    window = (args.window_from or None, args.window_to or None)

    se_details = None
    if args.enrich_se:
        try:
            se_details = enrich_se_details(snaps, out_dir, args.max_http, args.sleep,
                                           out_dir / "se_details.json",
                                           args.env_file or None)
        except InputError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
    elif args.reuse_se_details:
        p = out_dir / "se_details.json"
        if p.is_file():
            se_details = json.loads(p.read_text(encoding="utf-8"))
        else:
            print(f"⚠ 没有可复用的 {p}；SE line 证据按缺失处理", file=sys.stderr)

    details = (se_details or {}).get("by_se") or {}
    scopes = [build_scope(s, {"by_se": details}, window, args.date_basis) for s in snaps]

    probe = None
    if args.probe_mismatch_wos > 0 and args.enrich_se:
        try:
            probe = probe_wo_mismatches(scopes, out_dir, args.probe_mismatch_wos,
                                        args.sleep, args.env_file or None)
        except InputError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2

    manifest = build_manifest(scopes, window, args.date_basis, se_details, probe, run_id)
    manifest["stable_sha256"] = stable_hash(manifest)

    # 逐行去向
    with open(out_dir / "line_dispositions.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for sc in scopes:
            for r in sc["rows"]:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    (out_dir / "association_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "snapshots_manifest.json").write_text(json.dumps(
        {"schema": "dn_wo_jc_se_inputs/1",
         "snapshots": [sc["snapshot"] for sc in scopes]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    # 运行日志
    total_rows = sum(sum(sc["counts"].values()) for sc in scopes)
    lines = [f"run_id={run_id}", f"scopes={len(scopes)}",
             f"audit_ok={manifest['audit_ok']}",
             f"evidence_complete={manifest['evidence_complete']}",
             f"rows={total_rows}"]
    for sc in scopes:
        lines.append(f"{sc['scope']}: rows={sum(sc['counts'].values())} "
                     f"audit={sc['checks']['C1_so_dn']}")
    (out_dir / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"OK: {out_dir}")
    print(f"  scopes={len(scopes)} rows={total_rows} "
          f"audit_ok={manifest['audit_ok']} evidence_complete={manifest['evidence_complete']}")
    for sc in scopes:
        print(f"  - {sc['scope']}: {json.dumps(sc['counts'], ensure_ascii=False)}")
        print(f"    C1={json.dumps(sc['checks']['C1_so_dn'], ensure_ascii=False)}")
        print(f"    C2={json.dumps(sc['checks']['C2_wo_se'], ensure_ascii=False)} "
              f"C3={json.dumps(sc['checks']['C3_se_internal'], ensure_ascii=False)}")
    print(f"  stable_sha256={manifest['stable_sha256']}")
    budget_ok = not (se_details and se_details["log"]["budget_exceeded"])
    if not (manifest["audit_ok"] and manifest["evidence_complete"] and budget_ok):
        print(f"  status=partial audit_ok={manifest['audit_ok']} "
              f"evidence_complete={manifest['evidence_complete']} "
              f"budget_ok={budget_ok}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
