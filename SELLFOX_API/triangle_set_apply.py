# -*- coding: utf-8 -*-
"""三角有扣套装批量执行：EN 创建 → 客户物料号登记 → 赛狐组合创建并回读。

用法
----
uv run --project .. python triangle_set_apply.py --apply            # 全部 13 行
uv run --project .. python triangle_set_apply.py --only SKU1,SKU2   # dry-run 只看计划
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import soft_wall_stage as sws
import triangle_set_stage as tss
from combo_en import EnRestClient, bundle_from_docs, make_en_session
from combo_reconcile import validate_en_bundle
from sellfox_combo_ops import cmd_create, make_client

HERE = Path(__file__).resolve().parent


def _children_for_row(row: dict) -> list[tuple[str, int]]:
    sku = str(row.get("通途SKU") or "")
    if sku in tss.REAL_SKU:
        fabric, color, size, rounds = tss.REAL_SKU[sku]
    else:
        parsed = tss._parse_name(str(row.get("物料名称") or ""))
        if not parsed:
            raise RuntimeError(f"无法解析组成: {sku}")
        fabric, color, size, rounds = parsed
    return tss._children_for(fabric, color, size, rounds)


def _apply_row(row: dict, args: argparse.Namespace, en: EnRestClient, client: object) -> None:
    sku = str(row.get("通途SKU") or "")
    children = _children_for_row(row)
    if not children:
        raise RuntimeError(f"缺少底层组成: {sku}")
    preview = en.preview(children)
    if preview.get("is_duplicate"):
        row["阶段状态"] = "EN已存在"
        row["备注"] = (row.get("备注") or "") + f" | duplicate={preview.get('existing_bundle')}"
        return
    row["预计TJ#"] = str(preview.get("new_item_code") or "")
    row["EN套件名称"] = str(preview.get("new_item_name") or "")
    if not args.apply:
        row["阶段状态"] = "已预览"
        return
    created = en.create_bundle(children)
    name = str(created.get("name") or created.get("new_item_code") or "")
    pb = en.get_product_bundle(name)
    item = en.get_item(str(pb.get("new_item_code") or name))
    bundle = bundle_from_docs(pb, item)
    problems = validate_en_bundle(bundle)
    if problems:
        raise RuntimeError(f"EN 回读断言失败: {', '.join(problems)}")
    tj_code = bundle.new_item_code
    en_name = bundle.new_item_code_name
    row["预计TJ#"] = tj_code
    row["EN套件名称"] = en_name
    row["EN结果"] = "创建成功并回读"
    detail = en.get_item_customer_items(tj_code)
    existing = list(detail.get("customer_items") or [])
    existing_refs = {str(c.get("ref_code") or "").casefold() for c in existing}
    if sku.casefold() not in existing_refs:
        en.put_customer_items(
            tj_code,
            [*existing, {"customer_group": "美国公司", "ref_code": sku}],
        )
        verified = en.get_item_customer_items(tj_code)
        verified_refs = {str(c.get("ref_code") or "").casefold() for c in (verified.get("customer_items") or [])}
        if sku.casefold() not in verified_refs:
            raise RuntimeError(f"客户物料号回读失败: {tj_code} -> {sku}")
    row["客户物料号结果"] = f"已登记并回读 ({sku})"
    namespace = argparse.Namespace(
        sku=tj_code,
        name=en_name,
        child=[f"{code}:{qty}" for code, qty in children],
        full_cid="428697-",
        auto_calc_weight="true",
        apply=True,
        ops_cache=None,
        bottom_cache=None,
    )
    if cmd_create(client, namespace) != 0:
        raise RuntimeError(f"赛狐创建失败: {tj_code}")
    row["赛狐结果"] = "已创建并回读"
    row["阶段状态"] = "完成"
    row["完成时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="逗号分隔的通途SKU，默认全部")
    parser.add_argument("--env", default="prod", choices=["prod", "test"], help="EN 环境，默认 prod")
    parser.add_argument("--apply", action="store_true", help="实际写入 EN 与赛狐")
    args = parser.parse_args()

    rows = sws.tracker_rows_sorted()
    selected = {s.strip() for s in (args.only or "").split(",") if s.strip()}
    root = HERE.parent
    base, session = make_en_session(root, args.env)
    en = EnRestClient(base, session)
    client = make_client() if args.apply else None
    failed = 0
    for row in rows:
        sku = str(row.get("通途SKU") or "")
        if selected and sku not in selected:
            continue
        if row.get("阶段状态") in {"完成", "EN已存在"}:
            continue
        try:
            _apply_row(row, args, en, client)
        except (SystemExit, RuntimeError, ValueError) as exc:
            failed += 1
            row["阶段状态"] = "失败"
            row["备注"] = (row.get("备注") or "") + f" | 失败: {exc}"
        sws.write_tracker(rows)
        print(json.dumps({"通途SKU": sku, "阶段状态": row["阶段状态"], "预计TJ#": row["预计TJ#"]}, ensure_ascii=False))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.get("阶段状态") or ""] = counts.get(row.get("阶段状态") or "", 0) + 1
    print(json.dumps({
        "mode": "apply" if args.apply else "dry-run",
        "selected": sorted(selected) if selected else "all_pending",
        "counts": counts,
        "failed": failed,
    }, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
