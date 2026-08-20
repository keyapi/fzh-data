---
okf: v0.1
type: Reference
title: 赛狐皮壳共享库存代理 Agent Handoff
description: 三角类皮壳组合商品方案的快速接手入口、冻结边界和下一步沙盒动作。
---

# 赛狐皮壳共享库存代理 Agent Handoff

## 30 秒结论

- 当前是通途 + 赛狐并行期；通途仍是分公司普通仓库存事实源。
- 赛狐底层 `KS` 是有库存普通商品；皮壳 `PK#` 是 `KS x1` 的无库存组合商品。
- 这是销售库存代理，不是 BOM、不是 EN Product Bundle、不得走 TJ# 同步。
- 加工商品有独立库存且需要加工单，本阶段不用。
- 下一步只做一个 SKU、一个普通仓、一条皮壳 Listing 的沙盒。

完整原因、排除方案、成本风险和验收标准只读：

- [canonical 决策记录](../docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md)
- [模块文档索引](docs/index.md)

## 接手顺序

1. 读 canonical 决策记录，不从聊天摘要重建方案。
2. 让用户确认唯一沙盒范围；禁止自动扩大到全部三角 SKU。
3. 填一份 JSON 配置，先运行 `audit_sandbox.py`，默认只校验配置；加 `--live` 才进行赛狐只读回读。
4. 报告所有 matched/missing/blocked，不静默跳过。
5. 任何创建商品、在线配对、库存调整都属于后续写入步骤，必须再次确认。

## 冻结边界

- 不改 EN 客户物料号登记和销售订单交付形态脚本。
- 不创建 EN Product Bundle。
- 不把 FBA、退货仓、不良品仓并入普通仓共享池；只读审计会 blocked。
- 不把美中 `DANEEY` / `FZH-DANEEY` 主仓或成品仓默认当成三角皮壳共享池；通途另有皮壳仓库，须用户确认。
- 赛狐 `POLAND` 对应通途 covers 仓（`FZHPoland-covers` / `波兰-FZHPoland-covers`），不对应 `FZHPoland-finished`。只读审计对波兰成品仓名 `cautions`。
- 不假定 `TT123 + TT123-Cover` 就是同步公式；先验证占用和时序。
- 不承诺利润成本正确；必须用真实测试订单验证。
- 不调用 `SELLFOX_API/sellfox_combo_ops.py sync-combos` 创建本方案对象，该命令面向 EN TJ# 套件。

## 代码地图

- `audit_sandbox.py`：默认无写入；`--live` 只调用赛狐查询接口。FBA/退货/不良仓 blocked；名称含 DANEEY 且不含皮壳/cover 的仓、以及波兰成品仓名写入 `cautions`。加工商品计数读 `totalSize`。
- `tests/test_audit_sandbox.py`：配置和组合关系纯函数测试。
- `SELLFOX_API/client.py`：复用认证、签名和限流。
- `.agents/skills/sellfox-cover-inventory/SKILL.md`：触发词和路由。
