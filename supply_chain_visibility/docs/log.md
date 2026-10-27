---
okf: v0.1
type: Log
title: supply_chain_visibility 变更日志
---

# 变更日志

## 2026-10-13
- **Stage 1 v35（出库按 DN 归组）**：修「N单」误报 —— 原按 `Delivery Note Item` **明细行**计数，一张 DN 拆多行会显示成「5单」。改为**按出库单归组**（`dns=[{dn,date,status,docstatus,is_return,qty,lines[]}]`），摘要「N单」= **DN 张数**；明细表加「行数」列，`>1` 行时列出 `q1 + q2 + … = 合计`。生产 SO-26-00101 实测：`DM-153-IVORY` 22 行 → **1单·已发200**；真有 2 张 DN 的 `HLR-140-GREY` → **2单**(DN-26-00071+DN-26-00089)。⚠️ 过程踩坑：归组后 `dns` 变 dict，`d.qty` 必须改 `d["qty"]`（否则 `AttributeError`→500），已在**测试机拦下**（未到生产）。
- **Stage 1 v34（报工/入库 两列 + 列宽）**：把「已生产」**拆成「报工」「入库」**，不一致标黄。`so_chain.py` 每工单加 `last_op_done`（末道必经工序报工，**去重 `max(整批卡[无菲号],逐菲号卡)`**，护栏=取有卡的最大 sequence 必经工序）、每行输出 `reported/instock/report_note`；**成品(KS)行无工序 → 报工取子装配件(皮壳/内胆)齐套(取较慢)**（用户选定）。列宽拖拽改**总宽模型**：拖宽→**整表总宽变、下方出横向滚动条**，**不再压缩首列**（对齐 AG Grid/Excel）；表头右缘**始终可见分隔条** + 悬停主色 + `col-resize` 光标，**双击=自适应内容**。测试 SO-26-00026/00025 验证（列/黄标/拖拽 qty 54→144 且首列 209 不变/双击 115→159）；生产 `6fc2ef7` 部署，SO-25-00169(82 行) 一屏放下、0 报错。详见 [docs/reference/en-produced-qty-vs-jobcard.md](reference/en-produced-qty-vs-jobcard.md)。
- **「已生产」口径实测（2026-10-14）**：核实 `Work Order.produced_qty` **= 工单入库**(Manufacture 入库单提交回写，非工序卡)；**成品(KS)工单 0 张有工序** → 成品只能用入库。查出两类不一致的成因：①**完工未入库**=入库单**未提交(草稿)/未创建/被取消**(实例 WO-26-00001/00008/01519…)；②**报工≈2×**=末道工序上**整批卡(无菲号)+逐菲号卡并存**叠加(WO-26-02835 406 vs 200；三元组零重复)。1733 张对账：去重 `max(整批卡,逐菲号卡)` 后待入库 41→**26**。末道判定=必经(排除 `is_corrective_operation` 的通用返工/质检发现问题)里 sequence 最大者(**质检 100% 是末道**)；护栏=末道取"有卡的最大 sequence 必经工序"(「包装」现存但 0 使用)。**B 方案**：已生产=入库(主)、末道完工=max(整批,菲号)(副)、差值=待入库(>0 标黄)。详见 [docs/reference/en-produced-qty-vs-jobcard.md](reference/en-produced-qty-vs-jobcard.md)。
- **Stage 1 v31–v33（列宽）**：v31 客户码回第 2 列 + 加「已生产」列 + 去「未发」列 + 表头右缘**拖拽列宽**(localStorage `so_chain_colw` 记忆)；v32 修 v31 漏删的重复 `const SO_CHAIN_COLS`（见下行事故）；v33 默认列宽 —— 「订单行物料」改**弹性列**(`w:0` 时不输出 `width`，`table-layout:fixed` 下吸收余量)、数字列(订单量/已生产/已发)锁 **54px**、客户物料号 115、交期 96、阶段 106、生产 142、出库 106。生产 SO-25-00169(82 行)实测 `wrapW=tblW=scrollW=1003` **一屏放下、0 控制台报错**。
- **事故+修复（2026-10-14）**：v31 漏删重复的 `const SO_CHAIN_COLS` → 生产表单空白（整脚本 SyntaxError）；叠加「部署基线被污染累计两份」+「生产 git pull 静默失败」。处置：生产回滚 v30 → 测试机修好并完整验证 → main `7947a1d`(v32) → 生产 `git reset --hard origin/main` 对齐 → 验证通过 → `5a3c9ef`(v33) 再发布。教训见 key_test/AGENT_HANDOFF.md §14。
- **Stage 1 v28–v30（排版）**：订单行物料改「小字 2 行(码上名下单行距)+超长省略号」；表 12px、不换行；不重要的「客户物料号」列后移到最后；**物料码/名称/客户码上限 150px 截断(省略号+hover 全值)** —— 修「单个 56 字符物料码把列撑到 466px 导致横向拉拽」。生产 SO-25-00169（82 行）实测 **一屏放下、无需横向滚动**。
- **Stage 1 v27**：**纳入草稿工单**（成品工单常是 Draft，docstatus=0，原先 docstatus=1 漏掉）+ **成品工单优先排序**（父在前，皮壳/内胆子装配件在后）+ 物料显示改「物料号: 物料名称」一行不换行 + 摘要紧凑。生产验证 SO-26-00117 成品 WO-26-03517 已在最前。
- **生产发布（2026-10-13）**：测试机 `feature/so-chain-embed` **快进合并 main**（push `ab3cdc0..2c11464`）→ 生产 `key_test` pull + `migrate`（建 **SO Chain Overview** 报表记录）+ `restart` + `clear-cache`。生产验证：方法 200（SO-25-00169 → 82 行）、报表 12 列 4520 行、浏览器实测皮壳工单显示所属计划。
- **Stage 1 v22**：更正「皮壳/内胆无计划」误判 —— 生产实测 **PK# 78% / ND# 77% 的工单有 `production_plan_item`**（指向 Production Plan Item）。修工单→PP 解析：按工单自身 `production_plan_item` 反查，**不带 SO 行过滤**（皮壳/内胆计划行常不带 SO 行）。
- **Stage 1 v21**：修 bug —— 清高亮只清**本行**(此前清全表，导致多行展开时他行框线被误清)；工单头补「计划 PP-xx」（`WO.production_plan_item`→PP）。实测：**成品工单有计划，皮壳/内胆工单 `production_plan_item` 为空**（只挂 SO 行）。
- **Stage 1 v18**：被点单元格的上/左/右边线改用 `box-shadow: inset` 在格内绘制（表格 border-collapse 会吃掉 td 的上/左边线），框线完整。
- **Stage 1 v17**：**不再单独画标题** —— 被点的那一格本身着蓝/绿框线(下边敞开)，与下方同色边框明细面板连成一体(模拟标签页)；未展开的格子无框线；切换/收起时框线随之变化。
- **Stage 1 v15**：标签按被点列的横向偏移定位 —— **落在该列正下方**（不再靠左），与同色边框明细面板连成一体（截图确认：标签左缘与被点列左缘对齐，差 1px）。
- **Stage 1 v14**：展开框改为**tab 造型** —— 摘要在标签里(上/左/右框线、下边不封)，直接并进下面**同色框线**的明细面板，框线连贯（对齐 vilavi_pim 产品模板标签样式）。
- **Stage 1 v13**：展开框**标题=被点的那块摘要文本**（如「1 工单 · 1 菲号 工序 4/4」），细色条+浅底框住明细；去掉多余标签按钮（v11/v12 理解偏差已纠正）。
- **Stage 1 v11**：列头即标签 —— 展开框标题=列名(绿/蓝)并紧贴框住明细；**生产计划列撤掉并入生产链条面板**；⤢ 加到两列。
- **Stage 1 v10**：同一行改为**单容器 + 标签页**（生产链条 | 出库），点任一摘要打开容器并切到该标签，标签间可切换（不再两条分离面板）。
- **Stage 1 v9**：「出库」列改简称；「1单·已发X」(有退货才显示退)；生产链条(绿)/出库(蓝) 两列各自独立展开，面板带色条+标题，区别于普通子表。
- **Stage 1 v8**：「链条」改名「生产链条」；新增「销售出库」列（DN 明细，一对多/含退货，可展开）；撤掉「弹窗」列（改 ⤢ 小图标）。两列各自独立行内展开。
- **Stage 1 v7**：「忘点完工」异常 —— 成品工单未完工但皮壳/内胆兄弟全完成 → 标黄提醒（`forgot_complete`）。
- **Stage 1 v6**：成品(KS)行挂 皮壳/内胆工单（`fg_sales_order_item`）→ 可见 3 张工单(成品+皮壳+内胆)；工序分母**排除返工分支**(`Operation.is_corrective_operation`)；摘要改「N 工单·M 菲号·工序 最慢–最快/总」。
- **Stage 1 v5**：主表合并「工单/菲号」为「链条」列（`N张·M菲号 工序 d/t`）+ **行内展开(accordion)**；菲号默认展开；保留弹窗。调研结论：**不做 hover**（触屏失效/WCAG 1.4.13/v15 无官方 hover 卡）；**不用树表**（父子字段异构）；正解=摘要+行内展开+弹窗深钻。
- **Stage 1 v4**：弹窗层级按菲号语义重构为 **工单 → 菲号(可折叠) → 逐工序 Job Card**（原「工单→工序→工序卡」是转置投影，丢菲号物证）；状态值过 `__()` 取中文翻译。菲号语义实测见 [docs/reference/en-tracking-number-semantics.md](reference/en-tracking-number-semantics.md)。
- **Stage 1 v3**：全加单据跳转链接（物料/计划/工单/工序卡/菲号/开料工单）；弹窗列工序卡明细；主表加「交期」列 + 逾期红字、阶段色块、未发合计行。
- **基数核实（生产实测）+ 连接键修正**：`(sales_order, production_item)` 复合键**有冲突** —— 同 SO 内同 item_code 最多 40 行，导致 **1464 张工单重复挂、139 张漏挂**。改用 ERPNext 原生行级外键 **`Work Order.sales_order_item`**（悬空 0）并加兜底；同步修 `so_chain.py`/报表/`EN_API/item_shipment_status.py` 的 `wos_for_line`（同 bug）。新增文档 [docs/reference/en-chain-cardinality.md](reference/en-chain-cardinality.md)。报表加「工单数/菲号数」列。
- **Stage 1 v2（一对多展示）**：主表补「生产计划」列；「工单/菲号」做成可点 chip，点开 `frappe.ui.Dialog` 看层级（工单 → 逐道工序(裁剪…) + 菲号(含**开料工单**，非空=已开料)）。依据业界「摘要 + 可下钻」（Frappe 子表只有 2 层、Dialog 子表有只读 bug）。测试机已部署并 Playwright 验证。

- **新开子项目** `supply_chain_visibility/` —— EN 供应链可视化与履约查询。
- **迁移**：`EN_API/docs/research/en-supply-chain-map.md` → `docs/reference/en-supply-chain-map.md`；
  `docs/solutions/architecture-patterns/supply-chain-visibility-forms-research.md` → `docs/research/presentation-forms.md`；
  `EN_API/so_chain_embed/` → `key_test/`（Stage 1/2 落地产物）。
- **新增**：`docs/reference/en-custom-apps-and-deploy.md`（自定义 app 拓扑 + 落地链路 + 实测坑）。
- **背景**：绍兴工厂负责人拟把「下单→出库」整条链的信息呈现/查询做到 EN 上（形式未定）；
  本次完成了事实地图、呈现形式调研、Stage 1（SO 表单内嵌）+ Stage 2（原生报表），均已在**测试机**部署验证，**生产未部署**。
- **2026-10-27 生产部署**：`key_test` 生产同步 `c34fa53`（PR #2）；`bench migrate` + `clear-cache` + `bench restart`；
  `SO Chain Overview` / `Supply Timeline` 冒烟通过。上文“生产未部署”已过时；详见 `JACK_QA.md` 的 `P0-PROD-DEPLOY-2026-10-27`。
