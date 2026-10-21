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
     **逐行全精度**判定；聚合只作展示，任何一行不过即 C1 不通过（不允许正负抵消）。
  C2 WO produced_qty == 该 WO 已提交 Manufacture SE 完工行数量（需 line 级证据）
     任一已提交 SE 未解决（缺证据/元数据漂移/不一致）时该 WO 不计 conserved，
     C2 只出 known_subtotal，不出完整总数。
  C3 单个 SE 的 finished 行合计 == SE.finished_qty
  C4 行账：**原始输入行数** == 逐行去向数（含 rejected/orphan 行），
     且业务键与派生子键都唯一。
  JC 不是守恒账：工序卡按工序批量开卡、返工卡会重复累加，只作进度证据。

UOM 契约：任何数量聚合都按 UOM 分区；UOM 缺失/未知一律 unverified，不进入合计。
退货符号契约：is_return=1 的行取 `abs(qty)`（源可能是 -2 或 2，结果都按 2 扣减），
非退货行负数量视为 invalid；不做二次取反。
HTTP 契约：`--max-http` 是**请求级**总预算，跨 SE 明细、探针翻页与重试共享；
预算耗尽必须显式记录并让运行返回 partial。
校验和契约：`payload_sha256` 在写入 `stable_sha256` **之后**对最终 manifest 计算。

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

import requests

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
PRODUCER = {"name": "g1b_dn_wo_jc_se.py", "version": "1.1.0"}
EPS = 1e-6
ROWTYPES = ("so_line", "dn_line", "wo", "jc_operation", "se", "se_line")
SE_DETAIL_SCHEMA = "dn_wo_jc_se_se_details/1"
WO_PROBE_SCHEMA = "dn_wo_jc_se_wo_probe/1"
SE_ENTRY_TYPE = "Manufacture"


class InputError(RuntimeError):
    """输入/契约错误：必须 exit 2，不能产出“成功”证据。"""


class BudgetExhausted(RuntimeError):
    """请求级 HTTP 预算耗尽；调用方必须显式记录 partial。"""


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


def jc_operation_payloads(ops: Any) -> tuple[dict[str, float], list[dict]]:
    """校验 JC 组的工序 payload，返回 (合法工序 -> sum_qty, 非法项列表)。

    合法工序必须同时满足：值为对象、`sum_qty` 是有限数值。null/字符串/数组/
    空对象/缺 sum_qty 一律非法。调用方必须落显式 invalid 披露行，且整组不计
    matched、不出 progress——工序卡只作进度证据，不参与数量守恒。
    """
    qty: dict[str, float] = {}
    bad: list[dict] = []
    if not isinstance(ops, dict):
        return qty, bad
    for op, v in ops.items():
        if not isinstance(v, dict):
            bad.append({"operation": op,
                        "reason_code": "jc_operation_payload_invalid",
                        "detail": f"工序 payload 不是对象: {type(v).__name__}"})
            continue
        q = num(v.get("sum_qty"))
        if q is None:
            bad.append({"operation": op,
                        "reason_code": "jc_operation_sum_qty_invalid",
                        "detail": "工序 payload 为空对象" if not v else
                                  f"sum_qty 非法: {v.get('sum_qty')!r}"})
            continue
        qty[op] = q
    return qty, bad


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


