# -*- coding: utf-8 -*-
"""同日快照一条命令流水线：快照 → 需求净额 → 供应净额 → 决策包 → 动作层。

设计原则
- **失败不覆盖**：所有输出先写进 ``.pipeline-<date>-<label>-<ts>`` 暂存目录，
  全部步骤成功后才改名到正式目录；失败时暂存目录改名 ``.failed-<ts>``，
  正式目录与 ``latest.json`` 指针都保持原样。
- **同一天多版**：``rN`` 由调用方给；正式名 ``run-<date>-<rN>`` /
  ``decision-pack-<date>-<rN>`` / ``pack-<date>-<rN>`` / ``actions-<date>-<rN>``。
- **快照校验**：列/日期/数值/行数/仓库数校验 + 冻结副本哈希，冻结副本一经存在不得静默替换。
- 只读输入、不写生产、不下单；动作层只做 join，不改净额数量。

用法
```bash
uv run python -m supply_netting.scripts.run_same_day \
  --snapshot-date 2026-10-26 \
  --stock D:/Work/fzh-order-store/en_stock.parquet \
  --demand D:/Work/fzh-order-store/en-demand-v1/canonical-r2/demand_netting.parquet \
  --label r1 --out-root D:/Work/fzh-order-store/en-demand-v1/supply-netting
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REQUIRED_SNAPSHOT_COLUMNS = ["snapshot_date", "snapshot_at", "warehouse_name", "sku",
                             "available", "intransit"]
DEFAULT_OUT_ROOT = "D:/Work/fzh-order-store/en-demand-v1/supply-netting"
DEFAULT_FORECAST_ROOT = "D:/Work/fzh-order-store/en-demand-v1/forecast"
DEFAULT_SKU_MAP = "D:/Work/fzh-order-store/sku_map.tsv"
FROZEN_SKU_MAP_SHA256 = "7da3dfd62969c2c06f5b01ce752ccd1bc8d26c46c693eaca22cacaad4d13d42e"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class StepError(RuntimeError):
    pass


def validate_snapshot(path: Path, snapshot_date: str) -> dict:
    """快照输入校验：列、日期、数值、行数、仓库数、时间戳。"""
    if not path.exists():
        raise StepError(f"库存快照不存在：{path}")
    frame = pd.read_parquet(path)
    missing = [c for c in REQUIRED_SNAPSHOT_COLUMNS if c not in frame.columns]
    if missing:
        raise StepError(f"库存快照缺列：{missing}")
    dates = sorted(pd.to_datetime(frame["snapshot_date"]).dt.date.astype(str).unique())
    if snapshot_date not in dates:
        raise StepError(f"快照里没有 {snapshot_date}；可用日期 {dates[-5:]}")
    part = frame[pd.to_datetime(frame["snapshot_date"]).dt.date.astype(str) == snapshot_date]
    if part.empty:
        raise StepError("所选快照日期没有行")
    available = pd.to_numeric(part["available"], errors="coerce")
    intransit = pd.to_numeric(part["intransit"], errors="coerce")
    if available.isna().any():
        raise StepError(f"available 有 {int(available.isna().sum())} 个非数值")
    if (available < 0).any():
        raise StepError("available 出现负值")
    snapshot_at = pd.to_datetime(part["snapshot_at"])
    if snapshot_at.isna().any():
        raise StepError("snapshot_at 有空值")
    warehouses = sorted(part["warehouse_name"].astype(str).unique().tolist())
    if len(warehouses) < 3:
        raise StepError(f"仓库数异常：{len(warehouses)}")
    return dict(path=str(path), sha256=_sha(path), snapshot_date=snapshot_date,
                rows=int(len(part)), skus=int(part["sku"].nunique()),
                warehouses=warehouses, warehouse_count=len(warehouses),
                snapshot_at=str(snapshot_at.max()), available_sum=float(available.sum()),
                intransit_sum=float(intransit.sum()),
                file_rows=int(len(frame)), file_dates=[dates[0], dates[-1]])


def freeze_snapshot(source: Path, target: Path, expected_sha: str, force: bool) -> dict:
    """冻结快照副本：已存在且哈希相同 → 复用；不同 → 拒绝（除非 --force）。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = _sha(target)
        if existing == expected_sha:
            return dict(path=str(target), sha256=existing, reused=True)
        if not force:
            raise StepError(f"冻结快照已存在且哈希不同：{target}（新 {expected_sha[:12]} ≠ 旧 "
                            f"{existing[:12]}）；确认要替换请加 --force")
        archive = target.with_name(f"{target.stem}.superseded-{int(time.time())}.parquet")
        target.rename(archive)
        frozen_note = f"replaced; old archived to {archive}"
    else:
        frozen_note = "created"
    shutil.copy2(source, target)
    frozen_sha = _sha(target)
    if frozen_sha != expected_sha:
        raise StepError("冻结副本哈希与源不一致（复制失败？）")
    return dict(path=str(target), sha256=frozen_sha, reused=False, note=frozen_note)


