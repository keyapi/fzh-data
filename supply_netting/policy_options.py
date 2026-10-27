# -*- coding: utf-8 -*-
"""政策选项表（P0，pending re-review）：把 v2 的 L×S 网格收成 3 个业务可选档。

**不改主表。** 只从 `service-inventory-frontier-2026-10-28-v2` 的网格里挑三个档，
补齐 CSL、相对 1× 的增量、缺货量与天数，并写一句取舍。全部数字直接取自 v2，
本模块不重算回放，只做聚合与取整。

口径提醒（写进 CSV 与 memo）：观测销售路径模拟，**不是承诺、不是采购量**；
不给业务做最终选择，只标推荐倾向与理由。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

STATUS = "pending re-review"
UOM_CANONICAL = ("D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/"
                 "claude/control/reference/UOM-CANONICAL.md")
UOM_CONFIRMATION = "已读 UOM-CANONICAL；个/套分列；TJ# 按套；PK# 按皮壳 1:1；未知单位不合计。"
DIGEST = ("D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/"
          "claude/control/reviews/2026-10-28-frepple-conversation-digest.md")
KNOWLEDGE_ALIGNMENT = [
    ("现行规则名义 95%", "实际 β 0.63–0.84",
     "本表「保守」档 fill 0.756 落在这个区间内，方向一致：名义目标不等于实际兑现"),
    ("经验分位 τ90–95", "实际 β 0.83–0.91，代价 2.4–4.6× 库存",
     "本表倍数是「相对 97 天分位目标」的 1.0/1.5/2.0×，与附件的「相对预测」倍数基不同；"
     "本表三档都低于该区间，说明本表**尚未覆盖到经验分位所需的量级**"),
    ("硬 95%", "需 τ99，8.8–40× 库存，多数业务不可接受",
     "本表「服务优先」fill 0.9635 **不能**读成「便宜地做到硬 95%」；口径不同，成本结论以附件为准"),
    ("MOQ", "15,230 个物料里 MOQ 非零只有 21 个；绍兴自有工厂无 MOQ 限制",
     "本表「无 MOQ」假设与之一致"),
    ("补货频率", "月补改周补", "本表复核周期 7 天，与周补一致"),
    ("SKU 分型/包装费", "按角色分型；包装费/运费/无角色 SKU 必须排除",
     "本表已检查 478 个键：无包装费/运费/无角色 SKU（`497268621` 等不在净额需求里）"),
]
ASSUMPTIONS_COMMON = ("提前期按设定值、复核 7 天、无 MOQ；需求取观测销售路径；"
                      "在途/PO 无 ETA 未计；服务档是目标库存的反解，不是承诺")

# 三个档：同一提前期（90 天）下比较库存策略，避免混入交期变量
TIERS = [
    dict(
        key="conservative", name="保守（控库存）", lead=90, level=0.90, multiplier=1.0,
        assumptions="维持现交期 90 天；只按 90% 目标备货，不额外加安全库存",
        trade_off="库存最省，但约 1/4 的需求拿不到货；适合现金流紧、缺货可后补的品类",
        leaning="不推荐作为默认",
    ),
    dict(
        key="balanced", name="均衡（推荐倾向）", lead=90, level=0.95, multiplier=1.5,
        assumptions="维持现交期 90 天；目标库存取 95% 分位并留 1.5× 缓冲",
        trade_off="fill 从 0.76 提到 0.92，代价是库存多约 1.7 万件；每多备 1 件换约 0.01 fill",
        leaning="**推荐倾向**：在不动交期的前提下，服务与库存的拐点就在这一档附近",
    ),
    dict(
        key="service_first", name="服务优先", lead=90, level=0.98, multiplier=2.0,
        assumptions="维持现交期 90 天；目标库存取 98% 分位并留 2× 缓冲",
        trade_off="fill 0.96、缺货天数降到 182，但库存要比 1× 多约 3.8 万件；边际收益已明显递减",
        leaning="只在缺货损失 > 库存成本的关键品类上考虑",
    ),
]


def _cell(by_key: pd.DataFrame, lead: int, level: float, multiplier: float,
          uom: str | None = None) -> dict:
    subset = by_key[(by_key["lead_days"] == lead) & (by_key["service_level"] == level)
                    & (by_key["target_multiplier"] == multiplier)]
    if uom is not None:
        subset = subset[subset["单位"] == uom]
    if subset.empty:
        raise ValueError(f"v2 网格里没有 L={lead} SL={level} ×{multiplier} 这一格")
    demand = float(subset["窗口需求"].sum())
    csl = float((subset["CSL"].fillna(0) * subset["窗口需求"]).sum() / demand) if demand else None
    return dict(
        keys=int(len(subset)),
        demand=demand,
        served=float(subset["满足"].sum()),
        lost=float(subset["缺货量"].sum()),
        lost_days=int(subset["缺货天数"].sum()),
        inventory=float(subset["平均库存"].sum()),
        fill_rate=float(subset["满足"].sum() / demand) if demand else None,
        csl=csl,
    )


def build_options(sensitivity_csv: str | Path, by_key_csv: str | Path) -> tuple[pd.DataFrame, dict]:
    by_key = pd.read_csv(by_key_csv)
    rows = []
    units = [u for u in sorted(by_key["单位"].dropna().unique()) if str(u).strip()]
    # UOM 口径：个/套分列，不跨单位相加（UOM-CANONICAL.md）
    for uom in units:
        baseline = _cell(by_key, 90, 0.90, 1.0, uom=uom)   # 同交期同单位 1× 基线
        for tier in TIERS:
            cell = _cell(by_key, tier["lead"], tier["level"], tier["multiplier"], uom=uom)
            delta = cell["inventory"] - baseline["inventory"]
            gain = (cell["fill_rate"] or 0) - (baseline["fill_rate"] or 0)
            if tier["key"] == "balanced":
                trade_off = (
                    f"fill 从 {baseline['fill_rate']:.2f} 提到 {cell['fill_rate']:.2f}，"
                    f"代价是平均库存多约 {delta:,.0f} {uom}"
                    + (f"（每多备 1,000 {uom} 约换 {gain / (delta / 1000):.3f} fill）"
                       if delta > 0 else "，与基线持平"))
            elif tier["key"] == "service_first":
                trade_off = (f"fill {cell['fill_rate']:.2f}、缺货天数降到 {cell['lost_days']}，"
                             f"但库存要比 1× 多约 {delta:,.0f} {uom}；边际收益已明显递减")
            else:
                trade_off = (f"库存最省（{cell['inventory']:,.0f} {uom}），但约 "
                             f"{(1 - (cell['fill_rate'] or 0)) * 100:.0f}% 的需求拿不到货；"
                             "适合现金流紧、缺货可后补的品类")
            rows.append({
                "单位": uom,
                "选项": tier["name"],
                "选项键": tier["key"],
                "提前期(天)": tier["lead"],
                "服务档": tier["level"],
                "目标倍数": tier["multiplier"],
                "涉及键数": cell["keys"],
                "fill_rate": round(cell["fill_rate"], 4),
                "CSL(需求加权)": round(cell["csl"], 4) if cell["csl"] is not None else None,
                "平均库存": round(cell["inventory"], 1),
                "相对同交期同单位1倍的增量": round(delta, 1),
                "缺货量": round(cell["lost"], 1),
                "缺货天数": cell["lost_days"],
                "窗口需求": round(cell["demand"], 1),
                "适用假设": tier["assumptions"],
                "取舍说明": trade_off,
                "推荐倾向": tier["leaning"],
                "状态": STATUS,
                "口径": "观测销售路径模拟；不是承诺、不是采购量",
                "UOM备注": "单键样本，仅示意" if cell["keys"] <= 1 else "",
            })
    frame = pd.DataFrame(rows)

    # 交期杠杆对照：同样服务档下把 L 从 90 压到 60 能省多少库存（只作 memo 论据）
    lever = []
    main_unit = units[0] if units else ""
    for uom in units:
        for level, multiplier in ((0.95, 1.5), (0.98, 2.0)):
            try:
                l90 = _cell(by_key, 90, level, multiplier, uom=uom)
                l60 = _cell(by_key, 60, level, multiplier, uom=uom)
            except ValueError:
                continue          # 网格未覆盖该格（部分数据/测试夹具）→ 跳过，不编造
            lever.append(dict(单位=uom, level=level, multiplier=multiplier,
                              inv_l90=round(l90["inventory"], 1),
                              inv_l60=round(l60["inventory"], 1),
                              saved=round(l90["inventory"] - l60["inventory"], 1),
                              fill_l90=round(l90["fill_rate"], 4),
                              fill_l60=round(l60["fill_rate"], 4)))
    main_baseline = _cell(by_key, 90, 0.90, 1.0, uom=main_unit) if main_unit else baseline
    meta = dict(
        uom_policy=dict(canonical=UOM_CANONICAL, confirmation=UOM_CONFIRMATION,
                        units=units, rule="个/套分列、不跨单位合计；TJ# 按套；PK# 按皮壳 1:1"),
        baseline=dict(unit=main_unit, fill_rate=round(main_baseline["fill_rate"], 4),
                      inventory=round(main_baseline["inventory"], 1),
                      lost=round(main_baseline["lost"], 1),
                      lost_days=main_baseline["lost_days"]),
        lead_time_lever=lever,
        assumptions_common=ASSUMPTIONS_COMMON,
        status=STATUS,
    )
    return frame, meta


def write_memo(path: Path, options: pd.DataFrame, meta: dict, generated_at: str,
               inputs: dict) -> None:
    first_unit = options["单位"].iloc[0]
    main = options[options["单位"] == first_unit].reset_index(drop=True)
    base, mid, top = main.iloc[0], main.iloc[1], main.iloc[2]
    lines = [
        "# 政策选项表（M2 / SC08）",
        "",
        f"生成时间：{generated_at}　｜　状态：**{STATUS}**",
        "",
        "## 一句话",
        "",
        f"以「{base['单位']}」为例：同一交期（{int(base['提前期(天)'])} 天）下，把目标库存从「"
        f"{int(base['服务档'] * 100)}% 档 ×{base['目标倍数']}」抬到「"
        f"{int(mid['服务档'] * 100)}% 档 ×{mid['目标倍数']}」，"
        f"fill rate 从 **{base['fill_rate']:.2f}** 到 **{mid['fill_rate']:.2f}**、"
        f"缺货天数从 {int(base['缺货天数']):,} 降到 {int(mid['缺货天数']):,}，代价是平均库存多约 "
        f"**{mid['相对同交期同单位1倍的增量']:,.0f} {base['单位']}**；再往「"
        f"{int(top['服务档'] * 100)}% 档 ×{top['目标倍数']}」推，库存要到 "
        f"**+{top['相对同交期同单位1倍的增量']:,.0f} {base['单位']}**"
        f"才再换 {top['fill_rate'] - mid['fill_rate']:.2f} fill——**在本表口径下，拐点在"
        f"「{mid['选项']}」这一档**（与附件「硬 95% 需 8.8–40×」不矛盾，两者倍数基不同）。",
        "",
        "> 口径：这是**观测销售路径模拟**，不是承诺、不是采购量；数字直接取自 frontier v2，"
        "本表只做聚合。**不替业务做最终选择**，只给推荐倾向。",
        "",
        "## 三档对照",
        "",
        "| 单位 | 选项 | 提前期 | 服务档×倍数 | fill_rate | CSL | 平均库存 | 相对 1× 增量 | 缺货量 | 缺货天数 | 备注 |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for _, row in options.iterrows():
        lines.append(f"| {row['单位']} | {row['选项']} | {row['提前期(天)']} | "
                     f"{row['服务档']}×{row['目标倍数']} | {row['fill_rate']} | "
                     f"{row['CSL(需求加权)']} | {row['平均库存']:,.0f} | "
                     f"{row['相对同交期同单位1倍的增量']:+,.0f} | {row['缺货量']:,.0f} | "
                     f"{row['缺货天数']} | {row['UOM备注']} |")
    lines += ["", "## 每档的适用假设与取舍", ""]
    for _, row in options.iterrows():
        lines.append(f"### [{row['单位']}] {row['选项']}")
        lines.append("")
        lines.append(f"- 假设：{row['适用假设']}")
        lines.append(f"- 取舍：{row['取舍说明']}")
        lines.append(f"- 倾向：{row['推荐倾向']}")
        lines.append("")
    lever = meta["lead_time_lever"]
    lines += [
        "## 交期杠杆（比加库存更便宜）",
        "",
        "| 单位 | 服务档×倍数 | 平均库存 L90 | 平均库存 L60 | 压交期可省 | fill L90 | fill L60 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in lever:
        lines.append(f"| {item.get('单位', '')} | {item['level']}×{item['multiplier']} | "
                     f"{item['inv_l90']:,.0f} | "
                     f"{item['inv_l60']:,.0f} | {item['saved']:,.0f} | "
                     f"{item['fill_l90']} | {item['fill_l60']} |")
    lines += [
        "",
        "把交期从 90 天压到 60 天，在同样服务档下平均库存可少约 "
        f"{lever[0]['saved']:,.0f}–{lever[-1]['saved']:,.0f} 件且 fill 基本持平，"
        "**说明压交期的性价比高于加库存**——但交期是供应链能力，不是本表能决定的。",
        "",
        "## 与既有结论对齐（frepple 对话知识清单）",
        "",
        f"来源：`{DIGEST}`。**本表不与它冲突，但口径不同，不能互相替代：**",
        "",
        "| 既有结论 | 本表的对应 |",
        "|---|---|",
    ]
    for topic, known, ours in KNOWLEDGE_ALIGNMENT:
        lines.append(f"| {topic}：{known} | {ours} |")
    lines += [
        "",
        "> 一句话：既有附件讲的是「相对预测要备几倍、硬 95% 有多贵」；本表讲的是"
        "「在 90 天提前期下，把 97 天分位目标再乘 1–2 倍，历史路径上能兑现多少」。",
        "> 两者方向一致（都要加库存、都有边际递减），但**倍数基不同、提前期不同**，",
        "> 不要拿本表的 0.96 去覆盖附件的「硬 95% 需 8.8–40×」。",
        "> **下一步：POLICY-RECONCILE** 统一两份文档的口径与对外表述。",
        "",
        "## UOM 口径（UOM-CANONICAL.md）",
        "",
        f"- 已读 `{UOM_CANONICAL}`；",
        f"- **{UOM_CONFIRMATION}**",
        "- 因此本表按 `单位` 分行输出（个/套各自一格），**没有跨单位合计**；",
        "- 只有 1 个键的单位（如 `套`）标注「单键样本，仅示意」，不能当政策依据；",
        "",
        "## 边界（必须随表一起读）",
        "",
        f"- {meta['assumptions_common']}；",
        "- 额外库存是**件数**，不是资金/预算，也不是采购量；",
        "- 样本为「校准段 ≥30 个有订单日」的 478 个键，历史稀疏的键未纳入；",
        "- 评估窗 2026-07-24 → 2026-10-26，只跑过一次历史路径，不做多路径置信区间；",
        f"- 状态 **{STATUS}**：本表在复审通过前不作为决策依据；不改 r6 / h180 决策包。",
        "",
        "## 输入",
        "",
        f"- 网格：`{inputs['sensitivity']}`（sha256 `{inputs['sensitivity_sha']}`）",
        f"- 逐键：`{inputs['by_key']}`（sha256 `{inputs['by_key_sha']}`）",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="政策选项表（三档，pending re-review）")
    parser.add_argument("--sensitivity", required=True)
    parser.add_argument("--by-key", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    frame, meta = build_options(args.sensitivity, args.by_key)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_dir / "policy_options.csv", index=False, encoding="utf-8-sig")

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    inputs = dict(sensitivity=str(args.sensitivity), by_key=str(args.by_key),
                  sensitivity_sha=sha(args.sensitivity), by_key_sha=sha(args.by_key))
    write_memo(out_dir / "memo.md", frame, meta, generated_at, inputs)
    (out_dir / "manifest.json").write_text(json.dumps(
        dict(generated_at=generated_at, status=STATUS, inputs=inputs,
             tiers=frame[["单位", "选项", "提前期(天)", "服务档", "目标倍数", "fill_rate",
                          "CSL(需求加权)", "平均库存", "相对同交期同单位1倍的增量"]]
             .to_dict("records"),
             knowledge_alignment=[dict(topic=t, known=k, ours=o)
                                  for t, k, o in KNOWLEDGE_ALIGNMENT],
             digest=DIGEST, next_step="POLICY-RECONCILE",
             meta=meta, note="观测销售路径模拟；不是承诺、不是采购量；不改主表"),
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(frame[["单位", "选项", "fill_rate", "CSL(需求加权)", "平均库存",
                 "相对同交期同单位1倍的增量", "缺货量", "缺货天数"]].to_string(index=False))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