def uom_known(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def uom_key(v: Any) -> str:
    return v.strip() if uom_known(v) else "unknown"


def parse_ts(v: Any) -> datetime | None:
    """解析 ISO 时间；无时区按本机时区解释（快照 generated_at 是本地时间）。"""
    if not isinstance(v, str) or len(v) < 10:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone() if dt.tzinfo is None else dt


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
    for k in ("so_rows", "dn_rows", "wos"):
        if not isinstance(data.get(k), list):
            raise InputError(f"快照 {k} 必须是数组: {path}")
    if data.get("se_rows") is not None and not isinstance(data.get("se_rows"), list):
        raise InputError(f"快照 se_rows 必须是数组或 null: {path}")
    if not isinstance(data.get("jc_summary") or {}, dict):
        raise InputError(f"快照 jc_summary 必须是对象: {path}")
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
def se_detail_for(se_row: dict, by_se: dict, snap_generated_at: Any) -> dict:
    """解析 SE 行明细并**校验父元数据**；不一致一律不进入守恒。

    来源二选一：快照内联 `lines`（抽取器已按 stock_entry_type=Manufacture 过滤）或
    本地缓存的按单据 GET 明细。缓存明细必须通过 docstatus / work_order / entry type /
    posting_date 一致性与取回时间不早于快照这两组校验。
    """
    name = se_row.get("se")
    if isinstance(se_row.get("lines"), list):
        return {"lines": se_row["lines"], "source": "snapshot", "problem": None,
                "problems": [], "entry_type": "implied_manufacture"}
    det = by_se.get(name) if isinstance(by_se, dict) else None
    if not isinstance(det, dict):
        return {"lines": None, "source": "absent", "problem": "se_detail_absent",
                "problems": ["se_detail_absent"], "entry_type": None}
    problems: list[str] = []
    if det.get("se") not in (None, name):
        problems.append("se_detail_name_mismatch")
    if not det.get("ok"):
        problems.append("se_detail_fetch_failed")
    dd, sd = docstatus(det.get("docstatus")), docstatus(se_row.get("docstatus"))
    if dd is None:
        problems.append("se_detail_docstatus_unknown")
    elif sd is not None and sd != dd:
        problems.append("se_detail_docstatus_drift")
    dw, sw = det.get("work_order") or "", se_row.get("work_order") or ""
    if not dw:
        problems.append("se_detail_work_order_missing")
    elif sw and sw != dw:
        problems.append("se_detail_work_order_drift")
    etype = det.get("stock_entry_type")
    if etype != SE_ENTRY_TYPE:
        problems.append("se_detail_entry_type_invalid")
    spd, dpd = date_part(se_row.get("posting_date")), date_part(det.get("posting_date"))
    if spd is None or dpd is None:
        problems.append("se_detail_posting_date_missing")
    elif spd != dpd:
        problems.append("se_detail_posting_date_drift")
    ft, gt = aware(parse_ts(det.get("fetched_at"))), aware(parse_ts(snap_generated_at))
    if ft is None:
        problems.append("se_detail_fetched_at_missing")
    elif gt is not None and ft < gt:
        problems.append("se_detail_predates_snapshot")
    lines = det.get("lines")
    if not isinstance(lines, list):
        problems.append("se_detail_lines_missing")
    return {"lines": lines if not problems else None, "source": "en_get",
            "problem": problems[0] if problems else None, "problems": problems,
            "entry_type": etype}


def build_scope(snap: dict, se_details: dict, window: tuple[str | None, str | None],
                basis: str) -> dict:
    """单快照：建索引、连边、逐行去向、守恒检查。

    C4 的口径是**原始输入行**（含非对象行）逐行有去向：非对象行落 rejected，
    快照外 WO 的 JC 组落 orphan，不静默丢弃。
    """
    scope = snap["_scope"]
    raw_inputs = {
        "so_line": list(snap["so_rows"]),
        "dn_line": list(snap["dn_rows"]),
        "wo": list(snap["wos"]),
        "se": list(snap.get("se_rows") or []),
    }
    so_rows = [r for r in raw_inputs["so_line"] if isinstance(r, dict)]
    dn_rows = [r for r in raw_inputs["dn_line"] if isinstance(r, dict)]
    wos = [r for r in raw_inputs["wo"] if isinstance(r, dict)]
    se_rows = [r for r in raw_inputs["se"] if isinstance(r, dict)]
    jc_map = snap.get("jc_summary") or {}
    as_of = date_part(snap.get("generated_at"))
    se_query_error = snap.get("se_query_error") or None
    by_se = (se_details or {}).get("by_se") or {}

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
    rejected: list[dict] = []
    child_dup: list[dict] = []

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

    # ── 0. 非对象原始行：保留为 rejected，不静默丢弃 ──
    for t, vals in raw_inputs.items():
        for i, raw in enumerate(vals):
            if isinstance(raw, dict):
                continue
            rec = {"scope": scope, "row_type": t, "row_key": f"raw::{i}",
                   "link": {"raw_index": i, "raw_type": type(raw).__name__},
                   "qty": {}, "uom": None, "in_window": None, "dates": {},
                   "disposition": "rejected", "reason_code": "row_not_object",
                   "reason_detail": f"{type(raw).__name__}"}
            out_rows.append(rec)
            rejected.append(rec)

    # ── 1. DN 行：先归属到 SO 行（精确 so_line_id；**仅当引用缺失**才按 so+item 唯一匹配）──
    dn_net: dict[tuple, float] = defaultdict(float)     # (so, line_id) -> 已提交净量
    dn_ret: dict[tuple, float] = defaultdict(float)
    dn_draft: dict[tuple, float] = defaultdict(float)
    dn_by_line: dict[tuple, list[dict]] = defaultdict(list)
    dn_unverified: dict[tuple, int] = defaultdict(int)
    dn_item_bad: dict[tuple, int] = defaultdict(int)
    dn_unlinked: list[dict] = []
    for d in dn_rows:
        so, sl = d.get("so"), d.get("so_line_id")
        key = None
        link_mode = None
        unlink_code = "dn_unlinked_so_line"
        if so and sl:
            if (so, sl) in so_idx:
                key, link_mode = (so, sl), "so_line_id"
            else:
                unlink_code = "dn_so_line_ref_not_found"
        elif so:
            if not d.get("item_code"):
                unlink_code = "dn_item_missing"
            else:
                cands = [r for r in so_by_so.get(so, [])
                         if r.get("item_code") == d.get("item_code") and r.get("line_id")]
                if len(cands) == 1:
                    key = (cands[0].get("so"), cands[0].get("line_id"))
                    link_mode = "so_item_unique"
                elif len(cands) > 1:
                    unlink_code = "dn_item_ambiguous"
                else:
                    unlink_code = "dn_item_not_found"
        else:
            unlink_code = "dn_no_so_ref"
        ds = docstatus(d.get("dn_docstatus"))
        is_ret = flag01(d.get("is_return"))
        q_raw = num(d.get("qty"))
        # 退货符号归一：is_return=1 一律取绝对值；非退货负数视为非法。
        q: float | None = q_raw
        sign_normalized = False
        if q_raw is not None and is_ret == 1 and q_raw < 0:
            q, sign_normalized = -q_raw, True
        d_date = date_part(d.get("dn_date"))
        in_win = in_window(d_date, window)
        row_link = {"so": so, "so_line_id": sl, "dn": d.get("dn"),
                    "dn_line_id": d.get("dn_line_id")}
        if key is None:
            dn_unlinked.append(d)
            emit(scope, "dn_line", f"{d.get('dn')}::{d.get('dn_line_id')}",
                 row_link, {"qty": r2(q), "qty_raw": r2(q_raw)}, d.get("uom"),
                 "unlinked", unlink_code,
                 "DN 行无法精确归属到本快照 SO 行"
                 "（引用缺失时只允许 so+item 唯一匹配）",
                 in_win, {"dn_date": d.get("dn_date")})
            continue
        dn_by_line[key].append(d)
        line = so_idx[key]
        line_uom = line.get("uom")
        dn_uom = d.get("uom")
        code, detail = "", ""
        if q is None:
            code, detail = "dn_qty_invalid", "DN 行数量缺失/非有限数"
        elif is_ret is None:
            code, detail = "dn_return_flag_invalid", f"is_return 非 0/1: {d.get('is_return')!r}"
        elif is_ret == 0 and q < 0:
            code, detail = "dn_qty_invalid", "非退货行数量为负"
        elif not uom_known(dn_uom):
            code, detail = "dn_uom_missing", "DN 行 UOM 缺失"
        elif not uom_known(line_uom):
            code, detail = "dn_so_line_uom_missing", "SO 行 UOM 缺失"
        elif uom_key(dn_uom) != uom_key(line_uom):
            code, detail = "dn_uom_mismatch", f"DN {dn_uom} != SO {line_uom}"
        elif not d.get("item_code") or not line.get("item_code"):
            code, detail = "dn_item_unknown", "DN/SO 物料缺失，无法校验身份"
        elif d.get("item_code") != line.get("item_code"):
            code, detail = "dn_item_mismatch", \
                f"DN item={d.get('item_code')} != SO item={line.get('item_code')}"
        if not code:
            if ds == 1:
                if is_ret:
                    dn_ret[key] += q
                    code = "dn_return_submitted"
                else:
                    dn_net[key] += q
                    code = "dn_submitted"
                disp = "linked"
            elif ds == 0:
                dn_draft[key] += q
                disp, code = "excluded", "dn_draft"
            elif ds == 2:
                disp, code = "excluded", "dn_cancelled"
            else:
                disp, code = "unverified", "dn_docstatus_invalid"
                detail = f"docstatus={d.get('dn_docstatus')!r}"
        else:
            disp = "mismatch" if code == "dn_item_mismatch" else "unverified"
        if disp == "mismatch":
            dn_item_bad[key] += 1
        elif disp == "unverified":
            dn_unverified[key] += 1
        emit(scope, "dn_line", f"{d.get('dn')}::{d.get('dn_line_id')}",
             dict(row_link, so_line_key=f"{key[0]}::{key[1]}", link_mode=link_mode),
             {"qty": r2(q), "qty_exact": q, "qty_raw": r2(q_raw),
              "sign_normalized": sign_normalized},
             dn_uom, disp, code or "dn_linked", detail, in_win,
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

    # ── 3. SE：归属 WO；行级同单位校验 + 父元数据校验 + 覆盖完整性 ──
    # (WO, UOM) -> 已守恒 finished 行合计：跨 UOM **永不**相加
    se_finished_by_wo_uom: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float))
    se_submitted_by_wo: Counter = Counter()
    se_blocked_wo: set[str] = set()   # 有已提交但未解决的 SE 的 WO
    se_rows_out: list[dict] = []
    se_line_keys: dict[str, set] = defaultdict(set)
    se_coverage: dict[str, Any] = {
        "query_error": se_query_error, "submitted": 0, "conserved": 0,
        "draft": 0, "cancelled": 0, "out_of_snapshot": 0,
        "unresolved": [], "wo_unresolved": [], "complete": False,
    }

    for s in se_rows:
        name = s.get("se")
        wo = s.get("work_order") or ""
        ds = docstatus(s.get("docstatus"))
        s_date = date_part(s.get("posting_date"))
        in_win = in_window(s_date, window)
        resolved = se_detail_for(s, by_se, snap.get("generated_at"))
        lines = resolved["lines"]
        sources = resolved["source"]
        finished_lines = s.get("finished_lines")
        wo_item = (wo_idx.get(wo) or {}).get("production_item")
        wo_known = wo in wo_idx
        # 行级：同 UOM + 身份 + 子键唯一
        line_rows = []
        for i, ln in enumerate(lines or []):
            if not isinstance(ln, dict):
                rec = {"scope": scope, "row_type": "se_line",
                       "row_key": f"{name}::raw::{i}",
                       "link": {"se": name, "se_line_id": None, "work_order": wo or None},
                       "qty": {}, "uom": None, "in_window": in_win,
                       "is_finished": None, "dates": {"posting_date": s.get("posting_date")},
                       "disposition": "rejected", "reason_code": "se_line_row_not_object",
                       "reason_detail": f"{type(ln).__name__}"}
                se_rows_out.append(rec)
                line_rows.append(rec)
                rejected.append(rec)
                continue
            lid = ln.get("line")
            has_lid = lid not in (None, "")
            q = num(ln.get("qty"))
            uom, suom = ln.get("uom"), ln.get("stock_uom")
            is_fin = flag01(ln.get("is_finished_item"))
            if not has_lid:
                code, disp = "se_line_key_missing", "unverified"
            elif lid in se_line_keys[name]:
                code, disp = "se_line_duplicate_key", "rejected"
            else:
                se_line_keys[name].add(lid)
                if is_fin == 1:
                    if not wo_known:
                        code, disp = "se_line_parent_wo_out_of_snapshot", "unverified"
                    elif not uom_known(uom) or not uom_known(suom):
                        code, disp = "se_line_finished_uom_missing", "unverified"
                    elif uom_key(uom) != uom_key(suom):
                        code, disp = "se_line_finished_uom_mismatch", "unverified"
                    elif not wo_item:
                        code, disp = "se_line_wo_item_unknown", "unverified"
                    elif ln.get("item_code") != wo_item:
                        code, disp = "se_line_item_mismatch", "mismatch"
                    elif q is None or q < 0:
                        code, disp = "se_line_qty_invalid", "unverified"
                    else:
                        code, disp = "se_line_finished_same_unit", "conserved"
                elif is_fin == 0:
                    code, disp = "se_line_not_finished", "excluded"
                else:
                    code, disp = "se_line_finished_flag_invalid", "unverified"
            key_id = str(lid) if has_lid else f"#{i}"
            rec = {"scope": scope, "row_type": "se_line",
                   "row_key": f"{name}::{key_id}",
                   "link": {"se": name, "se_line_id": lid, "work_order": wo or None},
                   "qty": {"qty": q}, "uom": uom or None, "in_window": in_win,
                   "is_finished": is_fin,
                   "dates": {"posting_date": s.get("posting_date")},
                   "disposition": disp, "reason_code": code,
                   "reason_detail": "" if disp == "conserved" else
                   f"uom={uom} stock_uom={suom} item={ln.get('item_code')} wo_item={wo_item}"}
            se_rows_out.append(rec)
            line_rows.append(rec)
            if disp == "rejected":
                rejected.append({"scope": scope, "row_type": "se_line",
                                 "row_key": rec["row_key"],
                                 "link": rec["link"], "qty": rec["qty"], "uom": rec["uom"],
                                 "in_window": in_win, "dates": rec["dates"],
                                 "disposition": disp, "reason_code": code,
                                 "reason_detail": rec["reason_detail"]})
        # 未解决的子行（非法 flag / 缺键 / 重复键 / 非对象 / 物料不符）必须向上传播：
        # 只要有一个子行没有明确为 conserved/excluded，父 SE 就不能 conserved。
        line_blocking = [r for r in line_rows
                         if r["disposition"] in ("unverified", "rejected", "mismatch")]
        fin_rows = [r for r in line_rows if r.get("is_finished") == 1]
        fin_bad_item = any(r["reason_code"] == "se_line_item_mismatch" for r in fin_rows)
        fin_ok_rows = [r for r in fin_rows
                       if r["reason_code"] == "se_line_finished_same_unit"]
        fin_ok = bool(fin_rows) and len(fin_ok_rows) == len(fin_rows)
        fin_uoms = {uom_key(r["uom"]) for r in fin_ok_rows}
        mixed_uom = len(fin_uoms) > 1
        fin_qty = (sum(float(r["qty"]["qty"]) for r in fin_ok_rows)
                   if fin_ok and not mixed_uom and not line_blocking else None)
        child_codes = ",".join(sorted({r["reason_code"] for r in line_blocking}))
        # 文档级去向
        if ds == 2:
            disp, code = "excluded", "se_cancelled"
        elif ds is None:
            disp, code = "unverified", "se_docstatus_invalid"
        elif ds == 0:
            disp, code = "excluded", "se_docstatus_0"
        elif not wo:
            disp, code = "unlinked", "se_unlinked_work_order"
        elif not wo_known:
            disp, code = "unlinked", "se_work_order_out_of_snapshot"
        elif resolved["problem"]:
            disp, code = "unverified", resolved["problem"]
        elif lines is None:
            disp, code = "unverified", "se_detail_absent"
        elif not fin_rows:
            disp, code = "unverified", "se_no_finished_line"
        elif fin_bad_item:
            disp, code = "mismatch", "se_finished_item_mismatch"
        elif line_blocking:
            disp, code = "unverified", "se_line_child_unresolved"
        elif mixed_uom:
            disp, code = "unverified", "se_finished_uom_mixed"
        elif fin_qty is None:
            disp, code = "unverified", "se_finished_lines_unverified"
        elif not close(num(s.get("finished_qty")), fin_qty):
            disp, code = "mismatch", "se_internal_sum_mismatch"
        else:
            disp, code = "conserved", "se_finished_conserved"
        se_uom = next(iter(fin_uoms)) if len(fin_uoms) == 1 else None
        if disp == "conserved":
            se_finished_by_wo_uom[wo][se_uom] += fin_qty
        # 覆盖：每个已提交 SE 必须有明确结论；未解决的要传播到 WO/C2/证据状态
        if ds == 1:
            se_coverage["submitted"] += 1
            se_submitted_by_wo[wo] += 1
            if not wo_known:
                se_coverage["out_of_snapshot"] += 1
            if disp == "conserved":
                se_coverage["conserved"] += 1
            else:
                se_coverage["unresolved"].append(
                    {"se": name, "work_order": wo or None,
                     "disposition": disp, "reason_code": code})
                if wo:
                    se_blocked_wo.add(wo)
        elif ds == 0:
            se_coverage["draft"] += 1
        elif ds == 2:
            se_coverage["cancelled"] += 1
        emit(scope, "se", f"{name}", {"se": name, "work_order": wo or None,
                                      "wo_key": wo or None, "detail_source": sources,
                                      "detail_problems": resolved["problems"],
                                      "entry_type": resolved["entry_type"]},
             {"finished_qty": r2(num(s.get("finished_qty"))),
              "finished_lines_sum": r2(fin_qty),
              "finished_lines_sum_exact": fin_qty,
              "declared_finished_lines": finished_lines},
             se_uom, disp, code,
             "" if disp == "conserved" else
             f"lines={0 if lines is None else len(lines)} "
             f"problems={','.join(resolved['problems']) or '-'}"
             + (f" child_codes={child_codes}" if child_codes else ""),
             in_win, {"posting_date": s.get("posting_date")})
    out_rows.extend(se_rows_out)
    # 同一 WO 的已守恒 SE 若落在不同 UOM，只保留分桶，不给跨单位总量；
    # 该 WO 进入未解决清单，C2/C1 完整性与 audit/evidence 一律降级。
    for wo_name, buckets in sorted(se_finished_by_wo_uom.items()):
        if len(buckets) > 1:
            se_coverage["wo_unresolved"].append({
                "work_order": wo_name, "reason_code": "wo_uom_mixed",
                "se_finished_by_uom": {u: r2(q) for u, q in sorted(buckets.items())}})
    se_coverage["complete"] = bool(se_query_error is None
                                   and not se_coverage["unresolved"]
                                   and not se_coverage["wo_unresolved"])

    # ── 4. WO 行：produced_qty vs SE 完工量；JC 进度证据 ──
    wo_rows_out: list[dict] = []
    wo_summary: dict[str, dict] = {}
    jc_seen: set = set()
    for w in wos:
        name = w.get("name")
        info = wo_link[name]
        ds = docstatus(w.get("docstatus"))
        q, prod = info["qty"], info["produced_qty"]
        buckets = dict(se_finished_by_wo_uom.get(name) or {})
        uoms = set(buckets)
        uom = next(iter(uoms)) if len(uoms) == 1 else None
        mixed_uom = len(uoms) > 1
        se_q = buckets[uom] if uom is not None else None
        link_status, link_code = info["disposition"], info["reason_code"]
        codes = []
        wo_status = str(w.get("status") or "")
        not_started = ((prod is None or prod == 0) and se_submitted_by_wo.get(name, 0) == 0
                       and wo_status in ("Not Started", "Draft", "Pending", "Open"))
        if ds == 2:
            disp, code = "excluded", "wo_cancelled"
        elif ds is None:
            disp, code = "unverified", "wo_docstatus_invalid"
        elif not_started:
            disp, code = "open", "wo_not_started"
        elif se_query_error:
            disp, code = "unverified", "wo_se_query_incomplete"
        elif name in se_blocked_wo:
            disp, code = "unverified", "wo_se_incomplete"
        elif mixed_uom:
            disp, code = "unverified", "wo_uom_mixed"
        elif uom is None:
            disp, code = "unverified", "wo_uom_unresolved"
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
        if mixed_uom:
            codes.append("wo_se_finished_uom_mixed")
        raw_jc = jc_map.get(name)
        jc = raw_jc if isinstance(raw_jc, dict) else {}
        jc_seen.add(name)
        raw_ops = jc.get("operations")
        ops_ok = isinstance(raw_ops, dict)
        ops = raw_ops if ops_ok else {}
        numeric, op_bad = jc_operation_payloads(ops)
        max_op = max(numeric, key=numeric.get) if numeric else None
        jc_flags = []
        if name not in jc_map:
            jc_flags.append("jc_missing")
        elif not isinstance(raw_jc, dict):
            jc_flags.append("jc_group_invalid")
        elif not ops_ok:
            jc_flags.append("jc_operations_invalid")
        elif not ops:
            jc_flags.append("jc_no_operations")
        elif op_bad:
            jc_flags.append("jc_operation_payload_invalid")
        elif not numeric:
            jc_flags.append("jc_zero_completed")
        elif jc.get("last_operation") not in numeric or (
                numeric[jc["last_operation"]] < numeric[max_op] - EPS):
            jc_flags.append("jc_routing_final_op_not_completion")
        wo_summary[name] = {
            "qty": r2(q), "produced_qty": r2(prod), "se_finished_qty": r2(se_q),
            "se_finished_qty_exact": se_q,
            "se_finished_by_uom": {u: r2(v) for u, v in sorted(buckets.items())},
            "se_finished_uom_mixed": mixed_uom,
            "uom": uom, "disposition": disp, "reason_code": code,
            "link_status": link_status, "link_reason_code": link_code,
            "jc_cards": jc.get("cards"),
            "jc_ops": len(ops),
            "jc_max_op": max_op, "jc_max_qty": r2(numeric.get(max_op)),
            "jc_last_op": jc.get("last_operation"),
            "jc_last_op_qty": r2(numeric.get(jc.get("last_operation"))),
            "jc_flags": jc_flags,
        }
        rec = {"scope": scope, "row_type": "wo", "row_key": name,
               "link": dict(info["link"]),
               "qty": {"qty": r2(q), "produced_qty": r2(prod),
                       "se_finished_qty": r2(se_q),
                       "se_finished_by_uom": {u: r2(v) for u, v in sorted(buckets.items())},
                       "qty_exact": q, "produced_qty_exact": prod,
                       "se_finished_qty_exact": se_q,
                       "produced_pending": r2(prod - se_q) if prod is not None and se_q is not None else None},
               "uom": uom, "in_window": None,
               "dates": {"planned_start": w.get("planned_start_date"),
                         "planned_end": w.get("planned_end_date")},
               "disposition": disp, "reason_code": code,
               "link_status": link_status, "link_reason_code": link_code,
               "reason_detail": ";".join(codes + jc_flags)}
        wo_rows_out.append(rec)
        # JC 工序行（每工序一条；只作进度证据）。组内任一工序 payload 非法 →
        # 整组不出 progress，改由下方 jc_stats 分支落显式 invalid 披露行。
        if not op_bad:
            for op, v in ops.items():
                emit(scope, "jc_operation", f"{name}::{op}",
                     {"work_order": name, "operation": op,
                      "jc_ids": (v or {}).get("jc_ids") if isinstance(v, dict) else [],
                      "so_line_key": info["link"].get("so_line_key")},
                     {"sum_qty": r2(num((v or {}).get("sum_qty"))) if isinstance(v, dict) else None,
                      "cards": (v or {}).get("cards") if isinstance(v, dict) else None},
                     None, "progress", "jc_progress_evidence_only",
                     "工序卡按批量/返工重复开卡，不作数量守恒",
                     None, {})
    out_rows.extend(wo_rows_out)

    # 快照外 WO 的 JC 组：保留为 orphan；匹配到 WO 但工序明细非法的组：
    # 必须落**显式 invalid 披露行**，不能静默计入 matched。工序 payload 也逐个
    # 校验（null/字符串/空对象/非法 sum_qty 都非法），整组 matched=0、无 progress。
    jc_stats = {"read": len(jc_map), "matched": 0, "orphan": 0, "invalid": 0}
    for jc_name, jc in jc_map.items():
        raw_ops = jc.get("operations") if isinstance(jc, dict) else None
        if jc_name in jc_seen and jc_name in wo_idx:
            if isinstance(jc, dict) and isinstance(raw_ops, dict) and raw_ops:
                _op_qty, op_bad = jc_operation_payloads(raw_ops)
                if not op_bad:
                    jc_stats["matched"] += 1
                    continue
                jc_stats["invalid"] += 1
                for b in op_bad:
                    op = b["operation"]
                    v = raw_ops.get(op)
                    emit(scope, "jc_operation", f"{jc_name}::{op}",
                         {"work_order": jc_name, "operation": op, "jc_ids": []},
                         {"sum_qty": None,
                          "cards": v.get("cards") if isinstance(v, dict) else None},
                         None, "invalid", b["reason_code"], b["detail"], None, {})
                continue
            jc_stats["invalid"] += 1
            if not isinstance(jc, dict):
                reason = "jc_group_invalid"
                detail = f"JC 组不是对象: {type(jc).__name__}"
            elif not isinstance(raw_ops, dict):
                reason = "jc_operations_invalid"
                detail = f"JC operations 不是对象: {type(raw_ops).__name__}"
            else:
                reason = "jc_no_operations"
                detail = "JC 组没有任何可用的工序明细"
            emit(scope, "jc_operation", f"{jc_name}::<invalid_operations>",
                 {"work_order": jc_name, "operation": None, "jc_ids": []},
                 {"sum_qty": None,
                  "cards": jc.get("cards") if isinstance(jc, dict) else None},
                 None, "invalid", reason, detail, None, {})
            continue
        if not isinstance(jc, dict):
            jc_stats["invalid"] += 1
            emit(scope, "jc_operation", f"{jc_name}::<invalid>",
                 {"work_order": jc_name, "operation": None, "jc_ids": []},
                 {}, None, "orphan", "jc_group_invalid",
                 f"JC 组不是对象: {type(jc).__name__}", None, {})
            continue
        jc_stats["orphan"] += 1
        ops = jc.get("operations") if isinstance(jc.get("operations"), dict) else {}
        if not ops:
            emit(scope, "jc_operation", f"{jc_name}::<no_operation>",
                 {"work_order": jc_name, "operation": None, "jc_ids": []},
                 {"sum_qty": None, "cards": jc.get("cards")},
                 None, "orphan",
                 "jc_group_invalid" if not isinstance(jc.get("operations"), dict)
                 else "jc_no_operations",
                 "JC 组没有任何可用的工序明细", None, {})
            continue
        for op, v in ops.items():
            emit(scope, "jc_operation", f"{jc_name}::{op}",
                 {"work_order": jc_name, "operation": op,
                  "jc_ids": (v or {}).get("jc_ids") if isinstance(v, dict) else []},
                 {"sum_qty": r2(num((v or {}).get("sum_qty"))) if isinstance(v, dict) else None,
                  "cards": (v or {}).get("cards") if isinstance(v, dict) else None},
                 None, "orphan", "jc_work_order_out_of_snapshot",
                 "JC 组指向的 WO 不在本快照内；只作进度证据", None, {})

    # ── 5. SO 行：delivered vs DN 净量；窗口与开单状态（逐行全精度）──
    so_out: list[dict] = []
    c1_lines: list[dict] = []
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
        dn_mismatch = dn_item_bad.get(key, 0)
        dn_incomplete = dn_unverified.get(key, 0)
        codes = []
        if ds == 2 or (r.get("so_status") or "") == "Cancelled":
            disp, code = "excluded", "so_line_voided"
        elif q is None or delivered is None:
            disp, code = "unverified", "so_line_qty_invalid"
        elif not uom_known(line_uom):
            disp, code = "unverified", "so_line_uom_missing"
        elif dn_mismatch:
            disp, code = "mismatch", "so_line_dn_item_mismatch"
        elif dn_incomplete:
            disp, code = "unverified", "so_line_dn_evidence_incomplete"
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
                       "dn_return": r2(dn_ret.get(key)), "dn_draft": r2(dn_draft.get(key)),
                       "qty_exact": q, "delivered_qty_exact": delivered,
                       "open_qty_exact": open_q, "dn_net_exact": net},
               "uom": line_uom or None, "in_window": in_win,
               "dates": {"delivery": r.get("so_delivery_date"),
                         "transaction": r.get("transaction_date")},
               "disposition": disp, "reason_code": code,
               "reason_detail": ";".join(codes)}
        so_out.append(rec)
        eligible = disp != "excluded"
        passed = True if disp == "conserved" else (False if disp == "mismatch" else None)
        c1_lines.append({
            "scope": scope, "so_line_key": f"{so}::{sl}", "row_key": f"{so}::{sl}",
            "uom": line_uom if uom_known(line_uom) else None,
            "delivered": delivered, "dn_net": net,
            "delta": (delivered - net) if delivered is not None else None,
            "eligible": eligible, "pass": passed, "reason_code": code,
        })
    out_rows = so_out + out_rows   # 输出顺序：SO 行锚点在前

    # 行键全局唯一性（含派生的 se_line / jc_operation）；重复即 audit 失败
    seen_keys: set[tuple[str, str]] = set()
    for r in out_rows:
        k = (r["row_type"], str(r["row_key"]))
        if k in seen_keys:
            child_dup.append({"label": r["row_type"], "key": str(r["row_key"]),
                              "error": "duplicate_row_key"})
        seen_keys.add(k)

    # ── 守恒检查 ──
    checks = conservation_checks(scope, so_out, out_rows, wo_summary, c1_lines,
                                 raw_inputs, child_dup, rejected, jc_stats)
    checks["C2_wo_se"]["complete"] = bool(se_coverage["complete"])
    counts = Counter(r["row_type"] for r in out_rows)
    disp_counts = Counter(f"{r['row_type']}:{r['disposition']}" for r in out_rows)
    link_counts = Counter(f"{r['row_type']}:{r.get('link_status')}" for r in out_rows
                          if r.get("link_status"))
    # 关联覆盖：工单量按关联状态 + UOM 分区（UOM 来自链接 SO 行；无 SO 记 unknown）
    wo_by_link, wo_qty_by_link_uom = Counter(), defaultdict(lambda: defaultdict(float))
    for r in out_rows:
        if r["row_type"] != "wo":
            continue
        k = "linked" if r.get("link_status") == "linked" else (r.get("link_reason_code") or "?")
        wo_by_link[k] += 1
        u = r.get("link", {}).get("so_line_uom")
        wo_qty_by_link_uom[k][uom_key(u)] += r["qty"]["qty"] or 0
    so_with_wo = [r for r in so_out if r["link"].get("work_orders")]
    so_qty_uom: dict[str, dict] = defaultdict(lambda: {"lines": 0, "total": 0.0,
                                                       "with_work_order": 0.0,
                                                       "lines_with_work_order": 0})
    so_uom_unknown = 0
    for r in so_out:
        u = r.get("uom")
        if not uom_known(u):
            so_uom_unknown += 1
            continue
        b = so_qty_uom[u]
        b["lines"] += 1
        b["total"] += r["qty"]["qty_exact"] or 0.0
        if r["link"].get("work_orders"):
            b["with_work_order"] += r["qty"]["qty_exact"] or 0.0
            b["lines_with_work_order"] += 1
    association = {
        "wo_by_link": dict(sorted(wo_by_link.items())),
        "wo_qty_by_link_uom": {k: dict(sorted(v.items()))
                               for k, v in sorted(wo_qty_by_link_uom.items())},
        "wo_qty_uom_basis": "linked SO line uom; unlinked work orders -> unknown",
        "so_lines": len(so_out),
        "so_lines_with_work_order": len(so_with_wo),
        "so_qty_by_uom": {u: {"lines": b["lines"],
                              "lines_with_work_order": b["lines_with_work_order"],
                              "total": b["total"],
                              "with_work_order": b["with_work_order"]}
                          for u, b in sorted(so_qty_uom.items())},
        "so_lines_uom_unknown": so_uom_unknown,
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
        "dup_keys": so_dup + dn_dup + wo_dup + se_dup + child_dup,
        "child_dup": child_dup,
        "rejected": [{"row_type": r["row_type"], "row_key": r["row_key"],
                      "reason_code": r["reason_code"]} for r in rejected],
        "inputs": {k: len(v) for k, v in raw_inputs.items()},
        "parsed_inputs": {"so_line": len(so_rows), "dn_line": len(dn_rows),
                          "wo": len(wos), "se": len(se_rows)},
        "se_coverage": se_coverage,
        "jc_stats": jc_stats,
        "c1_lines": c1_lines,
        "unlinked_dn": len(dn_unlinked),
        "se_unlinked": sum(1 for r in out_rows if r["row_type"] == "se"
                           and r["reason_code"].startswith("se_unlinked")),
    }


