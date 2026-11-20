---
name: pb-orders
description: >
  Pottery Barn (PB) 出件与断货闭环：SPS 库存预检 → 通途导入 xlsx + 标签/背贴 PDF；
  打单后才发现无货时的 invoice 清理惯例、Notion 断货台账登记、通知 Diane 的邮件规律。
  当用户提到「PB」「Pottery Barn」「出件」「库存预检」「标签 PDF」「背贴」「Packslip」
  「无货未发」「断货台账」「通知对接人」「给 Diane 发邮件」「清 invoice」「invoice 总额」
  「楔形枕补货」「PB 补货」「重发 AKN」「改 SPS 发货日期」「Ship No Later」「Order 状态 open」
  「JSON API」「/api/v1」「Bearer」「api.vilavi.cn/pb」时触发。
  不要用于 PB 月度对账 / TM 佣金 / UPS 交付核查（那是 pb-reconciliation）。
metadata:
  module: pb_orders
  docs: pb_orders/docs/reference/stockout-closed-loop.md
  updated: 2026-11-02
---

# PB 出件与断货闭环

完整规范见 [pb_orders/docs/reference/stockout-closed-loop.md](../../pb_orders/docs/reference/stockout-closed-loop.md)
与 [workflow.md](../../pb_orders/docs/reference/workflow.md)。这里是可复跑清单。

## 必须先做

1. 读 `pb_orders/AGENT_HANDOFF.md`（背景 / 文件位置 / 函数表 / 坑）。
2. 数据在**仓库外**：`D:\Work\美国\Tracy Miller\PB orders\<YYYYMMDD>\`。
3. 凭证在**父仓库** `D:\Work\赛狐\Cursor`，worktree 里没有。一律 `uv run python`。
4. 判定「真发」只认 **UPS 取件** —— ASN / 通途 `despatched` / `PBUS-<PO>` 都只等于「建了标」。
5. **shipment CSV 的包裹号看 `Pack Level Carrier Tracking ID`，不要看 `Carrier Tracking`**：
   后者是主跟踪号，一单多件时也可能只有一个；前者才逐包裹列出全部
   （2026-08-27 ASN 12262：Carrier Tracking 只有 `1ZC…14807245`，Pack Level 才是
   `1ZC…14807245 1ZC…15985060` 两个）。

## 两条主线

### A. 正常出件（步骤 0 → 4）

```bash
cd pb_orders
uv run python run_stock_check.py --dir "<批次目录>" --no-stock "<断货SKU,…>"   # 步骤 0 预检
uv run python run_pb_orders.py --dir "<批次目录>"                              # 出件（xlsx+标签+背贴）
```

判定单位是**明细行**不是整单（部分缺货只剔缺货行）。逐行照搬源文件 → checked CSV 与 SPS 导出一致。

### B. 打单后才发现无货（本 skill 的重点）

**先查上游再报 restock date**：EN **Sales Order / Production Plan / Work Order / Delivery Note**
+ 钉钉 **`2026年下单表` / `发货信息总表`**（头程在途、ETA）+ 通途**采购在途**。
有在途且 ETA 早于客户最晚发货日 → 以在途为准；没有才按「补货下单 + 提前期」推并标 TBC。
**不要默认拍 +3 个月**（reference 文档 §1.2）。
**报出去的日期必须是工作日**：预约送仓/ETA 落在周末或节假日 → 顺延到下一个工作日
（2026-11-19 实例：12/12 周六 → 报 12/14 周一）；临近圣诞也不要为了「往后加几天」写成 12/24 之后。

美中仓回话说某 PO 无货时，按顺序做五件事 —— 见 reference 文档 §2：

1. **清 invoice**（月底钉钉提交前必须做）：原 `invoice xNN …csv` + 总额 txt 移进 `invoice/NotUsed/`；
   生成去掉无货 H+D 行的新 csv；**新总额写进新的 0 字节 txt 文件名**，格式
   `<新总额> 已去除无货N单<PO…> 之前是<旧总额>.txt`。
2. **Notion 登记**：库「PB 无货未发（一行一个 PO）」，用 `pb_orders/notion_stockout.py` 算待追加行。
   **⚠️ 每次操作完必须把过程追加写回该行「备注」**（带日期的逐条记录，不覆盖旧记录）——
   用户明确要求「所有操作的过程都需要记录到 Notion」。
   **跨单/不挂在 PO 上的操作**（BOM 刷新、补货决策…）→ 改为在 `任务202408-` 库**建任务页**。
   口径与坑见 reference 文档 §2 第 2 步 + notion-stockout.md §5。
3. **通知 Diane**（`us@mxdeals.com` → PB 采购对接人，地址见历史邮件）：主题 `SKU:<PB买家SKU> out of stock Vendor 5806`，
   **后续新 SKU 回复上一封**（主题滚成 `Re:RE: …`）。
4. **SPS 后台**：先点开 Order（New → Open），再判断要不要重发 AKN ——
   读 **Order 明细行**的 `Ship No Later`（原 ACK 表头日期常为空）：计划到货 ≤ 它 → **不用发**；
   晚于它 → 重发 AKN（Expected Ship = 计划到货日，Delivery = +7 天），发完在交易列表确认
   「当天新 ACK + Accepted/In Transit」。IA 重提（`SPS_Selenium_Local/sps_automation.py` 每天定时发，
   模板 `IA Template 20250605 x100`）—— 完整点法见
   `docs/solutions/workflow-issues/sps-portal-ia-akn-operations.md`
   （⚠️ 一次 Send 不一定发得出去，以交易列表为准；IA 是「发送日+7」的单日报告，改模板只影响 7 天后。
   **改 IA 模板的入口是交易列表右上 Create New**（不是模板文档页）；**Handsontable 单元格只认
   `focus()` textarea + 真实键盘 `type` + `Enter`**，`fill()` / JS dispatch 不提交）。
5. **把断货 SKU 加进网页预检的断货清单**（`https://api.vilavi.cn/pb/settings`；
   存 `sh-erpnext-test:/opt/pb-orders/pb_orders/runtime/jobs.sqlite` 的 `app_settings.default_no_stock`）。
   **最容易漏** —— 不改的话下一批预检仍会把它当有货放过。**到货后必须删掉**。
   命令见 reference 文档 §2 第 5 步。

