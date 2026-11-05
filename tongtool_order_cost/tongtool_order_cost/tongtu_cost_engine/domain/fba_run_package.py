# -*- coding: utf-8 -*-
"""Phase 4.FBA canary：本地 run 包（绝不写 GS/EN）。

- 选 202608 FBA 的最小站点桶（按账号/站点分组，排除待确认 SKU），生成 78 列写回骨架 canary。
- 四列取自 FBA shadow（成品口径；头程=FBA 成品头程；二次=0）。
- 写前：目标行旧值备份 + hash、输入 manifest（订单/EN/BOM/套件/白名单）、diff；
  写后回读模拟：行数/主键/四列/非目标列零变化/摘要 hash。
- 待审行与直采零成本行保留状态：不填 0、不沿用旧值。
- 不可变 `out/runs/fba-<month>-<bucket>-<ts>/`（manifest/audit/readback/diff/summary/csv）。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .fba_shadow import MERGED_COLUMNS
from .split_merge import normalize_sku

TZ_CN = timezone(timedelta(hours=8))
TOL = 0.01
FBA_FOUR = ("皮壳成本", "绍兴二次加工成本", "二次加工成本", "头程运费金额")
STATUS_COLUMNS = ("cost_status", "auto_pref", "bridge_status", "bridge_reason", "unique_key")


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


def _text(v) -> str:
    return str(v).strip() if v is not None else ""


def _amount_col(col: str) -> str:
    return "头程运费*数量" if col == "头程运费金额" else f"{col}*数量"


TARGET_COLUMNS = tuple(FBA_FOUR) + tuple(_amount_col(c) for c in FBA_FOUR)


def _month_end(month: str) -> str:
    import calendar
    year, mon = int(month[:4]), int(month[4:6])
    return f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}"


def _key(row: Mapping) -> str:
    site = _text(row.get("站点")) or _text(row.get("site")) or _text(row.get("渠道账号"))
    return "|".join((
        site,
        normalize_sku(row.get("MSKU") or row.get("平台SKU") or row.get("gs_msku")),
        normalize_sku(row.get("SKU") or row.get("通途SKU") or row.get("gs_sku")),
    ))


def _row_key(row: Mapping) -> str:
    return _text(row.get("unique_key")) or "|".join((
        _text(row.get("订单号")), normalize_sku(row.get("平台SKU")), normalize_sku(row.get("通途SKU")),
    ))


def _cost_status(row: Mapping) -> str:
    if _text(row.get("bridge_status")) != "ok":
        return f"pending:{_text(row.get('bridge_reason')) or 'unknown'}"
    if _text(row.get("bridge_reason")) == "direct_purchase_zero":
        return "direct_purchase_zero"
    return "priced"


def _read_index(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


@dataclass
class FbaRunPackage:
    run_id: str
    run_dir: Path
    manifest: dict
    canary_rows: list[dict]
    summary: dict
    diff_rows: list[dict]
    gates: list[dict]
    readback: list[dict]

    @property
    def ok(self) -> bool:
        return all(g["status"] != "fail" for g in self.gates + self.readback)


def build_fba_run_package(
    *,
    month: str,
    root: str | Path = ".",
    bucket: str | None = None,
    exclude_skus: Sequence[str] = ("OSKBG-RSUS-FBA",),
    runs_root: str | Path | None = None,
    shadow_csv: str | Path | None = None,
    gs_csv: str | Path | None = None,
    en_csv: str | Path | None = None,
    bom_csv: str | Path | None = None,
    bundle_csv: str | Path | None = None,
    ref_map_csv: str | Path | None = None,
    whitelist_csv: str | Path | None = None,
    old_source_csv: str | Path | None = None,
    allow_duplicate: bool = False,
    run_id: str | None = None,
) -> FbaRunPackage:
    root = Path(root)
    out = root / "out"
    shadow_csv = Path(shadow_csv or out / "fba_shadow" / month / f"fba_shadow_{month}.csv")
    gs_csv = Path(gs_csv or out / f"raw_fba_{month}.csv")
    en_csv = Path(en_csv or out / "en_items_all_089.csv")
    bom_csv = Path(bom_csv or out / "bom_cost_product_with_kits.csv")
    bundle_csv = Path(bundle_csv or out / "product_bundles.csv")
    ref_map_csv = Path(ref_map_csv or out / "item_refcode.csv")
    whitelist_csv = Path(whitelist_csv or out / "fba_shadow" / month / f"fba_whitelist_{month}.csv")
    runs_root = Path(runs_root or out / "runs")
    # 旧值来源 = 目标写回表 FBA 行（merged_<month>.csv）；缺失时退回到 FBA 销量报表
    old_source_csv = Path(old_source_csv) if old_source_csv else out / f"merged_{month}.csv"
    old_source_kind = "writeback"
    if not old_source_csv.exists():
        old_source_csv = Path(gs_csv)
        old_source_kind = "fba_report"

    gates: list[dict] = []
    input_files: dict[str, dict] = {}
    input_paths = {
        "fba_shadow": shadow_csv,
        "gs_fba_orders": gs_csv,
        "en_items": en_csv,
        "bom_kits": bom_csv,
        "product_bundles": bundle_csv,
        "item_refcode": ref_map_csv,
        "whitelist": whitelist_csv,
        "old_target": old_source_csv,
    }
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

    # 版本锁：月末 + bundle_version + 白名单 hash
    bundle_versions: list[str] = []
    if bundle_csv.exists():
        bdf = pd.read_csv(bundle_csv, dtype=str, low_memory=False, keep_default_na=False)
        if "bundle_version" in bdf.columns:
            bundle_versions = sorted({v.strip() for v in bdf["bundle_version"] if str(v).strip()})
    whitelist_sha = input_files.get("whitelist", {}).get("sha256", "")
    version_ok = bool(bundle_versions) and bool(whitelist_sha)
    gates.append({
        "gate": "version_lock", "status": "pass" if version_ok else "fail",
        "detail": f"month_end={_month_end(month)}; bundle_versions={len(bundle_versions)}; "
                  f"whitelist_sha={whitelist_sha[:12]}",
    })
    if not version_ok:
        raise RuntimeError("版本锁失败：product_bundles 缺 bundle_version 或白名单缺失")

    shadow = pd.read_csv(shadow_csv, dtype=str, low_memory=False, keep_default_na=False)
    rows = shadow.to_dict("records")
    exclude_norm = {normalize_sku(x) for x in exclude_skus if normalize_sku(x)}
    kept = [
        r for r in rows
        if normalize_sku(r.get("平台SKU")) not in exclude_norm
        and normalize_sku(r.get("通途SKU")) not in exclude_norm
    ]

    # 选桶：按站点，取最小桶（行数 → 数量 → 站点名）；待审行按状态保留，不静默丢
    groups: dict[str, list[dict]] = {}
    for r in kept:
        groups.setdefault(_text(r.get("site")), []).append(r)
    candidates = {s: rs for s, rs in groups.items() if s}
    if not candidates:
        gates.append({"gate": "canary_bucket", "status": "fail", "detail": "无可用站点桶"})
        raise RuntimeError("无可用站点桶")
    if bucket:
        if bucket not in candidates:
            gates.append({"gate": "canary_bucket", "status": "fail", "detail": f"{bucket} 不可用"})
            raise RuntimeError(f"指定桶不可用: {bucket}")
        bucket_rows = candidates[bucket]
    else:
        bucket = min(candidates, key=lambda s: (len(candidates[s]),
                                                sum(_num(r.get("发货数量")) or 0.0 for r in candidates[s]),
                                                s))
        bucket_rows = candidates[bucket]
    gates.append({"gate": "canary_bucket", "status": "pass",
                  "detail": f"{bucket}: {len(bucket_rows)} rows"})

    # 排除待确认 SKU 生效校验（canary 内不得出现）
    leaked = [r for r in bucket_rows if normalize_sku(r.get("通途SKU")) in exclude_norm]
    gates.append({"gate": "excluded_skus_absent", "status": "pass" if not leaked else "fail",
                  "detail": f"excluded={sorted(exclude_norm)}; leaked={len(leaked)}"})

    # 78 列骨架 + 状态列
    canary_rows: list[dict] = []
    for r in bucket_rows:
        out_row = {c: _text(r.get(c)) for c in MERGED_COLUMNS}
        if not out_row["渠道账号"]:
            out_row["渠道账号"] = _text(r.get("site"))
        out_row.update({
            "cost_status": _cost_status(r),
            "auto_pref": _text(r.get("auto_pref")),
            "bridge_status": _text(r.get("bridge_status")),
            "bridge_reason": _text(r.get("bridge_reason")),
            "unique_key": _row_key(r),
        })
        canary_rows.append(out_row)

    pending_rows = [r for r in canary_rows if r["cost_status"].startswith("pending:")]
    pending_blank = all(
        _text(r.get(c)) == "" for r in pending_rows for c in TARGET_COLUMNS
    )
    gates.append({
        "gate": "pending_status_preserved", "status": "pass" if pending_blank else "fail",
        "detail": f"pending={len(pending_rows)}; 成本列留空={pending_blank}",
    })

    # 重复检测：行级唯一键 / 业务键
    key_counter = Counter(_row_key(r) for r in canary_rows)
    biz_counter = Counter(_key(r) for r in canary_rows)
    dup_keys = [k for k, n in key_counter.items() if n > 1]
    dup_biz = [k for k, n in biz_counter.items() if n > 1]
    gates.append({
        "gate": "duplicate_keys",
        "status": "pass" if not dup_keys and not dup_biz else "fail",
        "detail": f"unique_key_dupes={len(dup_keys)}; business_key_dupes={len(dup_biz)}",
    })

    fingerprint = _sha_json({
        "inputs": {k: v["sha256"] for k, v in sorted(input_files.items())},
        "month": month, "bucket": bucket, "exclude": sorted(exclude_norm),
    })
    if run_id is None:
        run_id = f"fba-{month}-{bucket}-{datetime.now(TZ_CN):%Y%m%dT%H%M%S}"
    run_dir = runs_root / run_id
    if run_dir.exists():
        if any(run_dir.iterdir()):
            gates.append({"gate": "immutable_run", "status": "fail", "detail": f"run 目录非空: {run_dir}"})
            raise FileExistsError(f"run 目录非空，拒绝覆盖: {run_dir}")
        run_dir.rmdir()
    gates.append({"gate": "immutable_run", "status": "pass", "detail": f"{run_dir.name}: 新建"})
    index_path = runs_root / "_written_index.json"
    prior = _read_index(index_path)
    duplicated = [x for x in prior if x.get("fingerprint") == fingerprint and x.get("completed")]
    if duplicated and not allow_duplicate:
        gates.append({"gate": "duplicate_write", "status": "fail",
                      "detail": f"已完成同指纹 run: {duplicated[0]['run_id']}"})
        raise RuntimeError(f"重复写入：同指纹 run 已完成 {duplicated[0]['run_id']}")
    gates.append({"gate": "duplicate_write", "status": "pass",
                  "detail": "无重复" if not duplicated else "allow_duplicate"})

    # 旧值备份 + diff：目标写回表 FBA 行（merged_<month>.csv）四列/头程
    try:
        old_df = pd.read_csv(old_source_csv, dtype=str, low_memory=False, keep_default_na=False)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        old_df = pd.DataFrame()
    old_records = old_df.to_dict("records")
    if old_source_kind == "writeback":
        if "发货仓分类" in old_df.columns:
            old_records = [r for r in old_records if _text(r.get("发货仓分类")) == "FBA"]
        elif "发货仓库" in old_df.columns:
            old_records = [r for r in old_records if "FBA" in _text(r.get("发货仓库")).upper()]
        site_col = "渠道账号" if "渠道账号" in old_df.columns else "站点"
    else:
        site_col = "站点"
    old_bucket_rows = [r for r in old_records if _text(r.get(site_col)) == bucket]
    old_by_key: dict[str, list[dict]] = {}
    for r in old_bucket_rows:
        old_by_key.setdefault(_key(r), []).append(r)
    gates.append({
        "gate": "old_source_ok",
        "status": "pass" if old_bucket_rows else "fail",
        "detail": f"{old_source_kind}: {old_source_csv.name}; rows={len(old_bucket_rows)}",
    })

    def _old_amount(rows: list[dict], unit_col: str) -> float:
        total = 0.0
        for o in rows:
            amt = _num(o.get(_amount_col(unit_col)))
            if amt is None:
                amt = (_num(o.get(unit_col)) or 0.0) * (_num(o.get("发货数量")) or 0.0)
            total += amt
        return round(total, 6)

    def _diff(a, b) -> float | None:
        if a is None or b is None:
            return None
        return round(b - a, 6)

    diff_rows: list[dict] = []
    matched = canary_only = old_only = 0
    diff_sums = {k: [0.0, 0.0] for k in ("皮壳", "绍兴侧", "二次", "头程", "1件合计")}
    for r in canary_rows:
        k = _key(r)
        olds = old_by_key.get(k, [])
        new_shell = _num(r.get("皮壳成本"))
        new_sx2 = _num(r.get("绍兴二次加工成本"))
        new_proc = _num(r.get("二次加工成本"))
        new_head = _num(r.get("头程运费金额"))
        new_one = _num(r.get("1件产品成本"))
        new_amt = {c: _num(r.get(_amount_col(c))) or 0.0 for c in FBA_FOUR}
        if not olds:
            canary_only += 1
            diff_rows.append({
                "key": k, "status": "canary_only", "cost_status": r["cost_status"],
                "auto_pref": r["auto_pref"], "qty_old": "", "qty_canary": r.get("发货数量"),
                "qty_diff": "", "diff_reason": "",
                "new_皮壳成本": new_shell, "new_绍兴二次加工成本": new_sx2,
                "new_二次加工成本": new_proc, "new_头程运费金额": new_head,
                "new_1件产品成本": new_one,
            })
            continue
        matched += 1
        qty_old = sum(_num(o.get("发货数量")) or 0.0 for o in olds)
        rep = max(olds, key=lambda o: _num(o.get("发货数量")) or 0.0)
        if old_source_kind == "writeback":
            old_shell = _num(rep.get("皮壳成本"))
            old_sx2 = _num(rep.get("绍兴二次加工成本"))
            old_proc = _num(rep.get("二次加工成本"))
            old_head = _num(rep.get("头程运费金额"))
            old_one = _num(rep.get("1件产品成本"))
            old_amt = {c: _old_amount(olds, c) for c in FBA_FOUR}
        else:  # fba_report：只有 成本/头程费用
            old_shell = old_sx2 = old_proc = old_one = None
            old_head = _num(rep.get("头程费用"))
            old_amt = {"皮壳成本": 0.0, "绍兴二次加工成本": 0.0, "二次加工成本": 0.0,
                       "头程运费金额": _old_amount(olds, "头程运费金额") if "头程运费金额" in rep else 0.0}
            old_amt["绍兴二次加工成本"] = _num(rep.get("成本")) or 0.0
        old_sx_side = None if old_sx2 is None or old_proc is None else round(old_sx2 + old_proc, 6)
        new_sx_side = None if new_sx2 is None or new_proc is None else round(new_sx2 + new_proc, 6)
        new_unit_amt = {
            "皮壳成本": new_amt["皮壳成本"], "绍兴二次加工成本": new_amt["绍兴二次加工成本"],
            "二次加工成本": new_amt["二次加工成本"], "头程运费金额": new_amt["头程运费金额"],
        }
        old_sx_side_amt = round(old_amt["绍兴二次加工成本"] + old_amt["二次加工成本"], 6)
        new_sx_side_amt = round(new_unit_amt["绍兴二次加工成本"] + new_unit_amt["二次加工成本"], 6)
        old_one_amt = round(old_amt["皮壳成本"] + old_sx_side_amt, 6)
        new_one_amt = round(new_unit_amt["皮壳成本"] + new_sx_side_amt, 6)
        diffs = [d for d in (
            _diff(old_shell, new_shell), _diff(old_sx_side, new_sx_side),
            _diff(old_head, new_head),
        ) if d is not None and abs(d) > TOL]
        note = ""
        if old_source_kind == "writeback" and old_proc and new_sx2 \
                and abs(old_proc) > TOL and abs(new_sx2) > TOL:
            note = "旧写回绍兴侧在二次加工列；新口径归入绍兴二次"
        diff_rows.append({
            "key": k, "status": "matched", "cost_status": r["cost_status"],
            "auto_pref": r["auto_pref"],
            "qty_old": qty_old, "qty_canary": r.get("发货数量"),
            "qty_diff": round((_num(r.get("发货数量")) or 0.0) - qty_old, 6),
            "old_皮壳成本": old_shell, "new_皮壳成本": new_shell,
            "diff_皮壳成本": _diff(old_shell, new_shell),
            "old_绍兴二次加工成本": old_sx2, "new_绍兴二次加工成本": new_sx2,
            "diff_绍兴二次加工成本": _diff(old_sx2, new_sx2),
            "old_二次加工成本": old_proc, "new_二次加工成本": new_proc,
            "diff_二次加工成本": _diff(old_proc, new_proc),
            "old_绍兴侧": old_sx_side, "new_绍兴侧": new_sx_side,
            "diff_绍兴侧": _diff(old_sx_side, new_sx_side),
            "old_头程运费金额": old_head, "new_头程运费金额": new_head,
            "diff_头程运费金额": _diff(old_head, new_head),
            "old_1件产品成本": old_one, "new_1件产品成本": new_one,
            "diff_1件产品成本": _diff(old_one, new_one),
            "old_金额_皮壳": old_amt["皮壳成本"], "new_金额_皮壳": new_unit_amt["皮壳成本"],
            "diff_金额_皮壳": round(new_unit_amt["皮壳成本"] - old_amt["皮壳成本"], 6),
            "old_金额_绍兴侧": old_sx_side_amt, "new_金额_绍兴侧": new_sx_side_amt,
            "diff_金额_绍兴侧": round(new_sx_side_amt - old_sx_side_amt, 6),
            "old_金额_头程": old_amt["头程运费金额"], "new_金额_头程": new_unit_amt["头程运费金额"],
            "diff_金额_头程": round(new_unit_amt["头程运费金额"] - old_amt["头程运费金额"], 6),
            "old_金额_1件": old_one_amt, "new_金额_1件": new_one_amt,
            "diff_金额_1件": round(new_one_amt - old_one_amt, 6),
            "diff_reason": "bom_version_change" if diffs else "",
            "caliber_note": note,
        })
        diff_sums["皮壳"][0] += old_amt["皮壳成本"]; diff_sums["皮壳"][1] += new_unit_amt["皮壳成本"]
        diff_sums["绍兴侧"][0] += old_sx_side_amt; diff_sums["绍兴侧"][1] += new_sx_side_amt
        diff_sums["二次"][0] += old_amt["二次加工成本"]; diff_sums["二次"][1] += new_unit_amt["二次加工成本"]
        diff_sums["头程"][0] += old_amt["头程运费金额"]; diff_sums["头程"][1] += new_unit_amt["头程运费金额"]
        diff_sums["1件合计"][0] += old_one_amt; diff_sums["1件合计"][1] += new_one_amt
    canary_keys = {_key(r) for r in canary_rows}
    for k in old_by_key:
        if k not in canary_keys:
            old_only += 1
            diff_rows.append({"key": k, "status": "old_only"})
    diff_totals = {
        k: {"old": round(v[0], 6), "new": round(v[1], 6), "diff": round(v[1] - v[0], 6)}
        for k, v in diff_sums.items()
    }

    totals = {
        c: round(sum(_num(r.get(_amount_col(c))) or 0.0 for r in canary_rows), 6)
        for c in FBA_FOUR
    }
    status_counts = dict(Counter(r["cost_status"] for r in canary_rows))
    key_list = sorted(_row_key(r) for r in canary_rows)
    row_hash = _sha_json([{k: _text(v) for k, v in r.items()} for r in canary_rows])
    summary_core = {
        "month": month, "bucket": bucket, "rows": len(canary_rows),
        "totals": totals, "status_counts": status_counts,
        "key_hash": _sha_json(key_list), "row_hash": row_hash,
    }
    summary_hash = _sha_json(summary_core)

    # 写包（临时目录 → 原子改名）
    runs_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = runs_root / f".{run_id}.tmp"
    if tmp_dir.exists():
        raise FileExistsError(tmp_dir)
    tmp_dir.mkdir()
    canary_name = f"fba_canary_{month}_{bucket}.csv"
    canary_path = tmp_dir / canary_name
    pd.DataFrame(canary_rows).to_csv(canary_path, index=False, encoding="utf-8-sig")
    canary_sha = _sha256(canary_path)
    old_name = f"old_values_{month}_{bucket}.csv"
    old_path = tmp_dir / old_name
    pd.DataFrame(old_bucket_rows).to_csv(old_path, index=False, encoding="utf-8-sig")
    old_sha = _sha256(old_path)

    readback = _readback(canary_path, canary_rows, summary_core, summary_hash, totals)
    summary = {
        **summary_core,
        "run_id": run_id, "fingerprint": fingerprint, "month_end": _month_end(month),
        "summary_hash": summary_hash, "canary_file": canary_name, "canary_sha256": canary_sha,
        "old_values_file": old_name, "old_values_sha256": old_sha,
        "old_source": {"kind": old_source_kind, "file": old_source_csv.name,
                       "rows": len(old_bucket_rows)},
        "row_match": {"matched": matched, "canary_only": canary_only, "old_only": old_only},
        "duplicate_keys": {"unique": len(dup_keys), "business": len(dup_biz)},
        "diff_totals": diff_totals,
    }

    manifest = {
        "run_id": run_id, "fingerprint": fingerprint, "month": month, "bucket": bucket,
        "month_end": _month_end(month),
        "created_at": datetime.now(TZ_CN).isoformat(),
        "inputs": input_files,
        "bundle_versions": bundle_versions,
        "bundle_versions_hash": _sha_json(bundle_versions),
        "whitelist_sha256": whitelist_sha,
        "excluded_skus": sorted(x for x in exclude_skus if x),
        "old_source": {"kind": old_source_kind, "file": old_source_csv.name,
                       "rows": len(old_bucket_rows)},
        "canary_file": canary_name, "canary_sha256": canary_sha,
        "old_values_file": old_name, "old_values_sha256": old_sha,
        "summary_hash": summary_hash,
    }
    (tmp_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp_dir / "readback.json").write_text(
        json.dumps(readback, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(diff_rows).to_csv(tmp_dir / "diff.csv", index=False, encoding="utf-8-sig")
    (tmp_dir / "summary.md").write_text(
        _render_summary(summary) + _render_checks(gates, readback["checks"]), encoding="utf-8")
    audit_lines = [
        f"{datetime.now(TZ_CN).isoformat()} run={run_id} fingerprint={fingerprint}",
        f"canary={len(canary_rows)} bucket={bucket} totals={totals}",
    ]
    audit_lines += [f"gate {g['gate']}: {g['status']} - {g['detail']}" for g in gates]
    audit_lines += [f"readback {c['check']}: {c['status']} - {c['detail']}" for c in readback["checks"]]
    (tmp_dir / "audit.log").write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    # Windows 下杀软/索引可能短暂占用 tmp 目录，重试原子改名
    for attempt in range(5):
        try:
            tmp_dir.rename(run_dir)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2)

    readback_ok = all(c["status"] == "pass" for c in readback["checks"])
    if readback_ok and not any(g["status"] == "fail" for g in gates):
        prior.append({
            "run_id": run_id, "fingerprint": fingerprint, "month": month,
            "bucket": bucket, "kind": "fba_canary", "completed": True,
            "completed_at": datetime.now(TZ_CN).isoformat(),
            "canary_sha256": canary_sha, "summary_hash": summary_hash,
        })
    index_path.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")

    return FbaRunPackage(
        run_id=run_id, run_dir=run_dir,
        manifest=json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")),
        canary_rows=canary_rows, summary=summary, diff_rows=diff_rows,
        gates=gates, readback=readback["checks"],
    )


def _readback(path: Path, source_rows: Sequence[Mapping], summary_core: dict,
              summary_hash: str, totals: dict) -> dict:
    df = pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False)
    rows = df.to_dict("records")
    keys = sorted(_row_key(r) for r in rows)
    got_totals = {
        c: round(sum(_num(r.get(_amount_col(c))) or 0.0 for r in rows), 6)
        for c in totals
    }
    # 非目标列零变化（逐列逐行比较）
    compare_cols = [c for c in MERGED_COLUMNS + STATUS_COLUMNS if c not in TARGET_COLUMNS]
    changed: Counter = Counter()
    src_by_key = {_row_key(r): r for r in source_rows}
    for r in rows:
        src = src_by_key.get(_row_key(r))
        if src is None:
            continue
        for c in compare_cols:
            if _text(src.get(c)) != _text(r.get(c)):
                changed[c] += 1
    status_counts = dict(Counter(r.get("cost_status", "") for r in rows))
    pending_blank = all(
        _text(r.get(c)) == ""
        for r in rows if _text(r.get("cost_status")).startswith("pending:")
        for c in TARGET_COLUMNS
    )
    direct_rows = [r for r in rows if _text(r.get("cost_status")) == "direct_purchase_zero"]
    direct_zero = all(_text(r.get(_amount_col("绍兴二次加工成本"))) in ("", "0", "0.0")
                      for r in direct_rows)
    checks = [
        {"check": "行数", "status": "pass" if len(rows) == summary_core["rows"] else "fail",
         "detail": f"{len(rows)} vs {summary_core['rows']}"},
        {"check": "键唯一", "status": "pass" if len(keys) == len(set(keys)) else "fail",
         "detail": f"{len(keys)} keys"},
        {"check": "键 hash", "status": "pass" if _sha_json(keys) == summary_core["key_hash"] else "fail",
         "detail": summary_core["key_hash"][:12]},
        {"check": "四列金额",
         "status": "pass" if all(abs(got_totals[c] - totals[c]) <= TOL for c in totals) else "fail",
         "detail": str(got_totals)},
        {"check": "非目标列零变化", "status": "pass" if not changed else "fail",
         "detail": f"changed={dict(changed)}"},
        {"check": "状态保留", "status": "pass" if status_counts == summary_core["status_counts"] else "fail",
         "detail": str(status_counts)},
        {"check": "待审成本留空", "status": "pass" if pending_blank else "fail",
         "detail": f"pending={status_counts.get('pending:en_item_missing', 0)}"},
        {"check": "直采绍兴二次=0", "status": "pass" if direct_zero else "fail",
         "detail": f"rows={len(direct_rows)}"},
        {"check": "行 hash", "status": "pass" if _sha_json(
            [{k: _text(v) for k, v in r.items()} for r in rows]) == summary_core["row_hash"] else "fail",
         "detail": summary_core["row_hash"][:12]},
        {"check": "摘要 hash", "status": "pass" if _sha_json(summary_core) == summary_hash else "fail",
         "detail": summary_hash[:12]},
    ]
    return {"checks": checks, "row_hash": summary_core["row_hash"], "totals": got_totals,
            "status_counts": status_counts}


def _render_summary(summary: dict) -> str:
    t = summary["totals"]
    d = summary["diff_totals"]
    old = summary["old_source"]
    lines = [
        f"# FBA Canary — {summary['month']} / {summary['bucket']}",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- fingerprint: `{summary['fingerprint']}`",
        f"- 月末版本: {summary['month_end']}",
        f"- 行数: {summary['rows']}；状态: {summary['status_counts']}",
        f"- 四列合计: 皮壳 {t['皮壳成本']:g} / 绍兴二次 {t['绍兴二次加工成本']:g} / "
        f"二次 {t['二次加工成本']:g} / 头程 {t['头程运费金额']:g}",
        f"- 旧值来源: {old['kind']} / `{old['file']}`（{old['rows']} 行）",
        f"- 旧值备份: `{summary['old_values_file']}`（sha256 `{summary['old_values_sha256'][:12]}`）",
        f"- canary sha256: `{summary['canary_sha256']}`",
        f"- summary hash: `{summary['summary_hash']}`",
        f"- 行匹配: {summary['row_match']}；重复键: {summary['duplicate_keys']}",
        "",
        "## diff（金额，我方−旧）",
        "",
        "| 口径 | 旧 | 新 | 差 | 原因 |",
        "|---|---:|---:|---:|---|",
    ]
    reason = "BOM 版本变化" if any(abs(v["diff"]) > TOL for v in d.values()) else ""
    for k, v in d.items():
        if k == "二次":
            row_reason = "口径归位（并入绍兴侧）" if abs(v["diff"]) > TOL else "不变"
        elif abs(v["diff"]) > TOL:
            row_reason = reason or "BOM 版本变化"
        else:
            row_reason = "不变"
        lines.append(f"| {k} | {v['old']:g} | {v['new']:g} | {v['diff']:+g} | {row_reason} |")
    lines += ["", "单件口径（diff.csv）：皮壳 / 绍兴侧（绍兴二次+二次）/ 头程 / 1件合计。", ""]
    return "\n".join(lines)


def _render_checks(gates: list[dict], checks: list[dict]) -> str:
    lines = ["## 门禁", "", "| 门禁 | 结果 | 说明 |", "|---|---|---|"]
    for g in gates:
        lines.append(f"| {g['gate']} | {g['status']} | {g['detail']} |")
    lines += ["", "## 写后回读（模拟）", "", "| 检查 | 结果 | 说明 |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['check']} | {c['status']} | {c['detail']} |")
    lines.append("")
    return "\n".join(lines)