def conservation_checks(scope: str, so_out: list[dict], all_rows: list[dict],
                        wo_summary: dict, c1_lines: list[dict],
                        raw_inputs: dict, child_dup: list[dict],
                        rejected: list[dict], jc_stats: dict) -> dict:
    """C1 逐行全精度、C2 覆盖完整、C3 SE 内部、C4 原始行账；数量按 UOM 分区。"""
    # C1：先逐行判定（全精度，不四舍五入、不允许正负抵消），再按 UOM 分组展示
    unresolved: list[dict] = []
    per_uom: dict[str, dict] = defaultdict(
        lambda: {"lines": 0, "lines_pass": 0, "lines_fail": 0,
                 "so_delivered": 0.0, "dn_net": 0.0})
    lines_pass = lines_fail = lines_excluded = 0
    for ln in c1_lines:
        if not ln["eligible"]:
            lines_excluded += 1
            continue
        if ln["pass"] is None or not uom_known(ln["uom"]):
            unresolved.append({"so_line_key": ln["so_line_key"],
                               "reason_code": ln["reason_code"]})
            continue
        b = per_uom[ln["uom"]]
        b["lines"] += 1
        b["so_delivered"] += ln["delivered"] or 0.0
        b["dn_net"] += ln["dn_net"] or 0.0
        if ln["pass"]:
            b["lines_pass"] += 1
            lines_pass += 1
        else:
            b["lines_fail"] += 1
            lines_fail += 1
    c1_out = []
    for u, b in sorted(per_uom.items()):
        c1_out.append({
            "uom": u, "lines": b["lines"],
            "lines_pass": b["lines_pass"], "lines_fail": b["lines_fail"],
            "so_delivered": b["so_delivered"], "dn_net": b["dn_net"],
            "delta": b["so_delivered"] - b["dn_net"],
            # 聚合 pass 只是“该 UOM 下每一行都过”的同义表达；不参与抵消
            "pass": b["lines_fail"] == 0,
        })
    c1 = {"pass": lines_fail == 0 and not unresolved,
          "lines_total": len(c1_lines),
          "lines_pass": lines_pass, "lines_fail": lines_fail,
          "lines_excluded": lines_excluded,
          "lines_unresolved": len(unresolved),
          "unresolved": unresolved,
          "per_uom": c1_out,
          "precision": "per_line_full_precision",
          "note": "每行 delivered_qty == dn_net 全精度判定；per_uom 汇总仅作展示，"
                  "任一行为 false 即 C1 不通过"}

    # C2：WO produced_qty vs SE 完工量；complete 取决于 SE 覆盖，不取决于可见子集
    compared = [w for w in wo_summary.values() if w["disposition"] in ("conserved", "mismatch")]
    by_uom: dict[str, dict] = defaultdict(
        lambda: {"wo": 0, "compared": 0, "pass": 0, "mismatch": 0,
                 "open": 0, "unverified": 0, "excluded": 0})
    for w in wo_summary.values():
        b = by_uom[uom_key(w["uom"])]
        b["wo"] += 1
        d = w["disposition"]
        if d == "conserved":
            b["pass"] += 1
        elif d in ("mismatch", "open", "unverified", "excluded"):
            b[d] += 1
        if d in ("conserved", "mismatch"):
            b["compared"] += 1
    c2 = {"wo_total": len(wo_summary), "compared": len(compared),
          "pass": sum(1 for w in compared if w["disposition"] == "conserved"),
          "mismatch": sum(1 for w in compared if w["disposition"] == "mismatch"),
          "open": sum(1 for w in wo_summary.values() if w["disposition"] == "open"),
          "unverified": sum(1 for w in wo_summary.values()
                            if w["disposition"] not in ("conserved", "mismatch",
                                                        "excluded", "open")),
          "by_uom": {u: dict(b) for u, b in sorted(by_uom.items())},
          "known_subtotal": {
              "compared": len(compared),
              "pass": sum(1 for w in compared if w["disposition"] == "conserved"),
              "mismatch": sum(1 for w in compared if w["disposition"] == "mismatch")},
          "note": "only evaluated work orders are counted; UOM from the single "
                  "conserved SE finished-unit bucket; a work order whose conserved "
                  "SEs span multiple UOMs stays unverified and is never summed"}

    # C3：单 SE 内部行合计 == finished_qty
    se_rows = [r for r in all_rows if r["row_type"] == "se"]
    c3_counts = Counter(r["disposition"] for r in se_rows)
    c3 = {"se_total": len(se_rows),
          "evaluated": c3_counts.get("conserved", 0) + c3_counts.get("mismatch", 0),
          "pass": c3_counts.get("conserved", 0),
          "mismatch": c3_counts.get("mismatch", 0),
          "unverified": c3_counts.get("unverified", 0),
          "excluded": c3_counts.get("excluded", 0),
          "acceptance_rule": "mismatch == 0 and unverified == 0"}

    # C4：原始输入行 == 逐行去向（含 rejected / orphan）；业务键与子键唯一
    emitted = Counter(r["row_type"] for r in all_rows)
    read = {t: len(v) for t, v in raw_inputs.items()}
    row_match = {t: read[t] == emitted.get(t, 0) for t in read}
    rejected_counts = Counter(r["row_type"] for r in rejected)
    c4 = {
        "read": read,
        "emitted": dict(sorted(emitted.items())),
        "match": row_match,
        "all_match": all(row_match.values()),
        "rejected": dict(sorted(rejected_counts.items())),
        "duplicate_keys": child_dup,
        "unique_keys": not child_dup,
        "jc_groups": dict(jc_stats),
        "jc_operations_emitted": emitted.get("jc_operation", 0),
        "se_lines_emitted": emitted.get("se_line", 0),
        "note": "read 是原始输入行数（含非对象行）；非对象行落 rejected，"
                "快照外 WO 的 JC 组落 orphan，不静默丢弃",
    }
    return {"C1_so_dn": c1, "C1_lines": c1_lines, "C2_wo_se": c2,
            "C3_se_internal": c3, "C4_rows": c4}


