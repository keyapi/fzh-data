# AGENT_HANDOFF — 板 PoC

## 目标

IvyeaOps fork → 赛狐只读：`sellers` + `sp_search_term_report`（规范化 cache）→ optimizer 出候选；写路径硬禁。

## 落点

| 位置 | 内容 |
|------|------|
| `d:\Work\赛狐\IvyeaOps-sellfox` | 完整应用（AGPL fork） |
| `ai_access_poc/board/` | 本仓：映射、偏差、checklist、探针脚本 |
| `SELLFOX_API/client.py` | 共享传输（proxy/direct） |

## 环境

```text
SELLFOX_PROXY_API_KEY=...
SELLFOX_PROXY_BASE_URL=https://api.vilavi.cn/sellfox
SELLFOX_WINDOW_MODE=aggregate
SELLFOX_POC_SHOP_NAME=TOODDLY-Daneey-US
FZH_DATA_ROOT=<path-to-fzh-data>   # 供外部树 import client
```

## 禁止

- 整仓 vendoring 进 fzh-data  
- 启用 lingxing_operate / 赛狐广告写  
- optimizer 按日循环 createTask（用 aggregate ingest）  
- 扩展第二期 READ_DATASETS（campaigns/keywords…）

## 验收

见 [docs/specs/b1-b6-checklist.md](docs/specs/b1-b6-checklist.md)。
