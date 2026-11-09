#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PB 弧形海绵带圆柱颈枕：旧通途 SKU -> 新通途 SKU 转换与上线前核对。

PB 料号不变，订单会带 2024 年登记的旧通途 SKU；旧 SKU 在美中仓为 0，
有货的是 2025-07-15 新建的改版 SKU。本工具只读通途、只写本地 CSV 副本，
不创建/修改任何通途单据。

用法：
    uv run python pb_orders/arc_sku_migration.py status
    uv run python pb_orders/arc_sku_migration.py check --csv "...\\checked0stock ....csv"
    uv run python pb_orders/arc_sku_migration.py map-order --csv "..." --out "..._新SKU.csv"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

import pb_tongtu_excel  # noqa: E402

DEFAULT_MAP = _MODULE_DIR / "sku_maps" / "pb_arc_foam_cylinder.json"
DEFAULT_ENV = _MODULE_DIR.parent / "tongtool_api" / ".env"
DEFAULT_WAREHOUSE = "美中-FZH-DANEEY"

COL_VENDOR = "Vendor Style"
COL_RECORD = "Record Type"
COL_PB = "Buyers Catalog or Stock Keeping #"

AUTH_URL = "https://open.tongtool.com/open-platform-service"
API_URL = "https://open.tongtool.com/api-service"


class MigrationError(Exception):
    pass


@dataclass
class RowPlan:
    replace: list[tuple[int, str, str]] = field(default_factory=list)
    already_new: Counter = field(default_factory=Counter)
    blocked: Counter = field(default_factory=Counter)
    unconfirmed: Counter = field(default_factory=Counter)
    conflicts: list[str] = field(default_factory=list)
    other_rows: int = 0
    detail_rows: int = 0

    @property
    def has_blockers(self) -> bool:
        return bool(self.conflicts or self.blocked or self.unconfirmed)


