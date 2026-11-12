---
type: Guide
title: 运营需求协同工作台
---

# 运营需求协同工作台

一个已实现的本地首版：查看系统基准，提交销量判断/业务事件，独立审核、裁决冲突、发布版本化需求情景。不是采购系统，也没有改变现有D/E管线。

## 本地打开

在仓库根运行，台账必须放私有目录：

```powershell
uv run python -m demand_collaboration --db D:/private/demand/demo.sqlite3 --demo --actor operator-a --port 8765
uv run python -m demand_collaboration --db D:/private/demand/demo.sqlite3 --actor reviewer-b --role reviewer --port 8766
```

运营打开 http://127.0.0.1:8765 ，审核人打开 http://127.0.0.1:8766 。两实例共享台账；身份由服务器配置，网页不能更改身份或自批。只绑定本机，不能把此本地身份模式直接暴露给多人生产使用。

`--demo`才会创建三分公司构想数据，页面始终标“演示数据”。不带它时为空台账，不暗中加载示例。SQLite记录基准、提案、裁决、审计和完整冻结版本；不提交数据库到Git。

## 工作过程

1. 运营选择商品/分公司/预测期间。数值输入分“预计总销量”“增减量”“比例”；只报事件不强迫估量。
2. 填写日期、事件标识、原因和依据。提案ID重复重试不会重复计量；内容变化则需新ID。
3. 另一审核人通过/驳回；已通过可以撤销。同一范围的重叠提案必须先裁决，禁止最后写入者覆盖或简单叠加。
4. 审核人选择决策截止日，发布共识版本。JSON保存详细证据；本地Parquet输出同样的逐商品数量，供后续适配。

当前每个物理商品/分公司/源期间仅允许一个数值共识。已实现行级范围（`scope.py`，站点私有 JSON，System Manager 维护，默认拒绝）；尚未实现店铺级销量拆分、类目批量分摊和自动事件增量学习。

## 接真实D5

```powershell
uv run python -m demand_collaboration.adapter --source D:/private/D5.xlsx --inspect --out D:/private/demand/inspection
```

读取`1_预测`，分别统计输入/不同horizon/可用/拒收，报告源文件SHA256。不把未知预测填0、不推断库存和历史。`--inspect`不会激活基准。

在确认源预测真正的起止日和数据时点后，显式提供`--forecast-start`与`--as-of`生成规范基准；使用CLI `--baseline baseline.json`装载。具体参数见`uv run python -m demand_collaboration.adapter --help`。范围外池（CG/其他）记 `out_of_scope`，不阻断；缺预测记 `missing_forecast`，默认阻断，显式 `--allow-missing-forecast` 才排除并保留去向；真正非法值才整批拒绝。不能把“1513可解析”说成全量已接通。

当前D5含97/157天整期需求，须分别导入，不允许同一物理商品重叠窗口相加。UI支持`period_end`标整期总量；不会自动拆周。名称/通途身份未接时明确标EN物料，不能冒充通途SKU。源期起不明时不得用文件名日期代替。

所有发布标`service_certified=false`、`replenishment_eligible=false`。期中发布含`needs_remaining_period_forecast=true`，整期数量不能当剩余需求直接用于补货。后续消费器必须先验证期间和概率语义，再进入C/E净额。

## 放到EN的方式

已提供`frappe_bridge.py`和`en_page.js`，复用EN登录会话和原生Desk Page。**未部署生产，也未进行真实站点bench/普通受限用户HTTP验收。**

测试站接入：把整个包复制到现有`key_test/key_test/demand_collaboration/`（保留`static/`）；注册名为`demand-collaboration`的Page并使用`en_page.js`。页面通过Frappe RPC取HTML，调用同源gateway，不在浏览器保存API密钥。基准仅System Manager可装载；提案角色Demand Contributor，审核角色Demand Reviewer（System Manager也可审核，自批仍拒绝）。

台账在站点private目录。行级范围由 `demand_scope.json` 控制（`set_scope`，仅 System Manager，默认拒绝），bridge 按 `(product_id, branch)` 过滤 state/proposals；发布快照与下载仅 Reviewer/System Manager 可见/可读，Contributor 的 state 不返回 publication 对象。**真实站点会话、CSRF、Page 注册尚未验收。** EN目前提供JSON下载；EN端Parquet显式未支持，本地端已测试支持。

测试站已验收：`https://ensh.vilavi.cn/app/demand-collaboration`（`demand-ops-test@vilavi.cn` / `demand-reviewer-test@vilavi.cn`，临时密码另行提供）。测试站用真实 D5 v6.8 基准 1,513 行 + 5 个 PL 商品的试点范围。**生产未部署。**

## 验证

```powershell
uv run python -m pytest tests/test_demand_collaboration_core.py tests/test_demand_collaboration_web.py tests/test_demand_collaboration_frappe.py tests/test_demand_collaboration_adapter.py -q
```

包含数值/日期验证、幂等、乐观锁、并发批准、冲突、过期、源版本、未知不填0、JSON/Parquet数量一致、角色与自批拒绝、行级范围/跨范围提交/发布权限、适配器范围外与缺数分类、基准 as_of 单调、EN桥接stub。stub通过不等于EN已上线。

详细交付记录见[文档入口](docs/index.md)。