到货后按 Notion 记录重发，变化同样回写 Notion。

### C. 用 API 而不是点页面（Agent 首选）

网页与 JSON API 共用 `web/jobs_service.py`，同一 job 模型 / 产物 / 审计。
Agent 做「检查 → 出件」优先走 `/api/v1`，不要用浏览器自动化。

```bash
BASE=https://api.vilavi.cn/pb
H="Authorization: Bearer $PB_ORDERS_API_KEY"

# 1) 库存预检（上传 SPS New 订单 csv）
curl -sS -X POST "$BASE/api/v1/checks" -H "$H" \
  -F "raw_csv=@新订单.csv" -F "no_stock=SKU-1,SKU-2"

# 2) 轮询状态 / 取产物
curl -sS "$BASE/api/v1/jobs/<job_id>" -H "$H"
curl -sS -OJ "$BASE/api/v1/artifacts/<artifact_id>/download" -H "$H"

# 3) 继续出件（只传 Packslip PDF；补发时带 reorder）
curl -sS -X POST "$BASE/api/v1/jobs/<check_job_id>/fulfill" -H "$H" \
  -F "packslip=@Packslip 美中 xN.pdf" -F "reorder=137924672,137940567"

# 或一次到位：POST /api/v1/jobs（order_csv + packslip）
```

- scope：`check` / `fulfill` / `read`；建 Key 见 `AGENT_HANDOFF.md` §4.5。
- 同输入重复 POST 会被去重（响应带 `deduplicated: true`）；要重跑用
  `POST /api/v1/jobs/{id}/retry`。
