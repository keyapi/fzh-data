# AGENT_HANDOFF — 板 PoC

## 目标

IvyeaOps fork → 赛狐只读：`sellers` + `sp_search_term_report`（规范化 cache）→ optimizer 出候选；写路径硬禁。

**主体验**：仓外完整 SPA `http://127.0.0.1:8001`（不是 Portal stub）。  
人手步骤见 [docs/specs/hands-on-ivyeaops-sellfox.md](docs/specs/hands-on-ivyeaops-sellfox.md)。

## 落点

| 位置 | 内容 |
|------|------|
| `d:\Work\赛狐\IvyeaOps-sellfox` | 完整应用（AGPL fork，`uv venv` + `client/dist`） |
| `ai_access_poc/board/` | 本仓：映射、偏差、checklist、启动/ingest 脚本 |
| `SELLFOX_API/client.py` | 共享传输（proxy/direct） |

## 环境

```text
SELLFOX_PROXY_API_KEY=...          # 通常在 open_webui/.env
SELLFOX_PROXY_BASE_URL=https://api.vilavi.cn/sellfox
SELLFOX_WINDOW_MODE=aggregate
SELLFOX_POC_SHOP_NAME=TOODDLY-Daneey-US
SELLFOX_READONLY_POC=1
FZH_DATA_ROOT=<path-to-fzh-data>
```

Python：**用 uv** 管理 IvyeaOps `server\.venv`（`setup_ivyeaops_uv.ps1`）。

## 一键脚本（fzh-data）

| 脚本 | 作用 |
|------|------|
| `scripts/setup_ivyeaops_uv.ps1` | uv venv + deps + 可选 npm build + `.env` |
| `scripts/start_ivyeaops_sellfox.ps1` | 注入赛狐 env，启 `:8001`（启动时自动 seed hub） |
| `scripts/ingest_sellfox_for_ivyeaops.ps1` | 拉搜索词 → `data/sellfox_cache` |
| `scripts/seed_ivyeaops_hub_from_owui.ps1` | 从 `open_webui/.env` 写入 hub `assistant_*`（默认模型 `deepseek-v4-flash`） |
| `scripts/sellfox_board_poc.py` | 独立 runner（可不启 UI） |

## 2026-07-27 阶段结论（E2E）

- AI 问答 503 根因不是网关宕机，而是 `assistant_model=deepseek-chat` 在 `api.vilavi.cn` 默认组无可用渠道。  
- `seed_ivyeaops_hub_from_owui.ps1` 默认模型已改为 `deepseek-v4-flash`，保留 `IVYEA_ASSISTANT_MODEL` 覆盖。  
- 修正后浏览器 E2E 可在 `/assistant` 收到真实回复；`/lingxing` 优化引擎候选稳定 29 条。  
- `/brain` 仍为 PARTIAL：`IvyeaAgent` 本地服务未启动时会 fallback 关键词检索，不阻断问答主链路。

## 经验教训

1. `api.vilavi.cn` 连通性不能等价于“模型可用”；必须带模型名做 chat/completions 冒烟。  
2. seed 脚本的默认模型要跟 `new-api-deployment/Quick_Start.md` 保持一致，避免 `deepseek-chat` 这种历史名漂移。  
3. 浏览器 E2E 要逐页导航测试，不要在一个 evaluate 里连跳多路由（会触发 execution context 销毁）。

## 禁止

- 整仓 vendoring 进 fzh-data  
- 启用 lingxing_operate / 赛狐广告写  
- optimizer 按日循环 createTask（用 aggregate ingest）  
- 扩展第二期 READ_DATASETS（见 Phase2 backlog）  

## 验收

- B1–B6：[docs/specs/b1-b6-checklist.md](docs/specs/b1-b6-checklist.md)  
- UI 体验：[docs/specs/hands-on-ivyeaops-sellfox.md](docs/specs/hands-on-ivyeaops-sellfox.md)  
- Phase2：[docs/specs/phase2-backlog.md](docs/specs/phase2-backlog.md)

## 下一步

- 运营审 **DEFERRED**。Portal 仅壳+摘要（另 PR）；完整产品在 `:8001`。
- **Sorftime Key**：暂不接销售人员链接；市场调研 `/market` 保持 UI-only，待用户提供 Key 再测真实查词。
- **IvyeaAgent**：与 IvyeaOps 不同仓 — https://github.com/Hector-xue/ivyea-agent（本地 `:8765`）。未启动不影响 `/assistant` 直连 new-api；仅知识库/部分 text chain 需要。
- **Phase2 调研门禁（2026-07-28）已过**：缺口矩阵 [`docs/specs/phase2-dataset-gap.md`](docs/specs/phase2-dataset-gap.md)。实现顺序留给 **superpowers**：Targeting+keyword 实体 → Campaign+budget → 财务权限/margin override → 上游 merge → IvyeaAgent。

经验沉淀见：[docs/solutions/integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md](../../docs/solutions/integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md)。
