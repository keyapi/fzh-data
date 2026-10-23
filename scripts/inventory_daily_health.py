#!/usr/bin/env python3
"""Daily health check for the two existing Tongtool inventory pipelines.

Reads artifacts only -- it never calls Tongtool and never writes inventory:

  browser export : web_automation/output/通途合并库存结存清单*.xlsx
                   web_automation/logs/export-stock.log
  API backup     : D:/Work/库存备份/YYYY-MM-DD/*.jsonl + manifest.json
                   D:/Work/库存备份/runs/YYYY-MM-DD/*/run_meta.json

When both sides have a complete snapshot it cross-checks them offline by
(warehouse, SKU) and compares available / in-transit / waiting / defective.

Exit codes: 0 = OK or WARN (alert sent if configured), 1 = FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]

BROWSER_WAREHOUSES = [
    "美东-CENTRADE",
    "波兰-FZHPoland-covers",
    "美中-FZH-DANEEY",
    "美中-FZH-DANEEY-退货产品仓",
]
BROWSER_EXPECTED_EMPTY = [
    "美东-CENTRADE-退货产品仓",
    "波兰-FZHPoland-退货产品仓",
]
WAYFAIR_WAREHOUSES = [
    "WayfairCG-Cranbury仓",
    "WayfairCG-McDonough仓",
    "WayfairCG-Perris仓",
    "WayfairCG-PortWentworth仓",
    "WayfairCG-Romeoville仓",
]
API_REQUIRED = BROWSER_WAREHOUSES + BROWSER_EXPECTED_EMPTY + WAYFAIR_WAREHOUSES

EXCEL_COLUMNS = ["SKU", "仓库", "可用库存", "在途库存", "待发库存", "故障品库存"]
API_QTY_FIELDS = {
    "可用库存": "availableStockQuantity",
    "在途库存": "intransitStockQuantity",
    "待发库存": "waitingShipmentStockQuantity",
    "故障品库存": "defectsStockQuantity",
}
EXCEL_GLOB = "通途合并库存结存清单*.xlsx"
EXCEL_NAME_RE = re.compile(r"(\d{8})_(\d{4})")
BASELINE_DAYS = 7

OK, WARN, FAIL = "OK", "WARN", "FAIL"
_RANK = {OK: 0, WARN: 1, FAIL: 2}

BROWSER_CMD = (
    "uv run python web_automation/scripts/dispatch.py "
    "tongtu.stock.export -- --auto-login"
)
API_CMD = r"D:\Work\fzh-stock-backup\run_stock_daily_backup.cmd"
BROWSER_TASK = "FZH-TongtuAutoExport-stock"
API_TASK = "FZH-TongtuStockApiDaily"


# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------


def resolve_data_root(explicit: str | None) -> Path:
    """The checkout that owns web_automation/output (main repo, not a worktree)."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("FZH_DATA_ROOT")
    if env:
        return Path(env)
    if (REPO_ROOT / "web_automation" / "output").is_dir():
        return REPO_ROOT
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if out:
            main = Path(out).parent
            if (main / "web_automation" / "output").is_dir():
                return main
    except OSError:
        pass
    return REPO_ROOT


def resolve_api_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("FZH_INVENTORY_ROOT") or r"D:/Work/库存备份")


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------


def worst(statuses: list[str]) -> str:
    return max(statuses, key=lambda s: _RANK.get(s, 0), default=OK)


def finish_status(reasons: list[str], warnings: list[str]) -> str:
    if reasons:
        return FAIL
    if warnings:
        return WARN
    return OK


