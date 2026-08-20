# -*- coding: utf-8 -*-
"""Sellfox combo SKU operations: EN fetch, reconcile, create, verify.

Commands
--------
check-bottoms   Check that every child SKU already exists in Sellfox.
check-combo     Check whether a combo SKU exists and print its childSkus/category.
create          Create a combo SKU if missing; dry-run by default.
set-category    Move an existing combo SKU to a category (dry-run by default).
sync-combos     Pull EN Product Bundles, reconcile Sellfox, plan, optional apply.
en-preview      Preview EN Product Bundle serial from items (read-only).
en-create       Create EN Product Bundle with items-only payload (dry-run default).

All write commands default to dry-run. Use --apply only after user approval.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from client import SellfoxClient, SellfoxConfig
from combo_en import (
    EnRestClient,
    assert_en_create_payload,
    bundle_from_docs,
    en_create_payload,
    fetch_en_bundles,
    make_en_session,
)
from combo_reconcile import (
    DEFAULT_FULL_CID,
    assert_combo_row,
    duplicate_skus,
    index_sellfox_combos,
    parse_child_specs,
    plan_sync,
    summarize_plan,
    validate_en_bundle,
)


def find_main_root() -> Path:
    """Find repo root containing .env and EN_API/.env (works in worktrees)."""
    here = Path(__file__).resolve().parent
    candidates = [here.parent, here.parents[1], here.parents[2], here.parents[3]]
    for root in candidates:
        if (root / ".env").exists() and (root / "EN_API" / ".env").exists():
            return root
    return here.parent


def make_client() -> SellfoxClient:
    root = find_main_root()
    cfg = SellfoxConfig.from_env(root / ".env", root / "EN_API" / ".env")
    return SellfoxClient(cfg)


def make_en_client(env_name: str) -> EnRestClient:
    base, session = make_en_session(find_main_root(), env_name)
    return EnRestClient(base, session)


def query_sku_rows(client: SellfoxClient, skus: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unique = [sku for sku in dict.fromkeys(skus) if sku]
    for offset in range(0, len(unique), 50):
        chunk = unique[offset : offset + 50]
        data = client.signed_post(
            "/api/commodity/pageList.json",
            {"pageNo": "1", "pageSize": str(max(len(chunk), 1)), "skus": chunk},
        )
        for row in data.get("rows") or []:
            if row.get("sku"):
                rows.append(row)
    return rows


def query_skus(client: SellfoxClient, skus: list[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in query_sku_rows(client, skus):
        sku = str(row.get("sku") or "")
        if sku:
            found[sku] = row
    return found


def require_unique_sku(rows: list[dict[str, Any]], sku: str) -> dict[str, Any] | None:
    dups = duplicate_skus(rows)
    if sku in dups:
        raise SystemExit(f"赛狐同 SKU 重复记录: {sku}")
    for row in rows:
        if str(row.get("sku") or "") == sku:
            return row
    return None


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


def require_combo_match(
    row: dict[str, Any] | None,
    *,
    sku: str,
    name: str,
    children: list[tuple[str, int]] | tuple[tuple[str, int], ...],
    full_cid: str | None,
) -> None:
    failures = assert_combo_row(
        row,
        sku=sku,
        name=name,
        children=children,
        full_cid=full_cid or "",
    )
    if failures:
        print_combo_row("回读断言失败", row)
        raise SystemExit(f"回读断言失败: {', '.join(failures)}")


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
    raw = query_sku_rows(client, [args.sku])
    row = require_unique_sku(raw, args.sku)
    print_combo_row("组合 SKU", row)
    return 0 if row else 1


def cmd_create(client: SellfoxClient, args: argparse.Namespace) -> int:
    child_specs = list(parse_child_specs(args.child))
    raw = query_sku_rows(client, [args.sku])
    existing_row = require_unique_sku(raw, args.sku)
    if existing_row:
        print("组合 SKU 已存在，跳过创建，执行回读断言")
        print_combo_row("组合 SKU", existing_row)
        require_combo_match(
            existing_row,
            sku=args.sku,
            name=args.name,
            children=child_specs,
            full_cid=args.full_cid,
        )
        print("回读断言通过")
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
    raw = query_sku_rows(client, [args.sku])
    row = require_unique_sku(raw, args.sku)
    print_combo_row("回读验证", row)
    require_combo_match(
        row,
        sku=args.sku,
        name=args.name,
        children=child_specs,
        full_cid=args.full_cid,
    )
    print("回读断言通过")
    return 0


def cmd_set_category(client: SellfoxClient, args: argparse.Namespace) -> int:
    raw = query_sku_rows(client, [args.sku])
    row = require_unique_sku(raw, args.sku)
    if not row:
        raise SystemExit(f"组合 SKU 不存在: {args.sku}")
    category = find_category(client, args.full_cid)
    if not category:
        raise SystemExit(f"分类不存在: {args.full_cid}")

    payload = {
        "id": str(row.get("id")),
        "sku": args.sku,
        "name": row.get("name") or "",
        "isGroup": str(row.get("isGroup") or "1"),
        "childSkus": row.get("childSkus") or [],
        "fullCid": str(category.get("fullCid")),
    }
    print("修改分类请求:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.apply:
        print("dry-run，未写入。确认后加 --apply。")
        return 0

    data = client.signed_post("/api/commodity/edit.json", payload)
    print("修改成功:", json.dumps(data, ensure_ascii=False))
    raw = query_sku_rows(client, [args.sku])
    verified = require_unique_sku(raw, args.sku)
    print_combo_row("回读验证", verified)
    children = [
        (str(child.get("sku")), int(child.get("num") or 0))
        for child in (row.get("childSkus") or [])
    ]
    require_combo_match(
        verified,
        sku=args.sku,
        name=str(row.get("name") or ""),
        children=children,
        full_cid=str(category.get("fullCid")),
    )
    print("回读断言通过")
    return 0


def _write_report(path: str | None, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if path:
        Path(path).write_text(text, encoding="utf-8")
        print(f"报告已写: {path}")


def cmd_sync_combos(client: SellfoxClient, args: argparse.Namespace) -> int:
    if not args.like and not args.sku:
        raise SystemExit("sync-combos 必须提供 --like 或 --sku，禁止无范围全量")
    en = make_en_client(args.env)
    bundles = fetch_en_bundles(en, name_like=args.like, names=args.sku)
    print(f"EN Product Bundle: {len(bundles)}")
    if not bundles:
        _write_report(
            args.report,
            {
                "input_en": 0,
                "output_rows": 0,
                "counts": {},
                "rows": [],
                "unmatched": [],
                "note": "EN 无匹配套件",
            },
        )
        return 1

    child_skus = sorted(
        {
            child.item_code
            for bundle in bundles
            for child in bundle.items
            if child.item_code
        }
    )
    combo_skus = [bundle.new_item_code or bundle.name for bundle in bundles]
    bottoms = query_skus(client, child_skus)
    combo_rows = query_sku_rows(client, combo_skus)
    sellfox_by_sku, dups = index_sellfox_combos(combo_rows)
    plan = plan_sync(
        bundles,
        sellfox_by_sku,
        set(bottoms),
        expected_full_cid=args.full_cid or DEFAULT_FULL_CID,
        duplicate_skus=dups,
    )
    summary = summarize_plan(plan)
    summary["en_env"] = args.env
    summary["filter"] = {"like": args.like, "sku": args.sku}
    _write_report(args.report, summary)

    blocked = [row for row in plan.rows if row.action.startswith("blocked") or row.action == "mismatch"]
    if not args.apply:
        print("dry-run，未写入。确认计划后加 --apply。mismatch/blocked 永远不会自动修。")
        return 1 if blocked else 0

    applied: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for row in plan.rows:
        if row.action == "create":
            ns = argparse.Namespace(
                sku=row.sku,
                name=row.name,
                child=[f"{sku}:{qty}" for sku, qty in row.expected_children],
                full_cid=args.full_cid or DEFAULT_FULL_CID,
                auto_calc_weight="true",
                apply=True,
            )
            try:
                cmd_create(client, ns)
                applied.append({"sku": row.sku, "action": "create"})
            except SystemExit as exc:
                failed.append({"sku": row.sku, "action": "create", "error": str(exc)})
        elif row.action == "set_category":
            ns = argparse.Namespace(
                sku=row.sku,
                full_cid=args.full_cid or DEFAULT_FULL_CID,
                apply=True,
            )
            try:
                cmd_set_category(client, ns)
                applied.append({"sku": row.sku, "action": "set_category"})
            except SystemExit as exc:
                failed.append({"sku": row.sku, "action": "set_category", "error": str(exc)})

    final_rows = query_sku_rows(client, combo_skus)
    final_by_sku, final_dups = index_sellfox_combos(final_rows)
    assertion_failures: list[dict[str, Any]] = []
    for row in plan.rows:
        if row.action not in {"ok", "create", "set_category"}:
            continue
        if row.sku in final_dups:
            assertion_failures.append({"sku": row.sku, "failures": ["duplicate_sku"]})
            continue
        expected_cid = args.full_cid or DEFAULT_FULL_CID
        combo = final_by_sku.get(row.sku)
        failures = assert_combo_row(
            {
                "sku": combo.sku,
                "name": combo.name,
                "isGroup": combo.is_group,
                "fullCid": combo.full_cid,
                "childSkus": [{"sku": sku, "num": num} for sku, num in combo.child_skus],
            }
            if combo
            else None,
            sku=row.sku,
            name=row.name,
            children=row.expected_children,
            full_cid=expected_cid,
        )
        if failures:
            assertion_failures.append({"sku": row.sku, "failures": list(failures)})

    result = {
        "applied": applied,
        "failed": failed,
        "assertion_failures": assertion_failures,
        "plan_counts": plan.counts,
        "blocked": [
            {"sku": row.sku, "action": row.action, "reason": row.reason, "problems": list(row.problems)}
            for row in blocked
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failed or assertion_failures or blocked:
        return 1
    return 0


def cmd_en_preview(_client: SellfoxClient, args: argparse.Namespace) -> int:
    children = parse_child_specs(args.child)
    en = make_en_client(args.env)
    preview = en.preview(children)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if preview.get("is_duplicate"):
        print("该组成已存在 EN 套件，不要再创建。")
        return 1
    return 0


def cmd_en_create(_client: SellfoxClient, args: argparse.Namespace) -> int:
    children = parse_child_specs(args.child)
    payload = en_create_payload(children)
    assert_en_create_payload(payload)
    en = make_en_client(args.env)
    preview = en.preview(children)
    print("EN 预览:")
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    if preview.get("is_duplicate"):
        print("该组成已存在，禁止重复创建。")
        print(f"existing_bundle={preview.get('existing_bundle')}")
        return 1
    print("EN 创建请求（只传 items）:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.apply:
        print(f"dry-run，未写入 EN {args.env}。确认后加 --apply。")
        return 0
    created = en.create_bundle(children)
    name = str(created.get("name") or created.get("new_item_code") or "")
    pb = en.get_product_bundle(name)
    item = en.get_item(str(pb.get("new_item_code") or name))
    bundle = bundle_from_docs(pb, item)
    problems = validate_en_bundle(bundle)
    print("EN 回读:")
    print(
        json.dumps(
            {
                "name": bundle.name,
                "new_item_code": bundle.new_item_code,
                "new_item_code_name": bundle.new_item_code_name,
                "item_code": bundle.item_code,
                "item_name": bundle.item_name,
                "item_group": bundle.item_group,
                "items": [{"item_code": c.item_code, "qty": c.qty} for c in bundle.items],
                "problems": list(problems),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if problems:
        raise SystemExit(f"EN 回读断言失败: {', '.join(problems)}")
    print("EN 回读断言通过。赛狐侧请再跑 sync-combos。")
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

    p = sub.add_parser("sync-combos", help="从 EN 拉取套件并对账赛狐（默认 dry-run）")
    p.add_argument("--like", help="EN Product Bundle name like，例如 TJ#KS0443%")
    p.add_argument("--sku", action="append", help="精确 EN/赛狐组合 SKU，可重复")
    p.add_argument("--full-cid", default=DEFAULT_FULL_CID, help="期望赛狐分类")
    p.add_argument("--env", default="prod", choices=["prod", "test"], help="EN 环境，默认 prod")
    p.add_argument("--report", help="把对账 JSON 写到该路径")
    p.add_argument("--apply", action="store_true", help="按计划创建缺失组合/改分类")
    p.set_defaults(func=cmd_sync_combos)

    p = sub.add_parser("en-preview", help="按 items 预览 EN 套件编号（只读）")
    p.add_argument("--child", action="append", required=True, help="底层 SKU:数量，可重复")
    p.add_argument("--env", default="prod", choices=["prod", "test"], help="EN 环境，默认 prod")
    p.set_defaults(func=cmd_en_preview)

    p = sub.add_parser("en-create", help="创建 EN Product Bundle（默认 dry-run，只传 items）")
    p.add_argument("--child", action="append", required=True, help="底层 SKU:数量，可重复")
    p.add_argument("--env", default="prod", choices=["prod", "test"], help="EN 环境，默认 prod")
    p.add_argument("--apply", action="store_true", help="实际写入 EN")
    p.set_defaults(func=cmd_en_create)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command in {"en-preview", "en-create"}:
        print(f"EN 环境: {args.env}")
        return args.func(None, args)
    client = make_client()
    print(f"赛狐模式: {client.config.mode}")
    return args.func(client, args)


if __name__ == "__main__":
    raise SystemExit(main())
