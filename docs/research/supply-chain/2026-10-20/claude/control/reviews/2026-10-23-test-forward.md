---
okf: v0.1
type: Review
title: forward-net TDD 验收例（红灯先行，未改实现）
date: 2026-10-23
owner: claude-worker
status: 完成；26 条断言；12 PASS / 14 RED（预期）/ 0 意外失败；forward_net.py 未改
artifacts:
  - experiments/business_phase/test_forward_net.py
---

# forward-net TDD 验收例

> 按 `PROJECT_ROADMAP.md`「核心验收例」六域写成可执行断言。**先写测试、未修实现**：
> `forward_net.py` 一个字没动，红灯是当前实现的真实状态，不是测试写错。

**运行方式**

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py
uv run python -m pytest docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py -q
```

**结果**：`PASS 12 / RED(expected) 14 / UNEXPECTED FAIL 0 / total 26`
（pytest 口径：14 failed、13 passed；14 个 failed 与上面的 RED 一一对应。）

沿用项目既有测试风格（`experiments/pb_stockout/test_censored_loss.py` 的 `check()` 清单）并兼容 pytest，
没有引入新框架；全部为固定合成小例，不连库、不连生产。

## 逐条清单

| # | 域 | 断言 | 现状 |
|---|---|---|---|
| 1 | SO/预测冲减 | F=100、SO=20（同窗）、库存 80 → 缺口 **20** | **RED**：现实现 `max(0,100−20−80)=0` |
| 2 | SO/预测冲减 | SO 不在预测内 → 需求 120、缺口 40 | **RED**：现实现没有"另加"概念，得 20 |
| 3 | SO/预测冲减 | available 已扣占用 → 不得再扣 SO | **RED**：同上，重复扣，得 0 |
| 4 | SO/预测冲减 | 记录现实现对 roadmap 例**无条件得 0** | PASS（红灯记录） |
| 5 | 时间账 | 快照 10/22、运行 10/23、日耗 10 → 期初 70 | **RED**：现实现未扣当天消耗（80） |
| 6 | 时间账 | 10/22→11/30 共 40 天，需求 40 | **RED**：现实现按整月算，得 41 |
| 7 | 时间账 | 超期/无 ETA 供应不得计入 | **RED**：现实现一并计入 |
| 8 | 时间账 | 部分签收 40 + 在途 60 = 100（同一批） | **RED**：现实现相加为 200 |
| 9 | 时间账 | 未来取消 30 → 供应 70 | **RED**：现实现无取消概念（100） |
| 10 | 时间账 | 最早缺口 10 不得被期末 +50 掩盖 | **RED**：现实现跨期净额得 40 |
| 11 | 供应数量 | 一个 DN 五个号 → 只算 2 件 | PASS |
| 12 | 供应数量 | 一个号多 DN → 不复制数量 | PASS |
| 13 | 供应数量 | 部分签收 + 在途不重复 | PASS |
| 14 | 供应数量 | 父已提交、子表 docstatus=0 → 排除 | PASS |
| 15 | 供应数量 | 退货冲减（10−4=6） | PASS |
| 16 | 供应数量 | 共享料不得均摊 | **RED**：无显式分配规则 |
| 17 | 未知/SKU×仓 | 缺库存 = unknown，不得自动 0 | **RED**：现实现当 0 |
| 18 | 未知/SKU×仓 | 缺 UOM/物料/ETA → 阻断 | **RED**：未阻断 |
| 19 | 未知/SKU×仓 | 同 SKU 不同仓不互抵（10 / 0） | **RED**：现实现按 SKU 合计得 40 |
| 20 | 未知/SKU×仓 | 已证零销售 ≠ 源缺失 | PASS |
| 21 | 未知/SKU×仓 | 缺值不静默当 0，且须输出 unknown 计数 | **RED**：现实现无 unknown 计数 |
| 22 | 预测评估 | 只用切点前信息；追加未来证据不改历史预测 | PASS |
| 23 | 预测评估 | 同训练窗 → 同预测 | PASS |
| 24 | 概率与政策 | Fill rate = 90/100 = 0.9 可手算 | PASS |
| 25 | 概率与政策 | CSL = P(D≤8) = 9/11 可手算 | PASS |
| 26 | 概率与政策 | 累计分位数 ≠ 逐月相加（手算 **16** vs 相加 18） | PASS |

## 红灯要点（当前实现的真实缺陷，待 301 返修清单到位再改）

1. **SO 双重冲减**：把"预测内已含的 SO"再减一次，roadmap 的标准例直接得 0 缺口。
2. **时间账**：不扣快照日到运行日的消耗；跨月按"整月"而不是实际天数。
3. **供应**：无 ETA 的 PO/在途一律计入；分批接收与在途重复相加；未来取消不处理。
4. **期末盈余掩盖最早缺口**：跨期净额把月 1 的缺口吃掉。
5. **未知当 0**：缺库存/单位/物料/ETA 不阻断，合计里也不保留 unknown 计数。
6. **仓间互抵**：同 SKU 多仓按合计求缺口，违背"同仓"口径。
7. **共享料均摊**：没有显式分配规则。

## 边界

- 未修改 `forward_net.py`；未 commit / push；未跑 `update_index.py`。
- 测试只用合成小例；不读数据库、不连生产。
- 14 条 RED 是**预期**状态，不是回归；转绿需要实现修复（等 301 返修清单）。