- 网络错误可安全重试：带 `Idempotency-Key`，同 key 同输入会重放原响应。
- 补发 `-N` 由服务端登记分配（`order_number_usage`），**不要手改 CSV**；
  冲突返回 `409 reorder_conflict`（换后缀或先查已用号）。
- OpenAPI：`https://api.vilavi.cn/pb/api/docs`。
- **先探活**：`GET $BASE/api/v1/healthz` 必须是 JSON `{"status":"ok"}`。若返回钉钉登录 HTML，
  镜像还没有 `/api/v1`（未合并 PR ≠ 已部署）。那时不要扫码，改走签会话 cookie 的
  `POST /pb/jobs/{id}/fulfill`（必须打公网 `/pb/`，直连 8412 会因 CSRF Path 403）。
- 现网（2026-11-02）已部署，Key 在本机 gitignore 的 `pb_orders/.env`（`PB_ORDERS_API_KEY`）。
  建新 Key：`docker exec pb-orders-web python -m web.api_keys create --name agent --scopes check,fulfill,read`。
- 通途导入 xlsx 的下载名带 `checked0stock` 词干，是 `kind=tongtool` 那一份，不要漏下。
  1:1 按 Packslip **页数 = 件数**（数量 2 的一行占 2 页）。
- **Label 与背贴按页序 1:1**：`service.py` 的 `df_join 行序 == PDF 页序`，背贴第 N 页对应标签第 N 页；
  手工重做子集必须从两个 PDF 用**同一 package index 列表**同序抽取，只抽 label 配全量背贴会错位。
  文件名 `xN` 的 **N = 真实标签页数（包裹数），不是 shipment 数**：
  2026-11-19 实例 37 个 shipment → 40 个包裹标签，再加 137770200 旧标签 1 页 → `x41`。

## 铁律

- **`Vendor Style` 大小写不敏感**（`CEN961NLinen-SageGreen-138` ≡ 大写形态）；对齐时统一 `upper()`。
- **别用通途库存判定断货**：通途为标记发货要先「报溢」，可用库存恒 0 是常态。
- **通途「已发货 / despatched」是 WXP 的正常顺序，不是异常**：WXP **先在通途标记发货** →
  把标签/背贴发给美中 → 美中有货就发走，**没货才回头告诉我们**。所以「打单后才发现无货」是常态；
  通途里这单会挂着「已发货」，**不要叫它状态异常、也不要要求改成未发**。处理方式是
  **在 GS「处理特殊订单」登记**，月底核算时把这单删掉即可。判真发仍只看 **UPS 取件**。
- **EN 侧不扣减通途库存**（2026-10 确认）→ EN 的 Bin 数量**不能当可用库存**；
  尤其 **`美中USTX到货仓` 未执行收货**，账面数完全不代表可发，**一律不要看它**。
- **SO 的「未交量」≠ 在途**：货常常已经出境到目的仓。
- **invoice 的 H 行才带 PO 号**，D 行 PO 为空 —— 删无货单要整块删（H+D），否则留孤儿明细。
- **改 invoice CSV 必须保留第 1 行表头**：按行摘单时 `keep = [lines[0]]` 再处理数据行；
  交付前断言首格是 `Invoice Number`、数据行数 = H+D、文件名 `xN` = H 数、H 行总额 = txt。
  **同额两张票会让「总额对」和「少一张」同时成立** —— 金额校验不够，必须查表头与逐行差异。
  D 行重复整票总额，`H ≠ ΣD` 是正常，别用 D 行求和校验。
- **通途付款时间 = 导入 xlsx 的 `PO Date`，不是导入时间**：超过 3 个月不会出现在仓库的
  「等待配货」。补发旧 PO 时 `service.run_job` 会把导入 xlsx 的 PO Date 超过 90 天的自动
  改成当天（源 CSV/报告保留原值）；手工单行补建时 PO Date 必须写成**文本**
  `yyyy-MM-dd HH:mm:ss`，写成 Excel 日期单元格会被通途拒收。
