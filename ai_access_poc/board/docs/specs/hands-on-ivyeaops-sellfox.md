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

3. **赛狐 Key**：写在 `ai_access_poc/open_webui/.env` 的 `SELLFOX_PROXY_API_KEY`（启动脚本会注入进程，不进 git）。

4. **一键启动**：

```powershell
cd d:\Work\赛狐\Cursor
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\start_ivyeaops_sellfox.ps1
```

打开 http://127.0.0.1:8001 — 默认用户 `admin`（密码以本机 `IvyeaOps-sellfox\server\.env` 为准；PoC 生成时常用 `poc-admin-change-me`，请登录后改掉）。

5. **拉搜索词进 cache**（选店分析前必做一次）：

```powershell
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\ingest_sellfox_for_ivyeaops.ps1
# 默认店 TOODDLY-Daneey-US；可改环境变量 SELLFOX_POC_SHOP_NAME
```

---

## 广告（赛狐只读）— 必点

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 侧边栏 **领星 ERP**（UI 文案仍叫领星；数据已走赛狐） | 能进工作台 |
| 2 | 确认「启用数据（只读）」已开；**不要**开「操作/写」 | `lingxing_enabled=true`，operate=off |
| 3 | 店铺列表 | 约数十～上百家赛狐店（探针级 99） |
| 4 | 选 **TOODDLY-Daneey-US**（或你 ingest 过的店）→ Optimizer **Run** | 出现否词 / 收割候选；降 bid/加预算为空属正常（缺报表） |
| 5 | 点工单确认 / 批量执行 | **应失败或不可用**（无赛狐写 API） |

独立核对（可不启 UI）：`board/out/candidates.csv` 与 Optimizer 同源阈值；live ingest 后条数可能随日期变化。

---

## 不依赖领星的其它模块 — 选点

| 模块 | 路径 | 需要 | 没有 Key/CLI 时 |
|------|------|------|-----------------|
| 头程比价 | `/freight` | Excel | 可直接用 |
| 资讯 | `/news` | 网络 + 可选 LLM | 可看 RSS；摘要可能弱 |
| Skill 中心 | `/skill-hub` | 兜底 LLM | 无模型则生成失败 |
| AI 问答 / 生图 | `/assistant` `/imagegen` | API Key | 配置页填 |
| Listing | `/listing` | LLM；完整主图建议 Docker `amazon-image-workflow` | 可手填；Sorftime 回退仅 1 图 |
| 市场 / 首页 / 打法 | `/` `/market` `/playbook` | **Sorftime Key**（或卖家精灵） | 留空即可，报错可忽略 |
| 外部智能体 | `/agents` | 本机 `claude` / `codex` 路径填系统配置 | 未装则跳过 |

---

## Portal `:8088` 是什么

仅 **Chat 壳 + Ops stub 摘要**。完整产品体验以 **`:8001`** 为准。可选 `IVYEAOPS_UPSTREAM=http://host.docker.internal:8001` 做 health，**不会**把 SPA 嵌进 `/ops`。

---

## 安全提醒

- 写广告：**关**  
- 运营审签字：**搁置**  
- AGPL 树在 `IvyeaOps-sellfox`，**勿**拷进 fzh-data  
