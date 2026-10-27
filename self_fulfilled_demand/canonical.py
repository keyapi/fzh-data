# -*- coding: utf-8 -*-
"""规范需求适配层：把旧 GS 历史与 EN 10 月增量统一到
``canonical sku × warehouse × uom``，供供应分桶（b08acc05）消费。

不变量
- SKU：`tongtool_sku → EN item_code` 来自既有 ``sku_map.tsv``；一对多**不**任取，
  标 ambiguous 并阻断净额；未映射保留 ``unmapped:<sku>`` 且阻断。
- 仓库：只合并有文档证据的旧名→新名；子仓/备用仓/未映射仓保持独立并写原因。
- UOM：复用/补建 ``EN Item.stock_uom`` 缓存；缺失或非「件类」单位 → 阻断净额，不猜。
- 需求形态：EN 行沿用 `demand_kind`；GS 行若有唯一 EN 行匹配则沿用其形态，
  否则保持 unknown 并保留原因（不按编码相似推断、不合并 Cover/成品）。
- 每一行输入都有去向：``demand_line_disposition`` 里能查到 canonical 键或阻断原因。

接口（与 b08acc05 约定）
- 主键：``demand_date × canonical_sku × canonical_warehouse × uom``；
- ``netting_allowed=false`` 的行（未知 SKU/仓库/UOM、unknown scope）不得直接净额相减；
- FBA 不出现在本表；3PL 保留，``in_default_series=false``，可按 scope 自行取舍。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Sequence

import pandas as pd

from . import config
from .consumer import build_demand
from .en_reader import EnReadOnlyClient
from .store import ParquetStore, now_iso

SKU_MAP_DEFAULT = "D:/Work/fzh-order-store/sku_map.tsv"
WAREHOUSE_ALIASES = Path(__file__).with_name("warehouse_aliases.json")
UOM_CACHE_DEFAULT = "D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet"

PIECE_UOMS = {"个", "件", "套", "对", "只", "条", "包", "Pcs", "PCS", "pcs", "Nos", "nos"}

FBA_PATTERN = re.compile(r"FBA", re.IGNORECASE)


def _sha256(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def load_sku_map(path: str | Path) -> pd.DataFrame:
    """tongtool_sku → item_codes。一对多不任取。"""
    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        dtype=str,
        quoting=3,
        keep_default_na=False,
        names=["item_code", "tongtool_sku", "customer_name"],
    )
    df["item_code"] = df["item_code"].astype(str).str.strip()
    df["tongtool_sku"] = df["tongtool_sku"].astype(str).str.strip()
    df = df[(df["item_code"] != "") & (df["tongtool_sku"] != "")]
    grouped = df.groupby("tongtool_sku")["item_code"].agg(lambda x: tuple(sorted(set(x))))
    out = grouped.reset_index(name="item_codes")
    out["n_items"] = out["item_codes"].map(len)
    out["mapping_status"] = out["n_items"].map(lambda n: "mapped" if n == 1 else "ambiguous")
    out["mapping_evidence"] = "sku_map.tsv: Item Customer Detail.ref_code → Item"
    return out


def load_warehouse_config(path: str | Path = WAREHOUSE_ALIASES) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_warehouse(name, cfg: dict) -> dict:
    raw = "" if name is None or (isinstance(name, float) and pd.isna(name)) else str(name).strip()
    if not raw:
        return {
            "canonical_warehouse": "<unknown>",
            "warehouse_status": "unknown",
            "warehouse_evidence": "warehouse empty",
            "warehouse_parent_candidate": None,
            "warehouse_merge_status": "unknown",
        }
    aliases = cfg.get("aliases", {})
    if raw in aliases:
        item = aliases[raw]
        return {
            "canonical_warehouse": item["canonical"],
            "warehouse_status": item["status"],
            "warehouse_evidence": item["evidence"],
            "warehouse_parent_candidate": None,
            "warehouse_merge_status": "alias_confirmed",
        }
    if raw in cfg.get("third_party", {}):
        return {
            "canonical_warehouse": raw,
            "warehouse_status": "third_party",
            "warehouse_evidence": cfg["third_party"][raw],
            "warehouse_parent_candidate": None,
            "warehouse_merge_status": "declared",
        }
    if FBA_PATTERN.search(raw):
        return {
            "canonical_warehouse": raw,
            "warehouse_status": "fba",
            "warehouse_evidence": "warehouse name contains FBA",
            "warehouse_parent_candidate": None,
            "warehouse_merge_status": "declared",
        }
    not_merged = cfg.get("not_merged", {})
    if raw in not_merged:
        item = not_merged[raw]
        return {
            "canonical_warehouse": raw,
            "warehouse_status": "declared",
            "warehouse_evidence": item["reason"],
            "warehouse_parent_candidate": item.get("parent_candidate"),
            "warehouse_merge_status": "not_merged_no_evidence",
        }
    if raw in cfg.get("declared", {}):
        return {
            "canonical_warehouse": raw,
            "warehouse_status": "declared",
            "warehouse_evidence": cfg["declared"][raw],
            "warehouse_parent_candidate": None,
            "warehouse_merge_status": "declared",
        }
    return {
        "canonical_warehouse": raw,
        "warehouse_status": "unknown",
        "warehouse_evidence": "not_in_alias_map",
        "warehouse_parent_candidate": None,
        "warehouse_merge_status": "unknown",
    }


def load_uom_cache(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["item_code", "stock_uom", "item_name", "is_stock_item", "fetched_at", "source"])
    return pd.read_parquet(p)


def ensure_uom_cache(
    client: EnReadOnlyClient | None,
    item_codes: Sequence[str],
    path: str | Path,
    *,
    max_items: int = 6000,
    batch_size: int = 50,
) -> pd.DataFrame:
    """有界补建 EN Item.stock_uom 缓存；只读、只查缺失的唯一物料。"""
    path = Path(path)
    codes = sorted({str(c).strip() for c in item_codes if str(c).strip()})
    if len(codes) > max_items:
        raise ValueError(f"待查物料 {len(codes)} 超过上限 {max_items}，拒绝无界查询")
    existing = load_uom_cache(path)
    known = set(existing["item_code"].astype(str)) if len(existing) else set()
    missing = [c for c in codes if c not in known]
    if missing and client is None:
        return existing
    rows = []
    if missing:
        for i in range(0, len(missing), batch_size):
            chunk = missing[i : i + batch_size]
            found = client.get_list(
                "Item",
                ["name", "stock_uom", "item_name", "is_stock_item"],
                filters=[["Item", "name", "in", chunk]],
                limit_page_length=0,
            )
            seen = {r["name"] for r in found}
            for r in found:
                rows.append(
                    {
                        "item_code": r["name"],
                        "stock_uom": r.get("stock_uom"),
                        "item_name": r.get("item_name"),
                        "is_stock_item": r.get("is_stock_item"),
                        "fetched_at": now_iso(),
                        "source": "EN Item.stock_uom",
                    }
                )
            for code in chunk:
                if code not in seen:
                    rows.append(
                        {
                            "item_code": code,
                            "stock_uom": None,
                            "item_name": None,
                            "is_stock_item": None,
                            "fetched_at": now_iso(),
                            "source": "EN Item not found",
                        }
                    )
        new_df = pd.DataFrame(rows)
        combined = pd.concat([existing, new_df], ignore_index=True) if len(existing) else new_df
        combined = combined.drop_duplicates(subset=["item_code"], keep="last")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        combined.to_parquet(tmp, index=False)
        tmp.replace(path)
        return combined
    return existing


def en_kind_lookup(store_or_root: ParquetStore | str | Path) -> pd.Series:
    """(en_doc_name, tongtool_sku) → 唯一非 unknown 的 demand_kind 集合。

    传 ParquetStore 时沿用调用方已固定的快照，避免与需求读取跨提交。
    """
    store = store_or_root if isinstance(store_or_root, ParquetStore) else ParquetStore(store_or_root)
    with store.pinned():
        lines = store.load_lines()
    if not len(lines):
        return pd.Series(dtype=object)
    grouped = lines.groupby(["en_doc_name", "tongtool_sku"], dropna=False)["demand_kind"].agg(
        lambda x: frozenset(k for k in set(x) if k and k != config.DSHIP_UNKNOWN)
    )
    return grouped


def snapshot_identity(store: ParquetStore) -> dict:
    """记录本次构建读取的 EN 快照身份与 orders/lines 文件哈希。

    快照身份从**固定目录**里的 commit.json 读取，而不是再看 CURRENT，
    否则构建期间发生提交会把 A 的数据标成 B 的身份。
    """
    with store.pinned():
        paths = store.current_files()
        directory = paths["orders"].parent
        marker_path = directory / "commit.json"
        if marker_path.exists():
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            commit_id = marker.get("commit_id")
            status = marker.get("status")
            committed_at = marker.get("committed_at")
        else:
            current = store.read_current()
            commit_id = current.get("commit_id")
            status = current.get("status")
            committed_at = current.get("committed_at")
        identity = {
            "commit_id": commit_id,
            "status": status,
            "committed_at": committed_at,
            "orders_path": str(paths["orders"]),
            "lines_path": str(paths["lines"]),
            "orders_sha256": _sha256(paths["orders"]),
            "lines_sha256": _sha256(paths["lines"]),
            "orders_rows": int(len(store.load_orders())),
            "lines_rows": int(len(store.load_lines())),
        }
    return identity


def _uom_status(uom, item_found: bool) -> tuple[str, str]:
    if not item_found:
        return "missing", "EN Item not found"
    value = None if uom is None or (isinstance(uom, float) and pd.isna(uom)) else str(uom).strip()
    if not value:
        return "missing", "EN Item.stock_uom empty"
    if value in PIECE_UOMS:
        return "known_piece", f"EN Item.stock_uom={value}"
    return "not_piece", f"EN Item.stock_uom={value} (非件类单位，数量口径可能不一致)"


def canonicalize(
    demand: pd.DataFrame,
    sku_map: pd.DataFrame,
    uom_cache: pd.DataFrame,
    warehouse_cfg: dict,
    kind_lookup: pd.Series | None = None,
) -> pd.DataFrame:
    """给每一行需求补 canonical sku/warehouse/uom 与净额资格。"""
    df = demand.copy()
    df["tongtool_sku"] = df["tongtool_sku"].astype("string").str.strip()

    df = df.merge(sku_map, on="tongtool_sku", how="left")
    df["n_items"] = pd.to_numeric(df["n_items"], errors="coerce")
    df["mapping_status"] = df["mapping_status"].fillna("unmapped")
    mapped_item = df["item_codes"].map(
        lambda v: v[0] if isinstance(v, tuple) and len(v) == 1 else None
    )
    df["item_code"] = mapped_item
    df["canonical_sku"] = mapped_item
    df.loc[df["mapping_status"] == "ambiguous", "canonical_sku"] = (
        "ambiguous:" + df["tongtool_sku"].astype(str)
    )
    df.loc[df["mapping_status"] == "unmapped", "canonical_sku"] = (
        "unmapped:" + df["tongtool_sku"].astype(str)
    )

    uom = uom_cache.copy()
    if len(uom):
        uom = uom[["item_code", "stock_uom"]].drop_duplicates(subset=["item_code"], keep="last")
        df = df.merge(uom, on="item_code", how="left")
    else:
        df["stock_uom"] = None
    found = df["item_code"].notna()
    status_pairs = [
        _uom_status(u, bool(f)) for u, f in zip(df["stock_uom"], found)
    ]
    df["uom_status"] = [p[0] for p in status_pairs]
    df["uom_evidence"] = [p[1] for p in status_pairs]
    df["uom"] = [
        (str(u) if pd.notna(u) and str(u).strip() else None) if st == "known_piece" else None
        for u, st in zip(df["stock_uom"], df["uom_status"])
    ]

    wh_rows = [resolve_warehouse(w, warehouse_cfg) for w in df["warehouse_name"]]
    for key in (
        "canonical_warehouse",
        "warehouse_status",
        "warehouse_evidence",
        "warehouse_parent_candidate",
        "warehouse_merge_status",
    ):
        df[key] = [r[key] for r in wh_rows]

    # GS 历史：有唯一 EN 行匹配时沿用其发货形态；冲突/缺失保持 unknown
    if "demand_kind_basis" not in df.columns:
        df["demand_kind_basis"] = "as_recorded"
    if kind_lookup is not None and len(kind_lookup):
        idx = pd.MultiIndex.from_frame(df[["order_key", "tongtool_sku"]])
        candidates = idx.map(kind_lookup)
        gs_mask = df["source"].astype("string").eq("gs_legacy")
        for pos, (is_gs, cands, current) in enumerate(
            zip(gs_mask, candidates, df["demand_kind"])
        ):
            if not is_gs:
                continue
            if isinstance(cands, frozenset) and len(cands) == 1:
                df.iat[pos, df.columns.get_loc("demand_kind")] = next(iter(cands))
                df.iat[pos, df.columns.get_loc("demand_kind_basis")] = "en_line_match"
            elif isinstance(cands, frozenset) and len(cands) > 1:
                df.iat[pos, df.columns.get_loc("demand_kind_basis")] = "en_line_conflict"
    df["demand_kind_status"] = df["demand_kind"].map(
        lambda k: "known"
        if (not pd.isna(k) and str(k).strip() and str(k) != config.DSHIP_UNKNOWN)
        else "unknown"
    )

    reason_masks = [
        ("sku_mapping_ambiguous", df["mapping_status"].eq("ambiguous")),
        ("sku_mapping_missing", df["mapping_status"].eq("unmapped")),
        ("uom_missing", df["uom_status"].eq("missing")),
        ("uom_not_piece", df["uom_status"].eq("not_piece")),
        ("warehouse_identity_unknown", df["warehouse_status"].eq("unknown")),
        ("subwarehouse_identity_unproven", df["warehouse_merge_status"].eq("not_merged_no_evidence")),
        ("scope_unknown", df["fulfillment_scope"].eq(config.SCOPE_UNKNOWN)),
        (
            "quantity_invalid",
            pd.to_numeric(df["quantity"], errors="coerce").isna()
            | pd.to_numeric(df["quantity"], errors="coerce").le(0),
        ),
    ]
    blocked_any = pd.Series(False, index=df.index)
    for _, mask in reason_masks:
        blocked_any = blocked_any | mask
    reason_df = pd.DataFrame({name: mask for name, mask in reason_masks}, index=df.index)
    df["netting_block_reason"] = ""
    if blocked_any.any():
        df.loc[blocked_any, "netting_block_reason"] = reason_df[blocked_any].apply(
            lambda row: ";".join([c for c in reason_df.columns if bool(row[c])]), axis=1
        )
    df["netting_block_primary"] = ""
    primary = pd.Series("", index=df.index, dtype="object")
    for reason, mask in reason_masks:
        primary = primary.mask(mask & primary.eq(""), reason)
    df["netting_block_primary"] = primary
    df["netting_allowed"] = ~blocked_any
    df["in_default_series"] = df["fulfillment_scope"].eq(config.SCOPE_SELF)
    return df


NETTING_KEY = ["demand_date", "canonical_sku", "canonical_warehouse", "canonical_uom"]


def _mix(values) -> str:
    return ",".join(sorted({str(v) for v in values if v is not None and not pd.isna(v)}))


def build_netting_views(disp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把行级去向拆成「四列唯一可净额表」与「阻断账」。

    - 可净额表只汇总 ``netting_allowed=true`` 的行；四列键唯一，先过滤资格再聚合，
      不任取任何一行资格，也不会把同一份供应重复扣减。
    - 阻断账保留每条原因组合与数量，单独建账，不与可净额量混在一起。
    """
    allowed = disp[disp["netting_allowed"]].copy()
    allowed["qty_default"] = allowed["quantity"].where(allowed["in_default_series"], 0)
    allowed["qty_third_party"] = allowed["quantity"].where(
        allowed["fulfillment_scope"].eq(config.SCOPE_THIRD_PARTY), 0
    )
    netting = (
        allowed.groupby(NETTING_KEY, dropna=False)
        .agg(
            quantity=("quantity", "sum"),
            quantity_default=("qty_default", "sum"),
            quantity_third_party=("qty_third_party", "sum"),
            order_count=("order_key", "nunique"),
            line_count=("order_key", "count"),
            demand_kind_mix=("demand_kind", _mix),
            scope_mix=("fulfillment_scope", _mix),
            source_mix=("source", _mix),
            coverage_status_mix=("coverage_status", _mix),
        )
        .reset_index()
    )
    netting["netting_allowed"] = True
    netting["in_default_series"] = netting["quantity_default"].gt(0)

    blocked_rows = disp[~disp["netting_allowed"]].copy()
    blocked = (
        blocked_rows.groupby(
            NETTING_KEY + ["netting_block_primary", "netting_block_reason"], dropna=False
        )
        .agg(
            quantity=("quantity", "sum"),
            order_count=("order_key", "nunique"),
            line_count=("order_key", "count"),
        )
        .reset_index()
    )
    blocked["netting_allowed"] = False
    return netting, blocked