# ── EN 有界只读：请求级预算 + SE 明细 + 异常 WO 探针 ─────
class HttpBudget:
    """请求级总预算：SE 明细、探针翻页、连接重试共用同一个计数器。"""

    def __init__(self, limit: int):
        self.limit = max(0, int(limit))
        self.used = 0
        self.exhausted = False
        self.by_kind: Counter = Counter()
        self.events: list[dict] = []

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def spend(self, kind: str, detail: str = "") -> None:
        if self.used >= self.limit:
            self.exhausted = True
            raise BudgetExhausted(f"HTTP budget {self.limit} exhausted ({kind})")
        self.used += 1
        self.by_kind[kind] += 1
        self.events.append({"n": self.used, "kind": kind, "detail": detail})

    def as_log(self) -> dict:
        return {"limit": self.limit, "used": self.used, "remaining": self.remaining,
                "by_kind": dict(sorted(self.by_kind.items())),
                "exhausted": self.exhausted,
                "events": self.events[:50],
                "events_truncated": len(self.events) > 50,
                "note": "request-level budget shared by enrichment, probe pages and retries"}


def budgeted_get_status(budget: HttpBudget, path: str, base_url: str, key: str,
                        secret: str, kind: str = "enrich", timeout: int = 60
                        ) -> tuple[int, dict]:
    """与 iss.api_get_status 同语义，但**每次尝试**都计入共享预算。"""
    url = f"{base_url}{path}"
    last: Exception | None = None
    for attempt in range(iss.MAX_RETRIES):
        budget.spend("retry" if attempt else kind, path[:120])
        try:
            resp = requests.get(url, headers=iss._auth_headers(key, secret), timeout=timeout)
            try:
                return resp.status_code, resp.json()
            except ValueError:
                return resp.status_code, {}
        except requests.RequestException as e:  # noqa: PERF203 - 重试要计数
            last = e
            if attempt < iss.MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
    print(f"  ✗ 请求失败 ({type(last).__name__}): {path[:120]}", file=sys.stderr)
    return 0, {}


