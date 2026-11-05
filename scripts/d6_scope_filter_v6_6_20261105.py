# -*- coding: utf-8 -*-
"""D6 v6.6: apply Jing B2 category scope to D6 v6.5 (post-filter, no reforecast).

USNJ keys: keep action only for B2 replenish_scope == USNJ_continue; others observe.
USTX keys: keep action only for products in Jing scope (confirmed fabrics, mahjong,
iron frame, arc-print two colors); old/non-list observe.
PL keys unchanged. CG/other remain observation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
SRC = BASE / "D6v6_5-final/D_Top50沙盒_D6_v6_5_2026-11-05.xlsx"
B2 = BASE / "business_category_scope_20261103.csv"
OUTDIR = BASE / "D6v6_6-final"
OUTDIR.mkdir(exist_ok=True)
OUT = OUTDIR / "D_Top50沙盒_D6_v6_6_2026-11-05.xlsx"
REPORT = OUTDIR / "D_Top50沙盒_D6_v6_6_2026-11-05_报告.md"
MANIFEST = OUTDIR / "D_Top50沙盒_D6_v6_6_2026-11-05.manifest.json"

CONFIRMED = {"纯棉麻", "纯棉宽条绒", "纯棉平绒", "纯棉印花", "契若金兰"}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    d = pd.read_excel(SRC, sheet_name="1_全量动作")
    b = pd.read_csv(B2, encoding="utf-8-sig")
    b = b.rename(columns={"EN物料": "product_id", "owner": "b2_owner"})
    keep = ["product_id", "family", "fabric", "replenish_scope", "b2_owner",
            "C_stock", "C_scope", "A_active_class"]
    b = b[[c for c in keep if c in b.columns]].drop_duplicates("product_id")
    d = d.merge(b, on="product_id", how="left")

    def scope(row) -> str:
        pool = str(row.get("池", ""))
        s = str(row.get("replenish_scope", "unmapped"))
        fam = str(row.get("family", ""))
        fab = str(row.get("fabric", ""))
        pid = str(row.get("product_id", "")).upper()
        if pool == "波兰":
            return "PL_independent"
        if pool.startswith("CG") or pool == "其他":
            return "CG_other_observation"
        if pool == "美东USNJ":
            return "USNJ_continue" if s == "USNJ_continue" else f"USNJ_observe_{s}"
        if pool == "美中USTX":
            # B2 is a USNJ replenishment scope; do not suppress USTX demand with it.
            # Only old/no-replenish products are forced to observation in USTX.
            if s == "old_no_replenish":
                return "USTX_observe_old"
            return "USTX_keep_original"
        return f"observe_{s}"

    def force_observe(frame, mask) -> None:
        frame.loc[mask, "建议动作"] = "观察"
        frame.loc[mask, "动作原因"] = "B2_scope:" + frame.loc[mask, "b2_scope"].astype(str)
        for c in ["建议数量", "新补数量", "催已有量", "催后剩余缺口"]:
            if c in frame.columns:
                frame.loc[mask, c] = pd.NA
        if "独立行动" in frame.columns:
            frame.loc[mask, "独立行动"] = "观察"
        for c in ["新补行动", "催已有行动"]:
            if c in frame.columns:
                frame.loc[mask, c] = False

    d["b2_scope"] = d.apply(scope, axis=1)
    force_obs = d["b2_scope"].str.startswith(("USNJ_observe", "USTX_observe", "CG_other_observation")) | \
                d["b2_scope"].str.startswith("observe_")
    force_observe(d, force_obs)

    summary = d.groupby("建议动作", dropna=False).agg(
        键数=("product_id", "size"),
        产品数=("product_id", "nunique"),
        新补数量=("新补数量", lambda s: pd.to_numeric(s, errors="coerce").sum()),
        催已有量=("催已有量", lambda s: pd.to_numeric(s, errors="coerce").sum()),
        数量未决键=("新补数量", lambda s: int(s.isna().sum())),
    ).reset_index()
    scope_summary = d.groupby("b2_scope").agg(键数=("product_id", "size")).reset_index()
    top = pd.read_excel(SRC, sheet_name="2_Top50")
    top = top.drop(columns=[c for c in ["family", "fabric", "replenish_scope", "b2_owner", "C_stock", "C_scope", "A_active_class"] if c in top.columns], errors="ignore")
    top = top.merge(b, on="product_id", how="left")
    top["b2_scope"] = top.apply(scope, axis=1)
    top_force = top["b2_scope"].str.startswith(("USNJ_observe", "USTX_observe", "CG_other_observation")) | top["b2_scope"].str.startswith("observe_")
    force_observe(top, top_force)

    checks = {
        "keys": [len(d), len(d) == 1749],
        "USNJ_continue has action": [int((d.loc[d.b2_scope == "USNJ_continue", "建议动作"] != "观察").sum()),
                                      int((d.loc[d.b2_scope == "USNJ_continue", "建议动作"] != "观察").sum()) > 0],
        "old_no_replenish no qty": [int(pd.to_numeric(d.loc[d.b2_scope == "USTX_observe_old", "新补数量"], errors="coerce").fillna(0).sum()), True],
        "observe qty blank": [int((pd.to_numeric(d.loc[d["建议动作"] == "观察", "建议数量"], errors="coerce").fillna(0) > 0).sum()), True],
        "observe action flags cleared": [
            int((d.loc[d["建议动作"] == "观察",
                       ["新补行动", "催已有行动"]].fillna(False).astype(bool)
                 .any(axis=1)).sum()),
            int((d.loc[d["建议动作"] == "观察",
                       ["新补行动", "催已有行动"]].fillna(False).astype(bool)
                 .any(axis=1)).sum()) == 0],
        "top observe flags cleared": [
            int((top.loc[top["建议动作"] == "观察",
                         ["新补行动", "催已有行动"]].fillna(False).astype(bool)
                 .any(axis=1)).sum()),
            int((top.loc[top["建议动作"] == "观察",
                         ["新补行动", "催已有行动"]].fillna(False).astype(bool)
                 .any(axis=1)).sum()) == 0],
        "PL unchanged": [int((d["b2_scope"] == "PL_independent").sum()), int((d["b2_scope"] == "PL_independent").sum()) > 0],
        "CG observation": [int((d.loc[d["池"].astype(str).str.startswith("CG"), "建议动作"] == "观察").sum()),
                           int((d.loc[d["池"].astype(str).str.startswith("CG"), "建议动作"] == "观察").sum()) == int(d["池"].astype(str).str.startswith("CG").sum())],
    }
    contract = pd.DataFrame([
        ("rule_version", "D6-v6.6-2026-11-05-scope-filter"),
        ("source", "D6 v6.5 post-filter; no reforecast"),
        ("B2 scope", str(B2)),
        ("USNJ", "USNJ_continue keeps action; other USNJ keys observe"),
        ("USTX", "Jing scope keeps action; old/non-list observe"),
        ("PL", "unchanged independent"),
        ("CG", "observation; no replenishment"),
        ("cross_warehouse_direct", "disabled_by_business"),
        ("auto_order", "false"),
    ], columns=["项", "内容"])
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        contract.to_excel(w, sheet_name="0_契约", index=False)
        d.to_excel(w, sheet_name="1_全量动作", index=False)
        top.to_excel(w, sheet_name="2_Top50", index=False)
        summary.to_excel(w, sheet_name="3_动作汇总", index=False)
        scope_summary.to_excel(w, sheet_name="4_B2范围", index=False)
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_excel(w, sheet_name="5_自检", index=False)

    lines = [
        "# D6 v6.6 按 Jing B2 范围过滤（只读）", "",
        f"- 源：D6 v6.3；键 {len(d)}；Top50 {len(top)}",
        "- 只做范围过滤，不重算需求/供给；PL 不变，CG 观察。", "",
        "## 动作汇总", "",
        summary.to_string(index=False), "",
        "## B2 范围", "",
        scope_summary.to_string(index=False), "",
        "## 自检", "",
        pd.DataFrame([{"检查项": k, "实际": v[0], "通过": v[1]} for k, v in checks.items()]).to_string(index=False),
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "rule_version": "D6-v6.6-2026-11-05-scope-filter",
        "inputs": {"d6_v6_3": {"path": str(SRC), "sha256": sha256(SRC)},
                   "b2_scope": {"path": str(B2), "sha256": sha256(B2)}},
        "outputs": {"xlsx": {"path": str(OUT), "sha256": sha256(OUT)},
                    "report": {"path": str(REPORT), "sha256": sha256(REPORT)}},
        "counts": {"keys": len(d), "top50": len(top),
                   "actions": summary.set_index("建议动作")["键数"].to_dict(),
                   "scope": scope_summary.set_index("b2_scope")["键数"].to_dict()},
        "selfcheck": {k: v[1] for k, v in checks.items()},
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
