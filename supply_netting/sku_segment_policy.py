# -*- coding: utf-8 -*-
"""SKU-SEGMENT-POLICY：按「角色 × 形态」给服务档/ABC 映射（不是加库存，不是承诺）。

输入
- `sku_classification_by_role_20261027.csv`（PR #319 的分型名单：角色 + 形态 + 销量）
- forecast `forecast_sku_summary.parquet`（`forecast_eligible` 与 `tongtool_sku → canonical_sku`）
- h180 决策包的 `canonical_sku` 集合（净额可覆盖的 SKU）

口径（UOM-CANONICAL + frepple digest §3）
- 排除包装费/运费/无角色 SKU（本名单里 0 条，规则照做并留证）；
- **皮壳不独立定档**：按对应成品/BOM 的档位执行，不能当独立成品判死库存；
- 服务档是「经验分位目标档（τ）」，**不是 95% 承诺**；本轮只给映射，不改任何数量。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

VOID_ROLES = {"", "无角色", "包装费", "运费", "nan", "None"}
FEE_KEYWORDS = ("包装费", "运费", "礼盒包", "包装材料费", "paper fee", "shipping fee")
NORMAL_FORMS = ("正常", "正常(断货/季节干扰)")

# 角色 × 形态 → (服务档, τ 目标, 依据)
POLICY = {
    ("成品", "正常"): ("A", 0.95, "主线成品；按经验分位 τ95 目标执行"),
    ("成品", "正常(断货/季节干扰)"): ("A", 0.95, "形态看似正常但受断货/季节干扰，先按 A 执行并复核"),
    ("成品", "慢销"): ("B", 0.90, "销量低但稳定，降到 τ90 控制库存"),
    ("成品", "长尾/间歇"): ("C", 0.85, "间歇需求，接受较低服务；缺货可后补"),
    ("成品", "短史/新品"): ("观察", None, "历史不足，先攒数据，暂不定服务档"),
    ("半成品", "正常"): ("B", 0.90, "跟组装计划走，作支撑角色，不单独拉高服务"),
    ("半成品", "正常(断货/季节干扰)"): ("B", 0.90, "跟组装计划走，需复核干扰原因"),
    ("半成品", "慢销"): ("B", 0.90, "跟组装计划走"),
    ("半成品", "长尾/间歇"): ("C", 0.85, "跟组装计划走；长尾不单独备货"),
    ("半成品", "短史/新品"): ("观察", None, "历史不足，先攒数据"),
}
COVER_POLICY = ("跟随成品/BOM", None,
                "皮壳不是独立成品（PK# → KS x1 组合代理，不是套件）；"
                "按对应成品/BOM 的档位执行，不得单独判死库存")


def load_classification(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(path)
    raw["sku"] = raw["sku"].astype(str)
    role = raw["role"].fillna("").astype(str).str.strip()
    is_fee = raw["sku"].str.contains("|".join(FEE_KEYWORDS), case=False, na=False)
    is_numeric = raw["sku"].str.fullmatch(r"\d+").fillna(False)
    excluded = raw[(~role.isin(VOID_ROLES) & ~is_fee & ~is_numeric)]
    dropped = raw[~raw.index.isin(excluded.index)].copy()
    if len(dropped):
        dropped["exclude_reason"] = [
            "无角色" if not str(r).strip() else ("费用/包装类 SKU" if fee else "纯数字 SKU")
            for r, fee in zip(dropped["role"].fillna(""), dropped["sku"].str.contains(
                "|".join(FEE_KEYWORDS), case=False, na=False))
        ]
    return excluded.reset_index(drop=True), dropped.reset_index(drop=True)


def map_policy(frame: pd.DataFrame) -> pd.DataFrame:
    def lookup(row):
        if str(row["role"]) == "皮壳":
            return COVER_POLICY
        return POLICY.get((str(row["role"]), str(row["cls"])),
                          ("观察", None, "未覆盖的角色×形态组合，先按观察处理"))

    resolved = [lookup(row) for _, row in frame.iterrows()]
    frame = frame.copy()
    frame["服务档"], frame["τ目标"], frame["依据"] = zip(*resolved)
    return frame


def build(classification_csv: str | Path, forecast_parquet: str | Path,
          netting_parquet: str | Path) -> dict:
    classified, excluded = load_classification(classification_csv)
    classified = map_policy(classified)

    forecast = pd.read_parquet(forecast_parquet)
    forecast = forecast[["tongtool_sku", "canonical_sku", "forecast_eligible"]].dropna(
        subset=["canonical_sku"])
    netting_skus = set(pd.read_parquet(netting_parquet)["canonical_sku"].astype(str))

    joined = classified.merge(forecast, left_on="sku", right_on="tongtool_sku", how="left")
    joined["in_forecast"] = joined["canonical_sku"].notna()
    joined["in_netting"] = joined["canonical_sku"].astype(str).isin(netting_skus)
    joined["triple"] = joined["in_forecast"] & joined["in_netting"] & \
        joined["forecast_eligible"].fillna(False).astype(bool)

    total_sales = float(classified["total"].sum())
    matrix = (classified.groupby(["role", "cls", "服务档", "τ目标"], dropna=False)
              .agg(SKU数=("sku", "size"), 销量=("total", "sum"))
              .reset_index())
    matrix["SKU占比"] = (matrix["SKU数"] / len(classified) * 100).round(2)
    matrix["销量占比"] = (matrix["销量"] / total_sales * 100).round(2)
    matrix["依据"] = [POLICY.get((r, c), COVER_POLICY)[2] for r, c in
                      zip(matrix["role"], matrix["cls"])]

    cover_first = "跟随成品/BOM"
    role_summary = (classified.groupby("role")
                    .agg(SKU数=("sku", "size"), 销量=("total", "sum")).reset_index())
    role_summary["SKU占比"] = (role_summary["SKU数"] / len(classified) * 100).round(2)
    role_summary["销量占比"] = (role_summary["销量"] / total_sales * 100).round(2)
    role_summary["主推服务档"] = [
        cover_first if r == "皮壳" else POLICY.get((r, "正常"), ("观察",))[0]
        for r in role_summary["role"]]

    intersection = (joined.groupby("role")
                    .agg(SKU数=("sku", "size"), 命中预测与净额=("triple", "sum"),
                         命中销量=("total", lambda s: float(s[joined.loc[s.index, "triple"]].sum())))
                    .reset_index())
    context = dict(
        classified_skus=int(len(classified)),
        excluded_skus=int(len(excluded)),
        total_sales=round(total_sales, 1),
        matched_to_forecast=int(joined["in_forecast"].sum()),
        in_netting=int(joined["in_netting"].sum()),
        triple=int(joined["triple"].sum()),
        triple_sku_share=round(float(joined["triple"].mean() * 100), 2),
        triple_sales_share=round(float(joined.loc[joined["triple"], "total"].sum()
                                         / total_sales * 100), 2),
        role_sales_share={str(k): round(float(v / total_sales * 100), 2)
                          for k, v in classified.groupby("role")["total"].sum().items()},
        role_sku_share={str(k): round(float(v / len(classified) * 100), 2)
                        for k, v in classified["role"].value_counts().items()},
        digest_reference={"皮壳": "1,810 SKU / 80.3% / 88.2% 销量",
                          "成品": "352 / 15.6% / 7.8%",
                          "半成品": "93 / 4.1% / 4.7%",
                          "note": "本名单实测皮壳 1,808 个（差 2 个），销量占比 87.5%，"
                                  "其余两项与 digest 一致"},
        uom_confirmation="已读 UOM-CANONICAL；个/套分列；TJ# 按套；PK# 按皮壳 1:1；未知单位不合计。",
        disclaimer="服务档是经验分位目标档（τ），不是 95% 承诺；本表不给补货量、不改主表",
    )
    return dict(classified=classified, excluded=excluded, matrix=matrix,
                role_summary=role_summary, intersection=intersection, context=context)


def write_report(path: Path, data: dict, generated_at: str, sources: dict) -> None:
    ctx = data["context"]
    lines = [
        "# SKU 分型政策映射（SKU-SEGMENT-POLICY）",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 一句话",
        "",
        f"分型名单 {ctx['classified_skus']:,} 个 SKU 里，皮壳占 {ctx['role_sku_share'].get('皮壳')}% SKU / "
        f"{ctx['role_sales_share'].get('皮壳')}% 销量，但它**不是独立成品**——服务档按对应成品/BOM 走；"
        f"真正能直接套政策的是「预测可评 ∩ 净额可覆盖」的 **{ctx['triple']:,} 个 SKU**"
        f"（{ctx['triple_sku_share']}% SKU / {ctx['triple_sales_share']}% 销量）。",
        "",
        "> 服务档是**经验分位目标档（τ）**，不是 95% 承诺；本表只给映射，不给补货量、不改主表。",
        "",
        "## 排除规则（包装费/运费/无角色）",
        "",
        f"- 规则：角色为空/无角色、SKU 名含「包装费/运费/礼盒包」、或 SKU 是纯数字 → 排除；",
        f"- 本名单实际排除 **{ctx['excluded_skus']}** 条"
        "（digest 提到的 `497268621`「礼盒包装费」不在本名单里，规则仍保留以便下次名单复用时生效）。",
        "",
        "## 角色 × 形态 → 服务档",
        "",
        "| 角色 | 形态 | 服务档 | τ 目标 | SKU 数 | SKU 占比 | 销量占比 | 依据 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for _, row in data["matrix"].iterrows():
        tau = "" if pd.isna(row["τ目标"]) else f"{row['τ目标']:.2f}"
        lines.append(f"| {row['role']} | {row['cls']} | {row['服务档']} | {tau} | "
                     f"{row['SKU数']} | {row['SKU占比']}% | {row['销量占比']}% | {row['依据']} |")
    lines += [
        "",
        "### 皮壳为什么不单独定档",
        "",
        "- 皮壳是 `PK# → KS x1` 的组合代理（不是 EN Product Bundle，也不是「套」）；",
        "- 服务档跟对应成品/BOM 走：成品到多少服务，皮壳就按同一档备；",
        "- 因此**不能按皮壳自身销量判死库存**，也不能把皮壳当独立成品排服务档；",
        "- 半成品跟组装计划走，作为支撑角色取 B（τ90）。",
        "",
        "## 各角色汇总",
        "",
        "| 角色 | SKU 数 | SKU 占比 | 销量 | 销量占比 | 主推档位 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for _, row in data["role_summary"].iterrows():
        lines.append(f"| {row['role']} | {row['SKU数']} | {row['SKU占比']}% | "
                     f"{row['销量']:,.0f} | {row['销量占比']}% | {row['主推服务档']} |")
    lines += [
        "",
        "## 与 forecast_eligible ∩ netting_eligible 的交集",
        "",
        "映射链：分型名单的 `sku` 是通途 SKU → 预测表 `tongtool_sku → canonical_sku` → 决策包的 `canonical_sku`。",
        "",
        "| 角色 | 分型 SKU | 命中预测∩净额 | 命中销量 |",
        "|---|---:|---:|---:|",
    ]
    for _, row in data["intersection"].iterrows():
        lines.append(f"| {row['role']} | {row['SKU数']} | {row['命中预测与净额']} | "
                     f"{row['命中销量']:,.0f} |")
    lines += [
        "",
        f"- 分型名单 {ctx['classified_skus']:,} → 命中预测 {ctx['matched_to_forecast']:,}"
        f" → 命中净额 {ctx['in_netting']:,} → **三重交集 {ctx['triple']:,}**"
        f"（{ctx['triple_sku_share']}% SKU / {ctx['triple_sales_share']}% 销量）；",
        "- 没进交集的 SKU 分两类：预测不可评（短史/新品等）与不在净额键里；"
        "对这些 SKU **本表只给观察态，不定服务档**。",
        "",
        "## 与既有结论的关系",
        "",
        "- 分档只决定「用哪个 τ 目标」，不改变 POLICY-RECONCILE 的结论：",
        "  经验分位 τ90–95 需要 2.4–4.6× 预测，硬 95% 需 8.8–40×；",
        "- 本表的 A/B/C 是**档位选择**，不是覆盖率承诺；对外不得表述为「做到 95%」。",
        "",
        "## UOM 口径",
        "",
        f"- {ctx['uom_confirmation']}",
        "- 本表按 SKU 计数与销量汇总，不涉及跨单位数量相加。",
        "",
        "## 输入",
        "",
        f"- 分型名单：`{sources['classification']}`（sha256 `{sources['classification_sha']}`）",
        f"- 预测：`{sources['forecast']}`",
        f"- 净额键：`{sources['netting']}`",
        "",
        "## 边界",
        "",
        "- 不改 r6 / h180 决策包与任何政策表；不给补货量；",
        "- 分型名单基于全渠道 45 个月，进政策执行前必须走 `forecast_eligible ∩ netting_eligible`；",
        "- 未 push。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SKU 分型政策映射")
    parser.add_argument("--classification", required=True)
    parser.add_argument("--forecast", required=True)
    parser.add_argument("--netting", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    data = build(args.classification, args.forecast, args.netting)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    data["matrix"].to_csv(out_dir / "segment_policy_matrix.csv", index=False,
                          encoding="utf-8-sig")
    data["role_summary"].to_csv(out_dir / "role_summary.csv", index=False, encoding="utf-8-sig")
    data["excluded"].to_csv(out_dir / "excluded_skus.csv", index=False, encoding="utf-8-sig")
    data["intersection"].to_csv(out_dir / "intersection_summary.csv", index=False,
                                encoding="utf-8-sig")
    data["classified"].to_csv(out_dir / "sku_policy_by_sku.csv", index=False,
                              encoding="utf-8-sig")

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    sources = dict(classification=str(args.classification),
                   classification_sha=sha(args.classification),
                   forecast=str(args.forecast), netting=str(args.netting))
    write_report(out_dir / "report.md", data, generated_at, sources)
    (out_dir / "manifest.json").write_text(json.dumps(dict(
        generated_at=generated_at, sources=sources, context=data["context"],
        note="服务档是 τ 目标档不是承诺；不改主表"), ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(json.dumps(data["context"], ensure_ascii=False, indent=1))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