def budgeted_get_single(budget: HttpBudget, resource: str, docname: str, base_url: str,
                        key: str, secret: str, kind: str = "probe") -> dict:
    path = "/api/resource/{}/{}".format(urllib.parse.quote(resource, safe=""),
                                        urllib.parse.quote(docname, safe=""))
    status, body = budgeted_get_status(budget, path, base_url, key, secret, kind)
    if status != 200:
        raise iss.QueryError(f"{resource}/{docname}: HTTP {status}")
    return (body or {}).get("data") or {}


def budgeted_paginated_get(budget: HttpBudget, resource: str, base_url: str, key: str,
                           secret: str, filters: list, fields: list,
                           page_size: int = 100, order_by: str = "name asc",
                           fallback_fields: list | None = None, kind: str = "probe",
                           label: str = "") -> dict:
    """翻页拉取；每页（以及 417 回退重取）各计 1 次请求。"""
    rows: list[dict] = []
    start = page = pages = 0
    while page < 200:
        path = iss._build_url(resource, filters, fields, start, page_size, order_by)
        status, body = budgeted_get_status(budget, path, base_url, key, secret, kind)
        pages += 1
        if status == 417 and fallback_fields and fields != fallback_fields:
            print(f"  ⚠ {label or resource}: 字段被拒 (417), 回退字段集 {fallback_fields}")
            rest = budgeted_paginated_get(budget, resource, base_url, key, secret, filters,
                                          fallback_fields, page_size, order_by, None,
                                          kind, label)
            rest["rows"] = rows + rest["rows"]
            rest["pages"] += pages
            return rest
        if status != 200:
            raise iss.QueryError(f"{label or resource}: HTTP {status} {str(body)[:140]}")
        data = body.get("data", []) or []
        if not data:
            break
        rows.extend(data)
        if len(data) < page_size:
            break
        start += len(data)
        page += 1
    return {"rows": rows, "pages": pages, "complete": True}


