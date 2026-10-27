# -*- coding: utf-8 -*-
"""POLICY-RECONCILE：把「既有 β/τ 结论」与「frontier v2 / 政策选项」对齐成一张表。

两边都不改、都不重算：
- 既有结论来自 SC08 服务—库存附件与 frepple 对话知识清单（数字是文档给的区间）；
- v2 / 政策选项的数字直接从 `policy-options-2026-10-28/policy_options.csv` 读，
  只取「个」这一组（套只有 1 个键，单列示意）。

输出：口径对照表 + 数字并列表 + 一页 memo。**两边都不是 95% 承诺。**
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

STATUS = "pending re-review"
ANNEX = ("SC08 服务—库存附件 / frepple 对话知识清单（β 0.63–0.84；τ90–95 0.83–0.91、"
         "2.4–4.6×；τ99 8.8–40×）")
V2_SOURCE = "frontier v2 / policy-options-2026-10-28（观测销售路径模拟）"

DIMENSIONS = [
    ("指标定义", "单位满足率 β（已满足/总需求）；α 按周期是否缺货",
     "同样用 β（满足/需求）与 CSL（无缺货复核周期占比）", "定义一致"),
    ("母集", "18 格合成网格 + 6 个真实格子（790 全量 / 239 可验证）",
     "478 个真实 SKU×仓×UOM 键（校准段 ≥30 个有订单日）",
     "既有是小样本模型格；v2 是 478 键的聚合，按需求加权"),
    ("提前期", "L=60/90/120，R=7/30 混合",
     "本表固定 L=90、R=7（周补）", "v2 只跑了 90 天，交期杠杆另表"),
    ("目标口径", "τ 是「相对预测的乘数」；τ90–95 指经验分位",
     "S 是「校准段 97 天滚动销量和的经验分位」，倍数相对该分位再乘 1.0/1.5/2.0",
     "**倍数基不同**：既有乘在预测上，v2 乘在已抬高的分位目标上"),
    ("基线", "现行规则（正态 + 变异系数），库存记 1.0×",
     "本表 1× = 「90% 档 ×1.0」的回放结果（平均库存 24,063 个）",
     "基线不是同一个东西，不能直接比倍数"),
    ("库存分母", "相对现行规则的平均库存倍数（2.4–4.6×、8.8–40×）",
     "相对「同交期同单位 1×」的平均库存增量（+19,341 / +41,635 个）",
     "既有是倍数，v2 是件数增量；v2 也可换算倍数≈1.8×/2.7×"),
    ("样本差异（关键）", "评审窗用**真实预测**，带预测误差尾巴（q95 2.0–4.7、q99 13–47）",
     "回放用的是**观测销售**本身，等于假设预测完全正确（不存在预测误差）",
     "**这是两边最大差异**：v2 是「政策机制上限」，不是真实预测下的兑现"),
    ("结论性质", "带预测误差的可实现服务；硬 95% 成本极高",
     "政策机制在历史路径上的上限表现", "方向一致，量级不可互换"),
]

EXISTING_NUMBERS = [
    dict(口径="现行规则（名义 95%）", 目标="名义 95%", 实际服务="β 0.63–0.84", 库存代价="1.0×（基线）"),
    dict(口径="经验分位 τ90–95", 目标="τ90–95", 实际服务="β 0.83–0.91", 库存代价="2.4–4.6×"),
    dict(口径="硬 95%（τ99）", 目标="τ99", 实际服务="β ≥95%", 库存代价="8.8–40×"),
]


def build(policy_csv: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    options = pd.read_csv(policy_csv, encoding="utf-8-sig")
    piecewise = options[options["单位"] == "个"].reset_index(drop=True)
    if piecewise.empty:
        piecewise = options.reset_index(drop=True)

    base_inventory = float(piecewise.iloc[0]["平均库存"])
    v2_rows = []
    for row in piecewise.to_dict("records"):
        inventory = float(row["平均库存"])
        level = int(float(row["服务档"]) * 100)
        v2_rows.append(dict(
            口径=f"{row['选项']}（{level}% 档 ×{row['目标倍数']}）",
            目标=f"{level}% 分位 ×{row['目标倍数']}",
            实际服务=(f"β {float(row['fill_rate']):.4f} / CSL "
                      f"{float(row['CSL(需求加权)']):.4f}"),
            库存代价=f"{inventory:,.0f} 个（≈{inventory / base_inventory:.2f}× 本表 1×）",
        ))
    table = pd.DataFrame(DIMENSIONS, columns=["口径维度", "既有结论（附件/共形）", "v2 / 政策选项",
                                              "差异说明"])
    numbers = pd.concat([pd.DataFrame(EXISTING_NUMBERS), pd.DataFrame(v2_rows)],
                        ignore_index=True)
    meta = dict(
        base_inventory=base_inventory,
        v2_tiers=[dict(option=r["口径"], fill=extract_fill(r), inventory=r["库存代价"])
                  for r in v2_rows],
        note="两边都不是 95% 承诺；v2 用观测销售（无预测误差），既有结论带预测误差",
    )
    return table, numbers, meta


def extract_fill(row: dict) -> float | None:
    text = str(row.get("实际服务", ""))
    for part in text.split("/"):
        part = part.strip()
        if part.startswith("β"):
            try:
                return float(part.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def write_memo(path: Path, numbers: pd.DataFrame, meta: dict, generated_at: str,
               sources: dict) -> None:
    piece = numbers[numbers["口径"].str.contains("保守|均衡|服务优先", regex=True)]
    base = piece.iloc[0]
    mid = piece.iloc[1] if len(piece) > 1 else base
    top = piece.iloc[2] if len(piece) > 2 else mid

    lines = [
        "# 政策口径对账（POLICY-RECONCILE）",
        "",
        f"生成时间：{generated_at}　｜　状态：**{STATUS}**",
        "",
        "## 结论：两份文档不矛盾，但**不能互相替代**",
        "",
        "- **既有结论**（" + ANNEX + "）讲的是「**带预测误差**时，",
        "  要兑现某档服务要备多少倍」；",
        "- **v2 / 政策选项**讲的是「**在预测完全正确**的观测销售路径上，",
        "  把目标库存再乘 1–2 倍，能兑现多少」；",
        "- 关键差异是**样本里有没有预测误差**：v2 回放用观测销售本身，",
        "  没有误差尾巴；既有结论是在真实预测的误差尾（q95 2.0–4.7、q99 13–47）下测的。",
        "  所以 **v2 的 0.96 是政策机制的上限，不是真实业务能拿到的服务**。",
        "",
        "## 数字并列",
        "",
        "| 来源 | 口径 | 目标 | 实际服务 | 库存代价 |",
        "|---|---|---|---|---|",
    ]
    for _, row in numbers.iterrows():
        lines.append(f"| {'既有' if row['口径'] in ('现行规则（名义 95%）', '经验分位 τ90–95', '硬 95%（τ99）') else 'v2'} "
                     f"| {row['口径']} | {row['目标']} | {row['实际服务']} | {row['库存代价']} |")
    lines += [
        "",
        "## 为什么看起来矛盾、其实不矛盾",
        "",
        f"1. **倍数基不同**：既有乘在「预测」上；v2 乘在「97 天分位目标」上，"
        f"而该目标本身已经把需求高分位算进去了。v2 的 1.5× 不等于附件的 1.5× 预测。",
        "2. **母集不同**：既有是 18 格合成 + 6 个模型格；v2 是 478 个真实键按需求加权聚合。",
        "3. **误差结构不同（决定性）**：v2 的路径就是观测销售，没有预测误差；"
        "既有结论的 β 是在预测误差下测的，所以天然更低。",
        "4. **库存分母不同**：既有是「相对现行规则的平均库存倍数」；"
        "v2 是「相对本表 1× 的件数增量」，两者不能直接换算成同一个倍数。",
        "",
        "## 给业务的一句可执行建议",
        "",
        f"**主线仍按既有结论走：按角色分层 + 经验分位 τ90–95（约 2.4–4.6× 预测）**，"
        f"把 v2 的 1.5×/2× 当作「同一分位口径下再加安全库存」的增量参考；"
        f"对外只能说「目标档位」，**不能说 95% 兑现**。",
        "",
        "## 必须同时声明的边界",
        "",
        "- 两份文档**都不是 95% 承诺**：既有是带误差的历史兑现区间，v2 是无误差的机制上限；",
        "- v2 的 0.9635 不能对外宣称「加 2 倍库存就能做到 95%」；",
        "- 额外库存是**件数**，不是资金/预算，也不是采购量；",
        "- 本表不改 r6 / h180 决策包，也不覆盖 policy-options 与 frontier v2 的产物。",
        "",
        "## 输入",
        "",
        f"- 政策选项：`{sources['policy']}`（sha256 `{sources['policy_sha']}`）",
        f"- 既有结论：{ANNEX}",
        "",
        "下一步：把本表的表述同步进 BOSS_BRIEF / 决策包说明页（由工头统一写）。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="政策口径对账")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    table, numbers, meta = build(args.policy)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "reconcile_dimensions.csv", index=False, encoding="utf-8-sig")
    numbers.to_csv(out_dir / "reconcile_numbers.csv", index=False, encoding="utf-8-sig")

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    sources = dict(policy=str(args.policy), policy_sha=sha(args.policy))
    write_memo(out_dir / "memo.md", numbers, meta, generated_at, sources)
    (out_dir / "manifest.json").write_text(json.dumps(dict(
        generated_at=generated_at, status=STATUS, sources=sources, meta=meta,
        note="两边都不是 95% 承诺；不改主表"), ensure_ascii=False, indent=1), encoding="utf-8")
    print(numbers.to_string(index=False))
    print("输出：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