def supply_targets(netting: pd.DataFrame) -> pd.DataFrame:
    """供应适配器入口：只接受已过滤且 sku/仓/uom 均非 <unknown> 的净额目标。"""
    out = netting[
        netting["canonical_uom"].astype("string").fillna("<unknown>").ne("<unknown>")
        & netting["canonical_warehouse"].astype("string").fillna("<unknown>").ne("<unknown>")
        & pd.to_numeric(netting["quantity"], errors="coerce").gt(0)
    ].copy()
    cols = NETTING_KEY + [
        "quantity",
        "quantity_default",
        "quantity_third_party",
        "order_count",
        "demand_kind_mix",
        "scope_mix",
    ]
    return out[cols].reset_index(drop=True)


def _coverage(disp: pd.DataFrame, input_rows: int, input_qty: float) -> pd.DataFrame:
    rows = []
    for sku, grp in disp.groupby("tongtool_sku", dropna=False):
        ready = grp[grp["netting_allowed"]]
        blocked = grp[~grp["netting_allowed"]]
        rows.append(
            {
                "tongtool_sku": sku,
                "demand_rows": int(len(grp)),
                "demand_qty": float(pd.to_numeric(grp["quantity"], errors="coerce").sum()),
                "mapping_status": grp["mapping_status"].iloc[0],
                "item_codes": ",".join(grp["item_codes"].dropna().map(lambda x: "|".join(x)).unique())
                if grp["item_codes"].notna().any()
                else None,
                "canonical_sku": grp["canonical_sku"].iloc[0],
                "uom_status": grp["uom_status"].iloc[0],
                "uom": grp["uom"].iloc[0],
                "canonical_warehouses": int(grp["canonical_warehouse"].nunique()),
                "ready_rows": int(len(ready)),
                "ready_qty": float(pd.to_numeric(ready["quantity"], errors="coerce").sum()),
                "blocked_rows": int(len(blocked)),
                "blocked_qty": float(pd.to_numeric(blocked["quantity"], errors="coerce").sum()),
                "block_reasons": ",".join(sorted(set(blocked["netting_block_reason"]))),
            }
        )
    out = pd.DataFrame(rows)
    total = pd.DataFrame(
        [
            {
                "tongtool_sku": "__TOTAL__",
                "demand_rows": input_rows,
                "demand_qty": input_qty,
                "mapping_status": None,
                "item_codes": None,
                "canonical_sku": None,
                "uom_status": None,
                "uom": None,
                "canonical_warehouses": None,
                "ready_rows": int(disp["netting_allowed"].sum()),
                "ready_qty": float(pd.to_numeric(disp.loc[disp["netting_allowed"], "quantity"], errors="coerce").sum()),
                "blocked_rows": int((~disp["netting_allowed"]).sum()),
                "blocked_qty": float(pd.to_numeric(disp.loc[~disp["netting_allowed"], "quantity"], errors="coerce").sum()),
                "block_reasons": ",".join(sorted(set(disp.loc[~disp["netting_allowed"], "netting_block_reason"]))),
            }
        ]
    )
    return pd.concat([out, total], ignore_index=True)


