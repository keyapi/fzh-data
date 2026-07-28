---
okf: v0.1
type: Spec
title: IvyeaOps × 赛狐 本机体验清单
description: 无领星账号时，在 :8001 用赛狐只读跑完整 SPA 的点击步骤
tags: [ivyeaops, sellfox, hands-on, ux]
timestamp: 2026-07-27
---

# 本机体验清单（主体验 = `:8001`，不是 Portal `:8088`）

## 前置（已由脚本完成则可跳过）

1. **uv 装后端**（本机约定用 uv，不用全局 pip）：

```powershell
cd d:\Work\赛狐\IvyeaOps-sellfox\server
uv venv .venv
uv pip install -r requirements.txt pandas
# 若尚无 server\.env：按 docs/CONFIG.md 或重跑官方 install.ps1 生成 admin
```

2. **构建前端**（需 Node 18+）：

```powershell
cd d:\Work\赛狐\IvyeaOps-sellfox\client
npm install --registry=https://registry.npmmirror.com
npm run build
```

3. **赛狐 Key + 兜底 LLM**：都在 `ai_access_poc/open_webui/.env`  
   - `SELLFOX_PROXY_API_KEY`（推荐 Proxy）  
   - `OPENAI_API_BASE_URL` + `OPENAI_API_KEY`（公司 new-api / api.vilavi.cn）  

4. **一键启动**（会 seed hub_settings 的 assistant_*，并注入赛狐只读）：

```powershell
cd d:\Work\赛狐\Cursor
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\start_ivyeaops_sellfox.ps1
# 仅 seed LLM：
# powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\seed_ivyeaops_hub_from_owui.ps1
```

打开 http://127.0.0.1:8001 — 用户 `admin`（密码见本机 `server\.env`）。  
**默认主题 light**；若仍黑底：右上角切浅色，或清 `localStorage['ivyea-ops.theme']` 后刷新。

5. **拉搜索词进 cache**（选店分析前必做一次）：

```powershell
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\ingest_sellfox_for_ivyeaops.ps1
```

---

## 广告（赛狐只读）— 必点

侧栏入口已改名为 **赛狐 ERP**（路由仍为 `/lingxing`）。

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 侧边栏 **赛狐 ERP** | 顶栏 Chip：**赛狐 Proxy 已配置**（不再「未配置凭证」） |
| 2 | 「启用赛狐数据(只读)」；**不要**开操作/写 | 数据已启用；写关 |
| 3 | 店铺列表 | 赛狐店列表 |
| 4 | 选 **TOODDLY-Daneey-US** → Optimizer **运行优化引擎** | 否词/收割候选 |
| 5 | 点工单确认 | 应失败/不可用 |

「个人工作台」左上角品牌位：**不用改**（上游壳）。头程比价：可不关心。

---

## 不依赖领星的其它模块 — 选点

| 模块 | 路径 | 需要 | 没有 Key/CLI 时 |
|------|------|------|-----------------|
| 头程比价 | `/freight` | Excel | 可直接用 |
| 资讯 | `/news` | 网络 + 可选 LLM | 可看 RSS；摘要可能弱 |
| Skill 中心 | `/skill-hub` | 兜底 LLM | 无模型则生成失败 |
| AI 问答 / 生图 | `/assistant` `/imagegen` | new-api Key（seed） | 启动脚本已 seed assistant_* |
| Listing | `/listing` | LLM；完整主图建议 Docker `amazon-image-workflow` | 可手填；Sorftime 回退仅 1 图 |
| 市场 / 首页 / 打法 | `/` `/market` `/playbook` | **Sorftime Key**（或卖家精灵） | 留空即可，报错可忽略 |
| 外部智能体 | `/agents` | Claude/Codex CLI（≠ DeepSeek HTTP） | 可照搬上游；未装 CLI 则只看项目列表 |

---

## Portal `:8088` 是什么

