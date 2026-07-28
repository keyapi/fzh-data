# AGENT_HANDOFF — 板 PoC

## 目标

IvyeaOps fork → 赛狐只读：sellers + 五杠杆所需报表/实体/利润 → optimizer 出候选；写路径硬禁。

**主体验**：仓外完整 SPA `http://127.0.0.1:8001`（不是 Portal stub）。  
人手步骤见 [docs/specs/hands-on-ivyeaops-sellfox.md](docs/specs/hands-on-ivyeaops-sellfox.md)。

## 落点

| 位置 | 内容 |
|------|------|
| `d:\Work\赛狐\IvyeaOps-sellfox` | 完整应用（AGPL fork，`uv venv` + `client/dist`） |
| `ai_access_poc/board/` | 本仓：映射、偏差、checklist、启动/ingest 脚本 |
| `SELLFOX_API/client.py` | 共享传输（proxy/direct）；含通用 `pull_cpc_report` |

## 环境

```text
SELLFOX_PROXY_API_KEY=...          # 通常在 open_webui/.env
SELLFOX_PROXY_BASE_URL=https://api.vilavi.cn/sellfox
SELLFOX_WINDOW_MODE=aggregate
SELLFOX_POC_SHOP_NAME=BJRYECLTD-US   # Phase2 标定店；旧默认 TOODDLY 仍可用
SELLFOX_READONLY_POC=1
FZH_DATA_ROOT=<path-to-fzh-data>
```

Python：**用 uv** 管理 IvyeaOps `server\.venv`（`setup_ivyeaops_uv.ps1`）。

## 一键脚本（fzh-data）

| 脚本 | 作用 |
|------|------|
| `scripts/setup_ivyeaops_uv.ps1` | uv venv + deps + 可选 npm build + `.env` |
| `scripts/start_ivyeaops_sellfox.ps1` | 注入赛狐 env，启 `:8001`（默认**不**弹系统浏览器；人手加 `-OpenBrowser`） |
| `scripts/ingest_sellfox_phase2.ps1` | **推荐**：实体 + SearchTerm/Targeting/Campaign + asin_profit → cache |
| `scripts/ingest_sellfox_for_ivyeaops.ps1` | 仅搜索词（Phase1） |
| `scripts/seed_ivyeaops_hub_from_owui.ps1` | 从 `open_webui/.env` 写入 hub `assistant_*`（默认 `deepseek-v4-flash`） |
| `scripts/sellfox_board_poc.py` | 独立 runner（可不启 UI） |

## 2026-07-28 阶段结论（Phase2 ingest）

- 五杠杆相关 dataset **已接线**（报表 + manageData + 利润）。矩阵：[docs/specs/phase2-dataset-gap.md](docs/specs/phase2-dataset-gap.md)。  
- 标定店 `run_store(596841)` → 35 候选（含降/加 bid）；加预算视阈值可为 0。  
- **五杠杆 ≠ 五桶** — `CONCEPTS.md`。  
- 经验沉淀：[docs/solutions/architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md](../../docs/solutions/architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md)。  
- Gotcha：Targeting 过滤关键词匹配类型；`monthProfit` 用 `reportList`；利润 `pageSize`≤200。

## 2026-07-27 阶段结论（E2E）

- AI 问答 503：`deepseek-chat` 无渠道 → 默认改为 `deepseek-v4-flash`。  
- `/brain` 仍 PARTIAL：依赖未启动的 IvyeaAgent。

## 经验教训

1. `api.vilavi.cn` 在线 ≠ 模型可用；chat/completions 必须带模型名冒烟。  
2. 表现报表 ≠ 实体配置；bid/预算杠杆两者都要 ingest。  
3. 不要把 advertise「五桶」当成 IvyeaOps「五杠杆」。  
4. optimizer 用 aggregate cache，禁止按日循环 createTask。

## 禁止

- 整仓 vendoring 进 fzh-data  
- 启用 lingxing_operate / 赛狐广告写  
- optimizer 按日循环 createTask（用 aggregate ingest）  

## 验收

- B1–B6：[docs/specs/b1-b6-checklist.md](docs/specs/b1-b6-checklist.md)  
- UI 体验：[docs/specs/hands-on-ivyeaops-sellfox.md](docs/specs/hands-on-ivyeaops-sellfox.md)  
- Phase2：[docs/specs/phase2-backlog.md](docs/specs/phase2-backlog.md)

## 下一步

- 运营审 **DEFERRED** → 用 Phase3 计划刷新简报（候选已含 bid 类）。  
- **上游 IvyeaOps merge** / **IvyeaAgent**：见 [`docs/superpowers/plans/2026-07-28-phase3-ops-merge-agent.md`](../../docs/superpowers/plans/2026-07-28-phase3-ops-merge-agent.md)。  
- **E2E**：只用 Cursor 内置浏览器；`start_ivyeaops_sellfox.ps1` 默认不弹 Chrome。  
- **2026-07-28 内置浏览器 E2E**：BJRYECLTD-US → 运行优化引擎 → **候选 35**（否词/收割/降bid/加bid；加预算 0 因利用率&lt;85%）。  

经验沉淀另见：[docs/solutions/integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md](../../docs/solutions/integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md)。
