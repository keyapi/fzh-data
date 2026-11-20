# -*- coding: utf-8 -*-
"""Phase 4.FBA alias 登记 dry-run（不写 EN/GS）。

- 对未登记 SKU 生成 customer_code 登记提案：旧/新值 + sha256 + 影响 SKU/行/数量。
- `cost_borrow`：无对应物料时只给借成本建议，不产生别名写入。
- 另列已 auto 的 SKU：按归一化别名能否命中，区分「仅归一化差异」与「真正缺登记」。
- 只落本地文件 `out/fba_shadow/alias_dryrun_<ts>/`，绝不调用 EN API。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .split_merge import EnResolver, normalize_alias

TZ_CN = timezone(timedelta(hours=8))

DEFAULT_PROPOSALS: tuple[dict, ...] = (
    {"sku": "OSKBG-RSUS-FBA", "action": "add_alias",
     "target_item": "KS0423-XNEOSTH-153x65x23-OFFWHITE",
     "note": "欧式米白滚边吊穗大靠背 153*65*23；EN 现有物料，登记别名后可直接计价"},
    {"sku": "SUK-SFZCD-black3pcs FBA", "action": "add_alias",
     "target_item": "TJ#KS0156x3-001",
     "note": "套件 3×KS0156-NYBDSFH-52x52x5-BLACK（5cm 三件装）"},
    {"sku": "FUDE-huxingdima-wh-200", "action": "cost_borrow",
     "target_item": "KS0007-DM-200-IVORY",
     "note": "无白色物料；按同组/同面料/同尺寸借用象牙白成本，先不登记"},
    {"sku": "FUDE-huxingdima-wh-200", "action": "add_alias",
     "target_item": "KS0007-DM-200-IVORY",
     "note": "cost_borrow_white→ivory，供用户确认（白色实际借象牙白）"},
)


def _sha(text: str) -> str:
    return hashlib.sha256(str(text).encode()).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def build_alias_dryrun(
    *,
    root: str | Path = ".",
    months: Sequence[str] = ("202608", "202609"),
    proposals: Sequence[Mapping] = DEFAULT_PROPOSALS,
    out_root: str | Path | None = None,
) -> dict:
    root = Path(root)
    out_root = Path(out_root or root / "out" / "fba_shadow")
    ref_csv = root / "out" / "item_refcode.csv"
    ref = pd.read_csv(ref_csv, dtype=str, keep_default_na=False)
    by_item = {str(r.get("name") or "").strip(): r for r in ref.to_dict("records")}
    resolver = EnResolver.from_items_csv(ref_csv)
    bom_csv = root / "out" / "bom_cost_product_with_kits.csv"
    bom_group: dict[str, str] = {}
    if bom_csv.exists():
        bom = pd.read_csv(bom_csv, dtype=str, keep_default_na=False)
        for r in bom.to_dict("records"):
            item = str(r.get("item_fg") or "").strip()
            name = str(r.get("item_fg_name") or "").strip()
            if item and name:
                bom_group.setdefault(item, name.split("-")[0].strip())

    whitelists: dict[str, pd.DataFrame] = {}
    for m in months:
        p = root / "out" / "fba_shadow" / m / f"fba_whitelist_{m}.csv"
        if p.exists():
            whitelists[m] = pd.read_csv(p, dtype=str, keep_default_na=False)

    def _affected(sku: str) -> tuple[int, int, float, str]:
        rows = 0
        qty = 0.0
        ms: list[str] = []
        for m, wl in whitelists.items():
            hit = wl[wl["sku"].astype(str) == sku]
            if len(hit):
                rows += len(hit)
                qty += sum(_num(x) for x in hit["qty"])
                ms.append(m)
        return (1 if rows else 0), rows, round(qty, 6), ",".join(sorted(set(ms)))

    # 已 auto 的 SKU 汇总（先算：既用于分类，也用于生成 add_alias 提案）
    auto_rows: dict[str, dict] = {}
    for m, wl in whitelists.items():
        for r in wl[wl["status"] == "auto_mapped"].to_dict("records"):
            sku = str(r.get("sku") or "")
            if not sku:
                continue
            hits = resolver.items_for_sku(sku)
            entry = auto_rows.setdefault(sku, {
                "sku": sku, "months": set(), "qty": 0.0, "auto_pref": r.get("auto_pref", ""),
                "approved_item_code": r.get("approved_item_code", ""),
                "alias_key": normalize_alias(sku), "alias_hits": list(hits),
            })
            entry["months"].add(m)
            entry["qty"] += _num(r.get("qty"))
    class_rows: list[dict] = []
    for sku, e in sorted(auto_rows.items()):
        alias_ok = len(e["alias_hits"]) > 0
        class_rows.append({
            "sku": sku,
            "class": "normalization_only" if alias_ok else "needs_registration",
            "auto_pref": e["auto_pref"], "approved_item_code": e["approved_item_code"],
            "alias_key": e["alias_key"], "alias_hits": ";".join(e["alias_hits"]),
            "months": ",".join(sorted(e["months"])), "qty": round(e["qty"], 6),
        })

    def _alias_present(item: str, sku: str) -> bool:
        row = by_item.get(item)
        if row is None:
            return False
        codes = [c.strip() for c in str(row.get("customer_code") or "").split(",") if c.strip()]
        return any(normalize_alias(c) == normalize_alias(sku) for c in codes)

    def _proposal(action: str, sku: str, item: str, note: str) -> dict:
        row = by_item.get(item)
        old_code = str(row.get("customer_code") or "") if row is not None else ""
        new_code = (sku if not old_code else f"{old_code},{sku}") if action == "add_alias" else old_code
        skus, rows, qty, ms = _affected(sku)
        if action == "add_alias":
            status = "noop" if _alias_present(item, sku) else "needs_review"
        else:
            status = "suggestion"
        affected = f"{skus} SKU / {rows} 行 / {qty:g} 件"
        if ms:
            affected += f"（{ms}）"
        item_group = (str(row.get("item_group") or "") if row is not None
                      else bom_group.get(item, ""))
        return {
            "action": action, "sku": sku, "target_item": item,
            "item_in_ref": bool(row), "item_group": item_group,
            "old_customer_code": old_code, "new_customer_code": new_code,
            "old_hash": _sha(old_code), "new_hash": _sha(new_code),
            "affected": affected,
            "affected_skus": skus, "affected_rows": rows, "affected_qty": qty, "months": ms,
            "write": False, "status": status, "note": note,
        }

    manual_rows = [
        _proposal(str(p["action"]), str(p["sku"]), str(p["target_item"]), str(p.get("note") or ""))
        for p in proposals
    ]
    seen = {(r["sku"], r["target_item"]) for r in manual_rows}
    auto_prop_rows: list[dict] = []
    for sku, e in sorted(auto_rows.items()):
        item = e["approved_item_code"]
        if not item or (sku, item) in seen:
            continue
        auto_prop_rows.append(_proposal(
            "add_alias", sku, item,
            f"auto_mapped:{e['auto_pref'] or '—'}；{','.join(sorted(e['months']))}",
        ))
        seen.add((sku, item))
    prop_rows = manual_rows + auto_prop_rows

    ts = datetime.now(TZ_CN)
    run_dir = out_root / f"alias_dryrun_{ts:%Y%m%dT%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=False)
    prop_df = pd.DataFrame(prop_rows)
    manual_df = pd.DataFrame(manual_rows)
    cls_df = pd.DataFrame(class_rows)
    prop_df.to_csv(run_dir / "proposals_all.csv", index=False, encoding="utf-8-sig")
    manual_df.to_csv(run_dir / "proposals.csv", index=False, encoding="utf-8-sig")
    cls_df.to_csv(run_dir / "classification.csv", index=False, encoding="utf-8-sig")
    counts = {str(k): int(v) for k, v in cls_df["class"].value_counts().items()} if len(cls_df) else {}
    status_counts = {str(k): int(v) for k, v in prop_df["status"].value_counts().items()}
    summary = {
        "dry_run": True, "no_write": True,
        "created_at": ts.isoformat(),
        "months": list(months),
        "proposals": len(prop_rows),
        "manual_proposals": len(manual_rows),
        "auto_proposals": len(auto_prop_rows),
        "add_alias": sum(1 for r in prop_rows if r["action"] == "add_alias"),
        "cost_borrow": sum(1 for r in prop_rows if r["action"] == "cost_borrow"),
        "noop": status_counts.get("noop", 0),
        "needs_review": status_counts.get("needs_review", 0),
        "suggestion": status_counts.get("suggestion", 0),
        "auto_total": len(class_rows),
        "normalization_only": counts.get("normalization_only", 0),
        "needs_registration": counts.get("needs_registration", 0),
        "inputs": {
            "item_refcode": {"path": str(ref_csv), "sha256": _sha_file(ref_csv)},
            **{
                f"whitelist_{m}": {"path": str(root / 'out' / 'fba_shadow' / m / f'fba_whitelist_{m}.csv'),
                                   "sha256": _sha_file(root / 'out' / 'fba_shadow' / m / f'fba_whitelist_{m}.csv')}
                for m in whitelists
            },
        },
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# FBA alias 登记 dry-run（不写 EN/GS）", "",
        f"- 生成时间: {summary['created_at']}",
        f"- 提案: {summary['proposals']}（手动 {summary['manual_proposals']} + auto {summary['auto_proposals']}）",
        f"- add_alias {summary['add_alias']}；noop {summary['noop']}；needs_review {summary['needs_review']}；"
        f"cost_borrow {summary['cost_borrow']}",
        f"- auto SKU: {summary['auto_total']}；仅归一化差异 {summary['normalization_only']}；"
        f"真正缺登记 {summary['needs_registration']}", "",
        "## 登记提案（完整见 proposals_all.csv）", "",
        "| 动作 | SKU | 目标物料 | 旧 customer_code | 新 customer_code | 影响 | 状态 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in prop_rows:
        lines.append(
            f"| {r['action']} | {r['sku']} | {r['target_item']} | {r['old_customer_code'] or '（未登记）'} | "
            f"{r['new_customer_code'] or '（无变更）'} | {r['affected']} | {r['status']} |")
    lines += ["", "## 已 auto SKU 分类", "", "| SKU | 分类 | auto_pref | 目标物料 | 别名命中 |", "|---|---|---|---|---|"]
    for r in class_rows:
        lines.append(f"| {r['sku']} | {r['class']} | {r['auto_pref']} | {r['approved_item_code']} | "
                     f"{r['alias_hits'] or '—'} |")
    lines.append("")
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "run_dir": str(run_dir), "summary": summary,
        "proposals": prop_rows, "manual_proposals": manual_rows,
        "auto_proposals": auto_prop_rows, "classification": class_rows,
    }