def _ambiguities(disp: pd.DataFrame, sku_map: pd.DataFrame, warehouse_cfg: dict) -> pd.DataFrame:
    rows: list[dict] = []

    def add(kind: str, key: str, candidates, evidence: str, grp: pd.DataFrame | None):
        rows.append(
            {
                "ambiguity_type": kind,
                "key": key,
                "candidates": candidates,
                "evidence": evidence,
                "demand_rows": int(len(grp)) if grp is not None else 0,
                "demand_qty": float(pd.to_numeric(grp["quantity"], errors="coerce").sum()) if grp is not None else 0.0,
            }
        )

    ambiguous_skus = sku_map[sku_map["mapping_status"] == "ambiguous"]
    for row in ambiguous_skus.itertuples():
        grp = disp[disp["tongtool_sku"] == row.tongtool_sku]
        if len(grp):
            add("sku_mapping_ambiguous", row.tongtool_sku, "|".join(row.item_codes), row.mapping_evidence, grp)

    unmapped = disp[disp["mapping_status"] == "unmapped"]
    for sku, grp in unmapped.groupby("tongtool_sku", dropna=False):
        add("sku_mapping_missing", str(sku), None, "sku_map.tsv 无该通途SKU", grp)

    for wh, grp in disp.groupby("warehouse_name", dropna=False):
        status = grp["warehouse_status"].iloc[0]
        if status == "unknown":
            add("warehouse_identity_unknown", str(wh), None, grp["warehouse_evidence"].iloc[0], grp)
        elif grp["warehouse_merge_status"].iloc[0] == "not_merged_no_evidence":
            add(
                "warehouse_not_merged",
                str(wh),
                grp["warehouse_parent_candidate"].iloc[0],
                grp["warehouse_evidence"].iloc[0],
                grp,
            )

    for detail, grp in disp[disp["uom_status"] != "known_piece"].groupby("uom_status", dropna=False):
        add(f"uom_{detail}", str(detail), None, grp["uom_evidence"].iloc[0], grp)

    unknown_kind = disp[disp["demand_kind_status"] == "unknown"]
    if len(unknown_kind):
        add(
            "demand_kind_unknown",
            "__all__",
            None,
            "GS 历史无发货形态，且无唯一 EN 行可沿用",
            unknown_kind,
        )
    conflict_kind = disp[disp["demand_kind_basis"] == "en_line_conflict"]
    if len(conflict_kind):
        add("demand_kind_conflict", "__all__", None, "同一订单+SKU 在 EN 有多条不同发货形态", conflict_kind)

    return pd.DataFrame(rows)


