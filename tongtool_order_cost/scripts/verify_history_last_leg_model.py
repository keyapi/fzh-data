# -*- coding: utf-8 -*-
"""对「采纳 V3c（结构修复 + 分区优先 + 10/2 门槛）」这一结论做对抗性自检。

检查项：
1. 独立时间窗（训练 ≤2026-02 / 验证 2026-03~04）复核 V3 是否仍胜出，排除「在验证集上选模型」
2. 覆盖率对齐后再比精度，排除「V3 只是多覆盖了行」这一解释
3. 分解「老方式 ×件数」与「层级结构」各自的贡献
4. 确定性：同输入重复计算是否给出一致结果
5. 发布层的病态格子检查（样本数过小、极差过大）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost.history_last_leg_analysis import (
    PUBLISH_LEVELS,
    add_outlier_flags,
    build_package_observations,
    legacy_predict_fee_faithful,
    load_legacy_items,
    prepare_order_rows,
)
from tongtool_order_cost.model_variants import (
    MODERN_LEVELS,
    _predict_baseline,
    build_variant_tiers,
    error_metrics,
    predict_with_variant,
)

CACHE = ROOT / "out" / "monthly_orders_full.csv.gz"
EN_MAY = Path(r"D:/Work/王忠于/成本核算")
EN_OUT = "通途非FBA订单202605 EN估尾程 tongtool_order_costs_2026-06-02_13-49-05.707983.xlsx"
LATE = "只用尾程 通途非FBA订单202605 202607081128.xlsx"

print("=" * 72)
print("读取数据")
raw = pd.read_csv(CACHE, dtype=str)
rows = pd.concat([prepare_order_rows(f, m) for m, f in raw.groupby("月份")], ignore_index=True)
observations = add_outlier_flags(build_package_observations(rows))
legacy = load_legacy_items(ROOT / "out" / "hlf0001_items.csv.gz")


def build(name: str, training: pd.DataFrame):
    baseline = name == "V0_基线"
    tiers, _ = build_variant_tiers(
        training,
        levels=PUBLISH_LEVELS if baseline else MODERN_LEVELS,
        exclusive=baseline,
        credibility=name.startswith("V3b"),
        min_samples=30 if name in ("V0_基线", "V1b_结构_分区优先") else 5,
        min_months=2 if name in ("V0_基线", "V1b_结构_分区优先") else 1,
    )
    return tiers, baseline


def predict(group: pd.DataFrame, tiers: pd.DataFrame, baseline: bool) -> pd.Series:
    return _predict_baseline(group, tiers) if baseline else predict_with_variant(
        group, tiers, scheme="zone_first"
    )


NAMES = ["V0_基线", "V1b_结构_分区优先", "V3_低门槛5", "V3b_低门槛5_可信度"]

# ---------------------------------------------------------------- 1) 独立时间窗
print("=" * 72)
print("1) 独立时间窗：训练 ≤2026-02 / 验证 2026-03~04")
eligible = observations[observations["建模状态"] == "可建模"].copy()
train_a = eligible[eligible["月份"].astype(str) <= "202602"]
valid_a = eligible[eligible["月份"].astype(str).isin(["202603", "202604"])].copy()
valid_a["HLF0001"] = valid_a.apply(
    lambda r: legacy_predict_fee_faithful(legacy, r["国家"], r["通途SKU"], r["观察重量_kg"])[0], axis=1
)
print(f"   训练 {len(train_a)} / 验证 {len(valid_a)}")
print("   " + "HLF0001".ljust(22) + str(error_metrics(valid_a["观察费用"], valid_a["HLF0001"])))
for name in NAMES:
    tiers, baseline = build(name, train_a)
    pred = predict(valid_a, tiers, baseline)
    valid_a[f"pred_{name}"] = pred
    print("   " + name.ljust(22) + str(error_metrics(valid_a["观察费用"], pred)))

# ---------------------------------------------------------------- 2) 覆盖率对齐
print("=" * 72)
print("2) 覆盖率对齐：只比三个变体都给出预测的行（排除覆盖差异）")
train_b = eligible[eligible["月份"].astype(str) <= "202604"]
valid_b = eligible[eligible["月份"].astype(str) >= "202605"].copy()
preds = {}
for name in NAMES:
    tiers, baseline = build(name, train_b)
    preds[name] = predict(valid_b, tiers, baseline)
mask = pd.Series(True, index=valid_b.index)
for name in NAMES:
    mask &= preds[name] > 0
print(f"   对齐后行数 {int(mask.sum())} / {len(valid_b)}")
for name in NAMES:
    print("   " + name.ljust(22)
          + str(error_metrics(valid_b.loc[mask, "观察费用"], preds[name][mask])))

# ---------------------------------------------------------------- 3) 贡献分解
print("=" * 72)
print("3) 真实月初工件：分解「×件数」与「层级结构」各自的贡献")
en = pd.read_excel(EN_MAY / EN_OUT)
late = pd.read_excel(EN_MAY / LATE)
en["_pk"] = en["包裹号"].astype(str).str.strip()
en["_est"] = pd.to_numeric(en["历史预估尾程费用"], errors="coerce").fillna(0)
en["_qty"] = pd.to_numeric(en["发货数量"], errors="coerce").fillna(0)
unit = en.groupby("_pk").agg(老单件=("_est", "sum"), 件数=("_qty", "sum"))
late["_pk"] = late["包裹号"].astype(str).str.strip()
for c in ("物流商运费", "包裹总运费", "通途运费"):
    late[c] = pd.to_numeric(late[c], errors="coerce").fillna(0)
act = late.groupby("_pk").agg(
    包裹总运费=("包裹总运费", "max"), 物流商和=("物流商运费", "sum"), 通途和=("通途运费", "sum"))
act["实际"] = act["物流商和"]
act.loc[act["实际"] <= 0, "实际"] = act.loc[act["实际"] <= 0, "包裹总运费"]
act.loc[act["实际"] <= 0, "实际"] = act.loc[act["实际"] <= 0, "通途和"]
cmp = unit.join(act[["实际"]], how="inner")
cmp = cmp[(cmp["实际"] > 0) & (cmp["老单件"] > 0)]
# 老方式在包裹级：因 ×件数，单件价被乘了件数 → 拆回单件价即去掉该效应
cmp["老方式_去×件数"] = cmp["老单件"] / cmp["件数"]
for label, col in (("老方式(含×件数)", "老单件"), ("老方式(去掉×件数)", "老方式_去×件数")):
    print("   " + label.ljust(24) + str(error_metrics(cmp["实际"], cmp[col])))
print(f"   单件行数 {int((cmp['件数'] == 1).sum())} / 多件行数 {int((cmp['件数'] > 1).sum())}")

# ---------------------------------------------------------------- 4) 确定性
print("=" * 72)
print("4) 确定性：重复构造与预测是否完全一致")
t1, b1 = build("V3_低门槛5", train_b)
p1 = predict(valid_b, t1, b1)
t2, b2 = build("V3_低门槛5", train_b)
p2 = predict(valid_b, t2, b2)
print(f"   层表完全相同: {t1.equals(t2)}   预测完全相同: {bool((p1 == p2).all())}")

# ---------------------------------------------------------------- 5) 病态格子
print("=" * 72)
print("5) V3 发布层的样本分布与病态格子")
simple = t1[t1["匹配层级"] != "__none__"]
print(f"   层数 {len(simple)}   样本数分位 "
      f"{[int(simple['样本数'].quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)]}")
print(f"   样本数 <10 的层 {int((simple['样本数'] < 10).sum())}，"
      f"<5 的层 {int((simple['样本数'] < 5).sum())}")
if "可信度Z" in simple.columns:
    print(f"   可信度Z 分位 {[round(float(simple['可信度Z'].quantile(q)), 3) for q in (0.05, 0.5, 0.95)]}")
spread = (simple["P75"] / simple["P25"].replace(0, pd.NA)).dropna()
print(f"   P75/P25 比值分位 {[round(float(spread.quantile(q)), 2) for q in (0.5, 0.9, 0.99)]}  "
      f"最大 {round(float(spread.max()), 1)}")
worst = simple.nlargest(3, "样本数")[["匹配层级", "国家", "标准仓库", "标准渠道", "观察重量阶梯",
                                     "样本数", "中位数"]]
print("   样本最多的层：")
print(worst.to_string(index=False))
