---
type: Handoff
title: 运营需求协同Agent接手
---

# Agent接手

先读README和docs/index.md。核心Store只依赖标准库；FastAPI本地界面与Frappe桥接共享核心。不要把固定本地actor/role当生产鉴权。部署测试站先确认key_test路径、角色与行级范围；本轮没有部署权限变更。

业务铁律：真实订单不写本模块；这里是运营判断。总量/增量分开，同范围不自动相加。当前只有物理商品×分公司×明确源期间，不能伪造店铺预测或把97天总量拆周。所有导出不具采购资格与概率认证。期中发布不能当剩余期。

可直接扩展：明确日期的D5数据适配、名称/客户物料号只读补充、运营范围权限、完整事件估量流程、同范围提案合并裁决、实际FVA；不重写预测库、不扩大FBA/仓库范围。

USNJ 建议：`recommendation.py` 把一份显式 CSV 转成不可变、只读的 `recommendation_snapshot`（键含客户/仓/形态/UOM/期间），Store 用独立表与 settings 键保存，不写 D5 基准。报告必须 `输入=接收+拒收+跳过`，未知数值保留 `None` 不补 0；页签无改量/审批/下单入口，两项资格恒 false。导入 CLI 见 README。

SO 证据：`so_evidence.py` 按 `transaction_date` 把开放 SO 行分成近期（默认 as_of 前 6 个月）、历史开放、创建日未知三段；三段数量合计等于开放总量，历史正余额单列不丢弃。`delivery_date`、已交/未交、逾期天数逐行保留，但都不加入建议量。

EN 实时库存：`live_stock.py` 只读 GET `Tongtool Stock Run` + `Tongtool Stock Latest`，按通途 SKU+仓 join；`web.py` 在返回只读视图时装饰，**绝不写回快照**。失败回退本地缓存并标 `fallback_stale`，无缓存标 `unavailable`；未知量保持 `None`。`waiting_shipment` 的 UI 文案是“通途库存待发，未关联单据/订单”，不要叫催已有。实时拉取默认开（`--no-live-stock` 可关），凭证读 `EN_API/.env`。

tests/test_demand_collaboration_*是行为契约。对业务语义的改变须先反例，再修改实现。不要提交private数据库、真实快照、截图或行级导入报告。