def load_mapping(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise MigrationError(f"读不到映射文件 {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MigrationError(f"映射文件不是合法 JSON {path}: {exc}") from exc


def _entries(mapping: dict) -> dict:
    confirmed = mapping.get("confirmed") or []
    old_to_new = {
        str(e["old_tt"]).upper(): str(e["new_tt"])
        for e in confirmed
        if e.get("old_tt") and e.get("new_tt")
    }
    new_entries = {str(e["new_tt"]).upper(): e for e in confirmed if e.get("new_tt")}
    pb_entries = {str(e["pb_sku"]).strip(): e for e in confirmed if e.get("pb_sku")}
    blocked = {str(e["sku"]).upper(): e for e in (mapping.get("blocked") or []) if e.get("sku")}
    unconfirmed = {
        str(e["sku"]).upper(): e for e in (mapping.get("unconfirmed") or []) if e.get("sku")
    }
    return {
        "old_to_new": old_to_new,
        "new_entries": new_entries,
        "pb_entries": pb_entries,
        "blocked": blocked,
        "unconfirmed": unconfirmed,
    }


def alias_map(mapping: dict) -> dict[str, set[str]]:
    """旧/新 SKU 互为别名：key 与 value 都是大写 SKU。"""
    groups: dict[str, set[str]] = {}
    for entry in mapping.get("confirmed") or []:
        members = {
            str(entry.get("old_tt") or "").upper(),
            str(entry.get("new_tt") or "").upper(),
        } - {""}
        for sku in members:
            groups[sku] = members
    return groups


def canonical_sku(sku: str, mapping: dict) -> str:
    """把旧 SKU 统一成新 SKU；其它 SKU 原样返回。"""
    key = str(sku or "").strip().upper()
    return _entries(mapping)["old_to_new"].get(key, str(sku or "").strip())


def old_to_new_map(mapping: dict) -> dict[str, str]:
    return _entries(mapping)["old_to_new"]


def expand_sku_set(skus, mapping: dict) -> set[str]:
    """把断货清单展开成「旧+新」别名集合（小写，供 stock_precheck 比较）。"""
    groups = alias_map(mapping)
    out: set[str] = set()
    for value in skus or []:
        key = str(value or "").strip().upper()
        if not key:
            continue
        out.add(key.lower())
        out.update(member.lower() for member in groups.get(key, set()))
    return out



def describe_blockers(plan: RowPlan, mapping: dict) -> list[str]:
    """把拦截原因整理成给页面看的中文列表。"""
    sets = _entries(mapping)
    items: list[str] = []
    for sku, count in plan.blocked.items():
        entry = sets["blocked"].get(sku.upper()) or {}
        items.append(f"{sku} × {count} 行：{entry.get('reason') or '未登记'}")
    for sku, count in plan.unconfirmed.items():
        entry = sets["unconfirmed"].get(sku.upper()) or {}
        items.append(f"{sku} × {count} 行：{entry.get('reason') or '未确认'}")
    items.extend(plan.conflicts)
    return items


def _column_index(header: list[str], name: str, required: bool = True) -> int | None:
    try:
        return header.index(name)
    except ValueError:
        if required:
            raise MigrationError(f"订单 CSV 缺少列：{name}")
        return None


def _pad(row: list[str], width: int) -> list[str]:
    if len(row) >= width:
        return row
    return row + [""] * (width - len(row))


def analyze_rows(header: list[str], rows: list[list[str]], mapping: dict) -> RowPlan:
    sets = _entries(mapping)
    vi = _column_index(header, COL_VENDOR)
    ri = _column_index(header, COL_RECORD)
    pi = _column_index(header, COL_PB, required=False)
    plan = RowPlan()

    for row_index, raw in enumerate(rows):
        line_no = row_index + 2
        row = _pad(raw, len(header))
        if row[ri].strip().upper() != "D":
            continue
        plan.detail_rows += 1
        vendor = row[vi].strip()
        key = vendor.upper()

        if key in sets["old_to_new"]:
            plan.replace.append((row_index, vendor, sets["old_to_new"][key]))
        elif key in sets["new_entries"]:
            plan.already_new[vendor] += 1
        elif key in sets["blocked"]:
            plan.blocked[vendor] += 1
        elif key in sets["unconfirmed"]:
            plan.unconfirmed[vendor] += 1
        else:
            plan.other_rows += 1

        if pi is not None:
            pb_sku = row[pi].strip()
            entry = sets["pb_entries"].get(pb_sku)
            if entry:
                allowed = {
                    str(entry["old_tt"]).upper(),
                    str(entry["new_tt"]).upper(),
                }
                if key not in allowed:
                    plan.conflicts.append(
                        f"第 {line_no} 行：PB {pb_sku} 应配 "
                        f"{entry['old_tt']} 或 {entry['new_tt']}，实际是 {vendor}"
                    )
    return plan


def read_order_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    try:
        lines = pb_tongtu_excel.read_order_csv_lines(path)
    except pb_tongtu_excel.CsvSourceError as exc:
        raise MigrationError(str(exc)) from exc
    if not lines:
        raise MigrationError(f"CSV 是空的：{path}")
    reader = list(csv.reader(lines))
    header, rows = reader[0], reader[1:]
    return header, rows


def write_order_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)


def apply_plan(header: list[str], rows: list[list[str]], plan: RowPlan) -> list[list[str]]:
    vi = _column_index(header, COL_VENDOR)
    out = [list(row) for row in rows]
    for row_index, _old, new in plan.replace:
        out[row_index] = _pad(out[row_index], len(header))
        out[row_index][vi] = new
    return out


def print_plan(plan: RowPlan, path: Path) -> None:
    print(f"订单文件 : {path}")
    print(f"明细行   : {plan.detail_rows}")
    print(f"可转换   : {len(plan.replace)} 行")
    for old, new, count in _replacement_summary(plan):
        print(f"  {old} -> {new}: {count} 行")
    if plan.already_new:
        print(f"已是新 SKU: {sum(plan.already_new.values())} 行")
        for sku, count in plan.already_new.items():
            print(f"  {sku}: {count} 行")
    print(f"其它产品行: {plan.other_rows} 行（不处理）")
    if plan.blocked:
        print("\n[拦截] 未进入 PB SKU Worksheet 的 SKU：")
        for sku, count in plan.blocked.items():
            print(f"  {sku}: {count} 行")
    if plan.unconfirmed:
        print("\n[拦截] 未确认/未报价的 SKU：")
        for sku, count in plan.unconfirmed.items():
            print(f"  {sku}: {count} 行")
    if plan.conflicts:
        print("\n[拦截] PB 料号与 Vendor Style 冲突：")
        for item in plan.conflicts:
            print(f"  {item}")


def _replacement_summary(plan: RowPlan) -> list[tuple[str, str, int]]:
    counter: Counter = Counter()
    for _line, old, new in plan.replace:
        counter[(old, new)] += 1
    return [(old, new, count) for (old, new), count in counter.items()]


def resolve_env_path(explicit: str | None) -> Path:
    """按 参数 -> TONGTOOL_ENV_FILE -> 模块同级 -> 向上找主仓库 的顺序定位 .env。"""
    import os

    if explicit:
        return Path(explicit)
    from_env = os.environ.get("TONGTOOL_ENV_FILE", "").strip()
    if from_env:
        return Path(from_env)
    candidate = _MODULE_DIR.parent / "tongtool_api" / ".env"
    if candidate.is_file():
        return candidate
    for parent in _MODULE_DIR.parents:
        candidate = parent / "tongtool_api" / ".env"
        if candidate.is_file():
            return candidate
    return Path(explicit or DEFAULT_ENV)


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise MigrationError(f"读不到通途凭证文件 {path}: {exc}") from exc
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fetch_stock(env_path: Path, warehouse: str, skus: list[str]) -> dict[str, dict]:
    """通途直连 API 只读查询；不打印任何凭证。"""
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给出明确提示
        raise MigrationError("缺少 httpx，请用项目 .venv 运行：uv run python ...") from exc

    env = _read_env(env_path)
    access_key = env.get("TONGTOOL_ERP2_PRIMARY_KEY", "").strip()
    secret = env.get("TONGTOOL_ERP2_PRIMARY_SECRET", "").strip()
    if not access_key or not secret:
        raise MigrationError(f"{env_path} 缺少 TONGTOOL_ERP2_PRIMARY_KEY/SECRET")

    with httpx.Client(
        timeout=60,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "api_version": "3.0",
        },
    ) as client:
        try:
            auth = client.get(
                f"{AUTH_URL}/devApp/appToken",
                params={"accessKey": access_key, "secretAccessKey": secret},
            ).json()
            if not auth.get("success"):
                raise MigrationError(f"通途鉴权失败：{auth.get('code')} {auth.get('message')}")
            token = auth["datas"]
            timestamp = int(time.time())
            sign = hashlib.md5(
                f"app_token{token}timestamp{timestamp}{secret}".encode()
            ).hexdigest()
            merchants = client.get(
                f"{AUTH_URL}/partnerOpenInfo/getAppBuyerList",
                params={"app_token": token, "timestamp": timestamp, "sign": sign},
            ).json()
            if not merchants.get("success") or not merchants.get("datas"):
                raise MigrationError("通途鉴权失败：没有返回商户信息")
            merchant_id = merchants["datas"][0]["partnerOpenId"]
            body = {
                "merchantId": merchant_id,
                "warehouseName": warehouse,
                "skus": list(skus),
                "pageNo": 1,
                "pageSize": max(50, len(skus) * 2),
                "updatedDateFrom": "2000-01-01 00:00:00",
            }
            resp = client.post(
                f"{API_URL}/openapi/tongtool/stocksQuery",
                params={"app_token": token, "timestamp": str(timestamp), "sign": sign},
                json=body,
            ).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MigrationError(f"通途 API 请求失败：{exc}") from exc

    if resp.get("code") != 200:
        raise MigrationError(f"通途库存查询失败：{resp.get('code')} {resp.get('message')}")
    rows = (resp.get("datas") or {}).get("array") or []
    return {str(r.get("goodsSku", "")).strip(): r for r in rows}


