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

当前每个物理商品/分公司/源期间仅允许一个数值共识。尚未实现店铺级销量拆分、类目批量分摊、自动事件增量学习和行级权限。

## 接真实D5

```powershell
uv run python -m demand_collaboration.adapter --source D:/private/D5.xlsx --inspect --out D:/private/demand/inspection
```

读取`1_预测`，分别统计输入/不同horizon/可用/拒收，报告源文件SHA256。不把未知预测填0、不推断库存和历史。`--inspect`不会激活基准。

在确认源预测真正的起止日和数据时点后，显式提供`--forecast-start`与`--as-of`生成规范基准；使用CLI `--baseline baseline.json`装载。具体参数见`uv run python -m demand_collaboration.adapter --help`。有拒收时转换整批拒绝，原始拒收仍在报告；不能把“1513可解析”说成全量已接通。

当前D5含97/157天整期需求，须分别导入，不允许同一物理商品重叠窗口相加。UI支持`period_end`标整期总量；不会自动拆周。名称/通途身份未接时明确标EN物料，不能冒充通途SKU。源期起不明时不得用文件名日期代替。

所有发布标`service_certified=false`、`replenishment_eligible=false`。期中发布含`needs_remaining_period_forecast=true`，整期数量不能当剩余需求直接用于补货。后续消费器必须先验证期间和概率语义，再进入C/E净额。

## USNJ 补货建议（只读快照）

USNJ 建议是“预测 + C 库存 + E 供给”的独立补货建议，不是 D5 需求基准；两者不相加。工作台新增“USNJ 建议”页签，按 SKU×客户×仓×形态×UOM×期间一行展示，默认只看动作/数量/覆盖/原因/置信度，展开看 C/E、预测与 q50/q90/q95，模型与来源再折叠。筛选项为需拍板、低置信、缺供给、特殊品；缺失值显示“未知”，绝不补 0。页签没有任何改量、审批或下单入口。

```powershell
# 只生成私有报告与不可变快照（不改D5/C/E，不写EN）
uv run python -m demand_collaboration.recommendation `
  --source D:/private/USNJ补货建议.csv --as-of 2026-11-13 `
  --so-evidence D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl `
  --out D:/private/demand/usnj-20261113
# 可选：装载到本地SQLite台账，工作台即可只读查看
uv run python -m demand_collaboration.recommendation `
  --source D:/private/USNJ补货建议.csv --as-of 2026-11-13 `
  --so-evidence D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl `
  --out D:/private/demand/usnj-20261113 --db D:/private/demand/demo.sqlite3
```

SO 证据默认按**创建日期**分成两段：`as_of` 往前 6 个月为“近期 SO”，更早但仍正余额的行单列“历史开放 SO”，缺创建日期的行进“创建日未知”。三段都保留、不丢弃，合计仍等于开放 SO 总量；SO 明细显示创建日、交付日、已交/未交与逾期天数。窗口起点可用 `--so-window-start 2026-05-13` 固定。

### EN 实时库存覆盖层（只读）

工作台启动时默认尝试读取生产 EN 的 `Tongtool Stock Run`（最近一次 `Success` 且 `complete=1`）与 `Tongtool Stock Latest`，按**通途 SKU + 仓** join 到建议快照，显示 `available / intransit / waiting_shipment / defects`、`run_id`、`snapshot_at`，以及与快照 C/E 的差值。`waiting_shipment` 固定标注“通途库存待发，未关联单据/订单”，不叫催已有。

```powershell
# 默认开；凭证先读进程ERP_API_KEY/ERP_API_SECRET，再读仓库EN_API/.env
uv run python -m demand_collaboration --db D:/private/demand/demo.sqlite3
# 关闭实时覆盖层
uv run python -m demand_collaboration --db D:/private/demand/demo.sqlite3 --no-live-stock
# 指定凭证 / 缓存 / TTL
uv run python -m demand_collaboration --db D:/private/demand/demo.sqlite3 `
  --live-stock-env D:/Work/赛狐/Cursor/EN_API/.env `
  --live-stock-cache D:/private/demand/en_live_stock.json --live-stock-ttl 60
```

只发 GET，不写 EN、不写快照。拉取失败时回退到最近一次本地缓存并标“旧数据”；连缓存也没有则显示“不可用”，行内实时量保持未知，**绝不补 0**。未匹配到 SKU×仓的行显示“未匹配”，同样不补 0。

导入报告严格对账：`输入 = 接收 + 拒收 + 跳过`，每个拒收/跳过都保留源行与原因。同一内容重复装载幂等；不同内容生成新快照，旧快照不可修改。快照、行级 `service_certified=false`、`replenishment_eligible=false` 恒为只读参考，不得当作采购指令。

## 放到EN的方式

已提供`frappe_bridge.py`和`en_page.js`，复用EN登录会话和原生Desk Page。**未部署生产，也未进行真实站点bench/普通受限用户HTTP验收。**

测试站接入：把整个包复制到现有`key_test/key_test/demand_collaboration/`（保留`static/`）；注册名为`demand-collaboration`的Page并使用`en_page.js`。页面通过Frappe RPC取HTML，调用同源gateway，不在浏览器保存API密钥。基准仅System Manager可装载；提案角色Demand Contributor，审核角色Demand Reviewer（System Manager也可审核，自批仍拒绝）。

台账在站点private目录。此首版对获授角色共享整个需求台账，**尚无按运营商品/分公司的行级隔离，不能直接向需隔离数据的全部运营开放**。发布前应先确定负责人权限并做测试站真实会话验收。EN目前提供JSON下载；EN端Parquet显式未支持，本地端已测试支持。

## 验证

```powershell
uv run python -m pytest tests/test_demand_collaboration_core.py tests/test_demand_collaboration_web.py tests/test_demand_collaboration_frappe.py tests/test_demand_collaboration_adapter.py tests/test_demand_collaboration_recommendation.py -q
```

包含数值/日期验证、幂等、乐观锁、并发批准、冲突、过期、源版本、未知不填0、JSON/Parquet数量一致、角色与自批拒绝、EN桥接stub。stub通过不等于EN已上线。

详细交付记录见[文档入口](docs/index.md)。