def enrich_se_details(snaps: list[dict], out_dir: Path, budget: HttpBudget,
                      sleep_s: float, reuse_path: Path | None,
                      env_file: str | None = None) -> dict:
    """按单据名 GET 补齐 SE 行明细；只读、单并发、共享请求级预算。"""
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
    if existing and existing.get("schema") not in (None, SE_DETAIL_SCHEMA):
        raise InputError(f"SE 明细缓存 schema 不符: {existing.get('schema')!r}")
    by_se: dict = dict(existing.get("by_se") or {})
    need: list[str] = []
    for snap in snaps:
        for s in snap.get("se_rows") or []:
            if not isinstance(s, dict):
                continue
            n = s.get("se")
            if not n or isinstance(s.get("lines"), list):
                continue
            if n not in by_se and n not in need:
                need.append(n)
    prev_log = existing.get("log") or {}
    start_used = budget.used
    log = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "site": SITE, "requested": len(need), "requested_this_run": 0,
           "http": 0, "retries": 0, "ok": 0, "failed": 0,
           "status_codes": {}, "budget": budget.limit,
           "budget_used_before": start_used, "budget_exceeded": False,
           "not_requested": [],
           "kept_from_previous": len(by_se),
           "previous_requested": int(prev_log.get("requested") or 0)}
    for i, name in enumerate(need):
        path = "/api/resource/Stock%20Entry/" + urllib.parse.quote(str(name), safe="")
        before = dict(budget.by_kind)
        try:
            status, body = budgeted_get_status(budget, path, SITE, key, secret, "enrich")
        except BudgetExhausted:
            budget.exhausted = True
            log["budget_exceeded"] = True
            log["not_requested"] = need[i:]
            break
        log["requested_this_run"] += 1
        log["retries"] += (budget.by_kind.get("retry", 0)
                           - before.get("retry", 0))
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
    log["http"] = budget.used - start_used
    log["budget_used_after"] = budget.used
    log["budget_exhausted"] = budget.exhausted
    log["detail_records"] = len(by_se)
    log["detail_records_ok"] = sum(1 for v in by_se.values() if v.get("ok"))
    stamps = sorted(v.get("fetched_at") for v in by_se.values() if v.get("fetched_at"))
    log["fetched_at_range"] = [stamps[0], stamps[-1]] if stamps else []
    log["note"] = ("每条 detail 记录来自一次成功的按单据 GET；本次 requested=0 "
                   "表示全部命中本地缓存，不代表历史未取数。"
                   "http 含该阶段的重试次数；预算与探针共享。")
    log["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {"schema": SE_DETAIL_SCHEMA, "site": SITE, "log": log,
               "by_se": dict(sorted(by_se.items()))}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "se_details.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


