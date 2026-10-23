#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T19: WO / DN coverage and linkage-gap table (third deliverable).

Purpose
  Separate "the work order is not in the current aggregate snapshot" from
  "there is no material at all" for every row of the main table (2,309 rows /
  1,328 SKUs).

Sources used (local only, read-only; NO new query types)
  * order_store.duckdb — information_schema only (table/column structure);
    no row-level query is issued.
  * g1_contract/out/dn_wo_jc_se* — WO/DN/JC/SE association artifacts with
    their own audit_ok / evidence_complete / conservation flags.
  * g1_contract/out/g1b_en_*.json — raw EN extracts (WO rows, production
    four-way).
  * out/replenishment_v0/evidence.json — V0.1 supply evidence: open WO
    remaining quantities and ETA status per SKU.
  * out/business_phase/n2_b*.json — N2 chain tables that explicitly state
    "WO not in this snapshot".
  * out/business_phase/decision_v2.csv — the 2,309-row universe.

Three states (per main-table row)
  covered_validated   material exists AND is usable for supply: the
                      association passed its audit/conservation AND every open
                      WO has a known remaining quantity with known UOM and an
                      ETA (so it can be placed in the L60/L90/L120 window).
  covered_unvalidated material exists but fails any of those tests; it MUST
                      NOT be counted as supply.
  no_material_found   no WO/DN material in any local source; the sources
                      checked are listed, never guessed or extrapolated.

Linkage keys reported separately (no inference)
  WO x SO   — linked vs unlinked, with the artifact's own reason codes
  DN x WO   — DN lines carrying a work-order key
  WO x PO   — no source exposes a WO->PO key at all

Wording: this table reports coverage extent and what is missing. It does not
add supply, does not change the main table, and does not extrapolate.

Outputs: out/business_phase/wo_dn_coverage.csv / .json / (md in out/business_phase)
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
DECISION = OUT / "decision_v2.csv"
MAIN = OUT / "replenishment_v2.csv"
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
G1_OUT = CLAUDE_DIR / "experiments" / "g1_contract" / "out"
V0_EVIDENCE = CLAUDE_DIR / "out" / "replenishment_v0" / "evidence.json"
OUT_CSV = OUT / "wo_dn_coverage.csv"
OUT_JSON = OUT / "wo_dn_coverage.json"
OUT_MD = OUT / "wo_dn_coverage.md"

STATE_V = "covered_validated"
STATE_U = "covered_unvalidated"
STATE_N = "no_material_found"

