# -*- coding: utf-8 -*-
"""Sellfox PK# → KS x1 cover combo ops (inventory alias, not EN TJ# bundles).

Commands
--------
plan                Build create/ok/blocked/mismatch plan (always dry-run).
apply               Create missing PK# combos from a plan JSON (--apply required).
pairing-candidates  Read-only cover listing → PK# suggestions (no match write).

All writes require --apply. Default env is prod.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

from client import SellfoxClient
from cover_combo_plan import (
    FAMILIES,
    SPU_PREFIXES,
    BomCost,
    EnItemBrief,
    SellfoxSkuBrief,
    build_bom_cost,
    is_ordinary_finished,
    parse_children,
    pk_sku_for_ks,
    plan_cover_combos,
    summarize_plan,
)
from repo_root import find_main_root
from sellfox_combo_ops import (
    make_client,
    make_en_client,
    query_sku_rows,
    query_skus,
    require_unique_sku,
    resolve_child_skus,
)

DEFAULT_BOM_XLSX = Path("en_bom_cost_list") / "EN产品BOM成本列表_20260821_1501.xlsx"
DEFAULT_BOM_META = Path(".codex_tmp") / "bom_cost_list_20260821_1501.json"


def _root() -> Path:
    return find_main_root(start=Path(__file__).resolve().parent)


def sellfox_brief(row: dict[str, Any]) -> SellfoxSkuBrief:
    return SellfoxSkuBrief(
        sku=str(row.get("sku") or ""),
        name=str(row.get("name") or ""),
        is_group=str(row.get("isGroup") if row.get("isGroup") is not None else ""),
        full_cid=str(row.get("fullCid") or ""),
        child_skus=parse_children(row.get("childSkus")),
        id=str(row.get("id") or ""),
    )


def list_en_variants(en_client: Any, template: str) -> dict[str, EnItemBrief]:
    out: dict[str, EnItemBrief] = {}
    start = 0
    page = 200
    fields = ["name", "item_code", "item_name", "disabled", "variant_of"]
    while True:
        data = en_client._get(
            "/api/resource/Item",
            {
                "filters": json.dumps([["variant_of", "=", template]]),
                "fields": json.dumps(fields),
                "limit_start": start,
                "limit_page_length": page,
            },
        )
        rows = data.get("data") or []
        for row in rows:
            code = str(row.get("item_code") or "")
            if not code:
                continue
            out[code] = EnItemBrief(
                item_code=code,
                item_name=str(row.get("item_name") or ""),
                disabled=bool(row.get("disabled")),
            )
        if len(rows) < page:
            break
        start += page
    return out


def list_sellfox_ordinary_for_skus(
    client: SellfoxClient, skus: list[str]
) -> dict[str, SellfoxSkuBrief]:
    """Batch-query Sellfox ordinary finished SKUs (isGroup=0)."""
    found: dict[str, SellfoxSkuBrief] = {}
    unique = [s for s in dict.fromkeys(skus) if s]
    for offset in range(0, len(unique), 50):
        chunk = unique[offset : offset + 50]
        raw = query_sku_rows(client, chunk)
        for row in raw:
            sku = str(row.get("sku") or "")
            if sku not in chunk:
                continue
            if not is_ordinary_finished(row):
                continue
            found[sku] = sellfox_brief(row)
    return found


def page_sellfox_sku_search(
    client: SellfoxClient,
    search_value: str,
    *,
    is_group: str | None = None,
    page_size: int = 200,
) -> list[dict[str, Any]]:
    """Prefix/keyword sku search. Inventory PK# without 50-sku chunks."""
    rows: list[dict[str, Any]] = []
    page_no = 1
    while True:
        body: dict[str, Any] = {
            "pageNo": str(page_no),
            "pageSize": str(page_size),
            "searchField": "sku",
            "searchValue": search_value,
        }
        if is_group is not None:
            body["isGroup"] = str(is_group)
        data = client.signed_post("/api/commodity/pageList.json", body)
        if not isinstance(data, dict):
            break
        batch = data.get("rows") or []
        rows.extend(batch)
        total = int(data.get("total") or 0)
        pages = -(-total // page_size) if page_size and total else 0
        print(
            f"  search sku={search_value!r} isGroup={is_group} page={page_no} "
            f"got={len(batch)} accum={len(rows)} total={total}",
            flush=True,
        )
        # Some Sellfox list calls return rows but total=0. Keep paging while the
        # page is full; stop on a short page.
        if len(batch) < page_size:
            break
        if pages and page_no >= pages:
            break
        page_no += 1
        if page_no > 100:
            raise SystemExit(f"sku search {search_value} exceeded 100 pages")
    return rows


def classify_plan_against_live(
    plan_rows: list[dict[str, Any]],
    live_by_sku: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    already_ok: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []
    need_create: list[dict[str, Any]] = []
    for row in plan_rows:
        pk = row["pk_sku"]
        live = live_by_sku.get(pk)
        if live is None:
            need_create.append(row)
            continue
        try:
            _assert_created(live, row)
            already_ok.append(row)
        except SystemExit:
            mismatch.append(
                {
                    **row,
                    "live_isGroup": live.get("isGroup"),
                    "live_id": live.get("id"),
                    "live_name": live.get("name"),
                    "live_children": parse_children(live.get("childSkus")),
                }
            )
    return {
        "already_ok": already_ok,
        "mismatch": mismatch,
        "need_create": need_create,
    }


def load_bom_costs(root: Path, xlsx: Path, meta: Path | None) -> dict[str, BomCost]:
    path = xlsx if xlsx.is_absolute() else root / xlsx
    if not path.is_file():
        raise SystemExit(f"BOM xlsx missing: {path}")

    df = pd.read_excel(path)
    # Prefer labeled Chinese columns; fall back to fieldnames via meta.
    colmap: dict[str, str] = {}
    if meta is not None:
        meta_path = meta if meta.is_absolute() else root / meta
        if meta_path.is_file():
            columns = json.loads(meta_path.read_text(encoding="utf-8")).get("columns") or []
            for c in columns:
                fieldname = str(c.get("fieldname") or "")
                label = str(c.get("label") or "").replace("<br>", ",")
                if fieldname and fieldname in df.columns:
                    colmap[fieldname] = fieldname
                # rename labeled export if present
                if label in df.columns:
                    colmap[fieldname] = label

    def col(*candidates: str) -> str | None:
        for name in candidates:
            if name in df.columns:
                return name
            mapped = colmap.get(name)
            if mapped and mapped in df.columns:
                return mapped
        return None

    sku_col = col("产品编号", "item_fg")
    cover_col = col("皮壳成本", "cost_fg")
    usnj_col = col("头程皮壳运费,美东USNJ", "头程皮壳运费美东USNJ", "cover_freight_2kk9fsq8ln")
    ustx_col = col("头程皮壳运费,美中USTX", "头程皮壳运费美中USTX", "cover_freight_e5asph24tk")
    pl_col = col("头程皮壳运费,波兰PL", "头程皮壳运费波兰PL", "cover_freight_tmvvepd80f")
    mode_col = col("绍兴发货方式", "shipping_method")
    if not sku_col or not cover_col:
        raise SystemExit(f"BOM missing sku/cover columns; have={list(df.columns)[:20]}")

    out: dict[str, BomCost] = {}
    for _, row in df.iterrows():
        sku = str(row.get(sku_col) or "").strip()
        if not sku.startswith(SPU_PREFIXES):
            continue
        out[sku] = build_bom_cost(
            cover_cost=row.get(cover_col),
            usnj=row.get(usnj_col) if usnj_col else None,
            ustx=row.get(ustx_col) if ustx_col else None,
            pl=row.get(pl_col) if pl_col else None,
            mode=str(row.get(mode_col) or "") if mode_col else "",
        )
    return out


def build_plan(client: SellfoxClient, en_client: Any, root: Path, args: argparse.Namespace) -> dict[str, Any]:
    print("Loading EN variants…", flush=True)
    en_products: dict[str, EnItemBrief] = {}
    en_covers: dict[str, EnItemBrief] = {}
    for fam in FAMILIES:
        products = list_en_variants(en_client, fam["product_template"])
        covers = list_en_variants(en_client, fam["cover_template"])
        en_products.update(products)
        en_covers.update(covers)
        print(
            f"  EN {fam['spu']}: products={len(products)} covers={len(covers)}",
            flush=True,
        )

    print("Querying Sellfox ordinary KS for EN product codes…", flush=True)
    sellfox_ks: dict[str, SellfoxSkuBrief] = {}
    product_codes = sorted(en_products.keys())
    sellfox_ks = list_sellfox_ordinary_for_skus(client, product_codes)
    for fam in FAMILIES:
        prefix = fam["product_template"] + "-"
        n = sum(1 for s in sellfox_ks if s.startswith(prefix))
        print(f"  Sellfox {fam['spu']}: ordinary={n}", flush=True)

    ks_list = sorted(sellfox_ks.values(), key=lambda r: r.sku)
    pk_skus = [pk for ks in ks_list if (pk := pk_sku_for_ks(ks.sku))]
    print(f"Querying Sellfox PK# for {len(pk_skus)} candidates…", flush=True)
    pk_raw = query_skus(client, pk_skus)
    sellfox_pk = {sku: sellfox_brief(row) for sku, row in pk_raw.items()}

    print("Loading BOM costs…", flush=True)
    bom = load_bom_costs(root, Path(args.bom), Path(args.bom_meta) if args.bom_meta else None)
    print(f"  BOM triangle rows: {len(bom)}", flush=True)

    rows = plan_cover_combos(
        sellfox_ks_rows=ks_list,
        en_products=en_products,
        en_covers=en_covers,
        sellfox_pk_rows=sellfox_pk,
        bom_by_ks=bom,
    )
    summary = summarize_plan(rows)
    report = {
        "families": [f["spu"] for f in FAMILIES],
        "bom_path": str((root / args.bom) if not Path(args.bom).is_absolute() else args.bom),
        **summary,
        "rows": [r.to_dict() for r in rows],
    }
    return report


def cmd_plan(args: argparse.Namespace) -> int:
    root = _root()
    client = make_client()
    en_client = make_en_client(args.env)
    report = build_plan(client, en_client, root, args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        out = Path(args.report)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}", flush=True)
    print(
        json.dumps(
            {
                "input_ks": report["input_ks"],
                "output_rows": report["output_rows"],
                "counts": report["counts"],
                "cost_missing": report["cost_missing"],
                "unmatched_n": len(report["unmatched"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


def _assert_created(row: dict[str, Any], plan_row: dict[str, Any]) -> None:
    problems: list[str] = []
    if str(row.get("sku")) != plan_row["pk_sku"]:
        problems.append("sku")
    if not str(row.get("isGroup")).strip() in {"1", "true"}:
        problems.append("isGroup")
    children = parse_children(row.get("childSkus"))
    if tuple(sorted(children)) != ((plan_row["ks_sku"], 1),):
        problems.append("childSkus")
    expected_name = plan_row.get("en_pk_name") or ""
    if expected_name and str(row.get("name") or "") != expected_name:
        problems.append("name")
    if problems:
        raise SystemExit(
            f"回读断言失败 {plan_row['pk_sku']}: {problems} "
            f"got children={children} name={row.get('name')}"
        )


def cmd_status(args: argparse.Namespace) -> int:
    """Live-reconcile plan vs Sellfox PK# (combo + ordinary). No writes."""
    root = _root()
    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    create_rows = [r for r in plan.get("rows") or [] if r.get("action") == "create"]
    client = make_client()
    live_rows: list[dict[str, Any]] = []
    for prefix in ("PK#KS0001", "PK#KS0248"):
        live_rows.extend(page_sellfox_sku_search(client, prefix, is_group=None))
    live_by_sku: dict[str, dict[str, Any]] = {}
    for row in live_rows:
        sku = str(row.get("sku") or "")
        if sku:
            live_by_sku[sku] = row
    classified = classify_plan_against_live(create_rows, live_by_sku)
    extra = [
        sku
        for sku in live_by_sku
        if sku.startswith(("PK#KS0001", "PK#KS0248"))
        and sku not in {r["pk_sku"] for r in create_rows}
    ]
    by_spu_need: dict[str, int] = {}
    by_spu_ok: dict[str, int] = {}
    for r in classified["need_create"]:
        by_spu_need[r.get("spu") or "?"] = by_spu_need.get(r.get("spu") or "?", 0) + 1
    for r in classified["already_ok"]:
        by_spu_ok[r.get("spu") or "?"] = by_spu_ok.get(r.get("spu") or "?", 0) + 1
    group_counts: dict[str, int] = {}
    for row in live_by_sku.values():
        key = str(row.get("isGroup"))
        group_counts[key] = group_counts.get(key, 0) + 1
    summary = {
        "plan_create": len(create_rows),
        "live_pk_hits": len(live_by_sku),
        "live_isGroup": group_counts,
        "already_ok": len(classified["already_ok"]),
        "already_ok_by_spu": by_spu_ok,
        "mismatch": len(classified["mismatch"]),
        "need_create": len(classified["need_create"]),
        "need_create_by_spu": by_spu_need,
        "extra_live_not_in_plan": extra[:50],
        "next_batch": [r["pk_sku"] for r in classified["need_create"][:50]],
        "mismatch_sample": [
            {
                "pk_sku": r["pk_sku"],
                "live_isGroup": r.get("live_isGroup"),
                "live_id": r.get("live_id"),
            }
            for r in classified["mismatch"][:20]
        ],
        "note": "组合商品不会出现在「普通商品」筛选里；用 SKU=PK# 或商品类型=组合商品。",
    }
    out = Path(args.report)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **summary,
        "need_create_skus": [r["pk_sku"] for r in classified["need_create"]],
        "already_ok_skus": [r["pk_sku"] for r in classified["already_ok"]],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"wrote {out}", flush=True)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    root = _root()
    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    if not plan_path.is_file():
        raise SystemExit(f"plan not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    all_create = [r for r in plan.get("rows") or [] if r.get("action") == "create"]
    if args.only:
        allow = set(args.only)
        all_create = [r for r in all_create if r["pk_sku"] in allow or r["ks_sku"] in allow]

    client = make_client()
    print("Live inventory PK#KS0001 / PK#KS0248…", flush=True)
    live_rows: list[dict[str, Any]] = []
    for prefix in ("PK#KS0001", "PK#KS0248"):
        live_rows.extend(page_sellfox_sku_search(client, prefix, is_group=None))
    live_by_sku = {str(r.get("sku")): r for r in live_rows if r.get("sku")}
    classified = classify_plan_against_live(all_create, live_by_sku)
    remaining = classified["need_create"]
    batch_size = max(int(args.batch_size), 1)
    batch = remaining[:batch_size]
    print(
        f"already_ok={len(classified['already_ok'])} mismatch={len(classified['mismatch'])} "
        f"need_create={len(remaining)} this_batch={len(batch)} apply={args.apply}",
        flush=True,
    )

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = [
        {"pk_sku": r["pk_sku"], "reason": "already_ok"} for r in classified["already_ok"]
    ]
    failed: list[dict[str, Any]] = [
        {"pk_sku": r["pk_sku"], "reason": "mismatch", "live_isGroup": r.get("live_isGroup")}
        for r in classified["mismatch"]
    ]

    def write_progress(*, pending_skus: list[str]) -> None:
        report_path.write_text(
            json.dumps(
                {
                    "plan": str(plan_path),
                    "already_ok": len(classified["already_ok"]),
                    "mismatch": len(classified["mismatch"]),
                    "need_create_before_batch": len(remaining),
                    "batch_size": batch_size,
                    "created": created,
                    "skipped_new": [s for s in skipped if s.get("reason") != "already_ok"],
                    "failed": failed,
                    "pending": pending_skus,
                    "counts": {
                        "created_this_batch": len(created),
                        "failed_this_batch": len(
                            [f for f in failed if f.get("stage") == "create"]
                        ),
                        "remaining_after": len(pending_skus),
                    },
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    if not batch:
        write_progress(pending_skus=[])
        print("nothing to create", flush=True)
        return 0

    ks_list = [r["ks_sku"] for r in batch]
    print(f"Loading {len(ks_list)} bottoms for this batch…", flush=True)
    bottom_cache = query_skus(client, ks_list)

    for i, row in enumerate(batch, 1):
        pk = row["pk_sku"]
        ks = row["ks_sku"]
        print(f"[{i}/{len(batch)}] {pk}", flush=True)
        if ks not in bottom_cache:
            failed.append({"pk_sku": pk, "error": f"missing bottom {ks}", "stage": "bottom"})
            print("  FAIL missing bottom", flush=True)
            continue
        if row.get("cost_missing") and not args.allow_missing_cost:
            failed.append({"pk_sku": pk, "error": "cost_missing", "stage": "cost"})
            print("  SKIP cost_missing", flush=True)
            continue
        children = resolve_child_skus(client, [(ks, 1)], bottom_cache=bottom_cache)
        payload: dict[str, Any] = {
            "name": row.get("en_pk_name") or f"皮壳#{ks}",
            "sku": pk,
            "isGroup": "1",
            "autoCalcWeight": "false",
            "childSkus": children,
            "purchaseCostLock": "0",
            "fullCid": str(row.get("full_cid") or ""),
        }
        if row.get("purchase_cost") is not None:
            payload["purchaseCost"] = str(row["purchase_cost"])
        if row.get("remark"):
            payload["remark"] = row["remark"]
        if not args.apply:
            skipped.append({"pk_sku": pk, "reason": "dry_run"})
            continue
        try:
            created_data = client.signed_post("/api/commodity/create.json", payload)
            created_id = created_data.get("id") if isinstance(created_data, dict) else None
            created.append({"pk_sku": pk, "id": created_id})
            print(f"  created id={created_id}", flush=True)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "已存在" in msg:
                skipped.append({"pk_sku": pk, "reason": "already_exists_on_create"})
                print("  skip already exists", flush=True)
            else:
                failed.append({"pk_sku": pk, "error": msg, "stage": "create"})
                print(f"  FAIL: {exc}", flush=True)
        if i % 10 == 0:
            write_progress(pending_skus=[r["pk_sku"] for r in remaining[i:]])

    write_progress(pending_skus=[r["pk_sku"] for r in remaining[len(batch) :]])
    print(
        json.dumps(
            {
                "created_this_batch": len(created),
                "need_create_before": len(remaining),
                "remaining_after": max(len(remaining) - len(batch), 0),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    print(f"wrote {report_path}", flush=True)
    remaining_after = max(len(remaining) - len(batch), 0)
    if (
        args.apply
        and getattr(args, "until_done", False)
        and remaining_after > 0
        and len(created) > 0
    ):
        print(f"until-done: remaining ~{remaining_after}, next batch…", flush=True)
        return cmd_apply(args)
    return 1 if any(f.get("stage") == "create" for f in failed) else 0
def cmd_pairing_candidates(args: argparse.Namespace) -> int:
    """Read-only: true cover listings that could pair to PK# (no write)."""
    root = _root()
    sys.path.insert(0, str(root))
    from amazon_pairing.routing import route_listing  # noqa: WPS433

    cache = root / "missing_products" / "out" / "pairing_cache"
    plan_pk: set[str] = set()
    plan_ks_to_pk: dict[str, str] = {}
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.is_absolute():
            plan_path = root / plan_path
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        for row in plan.get("rows") or []:
            if row.get("action") in {"ok", "create"} and row.get("pk_sku"):
                plan_pk.add(row["pk_sku"])
                plan_ks_to_pk[row["ks_sku"]] = row["pk_sku"]

    client = make_client()
    # Refresh which PK# already exist
    existing_pk = set()
    if plan_pk:
        found = query_skus(client, sorted(plan_pk))
        existing_pk = set(found)

    candidates: list[dict[str, Any]] = []
    for fname, matched in (("amazon_matched.json", True), ("amazon_unmatched.json", False)):
        path = cache / fname
        if not path.is_file():
            print(f"skip missing cache {path}", flush=True)
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            msku = str(row.get("sku") or "")
            title = str(row.get("title") or "")
            parent = str(row.get("parentSku") or "")
            fulfillment = str(row.get("switchFulfillmentTo") or "")
            route = route_listing(msku, title, parent, fulfillment)
            if route.object_type != "cover":
                continue
            commodity = str(row.get("commoditySku") or "")
            suggested = ""
            if commodity in plan_ks_to_pk:
                suggested = plan_ks_to_pk[commodity]
            elif commodity.startswith("PK#") and commodity in plan_pk:
                suggested = commodity
            else:
                # Infer from family commodity
                if commodity.startswith(SPU_PREFIXES):
                    suggested = pk_sku_for_ks(commodity) or ""
                else:
                    blob = " ".join([title, msku, parent, commodity]).lower()
                    if not any(x in blob for x in ("triangle", "wedge", "ks0001", "ks0248", "三角")):
                        continue
            if not suggested:
                continue
            if not suggested.startswith(("PK#KS0001", "PK#KS0248")):
                continue
            candidates.append(
                {
                    "matched": matched,
                    "shopId": row.get("shopId"),
                    "marketplaceId": row.get("marketplaceId"),
                    "msku": msku,
                    "asin": row.get("asin"),
                    "title": title,
                    "onlineStatus": row.get("onlineStatus"),
                    "fulfillment": fulfillment,
                    "current_commoditySku": commodity,
                    "suggested_pk": suggested,
                    "pk_exists_on_sellfox": suggested in existing_pk,
                    "already_on_pk": commodity == suggested,
                    "route_reasons": list(route.reasons),
                }
            )

    # Deduplicate by shop+msku
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        key = (str(c.get("shopId") or ""), str(c.get("msku") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    unique.sort(
        key=lambda r: (
            0 if r.get("onlineStatus") == "Active" else 1,
            0 if r.get("pk_exists_on_sellfox") else 1,
            str(r.get("suggested_pk") or ""),
            str(r.get("msku") or ""),
        )
    )

    # Also write xlsx if openpyxl available via pandas
    report = {
        "cache_dir": str(cache),
        "input_candidates": len(candidates),
        "unique_candidates": len(unique),
        "pk_exists": sum(1 for r in unique if r["pk_exists_on_sellfox"]),
        "already_on_pk": sum(1 for r in unique if r["already_on_pk"]),
        "active": sum(1 for r in unique if r.get("onlineStatus") == "Active"),
        "rows": unique,
    }
    if args.report:
        out = Path(args.report)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        xlsx = out.with_suffix(".xlsx")
        pd.DataFrame(unique).to_excel(xlsx, index=False)
        print(f"wrote {out}", flush=True)
        print(f"wrote {xlsx}", flush=True)
    print(
        json.dumps(
            {
                "unique_candidates": report["unique_candidates"],
                "pk_exists": report["pk_exists"],
                "already_on_pk": report["already_on_pk"],
                "active": report["active"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sellfox cover PK# combo ops")
    sub = p.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Build dry-run plan JSON")
    plan.add_argument("--env", default="prod", choices=["prod", "test"])
    plan.add_argument("--bom", default=str(DEFAULT_BOM_XLSX))
    plan.add_argument("--bom-meta", default=str(DEFAULT_BOM_META))
    plan.add_argument("--report", default=".codex_tmp/cover_combo_plan.json")
    plan.set_defaults(func=cmd_plan)

    apply = sub.add_parser("apply", help="Create missing PK# from plan")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--apply", action="store_true")
    apply.add_argument("--only", nargs="*", default=None)
    apply.add_argument("--allow-missing-cost", action="store_true")
    apply.add_argument("--batch-size", type=int, default=50)
    apply.add_argument("--until-done", action="store_true")
    apply.add_argument("--report", default=".codex_tmp/cover_combo_progress.json")
    apply.set_defaults(func=cmd_apply)

    status = sub.add_parser("status", help="Live PK# vs plan (read-only)")
    status.add_argument("--plan", default=".codex_tmp/cover_combo_plan.json")
    status.add_argument("--report", default=".codex_tmp/cover_combo_status.json")
    status.set_defaults(func=cmd_status)

    pair = sub.add_parser("pairing-candidates", help="Read-only pairing suggestions")
    pair.add_argument("--plan", default=".codex_tmp/cover_combo_plan.json")
    pair.add_argument("--report", default=".codex_tmp/cover_pairing_candidates.json")
    pair.set_defaults(func=cmd_pairing_candidates)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
