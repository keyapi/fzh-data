#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""V0 replenishment action list (P90-free) — R1 fix generator.

This is the missing same-source generator for
out/replenishment_v0/actions.json. It reads ONLY the frozen V0.1 evidence and
emits the action list; it never reads model_race.json and never touches a P90
field (enforced by an accessor that raises on any key containing "p90").

R1 fixes (control/reviews/2026-10-22-v1-r1.md):
  M01 evidence input bound to the canonical (git-stored, LF) byte hash
      15d52072...; a mismatch aborts. The artifact records expected/actual
      hashes, raw and canonical byte counts, evidence blob and code commit.
  M03 horizon_stability labels are the windows actually computed (60/90/120
      days). The bogus "+30" is gone, and the artifact states that these are
      NOT the V1 action windows (V1 uses lead+30 = 90/120/150). Each window
      asserts requested_days == covered_days.
  M04 start_condition is structured: required_gates with tri-state
      ok/unproven/fail, plus outcomes and explicit forbidden transitions.
      always_replenish remains empty because the hard T2 (UOM) gate is
      unproven for 10/10. A shortfall of the supply LOWER bound never promotes
      to always_replenish. Every row whose demand view contains live SO is
      marked demand_overlap=unproven.
  N01 insufficient_evidence carries separate cause fields instead of one
      opaque label.
  N03 the invalid "cover can only add supply so it cannot change a shortage
      class" inference is removed, as is the blanket "N rows stable across
      windows" generalisation (stability is computed per row).

Output: out/replenishment_v0/actions.json
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import subprocess
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
EVIDENCE_PATH = CLAUDE_DIR / "out" / "replenishment_v0" / "evidence.json"
OUT_PATH = CLAUDE_DIR / "out" / "replenishment_v0" / "actions.json"

TITLE = "10 SKU 暂行补货行动清单（P90-free）"
DECISION_DATE = date(2026, 10, 22)

# M01 binding: the frozen V0.1 evidence, canonical (LF) bytes.
EXPECTED_EVIDENCE_SHA256 = (
    "15d52072dc5d0461f032de1a7df0b9a3a39f0c450da50366dbf63680693178ea")
EXPECTED_EVIDENCE_BYTES = 287307

# M03: the windows actually present in evidence.lead_time, lead days only.
HORIZON_WINDOWS = [
    ("remaining_3m", "remaining_3m", "决定窗 2026-10-22→2026-12-31"),
    ("L60", "L60", "提前期 60 天"),
    ("L90", "L90", "提前期 90 天"),
    ("L120", "L120", "提前期 120 天"),
]
V1_WINDOW_NOTE = ("本清单的 L60/L90/L120 是**提前期窗口本身**（60/90/120 天）；"
                  "V1（model_race）的动作窗口是 lead+30（90/120/150 天）。"
                  "两套窗口天数不同，分类与数字不可互换。")

# D9 layers, carried over verbatim from the frozen D9 decision (not recomputed).
D9_LAYER = {
    "KS0001-QDKTR-100-DEEPGREY": "暂缓",
    "KS0001-QDKTR-100-DEEPBLUE": "暂缓",
    "KS0001-XMMBS-100-HEMPNATURAL": "暂缓",
    "KS0001-CMKTR-100-DEEPBLUE": "暂缓",
    "KS0001-XMMBS-153-HEMPNATURAL": "待核实",
    "KS0001-PR-100-GREY": "暂缓",
    "KS0001-CMKTR-100-GREY": "暂缓",
    "KS0001-CMM-100-WHITE": "暂缓",
    "KS0001-HLR-100-OFFWHITE": "待核实",
    "KS0001-XMMBS-194-HEMPNATURAL": "可准备（仅准备）",
}
D9_REASON = {
    "KS0001-QDKTR-100-DEEPGREY": "同向：模型分歧；新分类只换了名字并为 P90-free 去掉派生量",
    "KS0001-QDKTR-100-DEEPBLUE": "同向",
    "KS0001-XMMBS-100-HEMPNATURAL": "变化：D9 依据的是 P90 派生区间（D10 已失效）；P50 下由到货时点决定",
    "KS0001-CMKTR-100-DEEPBLUE": "变化：D9 依据的是 P90 派生区间；P50 下去重供给仍覆盖",
    "KS0001-XMMBS-153-HEMPNATURAL": "同向：B 随 PO/在产重叠翻转，只是改用 P50 表述",
    "KS0001-PR-100-GREY": "同向",
    "KS0001-CMKTR-100-GREY": "变化：D9 依据的是 P90 派生区间；P50 下主口径覆盖、去重压力短 2",
    "KS0001-CMM-100-WHITE": "同向（但算术上已是唯一结构短缺，见 arithmetic_qualifies）",
    "KS0001-HLR-100-OFFWHITE": "同向：B 下界贴近需求，取决于在途/PO",
    "KS0001-XMMBS-194-HEMPNATURAL": "变化：D9 依据的是 P90 派生的 60 天区间；P50 下在手 360 < 859.8，必须靠在产完工",
}


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def canonical_hash(path: Path) -> dict:
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    return dict(
        raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw),
        canonical_sha256=hashlib.sha256(lf).hexdigest(), canonical_bytes=len(lf),
        crlf_count=raw.count(b"\r\n"),
        line_ending_normalization=("crlf_to_lf" if raw != lf else "none"),
    )


def git_binding(path: Path) -> dict:
    def _run(*args):
        try:
            return subprocess.run(args, capture_output=True, text=True, check=True,
                                  cwd=CLAUDE_DIR).stdout.strip()
        except Exception as exc:
            return f"unavailable: {exc.__class__.__name__}"
    try:
        top = _run("git", "rev-parse", "--show-toplevel")
        rel = path.resolve().relative_to(Path(top).resolve()).as_posix()
    except Exception:
        rel = None
    return dict(
        code_commit=_run("git", "rev-parse", "HEAD"),
        code_commit_semantics=("HEAD at run time; this artifact is committed in the "
                              "next commit, so code_commit is that commit's parent"),
        repo_relative_path=rel,
        evidence_blob_sha1=(_run("git", "rev-parse", f"HEAD:{rel}") if rel else None),
    )


def r4(x, nd=4):
    if x is None:
        return None
    if isinstance(x, int):
        return x
    v = float(x)
    if abs(v - round(v)) < 1e-9:
        return int(round(v))
    return round(v, nd)


def month_days(ym: str) -> int:
    y, m = int(ym[:4]), int(ym[5:7])
    return calendar.monthrange(y, m)[1]


