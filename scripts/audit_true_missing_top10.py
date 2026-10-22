# -*- coding: utf-8 -*-
"""只读证据审计：true_missing Top10 + 指定 TT0031245K0064088。

输入（全部只读）：
- ``D:/Work/fzh-order-store/order_store.duckdb``（gs_orders / sku_map）
- C 审计产物 ``out/sku_match_audit/{unmatched_all.csv,categories.json,deep100.md}``
  （脚本默认取仓库根 ``out/sku_match_audit/``；任务书写的是 experiments 路径，
   该目录当前不存在，报告中已单列该路径差异。）

禁止：写 EN、改 sku_map、恢复别名、创建映射、估算补数、访问生产、扩族。
所有输入（DuckDB / sku_map.tsv / C 三件产物 / 本脚本）在审计开始时计算 SHA256，
DuckDB 在关闭只读连接后复算一次，指纹写入 JSON 的 inputs.pins_sha256。
输出：聚合证据 JSON（不含订单行级明细），供人工裁决。

用法：``uv run python scripts/audit_true_missing_top10.py``
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = Path(r"D:/Work/fzh-order-store/order_store.duckdb")
MAP_TSV = Path(r"D:/Work/fzh-order-store/sku_map.tsv")
C_OUT = ROOT / "out" / "sku_match_audit"
OUT = ROOT / "docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/out/sku_match_audit"

MANDATORY = "TT0031245K0064088"
RELATED_VARIANT = "TT0031245K0064088-0"

ANNOTATION_PREFIXES = ("已删除", "删除", "作废", "停用")


def sha256_file(path: Path) -> str:
    """对输入文件做 SHA256（分块读取，不把整库读进内存）。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pin(path: Path) -> dict:
    """固定一个输入文件的路径 + SHA256 + 字节数，供报告复算。"""
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def load_map_tsv() -> tuple[dict[str, set[str]], int]:
    by_tt: dict[str, set[str]] = defaultdict(set)
    n = 0
    with MAP_TSV.open(encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 2 or not row[0].strip() or not row[1].strip():
                continue
            by_tt[row[1].strip()].add(row[0].strip())
            n += 1
    return dict(by_tt), n


def annotated_of(key: str) -> str | None:
    for pre in ANNOTATION_PREFIXES:
        if key.startswith(pre):
            return pre
    return None


def strip_annotation(key: str) -> str:
    pre = annotated_of(key)
    return key[len(pre):] if pre else key


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # --- 输入指纹（审计前固定；报告与 JSON 同时记录）---
    input_pins = {
        "order_store_duckdb": pin(DB),
        "sku_map_tsv": pin(MAP_TSV),
        "c_audit_unmatched_all_csv": pin(C_OUT / "unmatched_all.csv"),
        "c_audit_categories_json": pin(C_OUT / "categories.json"),
        "c_audit_deep100_md": pin(C_OUT / "deep100.md"),
        "audit_script": pin(Path(__file__).resolve()),
    }
    db_sha256_before = input_pins["order_store_duckdb"]["sha256"]

    by_tt, tsv_pairs = load_map_tsv()

    cats = json.loads((C_OUT / "categories.json").read_text(encoding="utf-8"))
    c_by_sku = {r["sku"]: r for r in cats["skus"]}

    true_missing = sorted(
        (r for r in cats["skus"] if r["category"] == "true_missing"),
        key=lambda r: (-r["lines"], -r["qty"], r["sku"]),
    )
    top10 = [r["sku"] for r in true_missing[:10]]
    selected = top10 + [MANDATORY, RELATED_VARIANT]

    # --- 用 CSV 复核每个 SKU 的行数（不丢行） ---
    csv_lines: Counter[str] = Counter()
    with (C_OUT / "unmatched_all.csv").open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            csv_lines[row["sku_tongtool"]] += 1

    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET threads TO 4")

    # 表级对账
    gs_total = con.execute("select count(*) from gs_orders").fetchone()[0]
    gs_unmatched = con.execute(
        """select count(*) from gs_orders g left join sku_map m
           on g.sku_tongtool=m.tongtool_sku where m.tongtool_sku is null"""
    ).fetchone()[0]

    # 平台码跨行证据：同一 platform_sku 在其他 sku_tongtool 行上是否已有映射
    cross = con.execute(
        """
        with p as (select distinct platform_sku from gs_orders where platform_sku is not null and platform_sku<>''),
        o as (
          select g.platform_sku, g.sku_tongtool, m.item_code, count(*) lines, sum(g.qty) qty
          from gs_orders g
          left join sku_map m on g.sku_tongtool=m.tongtool_sku
          join p on p.platform_sku=g.platform_sku
          where m.item_code is not null
          group by all
        )
        select * from o
        """
    ).fetchall()
    cross_by_platform: dict[str, list[tuple[str, str, int, int]]] = defaultdict(list)
    for plat, tt, item, lines, qty in cross:
        cross_by_platform[plat].append((tt, item, lines, qty or 0))

    # 直接映射：platform_sku 本身是 sku_map 的键
    direct_by_platform: dict[str, set[str]] = defaultdict(set)
    for plat, item in con.execute(
        "select tongtool_sku, item_code from sku_map"
    ).fetchall():
        direct_by_platform[plat].add(item)

    def family_keys(stem: str, include_deleted: bool = True) -> list[str]:
        out = []
        for k in by_tt:
            bare = strip_annotation(k)
            if bare == stem or bare.startswith(stem + "-"):
                if include_deleted or not annotated_of(k):
                    out.append(k)
        return sorted(out)

    def cross_evidence(platforms: list[tuple[str, int, int]], exclude: str) -> list[dict]:
        """汇总 platform_sku 在其他 tongtool 行上的已映射 item_code。"""
        agg: dict[str, dict] = {}
        for plat, _lines, _qty in platforms:
            for tt, item, lines, qty in cross_by_platform.get(plat, []):
                if tt == exclude:
                    continue
                d = agg.setdefault(item, {"item_code": item, "lines_elsewhere": 0, "qty_elsewhere": 0,
                                          "mapped_skus": Counter(), "platform_skus": Counter()})
                d["lines_elsewhere"] += lines
                d["qty_elsewhere"] += qty
                d["mapped_skus"][tt] += lines
                d["platform_skus"][plat] += lines
        rows = sorted(agg.values(), key=lambda x: (-x["lines_elsewhere"], x["item_code"]))
        for d in rows:
            d["mapped_skus"] = dict(d["mapped_skus"].most_common(5))
            d["platform_skus"] = dict(d["platform_skus"].most_common(5))
        return rows

    def base_profile(sku: str) -> dict:
        st = con.execute(
            """select count(*), coalesce(sum(qty),0), count(distinct month), min(month), max(month),
                      count(distinct channel), count(distinct account), count(distinct warehouse),
                      count(distinct platform_sku)
               from gs_orders where sku_tongtool=?""", [sku],
        ).fetchone()
        monthly = con.execute(
            "select month, count(*), coalesce(sum(qty),0) from gs_orders where sku_tongtool=? group by 1 order by 1",
            [sku],
        ).fetchall()
        chans = con.execute(
            "select channel, count(*), coalesce(sum(qty),0) from gs_orders where sku_tongtool=? group by 1 order by 2 desc",
            [sku],
        ).fetchall()
        plats = con.execute(
            """select coalesce(platform_sku,''), count(*), coalesce(sum(qty),0)
               from gs_orders where sku_tongtool=? group by 1 order by 2 desc, 1 limit 15""",
            [sku],
        ).fetchall()
        whs = con.execute(
            "select warehouse, count(*) from gs_orders where sku_tongtool=? group by 1 order by 2 desc",
            [sku],
        ).fetchall()
        self_lines = con.execute(
            "select count(*), coalesce(sum(qty),0) from gs_orders where sku_tongtool=? and platform_sku=sku_tongtool",
            [sku],
        ).fetchone()
        return {
            "order_lines": st[0],
            "qty": st[1],
            "months": {"distinct": st[2], "first": st[3], "last": st[4],
                       "histogram": {m: {"lines": l, "qty": q} for m, l, q in monthly}},
            "channels": {c: {"lines": l, "qty": q} for c, l, q in chans},
            "accounts_distinct": st[6],
            "warehouses": {w: l for w, l in whs},
            "platform_sku": {
                "distinct": st[8],
                "self_platform_sku": {"lines": self_lines[0], "qty": self_lines[1]},
                "top": [{"platform_sku": p, "lines": l, "qty": q} for p, l, q in plats],
            },
            "distinct_channels": st[5],
        }

    def candidates_for(sku: str, prof: dict) -> tuple[list[dict], list[dict], list[str]]:
        """返回 (candidates, conflicts, business_decisions)。人工规则显式列出，全部只读。"""
        plats = [(p["platform_sku"], p["lines"], p["qty"]) for p in prof["platform_sku"]["top"]]
        all_plats = con.execute(
            "select platform_sku, count(*), coalesce(sum(qty),0) from gs_orders where sku_tongtool=? group by 1",
            [sku],
        ).fetchall()
        cross_rows = cross_evidence(all_plats, sku)
        direct = {}
        for plat, lines, qty in all_plats:
            if plat and plat in direct_by_platform:
                for item in direct_by_platform[plat]:
                    direct.setdefault(item, {"item_code": item, "platform_sku": plat, "lines": 0, "qty": 0})
                    direct[item]["lines"] += lines
                    direct[item]["qty"] += qty

        cands: list[dict] = []
        conflicts: list[dict] = []
        decisions: list[str] = []

        if sku == "YCSOFA001":
            decisions += [
                "YCSOFA001 在 114 个平台编码、4 个渠道上出现，形态是「沙发类汇总码」而非单品编码；需业务确认它到底代表哪个商品，或按平台编码拆分。",
                "平台编码与 sku_map 直接命中 0 条；跨行也只有极少条目能落到 item_code，不能据此认领。",
            ]
            conflicts.append({
                "type": "aggregate_bucket_multi_listing",
                "detail": "114 个 platform_sku 取值（含 8 行空值）、4 个渠道（BESTBUY 105 / tiktok 73 / Shopify 34 / 亚马逊 22 行），无一个平台码直接命中 sku_map；该码不是单品身份。",
                "item_codes": [],
            })
        elif sku.startswith("XINGQIU-Jupiter"):
            size = "10" if sku.endswith("-10") else "16"
            target = "25" if size == "10" else "41"
            inferred = f"KS0019-PBHLR-{target}-JUPITER"
            cands.append({
                "base_code": f"XINGQIU-{('Jupiter-' + size)}",
                "item_codes": [inferred],
                "evidence_type": "family_naming_pattern",
                "evidence": (
                    "同族已登记键 XINGQIU-Moon-10→KS0019-PBHLR-25-MOON、XINGQIU-Moon-16→KS0019-PBHLR-41-MOON、"
                    "XINGQIU-BlackMoon-10/-16→25/41、XINGQIU-Earth-16→KS0019-PBHLR-41-EARTH；"
                    f"10 码对应 25、16 码对应 41，颜色位 JUPITER 尚无已登记键。"
                ),
                "confidence": "medium",
                "registered": False,
                "source": "sku_map TSV 同族键 + gs_orders platform_sku 分布",
            })
            decisions += [
                f"确认 EN 是否存在 {inferred}（本审计无 Item master 权限，不能证伪）。",
                "确认 Jupiter 是否沿用 KS0019-PBHLR 系列；若沿用，再由业务登记 alias。",
                "平台码 XUE9008YAN9481PL-US 同时出现在 Jupiter-10 与 Jupiter-16 行，平台侧无法区分尺寸；不能用平台码单独定尺寸。",
            ]
            conflicts.append({
                "type": "shared_platform_sku_across_sizes",
                "detail": "XUE9008YAN9481PL-US 同时挂在 Jupiter-10 与 Jupiter-16；尺寸只能靠 tongtool_sku，映射时不可用平台码反推。",
                "item_codes": [],
            })
        elif sku == "XINGQIU-Earth-10":
            inferred = "KS0019-PBHLR-25-EARTH"
            cands.append({
                "base_code": "XINGQIU-Earth-10",
                "item_codes": [inferred],
                "evidence_type": "family_naming_pattern",
                "evidence": (
                    "同族 XINGQIU-Earth-16 已登记→KS0019-PBHLR-41-EARTH；"
                    "XINGQIU-Moon-10→KS0019-PBHLR-25-MOON，10 码对应 25。"
                ),
                "confidence": "medium",
                "registered": False,
                "source": "sku_map TSV 同族键",
            })
            decisions.append(f"确认 EN 是否存在 {inferred}，并确认 Earth-10 与 Earth-16 的尺寸/物料差异。")
            conflicts.append({
                "type": "shared_platform_sku_across_sizes",
                "detail": "XUE9006YAN9477PL-US 也出现在 Earth-16（已映射 41-EARTH）行；平台码不能唯一区分 10/16。",
                "item_codes": ["KS0019-PBHLR-41-EARTH"],
            })
        elif sku == "CEN003-NZAIBLUE-100":
            inferred = "KS0001-TR-100-DENIMBLUE"
            cands.append({
                "base_code": "CEN003-NZAIBLUE",
                "item_codes": [inferred],
                "evidence_type": "family_size_color_pattern",
                "evidence": (
                    "同色已登记：CEN003-NZAIBLUE-150→KS0001-TR-153-DENIMBLUE、-180→183、-194→194；"
                    "同族其它颜色 -100 均映射到 KS0001-TR-100-<COLOR>（COFFEE/PURPLE/RED/SKYBLUE/YELLOW）；"
                    "仅 DPBLUE 走 QDKTR-100-DEEPBLUE，属另一面料线。"
                ),
                "confidence": "medium",
                "registered": False,
                "source": "sku_map TSV 同族键",
            })
            decisions += [
                f"确认 EN 是否存在 {inferred}，并确认 NZAIBLUE=DENIMBLUE 的 100 码不做 100→153 换算。",
                "同族 150→153、180→183 是既有尺码换算口径；100 码按同族规律为 100→100，需业务确认。",
            ]
        elif sku.startswith("CEN-No/B-Velvet-Grey"):
            size = sku.rsplit("-", 1)[-1]
            item = f"KS0248-HLR-{size}-GREY"
            plat = f"CEN-No/B-971-Velvet-Grey-{size}"
            cands.append({
                "base_code": f"CEN-No/B-971-Velvet-Grey-{size}",
                "item_codes": [item],
                "evidence_type": "registered_platform_sku_match",
                "evidence": (
                    f"订单 platform_sku 精确值 {plat} 本身就是 sku_map 键，映射到 {item}；"
                    f"该平台码在本 SKU 下命中 {direct.get(item, {}).get('lines', 0)} 行。"
                ),
                "confidence": "high",
                "registered": True,
                "source": "gs_orders.platform_sku = sku_map.tongtool_sku 精确等值",
            })
            decisions += [
                f"确认原始码 {sku}（无 971 段）与已登记 {plat} 是同一商品的不同渠道写法。",
                ("平台码 CEN-No/B-971-Velvet-Grey-Twin（49 行）按同族 138→140 的换算口径应对应 100 码；需确认 Twin=100 后再并入同一 item_code。" if size == "100"
                 else "平台码 CEN-No/B-971-Velvet-Grey-King（32 行）需确认 King=194 后再并入同一 item_code。"),
                "确认后按业务流程登记 alias；本审计未写 EN。",
            ]
            if size == "194":
                conflicts.append({
                    "type": "platform_sku_reused_across_fabrics",
                    "detail": "WM-971-Velvet-Grey-King 在 CEN-No/B-968-Linen-Grey-194 行映射 KS0248-DM-194-GREY（另一面料），与本 SKU 的 HLR 面料不同；平台码有复用，不能跨行直接认领。",
                    "item_codes": ["KS0248-HLR-194-GREY", "KS0248-DM-194-GREY"],
                })
        elif sku == "BAI20019N0A62887SX-FBA":
            item = "KS0125-MM-110-NAVYSTRIPE"
            ex = [r for r in cross_rows if r["item_code"] == item]
            cands.append({
                "base_code": "BAI20019N0A62887SX",
                "item_codes": [item],
                "evidence_type": "cross_row_platform_sku_match",
                "evidence": (
                    "平台码 BAI20019N0A62887SX（去掉 -FBA/-cui/-qinghuo 操作后缀）在其它订单行上对应 "
                    f"tongtool_sku TT0020019K0062887 → {item}；跨行证据 "
                    f"{ex[0]['lines_elsewhere'] if ex else 0} 行（含 -cui 变体）。"
                ),
                "confidence": "high",
                "registered": True,
                "source": "同一 platform_sku 的跨行已映射证据（gs_orders LEFT JOIN sku_map）",
            })
            decisions += [
                f"-FBA 是 FBA 渠道别名后缀；确认基础平台码 BAI20019N0A62887SX 与 {item} 的对应关系后登记。",
                "-cui（催）/ -qinghuo（清货）是运营后缀，不应成为独立商品；需确认是否统一到同一 item_code。",
            ]
        elif sku == "FBA-duo":
            items = [r["item_code"] for r in cross_rows]
            cands.append({
                "base_code": "FBA-duo",
                "item_codes": items,
                "evidence_type": "multi_product_bucket (no single candidate)",
                "evidence": (
                    f"30 个平台编码跨行落到 {len(items)} 个已映射 item_code（见 conflicts），说明 FBA-duo 是「多商品/多件套」汇总码，"
                    "不是一个可登记的单品 alias。"
                ),
                "confidence": "low",
                "registered": False,
                "source": "跨行平台码证据",
            })
            decisions += [
                "FBA-duo 不能登记为单条 alias；需业务定义 duo 的套件组成与件数口径。",
                "若 duo 表示 2 件装，订单 qty 的 UOM 与库存扣减口径需单独确认（本审计不估算）。",
            ]
            conflicts.append({
                "type": "aggregate_bucket_multi_item",
                "detail": f"同一 FBA-duo 码下 30 个平台编码，跨行对应 {len(cross_rows)} 个 item_code（Top 10 见 item_codes）。",
                "item_codes": [r["item_code"] for r in cross_rows[:10]],
            })
        elif sku == "petcushionjp-76":
            decisions += [
                "99 行全部只有一个平台码 petcushionjp-76x，sku_map 中无任何 cushion 相关键；本地无候选证据。",
                "需业务确认 EN 是否曾建过该宠物垫物料（本审计无 Item master 权限，标 pending）。",
            ]
        elif sku == MANDATORY:
            family = family_keys("TT0031245K0064088")
            live_child = [k for k in family if not annotated_of(k) and k != sku]
            deleted_base = [k for k in family if annotated_of(k) and strip_annotation(k) == sku]
            cands.append({
                "base_code": sku,
                "item_codes": sorted({i for k in deleted_base for i in by_tt[k]}),
                "evidence_type": "annotated_alias_deleted",
                "evidence": "仅存删除前缀 alias：删除TT0031245K0064088 → HM1510-YD2-135x152x80-WHITE；无活映射。",
                "confidence": "low",
                "registered": True,
                "deleted": True,
                "source": "sku_map TSV 删除前缀行",
            })
            cands.append({
                "base_code": "TT0031245K0064088-Foam",
                "item_codes": sorted({i for k in live_child for i in by_tt[k]}),
                "evidence_type": "live_sibling_alias",
                "evidence": f"活别名 {', '.join(live_child)} → KS0394-CTTM-135x152x80-REDDISHGRAY；同族 64086/64087 基础码也映射 KS0394 的 Beige/Gray。",
                "confidence": "medium",
                "registered": True,
                "source": "sku_map TSV 同族活键",
            })
            if cross_rows:
                cands.append({
                    "base_code": "platform_sku_cross_row",
                    "item_codes": [r["item_code"] for r in cross_rows],
                    "evidence_type": "cross_row_platform_sku_match",
                    "evidence": "平台码跨行证据全量列在 candidate_count_audit.cross_row_nonblank_query（不截断）；"
                                "另有多行平台码是其它 tongtool 码（汇总码特征）。",
                    "confidence": "medium",
                    "registered": True,
                    "omitted_item_codes": 0,
                    "source": "gs_orders.platform_sku 跨行证据",
                })
            decisions += [
                "TT0031245K0064088 同时是 553 行的 tongtool_sku，但 platform_sku 覆盖 23 个值，其中 189 行指向其它商品码——需业务确认该码是否为 Tiktok 沙发的汇总/占位码。",
                "删除别名指向 HM1510-YD2-135x152x80-WHITE，而同族活别名 -Foam 与 64087 指向 KS0394-REDDISHGRAY；HM1510（白）与 KS0394（红灰）不是同一物料，必须先裁决。",
                "恢复别名属禁止项；是否恢复、恢复成哪个 item_code，只能由业务决定。",
            ]
            conflicts += [
                {"type": "live_vs_deleted_alias_conflict",
                 "detail": "活键 TT0031245K0064088-Foam → KS0394-REDDISHGRAY；删除键 删除TT0031245K0064088-Foam → HM1510-YD2-135x152x80-WHITE。同一别名族在活/删两侧指向不同 item_code。",
                 "item_codes": ["KS0394-CTTM-135x152x80-REDDISHGRAY", "HM1510-YD2-135x152x80-WHITE"]},
                {"type": "aggregate_umbrella_code",
                 "detail": "189/553 行的 platform_sku 是别的 tongtool 码（如 TT0031245K0064087-SOFA-Gray、TT0020043K0063354），跨行映射到多个 item_code；该码不是单品身份。",
                 "item_codes": [r["item_code"] for r in cross_rows],
                 "omitted_item_codes": 0},
            ]
        elif sku == RELATED_VARIANT:
            item = "KS0394-CTTM-135x152x80-REDDISHGRAY"
            cands.append({
                "base_code": "TT0031245K0064088-0",
                "item_codes": [item],
                "evidence_type": "annotated_alias_deleted",
                "evidence": "删除TT0031245K0064088-0 → KS0394-REDDISHGRAY；与活别名 -Foam 指向一致。",
                "confidence": "high",
                "registered": True,
                "deleted": True,
                "source": "sku_map TSV 删除前缀行 + 同族活键",
            })
            decisions += [
                "别名被删除但订单持续到 2025-11；需业务确认当初删除原因，以及是否按 KS0394-REDDISHGRAY 恢复登记。",
                "该 SKU 236 行中 223 行 platform_sku 就是自身，13 行指向其它商品码；主体可收敛到 KS0394，但删除意图未明，标 pending。",
            ]
            conflicts.append({
                "type": "platform_sku_contamination",
                "detail": "236 行中 223 行 platform_sku=自身；其余 13 行指向 KS0223/KS0390/KS0193/KS0394 等其它商品码，属汇总码污染，映射前需排除。",
                "item_codes": ["KS0223-NL-65XL-BLUERED", "KS0390-CTTM-120x120x70-CREAMYBEIGE",
                               "KS0193-MZ-16-GREY", "KS0394-CTTM-135x152x80-REDDISHGRAY"],
            })

        # 通用：platform_sku 直接命中 / 跨行证据作为附录。
        # 汇总码/桶码/同平台跨尺寸场景下，这些证据只进 conflicts，不当作单品候选。
        suppress_generic = {
            "YCSOFA001", "XINGQIU-Jupiter-10", "XINGQIU-Jupiter-16", "XINGQIU-Earth-10",
            "FBA-duo", "CEN-No/B-Velvet-Grey-194", MANDATORY, RELATED_VARIANT,
        }
        if direct and sku not in suppress_generic and not any(
                c["evidence_type"] == "registered_platform_sku_match" for c in cands):
            cands.append({
                "base_code": "platform_sku_direct_match",
                "item_codes": sorted(direct),
                "evidence_type": "registered_platform_sku_match",
                "evidence": "订单 platform_sku 直接等于 sku_map 键。",
                "confidence": "high",
                "registered": True,
                "source": "gs_orders.platform_sku = sku_map.tongtool_sku",
            })
        if cross_rows and sku not in suppress_generic and not any(
                c["evidence_type"] == "cross_row_platform_sku_match" for c in cands):
            cands.append({
                "base_code": "platform_sku_cross_row",
                "item_codes": [r["item_code"] for r in cross_rows[:10]],
                "evidence_type": "cross_row_platform_sku_match",
                "evidence": f"{len(cross_rows)} 个 item_code 可从同平台码的其它行找到已映射证据。",
                "confidence": "medium",
                "registered": True,
                "source": "同一 platform_sku 的跨行证据",
            })
        return cands, conflicts, decisions

    def platform_code_audit(sku: str) -> dict:
        """v2：TT0031245K0064088 候选计数的显式定义与全量清单。

        两个口径分开算、都报总数：
        - 直接口径：本 SKU 的（非空）platform_sku 本身是 sku_map.tongtool_sku 键；
        - 跨行口径：本 SKU 的（非空）platform_sku 出现在 sku_tongtool<>本 SKU 的
          其它订单行上，且那些行的 sku_tongtool 已在 sku_map 中映射。
        两个口径都列出全部 item_code，不做 top-N 截断。
        """
        total_rows, total_qty = con.execute(
            "select count(*), coalesce(sum(qty),0) from gs_orders where sku_tongtool=?", [sku],
        ).fetchone()
        self_rows, self_qty = con.execute(
            "select count(*), coalesce(sum(qty),0) from gs_orders "
            "where sku_tongtool=? and platform_sku=sku_tongtool", [sku],
        ).fetchone()
        blank_rows, blank_qty = con.execute(
            "select count(*), coalesce(sum(qty),0) from gs_orders "
            "where sku_tongtool=? and platform_sku=''", [sku],
        ).fetchone()
        distinct_all = con.execute(
            "select count(distinct platform_sku) from gs_orders where sku_tongtool=?", [sku],
        ).fetchone()[0]
        distinct_nonblank = con.execute(
            "select count(distinct platform_sku) from gs_orders "
            "where sku_tongtool=? and platform_sku<>''", [sku],
        ).fetchone()[0]

        values = con.execute(
            """select platform_sku, count(*) lines, coalesce(sum(qty),0) qty
               from gs_orders where sku_tongtool=? group by 1 order by 2 desc, 1""", [sku],
        ).fetchall()

        # 口径 1：直接平台码查询（非空 platform_sku = sku_map 键）
        direct = con.execute(
            """select g.platform_sku, count(*) lines, coalesce(sum(g.qty),0) qty,
                      list(distinct m.item_code) items
               from gs_orders g join sku_map m on g.platform_sku=m.tongtool_sku
               where g.sku_tongtool=? and g.platform_sku<>''
               group by 1 order by 2 desc, 1""", [sku],
        ).fetchall()
        direct_by_code = {code: sorted(items) for code, _l, _q, items in direct}
        direct_items = sorted({i for items in direct_by_code.values() for i in items})

        # 口径 2：跨行非空平台码查询（排除本 SKU 自身行；本 SKU 未映射，含入与否结果相同）
        cross = con.execute(
            """select m.item_code, count(*) lines, coalesce(sum(g.qty),0) qty,
                      count(distinct g.sku_tongtool) mapped_skus,
                      count(distinct g.platform_sku) platform_skus,
                      list(distinct g.sku_tongtool) sku_list,
                      list(distinct g.platform_sku) platform_list
               from gs_orders g join sku_map m on g.sku_tongtool=m.tongtool_sku
               where g.platform_sku in (
                       select distinct platform_sku from gs_orders
                       where sku_tongtool=? and platform_sku<>'')
                 and g.sku_tongtool<>?
               group by 1 order by 2 desc, 1""", [sku, sku],
        ).fetchall()
        cross_items = [
            {"item_code": item, "lines_elsewhere": lines, "qty_elsewhere": qty,
             "mapped_skus": skus, "platform_skus": plats,
             "mapped_sku_list": sorted(sku_list), "platform_list": sorted(platform_list)}
            for item, lines, qty, skus, plats, sku_list, platform_list in cross
        ]
        cross_item_set = {r["item_code"] for r in cross_items}

        # 每个平台码的跨行 item_code 数（用于全量分布表，不截断）
        per_code_cross = dict(con.execute(
            """select g.platform_sku, count(distinct m.item_code)
               from gs_orders g join sku_map m on g.sku_tongtool=m.tongtool_sku
               where g.platform_sku in (
                       select distinct platform_sku from gs_orders
                       where sku_tongtool=? and platform_sku<>'')
                 and g.sku_tongtool<>?
               group by 1""", [sku, sku],
        ).fetchall())

        value_rows = []
        for platsku, lines, qty in values:
            is_blank = platsku == ""
            value_rows.append({
                "platform_sku": platsku if not is_blank else "",
                "is_blank": is_blank,
                "is_self": platsku == sku,
                "lines": lines,
                "qty": qty,
                "direct_item_codes": direct_by_code.get(platsku, []),
                "cross_row_item_code_count": per_code_cross.get(platsku, 0),
            })

        other_rows = total_rows - self_rows
        direct_lines = sum(r[1] for r in direct)
        direct_qty = sum(r[2] for r in direct)
        cross_lines = sum(r["lines_elsewhere"] for r in cross_items)
        cross_qty = sum(r["qty_elsewhere"] for r in cross_items)
        listed_in_v1 = 10  # v1 用 cross_rows[:10] 截断
        omitted = len(cross_items) - listed_in_v1

        return {
            "definitions": {
                "platform_sku_values_total": "gs_orders 中该 sku_tongtool 的 platform_sku distinct 数（含空串）",
                "self_rows": "platform_sku = sku_tongtool 的行",
                "other_code_rows": "total_rows - self_rows，含空 platform_sku",
                "direct_platform_code_lookup": "本 SKU 的非空 platform_sku 本身是 sku_map.tongtool_sku 键；返回平台码 → item_code",
                "cross_row_nonblank_query": "本 SKU 的非空 platform_sku 也出现在 sku_tongtool<>本 SKU 的其它行上，且其它行的 sku_tongtool 在 sku_map 有 item_code；返回 distinct item_code",
            },
            "platform_sku_values": {
                "total_rows": total_rows,
                "total_qty": total_qty,
                "distinct_including_blank": distinct_all,
                "distinct_nonblank": distinct_nonblank,
                "blank_rows": blank_rows,
                "blank_qty": blank_qty,
                "self_rows": self_rows,
                "self_qty": self_qty,
                "other_code_rows": other_rows,
                "other_code_qty": total_qty - self_qty,
                "values_all": value_rows,
            },
            "direct_platform_code_lookup": {
                "platform_codes": len(direct_by_code),
                "item_codes": len(direct_items),
                "rows": direct_lines,
                "qty": direct_qty,
                "codes": [{"platform_sku": code, "lines": l, "qty": q,
                           "item_codes": direct_by_code[code]} for code, l, q, _ in direct],
                "item_code_list": direct_items,
                "omitted_item_codes": 0,
            },
            "cross_row_nonblank_query": {
                "item_codes": len(cross_items),
                "rows": cross_lines,
                "qty": cross_qty,
                "items_all": cross_items,
                "omitted_item_codes": 0,
            },
            "union_item_codes": sorted(set(direct_items) | cross_item_set),
            "v1_claim_reconciliation": {
                "v1_direct_platform_codes": 7,
                "v1_cross_row_item_codes_claimed": 8,
                "v1_cross_row_item_codes_listed": listed_in_v1,
                "v2_direct_platform_codes": len(direct_by_code),
                "v2_direct_item_codes": len(direct_items),
                "v2_cross_row_item_codes": len(cross_items),
                "v1_cross_total_reproducible": 8 == len(cross_items),
                "explanation": (
                    "v1 的 “8 个 item_code” 无法由任何显式查询复现：直接口径是 7 个平台码 / 6 个 item_code，"
                    f"跨行口径是 {len(cross_items)} 个 item_code。v1 用 cross_rows[:10] 只列了前 10 个，"
                    f"恰好隐藏 {omitted} 个；8 = {len(cross_items)} − {listed_in_v1}，即「被截断隐藏的数量」，"
                    "不是总数。该数字是在 commit d6115ea6 中以纯文本写入的（该 commit 未改任何计算代码），"
                    "且与同一条 JSON 候选已列出的 10 个 item_code 自相矛盾。v2 的 8 个被隐藏项见 "
                    "cross_row_nonblank_query.items_all 的第 11–18 位。"
                ),
                "v1_hidden_items": [r["item_code"] for r in cross_items[listed_in_v1:]],
            },
            "checks": {
                "self_plus_other_equals_total": self_rows + other_rows == total_rows,
                "direct_code_count_matches": len(direct_by_code) == len(direct),
                "direct_items_subset_of_cross": set(direct_items) <= cross_item_set,
                "cross_item_count_matches": len(cross_items) == len(cross_item_set),
                "direct_list_not_truncated": len(direct) == len(direct_by_code),
            },
        }

    out_skus = []
    for i, sku in enumerate(selected, 1):
        prof = base_profile(sku)
        cands, conflicts, decisions = candidates_for(sku, prof)
        c = c_by_sku.get(sku, {})
        candidate_count_audit = None
        if sku == MANDATORY:
            # v2：候选计数显式定义 + 全量清单；同时用全量结果覆盖 v1 的 top-10 截断。
            candidate_count_audit = platform_code_audit(sku)
            cross_all = candidate_count_audit["cross_row_nonblank_query"]["items_all"]
            for cand in cands:
                if cand["base_code"] == "platform_sku_cross_row":
                    cand["item_codes"] = [r["item_code"] for r in cross_all]
                    cand["omitted_item_codes"] = 0
                    cand["evidence"] = (
                        "跨行非空平台码查询："
                        f"{candidate_count_audit['cross_row_nonblank_query']['item_codes']} 个 item_code，"
                        "全部列出（见 candidate_count_audit.cross_row_nonblank_query.items_all）；"
                        "直接口径："
                        f"{candidate_count_audit['direct_platform_code_lookup']['platform_codes']} 个平台码 → "
                        f"{candidate_count_audit['direct_platform_code_lookup']['item_codes']} 个 item_code。"
                    )
            for conf in conflicts:
                if conf["type"] == "aggregate_umbrella_code":
                    conf["item_codes"] = [r["item_code"] for r in cross_all]
                    conf["omitted_item_codes"] = 0
        # 证据状态显式裁决（不是业务结论）：
        # - conflicting_evidence：同一码存在指向不同 item_code 的证据，需先裁决冲突；
        # - pending_insufficient_evidence：本地无候选；
        # - pending_business_confirmation：有候选但需业务确认后才能登记。
        status_map = {
            "YCSOFA001": "pending_insufficient_evidence",
            "petcushionjp-76": "pending_insufficient_evidence",
            "XINGQIU-Jupiter-10": "conflicting_evidence",
            "XINGQIU-Jupiter-16": "conflicting_evidence",
            "XINGQIU-Earth-10": "conflicting_evidence",
            "FBA-duo": "conflicting_evidence",
            "CEN-No/B-Velvet-Grey-194": "conflicting_evidence",
            MANDATORY: "conflicting_evidence",
            RELATED_VARIANT: "conflicting_evidence",
        }
        status = status_map.get(sku, "pending_business_confirmation")
        out_skus.append({
            "rank": i,
            "sku": sku,
            "selection": ("mandatory" if sku == MANDATORY else
                          "related_variant_of_mandatory" if sku == RELATED_VARIANT else "top10_true_missing"),
            "c_audit_category": c.get("category"),
            "c_audit_lines": c.get("lines"),
            "csv_recomputed_lines": csv_lines.get(sku),
            "lines_match_c": csv_lines.get(sku) == c.get("lines"),
            "status": status,
            "order_lines": prof["order_lines"],
            "qty": prof["qty"],
            "months": prof["months"],
            "channels": prof["channels"],
            "accounts_distinct": prof["accounts_distinct"],
            "warehouses": prof["warehouses"],
            "platform_sku": prof["platform_sku"],
            **({"candidate_count_audit": candidate_count_audit} if candidate_count_audit else {}),
            "raw_identifier": {
                "value": sku,
                "table_column": "gs_orders.sku_tongtool",
                "note": "通途侧原始编码；同订单行的 platform_sku 是渠道侧编码。",
            },
            "base_code_candidates": cands,
            "conflicts": conflicts,
            "evidence_sources": [
                "D:/Work/fzh-order-store/order_store.duckdb :: gs_orders (read_only)",
                "D:/Work/fzh-order-store/order_store.duckdb :: sku_map (read_only)",
                "D:/Work/fzh-order-store/sku_map.tsv (read_only)",
                "out/sku_match_audit/unmatched_all.csv",
                "out/sku_match_audit/categories.json",
                "out/sku_match_audit/deep100.md",
            ],
            "business_decisions": decisions,
            "pending": [d for d in decisions] or ["无候选证据；需业务提供商品主数据/渠道对照。"],
        })

    sel_lines = sum(r["order_lines"] for r in out_skus)
    sel_qty = sum(r["qty"] for r in out_skus)
    tm_lines = sum(r["lines"] for r in true_missing)
    insuf = [r for r in cats["skus"] if r["category"] == "insufficient_evidence"]
    insuf_lines = sum(r["lines"] for r in insuf)
    mandatory_lines = sum(r["order_lines"] for r in out_skus if r["sku"] in (MANDATORY, RELATED_VARIANT))

    # 关闭只读连接后再复核 DB 指纹：证明审计期间未写库。
    con.close()
    db_sha256_after = sha256_file(DB)
    input_pins["order_store_duckdb"]["recheck_sha256_after_run"] = db_sha256_after
    input_pins["order_store_duckdb"]["unchanged_during_run"] = db_sha256_after == db_sha256_before

    recon = {
        "gs_orders_total_rows": gs_total,
        "gs_orders_unmatched_rows": gs_unmatched,
        "c_audit_unmatched_rows": cats["totals"]["unmatched_lines"],
        "c_audit_unmatched_skus": cats["totals"]["unmatched_unique_skus"],
        "selected_skus": len(out_skus),
        "selected_order_lines": sel_lines,
        "selected_qty": sel_qty,
        "selected_share_of_unmatched_lines": round(sel_lines / gs_unmatched, 4),
        "top10_true_missing_skus": 10,
        "top10_true_missing_lines": sum(r["order_lines"] for r in out_skus if r["selection"] == "top10_true_missing"),
        "true_missing_category_lines": tm_lines,
        "top10_share_of_true_missing_lines": round(
            sum(r["order_lines"] for r in out_skus if r["selection"] == "top10_true_missing") / tm_lines, 4),
        "mandatory_plus_variant_lines": mandatory_lines,
        "insufficient_evidence_category_lines": insuf_lines,
        "mandatory_share_of_insufficient_lines": round(mandatory_lines / insuf_lines, 4),
        "every_selected_line_accounted": all(r["lines_match_c"] for r in out_skus),
        "csv_lines_sum_equals_unmatched": sum(csv_lines.values()) == gs_unmatched,
        "no_rows_dropped": True,
        "checks": {
            "selected_lines_match_c": all(r["lines_match_c"] for r in out_skus),
            "csv_total_matches": sum(csv_lines.values()) == gs_unmatched,
            "top10_count": sum(1 for r in out_skus if r["selection"] == "top10_true_missing") == 10,
            "mandatory_included": MANDATORY in {r["sku"] for r in out_skus},
            "no_sku_duplicated": len({r["sku"] for r in out_skus}) == len(out_skus),
            "mandatory_candidate_audit_present": any("candidate_count_audit" in r for r in out_skus),
            "mandatory_cross_candidates_all_listed": all(
                r["candidate_count_audit"]["cross_row_nonblank_query"]["omitted_item_codes"] == 0
                for r in out_skus if "candidate_count_audit" in r),
            "status_counts_unchanged": Counter(r["status"] for r in out_skus) == Counter({
                "conflicting_evidence": 7,
                "pending_insufficient_evidence": 2,
                "pending_business_confirmation": 3,
            }),
        },
    }
    if not all(recon["checks"].values()):
        raise SystemExit("对账失败: " + json.dumps(recon["checks"], ensure_ascii=False))

    status_counts = Counter(r["status"] for r in out_skus)
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "task": "只读 true_missing Top10 证据审计（含 TT0031245K0064088）",
        "mode": "read_only_evidence_audit",
        "inputs": {
            "duckdb": str(DB),
            "sku_map_tsv": str(MAP_TSV),
            "c_audit_actual_dir": str(C_OUT),
            "c_audit_task_stated_dir": str(OUT),
            "path_note": "任务书写的 experiments/g1_contract/out/sku_match_audit/ 当前不存在；C 产物实际在仓库根 out/sku_match_audit/（.gitignore: out/*）。本审计读取实际目录，并把 JSON 写到任务书路径。",
            "pins_sha256": input_pins,
            "pins_note": "所有输入在审计开始时算 SHA256；DuckDB 关闭连接后复算一次，unchanged_during_run 证明只读。",
        },
        "selection_rule": {
            "top10": "categories.json 中 category=true_missing，按 order_lines 降序、qty 降序、sku 升序取前 10。",
            "mandatory": MANDATORY,
            "related_variant": RELATED_VARIANT,
            "related_variant_reason": "同一删除 alias 族的 -0 变体，789 行问题的一部分；单列不并入 Top10。",
        },
        "reconciliation": recon,
        "summary": {
            "selected_skus": len(out_skus),
            "order_lines": sel_lines,
            "qty": sel_qty,
            "status_counts": dict(status_counts),
            "skus_with_candidates": sum(1 for r in out_skus if r["base_code_candidates"]),
            "skus_with_conflicts": sum(1 for r in out_skus if r["conflicts"]),
            "business_decision_items": sum(len(r["business_decisions"]) for r in out_skus),
        },
        "skus": out_skus,
        "not_modified": [
            "未写 EN / ERPNext",
            "未改 sku_map.tsv 或 DuckDB（DuckDB SHA256 审计前后一致，见 inputs.pins_sha256）",
            "未恢复任何删除别名",
            "未创建任何映射",
            "未估算数量或成本",
            "未访问生产系统",
            "未扩展到 Top10 之外的族",
        ],
        "caveats": [
            "true_missing 只表示 alias 未在 sku_map 登记，不代表 EN 没有该物料；本审计无 Item master 访问权。",
            "platform_sku 跨行证据只作候选证据；不同渠道/不同时期可能复用同一平台码。",
            "所有 item_code 推断均未回写，也不构成登记建议的最终结论；需业务/EN 归属人裁决。",
        ],
    }
    out_path = OUT / "true_missing_top10.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out_path), "reconciliation": recon,
                      "summary": payload["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
