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
| 后端端口 | `8001` |
| fzh-data 分支 | `feature/ai-access-board-poc` |

## 与壳的分工

- **壳**（`open_webui/`）：Chat 拉数 + Tool JSON summary + Terminal 深挖  
- **板**（本目录笔记 + 外部树）：规则引擎否词/收割**候选** → 人工去赛狐后台；**禁止写 API**

## 共享代码

复用本仓 [`SELLFOX_API/client.py`](../../SELLFOX_API/client.py)。外部树通过 `PYTHONPATH` 或拷贝薄适配器 `sellfox_openapi.py` 调用 client。