def parse_snapshot_date(path: Path) -> Date | None:
    match = EXCEL_NAME_RE.search(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_tail(path: Path, lines: int = 8) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [line.rstrip() for line in text.splitlines() if line.strip()][-lines:]


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        return str(pid) in (result.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def api_lock_alive(api_root: Path) -> bool:
    lock = api_root / ".lock"
    try:
        pid = int(lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return pid_alive(pid)


def scheduled_task_result(name: str) -> int | None:
    """LastTaskResult from Windows Task Scheduler (None elsewhere/unavailable)."""
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-ScheduledTaskInfo -TaskName '{name}').LastTaskResult",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        value = (result.stdout or "").strip()
        return int(value) if value else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------------------
# browser (Excel) pipeline
# ---------------------------------------------------------------------------


def excel_files_by_date(output_dir: Path) -> dict[Date, Path]:
    found: dict[Date, Path] = {}
    try:
        paths = sorted(output_dir.glob(EXCEL_GLOB), key=lambda p: p.stat().st_mtime)
    except OSError:
        return found
    for path in paths:
        day = parse_snapshot_date(path)
        if day is not None:
            found[day] = path
    return found


def read_excel_full(path: Path) -> tuple[pd.DataFrame, list[str]]:
    frame = pd.read_excel(path)
    missing = [col for col in EXCEL_COLUMNS if col not in frame.columns]
    if missing:
        return frame, missing
    frame = frame.copy()
    frame["仓库"] = frame["仓库"].astype(str).str.strip()
    frame["SKU"] = frame["SKU"].astype(str).str.strip()
    for col in EXCEL_COLUMNS[2:]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
    frame = frame[(frame["SKU"] != "") & (frame["SKU"] != "nan")]
    return frame, []


def read_excel_counts(path: Path) -> dict[str, int]:
    frame = pd.read_excel(path, usecols=["仓库"])
    counts = frame["仓库"].astype(str).str.strip().value_counts()
    return {str(k): int(v) for k, v in counts.items()}


def count_deviation(today: int, baseline: float | None) -> tuple[str | None, float | None]:
    if baseline is None or baseline <= 0:
        return None, None
    deviation = (today - baseline) / baseline
    if today <= 0:
        return FAIL, deviation
    if abs(deviation) > 0.5:
        return FAIL, deviation
    if abs(deviation) > 0.2:
        return WARN, deviation
    return None, deviation


def parse_export_log(path: Path) -> tuple[str | None, list[str]]:
    tail = read_tail(path, lines=2000)
    status = None
    for line in tail:
        match = re.match(r"^status=(\S+)\s*$", line.strip())
        if match:
            status = match.group(1)
    return status, tail[-8:]


def browser_check(target: Date, data_root: Path) -> dict[str, Any]:
    output_dir = data_root / "web_automation" / "output"
    log_path = data_root / "web_automation" / "logs" / "export-stock.log"
    reasons: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {
        "status": OK,
        "file": None,
        "rows": None,
        "warehouses": {},
        "log_status": None,
        "reasons": reasons,
        "warnings": warnings,
        "baseline": {},
    }

    by_date = excel_files_by_date(output_dir)
    path = by_date.get(target)
    if path is None:
        reasons.append(f"无 {target.isoformat()} 合并清单")
    else:
        result["file"] = str(path)
        try:
            frame, missing = read_excel_full(path)
        except Exception as exc:  # noqa: BLE001 - report, do not crash the check
            reasons.append(f"合并清单读取失败：{type(exc).__name__}: {exc}")
            frame = None
            missing = []
        if frame is not None and missing:
            reasons.append("缺少必需列：" + "、".join(missing))
        elif frame is not None:
            counts = {str(k): int(v) for k, v in frame["仓库"].value_counts().items()}
            result["rows"] = int(len(frame))
            result["warehouses"] = counts
            for warehouse in BROWSER_WAREHOUSES:
                if counts.get(warehouse, 0) <= 0:
                    reasons.append(f"{warehouse}：当日无数据")
            for warehouse in BROWSER_EXPECTED_EMPTY:
                if warehouse not in counts:
                    continue
                subset = frame[frame["仓库"] == warehouse]
                total = float(subset[EXCEL_COLUMNS[2:]].sum().sum())
                if total > 0:
                    warnings.append(f"{warehouse}：长期空仓出现库存 {total:g}")

            history: list[dict[str, int]] = []
            for offset in range(1, BASELINE_DAYS + 1):
                previous = by_date.get(target - timedelta(days=offset))
                if previous is None:
                    continue
                try:
                    history.append(read_excel_counts(previous))
                except Exception:  # noqa: BLE001 - baseline is best effort
                    continue
            for warehouse in BROWSER_WAREHOUSES:
                values = [item.get(warehouse, 0) for item in history]
                baseline = median(values) if len(values) >= 3 else None
                status, deviation = count_deviation(counts.get(warehouse, 0), baseline)
                result["baseline"][warehouse] = {
                    "median": baseline,
                    "deviation": round(deviation, 4) if deviation is not None else None,
                }
                if status == FAIL:
                    reasons.append(
                        f"{warehouse}：行数 {counts.get(warehouse, 0)} 偏离 7 日中位数 "
                        f"{baseline:g} 超过 50%"
                    )
                elif status == WARN:
                    warnings.append(
                        f"{warehouse}：行数 {counts.get(warehouse, 0)} 偏离 7 日中位数 "
                        f"{baseline:g} 超过 20%"
                    )

    if target == Date.today():
        log_status, tail = parse_export_log(log_path)
        result["log_status"] = log_status
        result["log_tail"] = tail
        if log_status is None:
            warnings.append("export-stock.log 未找到 status 行")
        elif log_status != "READY":
            reasons.append(f"export-stock.log 末尾 status={log_status}")
        task_rc = scheduled_task_result(BROWSER_TASK)
        result["task_last_result"] = task_rc
        if task_rc not in (None, 0):
            reasons.append(f"定时任务上次结果 {task_rc}")

    result["status"] = finish_status(reasons, warnings)
    return result


# ---------------------------------------------------------------------------
# API pipeline
# ---------------------------------------------------------------------------


def api_manifest_rows(manifest: dict[str, Any]) -> dict[str, int]:
    return {
        str(item.get("warehouseName")): int(item.get("rows") or 0)
        for item in manifest.get("warehouses", [])
        if item.get("warehouseName")
    }


def api_check(target: Date, api_root: Path) -> dict[str, Any]:
    day = target.isoformat()
    day_dir = api_root / day
    manifest_path = day_dir / "manifest.json"
    reasons: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {
        "status": OK,
        "manifest": None,
        "run_id": None,
        "complete": None,
        "warehouses": {},
        "reasons": reasons,
        "warnings": warnings,
        "baseline": {},
    }

    lock_alive = api_lock_alive(api_root)
    result["lock_alive"] = lock_alive

    failure_marker = read_json(api_root / ".last_failure.json")
    if failure_marker and str(failure_marker.get("date", "")) == day:
        result["failure_marker"] = failure_marker

    if not manifest_path.exists():
        if lock_alive:
            warnings.append("API 备份仍在运行（.lock 对应进程存活）")
        else:
            reasons.append(f"无 {day}/manifest.json")
            if target == Date.today():
                task_rc = scheduled_task_result(API_TASK)
                result["task_last_result"] = task_rc
                if task_rc not in (None, 0):
                    reasons.append(f"定时任务上次结果 {task_rc}")
        if result.get("failure_marker"):
            marker = result["failure_marker"]
            reasons.append(
                f"上次失败标记：阶段 {marker.get('stage', '?')}，退出码 {marker.get('exit_code', '?')}"
            )
        result["status"] = finish_status(reasons, warnings)
        return result

    manifest = read_json(manifest_path)
    if manifest is None:
        reasons.append("manifest.json 无法解析")
        result["status"] = FAIL
        return result

    result["manifest"] = str(manifest_path)
    result["run_id"] = manifest.get("run_id")
    result["script_version"] = manifest.get("script_version")
    result["complete"] = bool(manifest.get("complete"))
    rows = api_manifest_rows(manifest)
    result["warehouses"] = rows

    if not result["complete"]:
        reasons.append("manifest.complete=false")
    missing = manifest.get("missing_warehouses") or []
    if missing:
        reasons.append("缺失请求仓：" + "、".join(map(str, missing)))

    for item in manifest.get("warehouses", []):
        name = str(item.get("warehouseName") or "?")
        if item.get("error"):
            if name in WAYFAIR_WAREHOUSES:
                warnings.append(f"{name}：{item['error']}")
            else:
                reasons.append(f"{name}：{item['error']}")
        elif item.get("complete") is False:
            warnings.append(f"{name}：分页未完成")

    for warehouse in API_REQUIRED:
        if warehouse not in rows:
            if warehouse in WAYFAIR_WAREHOUSES:
                warnings.append(f"{warehouse}：API 未返回该仓")
            else:
                reasons.append(f"{warehouse}：API 未返回该仓")
    for warehouse in BROWSER_EXPECTED_EMPTY:
        if rows.get(warehouse, 0) > 0:
            warnings.append(f"{warehouse}：长期空仓出现库存（{rows[warehouse]} 行）")

    # run archive (runs/<date>/<run_id>/, sealed)
    run_dirs = sorted((api_root / "runs" / day).glob("*/")) if (api_root / "runs" / day).is_dir() else []
    if run_dirs:
        latest = run_dirs[-1]
        meta = read_json(latest / "run_meta.json")
        result["run_meta"] = {
            "dir": str(latest),
            "exit_code": meta.get("exit_code") if meta else None,
            "source": meta.get("source") if meta else None,
            "sealed": (latest / ".sealed").exists(),
        }
        if meta and meta.get("exit_code") not in (0, None):
            warnings.append(f"归档记录 exit_code={meta.get('exit_code')}")
        if not (latest / ".sealed").exists():
            warnings.append("当日批次未封存（缺少 .sealed）")
        if target == Date.today() and meta and meta.get("source") not in (None, "scheduled"):
            warnings.append(f"当日数据来源={meta.get('source')}（非定时任务）")
    else:
        warnings.append("当日批次未归档（runs/ 下无目录）")

    # row-count baseline from previous manifests
    history: list[dict[str, int]] = []
    for offset in range(1, BASELINE_DAYS + 1):
        previous = read_json(api_root / (target - timedelta(days=offset)).isoformat() / "manifest.json")
        if previous:
            history.append(api_manifest_rows(previous))
    for warehouse in BROWSER_WAREHOUSES + WAYFAIR_WAREHOUSES:
        if warehouse in BROWSER_EXPECTED_EMPTY:
            continue
        values = [item.get(warehouse, 0) for item in history]
        baseline = median(values) if len(values) >= 3 else None
        status, deviation = count_deviation(rows.get(warehouse, 0), baseline)
        result["baseline"][warehouse] = {
            "median": baseline,
            "deviation": round(deviation, 4) if deviation is not None else None,
        }
        if status == FAIL:
            reasons.append(
                f"{warehouse}：行数 {rows.get(warehouse, 0)} 偏离 7 日中位数 "
                f"{baseline:g} 超过 50%"
            )
        elif status == WARN:
            warnings.append(
                f"{warehouse}：行数 {rows.get(warehouse, 0)} 偏离 7 日中位数 "
                f"{baseline:g} 超过 20%"
            )

    if target == Date.today():
        tail = read_tail(api_root / "stock_daily_backup.log")
        result["log_tail"] = tail
        if any("[archive] FAILED" in line or "✗" in line for line in tail):
            warnings.append("stock_daily_backup.log 末尾含失败记录")

    result["status"] = finish_status(reasons, warnings)
    return result


# ---------------------------------------------------------------------------
# offline parity
# ---------------------------------------------------------------------------


def _api_frame_from_manifest(manifest: dict[str, Any], day_dir: Path) -> tuple[pd.DataFrame | None, int]:
    rows: list[dict[str, Any]] = []
    duplicated = 0
    for item in manifest.get("warehouses", []):
        name = str(item.get("warehouseName") or "")
        if name not in BROWSER_WAREHOUSES:
            continue
        file_value = item.get("file")
        path = Path(str(file_value)) if file_value else None
        if path is None or not path.exists():
            candidates = list(day_dir.glob(f"warehouse=*_{name}.jsonl"))
            path = candidates[0] if candidates else None
        if path is None or not path.exists():
            continue
        seen: set[str] = set()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            sku = str(obj.get("goodsSku") or "").strip()
            if not sku:
                continue
            if sku in seen:
                duplicated += 1
            seen.add(sku)
            rows.append(
                {
                    "仓库": name,
                    "SKU": sku,
                    "可用库存_api": obj.get("availableStockQuantity"),
                    "在途库存_api": obj.get("intransitStockQuantity"),
                    "待发库存_api": obj.get("waitingShipmentStockQuantity"),
                    "故障品库存_api": obj.get("defectsStockQuantity"),
                }
            )
    if not rows:
        return None, duplicated
    frame = pd.DataFrame(rows)
    for col in frame.columns[2:]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
    frame = frame.drop_duplicates(subset=["仓库", "SKU"], keep="last")
    return frame, duplicated


def parity_check(
    target: Date,
    browser: dict[str, Any],
    api: dict[str, Any],
    api_root: Path,
) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {
        "status": "SKIPPED",
        "overlap": 0,
        "excel_only": 0,
        "api_only": 0,
        "api_only_nonzero": 0,
        "diff_rows": 0,
        "diff_fields": {},
        "reasons": reasons,
        "warnings": warnings,
    }

    if not browser.get("file"):
        reasons.append("Excel 无当日文件，无法互证")
        result["status"] = "SKIPPED"
        return result
    if not api.get("manifest"):
        reasons.append("API 无当日 manifest，无法互证")
        result["status"] = "SKIPPED"
        return result

    try:
        excel_frame, missing = read_excel_full(Path(str(browser["file"])))
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"Excel 读取失败：{type(exc).__name__}: {exc}")
        result["status"] = "SKIPPED"
        return result
    if missing:
        reasons.append("Excel 缺少必需列，无法互证")
        result["status"] = "SKIPPED"
        return result

    manifest = read_json(Path(str(api["manifest"])))
    if manifest is None:
        reasons.append("manifest 无法解析，无法互证")
        result["status"] = "SKIPPED"
        return result

    api_frame, duplicated = _api_frame_from_manifest(manifest, api_root / target.isoformat())
    if api_frame is None:
        reasons.append("API JSONL 无可用行，无法互证")
        result["status"] = "SKIPPED"
        return result

    excel_dupes = int(excel_frame.duplicated(subset=["仓库", "SKU"]).sum())
    if excel_dupes or duplicated:
        warnings.append(f"重复行：Excel {excel_dupes}、API {duplicated}（已按最后一条去重）")
    excel_frame = excel_frame.drop_duplicates(subset=["仓库", "SKU"], keep="last")

    merged = excel_frame.merge(api_frame, on=["仓库", "SKU"], how="inner", suffixes=("", ""))
    overlap = int(len(merged))
    result["overlap"] = overlap
    if overlap == 0:
        reasons.append("两线无重叠 SKU")
        result["status"] = FAIL
        return result

    result["excel_only"] = int(len(excel_frame) - overlap)
    api_only_frame = api_frame.merge(
        excel_frame[["仓库", "SKU"]].drop_duplicates().assign(_in_excel=True),
        on=["仓库", "SKU"],
        how="left",
    )
    api_only_frame = api_only_frame[api_only_frame["_in_excel"].isna()]
    result["api_only"] = int(len(api_only_frame))
    api_only_available = 0.0
    if len(api_only_frame):
        api_qty_columns = [f"{col}_api" for col in API_QTY_FIELDS]
        result["api_only_nonzero"] = int(
            (api_only_frame[api_qty_columns].sum(axis=1) > 0).sum()
        )
        api_only_available = float(api_only_frame[api_qty_columns[0]].sum())
    result["api_only_available"] = api_only_available

    any_diff = pd.Series(False, index=merged.index)
    for excel_col, api_field in API_QTY_FIELDS.items():
        api_col = f"{excel_col}_api"
        column_diff = (merged[excel_col].round(6) != merged[api_col].round(6))
        result["diff_fields"][excel_col] = int(column_diff.sum())
        any_diff = any_diff | column_diff
    result["diff_rows"] = int(any_diff.sum())

    sum_excel = float(merged["可用库存"].sum())
    sum_api = float(merged["可用库存_api"].sum())
    result["available_sum_excel"] = sum_excel
    result["available_sum_api"] = sum_api
    result["available_diff_ratio"] = (
        abs(sum_api - sum_excel) / sum_excel if sum_excel else 0.0
    )

    diff_ratio = result["diff_rows"] / overlap
    if diff_ratio > 0.05:
        reasons.append(f"数量差异覆盖 {diff_ratio:.1%} 的重叠 SKU（>5%）")
    elif diff_ratio > 0.005:
        warnings.append(f"数量差异覆盖 {diff_ratio:.1%} 的重叠 SKU（>0.5%）")
    if result["available_diff_ratio"] > 0.10:
        reasons.append(
            f"可用库存合计差异 {result['available_diff_ratio']:.1%}（>10%）"
        )
    elif result["available_diff_ratio"] > 0.01:
        warnings.append(
            f"可用库存合计差异 {result['available_diff_ratio']:.1%}（>1%）"
        )
    if result["excel_only"] > 0:
        warnings.append(f"Excel 独有 {result['excel_only']} 个 SKU（API 未返回）")
    # The browser export applies a status/FBA filter, so a small number of
    # API-only SKUs with stock is expected (43 real SKUs + TEST-1 on 2026-10-22).
    api_only_ratio = result["api_only_nonzero"] / overlap
    if api_only_ratio > 0.05:
        reasons.append(f"API 独有有库存 SKU 占重叠 {api_only_ratio:.1%}（>5%）")
    elif api_only_ratio > 0.01:
        warnings.append(f"API 独有有库存 SKU 占重叠 {api_only_ratio:.1%}（>1%）")
    if sum_excel and api_only_available / sum_excel > 0.01:
        warnings.append(
            f"API 独有 SKU 的可用库存占总可用 {api_only_available / sum_excel:.1%}（>1%）"
        )

    result["status"] = finish_status(reasons, warnings)
    return result


# ---------------------------------------------------------------------------
# alerting / output
# ---------------------------------------------------------------------------


def load_env_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def send_alert(text: str, title: str, data_root: Path, api_root: Path, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "title": title, "text": text}
    load_env_files([data_root / ".env", api_root / ".env", REPO_ROOT / ".env"])
    if not os.getenv("DINGTALK_WEBHOOK") and os.getenv("DINGTALK_WEBHOOK_STOCK"):
        os.environ["DINGTALK_WEBHOOK"] = os.environ["DINGTALK_WEBHOOK_STOCK"]
        os.environ["DINGTALK_SECRET"] = os.environ.get("DINGTALK_SECRET_STOCK", "")
    if not os.getenv("DINGTALK_WEBHOOK") or not os.getenv("DINGTALK_SECRET"):
        message = "未配置 DINGTALK_WEBHOOK / DINGTALK_SECRET，跳过推送"
        print(f"[警告] {message}", file=sys.stderr)
        return {"skipped": True, "reason": message}
    robot_dir = data_root / "dingtalk" / "dingtalk_robot"
    if str(robot_dir) not in sys.path:
        sys.path.insert(0, str(robot_dir))
    try:
        from send_dingtalk import send_markdown

        return send_markdown(text, title)
    except Exception as exc:  # noqa: BLE001 - alert failure must not hide the report
        print(f"[警告] 钉钉推送失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return {"error": f"{type(exc).__name__}: {exc}"}


def build_alert(target: Date, payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        f"## 通途库存体检 · {target.isoformat()}",
        f"**结果：{'失败' if overall == FAIL else '警告'}**",
        "",
    ]
    sections = (("Excel", payload["browser"]), ("API", payload["api"]), ("互证", payload["parity"]))
    for label, section in sections:
        if section["status"] == OK:
            continue
        for reason in section.get("reasons", []):
            lines.append(f"- {label}：{reason}")
        for warning in section.get("warnings", []):
            lines.append(f"- {label}：{warning}")
    lines += ["", "补救：", f"  浏览器：{BROWSER_CMD}", f"  API：{API_CMD}"]
    return "\n".join(lines)


def summarize(payload: dict[str, Any]) -> str:
    browser = payload["browser"]
    api = payload["api"]
    parity = payload["parity"]
    return (
        f"{payload['date']} overall={payload['overall']} "
        f"excel={browser['status']}({browser.get('rows')}) "
        f"api={api['status']}({api.get('complete')}) "
        f"parity={parity['status']}(overlap={parity.get('overlap', 0)}, "
        f"diff={parity.get('diff_rows', 0)})"
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="通途库存两条流水线的每日体检（只读）")
    parser.add_argument("--date", help="YYYY-MM-DD，默认今天")
    parser.add_argument("--data-root", help="含 web_automation/ 的主检出目录")
    parser.add_argument("--api-root", help="API 备份根目录，默认 D:/Work/库存备份")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写文件、不推送")
    parser.add_argument("--no-alert", action="store_true", help="写状态文件但不推钉钉")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    parser.add_argument("--test-alert", action="store_true", help="发送一条测试告警后退出")
    args = parser.parse_args(argv)

    target = Date.fromisoformat(args.date) if args.date else Date.today()
    data_root = resolve_data_root(args.data_root)
    api_root = resolve_api_root(args.api_root)

    if args.test_alert:
        text = (
            f"## 通途库存体检 · 测试\n\n"
            f"> 这是一条测试消息，来自 `scripts/inventory_daily_health.py`。\n"
            f"> 数据目录：{data_root}\n> API 目录：{api_root}"
        )
        print(json.dumps(send_alert(text, "通途库存体检测试", data_root, api_root, args.dry_run), ensure_ascii=False))
        return 0

    browser = browser_check(target, data_root)
    api = api_check(target, api_root)
    parity = parity_check(target, browser, api, api_root)

    overall = worst([browser["status"], api["status"], parity["status"] if parity["status"] != "SKIPPED" else OK])
    if browser["status"] == OK and api["status"] == OK and parity["status"] == "SKIPPED":
        overall = WARN

    payload: dict[str, Any] = {
        "date": target.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_root": str(data_root),
        "api_root": str(api_root),
        "browser": browser,
        "api": api,
        "parity": parity,
        "overall": overall,
        "alerted": False,
    }

    if args.dry_run:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(text if args.json else summarize(payload))
        return 0

    health_dir = api_root / "health"
    status_path = health_dir / f"{target.isoformat()}.json"
    write_atomic(status_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    alerted = False
    if overall in (WARN, FAIL) and not args.no_alert:
        alert = send_alert(build_alert(target, payload), f"通途库存体检 · {target.isoformat()}", data_root, api_root, False)
        alerted = not alert.get("skipped") and not alert.get("error")
    payload["alerted"] = alerted
    write_atomic(status_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    try:
        with (health_dir / "health.log").open("a", encoding="utf-8") as handle:
            handle.write(
                f"{datetime.now().isoformat(timespec='seconds')} {summarize(payload)} "
                f"alerted={alerted}\n"
            )
    except OSError as exc:
        print(f"[警告] 写 health.log 失败：{exc}", file=sys.stderr)

    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else summarize(payload))
    return 1 if overall == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