- **SPS IA 模板取值**：有货 SKU = Stock **100**、On Order 数量/日期**留空**；无货 SKU = Stock **0**、
  On Order **50** + 到货日。不要给有货 SKU 填 On Order；取值没写死先问用户。
  覆盖模板会**生成新的 Template 文档**（旧链接变 `UNDEFINED`，看到旧值正常）；
  同一 advice date 重发会**多一份 IA**，交易列表以最新时间为准。
- **WSI/Cancel 回信要带 HTML 表格**：multipart/alternative（纯文本 + HTML），HTML 里嵌入原邮件表格
  并把 `Vendor Comment` 单元格填 `Cancel accepted`；只发纯文本会把表格压成一行。
- **Notion 只登记「断货 → 到货 → 发货」**：正常订单到货后美中暂时迟发不登记；
  建行前先按 PO 查重，已有行只追加备注。给 Diane 的 HTML 表格回复先发一封到
  `us@mxdeals.com` 自检表头/数据行，再发 Diane。
- **通途导入后的核查顺序**：先销售渠道选 **PotteryBarn** → 本页全选 → **重新核查**；
  导入前按完整订单号查重（重号整批失败），多明细 PO 落成 `-1/-2` 是正常。
- **报日期必须标来源**：SPS Order 的 `Ship No Later` / IA 计划值 / EN DN-Shipment 不能混说；
  IA 计划值不是 EN 出货 ETA。`TT0031010K0062878/80` 是**床楔形枕**（楔形白色153/194），
  不是三角靠枕；`CEN803NLinen-Black-153` 是**三角靠枕**（三角黑色153）。
- **绝不把邮件口令 / 账号密码写进仓库**；邮件里不出现 Tracy / 中间人 / 5% 佣金。

## 相关经验（docs/solutions）

- `docs/solutions/workflow-issues/pb-stockout-post-shipment-closed-loop.md` —— 打单后才发现无货的闭环：invoice 清理惯例、邮件成链、两套库存不能混用
- `docs/solutions/workflow-issues/pb-partial-package-unshipped-invoice-paid.md` —— 部分包裹未发：`Pack Level Carrier Tracking ID`、已付发票不重开、旧 UPS 标签 90 天与 Packslip 提取
- `docs/solutions/workflow-issues/pb-orders-tongtool-import-and-wxp-handoff.md` —— 通途导入（模板/渠道/账号）、先选渠道再本页全选重新核查、钉钉交接 WXP
- `docs/solutions/workflow-issues/pb-invoice-csv-header-loss.md` —— invoice CSV 摘单丢表头：行筛选保留表头 + 交付前结构断言（同额票是金额校验盲区）
- `docs/solutions/architecture-patterns/pb-orders-json-api-human-agent.md` —— 网页与 JSON API 共用服务层：双鉴权 / 幂等 / 补发号登记；现网判定与 compose 服务名
- `docs/solutions/workflow-issues/pb-replenishment-sizing-from-sales.md` —— 补货量估算：美中 Daneey 口径、通途订单表读法、剔除断货月、交付用 Excel
- `docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md` —— 断货判据 / PO→Tongtool Order 映射 / UPS 才算真发
- `docs/solutions/workflow-issues/sps-portal-ia-akn-operations.md` —— IA/AKN 操作 + **IA 模板取值口径**（有货 100/无 On Order；无货 0/50/到货日）与覆盖模板行为

## 相关 skill

- `pb-reconciliation` —— PB 月度对账 / TM 佣金 / UPS 交付核查（**不是**本 skill）
- `ups-track` —— 判「真发」用
- `tongtu-automation` / `tongtool-api` —— 通途库存与销量
