---
okf: v0.1
type: Reference
title: 赛狐皮壳共享库存代理 Agent Handoff
description: 三角类皮壳库存模型的快速接手入口、生命周期决策边界和两条沙盒验证链。
---

# 赛狐皮壳共享库存代理 Agent Handoff

## 30 秒结论

- 当前是通途 + 赛狐并行期；通途仍是分公司普通仓库存事实源。
- `PK#` 不天然必须是组合商品；当前现场只有一个未拆分数量池，所以并行期默认推荐 `KS` 普通库存 + `PK# -> KS x1` 组合代理。
- 这是销售库存代理，不是 BOM、不是 EN Product Bundle、不得走 TJ# 同步。
- 加工商品有独立库存且需要加工单，本阶段不用。
- 组合代理只解决扣同一仓 `KS` 数量。商品采购成本勾选、子件 FIFO 批次都**不能**替代 EN Tongtool Cost Review（通途 `-Cover`/`-Foam`/`-1`/`-2` + 交付形态切片）。赛狐没有部分成本定制。
- 同一通途数量不能完整同步给普通 `KS` 和普通 `PK#` 两个目标，否则重复承诺可售库存；一对多、多对一必须先定数量归属。
- 成本另走订单覆盖链：FBM 导入采购成本优先于仓单位成本和商品采购成本，但公开 OpenAPI 未找到写端点，先验证 Excel/UI。
- 下一步分两条：只读审计核对一个 SKU + 已确认皮壳仓；随后分别验证组合扣减、已有皮壳 FBM 订单成本导入。现在不必请井新下单。

完整原因、排除方案、成本风险和验收标准只读：

- [canonical 决策记录](../docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md)
- [模块文档索引](docs/index.md)

## 接手顺序

1. 读 canonical 决策记录，不从聊天摘要重建方案。
2. 让用户确认唯一沙盒范围；禁止自动扩大到全部三角 SKU。
3. 填一份 JSON 配置，先运行 `audit_sandbox.py`，默认只校验配置；加 `--live` 才进行赛狐只读回读。
4. 报告所有 matched/missing/blocked，不静默跳过。
5. 任何创建商品、在线配对、库存调整、测试下单都属于后续写入步骤，必须再次确认。
6. 不要用组合采购成本复选框或「子件仓成本出现」解释皮壳利润；对照 canonical「成本与利润风险」。

## 决策边界

- 不改 EN 客户物料号登记和销售订单交付形态脚本。
- 不创建 EN Product Bundle。
- 不把 FBA、退货仓、不良品仓并入普通仓共享池；只读审计会 blocked。
- 不把美中 `DANEEY` / `FZH-DANEEY` 主仓或成品仓默认当成三角皮壳共享池；通途另有皮壳仓库，须用户确认。
- 赛狐 `POLAND` 对应通途 covers 仓（`FZHPoland-covers` / `波兰-FZHPoland-covers`），不对应 `FZHPoland-finished`。只读审计对波兰成品仓名 `cautions`。
- 不假定 `TT123 + TT123-Cover` 就是同步公式；先验证占用和时序。
- 不承诺赛狐利润等于 EN Cost Review 皮壳切片；vanilla 赛狐预期对不上。不要发明赛狐后缀部分成本。
- 独立普通 `PK#` 只有在仓库分别盘点、入库并记录身份转换时才成立；停用通途本身不是迁移条件。
- 公开 API 有数量/SKU 调整，但没有完整加工单写链；不要把未来加工模型描述为现成自动化。
- `--live` 不查 Listing；成本覆盖可先用已有皮壳 FBM 订单，不必请运营新下测试单。
- 不调用 `SELLFOX_API/sellfox_combo_ops.py sync-combos` 创建本方案对象，该命令面向 EN TJ# 套件。

## 代码地图

- `audit_sandbox.py`：默认无写入；`--live` 只查仓库列表和商品 pageList（底层 + 皮壳 SKU），不查 Listing。FBA/退货/不良仓 blocked；DANEEY 主仓 `cautions`；`POLAND` 无 caution，波兰成品仓名才 caution。加工商品计数读 `totalSize`。报告不验收利润。
- `PK#` 已是普通/加工商品时的 blocked 只保护“组合候选不得自动改类型”；若业务确认独立数量池，应另立独立库存沙盒，不要删除或重建现有商品。
- `tests/test_audit_sandbox.py`：配置和组合关系纯函数测试。
- `SELLFOX_API/client.py`：复用认证、签名和限流。
- `.agents/skills/sellfox-cover-inventory/SKILL.md`：触发词和路由。
