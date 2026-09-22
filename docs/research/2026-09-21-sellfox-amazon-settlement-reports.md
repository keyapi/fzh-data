---
okf: v0.1
type: Research
title: 赛狐 API 拉取 Amazon 账期报表 —— 可行性与覆盖度实测
description: Amazon 账期(Transaction/Summary) 在赛狐侧只有「插件获取报告」一条路且 API 不可触发抓取；实测 90 店仅 39 店有数据、只覆盖 2026-06/07；fileUrls 为 1 小时过期的 COS 预签名 URL
tags: [sellfox, amazon, settlement, report-center, plugin, tax, research]
timestamp: 2026-09-21
---

# 赛狐 API 拉取 Amazon 账期报表 —— 可行性与覆盖度实测

> 目的：财务报税需要各账号的 Amazon 账期报表（此前是财务拿 PDF 自己算）。
> 问题：**赛狐 API 能不能拉？能不能拉全 90 个账号 × 过去 3 个月？**
> 结论：**能拉，但只能拉「插件已抓过的」—— API 不能触发抓取。实测 90 店只有 39 店有数据，且只有 6/7 两个月。**
> 用户确认**只要 Amazon 官方报表、不要赛狐自算口径**（怕不准）⇒ **插件是唯一路径，51 个店需运营补抓**（见 §6）。

- 日期：2026-09-21
- 实测环境：赛狐代理 API（`api.vilavi.cn/sellfox`），只读
- 实测数据落盘：`out/amazon_settlement/`（gitignored）

## 1. 赛狐侧三条 Amazon 报表路径（先分清）

用户原有认知「有的走标准 Amazon API，有的走自定义报表，账期（非 v2）要插件」—— 实测**完全吻合**：

| 路径 | 端点 | 生成方式 | 能否含账期 |
|---|---|---|---|
| **A. 亚马逊原报告** | `/api/report/center/add.json` + `pageList.json` | **赛狐服务端生成**（走 Amazon SP-API） | ✗ 报告类型列表里**没有账期/结算**（有 VAT、库存、仓储费、赔偿…） |
| **B. 自定义报表** | `/api/custom/report/reportList.json` + `pageList.json` | 赛狐自建报表引擎 | ✗ 是赛狐自己的分析表，不是 Amazon 结算文件 |
| **C. 插件获取报告** | `/api/report/center/task/getPlugPageList.json` | **浏览器插件在账号登录态下抓回**，存 COS | **✓ 只有这条有** |

**所以 Amazon 账期（Transaction / Summary）只有 C 一条路。**

### C 是纯读接口 —— 这是本次最关键的一条

- `getPlugPageList` 只**返回**已有任务与文件地址，没有任何参数能"发起抓取"。
- 旁证 1：`创建报告任务`（`/api/report/center/task/createTask.json`）的 `reportType` 只支持 `PRODUCT_SALE_REPORT` 一个值。
- 旁证 2：A 路径的报告类型枚举里没有账期。
- ⇒ **插件抓取这个动作只能在赛狐/紫鸟的 UI 侧发生。**
  （注：这一步是**从接口能力反推**的，没有实测 UI；但三条接口都无写入口，结论可靠。）

## 2. 插件报告能拿到什么

`PlugTaskOpenQo` → `reportType` 四种：

| reportType | 含义 | 文件形态 |
|---|---|---|
| 3 | Transaction | csv 或 zip |
| **4** | **Summary** | **pdf** ← 财务现在自己算的那种 |
| 5 | Deferred transaction | csv 或 zip |
| 6 | FBAInboundConvenience | csv |

返回字段：`shopId` / `shopName` / `marketplaceName` / `reportDayType`（月份，`yyyy-MM`）/
`status`（0 获取中 / 1 成功 / 2 失败）/ `fileUrls`。

**实测只有 3 和 4 存在**（Transaction 64 条、Summary 26 条），5 和 6 一条没有。

## 3. 覆盖度实测（90 店 × 2026-06/07）

窗口拉 `2026-06-01 → 2026-09-21`，**只返回 90 条任务**，覆盖月份只有 `2026-06`、`2026-07`。

| 店群/账号 | 店数 | 2026-06 | 2026-07 |
|---|---|---|---|
| Daneey-LELEFIDO | 12 | 交易+汇总 | 交易+汇总 |
| 云途汇德-Novelledo | 2 | 交易+汇总 | 交易 |
| FZH深圳-Strusery | 12 | — | 交易 |
| 君缘-Johnear | 13 | — | 交易 |

**有数据 39/90 店；完全没抓过 51 店；缺部分月份 25 店。**

没抓过的 9 个店群（51 店）：`Centrade-WOWMAX`(2)、`TOODDLY-Daneey`(2)、`VERCART`(12)、
`北京固祥-US`(4)、`北京如森-Rucener`(12)、`北京如泱-BJRYECLTD`(2)、`北京熙锦-Jalnoddsa`(2)、
`方州汇绍兴-Xalviortex`(3)、`百纳-BNCKTRD`(12)

**两个硬缺口：**
1. **8 月、9 月一条都没有** —— 财务要"过去 3 个月"，实际只有 2 个月。
2. 覆盖是**整店群**式的（运营按品牌去插件跑，跑过的品牌全店都有，没跑过的全空），说明这是**人工按账号逐个执行**的，不是系统周期性任务。

## 4. 下载约束（做归档必须知道）

- **`fileUrls` 是 1 小时有效的临时签名 URL**（腾讯 COS，`q-sign-time` 参数可见）。
  ⇒ **不能存链接**，必须「调 API 拿新 URL → 立刻下载落盘」。
- 路径带 `q-sign-algorithm=sha1&q-ak=<access-key-id>&q-sign-time=...` —— 是对象存储预签名，非永久地址。

