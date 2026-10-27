# -*- coding: utf-8 -*-
"""POLICY-RECONCILE v2（按复审 reject 返修）。

四项修正：
- F1：区分「目标档位 τ（分位）」「预测乘数（备货/预测）」「库存比值（平均库存/现行规则）」
  「目标倍数（v2 相对 97 天分位目标）」四个不同字段；**2.4–4.6× 是库存比值，不是预测乘数**；
- F2：删掉「预测完全正确 / 无误差上限 / 机制上限」的说法，改成
  「v2 未接入模型误差链，评价的是另一套历史经验分位政策」；
- F3：τ99 旧格子的 β 是 0.78–1.00、6 格有 5 格 ≥95%；8.8–40× 只是**部分高成本格**，不是普遍保证；
- F4：18 格合成 vs 6 格含误差证据分开列，并补逐源哈希。

不改主表、不改上游任何数字；只做对账表述与证据分列。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ANNEX = ("C:/Users/zhang/orca/workspaces/Cursor/replenishment-coordination-oct29/docs/"
         "research/supply-chain/2026-10-20/claude/control/reviews/"
         "2026-10-23-service-inventory-annex.md")
DIGEST = ("D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/"
          "reviews/2026-10-28-frepple-conversation-digest.md")

# F1：四个字段分开——目标档位 / 预测乘数 / 库存比值 / 目标倍数
METRICS = [
    dict(来源="既有：现行规则（正态+CV）", 目标档位="名义 95%", 预测乘数="—",
         库存比值="1.00×（基线）", 目标倍数="—", 实际服务="β 0.63–0.84",
         证据="annex §2.2 外层实测"),
    dict(来源="既有：经验分位 τ90", 目标档位="τ=90%", 预测乘数="1.6–4.5×",
         库存比值="0.9–4.6×", 目标倍数="—", 实际服务="β 0.61–0.90",
         证据="annex §2.2 六格（含预测误差）"),
    dict(来源="既有：经验分位 τ95", 目标档位="τ=95%", 预测乘数="2.2–13.8×",
         库存比值="1.3–14.2×", 目标倍数="—",
         实际服务="β 0.67–0.99（6 格只有 1 格 ≥95%）",
         证据="annex §2.2 六格（含预测误差）"),
    dict(来源="既有：经验分位 τ99", 目标档位="τ=99%", 预测乘数="4.3–57×",
         库存比值="2.3–41×", 目标倍数="—",
         实际服务="β 0.78–1.00（6 格有 5 格 ≥95%）",
         证据="annex §2.2 六格（含预测误差）"),
    dict(来源="既有：路径① 现实档（τ90–95）", 目标档位="τ=90–95%", 预测乘数="—",
         库存比值="2.4–4.6×", 目标倍数="—", 实际服务="β 0.83–0.91",
         证据="annex §4：2.4–4.6× 指平均库存相对现行规则的比值，不是预测乘数"),
    dict(来源="既有：路径② 硬上 99%", 目标档位="τ=99%", 预测乘数="4.3–57×",
         库存比值="8.8–40×（仅部分高成本格）", 目标倍数="—", 实际服务="β 0.96–1.00",
         证据="annex §4：8.8–40× 是路径②里的高成本格区间，不是所有格子的普遍保证"),
    dict(来源="v2：保守（参考）", 目标档位="—", 预测乘数="—（v2 不产生预测乘数）",
         库存比值="1.00×（相对本表 1×）", 目标倍数="1.0×",
         实际服务="β 0.7561 / CSL 0.7628", 证据="policy-options-v2（观测销售路径回放）"),
    dict(来源="v2：均衡（参考档）", 目标档位="—", 预测乘数="—",
         库存比值="1.80×（相对本表 1×）", 目标倍数="1.5×",
         实际服务="β 0.9235 / CSL 0.9063", 证据="policy-options-v2"),
    dict(来源="v2：服务优先", 目标档位="—", 预测乘数="—",
         库存比值="2.73×（相对本表 1×）", 目标倍数="2.0×",
         实际服务="β 0.9635 / CSL 0.9648", 证据="policy-options-v2"),
]

DIMENSIONS = [
    ("指标定义", "单位满足率 β + 周期不缺货率 α", "β + CSL", "定义一致"),
    ("目标的口径", "τ 是**分位档位**（经验分位），不是乘数", "S 取 97 天滚动销量和的**经验分位**",
     "两边都是「分位目标」，都不能读成倍数"),
    ("预测乘数", "备货量 ÷ 预测（1.6–4.5× / 2.2–13.8× / 4.3–57×）",
     "**不产生预测乘数**（v2 直接用观测销售路径，不经过预测）", "字段不同，不可互换"),
    ("库存比值", "平均库存 ÷ 现行规则（0.9–4.6× / 1.3–14.2× / 2.3–41×；路径① 2.4–4.6×）",
     "平均库存 ÷ 本表 1×（1.00 / 1.80 / 2.73×）", "基线不同：现行规则 vs 本表 1×"),
    ("目标倍数", "—（既有结论没有这一层）", "相对 97 天分位目标再乘 1.0 / 1.5 / 2.0",
     "v2 特有的第三层倍数，不能与预测乘数混用"),
    ("母集", "18 格合成 + 6 个真实格子（790/239 宇宙）",
     "478 个可评分键（= 557 合格 − 79 零销量），需求加权", "样本性质不同"),
    ("提前期", "L=60/90/120，R=7/30 混合", "固定 L=90、R=7", "v2 只跑一个交期"),
    ("误差链", "接入真实预测误差（q95 2.0–4.7、q99 13–47）",
     "**未接入模型误差链**：需求输入是观测销售本身，评价的是另一套历史经验分位政策",
     "这是最大差异；v2 的 fill 不能当「可实现服务」"),
    ("结论性质", "带预测误差的可实现服务区间", "另一套政策的回放结果", "两种结果不能互相替代"),
]

EVIDENCE = [
    dict(证据族="合成网格（理想前沿）", 格数=18, 是否有预测误差="否（假设预测准确）",
         β表现="按目标反解，β 等于目标", 用途="成本下限/理论参照",
         来源="annex §2.1"),
    dict(证据族="真实数据（含预测误差）", 格数=6, 是否有预测误差="是",
         β表现="τ90 0.61–0.90；τ95 0.67–0.99（1/6 ≥95%）；τ99 0.78–1.00（5/6 ≥95%）",
         用途="可实现服务与代价", 来源="annex §2.2"),
    dict(证据族="现实路径①（τ90–95）", 格数=6, 是否有预测误差="是", β表现="0.83–0.91",
         用途="推荐现实档", 来源="annex §4"),
    dict(证据族="v2 回放（观测销售路径）", 格数=1, 是否有预测误差="**未接入误差链**",
         β表现="0.7561 / 0.9235 / 0.9635（三档）", 用途="另一套政策的情景结果",
         来源="policy-options-v2"),
]


def _sha256(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "missing"


def _source_hashes(paths: dict[str, str]) -> dict:
    return {name: dict(path=path, sha256=_sha256(path), exists=Path(path).is_file())
            for name, path in paths.items()}


def write_memo(path: Path, metrics: pd.DataFrame, evidence: pd.DataFrame, hashes: dict,
               generated_at: str, status: str) -> None:
    lines = [
        "# 政策口径对账 v2（POLICY-RECONCILE）",
        "",
        f"生成时间：{generated_at}　｜　状态：**{status}**",
        "",
        "## 结论：两份文档测的不是同一件事",
        "",
        "- 既有结论（`2026-10-23-service-inventory-annex.md`）在**真实预测误差**下测：",
        "  备货要多备几倍（预测乘数）、平均库存是现行规则的几倍（库存比值），可兑现的 β 是多少；",
        "- v2 / 政策选项**未接入模型误差链**：需求输入是观测销售本身，评价的是"
        "**另一套历史经验分位政策**在不同目标倍数下的回放结果；",
        "- 因此 v2 的 fill 与既有 β 是两种不同政策的输出，**不能互相替代、也不能互相校验**。",
        "",
        "## 四个字段必须分开读（F1）",
        "",
        "| 字段 | 含义 | 既有结论 | v2 |",
        "|---|---|---|---|",
        "| 目标档位 τ | 经验分位的**分位点**（90/95/99%） | 90–95% 或 99% | 97 天分位目标 |",
        "| 预测乘数 | 备货量 ÷ 预测 | 1.6–4.5× / 2.2–13.8× / 4.3–57× | **不产生** |",
        "| 库存比值 | 平均库存 ÷ 基线 | 相对现行规则 0.9–4.6× / 1.3–14.2× / 2.3–41× | 相对本表 1×：1.00/1.80/2.73× |",
        "| 目标倍数 | 在分位目标上再乘几倍 | — | 1.0 / 1.5 / 2.0 |",
        "",
        "> **2.4–4.6× 是「平均库存相对现行规则」的比值**（路径①，τ90–95），不是预测量乘数；",
        "> τ 是分位档位，本身**不是倍数**。——这是 v1 表述里最容易被误读的一处，v2 已拆开。",
        "",
        "## 数字并列",
        "",
        "| 来源 | 目标档位 | 预测乘数 | 库存比值 | 目标倍数 | 实际服务 |",
        "|---|---|---|---|---|---|",
    ]
    for _, row in metrics.iterrows():
        lines.append(f"| {row['来源']} | {row['目标档位']} | {row['预测乘数']} | "
                     f"{row['库存比值']} | {row['目标倍数']} | {row['实际服务']} |")
    lines += [
        "",
        "## 需要纠正的两处旧表述（F2 / F3）",
        "",
        "**F2**：不再说「v2 假设预测完全正确」「是无误差上限」「是机制上限」。"
        "准确说法是：**v2 未接入模型误差链**，它评价的是另一套历史经验分位政策。"
        "既然误差链没接，就不存在「上界」这种导出结论。",
        "",
        "**F3**：τ99 的旧格子里 β 实测 **0.78–1.00，6 格中有 5 格 ≥95%**；"
        "**8.8–40× 只是路径②里的部分高成本格**，不是所有格子的普遍保证，"
        "也不能反过来读成「只要备 8.8–40 倍就一定能到 99%」。",
        "",
        "## 证据分列（F4）",
        "",
        "| 证据族 | 格数 | 预测误差 | β 表现 | 用途 |",
        "|---|---:|---|---|---|",
    ]
    for _, row in evidence.iterrows():
        lines.append(f"| {row['证据族']} | {row['格数']} | {row['是否有预测误差']} | "
                     f"{row['β表现']} | {row['用途']} |")
    lines += [
        "",
        "合成 18 格与真实 6 格必须分开引用：前者是「假设预测准确」的成本下限，"
        "后者才是带误差的可实现区间。v2 回放既不属于合成网格，也不属于误差链结果。",
        "",
        "## 给业务的一句建议",
        "",
        "**主线仍按既有结论：按角色分层 + 经验分位 τ90–95（平均库存约为现行规则的 2.4–4.6 倍），"
        "对外只能说「目标档位」，不能说「95% 兑现」**；v2 的三档只作「同一分位口径再加安全库存」"
        "的参考，且必须标注未接误差链。",
        "",
        "## 逐源哈希",
        "",
        "| 来源 | sha256 | 存在 |",
        "|---|---|---|",
    ]
    for name, info in hashes.items():
        lines.append(f"| {name} | `{info['sha256'][:32]}…` | {info['exists']} |")
    lines += [
        "",
        "## 边界",
        "",
        "- 两边都**不是 95% 承诺**；",
        "- 不改 r6/h180 决策包、不改政策选项与前沿的任何数字；",
        "- 老板简报口径由工头单独修正，本表不覆盖其表述。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build(policy_csv: str, out_dir: str, *, annex_path: str = ANNEX,
          digest_path: str = DIGEST, status: str = "pending") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    metrics = pd.DataFrame(METRICS)
    evidence = pd.DataFrame(EVIDENCE)
    dimensions = pd.DataFrame(DIMENSIONS, columns=["口径维度", "既有结论", "v2 / 政策选项", "差异说明"])
    metrics.to_csv(out / "reconcile_metrics.csv", index=False, encoding="utf-8-sig")
    evidence.to_csv(out / "reconcile_evidence.csv", index=False, encoding="utf-8-sig")
    dimensions.to_csv(out / "reconcile_dimensions.csv", index=False, encoding="utf-8-sig")

    hashes = _source_hashes({
        "annex": annex_path,
        "digest": digest_path,
        "policy_options_v2": policy_csv,
        "frontier_v2_by_key": ("D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                               "service-inventory-frontier-2026-10-28-v2/frontier_v2_by_key.csv"),
        "frontier_v2_sensitivity": ("D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                    "service-inventory-frontier-2026-10-28-v2/"
                                    "frontier_v2_sensitivity.csv"),
    })
    (out / "source_hashes.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    write_memo(out / "memo.md", metrics, evidence, hashes, generated_at, status)
    manifest = dict(
        schema="policy-reconcile/v2", generated_at=generated_at, status=status,
        sources=hashes, metrics=metrics.to_dict("records"),
        evidence=evidence.to_dict("records"),
        dimension_count=int(len(dimensions)),
        withdrawn=["预测完全正确", "无误差上限", "机制上限", "压交期比加库存划算"],
        fixes=dict(F1="目标档位/预测乘数/库存比值/目标倍数 四字段分开",
                   F2="改为「v2 未接入模型误差链，评价的是另一套历史经验分位政策」",
                   F3="τ99 β 0.78–1.00（5/6 ≥95%）；8.8–40× 仅部分高成本格",
                   F4="合成 18 格与真实 6 格分列 + 逐源哈希"),
        note="不改主表；两边都不是 95% 承诺",
    )
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="政策口径对账 v2")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--annex", default=ANNEX)
    parser.add_argument("--digest", default=DIGEST)
    args = parser.parse_args(argv)
    manifest = build(args.policy, args.out, annex_path=args.annex, digest_path=args.digest)
    print(json.dumps({k: manifest[k] for k in ("schema", "status", "fixes", "dimension_count")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
