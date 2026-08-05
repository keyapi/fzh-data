---
okf: v0.1
type: Spec
title: 统一 AI 接入 C′ — 双 PoC 实施计划
description: Portal 融合下的壳 PoC（Open WebUI）与板 PoC（IvyeaOps 赛狐只读适配）可执行计划；含 READ_DATASETS↔赛狐映射与验收标准
tags: [ai-agent, poc, open-webui, ivyeaops, sellfox, portal]
created: 2026-07-24
updated: 2026-07-24
depends_on:
  - docs/research/2026-07-24-unified-ai-access-independent-review.md
---

# 统一 AI 接入 C′ — 双 PoC 实施计划

> **上游裁决**: 独立复审纠偏后推荐 **C′ 门户融合**（OWUI 壳 + IvyeaOps 板），非裸 A′、非全量 B。  
> **本阶段目标**: 用最小代码验证两条腿各自通不通；**不**做门户 nginx 生产上线、**不**接通广告写操作。  
> **禁止**: 把未验证的 `advertise/` 输出当运营真理；赛狐写 API 未上线前禁用 IvyeaOps 写工单执行。

## 0. 成功标准（两周盒）

| PoC | 必须通过 | 明确不做 |
|-----|----------|----------|
| **壳 PoC** | 浏览器 Chat 触发：拉取指定店铺近 N 天 SP 搜索词报告 → 落盘可下载；Open Terminal 仅 Docker | 不做广告写；不做运营看板 UI |
| **板 PoC** | IvyeaOps fork：赛狐签名通；`sellers` + `sp_search_term_report`（或等价规范化表）可读；规则引擎能对**一份**规范化搜索词窗跑出候选列表（只建议） | 不改全量 READ_DATASETS；不启用 put/add 写路由 |
| **共同** | 凭证只走环境变量 / 已有 `SELLFOX_API/.env` 或代理 Key；报告进 gitignore 目录 | 不提交 CSV/密钥 |

**总判定**: 任一条失败 → 记录翻车点再选型；两条都通 → 再开 Portal（nginx + 钉钉）专题。

---

## 1. 架构（PoC 范围）

```text
[运营浏览器]
    │
    ├─(壳) Open WebUI :3000 ── Tool: sellfox_pull_search_term
    │         │                    └─ 复用 SELLFOX_API signed_post / createTask
    │         └─ Open Terminal (Docker only)
    │
    └─(板) IvyeaOps :8001 ── sellfox_openapi 替换 lingxing_openapi
              │                READ_DATASETS 仅改 2 个 key（本 PoC）
              │                optimizer 读规范化 cache（写 UI 隐藏）
              └─ 禁用 lingxing_operate 执行入口
```

Portal（`/chat` `/ops`）留到两条 PoC 绿了再做。

---

## 2. 板 PoC — 赛狐 ↔ IvyeaOps 映射

### 2.1 传输层

| IvyeaOps | 赛狐替换 |
|----------|----------|
| `lingxing_openapi.make_sign` (MD5+AES) | `SELLFOX_API`：`authenticate` + `signed_post`（HMAC-SHA256） |
| token `access-token` / refresh | `client_credentials` → `access_token`（见 `fetch_ad_reports.py`） |
| host `openapi.lingxing.com` | `SELLFOX_API_DOMAIN` 或 `api.vilavi.cn/sellfox` 代理 |
| 成功码 `200/0/1` | `code == 0` |

**交付物**: `sellfox_openapi.py`（或 `erp_openapi.py` 适配器接口）+ 单测：mock token + 签名字符串金样（不打真网也可先测签名）。

### 2.2 身份与分页语义

| 概念 | 领星 | 赛狐 | 适配 |
|------|------|------|------|
| 店铺主键 | `sid` int | `shopId` string（`shop/pageList` 的 `id`） | 网关内映射表 `sid↔shopId`；PoC 可用配置写死 1 店 |
| 列表分页 | `length` + `offset` | `pageSize` + `nextToken` | `_extract_rows` 读 `data.itemList`；循环 nextToken |
| 报表 | 按日 JSON `report_date` | 异步 `createTask` 区间 + xlsx | **见 2.3**（本 PoC 最大块） |

### 2.3 READ_DATASETS：PoC 只改 2 个 key

#### A. `sellers` ← 店铺列表

| 项 | 领星 | 赛狐 |
|----|------|------|
| route | `GET /erp/sc/data/seller/lists` | `POST /api/shop/pageList.json` |
| 入参 | `{}` | `{ pageSize: 200 }`（已有脚本） |
| 行字段 | `sid, name, marketplace, …` | `id→sid(映射), name, marketplaceId, region, …` |

