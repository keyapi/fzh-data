---
type: Handoff
title: 运营需求协同Agent接手
---

# Agent接手

先读README和docs/index.md。核心Store只依赖标准库；FastAPI本地界面与Frappe桥接共享核心。不要把固定本地actor/role当生产鉴权。行级范围在 `scope.py`，由站点私有 `demand_scope.json` 控制（`set_scope` 仅 System Manager）；部署测试站先确认 key_test 路径、角色与范围文件；本轮没有生产部署。

业务铁律：真实订单不写本模块；这里是运营判断。总量/增量分开，同范围不自动相加。当前只有物理商品×分公司×明确源期间，不能伪造店铺预测或把97天总量拆周。所有导出不具采购资格与概率认证。期中发布不能当剩余期。发布快照/下载仅 Reviewer/System Manager 可读。

可直接扩展：名称/客户物料号只读补充、完整事件估量流程、同范围提案合并裁决、实际FVA、真实 EN 会话/CSRF/Page 验收；不重写预测库、不扩大FBA/仓库范围。

EN 入口两个实测坑：GET 时 `payload` 是空字符串（桥接视为 `{}`，否则 417）；iframe sandbox 必须带 `allow-forms`，否则表单提交被浏览器拦截。测试站公网是 `ensh.vilavi.cn`，`erpnext.vilavi.cn` 指向生产；`bench --site erpnext.vilavi.cn` 只是在测试机上的站点目录名。详见 `docs/solutions/integration-issues/frappe-desk-page-iframe-rpc-bridge.md` 与 `docs/solutions/architecture-patterns/side-ledger-row-scope-default-deny.md`。

tests/test_demand_collaboration_*是行为契约。对业务语义的改变须先反例，再修改实现。不要提交private数据库、真实快照、截图或行级导入报告。