## 5. 归档实测结果

`SELLFOX_API/fetch_amazon_settlement.py` 实测：**下载 79 个文件，0 失败**（34MB）。

| 项 | 值 |
|---|---|
| PDF (Summary) | 26 个，每个约 1.3MB |
| ZIP (Transaction) | 53 个，758 B ~ 44 KB |

**内容抽验（确认不是错误页）：**
- 最小的 zip（758 B，IE/2026-06）解出 `2026-06MonthlyTransaction.csv`，10 行 —— 仅表头与定义块，**当月该站点确实无交易**，是真报表。
- 最大的 zip（44 KB，US/2026-06）解出 722 行交易数据。
- PDF 用 pypdf 读出 1 页文字，含 `Seller fulfilled selling fees` / `Promotional rebate refunds` —— **是真正的 Amazon 结算摘要**。

## 6. 报税口径结论：只要 Amazon 官方报表 → 插件是唯一路径

用户澄清两点：①报税是**给中国税务报、销售额相关的口径，不是国外 VAT**；
②**不要赛狐自己算的（怕不准），就要 Amazon 官方报表**。

因此结论回到插件路径，**51 个店的缺口必须由运营补齐**。

### 曾经评估过、但被排除的替代方案（留档，避免重复提议）

`/api/financial/v2/monthProfit/shopSummary.json`（利润报表-店铺汇总）**服务端生成、不依赖插件**，
字段含 `productSales`（销售额）、`salesNum`、`orderIncome`、`refund`、`grossProfit`，
支持 `shopIds` 过滤与 `profitCaliberType=settlement|shipment`，按月（`yyyyMM`，最长 12 个月）。

实测（2026-07，CNY，结算口径）：

| 范围 | 销售额 |
|---|---|
| 全部店铺（不传 `shopIds`） | 4,450,681.69 |
| 仅 `Centrade-WOWMAX-US` | 2,472,552.27 |
| 仅 `TOODDLY-Daneey-US` | 226,125.58 |
| 两家相加 | 2,698,677.85 ✓ 可加 |

它的优势是**覆盖包括「插件从未抓过」店群在内的全部店铺**（`Centrade-WOWMAX-US` 一家占全站 56%，
而它恰无插件报表）。**但它是赛狐自己计算的口径，非 Amazon 官方结算文件 —— 用户明确不要。**

> 备注：`利润报表-店铺汇总` 即使传了 `shopIds` 也只返回聚合行（`shopId` 恒为 `null`），
> 逐店需按店铺分别调用。若将来改用此口径，注意这一点。

### 因此本次的交付重点回到「缺口清单」

需运营在赛狐/紫鸟的插件侧补抓的 **9 个店群 / 51 店**（清单见 `out/amazon_settlement/_gaps.csv`），
外加 **8 月、9 月两个月完全没有**。

**待财务确认：报税要的是 Summary（PDF，结算汇总）还是 Transaction（明细可自行汇总销售额）** ——
两者插件侧都在抓，但覆盖不同（Summary 只有 26 条、Transaction 64 条）。

## 7. 复现

```bash
# 看缺口、不下载
uv run python SELLFOX_API/fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21 --dry-run

# 下载归档（默认落 <repo_root>/out/amazon_settlement）
uv run python SELLFOX_API/fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21

# 只要 Summary PDF
uv run python SELLFOX_API/fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21 --types 4

# 覆盖度快查（轻量，只打印矩阵）
uv run python SELLFOX_API/probe_amazon_reports.py --start 2026-06-01 --end 2026-09-21
```

归档产物：

```
out/amazon_settlement/
  <报告月>/<店铺名>/<类型>-<原始文件名>     # 如 2026-07/Daneey-LELEFIDO-US/Summary-...pdf
  _manifest.csv     本次实际下载了什么（月/店铺/类型/文件/字节/状态）
  _gaps.csv         哪些店铺缺哪个月 → 交给运营去插件补抓
  _failures.csv     下载失败明细（本次为空）
```

## 8. 坑

1. **`getPlugPageList` 的 `startTime`/`endTime` 过滤的是任务时间**，实测传 6/1–9/21 只回 6/7 月的任务 —— 说明 8/9 月确实没有任务，不是过滤问题。
2. **不要用 `requests.Session()` 查 EN**；本脚本用裸 `urllib`。
3. **限流**：代理 ~1 rps；脚本内 API 调用 `sleep(2)`，下载走 COS 不占赛狐配额。
4. **归档文件名会很长**（原始名含 UUID 前缀），已加类型前缀便于人工辨认；如需整洁可后续加 `--rename` 选项。
5. **`reportDayType` 对 reportType=6 是区间**（`yyyy-MM-dd到yyyy-MM-dd`），其余是 `yyyy-MM` —— 归档目录用 `safe_name()` 兜底，否则含 `:` 会炸 Windows 路径。

## 9. 来源

- 本地文档镜像（Apifox）：
  - `SELLFOX_API/docs/api-reference/报告中心/插件获取报告/插件获取报告.md`
    （<https://app.apifox.com/web/project/1827046/apis/api-410910348-run>）
  - `.../报告中心/亚马逊原报告/Amazon原表下载-生成任务.md`、`Amazon原表下载-查询任务进度.md`
  - `.../报告中心/赛狐报告/创建报告任务.md`
  - `.../数据/自定义报表/获取自定义报表列表.md`
    （<https://app.apifox.com/web/project/1827046/apis/api-501584641-run>）
- 脚本：`SELLFOX_API/fetch_amazon_settlement.py`（下载归档）、`SELLFOX_API/probe_amazon_reports.py`（覆盖度核查）
- 代理与鉴权约定：`SELLFOX_API/AGENT_HANDOFF.md`
