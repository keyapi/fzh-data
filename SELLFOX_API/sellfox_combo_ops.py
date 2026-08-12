# -*- coding: utf-8 -*-
"""Sellfox combo SKU operations: check bottoms, dedupe, create, verify.

This script is a reusable, idempotent helper for the "组合商品/套件" workflow.

Commands
--------
check-bottoms   Check that every child SKU already exists in Sellfox.
check-combo     Check whether a combo SKU exists and print its childSkus/category.
create          Create a combo SKU if missing; dry-run by default.
set-category    Move an existing combo SKU to a category (dry-run by default).

All write commands default to dry-run. Use --apply only after user approval.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from client import SellfoxClient, SellfoxConfig


def find_main_root() -> Path:
    """Find repo root containing .env and EN_API/.env (works in worktrees)."""
    here = Path(__file__).resolve().parent
    candidates = [here.parent, here.parents[1], here.parents[2], here.parents[3]]
    for root in candidates:
        if (root / ".env").exists() and (root / "EN_API" / ".env").exists():
            return root
    # Fallback: normal checkout layout (SELLFOX_API -> repo root).
    return here.parent


def make_client() -> SellfoxClient:
    root = find_main_root()
    cfg = SellfoxConfig.from_env(root / ".env", root / "EN_API" / ".env")
    return SellfoxClient(cfg)


def query_skus(client: SellfoxClient, skus: list[str]) -> dict[str, dict[str, Any]]:
    if not skus:
        return {}
    data = client.signed_post(
        "/api/commodity/pageList.json",
        {"pageNo": "1", "pageSize": str(max(len(skus), 1)), "skus": skus},
    )
    rows = data.get("rows") or []
    return {str(r.get("sku")): r for r in rows}


def find_category(client: SellfoxClient, full_cid: str) -> dict[str, Any] | None:
    categories = client.signed_post("/api/category/getList.json", {}) or []

    def walk(items: list[dict[str, Any]]) -> dict[str, Any] | None:
        for cat in items or []:
            if str(cat.get("fullCid")) == full_cid or str(cat.get("id")) == full_cid:
                return cat
            found = walk(cat.get("childVo") or [])
            if found:
                return found
        return None

    return walk(categories)


def resolve_child_skus(
    client: SellfoxClient, specs: list[tuple[str, int]]
) -> list[dict[str, Any]]:
    skus = [sku for sku, _ in specs]
    existing = query_skus(client, skus)
    missing = [sku for sku, _ in specs if sku not in existing]
    if missing:
        raise SystemExit(f"赛狐底层商品缺失: {', '.join(missing)}")

    result = []
    for sku, num in specs:
        row = existing[sku]
        result.append(
            {
                "childId": str(row.get("id")),
                "sku": sku,
                "num": str(num),
            }
        )
    return result


def print_combo_row(label: str, row: dict[str, Any] | None) -> None:
    if not row:
        print(f"{label}: 不存在")
        return
    summary = {
        "id": row.get("id"),
        "sku": row.get("sku"),
        "name": row.get("name"),
        "fullCid": row.get("fullCid"),
        "fullName": row.get("fullName"),
        "isGroup": row.get("isGroup"),
        "childSkus": row.get("childSkus"),
    }
    print(f"{label}:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_check_bottoms(client: SellfoxClient, args: argparse.Namespace) -> int:
    existing = query_skus(client, args.skus)
    missing = [sku for sku in args.skus if sku not in existing]
    print(f"检测 {len(args.skus)} 个底层 SKU，存在 {len(existing)}，缺失 {len(missing)}")
    for sku in args.skus:
        row = existing.get(sku)
        if row:
            print(f"  存在  {sku}  id={row.get('id')}  isGroup={row.get('isGroup')}  category={row.get('fullName')}")
        else:
            print(f"  缺失  {sku}")
    return 1 if missing else 0


def cmd_check_combo(client: SellfoxClient, args: argparse.Namespace) -> int:
    rows = query_skus(client, [args.sku])
    print_combo_row("组合 SKU", rows.get(args.sku))
    return 0 if rows.get(args.sku) else 1


def cmd_create(client: SellfoxClient, args: argparse.Namespace) -> int:
    child_specs = [(sku, int(num)) for sku, num in (spec.split(":", 1) for spec in args.child)]

    existing = query_skus(client, [args.sku])
    if args.sku in existing:
        print("组合 SKU 已存在，跳过创建")
        print_combo_row("组合 SKU", existing[args.sku])
        return 0

    child_skus = resolve_child_skus(client, child_specs)
    payload = {
        "name": args.name,
        "sku": args.sku,
        "isGroup": "1",
        "autoCalcWeight": args.auto_calc_weight,
        "childSkus": child_skus,
    }
    if args.full_cid:
        category = find_category(client, args.full_cid)
        if not category:
            raise SystemExit(f"分类不存在: {args.full_cid}")
        payload["fullCid"] = str(category.get("fullCid"))

    print("创建请求:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.apply:
        print("dry-run，未写入。确认后加 --apply。")
        return 0

    data = client.signed_post("/api/commodity/create.json", payload)
    print("创建成功:", json.dumps(data, ensure_ascii=False))
    rows = query_skus(client, [args.sku])
    print_combo_row("回读验证", rows.get(args.sku))
    return 0


def cmd_set_category(client: SellfoxClient, args: argparse.Namespace) -> int:
    rows = query_skus(client, [args.sku])
    row = rows.get(args.sku)
    if not row:
        raise SystemExit(f"组合 SKU 不存在: {args.sku}")
    category = find_category(client, args.full_cid)
    if not category:
        raise SystemExit(f"分类不存在: {args.full_cid}")

    payload = {
        "id": str(row.get("id")),
        "sku": args.sku,
        "name": row.get("name") or "",
        "fullCid": str(category.get("fullCid")),
        "isGroup": str(row.get("isGroup") or "1"),
        "childSkus": row.get("childSkus") or [],
    }
    print("修改分类请求:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.apply:
        print("dry-run，未写入。确认后加 --apply。")
        return 0

    data = client.signed_post("/api/commodity/edit.json", payload)
    print("修改成功:", json.dumps(data, ensure_ascii=False))
    rows = query_skus(client, [args.sku])
    print_combo_row("回读验证", rows.get(args.sku))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check-bottoms", help="检查底层 SKU 是否存在")
    p.add_argument("--sku", dest="skus", action="append", required=True, help="底层 SKU，可重复")
    p.set_defaults(func=cmd_check_bottoms)

    p = sub.add_parser("check-combo", help="检查组合 SKU 是否存在")
    p.add_argument("--sku", required=True, help="组合 SKU")
    p.set_defaults(func=cmd_check_combo)

    p = sub.add_parser("create", help="创建组合 SKU（默认 dry-run）")
    p.add_argument("--sku", required=True, help="组合 SKU")
    p.add_argument("--name", required=True, help="组合商品名称")
    p.add_argument("--child", action="append", required=True, help="底层 SKU:数量，可重复")
    p.add_argument("--full-cid", help="分类全路径，例如 428697-")
    p.add_argument("--auto-calc-weight", default="true", help="组合商品是否自动计算重量")
    p.add_argument("--apply", action="store_true", help="实际写入赛狐")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("set-category", help="把组合 SKU 移到分类（默认 dry-run）")
    p.add_argument("--sku", required=True, help="组合 SKU")
    p.add_argument("--full-cid", required=True, help="分类全路径，例如 428697-")
    p.add_argument("--apply", action="store_true", help="实际写入赛狐")
    p.set_defaults(func=cmd_set_category)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = make_client()
    print(f"赛狐模式: {client.config.mode}")
    return args.func(client, args)


if __name__ == "__main__":
    raise SystemExit(main())