def _write_cases(path: Path, disp: pd.DataFrame) -> None:
    picks = []

    def pick(label: str, mask):
        sub = disp[mask]
        if len(sub):
            row = sub.iloc[0]
            picks.append((label, row))

    pick("旧名→新名仓库合并", disp["warehouse_merge_status"].eq("alias_confirmed"))
    pick("子仓未合并（保留独立规范仓）", disp["warehouse_merge_status"].eq("not_merged_no_evidence"))
    pick("EN 行匹配推断 GS 发货形态", disp["demand_kind_basis"].eq("en_line_match"))
    pick("SKU 未映射（阻断净额）", disp["mapping_status"].eq("unmapped"))
    pick("UOM 非件类（阻断净额）", disp["uom_status"].eq("not_piece"))
    pick("第三方代发需求保留（默认口径外）", disp["fulfillment_scope"].eq(config.SCOPE_THIRD_PARTY))
    pick("可净额的自发货行", disp["netting_allowed"].eq(True) & disp["in_default_series"].eq(True))

    lines = ["---", "okf: v0.1", "type: Reference", "title: 规范需求真实样例", "description: 从本次数据中自动抽取的可解释案例", "tags: [canonical, demand, cases]", "date: 2026-10-27", "---", "", "# 规范需求真实样例", ""]
    if not picks:
        lines.append("（本次数据没有命中样例）")
    for label, r in picks:
        uom_text = "<unknown>" if pd.isna(r["uom"]) else r["uom"]
        lines += [
            f"## {label}",
            "",
            f"- 输入：`{r['order_key']}` / `{r['tongtool_sku']}` / 仓库 `{r['warehouse_name']}` / 日期 `{r['sale_date']}`",
            f"- 输出：canonical_sku=`{r['canonical_sku']}`，canonical_warehouse=`{r['canonical_warehouse']}`，uom=`{uom_text}`",
            f"- 映射：{r['mapping_status']}；UOM：{r['uom_status']}（{r['uom_evidence']}）；仓库：{r['warehouse_status']}",
            f"- 发货形态：`{r['demand_kind']}`（{r['demand_kind_basis']}）",
            f"- 净额资格：`{bool(r['netting_allowed'])}`"
            + (f"，原因：`{r['netting_block_reason']}`" if not r["netting_allowed"] else ""),
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_canonical(
    store_root: str | Path,
    gs_path: str | Path,
    start: str,
    end: str,
    out_dir: str | Path,
    *,
    sku_map_path: str | Path = SKU_MAP_DEFAULT,
    warehouse_config_path: str | Path = WAREHOUSE_ALIASES,
    uom_cache_path: str | Path = UOM_CACHE_DEFAULT,
    client: EnReadOnlyClient | None = None,
    fetch_uom: bool = True,
    max_uom_items: int = 6000,
) -> dict:
    store = ParquetStore(store_root)
    # 整次构建固定同一个 EN 快照：需求读取、GS 形态补证、快照身份都来自同一 commit
    with store.pinned():
        frames = build_demand(
            store_root,
            gs_path,
            start,
            end,
            scopes=(config.SCOPE_SELF, config.SCOPE_THIRD_PARTY),
            store=store,
        )
        demand = frames["demand_non_fba"].copy()
        kind_lookup = en_kind_lookup(store)
        en_snapshot = snapshot_identity(store)
    sku_map = load_sku_map(sku_map_path)
    wh_cfg = load_warehouse_config(warehouse_config_path)

    sku_index = sku_map.set_index("tongtool_sku")["item_codes"]
    mapped_codes = demand["tongtool_sku"].map(sku_index)
    codes = [
        v[0] for v in mapped_codes if isinstance(v, tuple) and len(v) == 1
    ]
    if fetch_uom and client is not None:
        uom_cache = ensure_uom_cache(client, codes, uom_cache_path, max_items=max_uom_items)
    else:
        uom_cache = load_uom_cache(uom_cache_path)

    disp = canonicalize(demand, sku_map, uom_cache, wh_cfg, kind_lookup)
    disp["demand_date"] = disp["sale_date"]
    disp["canonical_uom"] = disp["uom"].fillna("<unknown>")
    disp["canonical_warehouse"] = disp["canonical_warehouse"].fillna("<unknown>")

    key_cols = [
        "demand_date",
        "canonical_sku",
        "canonical_warehouse",
        "canonical_uom",
        "demand_kind",
        "fulfillment_scope",
        "source",
        "coverage_status",
        "netting_allowed",
        "netting_block_reason",
        "demand_kind_status",
        "warehouse_status",
        "uom_status",
    ]
    agg = (
        disp.groupby(key_cols, dropna=False)
        .agg(
            quantity=("quantity", "sum"),
            order_count=("order_key", "nunique"),
            line_count=("order_key", "count"),
        )
        .reset_index()
    )
    agg["in_default_series"] = agg["fulfillment_scope"].eq(config.SCOPE_SELF)

    netting, blocked_ledger = build_netting_views(disp)
    four_key_duplicates = int(netting.duplicated(NETTING_KEY).sum())
    subwarehouse_rows = disp[disp["warehouse_merge_status"].eq("not_merged_no_evidence")]
    subwarehouse_blocked = subwarehouse_rows[~subwarehouse_rows["netting_allowed"]]

    coverage = _coverage(disp, int(len(disp)), float(pd.to_numeric(disp["quantity"], errors="coerce").sum()))
    ambiguities = _ambiguities(disp, sku_map, wh_cfg)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    disp.to_parquet(out / "demand_line_disposition.parquet", index=False, compression="zstd")
    agg.to_parquet(out / "demand_canonical.parquet", index=False, compression="zstd")
    netting.to_parquet(out / "demand_netting.parquet", index=False, compression="zstd")
    blocked_ledger.to_parquet(out / "demand_blocked.parquet", index=False, compression="zstd")
    coverage.to_parquet(out / "sku_coverage.parquet", index=False, compression="zstd")
    ambiguities.to_parquet(out / "ambiguity_list.parquet", index=False, compression="zstd")
    _write_cases(out / "cases.md", disp)

    manifest = {
        "schema": "canonical-demand-v1",
        "generated_at": now_iso(),
        "window": {"start": start, "end": end},
        "interface": {
            "consumer": "supply bucketing b08acc05",
            "primary_dataset": "demand_netting.parquet",
            "primary_key": NETTING_KEY,
            "primary_key_unique": four_key_duplicates == 0,
            "detailed_dataset": "demand_canonical.parquet",
            "detailed_note": "13 列明细聚合（含 demand_kind/source/scope/资格）；四列键不唯一，禁止 upsert/按行连接供应",
            "blocked_dataset": "demand_blocked.parquet",
            "filter_rule": "只消费 demand_netting；它已过滤 netting_allowed=true。默认自发货再筛 in_default_series=true；3PL 保留但 default=false；阻断量只在 demand_blocked。",
            "unknown_rule": "canonical_uom/canonical_warehouse 的 <unknown> 不得进入供应目标",
            "fba": "excluded from demand",
            "third_party": "retained; in_default_series=false",
        },
        "sources": {
            "sku_map": {"path": str(sku_map_path), "sha256": _sha256(sku_map_path), "rows": int(len(sku_map))},
            "warehouse_aliases": {
                "path": str(warehouse_config_path),
                "sha256": _sha256(warehouse_config_path),
                "version": wh_cfg.get("version"),
            },
            "uom_cache": {
                "path": str(uom_cache_path),
                "sha256": _sha256(uom_cache_path),
                "rows": int(len(uom_cache)),
            },
            "gs_orders": {"path": str(gs_path), "sha256": _sha256(gs_path)},
            "en_snapshot": en_snapshot,
        },
        "counts": {
            "input_rows": int(len(disp)),
            "input_qty": float(pd.to_numeric(disp["quantity"], errors="coerce").sum()),
            "canonical_rows": int(len(agg)),
            "canonical_qty": float(agg["quantity"].sum()),
            "netting_rows": int(len(netting)),
            "netting_qty": float(netting["quantity"].sum()),
            "blocked_ledger_rows": int(len(blocked_ledger)),
            "blocked_ledger_qty": float(blocked_ledger["quantity"].sum()),
            "four_key_duplicates_in_netting": four_key_duplicates,
            "subwarehouse_rows": int(len(subwarehouse_rows)),
            "subwarehouse_qty": float(pd.to_numeric(subwarehouse_rows["quantity"], errors="coerce").sum()),
            "subwarehouse_blocked_rows": int(len(subwarehouse_blocked)),
            "subwarehouse_blocked_qty": float(
                pd.to_numeric(subwarehouse_blocked["quantity"], errors="coerce").sum()
            ),
            "ready_rows": int(disp["netting_allowed"].sum()),
            "ready_qty": float(pd.to_numeric(disp.loc[disp["netting_allowed"], "quantity"], errors="coerce").sum()),
            "blocked_rows": int((~disp["netting_allowed"]).sum()),
            "blocked_qty": float(pd.to_numeric(disp.loc[~disp["netting_allowed"], "quantity"], errors="coerce").sum()),
            "fba_rows_excluded": int(len(frames["fba"])),
            "third_party_rows": int((disp["fulfillment_scope"] == config.SCOPE_THIRD_PARTY).sum()),
            "unknown_scope_rows": int((disp["fulfillment_scope"] == config.SCOPE_UNKNOWN).sum()),
            "unique_skus": int(disp["tongtool_sku"].nunique()),
            "unique_items": int(disp["item_code"].nunique()),
            "unique_warehouses": int(disp["canonical_warehouse"].nunique()),
            "kind_basis_counts": disp["demand_kind_basis"].value_counts().to_dict(),
            "netting_by_scope": {
                "self_allowed": int(
                    (disp["netting_allowed"] & disp["fulfillment_scope"].eq(config.SCOPE_SELF)).sum()
                ),
                "self_blocked": int(
                    (~disp["netting_allowed"] & disp["fulfillment_scope"].eq(config.SCOPE_SELF)).sum()
                ),
                "third_party_allowed": int(
                    (disp["netting_allowed"] & disp["fulfillment_scope"].eq(config.SCOPE_THIRD_PARTY)).sum()
                ),
                "unknown_scope_blocked": int(
                    (~disp["netting_allowed"] & disp["fulfillment_scope"].eq(config.SCOPE_UNKNOWN)).sum()
                ),
            },
            "alias_merge_rows": disp.loc[
                disp["warehouse_merge_status"].eq("alias_confirmed"), "warehouse_name"
            ].value_counts().to_dict(),
        },
        "block_reasons": disp.loc[~disp["netting_allowed"], "netting_block_reason"]
        .value_counts()
        .to_dict(),
        "ambiguity_counts": ambiguities["ambiguity_type"].value_counts().to_dict() if len(ambiguities) else {},
        "notes": [
            "UOM 为 EN Item.stock_uom 证据；非件类单位阻断净额，缺失保持 null。",
            "仓库只按有证据的旧名→新名合并；5 类子仓未证身份，保留原行但阻断净额。",
            "demand_canonical 是明细聚合；净额请用四列唯一的 demand_netting。",
            "整次构建固定同一 EN 快照，manifest 记录 commit_id 与 orders/lines 哈希。",
            "SKU 一对多不任取；未映射保留 unmapped:<sku>。",
            "GS 历史发货形态仅在唯一 EN 行匹配时沿用。",
        ],
    }
    (out / "identity_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="规范需求适配层（canonical sku×warehouse×uom）")
    ap.add_argument("--store", default="D:/Work/fzh-order-store/en-demand-v1")
    ap.add_argument("--gs-path", default="D:/Work/fzh-order-store/gs_orders.parquet")
    ap.add_argument("--start", default="2022-12-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/canonical")
    ap.add_argument("--sku-map", default=SKU_MAP_DEFAULT)
    ap.add_argument("--warehouse-aliases", default=str(WAREHOUSE_ALIASES))
    ap.add_argument("--uom-cache", default=UOM_CACHE_DEFAULT)
    ap.add_argument("--max-uom-items", type=int, default=6000)
    ap.add_argument("--no-fetch-uom", action="store_true")
    args = ap.parse_args(argv)

    client = None
    if not args.no_fetch_uom:
        client = EnReadOnlyClient(min_interval=0.15)
    manifest = build_canonical(
        args.store,
        args.gs_path,
        args.start,
        args.end,
        args.out,
        sku_map_path=args.sku_map,
        warehouse_config_path=args.warehouse_aliases,
        uom_cache_path=args.uom_cache,
        client=client,
        fetch_uom=not args.no_fetch_uom,
        max_uom_items=args.max_uom_items,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
