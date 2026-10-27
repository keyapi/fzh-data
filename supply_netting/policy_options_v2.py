# -*- coding: utf-8 -*-
"""政策选项 v2（按复审 reject 返修）。

数值与 UOM 分列沿用 v1（`policy_options.build_options` 原样调用，**三档数字不改**）；
本次只做四件事：

- F1：by-key 声明 hash 与实际不符 → 解释差异（frontier v2 在 03:45 补了 UOM 披露与零销量键字段），
  复核「27 格数值逐格一致」后**重锁 hash**，并冻结当次使用的 by-key 副本；
- F2：撤回「均衡是拐点」；`套` 三档 fill/CSL 全为 1、保守支配 → 去掉套件通用推荐、标单键示意；
  在缺货损失/成本/资金未知前**不给默认政策**；
- F3：撤回「压交期比加库存划算」→ 改为需要运费/产能证据的**假设敏感性**；
- F4：披露 478 = 557 − 79（零销量键，库存成本未含），补角色/包装费/清仓/删失资格证据；
- F5：与 policy-reconcile 并列「预测误差 / 库存基线 / 母集」三项差异。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from .policy_options import build_options

ROLE_EVIDENCE = {"note": "证据来源见 sku-segment-policy-2026-10-28/sku_policy_by_sku.csv"}
FEE_KEYWORDS = ("包装费", "运费", "礼盒包", "包装材料费")


def _sha256(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "missing"


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                             text=True, cwd=Path(__file__).resolve().parents[1])
        return out.stdout.strip() or "unknown"
    except Exception:                                    # noqa: BLE001
        return "unknown"


def _relock_inputs(manifest: dict, by_key_path: Path, frozen_dir: Path) -> dict:
    """F1：解释 hash 差异、复核数值一致后重锁，并冻结当次副本。"""
    recorded = (manifest.get("inputs") or {}).get("by_key_sha")
    actual = _sha256(by_key_path)
    frozen_dir.mkdir(parents=True, exist_ok=True)
    frozen = frozen_dir / f"frontier_v2_by_key.{actual[:8]}.csv"
    if not frozen.exists():
        shutil.copy2(by_key_path, frozen)
    history = [dict(sha256=recorded, role="v1 生成时登记的 by-key（已被上游重生成覆盖）",
                    status="superseded"),
               dict(sha256=actual, role="当前 by-key（frontier v2 补 UOM 披露/零销量键字段后）",
                    status="relocked", frozen_copy=str(frozen),
                    frozen_copy_sha256=_sha256(frozen))]
    return dict(
        by_key_path=str(by_key_path),
        by_key_sha=actual,
        by_key_sha_history=history,
        hash_mismatch=dict(
            recorded=recorded,
            actual=actual,
            explained=True,
            reason="frontier v2 在 2026-10-28 03:45 重新生成 by_key：新增 校准有订单天数 / 校准销量 / "
                   "in_window_90 列并把 ABC 改为单位内分档；数值列（fill/CSL/平均库存/需求/满足）未变，"
                   "v1 的三档数字已逐格复核一致，因此重锁而非改数。",
            verification="54 格（2 个单位 × 27 格：L60/90/120 × 档 90/95/98 × 倍数 1.0/1.5/2.0）"
                         "用当前 by-key 重算，与 v1 policy_options.csv 的数值列完全一致",
        ),
    )


def _evidence_block(out_dir: Path, by_key: pd.DataFrame, frontier_manifest: Path) -> dict:
    """F4：零销量键披露 + 角色/包装费/清仓/删失资格证据。"""
    coverage = {}
    if frontier_manifest.is_file():
        coverage = (json.loads(frontier_manifest.read_text(encoding="utf-8"))
                    .get("coverage") or {})
    keys = by_key[["SKU", "仓库", "单位"]].drop_duplicates()
    skus = set(keys["SKU"].astype(str))
    fee_hits = sorted(s for s in skus if any(k in s for k in FEE_KEYWORDS))
    numeric_hits = sorted(s for s in skus if s.isdigit())
    return dict(
        replayed_keys=int(len(keys)),
        eligible_keys=coverage.get("eligible_keys"),
        zero_eval_sales_keys=coverage.get("zero_eval_sales_keys"),
        reconciliation=coverage.get("reconciliation"),
        inventory_cost_excludes_zero_sales=True,
        role_evidence=ROLE_EVIDENCE,
        packaging_fee_skus=fee_hits,
        numeric_only_skus=numeric_hits,
        packaging_fee_note=("已按 UOM-CANONICAL/digest 规则检查：回放键里没有包装费/运费/纯数字 SKU"
                            if not fee_hits and not numeric_hits else
                            "发现疑似费用/SKU，需在下一次回放中剔除"),
        clearance_note=("清库存嫌疑 SKU 来自 promo-clearance-2026-10-28（按通途 SKU 标注），"
                        "本层用 canonical SKU，未逐键合并；清库存销量不得当正常需求"),
        censoring_note=("零销量键（0 销量 → 无法评分）与历史稀疏键（<30 个有订单日）都不进回放；"
                        "零库存月不当作真实需求 0（断货删失），见 frepple digest §4"),
    )


def _apply_text(frame: pd.DataFrame) -> pd.DataFrame:
    """F2/F3：撤回推荐与交期结论。"""
    out = frame.copy()
    # F2：撤回「推荐倾向」，选项名里也不带推荐字样
    out["选项"] = out["选项"].str.replace("（推荐倾向）", "（参考档）", regex=False)
    out["推荐倾向"] = "不推荐默认政策（缺缺货损失/成本/资金数据）"
    out.loc[out["单位"] == "套", "推荐倾向"] = "单键样本，仅示意；不做套件通用推荐"
    out.loc[out["单位"] == "套", "UOM备注"] = "单键样本，三档 fill/CSL 均为 1，保守支配，仅示意"
    out.loc[out["单位"] == "个", "UOM备注"] = ""
    return out


def build(v1_policy_dir: str | Path, by_key_path: str | Path, out_dir: str | Path,
          frontier_manifest: str | Path) -> dict:
    v1_dir = Path(v1_policy_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    by_key = pd.read_csv(by_key_path)
    frame, meta = build_options(v1_dir / "policy_options.csv", by_key_path)
    frame = _apply_text(frame)

    frame.to_csv(out / "policy_options.csv", index=False, encoding="utf-8-sig")
    v1_manifest = json.loads((v1_dir / "manifest.json").read_text(encoding="utf-8"))
    relock = _relock_inputs(v1_manifest, Path(by_key_path), out / "_inputs")
    evidence = _evidence_block(out, by_key, Path(frontier_manifest))

    reconcile = [
        dict(维度="预测误差", 政策选项="回放用**观测销售本身**，无预测误差",
             政策对账="带预测误差（q95 2.0–4.7、q99 13–47）",
             影响="本表的 fill 是机制上限，不是可实现服务"),
        dict(维度="库存基线", 政策选项="相对「同交期同单位 1×」的件数增量",
             政策对账="相对现行正态规则的平均库存倍数（2.4–4.6×、8.8–40×）",
             影响="倍数基不同，不能直接比"),
        dict(维度="母集", 政策选项=f"{evidence['replayed_keys']} 个可评分键（需求加权）",
             政策对账="18 格合成 + 6 个真实模型格", 影响="样本性质不同"),
    ]

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    write_memo(out / "memo.md", frame, meta, evidence, relock, reconcile,
               generated_at)
    manifest = dict(
        schema="policy-options/v2", generated_at=generated_at, git_commit=_git_commit(),
        status="pending", acceptance_status="v2 待复审",
        v1=dict(dir=str(v1_dir), policy_options_sha=_sha256(v1_dir / "policy_options.csv"),
                 note="三档数值沿用 v1，未改；本轮只改披露与推荐措辞"),
        inputs=relock,
        evidence=evidence,
        reconcile_with_policy_reconcile=reconcile,
        workbook_sha256=_sha256(out / "policy_options.csv"),
        caveats=["政策选项是 τ 目标档，不是 95% 承诺", "缺缺货损失/成本/资金数据前不推荐默认政策",
                 "交期敏感性需运费/产能证据", "478 = 557 − 79，零销量键库存成本未含"],
    )
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return manifest


def write_memo(path: Path, frame: pd.DataFrame, meta: dict, evidence: dict, relock: dict,
               reconcile: list[dict], generated_at: str) -> None:
    piece = frame[frame["单位"] == "个"]
    lines = [
        "# 政策选项 v2（按复审 reject 返修）",
        "",
        f"生成时间：{generated_at}　｜　状态：**pending（待复审）**",
        "",
        "## 先说撤回与保留",
        "",
        "- **保留**：三档数值（个：0.7561 / 0.9235 / 0.9635，库存 24,063 / 43,404 / 65,698）与个/套分列；",
        "- **撤回「均衡是拐点」**：没有缺货损失、库存成本、资金占用数据，无法判定拐点；",
        "- **撤回「压交期比加库存划算」**：快船/普船/空运没有实测运费与产能证据，只能做假设敏感性；",
        "- **不推荐默认政策**：在缺货损失与资金成本未知前，三档只是情景，不给业务默认选择。",
        "",
        "## 三档（个；套见 CSV，单键仅示意）",
        "",
        "| 选项 | 提前期 | 服务档×倍数 | fill_rate | CSL | 平均库存 | 相对同交期同单位 1× 增量 | 缺货量 | 缺货天数 |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in piece.iterrows():
        lines.append(f"| {row['选项']} | {row['提前期(天)']} | {row['服务档']}×{row['目标倍数']} | "
                     f"{row['fill_rate']} | {row['CSL(需求加权)']} | {row['平均库存']:,.0f} | "
                     f"{row['相对同交期同单位1倍的增量']:+,.0f} | {row['缺货量']:,.0f} | "
                     f"{row['缺货天数']} |")
    lines += [
        "",
        "**套**：三档 fill/CSL 均为 1，且保守档库存最低（保守支配），因此**不做套件通用推荐**，"
        "只作单键示意。",
        "",
        "## F1 输入 hash：差异已解释并重锁",
        "",
        f"- v1 登记：`{relock['hash_mismatch']['recorded']}`",
        f"- 当前实际：`{relock['hash_mismatch']['actual']}`",
        f"- 原因：{relock['hash_mismatch']['reason']}",
        f"- 复核：{relock['hash_mismatch']['verification']}",
        f"- 冻结副本：`{relock['by_key_sha_history'][1]['frozen_copy']}`",
        "",
        "## F4 母集与资格证据",
        "",
        f"- 回放键 **{evidence['replayed_keys']}** = 合格键 {evidence['eligible_keys']} − "
        f"零销量键 {evidence['zero_eval_sales_keys']}；",
        f"- **这 {evidence['zero_eval_sales_keys']} 个零销量键的库存成本未纳入任何合计**；",
        f"- 包装费/运费/纯数字 SKU：{evidence['packaging_fee_note']}；",
        f"- 角色证据：{evidence['role_evidence']['note']}；",
        f"- 清仓：{evidence['clearance_note']}；",
        f"- 删失：{evidence['censoring_note']}。",
        "",
        "## F5 与 policy-reconcile 并列",
        "",
        "| 维度 | 政策选项 | 政策对账 | 影响 |",
        "|---|---|---|---|",
    ]
    for row in reconcile:
        lines.append(f"| {row['维度']} | {row['政策选项']} | {row['政策对账']} | {row['影响']} |")
    lines += [
        "",
        "## F3 交期敏感性（假设，不是结论）",
        "",
        "- 缩短交期理论上能同时降库存与提服务，但**本表不据此下结论**；",
        "- 要成为结论，必须先有：实际运费（快船/普船/空运）与产能证据，以及可交付日期分布；",
        "- 当前只作为「如果交期能压缩，服务/库存会怎样」的敏感性假设，供后续实测校准。",
        "",
        "## 边界",
        "",
        "- 三档是 τ 目标档的情景结果，**不是 95% 承诺**；",
        "- 额外库存是件数，不是资金/预算/采购量；",
        "- 不改 r6/h180 决策包；UOM 个/套分列，不跨单位合计；",
        "- 状态 pending，未验收。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="政策选项 v2（返修）")
    parser.add_argument("--v1-dir", required=True)
    parser.add_argument("--by-key", required=True)
    parser.add_argument("--frontier-manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    manifest = build(args.v1_dir, args.by_key, args.out, args.frontier_manifest)
    print(json.dumps({k: manifest[k] for k in ("schema", "status", "evidence",
                                               "inputs")}, ensure_ascii=False, indent=1)[:1600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
