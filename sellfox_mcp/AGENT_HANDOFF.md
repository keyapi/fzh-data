# sellfox_mcp — Agent 交接

> **赛狐官方托管 MCP 的接入参考与只读探测**
> 人读：[README.md](README.md) ｜ OKF：[docs/index.md](docs/index.md) ｜ 参考：[docs/reference/official-mcp.md](docs/reference/official-mcp.md)

## 这是什么

赛狐**官方**托管的 MCP 端点 `https://api-mcp.sellfox.com/mcp` 的接入资料 + 一个**只读**探测脚本。

与相邻模块的区别：

| 模块 | 是什么 |
|---|---|
| `sellfox_mcp`（本模块） | 赛狐**官方托管** MCP；只读探测 |
| `sellfox-api-proxy` | **我们自己的 VPS 代理**（`api.vilavi.cn/sellfox`），签发自己的 key |
| `SELLFOX_API` | 赛狐公开 OpenAPI 的客户端与 443 篇端点文档 |
| `sellfox_shipping` | 发货域业务 + 一个只覆盖发货的 FastMCP（7 工具） |

## 何时用

- 要接赛狐官方 MCP → 先读 [docs/reference/official-mcp.md](docs/reference/official-mcp.md)（端点、两条鉴权路径、工具清单）
- 要验证「凭据/IP 白名单/MCP 是否通」→ 跑 `scripts/probe_mcp.py`
- 要判断「赛狐广告到底能不能写」→ 见 `docs/reference/official-mcp.md` 第三节，**当前结论是「未验证」**

## 三条最容易错的

1. **两条鉴权通道别混**。`X-Sellfox-Client-Id`/`Secret`（API 账号，**可用**）与 `X-MCP-Key`（后台 MCP管理页，**未启用** `40027`）是**独立的两条路**。搞混会得出「MCP 不可用」的错误结论（我们踩过）。
2. **`initialize` 不校验凭据**。无凭据也 200 —— 「能 initialize」≠「有权限」。鉴权在**工具调用**时才生效。且服务**有状态**，`tools/list` 不带 `mcp-session-id` 会 400。
3. **写工具默认拒绝**。脚本对 `edit_*`/`create_*`/`close_*`/… 一律拒绝（退出码 2），除非 `--allow-write`。那 9 个会改**线上广告**。

## 安全纪律（硬要求）

- **凭证只从环境变量读**（`SF_ID` / `SF_SECRET` / `SF_MCP_KEY`），**绝不写进文件或提交**。
- **业务数据不入库**。探测会返回真实店铺/订单数据；文档与提交里只留**结构**（字段名、分页形状），不留内容。
- **不调用破坏性写工具**，除非有明确授权 + 已在隔离店铺验证。

## 当前状态

| 项 | 状态 |
|---|---|
| 路径 A（API 账号凭证） | ✅ 只读链路已实测跑通 |
| 路径 B（`X-MCP-Key`） | ❌ `40027 未启用MCP功能`，等赛狐开通 |
| 9 个破坏性写工具 | ⚠️ **未调用、未验证**；公开 API 文档里没有对应端点 |
| 接入动作 | **未做任何配置改动** |