仅 **Chat 壳 + Ops stub 摘要**。完整产品体验以 **`:8001`** 为准。可选 `IVYEAOPS_UPSTREAM=http://host.docker.internal:8001` 做 health，**不会**把 SPA 嵌进 `/ops`。

---

## 功能板块总览（对照上游 README「工具 / AI & 系统」）

完整产品侧边栏都在；**赛狐 PoC 只替换「领星 ERP」读数**。其它板块代码已随 SPA 可用，依赖各自 Key/CLI。

### 工具

| 侧边栏 | 路径 | 干什么 | FZH 现状 |
|--------|------|--------|----------|
| 首页 | `/` | 运营驾驶舱（大盘/关键词/竞品…） | UI 可进；数据源默认 Sorftime，无 Key 则空 |
| 市场调研 | `/market` | 关键词/ASIN 调研报告 | UI 可进；需 Sorftime（或卖家精灵）Key |
| 打法推荐 | `/playbook` | SOP / 打法 | 同上，市场数据源 |
| Listing 工作台 | `/listing` | 文案/套图 | 需兜底 LLM；完整主图建议 Docker 采集服务 |
| 一键图片翻译 | `/image-translate` | 图翻 | 需模型/配置 |
| 分析工具 | `/tools` | 深度分析等 | 需 LLM / 数据源 |
| **赛狐 ERP** | `/lingxing` | 广告浏览/优化/工单 | **赛狐只读已接**；Chip 显示 Proxy/官网；写关 |
| Skill 中心 | `/skill-hub` | 自然语言生成 Skill | 需 LLM（兜底 = new-api） |

### AI & 系统

| 侧边栏 | 路径 | 干什么 | FZH 现状 |
|--------|------|--------|----------|
| AI 问答 | `/assistant` | 聊天 | **兜底 = api.vilavi.cn**（seed 自 open_webui/.env） |
| AI 生图 | `/imagegen` | 生图 | 需图像模型 Key |
| 知识库工作台 | `/brain` | 本地知识库 | IvyeaAgent / GBrain |
| 外部智能体 | `/agents` | Claude Code / Codex CLI | **照搬上游**；≠ new-api DeepSeek |
| 服务器终端 | `/terminal` | 浏览器里终端 | 本机运维 |
| 服务器监控 | `/servmon` | 资源监控 | 本机运维 |
| 头程比价 | `/freight` | 货代 Excel 比价 | FZH 可不关心 |
| 用户管理 | `/users` | 账号 | 管理 |
| 系统配置 | `/hub-settings` | 模型/数据源/智能体路径 | Sorftime、claude_bin、codex_bin |
| 资讯 | `/news` | RSS + 摘要 | 摘要吃兜底 LLM |

右下角 **Ivyea Agent** Dock：内置本地 Agent。

## 浏览器 E2E（品牌化 + 凭证 + LLM）

| 步骤 | 结果 |
|------|------|
| 默认主题 light；侧栏 **赛狐 ERP** | PASS（需清旧 `ivyea-ops.theme=dark` 缓存） |
| Chip **赛狐 Proxy 已配置** | PASS（`data_source=sellfox_proxy`） |
| 选店 → 运行优化引擎 | PASS（既有） |
| seed assistant → api.vilavi.cn / **deepseek-v4-flash** | PASS（`seed_ivyeaops_hub_from_owui.ps1` 默认 v4；`deepseek-chat` 网关无渠道会 503） |
| AI 问答 `/assistant` 发消息收回复 | PASS（2026-07-27 E2E；约 15s 内返回） |
| 资讯 `/news` 立即刷新 | PASS（约 60 条 digest） |
| 知识库 `/brain` | PARTIAL（IvyeaAgent :8765 未起；fallback 关键词检索） |
| 外部智能体 | 照搬；DeepSeek 不走此页 |

## 安全提醒

- 写广告：**关**  
- 运营审签字：**搁置**  
- AGPL 树在 `IvyeaOps-sellfox`，**勿**拷进 fzh-data  
- hub_settings / .env **勿提交** Key  
