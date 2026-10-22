---
okf: v0.1
type: Log
title: 审核记录（Codex1 审核负责人）
date: 2026-10-22
---

# 审核记录

| 日期 | 对象 | 复审轮次 | 结论 | 关键缺陷 |
|---|---|---|---|---|
| 10-21 | DN/WO/JC/SE v1 `22ae9a1e` | adapter | FAIL | 6 P1 + 3 P2（C1 抵消、DN join、UOM、SE 元数据/覆盖、C4） |
| 10-21 | v2 `49a142e0` | cross | FAIL | 2 P1 + 1 P2（SE 跨单位、finished 标志、JC 畸形） |
| 10-21 | v3 `e6b3cc9a` | cross | FAIL | 1 P2（嵌套 operations） |
| 10-21 | v4 `4b7ec55f` | cross | PASS | 非阻塞 P3（105 JC 组 vs 516 行） |
| 10-21 | 闸门 `be37645b` | review | FAIL | 重定向预读、先读后裁、停止绕过等 |
| 10-22 | 闸门 `ed6a7742` | review | FAIL | 重定向预读仍 16→0、watchdog、403 原子 |
| 10-22 | 闸门 `5300a6b0` | review | FAIL | 取消字节未入账、close 阻塞 |
| 10-22 | 闸门 `1fd196c8` | review | FAIL | 读异常释放预占 |
| 10-22 | 闸门 `ca27163c` | review | PASS | 放行阶段 1 |
| 10-22 | 库存代码 `cfca4c0c` | review | FAIL | 重导哈希、全仓标志、别名、回滚、锁 |
| 10-22 | `571929fa` | review | FAIL | A→B→失败重导 A 回滚 |
| 10-22 | `53291689` | review | PASS | 放行入库 |
| 10-22 | 归档器 1.0/1.2/1.3 | review ×3 | 1.3 PASS | tmp/锁/run-state；已真实归档 |
| 10-22 | 阶段 1 `ca27163c` 证据 | review | FAIL→PASS | 3,416 行、wo_uom_unresolved；修正后 PASS |
| 10-22 | SKU 审计 C `c583ace9` | review | PASS | 4,115 行/297 SKU；61/2/228/6 |
| 10-22 | B v1 证据 | review ×2 | FAIL | 范围错位（expand10 当主口径，trace 只有 5 SKU）；无映射 cover 写 0；缺 PO 行键/cover 仓键/逐文件 SO/源哈希；max/UOM/open_qty 结论过强 |
| 10-22 | B v2 证据 `611d9066` | review ×2 | PASS | lead+fresh 双审；5 trace 主口径 + 10 扩展分列；null/0 分离；PO 行键/215 SO/1,465 复算/源哈希 |
| 10-22 | B v2.1 UOM 注记 | targeted | 待复核 | 4 个主口径需求单位 unknown 的 note 改正；conversion_requirement=demand+stock UOM；evidence `a8b83618…` |

## 当前待审
- B v2.1（`2026-10-22-eta-cover-uom-evidence.md` + `evidence.json` sha256 `a8b83618…`）：
  v2 双审 PASS；仅 UOM 非阻塞注记已改，待 lead 定向复核。
