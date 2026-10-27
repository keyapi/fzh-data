#!/usr/bin/env python3
"""Batch machine entry for the supply facts contract (P2).

Calls `key_test.supply_facts.get_supply_facts` on the EN test/prod site and
writes a versioned, reproducible snapshot: JSON datasets + Excel + manifest
with file checksums. Row-level data stays local; nothing is pushed.

Examples:
  uv run python EN_API/supply_facts_export.py --codes "TT0031038K0062927,CENCord995-DKGrey-97" --test
  uv run python EN_API/supply_facts_export.py --so SO-26-00026 --test
  uv run python EN_API/supply_facts_export.py --all --test --page-size 500
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

EN_API = Path(__file__).resolve().parent
sys.path.insert(0, str(EN_API))
sys.stdout.reconfigure(encoding="utf-8")

import item_shipment_status as iss  # noqa: E402

METHOD = "/api/method/key_test.supply_facts.get_supply_facts"
DATASETS = ("lines", "stage_balances", "milestones", "availability_schedule", "links")
DEFAULT_OUT = EN_API / "out" / "supply_facts"
SCHEMA_VERSION = "supply-facts/v1"


def _call(base_url, key, secret, filters):
    import urllib.parse
    path = METHOD + "?" + urllib.parse.urlencode(
        {"filters": json.dumps(filters, ensure_ascii=False)})
    status, body = iss.api_get_status(path, base_url, key, secret, timeout=300)
    if status != 200:
        raise iss.QueryError("get_supply_facts HTTP %s %s" % (status, str(body)[:200]))
    message = body.get("message")
    if not isinstance(message, dict):
        raise iss.QueryError("get_supply_facts returned %s" % type(message).__name__)
    return message


def _merge(target, batch):
    for key in DATASETS:
        target[key].extend(batch.get(key) or [])
    manifest = batch.get("manifest") or {}
    target["partial"] = target["partial"] or bool(manifest.get("partial"))
    for key, value in (manifest.get("counts") or {}).items():
        target["counts"][key] = target["counts"].get(key, 0) + int(value or 0)
    for key, value in (manifest.get("coverage") or {}).items():
        if key == "sources":
            for name, ok in (value or {}).items():
                target["sources"][name] = bool(target["sources"].get(name, True)) and bool(ok)
        elif key == "restricted":
            for name, flag in (value or {}).items():
                target["restricted"][name] = bool(target["restricted"].get(name)) or bool(flag)
        elif key == "external_sources":
            for name, state in (value or {}).items():
                old = target["external_sources"].get(name)
                if old == "not_integrated":
                    continue
                if state != "integrated":
                    target["external_sources"][name] = state or "not_integrated"
                else:
                    target["external_sources"][name] = "integrated"
        elif key == "source_timestamps":
            for name, stamp in (value or {}).items():
                old = target["source_timestamps"].get(name)
                if old is None or (stamp and stamp < old):
                    target["source_timestamps"][name] = stamp
        elif isinstance(value, int):
            target["coverage"][key] = target["coverage"].get(key, 0) + value
        elif key == "empty_reason" and value:
            target["coverage"]["empty_reason"] = value
    for note in manifest.get("notes") or []:
        if note not in target["notes"]:
            target["notes"].append(note)
    if not target["rule_version"] and manifest.get("rule_version"):
        target["rule_version"] = manifest["rule_version"]
    if not target["implementation_version"] and manifest.get("implementation_version"):
        target["implementation_version"] = manifest["implementation_version"]
    if not target["as_of"] and manifest.get("as_of"):
        target["as_of"] = manifest["as_of"]


def _resolve_sos(codes, base_url, key, secret):
    names = []
    for code in codes:
        found = [r["name"] for r in iss.find_sales_orders_by_items([code], base_url, key, secret)]
        if not found:
            found = [r["name"] for r in iss.find_sales_orders_by_customer_code(
                code, base_url, key, secret)]
        if not found:
            print("  ! 未命中销售订单: %s" % code, file=sys.stderr)
        names.extend(found)
    return sorted(set(names))


def _write_xlsx(path, result):
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    columns = {
        "lines": list(result["lines"][0].keys()) if result["lines"] else [],
        "stage_balances": ["so", "so_line_id", "item_code", "warehouse", "uom", "stage",
                           "stage_detail", "qty", "qty_status", "qty_basis", "batch_key",
                           "source_record", "exclusion_reason", "included_in_stock",
                           "demand_status", "scope", "role"],
        "milestones": ["so", "so_line_id", "item_code", "uom", "node", "baseline_planned_at",
                       "committed_due_at", "latest_expected_at", "actual_at", "qty",
                       "qty_status", "date_precision", "timezone_status", "observed_at",
                       "source_record", "note", "rule_version"],
        "availability_schedule": ["tranche_id", "so", "so_line_id", "item_code", "warehouse",
                                  "uom", "qty", "qty_status", "qty_basis", "stage",
                                  "available_date", "latest_expected_at", "date_kind",
                                  "date_confidence", "scenario", "eligible",
                                  "exclusion_reason", "batch_key", "source_record",
                                  "demand_status", "rule_version"],
        "links": ["so", "so_line_id", "source_doctype", "source_name", "source_line_id",
                  "relation", "target_doctype", "target_name", "qty", "uom", "proof",
                  "allocation"],
    }
    for name in DATASETS:
        ws = wb.create_sheet(name)
        headers = columns[name]
        ws.append(headers)
        for row in result[name]:
            ws.append([row.get(key) for key in headers])
        ws.freeze_panes = "A2"
    covered = wb.create_sheet("Coverage")
    covered.append(["key", "value"])
    for key, value in (result["manifest"].get("coverage") or {}).items():
        covered.append([key, json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list)) else value])
    man = wb.create_sheet("Manifest")
    man.append(["key", "value"])
    for key, value in result["manifest"].items():
        if key == "scope":
            value = json.dumps(value, ensure_ascii=False, default=str)
        elif isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        man.append([key, value])
    wb.save(path)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="supply_facts_export",
                                     description="供应事实批量导出（结构化 JSON/Excel + manifest）")
    parser.add_argument("--codes", help="客户码或 EN 物料码，逗号分隔")
    parser.add_argument("--so", help="销售订单号，逗号分隔")
    parser.add_argument("--all", action="store_true", help="全部未发完 SO 行（分页）")
    parser.add_argument("--test", action="store_true", help="使用测试系统")
    parser.add_argument("--env-file", help=".env 路径")
    parser.add_argument("--as-of", help="as_of 日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--include-delivered", action="store_true", help="含已发完 SO 行")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--no-excel", action="store_true")
    args = parser.parse_args(argv)

    if not (args.codes or args.so or args.all):
        parser.error("至少给一个输入: --codes / --so / --all")
    env = "test" if args.test else "prod"
    key, secret = iss.load_credentials(env, iss.resolve_env_files(args.env_file))
    if not key or not secret or "your_" in key:
        print("✗ API 凭证未配置。请检查 EN_API/.env", file=sys.stderr)
        return 1
    base_url = iss.ENV_URLS[env]
    started = time.perf_counter()

    result = {"lines": [], "stage_balances": [], "milestones": [],
              "availability_schedule": [], "links": [], "partial": False,
              "counts": {}, "coverage": {}, "sources": {}, "source_timestamps": {},
              "restricted": {}, "external_sources": {},
              "notes": [], "rule_version": "", "implementation_version": "",
              "as_of": args.as_of or ""}
    today_str = time.strftime("%Y-%m-%d")
    if args.as_of and args.as_of != today_str:
        print("✗ 历史 as_of 未实现：只能导出当前快照，拒绝 --as-of %s" % args.as_of,
              file=sys.stderr)
        return 2
    base_filters = {"as_of": today_str}
    terminated_by = "exhausted"
    try:
        if args.codes:
            codes = [c.strip() for c in args.codes.replace(";", ",").split(",") if c.strip()]
            t0 = time.perf_counter()
            sos = _resolve_sos(codes, base_url, key, secret)
            print("解析 %d 个码 → %d 张 SO（%.2fs）" % (len(codes), len(sos), time.perf_counter() - t0))
            if not sos:
                raise iss.QueryError("没有命中的销售订单")
            for so in sos:
                filters = dict(base_filters, sales_order=so, include_delivered=1)
                _merge(result, _call(base_url, key, secret, filters))
        elif args.so:
            for so in [s.strip() for s in args.so.split(",") if s.strip()]:
                _merge(result, _call(base_url, key, secret,
                                     dict(base_filters, sales_order=so, include_delivered=1)))
        else:
            offset, page = 0, 0
            while page < 200:
                filters = dict(base_filters, limit=args.page_size, offset=offset)
                if args.include_delivered:
                    filters["include_delivered"] = 1
                batch = _call(base_url, key, secret, filters)
                rows = len(batch.get("lines") or [])
                _merge(result, batch)
                print("  第 %d 页: %d 行（累计 %d）" % (page + 1, rows, len(result["lines"])))
                if rows < args.page_size:
                    terminated_by = "exhausted"
                    break
                offset += rows
                page += 1
            if page >= 200:
                terminated_by = "page_limit"
                print("  ! 达到 200 页上限，结果可能截断（manifest.truncated=true）",
                      file=sys.stderr)
    except iss.QueryError as exc:
        print("✗ 导出失败，未写入新版本: %s" % exc, file=sys.stderr)
        return 1

    query_seconds = time.perf_counter() - started
    run_id = hashlib.sha1(("%s|%s|%s|%s|%s|%s" % (
        result["as_of"], args.codes, args.so, args.all, len(result["lines"]),
        time.time_ns())).encode()).hexdigest()[:12]
    out = Path(args.out)
    run_dir = out / "runs" / ("run-%s-%s" % (time.strftime("%Y%m%d_%H%M%S"), run_id))
    tmp_dir = run_dir.with_suffix(".tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    files = {}
    try:
        for name in DATASETS:
            path = tmp_dir / ("%s.json" % name)
            _write_json(path, result[name])
            files["%s.json" % name] = {"path": "%s.json" % name, "sha256": _sha256(path),
                                       "rows": len(result[name])}
        generated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "rule_version": result["rule_version"],
            "implementation_version": result["implementation_version"],
            "run_id": run_id,
            "as_of": result["as_of"],
            "as_of_kind": "current_snapshot",
            "observed_at": generated_at,
            "generated_at": generated_at,
            "scope": {"codes": args.codes, "so": args.so, "all": args.all,
                      "include_delivered": bool(args.include_delivered)},
            "coverage": dict(result["coverage"],
                             restricted=result["restricted"],
                             external_sources=result["external_sources"]),
            "sources": result["sources"],
            "source_timestamps": result["source_timestamps"],
            "restricted": result["restricted"],
            "external_sources": result["external_sources"],
            "counts": result["counts"],
            "partial": result["partial"],
            "notes": result["notes"],
            "truncated": terminated_by == "page_limit",
            "termination_reason": terminated_by,
            "performance": {"query_seconds": round(query_seconds, 3)},
        }
        if not args.no_excel:
            xlsx = tmp_dir / "supply_facts.xlsx"
            result["manifest"] = manifest
            _write_xlsx(xlsx, result)
            files["supply_facts.xlsx"] = {"path": "supply_facts.xlsx",
                                          "sha256": _sha256(xlsx), "rows": None}
        manifest["files"] = files
        _write_json(tmp_dir / "manifest.json", manifest)
        tmp_dir.rename(run_dir)
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("✗ 写文件失败，未切换最新版本: %s" % exc, file=sys.stderr)
        return 1

    pointer = out / "latest.json"
    pointer_tmp = out / ".latest.json.tmp"
    _write_json(pointer_tmp, {
        "run_id": run_id, "run_dir": str(run_dir),
        "manifest": str(run_dir / "manifest.json"),
        "as_of": result["as_of"],
        "rule_version": result["rule_version"],
        "implementation_version": result["implementation_version"],
        "truncated": terminated_by == "page_limit",
        "termination_reason": terminated_by,
        "last_success_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "rows": len(result["lines"]),
        "partial": result["partial"],
        "performance": {"query_seconds": round(query_seconds, 3),
                        "total_seconds": round(time.perf_counter() - started, 3)},
    })
    os.replace(pointer_tmp, pointer)

    print("\n✓ 完成: %s" % run_dir)
    print("  行: %d | 阶段余额: %d | 里程碑: %d | 可售片段: %d | 关联: %d" % (
        len(result["lines"]), len(result["stage_balances"]), len(result["milestones"]),
        len(result["availability_schedule"]), len(result["links"])))
    print("  partial: %s | 查询 %.2fs | 总计 %.2fs" % (
        result["partial"], query_seconds, time.perf_counter() - started))
    print("  最新指针: %s" % pointer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
