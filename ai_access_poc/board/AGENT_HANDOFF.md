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
| `scripts/start_ivyeaops_sellfox.ps1` | 注入赛狐 env，启 `:8001` |
| `scripts/ingest_sellfox_for_ivyeaops.ps1` | 拉搜索词 → `data/sellfox_cache` |
| `scripts/sellfox_board_poc.py` | 独立 runner（可不启 UI） |

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

运营审 **DEFERRED**。Portal 仅壳+摘要（另 PR）；完整产品在 `:8001`。