#### B. `sp_search_term_report` ← 搜索词（规则引擎否词/收割输入）

领星：按日 `POST /pb/openapi/newad/queryWordReports`，行字段约 `query, cost, clicks, orders, sales, campaign_id, …`。

赛狐推荐路径（与现网一致）：

1. `POST /api/cpc/download/createTask.json`  
   - `adTypeCode=sp`, `reportTypeCode=adSearchTermReport`  
   - `timeUnit=daily`（保留日粒度，便于对齐优化器窗）或先 `summary` 降复杂度  
   - `shopIds=[shopId]`, `reportStartDate/EndDate`
2. 轮询 `pageList` → `downloadUrl`
3. 解析 xlsx → **规范化行**写入 cache（列对齐优化器）：

| 优化器期望（领星归一后） | 赛狐 xlsx / API 常见列（需用真实文件标定） |
|--------------------------|---------------------------------------------|
| `query` | 客户搜索词 / search term |
| `cost` | 花费 / 广告花费 |
| `clicks` | 点击量 |
| `orders` | 订单数 / 7 天总订单数…（**必须用同窗口定义**，PoC 记不确定项） |
| `sales` | 销售额 |
| `campaign_id` | 广告活动 ID |
| `ad_group_id` | 广告组 ID |
| `match_type` | 匹配类型 |

**阻抗处理（强制）**: 不要让 `lingxing_optimizer._agg` 直接按日打赛狐 createTask（会炸配额）。PoC 做法：

```text
sellfox_report_ingest(shopId, start, end)
  → 1～若干 createTask
  → 下载 xlsx
  → 拆成「按日 bucket」或「整窗聚合表」
  → 写入与 lingxing_cache 兼容的 payload
fetch_dataset("sp_search_term_report")
  → 只读 cache / 规范化表（不再打领星 URL）
```

若整窗聚合更简单：给 optimizer 加 PoC 开关 `SELLFOX_WINDOW_MODE=aggregate`，跳过按日循环，直接一轮候选（文档标明与生产领星行为差异）。

### 2.4 本 PoC 明确不改的 READ_DATASETS

`sp_campaigns` / `sp_keywords` / `sp_keyword_report` / `asin_profit` / FBA … — **第二期**。  
无 keyword 报表时：降 bid/加 bid 候选会空；**否词+收割仍可验证**（只靠搜索词）。验收以「否词/收割候选非空或可解释为空」为准。

### 2.5 写路径

- UI：隐藏或 disable「操作开关 / 确认执行」  
- `lingxing_operate` 调用赛狐写：直接 `raise NotImplementedError("sellfox ad write API absent")`  
- 候选「生成工单」可改为「导出 CSV 供人工在赛狐后台执行」

### 2.6 板 PoC 任务拆解

| ID | 任务 | 预估 |
|----|------|------|
| B1 | fork IvyeaOps 到独立目录或 submodule（勿污染 fzh-data 主业务） | 0.5d |
| B2 | `sellfox_openapi` + 配置项 + probe（店铺列表） | 1–2d |
| B3 | `sellers` 注册表改赛狐 | 0.5–1d |
| B4 | 搜索词 ingest（createTask→xlsx→规范化 cache） | 2–4d |
| B5 | 接 optimizer 只跑搜索词杠杆；关写 | 1–2d |
| B6 | 用**真实一店**跑通；输出候选 JSON + 已知偏差清单给运营审 | 1d |
| | **合计** | **约 6–10.5 人天** |

---

## 3. 壳 PoC — Open WebUI

### 3.1 部署（开发机 / 单台 4C8G 试跑）

- Open WebUI 单容器 + **Open Terminal 独立容器**（Docker 网络 internal；官方安全清单）  
- 模型：`api.vilavi.cn` OpenAI 兼容  
- 用户：先管理员账号；多用户隔离留 Portal 期再开 Terminals

### 3.2 Tool 范围（最小）

`sellfox_pull_sp_search_term(shop_id|shop_name, days) -> {task_id, filepath, row_count}`

- 实现：抽 `SELLFOX_API/fetch_ad_reports.py` 为可 import 库函数，或 Tool 内嵌副本（注明同源）  
- 密钥：Tool Valves / 环境变量；**不给运营 Workspace Tool 创建权**  
- 输出目录：容器卷 `/data/sellfox_reports/`（gitignore）

### 3.3 Skill（弱 Level A）