class P90Guard(dict):
    """A dict that refuses to hand out any P90 field.

    The list is P90-free by construction (D10 invalidated V0.1's P90); this
    guard turns that promise into a runtime failure instead of a claim.
    """

    def __getitem__(self, key):
        if "p90" in str(key).lower():
            raise AssertionError(f"P90-free guard: attempted to read field {key!r}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if "p90" in str(key).lower():
            raise AssertionError(f"P90-free guard: attempted to read field {key!r}")
        return super().get(key, default)


def window_stats(block: dict, requested_days: int, label: str) -> dict:
    """Day accounting for a calendar window: bucket weights must sum to the
    requested days. The label must state the days actually computed (M03)."""
    buckets = block["buckets"]
    covered = sum(b["weight"] * month_days(b["month"]) for b in buckets)
    covered_days = int(round(covered))
    if covered_days != requested_days:
        raise AssertionError(
            f"window {label}: bucket days {covered_days} != requested {requested_days}")
    if f"{requested_days} 天" not in label:
        raise AssertionError(f"window label {label!r} does not state {requested_days} days")
    if "+30" in label:
        raise AssertionError(f"window label {label!r} still carries a bogus '+30'")
    start = DECISION_DATE
    end = start + timedelta(days=requested_days)
    return dict(requested_days=requested_days, covered_days=covered_days,
                start=start.isoformat(), end=end.isoformat(),
                months=r4(block.get("months")),
                buckets=[dict(month=b["month"], weight=r4(b["weight"]),
                              month_days=month_days(b["month"]))
                         for b in buckets])


# ----------------------------------------------------------------------------
# gates (M04)
# ----------------------------------------------------------------------------
def build_gates(ev_sku: dict, sup: dict, live_so: float) -> list[dict]:
    ident = ev_sku["identity"]
    inv = ev_sku["inventory"]
    po = ev_sku["po"]
    prod = ev_sku["production"]
    cover = ev_sku.get("cover") or {}
    # Cover counts as "no unbooked supply" only if its absence is proven, or it
    # is actually booked into supply. An unmapped/substitutable pool means the
    # record sum is not an upper bound.
    cover_absence_proven = bool(cover.get("absence_proven")) or bool(
        cover.get("counted_in_supply"))

    uom_status = inv.get("uom_status")
    uom_ok = bool(uom_status and str(uom_status).startswith("verified"))
    has_supply_docs = bool(po.get("open_line_count") or prod.get("remaining_qty")
                           or sup.get("intransit"))
    eta_missing = bool(po.get("eta_missing_lines") or prod.get("eta_missing_count"))
    has_prod = bool(prod.get("remaining_qty"))

    gates = [
        dict(id="G1_identity", label="客户码→单一 KS 物料",
             state=("ok" if ident.get("identity_status") == "confirmed" else "fail"),
             evidence=f"identity_status={ident.get('identity_status')}",
             owner_role="商品主数据",
             blocks_promotion="always_replenish"),
        dict(id="G2_uom", label="库存/单据单位已核实（T2 硬门）",
             state=("ok" if uom_ok else "unproven"),
             evidence=f"inventory.uom_status={uom_status}",
             owner_role="商品主数据/仓储",
             blocks_promotion="always_replenish"),
        dict(id="G3_demand_overlap", label="live SO 与预测是否为同一批需求",
             state=("unproven" if live_so > 0 else "ok"),
             evidence=(f"live SO {r4(live_so)} 件；证据只证明单据存在，未做桶级消费/分配"
                       if live_so > 0 else "无正向 live SO"),
             owner_role="业务/运营",
             blocks_promotion="任何把 SO 计入需求的动作"),
        dict(id="G4_supply_overlap", label="PO / 在途 / 在产逐笔重叠键（去重后才是数量）",
             state=("unproven" if has_supply_docs else "ok"),
             evidence=str(sup.get("overlap_status", "not_proven")),
             owner_role="数据/系统",
             blocks_promotion=("任何确定结论：去重前只能得到“记录之和”，"
                               "既不是已证下界，也不保证是紧上界")),
        dict(id="G5_arrival_in_window", label="PO 到货日 / WO 完工日在窗口内",
             state=("unproven" if (has_supply_docs and eta_missing) else
                    ("unproven" if has_supply_docs else "ok")),
             evidence=(f"PO ETA 缺失 {po.get('eta_missing_lines')} 行；"
                       f"WO 完工日缺失 {prod.get('eta_missing_count')} 张"),
             owner_role="采购/供应链；生产/PMC",
             blocks_promotion="供给下界（未证到货的批次不能计入下界）"),
        dict(id="G6_pk_ks_1to1", label="在产 PK# 皮壳按 1:1 计 KS 成品",
             state=("unproven" if has_prod else "ok"),
             evidence=(f"在产剩余 {prod.get('remaining_qty')} 件按 1:1 计入" if has_prod
                       else "无在产"),
             owner_role="生产/PMC",
             blocks_promotion="供给下界与上界（换算比例未证则数量不可用）"),
        dict(id="G7_unbooked_supply", label="不存在未上账的可替代供给（Cover 等）",
             state=("ok" if cover_absence_proven else "unproven"),
             evidence=("cover.absence_proven=True" if cover_absence_proven else
                       f"cover.verdict={cover.get('verdict')}；"
                       f"absence_proven={cover.get('absence_proven')}；"
                       "Cover 未并入供给，故实际供给可能高于记录之和"),
             owner_role="商品主数据/仓储",
             blocks_promotion="供给上界（有未上账替代供给时，记录之和不再是上界）"),
        dict(id="G8_demand_bounds", label="需求下界与上界均已给出（分位或业务人工界）",
             state="unproven",
             evidence=("P90-free 清单只有 P50 点预测：D1 是点估计不是下界，"
                       "D2=P50+SO 也不是上界；缺少需求下/上分位或业务人工上下限"),
             owner_role="业务/运营",
             blocks_promotion="任何确定结论（短缺要需求下界，充足要需求上界）"),
    ]
    for g in gates:
        if g["state"] not in ("ok", "unproven", "fail"):
            raise AssertionError(f"gate {g['id']} bad state {g['state']}")
    return gates


# R3/R4: one gate set for BOTH definite conclusions. A row may be called short
# (always_replenish) or sufficient (no_shortage_within_window) only when every
# one of these is ok AND the bound test in §R4 passes; anything less stays 待核实.
DEFINITIVE_GATES = [
    "G1_identity", "G2_uom", "G3_demand_overlap", "G4_supply_overlap",
    "G5_arrival_in_window", "G6_pk_ks_1to1", "G7_unbooked_supply",
    "G8_demand_bounds",
]


def gate(gates: list[dict], gid: str) -> dict:
    return next(g for g in gates if g["id"] == gid)


# ----------------------------------------------------------------------------
# explicit supply / demand bounds (R4)
# ----------------------------------------------------------------------------
def build_bounds(sup: dict, po: dict, prod: dict, inv: dict, d1: float, d2: float,
                 live_so: float, gates: list[dict]) -> dict:
    """Two-sided bounds with provenance.

    Shortage needs  supply upper  < demand lower .
    Sufficiency needs supply lower >= demand upper .
    `B_max` is only the record sum (a loose upper bound for as long as no
    unbooked supply exists and the unit cannot scale); it is NEVER evidence of
    sufficiency on its own.
    """
    st = {g["id"]: g["state"] for g in gates}
    uom_ok = st["G2_uom"] == "ok"
    dedup_ok = st["G4_supply_overlap"] == "ok"
    unbooked_ok = st["G7_unbooked_supply"] == "ok"
    demand_bounds_ok = st["G8_demand_bounds"] == "ok"

    po_lines = po.get("open_lines") or []
    wo_lines = prod.get("open_wo") or []
    lower_components = [dict(
        source="inventory.available", qty=r4(sup["available"]),
        documents=[], deduped=True, in_window=True, uom_converted=uom_ok,
        note="在手库存：天然在窗口内、无单据重复问题")]
    upper_components = lower_components + [
        dict(source="po.open_lines", qty=r4(sum(float(x.get("open_qty", 0)) for x in po_lines)),
             documents=[x.get("ponum") for x in po_lines],
             deduped=False, in_window=False, uom_converted=uom_ok,
             note="未去重、到货日未证；重复只会高估"),
        dict(source="production.open_wo",
             qty=r4(sum(float(x.get("remaining_qty", 0)) for x in wo_lines)),
             documents=[x.get("name") for x in wo_lines],
             deduped=False, in_window=False, uom_converted=uom_ok,
             note="PK# 计 KS 的 1:1 未证；完工日未证"),
        dict(source="inventory.intransit", qty=r4(sup["intransit"]),
             documents=[], deduped=False, in_window=False, uom_converted=uom_ok,
             note="与 PO 数值相同（10/10），可能重复；重复只会高估"),
    ]
    upper_sum = sum(float(c["qty"]) for c in upper_components)
    if abs(upper_sum - float(sup["B_max"])) > 1e-6:
        raise AssertionError(
            f"supply upper components {upper_sum} != frozen B_max {sup['B_max']}")

    supply_lower = dict(
        value=r4(sup["available"]),
        status=("ok" if (uom_ok and st["G1_identity"] == "ok") else "unproven"),
        basis=("已证下界 = 在手可用量；只计入确定在窗口内、无重复、"
               "且单位已换算的数量"),
        components=lower_components,
        excluded=[dict(source=c["source"], qty=c["qty"], reason=c["note"])
                  for c in upper_components[1:]],
        blockers=[g for g in ("G1_identity", "G2_uom") if st[g] != "ok"],
        missing_evidence=(["库存/单据单位口径（UOM）"] if not uom_ok else []),
    )
    supply_upper = dict(
        value=r4(sup["B_max"]),
        status=("ok" if (uom_ok and dedup_ok and unbooked_ok) else "unproven"),
        basis=("记录之和（每条未结记录只计一次）：重复只会高估，故方向上可作上界；"
               "但它只有在 UOM 换算已知、且不存在未上账替代供给时才是可用的上界"),
        components=upper_components,
        blockers=[g for g in ("G2_uom", "G4_supply_overlap", "G7_unbooked_supply")
                  if st[g] != "ok"],
        missing_evidence=(
            ([] if uom_ok else ["库存/单据单位口径（UOM）"]) +
            ([] if dedup_ok else ["PO/在途/在产逐笔重叠键"]) +
            ([] if unbooked_ok else ["Cover 等未上账可替代供给的缺席证明"])),
    )
    demand_lower = dict(
        value=r4(d1),
        status=("ok" if demand_bounds_ok else "unproven"),
        basis="P50 点预测（不含 live SO）；点估计不是已证下界",
        blockers=[] if demand_bounds_ok else ["G8_demand_bounds"],
        missing_evidence=[] if demand_bounds_ok else ["需求下分位或业务人工下限"],
    )
    demand_upper = dict(
        value=r4(d2),
        status=("ok" if demand_bounds_ok else "unproven"),
        basis=("P50 + 正向 live SO；SO 若与预测重复只会高估，故在方向上可作上界，"
               "但 P50 若低估则不再是上界"),
        blockers=[] if demand_bounds_ok else ["G8_demand_bounds"],
        missing_evidence=[] if demand_bounds_ok else ["需求上分位或业务人工上限"],
    )
    return dict(supply=dict(lower=supply_lower, upper=supply_upper),
                demand=dict(lower=demand_lower, upper=demand_upper),
                rule=("充足：已证供给下界 ≥ 需求上界；短缺：供给上界 < 需求下界；"
                      "其余保持待核实"))


def definitive_conclusion(gates: list[dict], bounds: dict):
    """Return (class, reason) only when BOTH the gates and the bound test pass."""
    st = {g["id"]: g["state"] for g in gates}
    if any(st[g] != "ok" for g in DEFINITIVE_GATES):
        return None, "gates"
    sl, su = bounds["supply"]["lower"], bounds["supply"]["upper"]
    dl, du = bounds["demand"]["lower"], bounds["demand"]["upper"]
    if su["status"] == "ok" and dl["status"] == "ok" and su["value"] < dl["value"]:
        return "always_replenish", "shortage_bounds"
    if sl["status"] == "ok" and du["status"] == "ok" and sl["value"] >= du["value"]:
        return "no_shortage_within_window", "sufficiency_bounds"
    return None, "bounds"


# ----------------------------------------------------------------------------
# classification
# ----------------------------------------------------------------------------
def classify(tests: dict, gates: list[dict], bounds: dict | None = None) -> dict:
    """Screening class + definitive class.

    The screening class (T3/T4) is a signal, never a conclusion. A definite
    conclusion requires every definitive gate AND the bound test (R4):
    shortage on (supply upper < demand lower), sufficiency on
    (supply lower >= demand upper). B_max >= D2 proves nothing.
    """
    blockers = [g for g in DEFINITIVE_GATES if gate(gates, g)["state"] != "ok"]
    if tests["t3"]:
        screening = "always_replenish"
    elif tests["t4"]:
        screening = "depends_on_arrival"
    else:
        screening = "insufficient_evidence"
    definitive, why = (definitive_conclusion(gates, bounds) if bounds else (None, "no_bounds"))
    if definitive:
        cls = definitive
    elif screening == "always_replenish":
        cls = "insufficient_evidence"      # never promote a screening signal
    else:
        cls = screening
    return dict(arithmetic_class=screening, screening_class=screening, cls=cls,
                promotion_blockers=blockers, definitive=definitive,
                definitive_blocked_by=why)


def horizon_class(d1: float, d2: float, sup: dict, tests: dict, gates: list[dict]):
    t3 = sup["B_max"] < d1
    t4 = sup["A_low"] < d2 <= sup["B_max"]
    return classify(dict(t1=tests["t1_identity_confirmed"],
                         t2=tests["t2_uom_verified"], t3=t3, t4=t4),
                    gates)["cls"]


# ----------------------------------------------------------------------------
# main build
# ----------------------------------------------------------------------------
def build(ev: dict, binding: dict, hash_info: dict) -> dict:
    agg = ev["aggregate"]
    rows = []
    for seq, ev_sku in enumerate(ev["skus"], 1):
        sku = ev_sku["sku"]
        sup = ev_sku["supply"]
        inv = ev_sku["inventory"]
        po = ev_sku["po"]
        prod = ev_sku["production"]
        so = ev_sku["open_so"]
        # P90 guard: only P50/F50 fields may be touched.
        dem = P90Guard(ev_sku["demand"])
        r3 = P90Guard(dem["remaining_3m"])

        d1 = float(r3["forecast_p50"])
        d2 = float(r3["p50"])
        live_so = float(r3["open_so"])
        supply = dict(
            available=sup["available"], intransit=sup["intransit"],
            open_po_raw=sup["open_po_raw"], open_po_dedup=sup["open_po_dedup"],
            po_duplicate_candidate=po.get("duplicate_candidate_qty", 0),
            open_po_lines=po.get("open_line_count", 0),
            po_eta_missing_lines=po.get("eta_missing_lines", 0),
            production_gross=prod.get("gross_qty", 0),
            production_remaining=prod.get("remaining_qty", 0),
            open_wo=len(prod.get("open_wo", [])),
            stopped_qty=prod.get("stopped_qty", 0),
            draft_wo=len(prod.get("draft_wo", [])),
            A_low=sup["A_low"], A_high=sup["A_high"],
            B_min=sup["B_min"], B_max=sup["B_max"],
            B_min_po_dedup=sup["B_min_po_dedup"],
            B_max_po_dedup=sup["B_max_po_dedup"],
            intransit_equals_po_dedup=bool(sup.get("intransit_equals_po_dedup")),
        )
        tests = dict(
            t1_identity_confirmed=ev_sku["identity"]["identity_status"] == "confirmed",
            t2_uom_verified=str(inv.get("uom_status", "")).startswith("verified"),
            t3_bmax_lt_d1=supply["B_max"] < d1,
            t4_a_low_lt_d2_le_bmax=supply["A_low"] < d2 <= supply["B_max"],
            screening_only=True,
            screening_note=("T3/T4 只用冻结值做筛查（B_max 是记录之和、A_low 是在手），"
                            "不是结论；确定结论必须走 bounds 检验"),
        )
        gates = build_gates(ev_sku, sup, live_so)
        bounds = build_bounds(sup, po, prod, inv, d1, d2, live_so, gates)
        cl = classify(dict(t1=tests["t1_identity_confirmed"],
                           t2=tests["t2_uom_verified"],
                           t3=tests["t3_bmax_lt_d1"], t4=tests["t4_a_low_lt_d2_le_bmax"]),
                      gates, bounds)
        # R4 counterexample guard (review's XMMBS-100 case): when the record sum
        # clears the demand upper bound but the dedup-stress point does not, an
        # "all records are the same supply" reading makes the row short. Under R4
        # neither reading can be certified, so it must stay 待核实.
        trap_active = (supply["B_max"] >= d2
                       and supply["B_min_po_dedup"] < d2)
        counterexample = dict(
            active=bool(trap_active),
            record_sum=supply["B_max"],
            dedup_stress_point=supply["B_min_po_dedup"],
            demand_upper=r4(d2),
            note=("若未结记录属同一批供应，唯一供给可低至 {:.1f}；而记录之和 {:.1f} "
                  "仍 ≥ 需求上界 {:.1f}。旧规则会用记录之和判“不缺”；"
                  "R4 要求已证供给下界覆盖需求上界，两者都未证，只能待核实"
                  ).format(supply["B_min_po_dedup"], supply["B_max"], d2)
            if trap_active else "该行不存在“记录之和够、去重后不够”的陷阱",
        )

        # ---- horizon windows (M03) ----
        stab = []
        for wkey, lkey, label_base in HORIZON_WINDOWS:
            if lkey == "remaining_3m":
                block, days = r3, int(r3["days"])
            else:
                block = P90Guard(ev_sku["lead_time"][lkey])
                days = int(block["days"])
            label = f"{label_base}（窗口 {days} 天）"
            ws = window_stats(block, days, label)
            wd1 = float(block["forecast_p50"])
            wd2 = float(block["p50"])
            cls_here = horizon_class(wd1, wd2, supply, tests, gates)
            stab.append(dict(
                window=wkey, label=label,
                requested_days=ws["requested_days"],
                covered_days=ws["covered_days"],
                start=ws["start"], end=ws["end"],
                d1_p50_forecast=r4(wd1),
                d2_p50_plus_live_so=r4(wd2),
                t3_bmax_lt_d1=supply["B_max"] < wd1,
                t4_a_low_lt_d2_le_bmax=supply["A_low"] < wd2 <= supply["B_max"],
                class_if_evaluated_here=cls_here,
            ))
        classes_here = [w["class_if_evaluated_here"] for w in stab]
        stable = len(set(classes_here)) == 1
        if stable:
            note = "四个窗口同规则判定一致（remaining_3m / L60 60 天 / L90 90 天 / L120 120 天）"
        else:
            diff = [f"{w['window']}={w['class_if_evaluated_here']}"
                    for w in stab if w["class_if_evaluated_here"] != cl["cls"]]
            note = ("窗口间不一致：" + "；".join(diff) +
                    "（各窗口 requested_days 与 covered_days 已逐项断言相等）")
        if cl["cls"] != classes_here[0]:
            raise AssertionError(f"{sku}: decision-window class mismatch")

        gaps = dict(
            bmax_minus_d1=r4(supply["B_max"] - d1),
            bmax_minus_d2=r4(supply["B_max"] - d2),
            bmin_minus_d2=r4(supply["B_min"] - d2),
            bmin_po_dedup_minus_d2=r4(supply["B_min_po_dedup"] - d2),
            bmin_po_dedup_margin_pct_of_d2=(
                r4(100 * (supply["B_min_po_dedup"] - d2) / d2, 1) if d2 > 1e-9 else None),
            duplicate_po_share_of_bmax_pct=(
                r4(100 * supply["po_duplicate_candidate"] / supply["B_max"], 1)
                if supply["B_max"] > 1e-9 else None),
            d1_shortfall_vs_bmax_pct=(
                r4(100 * (d1 - supply["B_max"]) / supply["B_max"], 1)
                if supply["B_max"] > 1e-9 else None),
        )

        rows.append(dict(
            seq=seq,
            evidence_priority=None,      # filled after ranking, below
            priority_tier=None,
            sku=sku,
            customer_code=ev_sku["customer_code"],
            item_name=ev_sku["identity"].get("item_name"),
            **{"class": cl["cls"]},
            screening_class=cl["screening_class"],
            definitive_conclusion=cl["definitive"],
            definitive_blocked_by=cl["definitive_blocked_by"],
            bounds=bounds,
            r4_counterexample=counterexample,
            arithmetic_qualifies=("always_replenish" if tests["t3_bmax_lt_d1"] else None),
            arithmetic_class=cl["arithmetic_class"],
            promotion_blockers=cl["promotion_blockers"],
            demand_overlap=("unproven" if live_so > 0 else "not_applicable"),
            demand_overlap_note=(
                "live SO 与 P50 是否同一批需求未证；未做桶级消费/分配前，D2 不能当净需求"
                if live_so > 0 else "无正向 live SO"),
            supply=supply,
            demand=dict(
                D1_p50_forecast=r4(d1), D2_p50_plus_live_so=r4(d2),
                live_so=r4(live_so),
                dead_so_excluded=ev_sku["demand"]["dead_so_excluded"],
                over_delivery_not_netted=ev_sku["demand"]["over_delivery_not_netted"],
                forecast_model=ev_sku["forecast"]["primary_model"],
                forecast_confidence=ev_sku["forecast"]["confidence"],
                history_months=ev_sku["forecast"]["history_months"],
                run_rate_ratio=ev_sku["forecast"]["run_rate_ratio"],
                recent3_mean=ev_sku["forecast"]["recent3_mean"],
                d2_overlap_status=("unproven: live SO may or may not be the same demand "
                                   "the P50 already covers"),
            ),
            gaps=gaps,
            tests=tests,
            gates=gates,
            horizon_stability=stab,
            class_horizon_stable=stable,
            class_horizon_note=note,
            arithmetic_qualifies_at_windows=[w["window"] for w in stab
                                             if w["t3_bmax_lt_d1"]],
            insufficient_evidence_causes=(
                dict(
                    demand_side=("SO 与预测重叠未证" if live_so > 0 else None),
                    supply_side=("PO/WO/在途重叠或到货日未证"
                                 if (supply["open_po_raw"] or supply["intransit"]
                                     or supply["production_remaining"]) else None),
                    unit_side=("库存 UOM 未证" if not tests["t2_uom_verified"] else None),
                    candidate_divergence=("P90-free 清单只有单一 P50 模型，"
                                          "候选分歧不在本清单判定内"),
                    calibration_insufficiency=("P90-free 清单不做区间校准，"
                                               "校准不足不在本清单判定内"),
                ) if cl["cls"] == "insufficient_evidence" else None),
        ))

    # priority tier / evidence priority (same rule as V0)
    def tier_of(row):
        s, t, g = row["supply"], row["tests"], row["gaps"]
        if t["t3_bmax_lt_d1"]:
            return 1
        if t["t4_a_low_lt_d2_le_bmax"] and (
                g["bmin_po_dedup_margin_pct_of_d2"] is not None
                and g["bmin_po_dedup_margin_pct_of_d2"] < 10
                or (g["duplicate_po_share_of_bmax_pct"] or 0) >= 25):
            return 2
        if t["t4_a_low_lt_d2_le_bmax"]:
            return 3
        return 4

    for row in rows:
        row["priority_tier"] = tier_of(row)
    # Same ordering as V0: tier, then the dedup-stress margin (thinnest first),
    # then report sequence. Keeps evidence_priority stable across regenerations.
    order = sorted(rows, key=lambda r: (
        r["priority_tier"],
        r["gaps"]["bmin_po_dedup_margin_pct_of_d2"]
        if r["gaps"]["bmin_po_dedup_margin_pct_of_d2"] is not None else 9e9,
        r["seq"]))
    for i, row in enumerate(order, 1):
        row["evidence_priority"] = i

    counts = dict(
        skus_in=len(ev["skus"]), skus_out=len(rows),
        excluded=len(ev["skus"]) - len(rows),
        always_replenish=sum(1 for r in rows if r["class"] == "always_replenish"),
        depends_on_arrival=sum(1 for r in rows if r["class"] == "depends_on_arrival"),
        insufficient_evidence=sum(1 for r in rows if r["class"] == "insufficient_evidence"),
        arithmetic_qualifies_always_replenish=sum(
            1 for r in rows if r["arithmetic_qualifies"] == "always_replenish"),
        class_horizon_stable=sum(1 for r in rows if r["class_horizon_stable"]),
        class_horizon_unstable=sum(1 for r in rows if not r["class_horizon_stable"]),
        by_class={c: [r["sku"] for r in rows if r["class"] == c]
                  for c in ("always_replenish", "depends_on_arrival",
                            "insufficient_evidence")},
        demand_overlap_unproven=sum(1 for r in rows if r["demand_overlap"] == "unproven"),
        definitive_shortage=sum(1 for r in rows if r["definitive_conclusion"] == "always_replenish"),
        definitive_sufficiency=sum(
            1 for r in rows
            if r["definitive_conclusion"] == "no_shortage_within_window"),
        definitive_pending=sum(1 for r in rows if r["definitive_conclusion"] is None),
        pending_blocked_by=dict(
            gates=sum(1 for r in rows if r["definitive_blocked_by"] == "gates"),
            bounds=sum(1 for r in rows if r["definitive_blocked_by"] == "bounds")),
        screening=dict(
            t3=sum(1 for r in rows if r["tests"]["t3_bmax_lt_d1"]),
            t4=sum(1 for r in rows if r["tests"]["t4_a_low_lt_d2_le_bmax"]),
            neither=sum(1 for r in rows if not r["tests"]["t3_bmax_lt_d1"]
                        and not r["tests"]["t4_a_low_lt_d2_le_bmax"]),
            note="screening 只是信号；确定结论数见 definitive_*"),
        counterexample_traps=sum(1 for r in rows
                                 if r["r4_counterexample"]["active"]),
    )

    totals = dict(
        window="2026-10-22 -> 2026-12-31",
        available=sum(int(r["supply"]["available"]) for r in rows),
        intransit=sum(int(r["supply"]["intransit"]) for r in rows),
        open_po_raw=sum(int(r["supply"]["open_po_raw"]) for r in rows),
        production_remaining=sum(int(r["supply"]["production_remaining"]) for r in rows),
        A_low=sum(int(r["supply"]["A_low"]) for r in rows),
        A_high=sum(int(r["supply"]["A_high"]) for r in rows),
        B_min=sum(int(r["supply"]["B_min"]) for r in rows),
        B_max=sum(int(r["supply"]["B_max"]) for r in rows),
        D1=r4(sum(r["demand"]["D1_p50_forecast"] for r in rows)),
        D2=r4(sum(r["demand"]["D2_p50_plus_live_so"] for r in rows)),
        live_so=sum(int(r["demand"]["live_so"]) for r in rows),
        dead_so=sum(int(r["demand"]["dead_so_excluded"]) for r in rows),
        over_delivery=sum(int(r["demand"]["over_delivery_not_netted"]) for r in rows),
        note="totals are cross-checks of the frozen evidence, not an aggregate demand or supply plan",
    )
    # totals must equal the frozen aggregate
    checks = [
        ("available", totals["available"], agg["available_total"]),
        ("intransit", totals["intransit"], agg["intransit_total"]),
        ("open_po_raw", totals["open_po_raw"], agg["open_po_raw_total"]),
        ("A_low", totals["A_low"], agg["supply_A_low_total"]),
        ("A_high", totals["A_high"], agg["supply_A_high_total"]),
        ("B_min", totals["B_min"], agg["supply_B_min_total"]),
        ("B_max", totals["B_max"], agg["supply_B_max_total"]),
        ("live_so", totals["live_so"], agg["open_so_live_total"]),
        ("dead_so", totals["dead_so"], agg["dead_so_total"]),
        ("over_delivery", totals["over_delivery"], agg["negative_over_delivery_total"]),
    ]
    for name, got, want in checks:
        if abs(float(got) - float(want)) > 1e-6:
            raise AssertionError(f"aggregate mismatch {name}: {got} != {want}")

    # P90-free assertion on everything we are about to write
    blob = json.dumps(dict(rows=rows, totals=totals), ensure_ascii=False).lower()
    for bad in ("p90_3m", "forecast_p90", '"p90_status"'):
        if bad in blob:
            raise AssertionError(f"P90-free guard: output contains {bad}")

    rule = dict(
        horizon_primary="remaining_3m: 2026-10-22 -> 2026-12-31 (calendar-integrated, decision time 2026-10-22)",
        D1="demand.remaining_3m.forecast_p50 (P50 point forecast, live SO excluded)",
        D2="demand.remaining_3m.p50 (= D1 + positive live open SO; SO<->forecast overlap unproven, may double count)",
        supply_A="A_low = available; A_high = available + open production remaining (no PO, no intransit)",
        supply_B="B_min = available + max(raw PO, production remaining, intransit) (maximum overlap); B_max = available + raw PO + production remaining + intransit (no overlap)",
        tests=dict(
            t1="identity_status == confirmed",
            t2="inventory.uom_status is a verified unit basis (false for 10/10: unknown_conditional)",
            t3="B_max < D1 (short even at the most generous supply bound, on the P50 forecast)",
            t4="A_low < D2 <= B_max (conclusion flips between on-hand-only and all-arrivals)",
        ),
        assignment=[
            "always_replenish <= t3 and t1 and t2 and every required gate is ok",
            "depends_on_arrival <= not t3 and t4",
            "insufficient_evidence <= otherwise",
            "supply lower bound (B_min, B_min_po_dedup) below demand NEVER promotes a row: it only shows a shortage scenario exists",
        ],
        gates=dict(
            states=["ok", "unproven", "fail"],
            definitive_conclusion_gates=DEFINITIVE_GATES,
            hard_gates_for_always=DEFINITIVE_GATES,
            note=("R4: 短缺与充足都必须过同一组 8 个 definitive gates，"
                  "并各自通过双边界检验。G7（无未上账替代供给）保证记录之和仍是上界；"
                  "G8（需求上下界）保证需求侧有真实界而不是把 P50 当界。"
                  "G4 只表示逐笔关系已核实，不代表记录互不重叠。"),
        ),
        bounds=dict(
            rule=("充足：已证供给下界 ≥ 需求上界；短缺：供给上界 < 需求下界；"
                  "其余保持待核实"),
            supply_lower=("在手 available，且仅在 G1/G2 ok 时才算已证（天然在窗口内、"
                          "无单据重复问题）"),
            supply_upper=("available + 未结 PO 原始量 + 在产剩余 + 在途（每条只计一次；"
                          "重复只会高估，方向上可作上界；需 G2/G4/G7 才可当作可用上界）"),
            demand_lower="D1 = P50，不含 live SO；点估计不是已证下界（需 G8）",
            demand_upper=("D2 = P50 + 正向 live SO；SO 若重复只会高估，方向上可作上界，"
                          "但 P50 若低估则不再是上界（需 G8）"),
            forbidden="B_max ≥ D2 永远不能证明充足：B_max 是记录之和，不是已证下界",
        ),
        cover_treatment=(
            "cover is not counted in supply (V0). It is an unbooked upside supply "
            "scenario: once alias mapping and substitutability are confirmed it may "
            "REMOVE a shortage and the row must be recomputed; it can never create a "
            "shortage. It is NOT evidence that a shortage cannot occur while unmapped."),
        window_basis=dict(
            note=V1_WINDOW_NOTE,
            requested_vs_covered="every window asserts requested_days == covered_days",
        ),
        priority_tier={
            "1": "t3: structurally short at B_max",
            "2": "t4 and (dedup-stress B_min - D2 < 10% of D2 or duplicate PO share >= 25% of B_max)",
            "3": "t4, other",
            "4": "no arrival lever; short only when live SO is added (D2)",
            "note": "tier orders evidence urgency, not purchase urgency",
        },
    )

    # start conditions (M04) are built from the row's gates
    for row in rows:
        row["start_condition"] = start_condition(row)
        row["missing_evidence"] = missing_evidence(row)
        row["responsible_role"] = responsible_role(row)
        row["decisive_unknown"] = decisive_unknown(row)
        row["basis"] = basis(row)

    d9 = [dict(sku=r["sku"], d9_layer=D9_LAYER.get(r["sku"]),
               v0_actions_class=r["class"], reason=D9_REASON.get(r["sku"]))
          for r in rows]

    residual = residual_unknowns(rows, ev)

    reconciliation = dict(
        skus_in=len(ev["skus"]), skus_out=len(rows),
        excluded=[],
        dropped_rows=[],
        class_sum=(f"{counts['always_replenish']} + {counts['depends_on_arrival']} + "
                   f"{counts['insufficient_evidence']} = {len(rows)}"),
        test_count=dict(
            t3_true=sum(1 for r in rows if r["tests"]["t3_bmax_lt_d1"]),
            t4_true=sum(1 for r in rows if r["tests"]["t4_a_low_lt_d2_le_bmax"]),
            neither=sum(1 for r in rows if not r["tests"]["t3_bmax_lt_d1"]
                        and not r["tests"]["t4_a_low_lt_d2_le_bmax"]),
        ),
        against_frozen_aggregate="10 项合计逐项相等（available 1,015 / intransit 1,184 / "
                                 "PO raw 1,465 / A 1,015–3,205 / B 3,953–5,854 / live SO "
                                 "2,924 / dead SO 1,675 / over -907）",
        class_horizon=dict(stable=counts["class_horizon_stable"],
                           unstable=counts["class_horizon_unstable"],
                           per_row={r["sku"]: r["class_horizon_stable"] for r in rows},
                           note=("computed per row; no blanket 'N rows agree across "
                                 "windows' claim")),
        d9_mapping="10/10 行给出 D9 层级 -> 新分类的对应与差异原因，不静默替换",
        unmatched_reason=("入 10 客户码全部在 evidence.skus 中且 identity_status=confirmed；"
                          "无未匹配记录，故无丢弃项"),
        bounds=dict(
            supply_lower_proven=sum(1 for r in rows
                                    if r["bounds"]["supply"]["lower"]["status"] == "ok"),
            supply_upper_proven=sum(1 for r in rows
                                    if r["bounds"]["supply"]["upper"]["status"] == "ok"),
            demand_lower_proven=sum(1 for r in rows
                                    if r["bounds"]["demand"]["lower"]["status"] == "ok"),
            demand_upper_proven=sum(1 for r in rows
                                    if r["bounds"]["demand"]["upper"]["status"] == "ok"),
            rows_with_all_four_proven=sum(
                1 for r in rows if all(r["bounds"][s][k]["status"] == "ok"
                                       for s in ("supply", "demand")
                                       for k in ("lower", "upper"))),
            note=("四侧界分别计数；任何一侧 unproven 都不会产出确定结论。"
                  "supply.upper 的数量 = 冻结 B_max，但其 status 必须另过 G2/G4/G7。"),
        ),
    )

    return dict(
        schema_version="replenishment_actions_v0/3",
        title=TITLE,
        status="provisional; not an instruction list; no quantities",
        owner="claude-worker",
        generated_at=__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        revision="R2 (R1 review fixes: M01/M03/M04/N01/N03)",
        based_on=dict(
            fixed_commit=binding.get("code_commit"),
            commit_semantics=binding.get("code_commit_semantics"),
            inputs=[dict(
                path=binding.get("repo_relative_path"),
                sha256=hash_info["canonical_sha256"],
                sha256_expected=EXPECTED_EVIDENCE_SHA256,
                bytes=hash_info["canonical_bytes"],
                bytes_expected=EXPECTED_EVIDENCE_BYTES,
                sha256_raw=hash_info["raw_sha256"],
                raw_bytes=hash_info["raw_bytes"],
                line_ending_normalization=hash_info["line_ending_normalization"],
                crlf_count=hash_info["crlf_count"],
                blob_sha1=binding.get("evidence_blob_sha1"),
            )],
            hash_binding_verified=True,
            later_workspace_changes_used=False,
            note=("只读冻结 evidence.json（canonical LF 字节 hash 绑定，失配即拒）；"
                  "未读取 model_race.json / 任何 P90 字段"),
        ),
        guards=dict(
            p90_used=False, p90_based_recommendations_used=False,
            order_quantities_emitted=False, production_accessed=False,
            en_or_sku_map_modified=False, scope_expanded=False,
            dead_so_excluded=True, over_delivery_not_netted=True,
            hash_binding_enforced=True,
            p90_free_runtime_guard=True,
        ),
        rule=rule,
        counts=counts,
        totals=totals,
        rows=rows,
        d9_mapping=d9,
        residual_unknowns=residual,
        reconciliation=reconciliation,
    )


# ----------------------------------------------------------------------------
# per-row prose, generated from the row's own numbers (never hand-typed values)
# ----------------------------------------------------------------------------
def start_condition(row: dict) -> dict:
    s, d, g, t = row["supply"], row["demand"], row["gaps"], row["tests"]
    gates = row["gates"]
    st = {x["id"]: x["state"] for x in gates}
    d2 = d["D2_p50_plus_live_so"]
    # Which supply level actually falls below D2? Never assert a rule that the
    # row's own numbers contradict.
    shortfalls = []
    if s["B_min_po_dedup"] < d2 and s["B_min_po_dedup"] != s["B_min"]:
        shortfalls.append("去重压力下 B_min {:.1f} < D2 {:.1f}".format(
            s["B_min_po_dedup"], d2))
    if s["B_min"] < d2:
        shortfalls.append("最大重叠下 B_min {:.1f} < D2 {:.1f}".format(s["B_min"], d2))
    if s["A_high"] < d2:
        shortfalls.append("只在手+在产 A_high {:.1f} < D2 {:.1f}（到货落在窗口外）".format(
            s["A_high"], d2))
    if s["A_low"] < d2:
        shortfalls.append("只在手 A_low {:.1f} < D2 {:.1f}".format(s["A_low"], d2))
    lower_bound_shortfall = (s["B_min"] < d2) or (s["B_min_po_dedup"] < d2)
    b = row["bounds"]
    sl, su = b["supply"]["lower"], b["supply"]["upper"]
    dl, du = b["demand"]["lower"], b["demand"]["upper"]
    bound_blockers = sorted({x for x in (
        su["blockers"] + dl["blockers"] + sl["blockers"] + du["blockers"])})
    # R4: definitive conclusions are bound tests, never "B_max >= D2".
    outcomes = [
        dict(when=("8 门全 ok ∧ "
                   "供给上界（当前记录之和 {:.1f}，未证 UOM/去重则不可用）"
                   " < 需求下界（当前 P50 {:.1f}，未证分位则不可用）").format(
                       su["value"], dl["value"]),
             then_class="always_replenish",
             uses=["supply.upper", "demand.lower"],
             arithmetic="短缺：连供给上界都低于需求下界"),
        dict(when=("8 门全 ok ∧ "
                   "供给下界（当前在手 {:.1f}）"
                   " ≥ 需求上界（当前 P50+SO {:.1f}）").format(
                       sl["value"], du["value"]),
             then_class="no_shortage_within_window",
             uses=["supply.lower", "demand.upper"],
             arithmetic=("充足只能由“已证供给下界 ≥ 需求上界”支持；"
                         "冻结的 B_max {:.1f} 不是已证下界，不能用来证明充足").format(su["value"])),
        dict(when="任一闸门 unproven/fail，或任一侧界 unproven",
             then_class="insufficient_evidence",
             uses=[],
             arithmetic=("维持待核实；当前缺：" + "、".join(bound_blockers)
                         if bound_blockers else "维持待核实")),
    ]
    blocking = [x for x in gates if x["id"] in DEFINITIVE_GATES and x["state"] != "ok"]
    return dict(
        rule=("R4 双向界规则：充足 = 已证供给下界 ≥ 需求上界；短缺 = 供给上界 < 需求下界；"
              "两侧数量都必须来自按证据去重并换算（UOM）后的窗口内数量；"
              "B_max 只是记录之和，永远不能单独证明充足"),
        demand_bounds_used=dict(lower="D1（P50，不含 SO）", upper="D2（P50 + 正向 live SO）"),
        demand_overlap=row["demand_overlap"],
        supply_bounds=dict(lower=sl, upper=su),
        demand_bounds=dict(lower=dl, upper=du),
        bound_blockers=bound_blockers,
        supply_lower_bound_shortfall=lower_bound_shortfall,
        supply_lower_bound_shortfall_note=(
            "B_min/B_min_po_dedup < D2 只说明存在短缺情景；在 R4 规则下，"
            "短缺需要“供给上界 < 需求下界”，下界不足本身不构成任何结论"
            if lower_bound_shortfall else
            "下界未低于 D2；短缺情景来自到货时点/在手不足，同样不构成结论"),
        binding_shortfall_conditions=shortfalls,
        required_gates=[dict(id=x["id"], label=x["label"], state=x["state"],
                             owner_role=x["owner_role"], evidence_needed=x["evidence"],
                             blocks=x["blocks_promotion"]) for x in gates],
        gates_required_for_definitive_conclusion=DEFINITIVE_GATES,
        gates_required_for_shortage=DEFINITIVE_GATES,
        gates_required_for_sufficiency=DEFINITIVE_GATES,
        gate_summary=st,
        outcomes=outcomes,
        forbidden=[
            "B_max >= D2 never proves sufficiency: B_max is the record sum, and G4 only "
            "means line-level overlap was checked, not that records are disjoint",
            "sufficiency requires a proven supply LOWER bound covering a demand UPPER bound",
            "shortage requires a supply UPPER bound below a demand LOWER bound",
            "SO overlapping the forecast never means SO can be deleted: bucket-level consumption first",
            "arrival/ completion dates alone never establish sufficiency",
            "supply lower bound below demand never promotes to always_replenish",
            "live SO in the demand view never becomes net demand before bucket-level consumption",
            "Cover or any unbooked supply never counts until mapping and substitutability are proven",
        ],
        summary=("补齐 " + "、".join(sorted({x["id"] for x in blocking} |
                                            set(bound_blockers))) +
                 " 后按 outcomes 重算；在此之前不发起采购/生产指令，也不宣布“不缺”。")
        if (blocking or bound_blockers) else
        "全部闸门与四侧界已 ok；仍须按 outcomes 重算一次再行动。",
    )


def missing_evidence(row: dict) -> list[dict]:
    s, d = row["supply"], row["demand"]
    sku = row["sku"]
    out = []
    if s["open_po_lines"]:
        out.append(dict(item=f"{s['open_po_lines']}/{s['open_po_lines']} 条未结 PO 的实际到货日",
                        owner_role="采购/供应链",
                        why_it_changes_answer=f"ETA 缺失 {s['po_eta_missing_lines']} 行；"
                                              "决定能否算窗口内到货"))
    if s["po_duplicate_candidate"]:
        out.append(dict(item=f"重复候选 PO {s['po_duplicate_candidate']} 件是否为同一笔",
                        owner_role="采购/供应链",
                        why_it_changes_answer="决定 B 取下界还是上界"))
    if s["open_wo"]:
        out.append(dict(item=f"{s['open_wo']}/{s['open_wo']} 张开放 WO 的 planned_end_date"
                             + (f"；{s['draft_wo']} 张 Draft WO 是否释放" if s["draft_wo"] else ""),
                        owner_role="生产/PMC",
                        why_it_changes_answer=f"在产剩余 {s['production_remaining']} 无日期"))
    if s["production_remaining"]:
        out.append(dict(item="PK#→KS 是否 1:1 计入", owner_role="生产/PMC",
                        why_it_changes_answer="在产 1:1 未证；若不成立在产量需重算（只会向下）"))
    if s["intransit"] or s["open_po_raw"]:
        out.append(dict(item=f"在途 {s['intransit']} 与去重 PO {s['open_po_dedup']} 的逐笔关单键",
                        owner_role="数据/系统（worker）",
                        why_it_changes_answer=f"决定 B 取 {s['B_min']} 还是 {s['B_max']}"))
    if d["live_so"]:
        out.append(dict(item=f"live SO {d['live_so']} 件是否与 P50 指向同一批需求",
                        owner_role="业务/运营",
                        why_it_changes_answer="决定 D2 是增量还是重复；决定本行是否结构短缺"))
    if d["dead_so_excluded"]:
        out.append(dict(item=f"死单 SO {d['dead_so_excluded']} 件是否补发",
                        owner_role="业务/运营",
                        why_it_changes_answer="未计入需求；若补发则需求上移"))
    out.append(dict(item="库存 UOM 是否为“件”", owner_role="商品主数据/仓储",
                    why_it_changes_answer="单位未证时，任何短缺幅度都不能当结论"))
    if sku in ("KS0001-CMM-100-WHITE", "KS0001-XMMBS-194-HEMPNATURAL"):
        out.append(dict(item="Cover 无映射（scenario）能否替代",
                        owner_role="商品主数据/仓储",
                        why_it_changes_answer=("若有 cover 且映射成立，可减少/消除短缺情景，需重算"
                                                "（不能据此断定不缺）")))
    return out


def responsible_role(row: dict) -> str:
    s = row["supply"]
    roles = []
    if s["open_po_lines"]:
        roles.append("采购/供应链（PO ETA/重复）")
    if s["open_wo"]:
        roles.append("生产/PMC（WO 完工日）")
    if row["demand"]["live_so"]:
        roles.append("业务/运营（需求口径）")
    if not row["tests"]["t2_uom_verified"]:
        roles.append("商品主数据/仓储（UOM）")
    return "；".join(roles)


def decisive_unknown(row: dict) -> str:
    s, d, t = row["supply"], row["demand"], row["tests"]
    if t["t3_bmax_lt_d1"]:
        return "UOM 口径（唯一算术上已短缺的 SKU，卡在单位未证与低置信预测）"
    if t["t4_a_low_lt_d2_le_bmax"]:
        if s["po_duplicate_candidate"]:
            return (f"PO 是否重复（去重后 B_min {s['B_min_po_dedup']} vs D2 "
                    f"{d['D2_p50_plus_live_so']}），以及到货能否在窗口内")
        return ("到货/完工时点与重叠："
                f"在产 {s['production_remaining']}、PO {s['open_po_raw']}、在途 {s['intransit']}")
    return "需求口径：live SO 是否与 P50 重叠，以及旺势是否延续"


def basis(row: dict) -> str:
    s, d, t, g = row["supply"], row["demand"], row["tests"], row["gaps"]
    parts = [
        f"可供上限 B_max {s['B_max']} vs D1 {d['D1_p50_forecast']}、D2 {d['D2_p50_plus_live_so']}。",
        f"在手 A_low {s['A_low']}；B_min {s['B_min']}（最大重叠，去重压力 {s['B_min_po_dedup']}）。",
    ]
    if t["t3_bmax_lt_d1"]:
        parts.append(f"即使全部到货也不够 D1，缺 {r4(d['D1_p50_forecast'] - s['B_max'])}"
                     f"（占 B_max {g['d1_shortfall_vs_bmax_pct']}%）。")
    elif t["t4_a_low_lt_d2_le_bmax"]:
        parts.append("结论只在“全部到货且不重叠”与“重叠/迟到”两个情景之间翻转；"
                     "两个方向都要过同一组 8 个 definitive gates，并且短缺看"
                     "“供给上界 < 需求下界”、充足看“供给下界 ≥ 需求上界”，"
                     "闸门与界未齐前只作待核实。")
    else:
        parts.append("B_max 覆盖 D1；只有在 live SO 确为增量、且完成桶级消费后才可能短缺。")
    parts.append(f"需求口径比值 {d['run_rate_ratio']}（近 3 月均值 {d['recent3_mean']}）。")
    if row["demand_overlap"] == "unproven":
        parts.append("所有含 SO 的判断均标 demand_overlap=unproven。")
    return "".join(parts)


def residual_unknowns(rows: list[dict], ev: dict) -> list[dict]:
    agg = ev["aggregate"]
    return [
        dict(item="PO ETA 空",
             count=f"{agg['open_po_line_count']} 行 / {agg['open_po_raw_total']:,} 件 / "
                   f"{agg['open_po_sku_count']} SKU",
             impact="无法确认能否在窗口内到货；B 是到货假设"),
        dict(item="在产无日期",
             count=f"{agg['open_wo_count']} 张开放 WO planned_end_date 全空",
             impact="计入供给但到货日未确认"),
        dict(item="PK# -> KS 1:1", count="10/10 SKU",
             impact="在产按 1:1 计入 KS 成品；未证，若不成立在产量需重算（只会向下）"),
        dict(item="库存 UOM", count="10/10 SKU unknown_conditional",
             impact="按件计数、未换算；T2 因此 10/10 不成立，always 层为空"),
        dict(item="Cover 可替代", count="10/10 未证（4 个无映射 scenario）",
             impact="不上账；确认映射与可替代后可重算并可能消除短缺，但未证前不能当作“不缺”"),
        dict(item="PO <-> 在途 / 在产 重叠",
             count=f"10/10（在途与去重 PO 数值一致 {agg['intransit_equals_po_dedup_skus']}/10）",
             impact="只发 B_min/B_max 边界，不发单点"),
        dict(item="SO <-> 预测重叠", count=f"{len(rows)}/10",
             impact="D2 可能重复计算未来需求；所有含 SO 动作 demand_overlap=unproven"),
        dict(item="单据/库存时点", count="SO/WO 10-20/21 vs 库存 10-22（1–2 天）",
             impact="未桥接；时点情景，不伪造对平"),
        dict(item="断货删失", count="stock_history 仅 3 天",
             impact="历史需求可能低估；未校正"),
        dict(item="取消/退货", count="gs_orders 无状态字段",
             impact="未剔除；若源表只含发货行则无影响，未证"),
        dict(item="死单 SO", count=f"{agg['dead_so_total']:,} 件",
             impact="未计入需求；若确认补发需另加"),
        dict(item="超发 SO", count=f"{agg['negative_over_delivery_total']:,} 件",
             impact="不冲抵其他行；净额仅对照"),
    ]


def main():
    global EVIDENCE_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(OUT_PATH))
    ap.add_argument("--evidence", default=str(EVIDENCE_PATH))
    args = ap.parse_args()
    EVIDENCE_PATH = Path(args.evidence).resolve()

    hash_info = canonical_hash(EVIDENCE_PATH)
    if hash_info["canonical_sha256"] != EXPECTED_EVIDENCE_SHA256:
        raise SystemExit(
            "evidence content mismatch: expected canonical sha256 "
            f"{EXPECTED_EVIDENCE_SHA256} ({EXPECTED_EVIDENCE_BYTES} bytes LF), got "
            f"{hash_info['canonical_sha256']} ({hash_info['canonical_bytes']} bytes LF; "
            f"raw {hash_info['raw_sha256']}, {hash_info['raw_bytes']} bytes). Refusing "
            "to write an action list on an unbound input.")
    if hash_info["canonical_bytes"] != EXPECTED_EVIDENCE_BYTES:
        raise SystemExit(
            f"evidence size mismatch: expected canonical {EXPECTED_EVIDENCE_BYTES}, "
            f"got {hash_info['canonical_bytes']}")
    binding = git_binding(EVIDENCE_PATH)

    with EVIDENCE_PATH.open("r", encoding="utf-8") as f:
        ev = json.load(f)

    out = build(ev, binding, hash_info)
    out_path = Path(args.json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    print(f"evidence canonical sha256: {hash_info['canonical_sha256']} "
          f"({hash_info['canonical_bytes']} bytes)")
    print(f"in {out['counts']['skus_in']} -> out {out['counts']['skus_out']}, "
          f"excluded {out['counts']['excluded']}")
    print("classes:", {c: out['counts'][c] for c in
                       ('always_replenish', 'depends_on_arrival', 'insufficient_evidence')})
    print("horizon stable/unstable:", out['counts']['class_horizon_stable'],
          "/", out['counts']['class_horizon_unstable'])
    print("demand_overlap unproven:", out['counts']['demand_overlap_unproven'])
    for r in out["rows"]:
        print(f"  #{r['seq']:>2} {r['sku']:32s} {r['class']:22s} tier{r['priority_tier']} "
              f"stable={r['class_horizon_stable']} gates_ok="
              f"{sum(1 for g in r['gates'] if g['state'] == 'ok')}/{len(r['gates'])}")


if __name__ == "__main__":
    main()
