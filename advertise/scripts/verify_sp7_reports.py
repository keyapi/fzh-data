"""Independent SP7 column + analyze verification (do not trust old out/ JSON).

Usage (after pull):
  uv run python advertise/scripts/verify_sp7_reports.py
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "advertise" / "data"
OUT = ROOT / "advertise" / "out" / "verify_2026-07-28"
DOCS = ROOT / "advertise" / "docs" / "research" / "2026-07-28-report-verify"

from advertise.column_maps import _API_MAPS, detect_api_report  # noqa: E402

ANALYZE = {
    "campaign": ("advertise.analyze_campaign", "analyze"),
    "targeting": ("advertise.analyze_targeting", "analyze"),
    "search_term": ("advertise.analyze_search_term", "analyze"),
    "placement": ("advertise.analyze_placement", "analyze"),
    "ad_group": ("advertise.analyze_ad_group", "analyze"),
    "advertised_product": ("advertise.analyze_advertised_product", "analyze"),
    "purchased_item": ("advertise.analyze_purchased_item", "analyze"),
}

METRIC_CANDIDATES = ["spend", "sales", "orders", "clicks", "impressions", "cost"]


def _find_xlsx() -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not DATA.is_dir():
        return found
    for p in sorted(DATA.glob("*.xlsx")):
        col_map, rtype = detect_api_report(p.name)
        if rtype and "BJRYECLTD" in p.name:
            found[rtype] = p
    # fallback: any matching type if no BJRYECLTD
    if not found:
        for p in sorted(DATA.glob("*.xlsx")):
            col_map, rtype = detect_api_report(p.name)
            if rtype and rtype not in found:
                found[rtype] = p
    return found


def verify_one(rtype: str, path: Path) -> dict:
    expected_map = _API_MAPS.get(rtype) or {}
    expected_zh = set(expected_map.keys())
    df_raw = pd.read_excel(path)
    actual_cols = [str(c) for c in df_raw.columns.tolist()]
    actual_set = set(actual_cols)
    missing = sorted(expected_zh - actual_set)
    unexpected = sorted(actual_set - expected_zh)

    df = df_raw.rename(columns=expected_map)
    mapped = [c for c in expected_map.values() if c in df.columns]
    df = df[mapped]

    metrics = {}
    for m in METRIC_CANDIDATES:
        if m in df.columns:
            s = pd.to_numeric(df[m], errors="coerce")
            metrics[m] = {
                "sum": float(s.sum(skipna=True)),
                "null_pct": round(float(s.isna().mean()), 4),
                "non_null": int(s.notna().sum()),
            }

    empty_cols = [c for c in df.columns if df[c].isna().all()]

    analyze_status = {"ran": False, "ok": False, "error": None, "keys": []}
    if rtype in ANALYZE:
        mod_name, fn_name = ANALYZE[rtype]
        try:
            import importlib

            mod = importlib.import_module(mod_name)
            fn = getattr(mod, fn_name)
            result = fn(df.copy())
            analyze_status = {
                "ran": True,
                "ok": True,
                "error": None,
                "keys": list(result.keys())[:20] if isinstance(result, dict) else ["<non-dict>"],
            }
            OUT.mkdir(parents=True, exist_ok=True)
            out_json = OUT / f"{rtype}_analysis.json"
            out_json.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            analyze_status["out"] = str(out_json.relative_to(ROOT))
        except Exception as e:
            analyze_status = {
                "ran": True,
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-800:],
                "keys": [],
            }

    verdict = "PASS"
    if missing:
        verdict = "PARTIAL"
    if analyze_status.get("ran") and not analyze_status.get("ok"):
        verdict = "FAIL" if missing else "PARTIAL_ANALYZE_FAIL"

    return {
        "report_type": rtype,
        "file": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "bytes": path.stat().st_size,
        "rows": int(len(df_raw)),
        "cols_raw": len(actual_cols),
        "cols_mapped": len(mapped),
        "actual_columns": actual_cols,
        "missing_vs_column_maps": missing,
        "unexpected_vs_column_maps": unexpected,
        "empty_mapped_columns": empty_cols,
        "metrics": metrics,
        "analyze": analyze_status,
        "verdict": verdict,
    }


def write_okf(all_results: list[dict], pull_meta: dict | None) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    index = {
        "okf": "v0.1",
        "type": "Index",
        "title": "2026-07-28 SP7 报表独立验证",
        "timestamp": "2026-07-28",
    }
    lines = [
        "---",
        "okf: v0.1",
        "type: Index",
        "title: 2026-07-28 SP7 报表独立验证",
        "description: BJRYECLTD-US 七表重拉后的列对账与 analyze 复跑索引",
        "tags: [sellfox, sp-report, verify, ivyeaops]",
        "timestamp: 2026-07-28",
        "---",
        "",
        "# 2026-07-28 SP7 报表独立验证",
        "",
        "| 报表 | 行数 | 列对账 | analyze | verdict | 详情 |",
        "|------|------|--------|---------|---------|------|",
    ]
    for r in all_results:
        an = r["analyze"]
        an_s = "PASS" if an.get("ok") else ("FAIL" if an.get("ran") else "SKIP")
        col_s = "OK" if not r["missing_vs_column_maps"] else f"缺{len(r['missing_vs_column_maps'])}"
        fname = f"{r['report_type']}.md"
        lines.append(
            f"| {r['report_type']} | {r['rows']} | {col_s} | {an_s} | **{r['verdict']}** | [{fname}]({fname}) |"
        )
    lines.append("")
    if pull_meta:
        lines.append(f"拉取 meta：`advertise/data/_pull_meta_*.json` — ok={pull_meta.get('ok_count')} fail={pull_meta.get('fail_count')}")
        lines.append("")
    lines.append("## README 纠偏")
    lines.append("")
    lines.append("- `fetch_ad_reports.py` 只拉 4 表；额外 3 表需 `fetch_extra_reports.py` 或本目录 `pull_sp7_verify.py`（Proxy 一键 7 表）。")
    lines.append("- 旧 `advertise/out/*_analysis.json` **不可信**；本轮产物在 `advertise/out/verify_2026-07-28/`。")
    (DOCS / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for r in all_results:
        body = [
            "---",
            "okf: v0.1",
            "type: Research",
            f"title: 验证 — {r['report_type']}",
            f"description: 独立验证 {r['report_type']} 列对账与 analyze",
            "tags: [sellfox, verify]",
            "timestamp: 2026-07-28",
            "---",
            "",
            f"# 验证 — {r['report_type']}",
            "",
            f"- **文件**: `{r['file']}`",
            f"- **行数**: {r['rows']}；原始列 {r['cols_raw']}；映射后 {r['cols_mapped']}",
            f"- **verdict**: {r['verdict']}",
            "",
            "## 列对账",
            "",
            f"- missing vs `column_maps.py`: {r['missing_vs_column_maps'] or '无'}",
            f"- unexpected: {r['unexpected_vs_column_maps'] or '无'}",
            f"- 全空映射列: {r['empty_mapped_columns'] or '无'}",
            "",
            "## 实际表头",
            "",
            "```",
            "\n".join(r["actual_columns"]),
            "```",
            "",
            "## 关键指标样例（映射后）",
            "",
            "```json",
            json.dumps(r["metrics"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## analyze 复跑",
            "",
            "```json",
            json.dumps(r["analyze"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        (DOCS / f"{r['report_type']}.md").write_text("\n".join(body), encoding="utf-8")

    summary = {
        "verified_at": datetime.now().isoformat(timespec="seconds"),
        "results": all_results,
        "pull_meta": pull_meta,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verify_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"OKF -> {DOCS}")
    print(f"summary -> {OUT / 'verify_summary.json'}")


def main() -> int:
    files = _find_xlsx()
    print(f"found types: {sorted(files)}")
    pull_meta = None
    metas = sorted(DATA.glob("_pull_meta_*.json")) if DATA.is_dir() else []
    if metas:
        pull_meta = json.loads(metas[-1].read_text(encoding="utf-8"))

    results = []
    for rtype in [
        "campaign",
        "targeting",
        "search_term",
        "placement",
        "ad_group",
        "advertised_product",
        "purchased_item",
    ]:
        if rtype not in files:
            results.append(
                {
                    "report_type": rtype,
                    "file": None,
                    "rows": 0,
                    "cols_raw": 0,
                    "cols_mapped": 0,
                    "actual_columns": [],
                    "missing_vs_column_maps": ["FILE_MISSING"],
                    "unexpected_vs_column_maps": [],
                    "empty_mapped_columns": [],
                    "metrics": {},
                    "analyze": {"ran": False, "ok": False, "error": "file missing"},
                    "verdict": "FAIL",
                }
            )
            continue
        print(f"verify {rtype} <- {files[rtype].name}")
        results.append(verify_one(rtype, files[rtype]))

    write_okf(results, pull_meta)
    fails = [r for r in results if r["verdict"] == "FAIL"]
    print(f"done: {len(results)} reports, FAIL={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