def probe_wo_mismatches(scopes: list[dict], out_dir: Path, limit: int, sleep_s: float,
                        budget: HttpBudget, env_file: str | None = None) -> dict:
    """对 produced_qty != SE 的 WO，补查 WO 详情与该 WO 的全部 SE 清单（有界）。"""
    targets: list[tuple[str, str]] = []
    for sc in scopes:
        for name, w in sc["wo_summary"].items():
            if w["reason_code"] == "wo_se_qty_mismatch" and (sc["scope"], name) not in targets:
                targets.append((sc["scope"], name))
    targets = targets[:limit]
    if not targets:
        return {"schema": WO_PROBE_SCHEMA, "targets": [], "probes": {},
                "log": {"http": 0, "retries": 0, "pages": 0,
                        "budget_exceeded": False, "requests": []}}
    env_files = [Path(env_file)] if env_file else iss.resolve_env_files()
    key, secret = iss.load_credentials("prod", env_files)
    if not key or not secret:
        raise InputError("EN 生产凭证未配置（EN_API/.env）")
    probes: dict = {}
    start_used = budget.used
    start_retries = budget.by_kind.get("retry", 0)
    log = {"http": 0, "retries": 0, "pages": 0, "errors": [],
           "budget": budget.limit, "budget_used_before": start_used,
           "budget_exceeded": False, "requests": [], "not_probed": []}
    for i, (scope, wo) in enumerate(targets):
        rec: dict = {"scope": scope, "work_order": wo}
        before = budget.used
        try:
            wd = budgeted_get_single(budget, "Work Order", wo, SITE, key, secret, "probe")
            rec["wo_detail"] = {k: wd.get(k) for k in
                                ("name", "status", "docstatus", "qty", "produced_qty",
                                 "material_transferred_for_manufacturing",
                                 "total_produced_qty", "skip_transfer",
                                 "sales_order", "production_item", "bom_no")}
            ses = budgeted_paginated_get(
                budget, "Stock Entry", SITE, key, secret,
                [["Stock Entry", "work_order", "=", wo], ["Stock Entry", "docstatus", "<", 2]],
                ["name", "stock_entry_type", "docstatus", "posting_date", "work_order"],
                kind="probe", label="SE(probe)")
            log["pages"] += ses["pages"]
            rec["stock_entries"] = ses["rows"]
            rec["probe_pages"] = ses["pages"]
            rec["by_type"] = dict(Counter(s.get("stock_entry_type")
                                          for s in ses["rows"]))
            rec["ok"] = True
        except BudgetExhausted:
            budget.exhausted = True
            log["budget_exceeded"] = True
            rec["ok"] = False
            rec["error"] = "budget_exhausted"
            log["errors"].append({"work_order": wo, "error": "budget_exhausted"})
            log["not_probed"] = [t[1] for t in targets[i:]]
            probes[wo] = rec
            break
        except Exception as e:  # noqa: BLE001 - 探针失败要留证
            rec["ok"] = False
            rec["error"] = f"{type(e).__name__}: {e}"
            log["errors"].append({"work_order": wo, "error": rec["error"]})
        log["requests"].append({"work_order": wo, "requests": budget.used - before})
        probes[wo] = rec
        if i + 1 < len(targets):
            time.sleep(sleep_s)
    log["http"] = budget.used - start_used
    log["retries"] = budget.by_kind.get("retry", 0) - start_retries
    log["budget_used_after"] = budget.used
    log["budget_exhausted"] = budget.exhausted
    payload = {"schema": WO_PROBE_SCHEMA, "site": SITE, "log": log,
               "probes": probes}
    (out_dir / "wo_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return payload


# ── 汇总写盘 ──────────────────────────────────────────
def window_summary(so_out: list[dict]) -> dict:
    """窗口只作分区；数量按 UOM 分区，绝不跨单位求和。"""
    inw = [r for r in so_out if r["in_window"] is True]
    outw = [r for r in so_out if r["in_window"] is False]
    unk = [r for r in so_out if r["in_window"] is None]

    def agg(rows):
        by_uom: dict[str, dict] = defaultdict(
            lambda: {"lines": 0, "qty": 0.0, "delivered": 0.0, "open": 0.0})
        uom_unknown = 0
        for r in rows:
            u = r.get("uom")
            if not uom_known(u):
                uom_unknown += 1
                continue
            b = by_uom[u]
            b["lines"] += 1
            b["qty"] += r["qty"]["qty_exact"] or 0.0
            b["delivered"] += r["qty"]["delivered_qty_exact"] or 0.0
            b["open"] += r["qty"]["open_qty_exact"] or 0.0
        return {"lines": len(rows),
                "lines_uom_unknown": uom_unknown,
                "by_uom": {u: {"lines": b["lines"],
                               "qty": b["qty"],
                               "delivered": b["delivered"],
                               "open": b["open"]}
                           for u, b in sorted(by_uom.items())},
                "dispositions": dict(sorted(Counter(r["disposition"]
                                                    for r in rows).items()))}
    return {"in_window": agg(inw), "out_of_window": agg(outw), "date_unknown": agg(unk)}


def build_manifest(scopes: list[dict], window: tuple[str | None, str | None], basis: str,
                   se_details: dict | None, probe: dict | None, run_id: str,
                   http_budget: HttpBudget | None = None) -> dict:
    row_type_read = Counter()
    for sc in scopes:
        i = sc["inputs"]
        row_type_read["so_line"] += i["so_line"]
        row_type_read["dn_line"] += i["dn_line"]
        row_type_read["wo"] += i["wo"]
        row_type_read["se"] += i["se"]
    emitted = Counter()
    for sc in scopes:
        emitted.update(r["row_type"] for r in sc["rows"])
    accounting = {}
    # SO/DN/WO/SE 行账：**原始输入** == 输出（含 rejected 行；JC/SE 行是派生子行）
    ok_all = True
    for t in ("so_line", "dn_line", "wo", "se"):
        ok = row_type_read[t] == emitted.get(t, 0)
        ok_all &= ok
        accounting[t] = {"read": row_type_read[t], "emitted": emitted.get(t, 0),
                         "match": ok}
    accounting["jc_operation"] = {"derived": emitted.get("jc_operation", 0)}
    accounting["se_line"] = {"derived": emitted.get("se_line", 0)}

    c1_all = [x for sc in scopes for x in sc["checks"]["C1_lines"]]
    c1_evaluated = [x for x in c1_all if x["eligible"] and x["pass"] is not None]
    c1_unresolved = [x for x in c1_all if x["eligible"] and x["pass"] is None]
    c1_fail = [x for x in c1_evaluated if x["pass"] is False]
    c1_pass = not c1_fail and not c1_unresolved
    c3 = [sc["checks"]["C3_se_internal"] for sc in scopes]
    c3_no_mismatch = all(x["mismatch"] == 0 for x in c3)
    c3_unverified = sum(x["unverified"] for x in c3)
    dup = [d for sc in scopes for d in sc["dup_keys"]]
    child_dup = [d for sc in scopes for d in sc["child_dup"]]
    rejected = [(sc["scope"], r) for sc in scopes for r in sc["rejected"]]
    se_cov = [dict(sc["se_coverage"]) | {"scope": sc["scope"]} for sc in scopes]
    se_complete = all(c["complete"] for c in se_cov)
    unresolved_se = [dict(u) | {"scope": c["scope"]}
                     for c in se_cov for u in c["unresolved"]]
    unresolved_wo = [dict(u) | {"scope": c["scope"]}
                     for c in se_cov for u in c.get("wo_unresolved") or []]
    query_errors = [{"scope": c["scope"], "error": c["query_error"]}
                    for c in se_cov if c["query_error"]]
    jc_stats = {sc["scope"]: sc["jc_stats"] for sc in scopes}
    orphan_jc = sum(s["orphan"] for s in jc_stats.values())
    invalid_jc = sum(s["invalid"] for s in jc_stats.values())

    audit_ok = bool(ok_all and c1_pass and c3_no_mismatch and c3_unverified == 0
                    and not dup and se_complete and not rejected)
    evidence_complete = bool(c3_unverified == 0 and se_complete and not rejected)
    budget_log = http_budget.as_log() if http_budget is not None else None
    budget_exhausted = bool(budget_log and budget_log["exhausted"])

    probe_by_wo = (probe or {}).get("probes") or {}
    findings = []
    for sc in scopes:
        for name, w in sc["wo_summary"].items():
            if w["reason_code"] in ("wo_se_qty_mismatch", "wo_uom_unresolved",
                                    "wo_uom_mixed",
                                    "wo_se_partially_unverified", "wo_se_missing",
                                    "wo_se_incomplete", "wo_se_query_incomplete"):
                item = {"scope": sc["scope"], "work_order": name,
                        "reason_code": w["reason_code"],
                        "qty": w["qty"], "produced_qty": w["produced_qty"],
                        "se_finished_qty": w["se_finished_qty"],
                        "se_finished_by_uom": w.get("se_finished_by_uom")}
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
                    "inputs": sc["inputs"], "parsed_inputs": sc["parsed_inputs"],
                    "counts": sc["counts"],
                    "disposition_counts": sc["disposition_counts"],
                    "link_counts": sc["link_counts"],
                    "association": sc["association"],
                    "checks": sc["checks"],
                    "se_coverage": sc["se_coverage"],
                    "jc_stats": sc["jc_stats"],
                    "window": window_summary([r for r in sc["rows"]
                                              if r["row_type"] == "so_line"]),
                    "unlinked_dn": sc["unlinked_dn"]}
                   for sc in scopes],
        "row_accounting": accounting,
        "audit_ok": audit_ok,
        "evidence_complete": evidence_complete,
        "coverage": {
            "se": {"complete": se_complete, "per_scope": se_cov,
                   "unresolved_submitted": unresolved_se,
                   "unresolved_work_orders": unresolved_wo,
                   "query_errors": query_errors,
                   "submitted_total": sum(c["submitted"] for c in se_cov),
                   "resolved_total": sum(c["conserved"] for c in se_cov)},
            "c1": {"complete": not c1_unresolved,
                   "lines_total": len(c1_all),
                   "lines_evaluated": len(c1_evaluated),
                   "lines_fail": len(c1_fail),
                   "unresolved": [{"scope": x.get("scope"),
                                   "so_line_key": x["so_line_key"],
                                   "reason_code": x["reason_code"]}
                                  for x in c1_unresolved]},
            "c3_unverified": c3_unverified,
            "rejected_rows": [{"scope": s, "row_type": r["row_type"],
                               "row_key": r["row_key"],
                               "reason_code": r["reason_code"]} for s, r in rejected],
            "orphan_jc_groups": orphan_jc,
            "invalid_jc_groups": invalid_jc,
            "duplicate_keys": dup,
            "child_duplicate_keys": child_dup,
        },
        "http_budget": budget_log,
        "conservation": {
            "C1_so_dn": {"pass": c1_pass, "per_scope": [sc["checks"]["C1_so_dn"]
                                                        for sc in scopes]},
            "C2_wo_se": [dict(sc["checks"]["C2_wo_se"],
                              complete=bool(sc["se_coverage"]["complete"]),
                              scope=sc["scope"]) for sc in scopes],
            "C3_se_internal": {"pass": c3_no_mismatch and c3_unverified == 0,
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
                if r["row_type"] == "se" and r["link"].get("detail_source"))),
            "enrichment": (se_details or {}).get("log"),
        },
        "wo_probe": (probe or {}).get("log"),
        "findings": findings,
        "notes": [
            "本文件只做 DN/WO/JC/SE 关联与数量守恒，不是 G1 验收、不是需求/补货结论。",
            "C1 逐行全精度判定（不四舍五入、不允许正负抵消）；UOM 汇总仅作展示。",
            "所有数量聚合按 UOM 分区；UOM 缺失/未知一律 unverified，不进入合计。",
            "SE finished 量按 (WO, UOM) 分桶；同一 SE 或同一 WO 的已守恒 SE 跨 UOM 时"
            "只留分桶、不出总量，且 C2/evidence 不完整。",
            "SE 子行任一未解决（非法 is_finished_item/缺键/重复键/非对象/物料不符）"
            "都让父 SE 与 WO 失去 conserved。",
            "JC 仅进度证据，不进入守恒；匹配到 WO 但工序明细非法的 JC 组落显式 invalid 行。",
            "C2 只对已取得 line 级证据且 SE 覆盖完整的 WO 出完整总数；否则只出 known_subtotal。",
            "WO.produced_qty 不作完工真值；SE finished 行合计才是守恒锚点。",
            "HTTP 预算为请求级（含重试与翻页），跨 SE 明细与探针共享。",
            "退货行按 is_return=1 取绝对值归一，只扣减一次。",
        ],
    }
    if budget_exhausted:
        manifest["run_status"] = "partial_http_budget_exhausted"
    return manifest