Import 一条 Markdown Skill：`$赛狐搜索词拉取` — 固定步骤：问店铺 → 调 Tool → 汇报路径与行数 → **禁止**自动否词。  
规则解释可另 Skill，正文可摘 IvyeaOps 方法论第五节（标注来源），**阈值数字留空待运营填**。

> **壳验收补记（2026-07-24）**：S1–S4 已绿。Tool 除 filepath 外须返回 JSON `summary`（totals + top CSV），深挖用 Docker Open Terminal；Pyodide Code Interpreter 为 legacy 且与 Terminal 同聊互斥。详见 `docs/solutions/tooling-decisions/owui-sellfox-xlsx-tool-summary-open-terminal.md` 与 `ai_access_poc/docs/specs/2026-07-24-shell-acceptance.md`。

### 3.4 壳 PoC 任务拆解

| ID | 任务 | 预估 |
|----|------|------|
| S1 | compose：OWUI + Open Terminal | 0.5–1d |
| S2 | 接 api.vilavi.cn 模型冒烟 | 0.5d |
| S3 | sellfox Tool + 真拉取 | 1–2d |
| S4 | Skill 导入 + 运营试用脚本（截图步骤） | 0.5d |
| | **合计** | **约 2.5–4 人天** |

---

## 4. 共同：运营校验（非代码，阻塞验收）

在板 PoC 产出候选后，组织运营负责人：

1. 对照 IvyeaOps 文档「优化方法论」与候选样例  
2. 标：可直接用 / 阈值要改 / 不适用家纺  
3. **签字前**不得把候选当自动执行依据  

壳 PoC 只验证「拉得到」；分析对错以板 PoC + 运营为准。

---

## 5. 顺序与依赖

```text
Week1:  S1–S3 与 B1–B3 并行
Week2:  B4–B6；S4；运营初审（若候选已出）
之后:   Portal nginx + 钉钉（新专题）；扩展 READ_DATASETS；写 API 再开 operate
```

---

## 6. 仓库落点约定（实施时遵守）

| 内容 | 建议路径 |
|------|----------|
| 壳 compose / Tool 源 | `ai_access_poc/open_webui/`（新建，本 PR 只出计划） |
| 板 fork | **独立 clone**（`../IvyeaOps-sellfox` 或单独私有 fork），适配补丁以 patch/分支记录；大体积勿塞进 fzh-data |
| 共享赛狐客户端 | 中期抽到 `SELLFOX_API/client.py` 供两边引用 |
| 报告/xlsx | 永远 gitignore |

---

## 7. 翻车信号（提前写进日报）

| 信号 | 含义 |
|------|------|
| createTask 长期「生成中」/ 限流 | 壳/板都要队列化；PoC 缩店铺与天数 |
| nextToken / itemList 与文档不符 | 更新映射，暂停扩数据集 |
| 订单字段窗口与领星不一致 | 候选不可比；先手工对齐定义再谈规则 |
| Open Terminal bare metal 误开 | 立即改回 Docker |
| 有人打开写开关点执行 | 视为事故；PoC 必须硬禁 |

---

## 8. 交付进度与下一切片

| 切片 | 状态 |
|------|------|
| 本 Spec + 索引 | 已交付 |
| 壳 PoC `feature/ai-access-shell-poc` | **已合并** [#113](https://github.com/keyapi/fzh-data/pull/113)（S1–S4） |
| 板 PoC `feature/ai-access-board-poc` | **已合并** [#116](https://github.com/keyapi/fzh-data/pull/116)（B1–B6；外部 fork 适配笔记在 `ai_access_poc/board/`） |

**当前下一步（非代码，阻塞 Portal）**：运营审 — 见 `ai_access_poc/board/docs/specs/ops-review-brief.md`（计划 §4）。

**再下一切片（需你确认启动）**：Portal nginx `/chat` + `/ops` + 钉钉专题；扩展 READ_DATASETS；写 API 后再开 operate。

---

## See also

- 独立复审（含纠偏 §8）: [2026-07-24-unified-ai-access-independent-review.md](2026-07-24-unified-ai-access-independent-review.md)  
- 赛狐拉取: `SELLFOX_API/fetch_ad_reports.py`  
- 赛狐搜索词任务: `SELLFOX_API/docs/api-reference/广告/天维度报告/创建广告下载任务.md`  
- 赛狐关键词实体: `SELLFOX_API/docs/api-reference/广告/基础数据/SP关键词投放.md`  
- IvyeaOps: `lingxing_data.py` / `lingxing_optimizer.py`
