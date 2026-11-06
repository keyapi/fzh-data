# -*- coding: utf-8 -*-
"""Phase 3.6：成本块 + 系数块补全（self 166 / FBA 95 / merged 78），只写本地文件。

公式（colab cell_125/168/169）：
- 1件产品成本 = 皮壳成本 + 绍兴二次加工成本 + 二次加工成本
- 产品成本*数量 = 1件产品成本 × 发货数量
- 订单总成本 = 产品成本*数量 + 头程运费*数量 + 运费 + 海外仓成本*数量
- 订单利润 = 售价*汇率 − 订单总成本
- 系数轨同结构（皮壳/绍兴二次/二次/1件/产品成本/总成本/利润 × 各自系数）

系数继承：
- self：Phase3 行（已从旧写回继承基础系数）→ 旧写回同键行 → 模板行；
- 合并组：组内统一取**载体行**系数；组内非空系数不一致 → 阻断（留空 + 原因）；
- 0 / 1 原样保留；空值按 1.0 参与派生计算（基础系数单元格仍留空）。
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .split_merge import normalize_sku
from ...order_side_input import platform_body, tiktok_platform_body

TZ_CN = timezone(timedelta(hours=8))
TOL = 1e-5

COST_COLUMNS = ("皮壳含包装成本", "皮壳不含包装成本", "皮壳成本", "绍兴二次加工成本",
                "二次加工成本", "头程运费金额", "运费", "海外仓成本")
AMOUNT_COLUMNS = ("皮壳成本*数量", "绍兴二次加工成本*数量", "二次加工成本*数量",
                  "头程运费*数量", "海外仓成本*数量")
BASE_COEF = ("绍兴成本系数", "二次加工成本系数", "绍兴二次加工成本系数")
DERIVED_COEF = ("皮壳不含包装成本*系数", "皮壳含包装成本*系数", "皮壳成本*系数",
                "皮壳成本*系数*数量", "二次加工成本*系数", "二次加工成本*系数*数量",
                "绍兴二次加工成本*系数", "绍兴二次加工成本*系数*数量",
                "1件产品成本*系数", "产品成本*系数*数量",
                "订单总成本*系数", "订单利润*系数")
FILL_COLUMNS = COST_COLUMNS + AMOUNT_COLUMNS + ("1件产品成本", "产品成本*数量",
                                                "订单总成本", "订单利润") + BASE_COEF + DERIVED_COEF


def _num(v) -> float | None:
    s = str(v).strip() if v is not None else ""
    if s in ("", "nan", "None", "NULL", "/"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _fmt(v: float | None) -> str:
    if v is None:
        return ""
    s = f"{round(v, 6):.6f}".rstrip("0").rstrip(".")
    return s or "0"


def _coef(v) -> float:
    n = _num(v)
    return 1.0 if n is None else n


def _key(order: object, sku: object) -> str:
    return f"{str(order or '').strip().upper()}|{normalize_sku(sku)}"


def _key_pt(order: object, platform: object) -> str:
    return f"{str(order or '').strip().upper()}|{normalize_sku(platform)}"


def _clamp_qty(v) -> float:
    return _num(v) or 0.0


def _fill_cells(*, shell: float | None, shell_in: float | None, shell_out: float | None,
                sx2: float | None, proc: float | None, head: float | None,
                qty: float, sales: float | None, freight: float | None,
                overseas: float | None, kc, k2, ksx, status: str,
                reason: str = "") -> dict:
    """生成一行的成本块 + 系数块；status != ok 时成本留空。"""
    q = qty or 0.0
    cells: dict[str, str] = {}
    if status != "ok" or shell is None:
        for c in FILL_COLUMNS:
            cells[c] = ""
        cells["cost_status"] = status
        cells["cost_reason"] = reason
        return cells
    shell_in = shell_in if shell_in is not None else shell
    shell_out = shell_out if shell_out is not None else shell
    sx2 = sx2 or 0.0
    proc = proc or 0.0
    head = head or 0.0
    fr = freight or 0.0
    ov = overseas or 0.0
    one = shell + sx2 + proc
    prod_amt = one * q
    rem_amt = head * q
    ov_amt = ov * q
    total = prod_amt + rem_amt + fr + ov_amt
    profit = None if sales is None else sales - total

    ck = _coef(kc)
    c2 = _coef(k2)
    csx = _coef(ksx)
    shell_k = shell * ck
    shell_out_k = shell_out * ck
    shell_in_k = shell_in * ck
    sx2_k = sx2 * csx
    proc_k = proc * c2
    one_k = shell_k + sx2_k + proc_k
    prod_k_amt = one_k * q
    total_k = prod_k_amt + rem_amt + fr + ov_amt
    profit_k = None if sales is None else sales - total_k

    cells.update({
        "皮壳含包装成本": _fmt(shell_in),
        "皮壳不含包装成本": _fmt(shell_out),
        "皮壳成本": _fmt(shell),
        "绍兴二次加工成本": _fmt(sx2),
        "二次加工成本": _fmt(proc),
        "头程运费金额": _fmt(head),
        "运费": _fmt(fr),
        "海外仓成本": _fmt(ov),
        "皮壳成本*数量": _fmt(shell * q),
        "绍兴二次加工成本*数量": _fmt(sx2 * q),
        "二次加工成本*数量": _fmt(proc * q),
        "头程运费*数量": _fmt(rem_amt),
        "海外仓成本*数量": _fmt(ov_amt),
        "1件产品成本": _fmt(one),
        "产品成本*数量": _fmt(prod_amt),
        "订单总成本": _fmt(total),
        "订单利润": _fmt(profit),
        "绍兴成本系数": str(kc).strip() if kc not in (None, "") else "",
        "二次加工成本系数": str(k2).strip() if k2 not in (None, "") else "",
        "绍兴二次加工成本系数": str(ksx).strip() if ksx not in (None, "") else "",
        "皮壳不含包装成本*系数": _fmt(shell_out_k),
        "皮壳含包装成本*系数": _fmt(shell_in_k),
        "皮壳成本*系数": _fmt(shell_k),
        "皮壳成本*系数*数量": _fmt(shell_k * q),
        "二次加工成本*系数": _fmt(proc_k),
        "二次加工成本*系数*数量": _fmt(proc_k * q),
        "绍兴二次加工成本*系数": _fmt(sx2_k),
        "绍兴二次加工成本*系数*数量": _fmt(sx2_k * q),
        "1件产品成本*系数": _fmt(one_k),
        "产品成本*系数*数量": _fmt(prod_k_amt),
        "订单总成本*系数": _fmt(total_k),
        "订单利润*系数": _fmt(profit_k),
        "cost_status": "ok",
        "cost_reason": "",
    })
    return cells


def _check_cells(cells: Mapping, qty: float, sales: float | None) -> list[str]:
    """普通轨与系数轨恒等断言，返回失败项。"""
    if cells.get("cost_status") != "ok":
        return []
    n = {c: _num(cells.get(c)) for c in FILL_COLUMNS}
    fails: list[str] = []
    q = qty or 0.0
    if None in (n["皮壳成本"], n["绍兴二次加工成本"], n["二次加工成本"], n["1件产品成本"]):
        fails.append("成本缺值")
    else:
        if abs((n["皮壳成本"] + n["绍兴二次加工成本"] + n["二次加工成本"]) - n["1件产品成本"]) > TOL:
            fails.append("1件≠皮壳+绍兴二次+二次")
        if n["产品成本*数量"] is not None and abs(n["1件产品成本"] * q - n["产品成本*数量"]) > TOL:
            fails.append("产品成本*数量≠1件×qty")
        total = (n["产品成本*数量"] or 0) + (n["头程运费*数量"] or 0) + (n["运费"] or 0) + (n["海外仓成本*数量"] or 0)
        if n["订单总成本"] is not None and abs(total - n["订单总成本"]) > TOL:
            fails.append("总成本公式不符")
        if sales is not None and n["订单利润"] is not None and abs(sales - total - n["订单利润"]) > TOL:
            fails.append("利润公式不符")
    if n["1件产品成本*系数"] is not None and None not in (
            n["皮壳成本*系数"], n["绍兴二次加工成本*系数"], n["二次加工成本*系数"]):
        if abs(n["皮壳成本*系数"] + n["绍兴二次加工成本*系数"] + n["二次加工成本*系数"]
               - n["1件产品成本*系数"]) > TOL:
            fails.append("1件*系数≠分量之和")
        if n["产品成本*系数*数量"] is not None and abs(
                n["1件产品成本*系数"] * q - n["产品成本*系数*数量"]) > TOL:
            fails.append("产品成本*系数*数量≠1件*系数×qty")
        total_k = (n["产品成本*系数*数量"] or 0) + (n["头程运费*数量"] or 0) + (n["运费"] or 0) + (n["海外仓成本*数量"] or 0)
        if n["订单总成本*系数"] is not None and abs(total_k - n["订单总成本*系数"]) > TOL:
            fails.append("总成本*系数公式不符")
        if sales is not None and n["订单利润*系数"] is not None and abs(sales - total_k - n["订单利润*系数"]) > TOL:
            fails.append("利润*系数公式不符")
    return fails


def _old_index(old: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in old.to_dict("records"):
        out.setdefault(_key(r.get("订单号"), r.get("通途SKU")), r)
        out.setdefault(_key_pt(r.get("订单号"), r.get("平台SKU")), r)
    return out


def _coef_tuple(row: Mapping | None) -> tuple:
    if row is None:
        return ("", "", "")
    return tuple(str(row.get(c, "") or "").strip() for c in BASE_COEF)


def _coef_conflict(a: Sequence[str], b: Sequence[str]) -> bool:
    for x, y in zip(a, b):
        if x != "" and y != "" and _num(x) != _num(y):
            return True
    return False


def build_phase36(*, month: str, root: str | Path = ".", out_dir: str | Path | None = None) -> dict:
    root = Path(root)
    out = root / "out"
    out_dir = Path(out_dir or out / "phase36" / month)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "self_template": out / f"wb_fresh_{month}.csv",
        "fba_template": out / f"wb_fba_{month}.csv",
        "merged_template": out / f"merged_{month}.csv",
        "self_source": out / "writeback_rehearsal" / month / f"writeback_new_{month}.csv",
        "fba_source": out / "fba_shadow" / month / f"fba_shadow_{month}.csv",
        "old_writeback": out / f"writeback_{month}.csv",
    }
    for p in paths.values():
        if not p.exists():
            raise FileNotFoundError(p)
    self_t = pd.read_csv(paths["self_template"], dtype=str, keep_default_na=False)
    fba_t = pd.read_csv(paths["fba_template"], dtype=str, keep_default_na=False)
    merged_t = pd.read_csv(paths["merged_template"], dtype=str, keep_default_na=False)
    src = pd.read_csv(paths["self_source"], dtype=str, keep_default_na=False)
    fba_shadow = pd.read_csv(paths["fba_source"], dtype=str, keep_default_na=False)
    old = pd.read_csv(paths["old_writeback"], dtype=str, keep_default_na=False)
    old_by_key = _old_index(old)

    src_by_key: dict[str, dict] = {}
    src_by_order: dict[str, list[dict]] = defaultdict(list)
    src_by_row: dict[int, dict] = {}
    src_by_body_sku: dict[tuple[str, str], dict] = {}
    for r in src.to_dict("records"):
        src_by_key.setdefault(_key(r.get("订单号"), r.get("通途SKU")), r)
        src_by_key.setdefault(_key_pt(r.get("订单号"), r.get("平台SKU_统一") or r.get("平台SKU")), r)
        src_by_order[str(r.get("订单号") or "").strip().upper()].append(r)
        body = tiktok_platform_body(str(r.get("订单号") or ""))
        if body:
            src_by_body_sku.setdefault((body, normalize_sku(r.get("通途SKU"))), r)
        for x in str(r.get("source_row") or "").split(","):
            if x.strip().isdigit():
                src_by_row[int(x.strip())] = r
    raw_csv = out / "snapshots" / month / f"raw_{month}.csv"
    raw_by_key: dict[str, int] = {}
    if raw_csv.exists():
        raw = pd.read_csv(raw_csv, dtype=str, keep_default_na=False)
        for i, r in enumerate(raw.to_dict("records")):
            raw_by_key.setdefault(_key(r.get("订单号"), r.get("通途SKU")), i)
            raw_by_key.setdefault(_key_pt(r.get("订单号"), r.get("平台SKU")), i)

    crosswalk_self: list[dict] = []
    blocks: Counter = Counter()
    blanks: list[dict] = []
    invalid_backup: list[dict] = []
    self_rows: list[dict] = []
    self_violations: list[dict] = []
    flags_csv = out / "snapshots" / month / "order_flags.csv"
    invalid_ids: set[str] = set()
    if flags_csv.exists():
        flags = pd.read_csv(flags_csv, dtype=str, keep_default_na=False)
        if {"order_id_code", "invalid"} <= set(flags.columns):
            invalid_ids = {
                str(r["order_id_code"]).strip().upper()
                for r in flags.to_dict("records")
                if str(r.get("invalid") or "").strip() == "1"
            }
    for rec in self_t.to_dict("records"):
        row = dict(rec)
        k = _key(rec.get("订单号"), rec.get("通途SKU"))
        srow = src_by_key.get(k)
        if srow is None:
            srow = src_by_key.get(
                _key_pt(rec.get("订单号"), rec.get("平台SKU_统一") or rec.get("平台SKU")))
        if srow is None:
            cands = src_by_order.get(str(rec.get("订单号") or "").strip().upper(), [])
            if len(cands) == 1:
                srow = cands[0]
        if srow is None:
            # TikTok 跨前缀：模板行可能是 Colab 归一化单号（如 xxx-1），
            # 与 raw 的 TTDaneeyGo/TTDaneeyUS 前缀不同但数字主体相同。
            body = platform_body(str(rec.get("订单号") or ""))
            if len(body) >= 12:
                srow = src_by_body_sku.get((body, normalize_sku(rec.get("通途SKU"))))
        if srow is None:
            ridx = raw_by_key.get(k)
            if ridx is None:
                ridx = raw_by_key.get(
                    _key_pt(rec.get("订单号"), rec.get("平台SKU") or rec.get("平台SKU_统一")))
            if ridx is not None:
                srow = src_by_row.get(ridx)
        qty = _clamp_qty(rec.get("发货数量"))
        old_row = old_by_key.get(k)
        if old_row is None:
            old_row = old_by_key.get(
                _key_pt(rec.get("订单号"), rec.get("平台SKU_统一") or rec.get("平台SKU")))
        if srow is None:
            oid = str(rec.get("订单号") or "").strip().upper()
            if oid in invalid_ids:
                # 作废原单：保留行与销售/非成本列，成本与系数轨全部留空；旧值只进备份
                status = "invalid_original"
                blocks["invalid_original"] += 1
                invalid_backup.append({
                    "订单号": rec.get("订单号"), "平台SKU": rec.get("平台SKU"),
                    "通途SKU": rec.get("通途SKU"), "reason": "invalid_original",
                    **{
                        c: (old_row.get(c) if old_row is not None
                            and str(old_row.get(c) or "").strip() != "" else rec.get(c))
                        for c in FILL_COLUMNS
                    },
                })
                cells = _fill_cells(shell=None, shell_in=None, shell_out=None, sx2=None,
                                    proc=None, head=None, qty=qty, sales=None, freight=None,
                                    overseas=None, kc="", k2="", ksx="",
                                    status="invalid_original", reason="invalid_original")
            else:
                status = "crosswalk_missing"
                blocks["crosswalk_missing"] += 1
                cells = _fill_cells(shell=None, shell_in=None, shell_out=None, sx2=None,
                                    proc=None, head=None, qty=qty, sales=None, freight=None,
                                    overseas=None, kc="", k2="", ksx="",
                                    status="crosswalk_missing", reason="crosswalk_missing")
        else:
            same_carrier = normalize_sku(rec.get("通途SKU")) == normalize_sku(srow.get("通途SKU"))
            src_status = str(srow.get("cost_status") or srow.get("status") or "ok")
            if src_status in ("component_absorbed", "non_product_accessory", "zero_cost",
                              "excluded_non_product"):
                # 零成本行：显式 0（不补旧值），保留原因
                coefs = _coef_tuple(srow)
                oldc = _coef_tuple(old_row)
                cells = _fill_cells(
                    shell=0.0, shell_in=0.0, shell_out=0.0, sx2=0.0, proc=0.0, head=0.0,
                    qty=qty, sales=_num(rec.get("售价*汇率")),
                    freight=_num(rec.get("运费")) or 0.0,
                    overseas=_num(rec.get("海外仓成本")) or 0.0,
                    kc=coefs[0] or oldc[0], k2=coefs[1] or oldc[1], ksx=coefs[2] or oldc[2],
                    status="ok", reason=src_status,
                )
                cells["cost_reason"] = src_status
                status = src_status
            elif src_status not in ("ok", "", "priced"):
                blocks[f"source_{src_status}"] += 1
                cells = _fill_cells(shell=None, shell_in=None, shell_out=None, sx2=None, proc=None,
                                    head=None, qty=qty, sales=None, freight=None, overseas=None,
                                    kc="", k2="", ksx="", status=f"source_{src_status}",
                                    reason=f"source_{src_status}")
                status = f"source_{src_status}"
            elif not same_carrier:
                # 合并组内被吸收行：成本显式 0；系数取载体；组内非空不一致 → 阻断
                carrier_coefs = _coef_tuple(srow) if srow is not None else ("", "", "")
                comp_coefs = _coef_tuple(old_row)
                if _coef_conflict(carrier_coefs, comp_coefs):
                    blocks["coef_conflict"] += 1
                    cells = _fill_cells(shell=None, shell_in=None, shell_out=None, sx2=None,
                                        proc=None, head=None, qty=qty, sales=None, freight=None,
                                        overseas=None, kc="", k2="", ksx="", status="coef_conflict",
                                        reason="coef_conflict")
                    status = "coef_conflict"
                else:
                    coefs = tuple(x if x != "" else y for x, y in zip(carrier_coefs, comp_coefs))
                    cells = _fill_cells(
                        shell=0.0, shell_in=0.0, shell_out=0.0, sx2=0.0, proc=0.0, head=0.0,
                        qty=qty, sales=_num(rec.get("售价*汇率")), freight=_num(rec.get("运费")) or 0.0,
                        overseas=_num(rec.get("海外仓成本")) or 0.0,
                        kc=coefs[0], k2=coefs[1], ksx=coefs[2],
                        status="ok", reason="component_absorbed")
                    cells["cost_reason"] = "component_absorbed"
                    status = "component_absorbed"
            else:
                sales = _num(rec.get("售价*汇率"))
                if sales is None:
                    sales = _num(rec.get("售价(人民币)")) or _num(rec.get("订单总售价(人民币)"))
                carrier_coefs = _coef_tuple(srow)
                oldc = _coef_tuple(old_row)
                if _coef_conflict(carrier_coefs, oldc):
                    blocks["coef_conflict"] += 1
                    cells = _fill_cells(shell=None, shell_in=None, shell_out=None, sx2=None,
                                        proc=None, head=None, qty=qty, sales=None, freight=None,
                                        overseas=None, kc="", k2="", ksx="", status="coef_conflict",
                                        reason="coef_conflict")
                    status = "coef_conflict"
                else:
                    coefs = tuple(x if x != "" else y for x, y in zip(carrier_coefs, oldc))
                    shell = _num(srow.get("皮壳成本"))
                    shell_out = _num(old_row.get("皮壳不含包装成本")) if old_row else None
                    shell_in = _num(old_row.get("皮壳含包装成本")) if old_row else None
                    cells = _fill_cells(
                        shell=shell, shell_in=shell_in, shell_out=shell_out,
                        sx2=_num(srow.get("绍兴二次加工成本")),
                        proc=_num(srow.get("二次加工成本")),
                        head=_num(srow.get("头程运费金额")), qty=qty, sales=sales,
                        freight=_num(rec.get("运费")) or 0.0,
                        overseas=_num(rec.get("海外仓成本")) or 0.0,
                        kc=coefs[0], k2=coefs[1], ksx=coefs[2],
                        status="ok", reason="")
                    status = "ok"
        row.update(cells)
        self_rows.append(row)
        crosswalk_self.append({
            "订单号": rec.get("订单号"), "通途SKU": rec.get("通途SKU"), "平台SKU": rec.get("平台SKU"),
            "status": status, "source_order": srow.get("订单号") if srow else "",
            "source_sku": srow.get("通途SKU") if srow else "",
            "same_carrier": (normalize_sku(rec.get("通途SKU")) == normalize_sku(srow.get("通途SKU"))) if srow else "",
            "qty": qty,
        })
        if status in ("crosswalk_missing", "coef_conflict", "invalid_original") or status.startswith("source_"):
            blanks.append({"table": "self", "订单号": rec.get("订单号"),
                           "平台SKU": rec.get("平台SKU"), "通途SKU": rec.get("通途SKU"),
                           "reason": cells.get("cost_reason", status)})
        v = _check_cells(cells, qty, _num(rec.get("售价*汇率")))
        if v:
            self_violations.append({"订单号": rec.get("订单号"), "通途SKU": rec.get("通途SKU"),
                                    "fails": v})

    self_cols = list(dict.fromkeys(list(self_t.columns) + list(FILL_COLUMNS)
                                   + ["cost_status", "cost_reason"]))
    self_df = pd.DataFrame(self_rows, columns=self_cols)

    # ── FBA 95 ──
    shadow_by_key: dict[str, dict] = {}
    for r in fba_shadow.to_dict("records"):
        shadow_by_key.setdefault(
            "|".join((str(r.get("site") or "").upper(),
                      normalize_sku(r.get("平台SKU")), normalize_sku(r.get("通途SKU")))), r)
    crosswalk_fba: list[dict] = []
    fba_rows: list[dict] = []
    fba_violations: list[dict] = []
    for rec in fba_t.to_dict("records"):
        row = dict(rec)
        k = "|".join((str(rec.get("站点") or "").upper(),
                      normalize_sku(rec.get("MSKU")), normalize_sku(rec.get("SKU"))))
        s = shadow_by_key.get(k)
        qty = _clamp_qty(rec.get("发货数量"))
        sales = _num(rec.get("售价*汇率"))
        if sales is None:
            sales = _num(rec.get("销售额"))
        kc, k2, ksx = (rec.get("绍兴成本系数"), rec.get("二次加工成本系数"),
                       rec.get("绍兴二次加工成本系数"))
        if s is None or str(s.get("bridge_status")) != "ok":
            reason = "shadow_missing" if s is None else f"shadow_{s.get('bridge_status')}"
            blocks[reason] += 1
            cells = _fill_cells(shell=None, shell_in=None, shell_out=None, sx2=None, proc=None,
                                head=None, qty=qty, sales=None, freight=None, overseas=None,
                                kc=kc, k2=k2, ksx=ksx, status="blocked", reason=reason)
            status = reason
        else:
            cells = _fill_cells(
                shell=_num(s.get("皮壳成本")),
                shell_in=_num(rec.get("皮壳含包装成本")),
                shell_out=_num(rec.get("皮壳不含包装成本")),
                sx2=_num(s.get("绍兴二次加工成本")),
                proc=_num(s.get("二次加工成本")),
                head=_num(s.get("头程运费金额")), qty=qty, sales=sales,
                freight=_num(rec.get("运费")) or 0.0,
                overseas=_num(rec.get("海外仓成本")) or 0.0,
                kc=kc, k2=k2, ksx=ksx, status="ok")
            status = "ok"
        row.update(cells)
        fba_rows.append(row)
        crosswalk_fba.append({"站点": rec.get("站点"), "MSKU": rec.get("MSKU"),
                              "SKU": rec.get("SKU"), "status": status,
                              "shadow_sku": s.get("通途SKU") if s else "",
                              "qty": qty})
        if status != "ok":
            blanks.append({"table": "fba", "站点": rec.get("站点"), "MSKU": rec.get("MSKU"),
                           "SKU": rec.get("SKU"), "reason": status})
        v = _check_cells(cells, qty, sales)
        if v:
            fba_violations.append({"站点": rec.get("站点"), "MSKU": rec.get("MSKU"), "fails": v})
    fba_cols = list(dict.fromkeys(list(fba_t.columns) + list(FILL_COLUMNS)
                                  + ["cost_status", "cost_reason"]))
    fba_df = pd.DataFrame(fba_rows, columns=fba_cols)

    # ── merged 78：fresh 行 + FBA 行按索引对齐 ──
    merged_rows: list[dict] = []
    merged_violations: list[dict] = []
    for i, rec in enumerate(merged_t.to_dict("records")):
        row = dict(rec)
        if i < len(self_df):
            src_row = self_df.iloc[i]
        elif i - len(self_df) < len(fba_df):
            src_row = fba_df.iloc[i - len(self_df)]
        else:
            src_row = None
        if src_row is not None:
            for c in FILL_COLUMNS + ("cost_status", "cost_reason"):
                if c in src_row:
                    row[c] = src_row[c]
        merged_rows.append(row)
        qty = _clamp_qty(rec.get("发货数量"))
        sales = _num(rec.get("售价*汇率"))
        v = _check_cells(row, qty, sales)
        if v:
            merged_violations.append({"订单号": rec.get("订单号"), "通途SKU": rec.get("通途SKU"), "fails": v})
    merged_cols = list(dict.fromkeys(list(merged_t.columns) + list(FILL_COLUMNS)
                                     + ["cost_status", "cost_reason"]))
    merged_df = pd.DataFrame(merged_rows, columns=merged_cols)

    # ── Phase 3.7：95↔78 粒度对账 + 重叠检查 + 作废备份 + GS-ready ──
    recon_metrics = ["发货数量", "售价*汇率", "皮壳成本", "绍兴二次加工成本", "二次加工成本",
                     "头程运费金额", "皮壳成本*数量", "绍兴二次加工成本*数量", "二次加工成本*数量",
                     "头程运费*数量", "1件产品成本", "产品成本*数量", "订单总成本", "订单利润"] \
                    + list(BASE_COEF) + list(DERIVED_COEF)
    metrics = [c for c in recon_metrics if c in fba_df.columns and c in merged_df.columns]
    merged_fba = merged_df.iloc[len(self_df):len(self_df) + len(fba_df)]

    def _group(df: pd.DataFrame, site: str, msku: str, sku: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in df.to_dict("records"):
            k = "|".join((str(r.get(site) or "").upper(),
                          normalize_sku(r.get(msku)), normalize_sku(r.get(sku))))
            acc = out.setdefault(k, {c: 0.0 for c in metrics})
            for c in metrics:
                acc[c] += _num(r.get(c)) or 0.0
        return out

    g95 = _group(fba_df, "站点", "MSKU", "SKU")
    g78 = _group(merged_fba, "渠道账号", "平台SKU", "通途SKU")
    recon_rows: list[dict] = []
    for k in sorted(set(g95) | set(g78)):
        a, b = g95.get(k, {}), g78.get(k, {})
        row = {"key": k, "in_95": k in g95, "in_78": k in g78}
        n_diff = 0
        for c in metrics:
            d = round((b.get(c, 0.0) or 0.0) - (a.get(c, 0.0) or 0.0), 6)
            row[f"diff_{c}"] = d
            if abs(d) > TOL:
                n_diff += 1
        row["diff_cols"] = n_diff
        if n_diff or k not in g95 or k not in g78:
            recon_rows.append(row)
    recon_totals = []
    total_diff_cols = 0
    for c in metrics:
        a = sum(v[c] for v in g95.values())
        b = sum(v[c] for v in g78.values())
        d = round(b - a, 6)
        if abs(d) > TOL:
            total_diff_cols += 1
        recon_totals.append({"metric": c, "fba95": round(a, 6), "merged78": round(b, 6), "diff": d})
    pd.DataFrame(recon_rows).to_csv(out_dir / "recon_95_78.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(recon_totals).to_csv(out_dir / "recon_95_78_totals.csv", index=False,
                                      encoding="utf-8-sig")

    # FBA 与非 FBA 重叠检查（订单号 / 站点+SKU）
    fba_orders = {str(r.get("订单号") or "").strip().upper() for r in fba_t.to_dict("records")}
    self_orders = {str(r.get("订单号") or "").strip().upper() for r in self_t.to_dict("records")}
    fba_keys = {f"{str(r.get('站点') or '').upper()}|{normalize_sku(r.get('SKU'))}"
                for r in fba_t.to_dict("records")}
    self_keys = {f"{''.join(str(r.get('渠道账号') or '').split()).upper()}|{normalize_sku(r.get('通途SKU'))}"
                 for r in self_t.to_dict("records")}
    overlap_rows = [{"type": "order", "key": k} for k in sorted(fba_orders & self_orders)]
    overlap_rows += [{"type": "site_sku", "key": k} for k in sorted(fba_keys & self_keys)]
    pd.DataFrame(overlap_rows, columns=["type", "key"]).to_csv(
        out_dir / "overlap_self_fba.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame(invalid_backup).to_csv(out_dir / "invalid_original_backup.csv", index=False,
                                        encoding="utf-8-sig")

    # GS-ready：严格模板列（剔除 +2 审计列）
    gs_dir = out_dir / "gs_ready"
    gs_dir.mkdir(parents=True, exist_ok=True)
    self_df[list(self_t.columns)].to_csv(gs_dir / f"wb_fresh_{month}.csv", index=False,
                                         encoding="utf-8-sig")
    fba_df[list(fba_t.columns)].to_csv(gs_dir / f"wb_fba_{month}.csv", index=False,
                                       encoding="utf-8-sig")
    merged_df[list(merged_t.columns)].to_csv(gs_dir / f"merged_{month}.csv", index=False,
                                             encoding="utf-8-sig")

    # ── 输出 ──
    self_csv = out_dir / f"wb_fresh_{month}.csv"
    fba_csv = out_dir / f"wb_fba_{month}.csv"
    merged_csv = out_dir / f"merged_{month}.csv"
    self_df.to_csv(self_csv, index=False, encoding="utf-8-sig")
    fba_df.to_csv(fba_csv, index=False, encoding="utf-8-sig")
    merged_df.to_csv(merged_csv, index=False, encoding="utf-8-sig")
    pd.DataFrame(crosswalk_self).to_csv(out_dir / "crosswalk_self.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(crosswalk_fba).to_csv(out_dir / "crosswalk_fba.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(blanks).to_csv(out_dir / "blanks.csv", index=False, encoding="utf-8-sig")
    fill_rows = []
    for name, df in (("self", self_df), ("fba", fba_df), ("merged", merged_df)):
        for c in FILL_COLUMNS:
            if c not in df.columns:
                continue
            filled = (df[c].astype(str).str.strip() != "").mean()
            fill_rows.append({"table": name, "column": c, "rows": len(df),
                              "fill_rate": round(float(filled), 6)})
    fill_df = pd.DataFrame(fill_rows)
    fill_df.to_csv(out_dir / "fill_rates.csv", index=False, encoding="utf-8-sig")

    summary = {
        "month": month, "created_at": datetime.now(TZ_CN).isoformat(),
        "rows": {"self": len(self_df), "fba": len(fba_df), "merged": len(merged_df)},
        "blocks": dict(blocks),
        "blanks": len(blanks),
        "invalid_original_rows": len(invalid_backup),
        "recon_95_78": {"metric_diffs": total_diff_cols, "key_diff_rows": len(recon_rows)},
        "overlap_self_fba": len(overlap_rows),
        "gs_ready_rows": {"self": len(self_df), "fba": len(fba_df), "merged": len(merged_df)},
        "gs_ready_dir": str(gs_dir),
        "violations": {"self": len(self_violations), "fba": len(fba_violations),
                       "merged": len(merged_violations)},
        "fill_rates": {
            t: round(float((fill_df[fill_df.table == t].fill_rate).mean()), 6) for t in ("self", "fba", "merged")
        },
        "inputs": {k: {"path": str(v), "sha256": hashlib.sha256(v.read_bytes()).hexdigest()}
                   for k, v in paths.items()},
        "outputs": {"self": str(self_csv), "fba": str(fba_csv), "merged": str(merged_csv)},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Phase 3.6 补全 — {month}", "",
        f"- 行数：self {len(self_df)} / FBA {len(fba_df)} / merged {len(merged_df)}",
        f"- 阻断：{summary['blocks'] or '无'}；空白 {summary['blanks']}；作废原单 {len(invalid_backup)}",
        f"- 95↔78 对账：指标合计差异 {total_diff_cols} 列 / 键级差异 {len(recon_rows)} 行；"
        f"FBA↔非FBA 重叠 {len(overlap_rows)} 条",
        f"- GS-ready 行数：self {len(self_df)} / FBA {len(fba_df)} / merged {len(merged_df)}",
        f"- 恒等违例：self {len(self_violations)} / FBA {len(fba_violations)} / merged {len(merged_violations)}",
        f"- 平均填充率：self {summary['fill_rates']['self']:.2%} / FBA {summary['fill_rates']['fba']:.2%} / "
        f"merged {summary['fill_rates']['merged']:.2%}",
        "",
        "## 低填充列（<100%）", "",
    ]
    for _, r in fill_df[fill_df.fill_rate < 1.0].sort_values("fill_rate").head(20).iterrows():
        lines.append(f"- {r['table']} / {r['column']}: {r['fill_rate']:.2%}")
    lines.append("")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return {"summary": summary, "fill_rates": fill_rows, "blanks": blanks,
            "violations": {"self": self_violations, "fba": fba_violations, "merged": merged_violations},
            "out_dir": str(out_dir)}
