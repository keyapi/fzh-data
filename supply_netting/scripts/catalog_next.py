# -*- coding: utf-8 -*-
"""目录覆盖的后续动作（FULL-CATALOG-NEXT）：四类未覆盖 → 动作/责任角色 + 64 项优先清单。

输入（只读）：`catalog-coverage-2026-10-28/`（`uncovered_items.csv` + `catalog_coverage_summary.json`）
+ EN `Item.stock_uom` 快照（只用来看「UOM 未证」到底是 EN 缺数据还是本层缓存没覆盖）。

输出（写进 `--out`）：
- ``coverage_actions.csv``：每类未覆盖的后续动作、责任角色、优先级、预期效果
- ``uom_unproven_priority.csv``：64 个「有库存但 UOM 未证」物料的优先清单
- ``report.md`` / ``manifest.json``

口径（不得违反）
----------------
- **4,014 个决策键不是公司全目录**：只覆盖 1,627 个 EN 物料（目录 6,573）。
- **未覆盖 ≠ 零需求**：有库存/有映射的必须单列，不能当 0 处理。
- 只读：不改净额、决策包、主表；不替业务裁定皮壳/内胆是否可售；不 push。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

REASONS = ("stock_without_uom_evidence", "unmapped_no_evidence",
           "mapped_no_stock_no_sales", "component_or_cover")

ROLE_SUPPLY = "供应链数据层（本层/Agent）"
ROLE_EN = "EN 主数据"
ROLE_OPS = "运营（通途配对）"
ROLE_BIZ = "业务（SKU 生命周期）"

ACTIONS = {
    "stock_without_uom_evidence": dict(
        action="补单位：刷新 EN stock_uom 缓存 → 重跑净额", priority="P0",
        owner=ROLE_SUPPLY, confirm_with=ROLE_EN,
        detail=("这 64 项在 EN 里都有 stock_uom（本次实查 64/64 = 个），缺口只在本层 UOM 缓存："
                "缓存 1,627 条是按决策键建的，没覆盖「有库存但没进包」的物料。"),
        expected=("刷新后 63 条可进入库存侧事实（有货不再被当成没有）；"
                  "1 条 EN disabled=1 转停售确认；补单位不自动带来需求证据"),
        guardrail="不得因为没有需求预测就删掉这 1,324 件库存"),
    "unmapped_no_evidence": dict(
        action="补映射：通途侧确认停用/在售；在售则建配对", priority="P1",
        owner=ROLE_OPS, confirm_with=ROLE_BIZ,
        detail="无通途码、无库存、无历史销量（761 项）。多数是老目录/开发期物料，需在通途侧确认状态。",
        expected="确认在售的补通途↔EN 配对（missing-products 流程）；停用的落停售标记",
        guardrail="不凭名称相似硬绑低置信映射；未知保留原因"),
    "mapped_no_stock_no_sales": dict(
        action="停售确认：业务标记停售/清仓，或在售则补订货与销量证据", priority="P1",
        owner=ROLE_BIZ, confirm_with=ROLE_OPS,
        detail="有通途映射但 12 个月无库存、无销量（284 项）；可能是已下架或仅样品。",
        expected="确认停售 → 目录噪声减少；确认在售 → 补订货/销售证据后才会进需求覆盖",
        guardrail="不把「无销量」直接写成「零需求」；停售要有业务标记"),
    "component_or_cover": dict(
        action="口径确认：组件/皮壳不建独立可售 SKU（维持 PK#→KS 1:1、ND# 不计独立可售）",
        priority="P2", owner=ROLE_BIZ, confirm_with=ROLE_SUPPLY,
        detail=("3,840 项是 ND# 内胆 / PK# 皮壳（2,988 皮壳 + 852 内胆），按 UOM-CANONICAL "
                "不是独立可售成品；是否按组件在渠道售卖属业务口径。"),
        expected="维持现状即不计需求；若业务要按组件售卖，另开 SKU 生命周期任务，不在此层建",
        guardrail="本层不替业务裁定；也不为凑覆盖率硬建成品 SKU"),
}


class InputError(ValueError):
    """输入不合约（缺列/未知原因/数量对不上）—— 直接失败，不猜。"""


def load_uncovered(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype={"item": str})
    required = {"item", "role", "group", "name", "mapped_tt_count", "stock_qty",
                "stock_warehouses", "sales_total", "sales_recent6", "reason"}
    missing = required - set(frame.columns)
    if missing:
        raise InputError(f"uncovered_items.csv 缺列：{sorted(missing)}")
    unknown = set(frame["reason"]) - set(REASONS)
    if unknown:
        raise InputError(f"出现未定义的未覆盖原因（先补 ACTIONS 再跑）：{sorted(unknown)}")
    return frame


def load_summary(path: str | Path) -> dict:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("keys_in_pack", "items_in_pack", "catalog_items", "catalog_uncovered",
                "stock_uncovered", "stock_uncovered_qty", "reasons"):
        if key not in summary:
            raise InputError(f"summary 缺字段：{key}")
    return summary


def coverage_actions(uncovered: pd.DataFrame, summary: dict) -> pd.DataFrame:
    """每类未覆盖一行：数量与库存来自明细，动作/角色来自 ACTIONS。"""
    rows = []
    for reason in REASONS:
        part = uncovered[uncovered["reason"] == reason]
        meta = ACTIONS[reason]
        rows.append(dict(
            reason=reason, items=int(len(part)),
            stock_items=int((pd.to_numeric(part["stock_qty"], errors="coerce").fillna(0) > 0).sum()),
            stock_qty=round(float(pd.to_numeric(part["stock_qty"], errors="coerce").fillna(0).sum()), 3),
            reported_items=int(summary["reasons"].get(reason, 0)),
            priority=meta["priority"], action=meta["action"], owner=meta["owner"],
            confirm_with=meta["confirm_with"], evidence=meta["detail"],
            expected_effect=meta["expected"], guardrail=meta["guardrail"],
        ))
    frame = pd.DataFrame(rows)
    if int(frame["items"].sum()) != int(summary["catalog_uncovered"]):
        raise InputError("动作表合计 != 未覆盖总数："
                         f"{int(frame['items'].sum())} vs {summary['catalog_uncovered']}")
    if int(frame["stock_items"].sum()) != int(summary["stock_uncovered"]):
        raise InputError("有库存条目合计 != summary.stock_uncovered："
                         f"{int(frame['stock_items'].sum())} vs {summary['stock_uncovered']}")
    return frame.sort_values(["priority", "items"], ascending=[True, False]).reset_index(drop=True)


def uom_priority(uncovered: pd.DataFrame, en_items: dict[str, dict],
                 cache_items: set[str]) -> pd.DataFrame:
    """64 个有库存但 UOM 未证的物料：按库存降序，标 EN 单位/停用/缓存状态与动作。"""
    part = uncovered[uncovered["reason"] == "stock_without_uom_evidence"].copy()
    part["stock_qty"] = pd.to_numeric(part["stock_qty"], errors="coerce").fillna(0.0)
    rows = []
    for row in part.to_dict("records"):
        en = en_items.get(row["item"]) or {}
        uom = en.get("stock_uom")
        disabled = en.get("disabled")
        in_cache = row["item"] in cache_items
        if in_cache:
            action, why = "已在缓存（重跑即可）", "cache_hit"
        elif uom:
            action = "刷新 UOM 缓存 → 重跑净额"
            why = "en_has_uom_cache_missing"
        else:
            action, why = "EN 主数据补 stock_uom", "en_uom_missing"
        if disabled in (1, True, "1"):
            action = "停售确认（EN disabled=1）"
            why = "en_item_disabled"
        rows.append(dict(
            item=row["item"], item_name=row["name"], item_group=row["group"],
            stock_qty=row["stock_qty"], stock_warehouses=row.get("stock_warehouses") or "",
            mapped_tt_count=int(row.get("mapped_tt_count") or 0),
            sales_total=float(row.get("sales_total") or 0.0),
            sales_recent6=float(row.get("sales_recent6") or 0.0),
            en_stock_uom=uom, en_disabled=disabled, in_uom_cache=in_cache,
            status=why, action=action,
        ))
    frame = pd.DataFrame(rows).sort_values("stock_qty", ascending=False).reset_index(drop=True)
    frame.insert(0, "rank", range(1, len(frame) + 1))
    frame["cum_stock_qty"] = frame["stock_qty"].cumsum().round(3)
    return frame


def build(uncovered_path: str | Path, summary_path: str | Path, en_items_path: str | Path,
          uom_cache_path: str | Path, out: str | Path) -> dict:
    uncovered = load_uncovered(uncovered_path)
    summary = load_summary(summary_path)
    en_items = json.loads(Path(en_items_path).read_text(encoding="utf-8"))
    cache = pd.read_parquet(uom_cache_path, columns=["item_code"])
    cache_items = set(cache["item_code"].astype(str))

    actions = coverage_actions(uncovered, summary)
    priority = uom_priority(uncovered, en_items, cache_items)
    if round(float(priority["stock_qty"].sum()), 3) != round(float(summary["stock_uncovered_qty"]), 3):
        raise InputError("优先清单库存合计 != summary.stock_uncovered_qty")

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    actions.to_csv(out_dir / "coverage_actions.csv", index=False, encoding="utf-8-sig")
    priority.to_csv(out_dir / "uom_unproven_priority.csv", index=False, encoding="utf-8-sig")

    manifest = dict(
        schema_version="catalog-next/v1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        inputs={str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for p in (uncovered_path, summary_path, en_items_path, uom_cache_path)},
        counts=dict(keys_in_pack=summary["keys_in_pack"], items_in_pack=summary["items_in_pack"],
                    catalog_items=summary["catalog_items"],
                    catalog_uncovered=summary["catalog_uncovered"],
                    uom_unproven_items=int(len(priority)),
                    uom_unproven_qty=round(float(priority["stock_qty"].sum()), 3),
                    uom_status=priority["status"].value_counts().to_dict(),
                    actions_by_priority=actions["priority"].value_counts().to_dict()),
        statements=dict(
            pack_not_full_catalog=(f"{summary['keys_in_pack']:,} 个决策键只覆盖 "
                                   f"{summary['items_in_pack']:,} 个 EN 物料，"
                                   f"公司目录 {summary['catalog_items']:,} 个"),
            uncovered_is_not_zero_demand="未覆盖不等于零需求；有库存/有映射的必须单列",
            no_main_table_change="不改净额/决策包/主表；不 push"),
        note="动作与责任角色建议；不改任何数字",
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    write_report(actions, priority, summary, manifest, out_dir)
    return manifest


def write_report(actions: pd.DataFrame, priority: pd.DataFrame, summary: dict,
                 manifest: dict, out: Path) -> None:
    total_uom = priority["stock_qty"].sum()
    en_has = int(priority["status"].eq("en_has_uom_cache_missing").sum())
    disabled = int(priority["status"].eq("en_item_disabled").sum())
    lines = [
        "# 目录覆盖的后续动作（2026-10-28）",
        "",
        f"- 生成时间：{manifest['generated_at']}",
        f"- 输入：`catalog-coverage-2026-10-28/`（{summary['catalog_items']:,} 目录 / "
        f"{summary['items_in_pack']:,} 进包物料 / {summary['catalog_uncovered']:,} 未进包）"
        "+ EN `Item.stock_uom` 快照 + 本层 UOM 缓存",
        "- 只读：不改净额、决策包、主表；不 push。",
        "",
        "## 1. 结论",
        "",
        f"1. **{summary['keys_in_pack']:,} 个决策键不是公司全目录**：只覆盖 "
        f"{summary['items_in_pack']:,} 个 EN 物料，目录共 {summary['catalog_items']:,} 个；"
        f"未进包 {summary['catalog_uncovered']:,} 个。",
        f"2. **未覆盖 ≠ 零需求**：其中 **64 个物料有 {total_uom:,.0f} 件库存**，只是在本层 UOM 缓存之外；把它们当 0 会把有货算成没货。",
        f"3. **这 64 个不是 EN 主数据缺失**：实查 EN `Item.stock_uom` **{en_has + disabled}/64 有单位**"
        f"（全为「个」），{en_has} 条只需刷新本层缓存即可进库存侧事实，"
        f"{disabled} 条 EN `disabled=1` 走停售确认。",
        "4. 其余三类是不同性质的问题：3,840 项组件/皮壳（口径问题，不该建独立 SKU）、"
        "761 项无映射无证据（补映射）、284 项有映射无库存无销量（停售确认）。",
        "",
        "## 2. 四类未覆盖的后续动作",
        "",
        "| 优先级 | 原因 | 物料 | 库存件 | 后续动作 | 责任角色 | 复核 | 预期效果 |",
        "|---|---|---:|---:|---|---|---|---|",
    ]
    for row in actions.itertuples(index=False):
        lines.append(f"| {row.priority} | {row.reason} | {row.items:,} | {row.stock_qty:,.0f} | "
                     f"{row.action} | {row.owner} | {row.confirm_with} | {row.expected_effect} |")
    lines += ["", "**每类的证据与红线**", ""]
    for row in actions.itertuples(index=False):
        lines += [f"- **{row.reason}**（{row.items:,} 项）：{row.evidence}",
                  f"  - 红线：{row.guardrail}"]
    lines += [
        "",
        "## 3. 64 个「有库存但 UOM 未证」优先清单（前 10，全表见 CSV）",
        "",
        "| 排名 | 物料 | 物料组 | 库存 | 仓 | 通途码数 | EN UOM | 动作 |",
        "|---:|---|---|---:|---|---:|---|---|",
    ]
    for row in priority.head(10).itertuples(index=False):
        lines.append(f"| {row.rank} | {row.item} | {row.item_group} | {row.stock_qty:,.0f} | "
                     f"{row.stock_warehouses} | {row.mapped_tt_count} | {row.en_stock_uom} | "
                     f"{row.action} |")
    lines += [
        "",
        f"- 合计 **{total_uom:,.0f} 件**；库存中位 {priority['stock_qty'].median():.0f} 件；"
        f"全部 64 项的 12 个月销量都是 **0**（`sales_total=0`）——所以补单位后它们进的是"
        "「库存侧事实」，不是「需求证据」；需求仍缺，不能拿库存当销量。",
        f"- 其中 {disabled} 项 EN 已停用（disabled=1），不在补单位范围内，交给业务确认停售。",
        "- 按物料组 Top 5："
        + "、".join(f"{group} {count} 项"
                   for group, count in priority["item_group"].value_counts().head(5).items()),
        "",
        "## 4. 使用边界",
        "",
        f"- **{summary['keys_in_pack']:,} ≠ 全目录**：任何「全公司零缺口」的说法都不成立。",
        "- **未覆盖 ≠ 零需求**：本报告只给动作，不把未覆盖项并入任何缺口或服务档。",
        "- 皮壳/内胆是否按组件售卖属业务口径，本层不裁定，也不为凑覆盖率建 SKU。",
        "- 不改主表：没动 `decision_pack` / `supply_netting` / r6 / h180 的任何数字；不 push。",
        "",
        "## 5. 产物与复现",
        "",
        "- `coverage_actions.csv`：四类动作（含责任角色、证据、红线）",
        "- `uom_unproven_priority.csv`：64 项优先清单（含 EN 单位、停用、缓存状态）",
        "- `manifest.json`：输入哈希、计数、三条口径声明",
        "",
        "```bash",
        "uv run python -m supply_netting.scripts.catalog_next \\",
        "  --coverage D:/Work/fzh-order-store/en-demand-v1/supply-netting/catalog-coverage-2026-10-28",
        "```",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def fetch_en_items(items: list[str], env_path: str | Path,
                   base: str = "https://erpnext.vilavi.cn") -> list[dict]:
    """只读查询 EN Item 的 stock_uom / disabled（一次 in 过滤，64 条）。"""
    import requests

    env = {}
    for line in Path(env_path).read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    session = requests.Session()
    session.headers.update({"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}",
                            "Accept": "application/json"})
    response = session.get(f"{base}/api/resource/Item", params={
        "filters": json.dumps([["Item", "name", "in", items]]),
        "fields": json.dumps(["name", "stock_uom", "item_group", "disabled", "is_stock_item"]),
        "limit_page_length": 500}, timeout=60)
    response.raise_for_status()
    return response.json()["data"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="目录覆盖后续动作（只读）")
    parser.add_argument("--coverage", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                              "catalog-coverage-2026-10-28")
    parser.add_argument("--en-items", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                              "catalog-next-2026-10-28/en_items_stock_uom.json")
    parser.add_argument("--uom-cache", default="D:/Work/fzh-order-store/en-demand-v1/canonical/"
                                               "item_uom_cache.parquet")
    parser.add_argument("--en-env", default="D:/Work/赛狐/Cursor/EN_API/.env")
    parser.add_argument("--fetch-en", action="store_true", help="只读拉按 64 项的 EN 单位快照")
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "catalog-next-2026-10-28")
    args = parser.parse_args(argv)
    coverage = Path(args.coverage)

    if args.fetch_en:
        uncovered = load_uncovered(coverage / "uncovered_items.csv")
        items = sorted(uncovered.loc[uncovered["reason"] == "stock_without_uom_evidence",
                                     "item"].astype(str))
        rows = fetch_en_items(items, args.en_env)
        path = Path(args.en_items)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({row["name"]: row for row in rows}, ensure_ascii=False,
                                   indent=1), encoding="utf-8")
        print(json.dumps({"fetched": len(rows), "path": str(path)}, ensure_ascii=False))
        return 0

    manifest = build(coverage / "uncovered_items.csv",
                     coverage / "catalog_coverage_summary.json",
                     args.en_items, args.uom_cache, args.out)
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print("输出：", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