def stock_roles(mapping: dict) -> list[dict]:
    roles: list[dict] = []
    for entry in mapping.get("confirmed") or []:
        if entry.get("old_tt"):
            roles.append(
                {
                    "sku": entry["old_tt"],
                    "role": "旧",
                    "color": entry.get("old_color") or entry.get("pb_color") or "",
                    "note": f"PB {entry.get('pb_sku')} / {entry.get('pb_color', '')}",
                }
            )
        roles.append(
            {
                "sku": entry["new_tt"],
                "role": "新",
                "color": entry.get("new_color") or "",
                "note": f"替代 {entry.get('old_tt')}",
            }
        )
    for entry in mapping.get("unconfirmed") or []:
        roles.append(
            {
                "sku": entry["sku"],
                "role": "新?",
                "color": entry.get("color") or "",
                "note": "未报价/未登记 PB",
            }
        )
    return roles


def evaluate_stock(stock: dict[str, dict], mapping: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for entry in mapping.get("confirmed") or []:
        new_sku = entry["new_tt"]
        available = int((stock.get(new_sku) or {}).get("availableStockQuantity") or 0)
        if available <= 0:
            errors.append(f"新 SKU {new_sku}（{entry.get('new_color')}）可用库存为 0")
        old_sku = entry.get("old_tt")
        if old_sku:
            old_available = int((stock.get(old_sku) or {}).get("availableStockQuantity") or 0)
            if old_available > 0:
                warnings.append(
                    f"旧 SKU {old_sku} 仍有库存 {old_available}；确认是否需要转换"
                )
    return errors, warnings


def cmd_status(args) -> int:
    mapping = load_mapping(Path(args.map))
    roles = stock_roles(mapping)
    stock = fetch_stock(resolve_env_path(args.env), args.warehouse, [r["sku"] for r in roles])

    print(f"仓库: {args.warehouse}")
    print(f"{'SKU':22} {'角色':4} {'颜色':10} {'可用':>5} {'在途':>5} {'待发':>5}  备注")
    for role in roles:
        row = stock.get(role["sku"]) or {}
        print(
            f"{role['sku']:22} {role['role']:4} {role['color']:10} "
            f"{int(row.get('availableStockQuantity') or 0):>5} "
            f"{int(row.get('intransitStockQuantity') or 0):>5} "
            f"{int(row.get('waitingShipmentStockQuantity') or 0):>5}  {role['note']}"
        )

    errors, warnings = evaluate_stock(stock, mapping)
    for warning in warnings:
        print(f"[警告] {warning}")
    for error in errors:
        print(f"[错误] {error}")
    for entry in mapping.get("unconfirmed") or []:
        print(
            f"[注意] {entry['sku']}（{entry.get('color')}）未报价/未登记 PB，"
            "出现订单必须人工确认"
        )
    return 3 if errors else 0


def _check_or_map(args, write: bool) -> int:
    mapping = load_mapping(Path(args.map))
    path = Path(args.csv)
    header, rows = read_order_csv(path)
    plan = analyze_rows(header, rows, mapping)
    print_plan(plan, path)

    if plan.has_blockers and not args.allow_unmapped:
        print("\n[停止] 存在未确认/冲突的 SKU，未写出文件。确认后可加 --allow-unmapped。")
        return 2

    if not write:
        return 0

    out = Path(args.out) if args.out else path.with_name(f"{path.stem}_新SKU{path.suffix}")
    write_order_csv(out, header, apply_plan(header, rows, plan))
    print(f"\n已写出: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="PB 弧形海绵带圆柱颈枕：旧通途 SKU -> 新 SKU 转换")
    ap.add_argument("--map", default=str(DEFAULT_MAP), help="映射 JSON 路径")
    sub = ap.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="查美中仓新旧 SKU 实时库存")
    p_status.add_argument("--env", default="", help="通途凭证 .env（默认自动查找）")
    p_status.add_argument("--warehouse", default=DEFAULT_WAREHOUSE)
    p_status.set_defaults(func=cmd_status)

    for name, write in (("check", False), ("map-order", True)):
        p = sub.add_parser(name, help="只报告" if not write else "转换并写出新 CSV")
        p.add_argument("--csv", required=True)
        p.add_argument("--out", default="")
        p.add_argument("--allow-unmapped", action="store_true")
        p.set_defaults(func=lambda a, w=write: _check_or_map(a, w))
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MigrationError as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
