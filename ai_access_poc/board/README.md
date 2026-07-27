# board PoC — IvyeaOps 赛狐只读板

人读入口。Agent 见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)；OKF 见 [docs/index.md](docs/index.md)。

## 默认拍板

| 项 | 值 |
|----|-----|
| 工作树 | `d:\Work\赛狐\IvyeaOps-sellfox`（**不**进 fzh-data） |
| 上游 | `Hector-xue/IvyeaOps`（AGPL）分支 `sellfox-readonly-poc` |
| 窗口模式 | `SELLFOX_WINDOW_MODE=aggregate`（整窗一次 createTask） |
| 标定店 | `TOODDLY-Daneey-US` |
| 凭证 | `SELLFOX_PROXY_API_KEY` → `api.vilavi.cn/sellfox` |
| 后端端口 | `8001`（**主体验入口**） |
| Python | **uv** 管理 `IvyeaOps-sellfox/server/.venv` |

## 快速开始（无领星）

```powershell
# 一次：uv + 前端
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\setup_ivyeaops_uv.ps1
# 每次：启动 SPA + 注入赛狐只读
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\start_ivyeaops_sellfox.ps1
# 分析前：拉搜索词 cache
powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\ingest_sellfox_for_ivyeaops.ps1
```

打开 http://127.0.0.1:8001 → 领星页（数据=赛狐）选店 → Optimizer。  
详细点击清单：[docs/specs/hands-on-ivyeaops-sellfox.md](docs/specs/hands-on-ivyeaops-sellfox.md)。

## 与壳 / Portal 的分工

- **壳**（`open_webui/`）：Chat 拉数 + Tool JSON summary + Terminal 深挖  
- **板 UI**（仓外 IvyeaOps `:8001`）：完整工作台 + 赛狐只读广告分析  
- **Portal `/ops`**：候选**摘要 stub**，不是完整 SPA  

## 共享代码

复用本仓 [`SELLFOX_API/client.py`](../../SELLFOX_API/client.py)。外部树 `sellfox_openapi.py` 经 `FZH_DATA_ROOT` import client。