SOURCES_CHECKED = (
    "本地来源：① order_store.duckdb information_schema（53 表，无 WO/DN 实体）；"
    "② g1_contract/out/dn_wo_jc_se*（10 个 SKU 的 WO/DN/JC/SE 关联，含自审标记）；"
    "③ g1b_en_*.json（原始 EN 抓取）；④ out/replenishment_v0/evidence.json（V0.1 供给证据）；"
    "⑤ n2_b1–b3 链条（WO 不在快照的显式说明）；⑥ g1b_coverage_*.json（BOM/库存/订单，无 WO/DN 字段）。"
)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def db_inventory() -> dict:
    """Structure only — no row-level query on business tables."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY 1").fetchall()]
        cols = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='main'").fetchall()
    finally:
        con.close()
    wo_dn_cols = [(t, c, d) for t, c, d in cols
                  if any(k in c.lower() for k in
                         ("work_order", "work order", "delivery_note", "delivery note",
                          "wo_id", "dn_id"))]
    prod_adj = sorted({t for t, c, d in cols if any(
        k in (t + " " + c).lower() for k in
        ("component_ship", "bom", "stock", "po_open", "tongtool_po", "replenishment_pool"))})
    return dict(n_tables=len(tables), tables=tables,
                wo_dn_columns=[list(x) for x in wo_dn_cols],
                production_adjacent_tables=prod_adj,
                note=("库里没有 Work Order / Delivery Note 实体，也没有任何 WO/DN 外键列；"
                      "只有订单、库存、PO、BOM 与组件发运计划。"))


def artifact_inventory() -> tuple[list, dict]:
    """Every dn_wo_jc_se* manifest plus the raw EN extracts."""
    runs = []
    for d in sorted(glob.glob(str(G1_OUT / "dn_wo_jc_se*"))):
        p = Path(d)
        mf = p / "association_manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        c2 = m.get("conservation", {}).get("C2_wo_se")
        c2_by = {}
        if isinstance(c2, list):
            c2_by = {x.get("scope"): dict(pass_=x.get("pass"), mismatch=x.get("mismatch"),
                                          unverified=x.get("unverified"),
                                          complete=x.get("complete"), open=x.get("open"))
                     for x in c2}
        runs.append(dict(
            dir=p.name, as_of=m.get("as_of"), audit_ok=m.get("audit_ok"),
            evidence_complete=m.get("evidence_complete"),
            scopes=[s.get("scope") for s in m.get("scopes", [])],
            row_accounting=m.get("row_accounting"),
            c2_wo_se=c2_by,
            note=("通过自审" if m.get("audit_ok") and m.get("evidence_complete")
                  else "未通过自审（audit/evidence 非 true）"),
        ))
    runs.sort(key=lambda r: (str(r["as_of"]), len(r["scopes"])))
    primary = next((r for r in reversed(runs)
                    if r["audit_ok"] and r["evidence_complete"]
                    and len(r["scopes"]) >= 10), None)
    raw = []
    for p in sorted(glob.glob(str(G1_OUT / "g1b_en_*.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        raw.append(dict(file=Path(p).name,
                        scope=(d.get("query") or {}).get("customer_code"),
                        generated_at=d.get("generated_at"),
                        wos=len(d.get("wos") or []),
                        production_four_way=len(d.get("production_four_way") or {})))
    return runs, dict(primary=primary, raw_extracts=raw)


def load_primary_dispositions(primary: dict) -> dict:
    """Per-scope WO/DN linkage from the validated association run."""
    p = G1_OUT / primary["dir"] / "line_dispositions.jsonl"
    rows = [json.loads(line) for line in p.open(encoding="utf-8")]
    by = defaultdict(lambda: dict(wo=0, wo_so=0, wo_unlinked=0,
                                  wo_reason=Counter(), dn=0, dn_wo=0,
                                  open_wo=0, open_wo_uom_known=0))
    for r in rows:
        sc = r["scope"]
        link = r.get("link") or {}
        if r["row_type"] == "wo":
            by[sc]["wo"] += 1
            if link.get("so"):
                by[sc]["wo_so"] += 1
            else:
                by[sc]["wo_unlinked"] += 1
                by[sc]["wo_reason"][r.get("link_reason_code") or "unknown"] += 1
            if r.get("disposition") == "open":
                by[sc]["open_wo"] += 1
                if r.get("uom") or link.get("so_line_uom"):
                    by[sc]["open_wo_uom_known"] += 1
        elif r["row_type"] == "dn_line":
            by[sc]["dn"] += 1
            if link.get("work_orders"):
                by[sc]["dn_wo"] += 1
    for v in by.values():
        v["wo_reason"] = dict(v["wo_reason"])
    return dict(by_scope=dict(by))


def load_v0() -> dict:
    d = json.loads(V0_EVIDENCE.read_text(encoding="utf-8"))
    out = {}
    for s in d.get("skus", []):
        p = s.get("production") or {}
        out[s["customer_code"]] = dict(
            sku=s.get("sku"), open_wo_count=p.get("open_wo_count"),
            remaining_qty=p.get("remaining_qty"), gross_qty=p.get("gross_qty"),
            eta_missing_count=p.get("eta_missing_count"), eta_status=p.get("eta_status"),
            production_item_kinds=p.get("production_item_kinds"),
            generated_at=d.get("generated_at"),
            source=str(V0_EVIDENCE.relative_to(CLAUDE_DIR)).replace("\\", "/"))
    return out


def load_n2_absence() -> dict:
    out = {}
    for f in ("n2_b1.json", "n2_b2.json", "n2_b3.json"):
        p = OUT / f
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for ch in d.get("chains", []):
            out[ch["sku"]] = dict(file=f, note="在产 WO 剩余量与完工日不在本快照")
    return out


def main() -> None:
    rows = list(csv.DictReader(open(DECISION, encoding="utf-8-sig")))
    n_rows, n_skus = len(rows), len({r["SKU"] for r in rows})

    db = db_inventory()
    runs, art = artifact_inventory()
    primary = art["primary"]
    if primary is None:
        raise SystemExit("no audited WO/DN association artifact found")
    disp = load_primary_dispositions(primary)["by_scope"]
    v0 = load_v0()
    n2 = load_n2_absence()

    # ---------------- per-SKU material + supply validation -----------------
    material = {}
    for sc, det in v0.items():
        c2 = (primary["c2_wo_se"] or {}).get(sc) or {}
        assoc_valid = bool(
            sc in primary["scopes"] and primary["audit_ok"] and primary["evidence_complete"]
            and c2.get("complete") and (c2.get("mismatch") or 0) == 0
            and (c2.get("unverified") or 0) == 0)
        eta_ok = (det["eta_missing_count"] == 0
                  and det["eta_status"] == "ok")
        remaining_ok = (det["remaining_qty"] or 0) > 0
        # UOM usability: mixed KS/PK# production makes the kit->SKU conversion
        # unproven; only a single, known kind passes.
        kinds = det["production_item_kinds"] or []
        uom_ok = len(kinds) == 1
        supply_valid = assoc_valid and eta_ok and remaining_ok and uom_ok
        material[sc] = dict(
            detail=det, assoc_valid=assoc_valid, eta_ok=eta_ok,
            remaining_ok=remaining_ok, uom_ok=uom_ok,
            supply_valid=supply_valid,
            state=STATE_V if supply_valid else STATE_U,
            reasons=[k for k, ok in (("association_not_validated", assoc_valid),
                                     ("eta_missing", eta_ok),
                                     ("no_remaining_qty", remaining_ok),
                                     ("uom_kind_mixed_or_unknown", uom_ok)) if not ok],
        )

    # ---------------- per-row table ---------------------------------------
    out = []
    for r in rows:
        sku, wh = r["SKU"], r["仓"]
        m = material.get(sku)
        d = (disp.get(sku) or {})
        base = dict(SKU=sku, 仓=wh, 主表状态=r["状态"],
                    在产=r["在产"], 在产状态=r["在产状态"],
                    WO总数=d.get("wo"), WO已关联SO=d.get("wo_so"),
                    WO未关联SO=d.get("wo_unlinked"),
                    WO未关联原因=json.dumps(d.get("wo_reason") or {}, ensure_ascii=False),
                    WO开放数=d.get("open_wo"), WO开放UOM已知=d.get("open_wo_uom_known"),
                    DN行数=d.get("dn"), DN到WO有键=d.get("dn_wo"),
                    WO到PO有键=0 if d.get("wo") is not None else None,
                    查过的来源=SOURCES_CHECKED)
        if m:
            det = m["detail"]
            base.update(
                覆盖状态=m["state"], 材料来源=det["source"], 材料时间=det["generated_at"],
                关联验证=("通过" if m["assoc_valid"] else "未通过"),
                WO剩余量_不计供给=det["remaining_qty"],
                ETA缺失数=det["eta_missing_count"], ETA状态=det["eta_status"],
                生产物料类型="/".join(det["production_item_kinds"] or []),
                供给可用量=None,
                判定依据=("；".join(m["reasons"]) + "；不计供给" if m["reasons"]
                          else "满足全部校验"),
                缺失说明="")
        else:
            base.update(覆盖状态=STATE_N, 材料来源="", 材料时间="", 关联验证="",
                        WO剩余量_不计供给=None, ETA缺失数=None, ETA状态="",
                        生产物料类型="", 供给可用量=None,
                        判定依据="本地 WO/DN 来源均未覆盖",
                        缺失说明=(n2[sku]["note"] + f"（{n2[sku]['file']} 显式说明）"
                                  if sku in n2 else "未在任何本地 WO/DN 来源中找到"))
        out.append(base)

    # ---------------- assertions ------------------------------------------
    cnt = Counter(x["覆盖状态"] for x in out)
    assert len(out) == n_rows == 2309
    assert len({x["SKU"] for x in out}) == n_skus == 1328
    assert sum(cnt.values()) == 2309
    assert cnt[STATE_U] + cnt[STATE_V] + cnt[STATE_N] == 2309
    u_skus = {x["SKU"] for x in out if x["覆盖状态"] == STATE_U}
    assert len(u_skus) == 10, len(u_skus)
    assert cnt[STATE_U] == 32, cnt[STATE_U]
    assert cnt[STATE_V] == 0, "no local source provides ETA-validated WO supply"

    # ---------------- linkage aggregates ----------------------------------
    wo_total = sum(d.get("wo", 0) for d in disp.values())
    wo_so = sum(d.get("wo_so", 0) for d in disp.values())
    dn_total = sum(d.get("dn", 0) for d in disp.values())
    dn_wo = sum(d.get("dn_wo", 0) for d in disp.values())
    reasons = Counter()
    for d in disp.values():
        for k, v in (d.get("wo_reason") or {}).items():
            reasons[k] += v
    linkage = dict(
        WO_SO=dict(total=wo_total, linked=wo_so, missing=wo_total - wo_so,
                   reasons=dict(reasons),
                   note="缺失来自工单本身无 SO 或 SO 不在快照；按原样记录，不猜测补全"),
        DN_WO=dict(total=dn_total, linked=dn_wo, missing=dn_total - dn_wo,
                   note="DN 行只带 SO 行键，未暴露 WO 键；DN→WO 只能经 SO 间接关联"),
        WO_PO=dict(total=wo_total, linked=0, missing=wo_total,
                   note="任何本地来源都没有 WO→PO 键；库里只有 SKU×仓的 PO 聚合"),
    )

    # ---------------- outputs ---------------------------------------------
    fields = list(out[0].keys())
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    result = dict(
        schema_version="t19_wo_dn_coverage/1",
        inputs=dict(decision_sha256=sha(DECISION), main_sha256=sha(MAIN),
                    v0_evidence_sha256=sha(V0_EVIDENCE),
                    primary_manifest=primary["dir"],
                    primary_manifest_sha256=sha(
                        G1_OUT / primary["dir"] / "association_manifest.json")),
        rules=dict(
            covered_validated=("有材料且可用于供给：关联通过自审（audit_ok、evidence_complete、"
                               "C2 mismatch=0/unverified=0）且开放 WO 有剩余量、UOM 单一已知、"
                               "ETA 已知（可放入 L60/L90/L120 窗口）"),
            covered_unvalidated=("有材料但任一校验失败；**不得计入供给**"),
            no_material_found=("本地任何 WO/DN 来源都未覆盖；逐行列出查过的来源"),
            linkage="WO↔SO / DN↔WO / WO↔PO 分别按有键/缺键计数，不猜测补全"),
        sources_checked=dict(db=db, association_runs=runs, primary_run=primary,
                             raw_en_extracts=art["raw_extracts"],
                             v0_evidence=dict(path="out/replenishment_v0/evidence.json",
                                              skus=sorted(v0)),
                             n2_explicit_absence=sorted(n2),
                             g1b_coverage=["out/g1b_coverage_20261020.json",
                                           "out/g1b_coverage_centrade_only.json",
                                           "out/g1b_coverage_complete.json"],
                             g1b_coverage_note="BOM/库存/订单覆盖，无 WO/DN 字段"),
        coverage=dict(rows={k: cnt.get(k, 0) for k in (STATE_V, STATE_U, STATE_N)},
                      skus={k: len({x["SKU"] for x in out if x["覆盖状态"] == k})
                            for k in (STATE_V, STATE_U, STATE_N)},
                      sum_rows=sum(cnt.values()), sum_skus=n_skus),
        material_skus=[dict(sku=s, state=m["state"], reasons=m["reasons"],
                            assoc_valid=m["assoc_valid"], eta_ok=m["eta_ok"],
                            remaining_ok=m["remaining_ok"], uom_ok=m["uom_ok"],
                            open_wo_count=m["detail"]["open_wo_count"],
                            remaining_qty=m["detail"]["remaining_qty"],
                            eta_missing_count=m["detail"]["eta_missing_count"],
                            eta_status=m["detail"]["eta_status"],
                            production_item_kinds=m["detail"]["production_item_kinds"])
                       for s, m in sorted(material.items())],
        linkage=linkage,
        wording=("只报告覆盖程度与缺口；covered_unvalidated 不计供给；不新增查询、不扩样、不外推。"),
    )
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    md = ["# T19 WO/DN 覆盖与关联缺口", "",
          "> 只盘点**本地已有**材料：不新增数据库数据查询（仅 information_schema 结构）、"
          "不访问生产、不扩样、不外推。", "",
          "## 1. 查过的来源", "",
          "| 来源 | 类型 | 覆盖 | 结论 |", "|---|---|---|---|",
          f"| order_store.duckdb | 表结构 | {db['n_tables']} 表 | "
          f"无 Work Order / Delivery Note 实体或键（WO/DN 列 0 个） |",
          f"| g1_contract/out/dn_wo_jc_se* | WO/DN/JC/SE 关联 | "
          f"{len(runs)} 个 run，{len({s for r in runs for s in r['scopes']})} 个 SKU | "
          f"主用 `{primary['dir']}`（audit/evidence 通过，{len(primary['scopes'])} SKU） |",
          f"| g1b_en_*.json | 原始 EN 抓取 | {len(art['raw_extracts'])} 个文件 / "
          f"{len({x['scope'] for x in art['raw_extracts']})} 个 SKU | "
          "WO 行与 production_four_way 原始字段 |",
          f"| out/replenishment_v0/evidence.json | V0.1 供给证据 | {len(v0)} 个 SKU | "
          "开放 WO 剩余量与 ETA 状态 |",
          f"| out/business_phase/n2_b1–b3.json | 链条表 | {len(n2)} 个 SKU | "
          "显式写“WO 不在本快照”，无具体 WO 材料 |",
          "| out/g1b_coverage_*.json | BOM/库存/订单 | 多 SKU | 无 WO/DN 字段（仅作交叉说明） |", "",
          "## 2. 三态计数（相加 = 2,309）", "",
          "| 状态 | 行数 | SKU | 含义 |", "|---|---:|---:|---|",
          f"| `covered_validated` | **{cnt.get(STATE_V, 0)}** | "
          f"{len({x['SKU'] for x in out if x['覆盖状态'] == STATE_V})} | "
          "有材料且可用于供给 |",
          f"| `covered_unvalidated` | **{cnt.get(STATE_U, 0)}** | {len(u_skus)} | "
          "有材料但未通过校验，**不得计供给** |",
          f"| `no_material_found` | **{cnt.get(STATE_N, 0)}** | "
          f"{len({x['SKU'] for x in out if x['覆盖状态'] == STATE_N})} | "
          "本地来源均未覆盖（逐行列出查过的来源） |", "",
          "**为什么 `covered_validated` 为 0**：10 个有材料的 SKU 中 7 个关联通过自审、"
          "3 个存在 C2 mismatch/unverified；但无论关联是否通过，**开放 WO 的 ETA 全部缺失**"
          "（`planned_end_date_all_null`），无法放入 L60/L90/L120 窗口；"
          "另有 1 个 SKU 的 KS/PK# UOM 口径未证。故全部只能算 `covered_unvalidated`，"
          "不得计入供给。", "",
          "## 3. 有材料的 10 个 SKU（全部 covered_unvalidated）", "",
          "| SKU | 开放 WO | 剩余量（不计供给） | ETA 缺失 | 关联自审 | 失败原因 |",
          "|---|---:|---:|---:|---|---|"]
    for s in result["material_skus"]:
        md.append(f"| `{s['sku']}` | {s['open_wo_count']} | {s['remaining_qty']} | "
                  f"{s['eta_missing_count']} | {'通过' if s['assoc_valid'] else '未通过'} | "
                  f"{'、'.join(s['reasons'])} |")
    md += ["", "## 4. 关联键覆盖（有键 / 缺键）", "",
           "| 关联 | 总数 | 有键 | 缺键 | 说明 |", "|---|---:|---:|---:|---|",
           f"| WO↔SO | {linkage['WO_SO']['total']} | {linkage['WO_SO']['linked']} | "
           f"{linkage['WO_SO']['missing']} | 缺键原因：{linkage['WO_SO']['reasons']} |",
           f"| DN↔WO | {linkage['DN_WO']['total']} | {linkage['DN_WO']['linked']} | "
           f"{linkage['DN_WO']['missing']} | DN 行只带 SO 键，无 WO 键 |",
           f"| WO↔PO | {linkage['WO_PO']['total']} | 0 | {linkage['WO_PO']['missing']} | "
           "任何本地来源都没有 WO→PO 键 |", "",
           "## 5. 结论", "",
           f"- 主表 2,309 行 / 1,328 SKU 中，WO/DN 材料只覆盖 **10 个 SKU（32 行）**；"
           f"其余 **1,318 个 SKU（2,277 行）** 在本地 WO/DN 来源中确实没有材料。",
           "- 10 个 SKU **全部是 `covered_unvalidated`**：关联/守恒可查，但开放 WO 缺 ETA、"
           "且 KS/PK# UOM 口径未证，不能计入供给。",
           "- 关联缺口是结构性的：DN 行没有 WO 键（只能经 SO 间接关联），"
           "WO 也没有 PO 键；这两类缺口靠现有材料无法补齐，不猜测。",
           "- 与主表 `在产状态=work_order_not_in_snapshot` 的关系：主表把在产一律按 0，"
           "本表说明其中 10 个 SKU 其实**有 WO 材料**（但不可用作供给），"
           "其余 SKU 才是真正的“无材料”。", "",
           "## 6. 复现", "",
           "```bash",
           "uv run python docs/research/supply-chain/2026-10-20/claude/"
           "experiments/business_phase/build_wo_dn_coverage.py",
           "uv run python scripts/check_secrets.py",
           "```", "",
           "只读 DB（仅 information_schema）；输入哈希见 JSON；三态与计数断言在脚本内。", ""]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("wrote", OUT_CSV.name, OUT_JSON.name, OUT_MD.name)
    print("rows", n_rows, "skus", n_skus, "states", dict(cnt))
    print("material skus", len(material), "u_skus", len(u_skus))
    print("linkage", {k: (v["total"], v["linked"], v["missing"])
                      for k, v in linkage.items()})


if __name__ == "__main__":
    main()