def _run_step(name: str, fn, *, required: bool = True) -> dict:
    """执行一步，记录耗时与 Python 内存峰值；失败不静默。"""
    tracemalloc.start()
    started = time.perf_counter()
    record = dict(name=name, status="running", started_at=_now())
    try:
        detail = fn() or {}
        record.update(status="ok", detail=detail)
    except Exception as exc:                     # noqa: BLE001 - 统一记录后上抛
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        record["seconds"] = round(time.perf_counter() - started, 2)
        current, peak = tracemalloc.get_traced_memory()
        record["py_peak_mb"] = round(peak / 1024 / 1024, 1)
        tracemalloc.stop()
        record["finished_at"] = _now()
    return record


def _call_main(module, argv: list[str]) -> dict:
    """在进程内调用模块 main，返回其退出码；非零视为失败。"""
    code = module.main(argv)
    if code not in (0, None):
        raise StepError(f"{module.__name__} 返回 {code}")
    return dict(exit_code=code)


def _latest(out_root: Path) -> dict:
    pointer = out_root / "latest.json"
    if not pointer.exists():
        return {}
    try:
        return json.loads(pointer.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="同日快照一条命令流水线（快照→需求→净额→决策包→动作）")
    ap.add_argument("--snapshot-date", required=True)
    ap.add_argument("--stock", required=True, help="en_stock.parquet（可含多天）")
    ap.add_argument("--as-of", default=None, help="缺省由 snapshot_at 推（按 --tz 解释）")
    ap.add_argument("--tz", default="+08:00", help="snapshot_at 无时区时的解释时区")
    ap.add_argument("--label", default="r1", help="同日版本号：r1/r2/...")
    ap.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    ap.add_argument("--demand-mode", choices=("reuse", "rebuild"), default="reuse")
    ap.add_argument("--demand", default=None, help="reuse 模式的 demand_netting.parquet")
    ap.add_argument("--store", default="D:/Work/fzh-order-store/en-demand-v1")
    ap.add_argument("--gs-path", default="D:/Work/fzh-order-store/gs_orders.parquet")
    ap.add_argument("--demand-start", default="2022-12-01")
    ap.add_argument("--forecast-root", default=DEFAULT_FORECAST_ROOT)
    ap.add_argument("--forecast-run-id", default=None)
    ap.add_argument("--forecast-manifest-sha256", default=None)
    ap.add_argument("--sku-map", default=DEFAULT_SKU_MAP)
    ap.add_argument("--sku-map-sha256", default=FROZEN_SKU_MAP_SHA256)
    ap.add_argument("--uom-cache", default="D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet")
    ap.add_argument("--po-tongtool", default="D:/Work/fzh-order-store/tongtool_po/purchase_orders_recent.jsonl")
    ap.add_argument("--demand-blocked", default=None)
    ap.add_argument("--protect-days", type=int, default=7)
    ap.add_argument("--weeks", type=int, default=4)
    ap.add_argument("--so-rows", default="D:/Work/fzh-order-store/en_sales_orders/open_nonclosed_rows.jsonl")
    ap.add_argument("--so-closed-rows", default="D:/Work/fzh-order-store/en_sales_orders/closed_undelivered_rows.jsonl")
    ap.add_argument("--w1-cache", default="D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl")
    ap.add_argument("--w1-manifest", default="D:/Work/fzh-order-store/w1_supply_facts_v2/fetch_manifest.json")
    ap.add_argument("--skip-actions", action="store_true", help="只到决策包，不做动作层")
    ap.add_argument("--allow-optional-failure", action="store_true",
                    help="动作层失败时仍保留已成功产物（默认失败即整体失败）")
    ap.add_argument("--test-count", type=int, default=None)
    ap.add_argument("--decision-date", default="2026-10-29",
                    help="决策日；默认沿用历史包口径 2026-10-29（只影响标注与文件名，"
                         "不参与数量计算）")
    ap.add_argument("--force", action="store_true", help="允许替换已存在的冻结快照/同号输出")
    ap.add_argument("--dry-run", action="store_true", help="只做校验与计划，不执行")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    out_root = Path(args.out_root)
    date = args.snapshot_date
    label = args.label
    staging = out_root / f".pipeline-{date}-{label}-{datetime.now().strftime('%H%M%S')}"
    plan = dict(
        schema_version="same-day-pipeline/v1",
        snapshot_date=date, label=label, started_at=_now(),
        staging=str(staging), steps=[], status="running",
        naming=dict(run=f"run-{date}-{label}", decision_pack=f"decision-pack-{date}-{label}",
                    action_inputs=f"pack-{date}-{label}", actions=f"actions-{date}-{label}"),
        inputs=dict(stock=args.stock, demand=args.demand, forecast_root=args.forecast_root,
                    forecast_run_id=args.forecast_run_id, sku_map=args.sku_map,
                    po_tongtool=args.po_tongtool, so_rows=args.so_rows,
                    w1_cache=args.w1_cache),
        options=dict(demand_mode=args.demand_mode, protect_days=args.protect_days,
                     weeks=args.weeks, skip_actions=args.skip_actions),
    )

    # --- 0. 校验（失败即退出，不建目录、不动任何现有产物） ---
    try:
        snapshot = validate_snapshot(Path(args.stock), date)
    except StepError as exc:
        print(f"[auto] 快照校验失败：{exc}")
        return 2
    as_of = args.as_of
    if not as_of:
        naive = datetime.fromisoformat(snapshot["snapshot_at"])
        tz = timezone(timedelta(hours=int(args.tz[1:3])) if args.tz.startswith("+")
                      else -timedelta(hours=int(args.tz[2:4])))
        as_of = (naive if naive.tzinfo else naive.replace(tzinfo=tz)).replace(
            microsecond=0).isoformat()
    plan["snapshot"] = snapshot
    plan["as_of"] = as_of
    print(f"[auto] 快照 {date}：{snapshot['rows']} 行 / {snapshot['warehouse_count']} 仓，as_of={as_of}")

    if args.dry_run:
        plan.update(status="dry_run", finished_at=_now())
        print(json.dumps(plan, ensure_ascii=False, indent=1))
        return 0

    # --- 1. 冻结快照 ---
    staging.mkdir(parents=True, exist_ok=False)
    frozen_target = out_root / "_inputs" / f"en_stock-{date}-backup.parquet"

    def step_freeze():
        info = freeze_snapshot(Path(args.stock), frozen_target, snapshot["sha256"], args.force)
        plan["frozen_snapshot"] = info
        return info

    steps = plan["steps"]
    try:
        steps.append(_run_step("freeze_snapshot", step_freeze))
    except Exception as exc:                     # noqa: BLE001
        return _fail(plan, staging, exc)

    # --- 2. 需求净额 ---
    from self_fulfilled_demand import canonical as demand_module

    def step_demand():
        if args.demand_mode == "rebuild":
            target = staging / f"demand-{date}-{label}"
            _call_main(demand_module, ["--store", args.store, "--gs-path", args.gs_path,
                                       "--start", args.demand_start, "--end", date,
                                       "--out", str(target), "--sku-map", args.sku_map,
                                       "--uom-cache", args.uom_cache, "--no-fetch-uom"])
            table = target / "demand_netting.parquet"
        else:
            if not args.demand:
                raise StepError("reuse 模式必须给 --demand")
            table = Path(args.demand)
        from supply_netting.demand import load_demand_netting
        _, meta = load_demand_netting(table)
        return dict(path=str(table), sha256=_sha(table), rows=meta["rows"],
                    four_key_duplicates=meta["four_key_duplicates"])

    try:
        demand_record = _run_step("demand_netting", step_demand)
        steps.append(demand_record)
    except Exception as exc:                     # noqa: BLE001
        return _fail(plan, staging, exc)
    demand_path = Path(demand_record["detail"]["path"])

    # --- 3. 供应净额 ---
    from supply_netting import __main__ as netting_module

    run_dir = staging / f"run-{date}-{label}"

    def step_netting():
        argv_net = ["--demand", str(demand_path), "--stock", str(frozen_target),
                    "--sku-map", args.sku_map, "--uom-cache", args.uom_cache,
                    "--snapshot-date", date, "--as-of", as_of,
                    "--protect-days", str(args.protect_days), "--weeks", str(args.weeks),
                    "--forecast-root", args.forecast_root, "--out", str(run_dir)]
        if args.po_tongtool:
            argv_net += ["--po-tongtool", args.po_tongtool]
        if args.demand_blocked:
            argv_net += ["--demand-blocked", args.demand_blocked]
        if args.forecast_run_id:
            argv_net += ["--forecast-run-id", args.forecast_run_id]
        if args.forecast_manifest_sha256:
            argv_net += ["--forecast-manifest-sha256", args.forecast_manifest_sha256]
        _call_main(netting_module, argv_net)
        manifest = json.loads((run_dir / "supply_netting_manifest.json").read_text(encoding="utf-8"))
        return dict(path=str(run_dir), run_id=manifest.get("run_id"),
                    partial=manifest.get("partial"),
                    outputs={k: v for k, v in (manifest.get("outputs") or {}).items()
                             if k.endswith("sha256")})

    try:
        steps.append(_run_step("supply_netting", step_netting))
    except Exception as exc:                     # noqa: BLE001
        return _fail(plan, staging, exc)

    # --- 4. 决策包 ---
    from supply_netting import decision_pack as pack_module

    decision_dir = staging / f"decision-pack-{date}-{label}"
    previous = _latest(out_root)

    def step_decision():
        argv_dp = ["--run", str(run_dir), "--demand", str(demand_path),
                   "--sku-map", args.sku_map, "--out", str(decision_dir)]
        if args.test_count:
            argv_dp += ["--test-count", str(args.test_count)]
        argv_dp += ["--decision-date", args.decision_date]
        supersedes = previous.get("decision_pack")
        if supersedes:
            argv_dp += ["--supersedes", supersedes]
        _call_main(pack_module, argv_dp)
        manifest = json.loads((decision_dir / "decision_pack_manifest.json").read_text(encoding="utf-8"))
        return dict(path=str(decision_dir),
                    destinations=(manifest.get("coverage") or {}).get("destinations"),
                    outputs={k: v for k, v in (manifest.get("outputs") or {}).items()
                             if k.endswith("sha256")})

    try:
        steps.append(_run_step("decision_pack", step_decision))
    except Exception as exc:                     # noqa: BLE001
        return _fail(plan, staging, exc)

    # --- 5. 动作层（可选，缺输入即跳过） ---
    actions_dir = staging / f"actions-{date}-{label}"
    pack_dir = staging / f"pack-{date}-{label}"
    if args.skip_actions:
        steps.append(dict(name="actions", status="skipped", reason="--skip-actions",
                          started_at=_now(), finished_at=_now(), seconds=0.0))
    elif not all(Path(p).exists() for p in (args.so_rows, args.w1_cache) if p):
        steps.append(dict(name="actions", status="skipped",
                          reason="缺少 SO/W1 动作层输入", started_at=_now(),
                          finished_at=_now(), seconds=0.0))
    else:
        from supply_netting import pack as action_inputs_module
        from supply_netting import decision_join

        def step_actions():
            argv_pack = ["--run", str(run_dir), "--demand", str(demand_path),
                         "--stock", str(frozen_target), "--out", str(pack_dir),
                         "--sku-map", args.sku_map]
            for flag, value in (("--so-rows", args.so_rows), ("--so-closed-rows", args.so_closed_rows),
                                ("--w1-cache", args.w1_cache), ("--w1-manifest", args.w1_manifest),
                                ("--blocked", args.demand_blocked)):
                if value:
                    argv_pack += [flag, value]
            _call_main(action_inputs_module, argv_pack)
            _call_main(decision_join, ["--wide", str(decision_dir / f"decision_pack_{args.decision_date}.parquet"),
                                       "--pack", str(pack_dir / "conditional_decision_pack.csv"),
                                       "--out", str(actions_dir),
                                       "--decision-date", args.decision_date])
            return dict(path=str(actions_dir),
                        action_inputs=str(pack_dir),
                        outputs={p.name: _sha(p) for p in sorted(actions_dir.iterdir())
                                 if p.is_file()})

        try:
            steps.append(_run_step("actions", step_actions))
        except Exception as exc:                 # noqa: BLE001
            steps.append(dict(name="actions", status="failed", error=f"{type(exc).__name__}: {exc}",
                              started_at=_now(), finished_at=_now(), seconds=0.0))
            if not args.allow_optional_failure:
                return _fail(plan, staging, exc, already_recorded=True)

    # --- 6. 成功：把暂存目录改名成正式名 ---
    try:
        finals = _promote(staging, out_root, date, label, args.force)
    except Exception as exc:                     # noqa: BLE001
        return _fail(plan, staging, exc)
    plan["outputs"] = finals
    plan.update(status="ok", finished_at=_now(),
                total_seconds=round(sum(s.get("seconds") or 0 for s in steps), 1))
    manifest_path = out_root / f"pipeline-manifest-{date}-{label}.json"
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")
    pointer = dict(snapshot_date=date, label=label, status="ok", updated_at=_now(),
                   manifest=str(manifest_path), **finals)
    (out_root / "latest.json").write_text(json.dumps(pointer, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(json.dumps(dict(status="ok", outputs=finals, steps=[s["name"] for s in steps],
                          total_seconds=plan["total_seconds"]), ensure_ascii=False, indent=1))
    return 0


def _promote(staging: Path, out_root: Path, date: str, label: str, force: bool) -> dict:
    finals = {}
    mapping = {
        "run": f"run-{date}-{label}",
        "decision_pack": f"decision-pack-{date}-{label}",
        "action_inputs": f"pack-{date}-{label}",
        "actions": f"actions-{date}-{label}",
    }
    for key, name in mapping.items():
        source = staging / name
        if not source.exists():
            continue
        target = out_root / name
        if target.exists():
            if not force:
                raise StepError(f"目标已存在：{target}；换 --label 或加 --force")
            archive = target.with_name(f"{name}.superseded-{int(time.time())}")
            target.rename(archive)
            finals[f"{key}_superseded"] = str(archive)
        source.rename(target)
        finals[key] = str(target)
    # 需求重建产物也一并提升
    for demand_dir in staging.glob(f"demand-{date}-{label}"):
        target = out_root / demand_dir.name
        if target.exists() and not force:
            raise StepError(f"目标已存在：{target}")
        demand_dir.rename(target)
        finals["demand"] = str(target)
    shutil.rmtree(staging, ignore_errors=True)
    return finals


def _fail(plan: dict, staging: Path, exc: Exception, *, already_recorded: bool = False) -> int:
    plan.update(status="failed", finished_at=_now(), error=f"{type(exc).__name__}: {exc}")
    failed_dir = staging.with_name(staging.name.replace(".pipeline-", ".failed-"))
    try:
        if staging.exists():
            staging.rename(failed_dir)
            plan["failed_staging"] = str(failed_dir)
    except OSError:
        plan["failed_staging"] = str(staging)
    print(f"[auto] 流水线失败：{exc}")
    print("[auto] 正式目录与 latest.json 未改动；暂存内容保留在：", plan.get("failed_staging"))
    print(json.dumps(plan, ensure_ascii=False, indent=1, default=str))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
