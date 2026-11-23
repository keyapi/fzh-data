---
type: Spec
title: 运营需求协同首版实现与验收
date: 2026-11-11
status: local-validated-not-production
---

# 交付边界

首版已从研究进入实现。采用项目已有FastAPI/SQLite/原生JS，不引入大型商业规划平台。独立代理负责界面、核心、EN桥接，主代理整合和浏览器验收。

## 扩大的调研与选择

[Dynamics 365工作表/版本/单元格评论](https://learn.microsoft.com/en-us/dynamics365/supply-chain/demand-planning/time-series)支持协作计划的版本与上下文；本版借鉴基准、提案、发布分层，而非购买该平台。

[Frappe角色权限](https://docs.frappe.io/framework/user/en/basics/users-and-permissions)与[Page API](https://docs.frappe.io/framework/user/en/api/page)支撑EN入口；保留服务端会话权限，前端不持API密钥。未来需在真实站点验证记录范围。

[frePPLe源窗口覆盖与分摊](https://frepple.com/docs/current/model-reference/forecast-plan.html)提示分摊必须有明确规则。本版现阶段没有周预测证据，保留97/157天整期，拒绝擅自平均拆分。完整事件模型、SOTA预测挑战者与FVA路线沿用上游研究；本轮没有伪称训练新模型。

## 验收证据

- 单元/API/桥接/导入测试先看到RED再实现GREEN；最终63项通过（核心33、适配11、EN桥接12、Web7）。只有依赖包httpx弃用提示，无失败。
- 浏览器分别以local-operator与local-reviewer身份：提交增量30、另一人通过、发布，页面出现JSON/Parquet入口；API测试核两格式数量相同。
- 演示是显式虚构三分公司案例，原始基准100→增量30→情景130，不写真实订单/采购。
- 独立复审找到五项可触发问题：只报事件错误值、null库存归0、旧as_of、缺撤销、恶意Host。均已修复并复核。

## 真实数据核验

只读检查D5 v6.8源：SHA256 `d6446fe7066b5a00c22113bebebb124ae91f3757a691ef0634892b4025e78d83`。共3498行；97天选择1749，157天另1749保留为跳过记录。

1749行中：三分公司1564（波兰735、美中533、美东296）；CG/CG-USNJ/CG-USTX/其他共185不映射为本模块国外分公司。三分公司另51行point_forecast为空（美东19、美中18、波兰14），不能补0。可数值化1513，拒收236，全部可追到源行，数量守恒。

185是范围/映射不适配，51是缺数，不可笼统称236个预测算法错误。当前审计未激活真实基准；名称、通途身份与源预测期起证据仍需接合，不能从文件更新时间猜测。

私有审计结果：`D:/Work/fzh-order-store/analysis/operator-demand-d5-inspect-20261111/report.json`。浏览器测试数据库：同analysis下operator-demand-workbench/demo.sqlite3，不纳入Git。

## 首版限制与下一阶段

- EN桥接stub通过，真实bench、普通用户HTTP、Page注册和行级权限尚未验收；没有生产部署。
- 只支持精确源期间的数值调整，短活动可登记待估，但还没有活动效果自动估量。不可凭主观信心生成概率。
- 当前一个物理目标期间仅一个数值共识；多人意见可提案和裁决，尚未实现店铺/类目多层自动分配。
- C/E只读上下文可显示，但未接实时生产；本模块不接管库存/供应刷新。
- 发布是需求情景，全部无直接补货资格。下一阶段需结合实际源期、未履约终端订单与C/E占用口径，再接净额适配。

没有把这些未完成部分藏在“已完成首版”里。可先用当前界面审视流程与交互，逐阶段扩大到真实已具资格商品。

## P0/P1 只读展示层增量（2026-11-13）

- **EN 实时库存覆盖层**：`live_stock.py` 用 EN REST 只读读取最新完整 `Tongtool Stock Run` / `Tongtool Stock Latest`，按通途 SKU+仓 join 到建议快照，展示 `available / intransit / waiting_shipment / defects`、`run_id`、`snapshot_at` 及与快照 C/E 的差值。拉取失败回退私有缓存并标“旧数据”；无缓存标“不可用”；未匹配或未知量保持未知，不补 0。覆盖层只装饰返回视图，**不写回不可变快照**。
- **SO 证据分组**：`so_evidence.py` 增加 `transaction_date`，以 `as_of` 前 6 个日历月为界分“近期 / 历史开放 / 创建日未知”。历史正余额单列展示、不丢弃；三段数量合计等于开放 SO 总量。SO 明细显示创建日、交付日、已交/未交、逾期。
- **UI 文案**：`waiting_shipment` 固定标注“通途库存待发，未关联单据/订单”，不再与“催已有”混用。
- **真实数据核验**：真实 USNJ 建议快照应为接收 169 / 拒收 1 / 跳过 9（输入 179），测试按此断言；真实 W1 测试校验三段分桶不丢行。若源文件变化导致计数不同，测试失败而不是静默放宽。
