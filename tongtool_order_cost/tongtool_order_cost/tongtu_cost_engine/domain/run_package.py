# -*- coding: utf-8 -*-
"""Phase 4.0 生产写回演练（本地，不写 GS/EN）。

- 固化 run 包：输入 manifest/hash、月末版本、bundle_version，写入不可变 `out/runs/<run_id>/`。
- 单月单仓库桶 canary：生成 `writeback_canary_<month>_<bucket>.csv`（166 列合同 + 血缘/标注列），
  与旧写回按 key 逐行/逐列 diff，金额影响按 method/套件/非商品配件/利润空白分层。
- 写前门禁：版本锁、禁止覆盖非空 run、重复写入检测；写后回读校验行数/键/四列金额/摘要 hash。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .bom_cost import Phase2Result, warehouse_bucket
from .split_merge import MergeShadowResult, normalize_sku
from .writeback_rehearsal import WritebackRehearsal

TZ_CN = timezone(timedelta(hours=8))
TOL = 0.01


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha_json(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def _num(v) -> float | None:
    s = str(v).strip() if v is not None else ""
    if s in ("", "nan", "None", "NULL"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _nonempty(v) -> str:
    return str(v).strip() if v is not None else ""


def _row_key(row: Mapping) -> str:
    return "|".join((
        _nonempty(row.get("订单号")),
        normalize_sku(row.get("平台SKU_统一") or row.get("平台SKU")),
        normalize_sku(row.get("通途SKU")),
    ))


def _keyed(rows: Sequence[Mapping]) -> list[tuple[str, Mapping]]:
    """业务键 + 同键出现序号，保证键唯一。"""
    counter: Counter = Counter()
    out: list[tuple[str, Mapping]] = []
    for row in rows:
        base = _row_key(row)
        counter[base] += 1
        out.append((f"{base}#{counter[base]}", row))
    return out


def _amount_col(col: str) -> str:
    return "头程运费*数量" if col == "头程运费金额" else f"{col}*数量"


def _month_end(month: str) -> str:
    import calendar
    year, mon = int(month[:4]), int(month[4:6])
    return f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}"


def _read_index(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


@dataclass
class RunPackage:
    run_id: str
    run_dir: Path
    manifest: dict
    canary_rows: list[dict]
    summary: dict
    diff_rows: list[dict]
    column_diffs: list[dict]
    amount_layers: list[dict]
    gates: list[dict]
    readback: list[dict]

    @property
    def ok(self) -> bool:
        return all(g["status"] != "fail" for g in self.gates + self.readback)


def build_run_package(
    shadow: MergeShadowResult,
    phase2: Phase2Result,
    rehearsal: WritebackRehearsal,
    *,
    input_paths: Mapping[str, Path],
    runs_root: str | Path,
    month: str,
    bucket: str | None = None,
    old_writeback_csv: str | Path | None = None,
    allow_duplicate: bool = False,
    run_id: str | None = None,
) -> RunPackage:
    runs_root = Path(runs_root)
    input_files: dict[str, dict] = {}
    gates: list[dict] = []
    for name, path in input_paths.items():
        p = Path(path)
        if not p.exists():
            gates.append({"gate": "input_exists", "status": "fail", "detail": f"{name} 不存在: {p}"})
            continue
        input_files[name] = {
            "path": str(p), "name": p.name, "sha256": _sha256(p),
            "bytes": p.stat().st_size,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime, TZ_CN).isoformat(),
        }
    if any(g["status"] == "fail" for g in gates):
        raise FileNotFoundError("输入文件缺失，版本锁无法建立")
    gates.append({"gate": "input_exists", "status": "pass", "detail": f"{len(input_files)} 个输入"})

    # 版本锁：月末 + bundle_version
    bundle_versions: list[str] = []
    bundle_file = input_paths.get("product_bundles")
    if bundle_file and Path(bundle_file).exists():
        bdf = pd.read_csv(bundle_file, dtype=str, low_memory=False, keep_default_na=False)
        if "bundle_version" in bdf.columns:
            bundle_versions = sorted({v.strip() for v in bdf["bundle_version"] if v.strip()})
    version_ok = bool(bundle_versions)
    gates.append({
        "gate": "version_lock", "status": "pass" if version_ok else "fail",
        "detail": f"month_end={_month_end(month)}; bundle_versions={len(bundle_versions)}",
    })
    if not version_ok:
        raise RuntimeError("版本锁失败：product_bundles 缺 bundle_version")

    # 选仓桶（USNJ/USTX 中行数较小者）
    bucket_counts = Counter(str(r.get("warehouse_bucket") or "") for r in phase2.rows)
    if not bucket:
        candidates = [(bucket_counts.get(b, 0), b) for b in ("USNJ", "USTX") if bucket_counts.get(b)]
        bucket = min(candidates)[1] if candidates else "USNJ"
    gates.append({"gate": "canary_bucket", "status": "pass", "detail": f"{bucket}: {bucket_counts.get(bucket, 0)} rows"})

    fingerprint = _sha_json({
        "inputs": {k: v["sha256"] for k, v in sorted(input_files.items())},
        "month": month, "bucket": bucket,
    })
    if run_id is None:
        run_id = f"{month}-{bucket}-{datetime.now(TZ_CN):%Y%m%dT%H%M%S}-{fingerprint[:8]}"
    run_dir = runs_root / run_id
    if run_dir.exists():
        if any(run_dir.iterdir()):
            gates.append({"gate": "immutable_run", "status": "fail", "detail": f"run 目录非空: {run_dir}"})
            raise FileExistsError(f"run 目录非空，拒绝覆盖: {run_dir}")
        run_dir.rmdir()
    index_path = runs_root / "_written_index.json"
    prior = _read_index(index_path)
    duplicated = [x for x in prior if x.get("fingerprint") == fingerprint and x.get("completed")]
    if duplicated and not allow_duplicate:
        gates.append({"gate": "duplicate_write", "status": "fail", "detail": f"已完成同指纹 run: {duplicated[0]['run_id']}"})
        raise RuntimeError(f"重复写入：同指纹 run 已完成 {duplicated[0]['run_id']}")
    gates.append({"gate": "duplicate_write", "status": "pass", "detail": "无重复" if not duplicated else "allow_duplicate"})

    # Canary 行：按 phase2 bucket 对齐 rehearsal 行
    canary_rows: list[dict] = []
    canary_meta: list[dict] = []
    for row, p2 in zip(rehearsal.rows, phase2.rows):
        if str(p2.get("warehouse_bucket") or "") != bucket:
            continue
        out = dict(row)
        out["warehouse_bucket"] = bucket
        out["cost_status"] = (
            "excluded_non_product" if row.get("cost_status") == "non_product_accessory"
            else row.get("cost_status")
        )
        canary_rows.append(out)
        canary_meta.append(p2)
    gates.append({
        "gate": "canary_nonempty", "status": "pass" if canary_rows else "fail",
        "detail": f"{len(canary_rows)} rows",
    })

    totals = {
        c: round(sum(float(r.get(_amount_col(c)) or 0.0) for r in canary_rows), 6)
        for c in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本")
    }
    key_list = sorted(k for k, _ in _keyed(canary_rows))
    row_hash = _sha_json([{k: _nonempty(v) for k, v in r.items()} for r in canary_rows])
    summary_core = {
        "month": month, "bucket": bucket,
        "rows": len(canary_rows), "totals": totals,
        "key_hash": _sha_json(key_list), "row_hash": row_hash,
    }
    summary_hash = _sha_json(summary_core)

    # diff vs 旧写回
    old = pd.read_csv(old_writeback_csv, dtype=str, low_memory=False, keep_default_na=False) if old_writeback_csv else pd.DataFrame()
    old_bucket_rows = [
        rec for rec in old.to_dict("records")
        if warehouse_bucket(str(rec.get("发货仓按销售汇总分类") or "")) == bucket
    ]
    old_by_key: dict[str, list[dict]] = {}
    for key, rec in _keyed(old_bucket_rows):
        old_by_key.setdefault(key, []).append(rec)
    canary_by_key = dict(_keyed(canary_rows))
    duplicate_keys = sorted(k for k, v in old_by_key.items() if len(v) > 1)
    matched = sorted(set(canary_by_key) & set(old_by_key))
    canary_only = sorted(set(canary_by_key) - set(old_by_key))
    old_only = sorted(set(old_by_key) - set(canary_by_key))

    diff_rows: list[dict] = []
    for key in matched:
        ours = canary_by_key[key]
        old_rows = old_by_key[key]
        row = {"key": key, "status": "matched", "method": ours.get("method"), "cost_status": ours.get("cost_status")}
        for c in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本"):
            row[f"我方_{c}"] = round(float(ours.get(_amount_col(c)) or 0.0), 6)
            row[f"旧_{c}"] = round(sum(
                (_num(o.get(c)) or 0.0) * (_num(o.get("发货数量")) or 0.0) for o in old_rows
            ), 6)
            row[f"diff_{c}"] = round(row[f"我方_{c}"] - row[f"旧_{c}"], 6)
        diff_rows.append(row)
    for key in canary_only:
        r = canary_by_key[key]
        old_by_key.setdefault(key, [])
        diff_rows.append({"key": key, "status": "canary_only", "method": r.get("method"), "cost_status": r.get("cost_status")})
    for key in old_only:
        diff_rows.append({"key": key, "status": "old_only", "rows": len(old_by_key[key])})

    template = rehearsal.template_columns
    column_counter: Counter = Counter()
    for key in matched:
        ours, olds = canary_by_key[key], old_by_key[key]
        old_vals = olds[0]  # 重复 key 已单独报告，列级取首行
        if len(olds) > 1:
            continue
        for col in template:
            if _nonempty(ours.get(col)) != _nonempty(old_vals.get(col)):
                column_counter[col] += 1
    column_diffs = [
        {"列": c, "差异行数": n, "匹配行数": len(matched)}
        for c, n in column_counter.most_common()
    ]

    # 金额分层
    canary_key_by_id = {id(r): k for k, r in _keyed(canary_rows)}
    layer_sets = {
        **{
            f"method:{m}": [r for r in canary_rows if _nonempty(r.get("method")) == m]
            for m in ("皮壳", "半成品", "成品")
        },
        "套件": [r for r in canary_rows if r.get("method_source") == "kit_bundle"],
        "非商品配件": [r for r in canary_rows if r.get("cost_status") == "excluded_non_product"],
        "利润空白": [
            r for r in canary_rows
            if not _nonempty(r.get("订单利润")) and _nonempty(r.get("derived_reason"))
        ],
    }
    amount_layers = []
    for layer, lrows in layer_sets.items():
        if not lrows:
            continue
        entry = {"layer": layer, "rows": len(lrows)}
        for c in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本"):
            ours = round(sum(float(r.get(_amount_col(c)) or 0.0) for r in lrows), 6)
            old_total = 0.0
            for r in lrows:
                for o in old_by_key.get(canary_key_by_id[id(r)], []):
                    old_total += (_num(o.get(c)) or 0.0) * (_num(o.get("发货数量")) or 0.0)
            entry[f"我方_{c}"] = ours
            entry[f"旧_{c}"] = round(old_total, 6)
            entry[f"diff_{c}"] = round(ours - old_total, 6)
        amount_layers.append(entry)

    # 行级差异解释
    from .diff_explain import explain_canary, render_explain_md, write_explain_xlsx
    disabled_path = input_paths.get("disabled_items")
    disabled = set()
    if disabled_path and Path(disabled_path).exists():
        disabled = {
            line.strip() for line in Path(disabled_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    explain = explain_canary(
        canary_rows, canary_meta, old_bucket_rows,
        bom_csv=input_paths["bom_kits"],
        ref_map_csv=input_paths["item_refcode"],
        wh_tsv=input_paths["wh_map"],
        bundle_map_csv=input_paths.get("product_bundles"),
        kit_report_csv=input_paths.get("kit_report"),
        prev_bom_csv=input_paths.get("import_bom_prev"),
        disabled_items=disabled,
        bucket=bucket,
    )
    gates.append({
        "gate": "explain_coverage", "status": "pass" if explain.coverage >= 0.95 else "fail",
        "detail": f"coverage={explain.coverage:.2%}; unexplained={explain.summary['unexplained_abs_diff']:g}",
    })

    # 非商品配件 / 利润空白单独对账
    accessories = [r for r in canary_rows if r.get("cost_status") == "excluded_non_product"]
    accessory_check = {
        "rows": len(accessories),
        "four_zero": all(
            _nonempty(r.get(c)) == "0"
            for r in accessories
            for c in ("皮壳成本", "头程运费金额", "二次加工成本", "绍兴二次加工成本")
        ),
    }
    profit_blank = [
        r for r in canary_rows
        if not _nonempty(r.get("订单利润")) and _nonempty(r.get("derived_reason"))
    ]
    profit_not_zero = all(_nonempty(r.get("订单利润")) != "0" for r in profit_blank)

    # 写包（先写临时目录再改名，保证不可变）
    runs_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = runs_root / f".{run_id}.tmp"
    if tmp_dir.exists():
        raise FileExistsError(tmp_dir)
    tmp_dir.mkdir()
    canary_name = f"writeback_canary_{month}_{bucket}.csv"
    canary_path = tmp_dir / canary_name
    pd.DataFrame(canary_rows).to_csv(canary_path, index=False, encoding="utf-8-sig")
    canary_sha = _sha256(canary_path)

    summary = {
        **summary_core,
        "summary_hash": summary_hash,
        "canary_file": canary_name,
        "canary_sha256": canary_sha,
        "row_match": {"matched": len(matched), "canary_only": len(canary_only),
                      "old_only": len(old_only), "duplicate_old_keys": len(duplicate_keys)},
        "column_diff_top": column_diffs[:20],
        "amount_layers": amount_layers,
        "accessory_check": accessory_check,
        "profit_blank": {"rows": len(profit_blank), "not_zero": profit_not_zero},
        "explain": explain.summary,
        "fingerprint": fingerprint,
        "run_id": run_id,
        "month_end": _month_end(month),
        "bucket": bucket,
    }
    readback = _readback(canary_path, summary_core, summary_hash, totals)
    (tmp_dir / "manifest.json").write_text(
        json.dumps({
            "run_id": run_id, "fingerprint": fingerprint, "month": month, "bucket": bucket,
            "month_end": _month_end(month),
            "created_at": datetime.now(TZ_CN).isoformat(),
            "inputs": input_files,
            "bundle_versions": bundle_versions,
            "bundle_versions_hash": _sha_json(bundle_versions),
            "summary_hash": summary_hash,
            "explain_coverage": explain.coverage,
            "explain_summary": explain.summary,
            "canary_file": canary_name, "canary_sha256": canary_sha,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (tmp_dir / "summary.md").write_text(
        _render_summary(summary) + _render_gates(gates, readback["checks"]), encoding="utf-8"
    )
    audit_lines = [f"{datetime.now(TZ_CN).isoformat()} run={run_id} fingerprint={fingerprint}"]
    audit_lines += [f"{g['gate']}: {g['status']} - {g['detail']}" for g in gates]
    audit_lines.append(f"canary={len(canary_rows)} totals={totals} hash={summary_hash}")
    audit_lines += [
        f"readback {c['check']}: {c['status']} - {c['detail']}" for c in readback["checks"]
    ]
    (tmp_dir / "audit.log").write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    (tmp_dir / "readback.json").write_text(
        json.dumps(readback, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    diff_xlsx = tmp_dir / "diff.xlsx"
    _write_diff_xlsx(diff_xlsx, summary, diff_rows, column_diffs, amount_layers, gates, readback)
    write_explain_xlsx(explain, tmp_dir / "diff_explain.xlsx")
    (tmp_dir / "diff_explain.md").write_text(render_explain_md(explain), encoding="utf-8")

    # 完成：原子改名
    tmp_dir.rename(run_dir)
    readback_ok = all(c["status"] == "pass" for c in readback["checks"])
    if readback_ok and not any(g["status"] == "fail" for g in gates):
        prior.append({
            "run_id": run_id, "fingerprint": fingerprint, "month": month, "bucket": bucket,
            "completed": True, "completed_at": datetime.now(TZ_CN).isoformat(),
            "canary_sha256": canary_sha, "summary_hash": summary_hash,
        })
    index_path.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")

    return RunPackage(
        run_id=run_id, run_dir=run_dir, manifest=json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")),
        canary_rows=canary_rows, summary=summary, diff_rows=diff_rows,
        column_diffs=column_diffs, amount_layers=amount_layers,
        gates=gates, readback=readback["checks"],
    )


def _readback(path: Path, summary_core: dict, summary_hash: str, totals: dict) -> dict:
    df = pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False)
    rows = df.to_dict("records")
    keys = sorted(k for k, _ in _keyed(rows))
    got_totals = {
        c: round(sum(float(r.get(_amount_col(c)) or 0.0) for r in rows), 6)
        for c in totals
    }
    row_hash = _sha_json([{k: _nonempty(v) for k, v in r.items()} for r in rows])
    checks = [
        {"check": "行数", "status": "pass" if len(rows) == summary_core["rows"] else "fail",
         "detail": f"{len(rows)} vs {summary_core['rows']}"},
        {"check": "键唯一", "status": "pass" if len(keys) == len(set(keys)) else "fail",
         "detail": f"{len(keys)} keys"},
        {"check": "键 hash", "status": "pass" if _sha_json(keys) == summary_core["key_hash"] else "fail",
         "detail": summary_core["key_hash"][:12]},
        {"check": "四列金额", "status": "pass" if all(abs(got_totals[c] - totals[c]) <= TOL for c in totals) else "fail",
         "detail": str(got_totals)},
        {"check": "行 hash", "status": "pass" if row_hash == summary_core["row_hash"] else "fail",
         "detail": row_hash[:12]},
        {"check": "摘要 hash", "status": "pass" if _sha_json(summary_core) == summary_hash else "fail",
         "detail": summary_hash[:12]},
    ]
    return {"checks": checks, "row_hash": row_hash, "totals": got_totals}


def _render_gates(gates: list[dict], checks: list[dict]) -> str:
    lines = ["", "## 门禁", "", "| 门禁 | 结果 | 说明 |", "|---|---|---|"]
    for g in gates:
        lines.append(f"| {g['gate']} | {g['status']} | {g['detail']} |")
    lines += ["", "## 写后回读", "", "| 检查 | 结果 | 说明 |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['check']} | {c['status']} | {c['detail']} |")
    lines.append("")
    return "\n".join(lines)


def _render_summary(summary: dict) -> str:
    t = summary["totals"]
    lines = [
        f"# 写回 Canary — {summary['month']} / {summary['bucket']}",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- fingerprint: `{summary['fingerprint']}`",
        f"- 月末版本: {summary['month_end']}",
        f"- 行数: {summary['rows']}",
        f"- 四列合计: 皮壳 {t['皮壳成本']:g} / 头程 {t['头程运费金额']:g} / "
        f"二次 {t['二次加工成本']:g} / 绍兴二次 {t['绍兴二次加工成本']:g}",
        f"- canary sha256: `{summary['canary_sha256']}`",
        f"- summary hash: `{summary['summary_hash']}`",
        f"- 行匹配: {summary['row_match']}",
        f"- 非商品配件: {summary['accessory_check']}",
        f"- 利润空白: {summary['profit_blank']}",
        "",
        "## 列差异 Top",
        "",
    ]
    for c in summary["column_diff_top"][:10]:
        lines.append(f"- {c['列']}: {c['差异行数']} / {c['匹配行数']} 行")
    lines += ["", "## 金额分层", ""]
    for l in summary["amount_layers"]:
        lines.append(
            f"- {l['layer']}: {l['rows']} 行；"
            f"皮壳 {l['diff_皮壳成本']:g} / 头程 {l['diff_头程运费金额']:g} / "
            f"二次 {l['diff_二次加工成本']:g} / 绍兴二次 {l['diff_绍兴二次加工成本']:g}（我方−旧）"
        )
    lines.append("")
    return "\n".join(lines)


def _write_diff_xlsx(path: Path, summary: dict, diff_rows: list[dict],
                     column_diffs: list[dict], amount_layers: list[dict],
                     gates: list[dict], readback: dict) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([
            {"指标": "月份", "值": summary["month"]},
            {"指标": "仓桶", "值": summary["bucket"]},
            {"指标": "行数", "值": summary["rows"]},
            {"指标": "summary_hash", "值": summary["summary_hash"]},
            {"指标": "canary_sha256", "值": summary["canary_sha256"]},
            {"指标": "行匹配", "值": str(summary["row_match"])},
            {"指标": "非商品配件对账", "值": str(summary["accessory_check"])},
            {"指标": "利润空白对账", "值": str(summary["profit_blank"])},
        ]).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(diff_rows).to_excel(writer, sheet_name="行匹配", index=False)
        pd.DataFrame(column_diffs).to_excel(writer, sheet_name="列差异", index=False)
        pd.DataFrame(amount_layers).to_excel(writer, sheet_name="金额分层", index=False)
        pd.DataFrame(gates).to_excel(writer, sheet_name="门禁", index=False)
        pd.DataFrame(readback["checks"]).to_excel(writer, sheet_name="回读", index=False)
