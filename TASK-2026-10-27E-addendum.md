# TASK 2026-10-27E 补充：生产周期与春节

用户补充（以用户口径为准）：

1. **绍兴生产周期约 3 个月**：WX 的口径是“下单时间 + 3 个月 = 国外分公司能发货”。最近 PB 到货实测有的比 3 个月提前约 2 周，有的提前几天；所以 **45 天假设太短**。
2. **默认 order-to-branch = 90 天 baseline**（可先 90，范围 75–90 天）；用 EN SO→DN/Shipment 实测“出厂→到仓”替换，输出 P50/P90，并标 `measured/assumed`。
3. **春节**：中国工厂春节月一般放假 1 个月，之后恢复产能约 1 个月；**若下单/交付跨 1–2 月，加 2 个月缓冲**。日历化，字段 `spring_festival_buffer_days`；不要静默忽略。
4. **Closed SO 语义确认**：2024/2025 的手工 Closed = 未交付也不再交付；2026 的未关闭才是开放。保持 `status != Closed`，Closed 旧单单列，不并入。
5. `customer_item_code` 是 EN SO 行上的**客户物料号**，本数据里通常是通途 SKU；没有就回退 `item_code`，不阻塞。

请并入 r4：

- SO 管线预计到分公司日 = 工厂交付日 + 90 天 baseline（或实测分布）+ 春节缓冲（如适用）；`date_confidence` 标 `estimated`/`measured`。
- 三层包/决策包用新日期重算；保留 `assumed` 标记，不写 confirmed。
- 若实测数据不足，先按 90 天 + 春节，写清是业务口径不是统计结论。
- 60 分钟 checkpoint 或完成报告；不 push/不写生产。