def stable_hash(manifest: dict) -> str:
    """去掉 run_id/as_of/在线探针/预算事件等易变字段后的稳定摘要。"""
    payload = {k: v for k, v in manifest.items()
               if k not in ("run_id", "as_of", "payload_sha256", "wo_probe",
                            "stable_sha256", "http_budget")}
    payload["findings"] = [{k: v for k, v in f.items() if k != "probe"}
                           for f in payload.get("findings") or []]
    if isinstance(payload.get("se_evidence"), dict):
        payload["se_evidence"] = {k: v for k, v in payload["se_evidence"].items()
                                  if k != "enrichment"}
    return canonical_sha(payload)


def finalize_manifest(manifest: dict) -> dict:
    """先写 stable_sha256，再对**完整最终 manifest** 计算 payload_sha256。"""
    manifest.pop("payload_sha256", None)
    manifest.pop("stable_sha256", None)
    manifest["stable_sha256"] = stable_hash(manifest)
    manifest["payload_sha256"] = canonical_sha(manifest)
    return manifest


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
    budget = HttpBudget(args.max_http)
    if args.enrich_se:
        try:
            se_details = enrich_se_details(snaps, out_dir, budget, args.sleep,
                                           out_dir / "se_details.json",
                                           args.env_file or None)
        except InputError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
    elif args.reuse_se_details:
        p = out_dir / "se_details.json"
        if p.is_file():
            se_details = json.loads(p.read_text(encoding="utf-8"))
            if se_details.get("schema") not in (None, SE_DETAIL_SCHEMA):
                print(f"✗ SE 明细缓存 schema 不符: {se_details.get('schema')!r}",
                      file=sys.stderr)
                return 2
        else:
            print(f"⚠ 没有可复用的 {p}；SE line 证据按缺失处理", file=sys.stderr)

    details = (se_details or {}).get("by_se") or {}
    scopes = [build_scope(s, {"by_se": details}, window, args.date_basis) for s in snaps]

    probe = None
    if args.probe_mismatch_wos > 0 and args.enrich_se:
        try:
            probe = probe_wo_mismatches(scopes, out_dir, args.probe_mismatch_wos,
                                        args.sleep, budget, args.env_file or None)
        except InputError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2

    manifest = build_manifest(scopes, window, args.date_basis, se_details, probe,
                              run_id, budget)
    finalize_manifest(manifest)

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
    budget_ok = not manifest["http_budget"]["exhausted"]
    if not (manifest["audit_ok"] and manifest["evidence_complete"] and budget_ok):
        print(f"  status=partial audit_ok={manifest['audit_ok']} "
              f"evidence_complete={manifest['evidence_complete']} "
              f"budget_ok={budget_ok}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
