---
okf: v0.1
type: Log
title: sellfox_mcp 变更日志
description: sellfox_mcp 子项目变更历史
tags: [sellfox, mcp, log]
---

# 变更日志

## 2026-09-20

- **初始化 OKF bundle**：新建 `sellfox_mcp/` 模块（README + AGENT_HANDOFF + `docs/` + `scripts/`）。
  **起因**：FAC（ERPNext）接通后接着问「赛狐能不能也接 MCP」；调研发现赛狐有官方托管 MCP，
  且结论在三轮验证中改过两次，需要一个**可复现**的落脚点而不只是一份结论文档。
- **新增**: [scripts/probe_mcp.py](../scripts/probe_mcp.py) — **只读探测脚本**（标准库、无依赖）。三档能力：
  `--check-token`（验凭据 + IP 白名单）、`--list-tools`（列工具、按「只读/非破坏性写/破坏性写」三分类）、
  `--call <tool>`（调只读工具）。鉴权支持 `--auth auto|api-creds|mcp-key|none`。
  - **内置安全护栏**：写工具前缀（`edit_`/`create_`/`close_`/`delete_`/`update_`/`remove_`/`set_`）
    与只读白名单外的工具**一律拒绝**（退出码 2），需显式 `--allow-write` 才放行。
    理由：那 9 个写工具会改**线上广告**（`edit_sp_campaign` 单次可改 100 条）。
  - **实测验证过**（不是写完就提交）：`--check-token` → `code=0 msg=success`；
    `--list-tools` → 23 个工具、三分类 `13/1/9`；`--call get_shop_page_list` → 返回真实数据；
    写工具护栏 → 退出码 2 正确拒绝。
- **新增**: [docs/reference/official-mcp.md](reference/official-mcp.md) — **完整操作参考**。端点与协议、
  **两条鉴权路径对照表**（API 账号凭证 ✅ 可用 vs 后台 `X-MCP-Key` ❌ `40027` 未启用）、
  23 个工具的三分类清单、`create_ad_download_task` 的文档对应关系、9 个写工具的 schema 特征、
  实测原始输出（凭据/握手/只读调用/路径 B 被挡四段）、与自建 `sellfox-api-proxy` 的凭证暴露取舍、未决项。
- **纪律**：本模块所有内容遵循两条硬要求 —— ① **凭证不落盘**（只从 `SF_ID`/`SF_SECRET`/`SF_MCP_KEY`
  环境变量读，提交前用 `git grep` 自查）；② **业务数据不入库**（探测返回真实店铺/订单，
  文档只留结构不留内容）。
- **未决**：9 个写工具的真伪未验证（需问客服，或在**明确指定的测试店铺**上用无副作用载荷验证，
  **须显式授权**）；路径 B 何时开通（等客服）。**本模块未做任何接入配置改动。**
