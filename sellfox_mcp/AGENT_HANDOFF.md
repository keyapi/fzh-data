# sellfox_mcp — Agent 交接

> **赛狐官方托管 MCP 的接入参考与探测**
> 人读：[README.md](README.md) ｜ OKF：[docs/index.md](docs/index.md) ｜ 参考：[docs/reference/official-mcp.md](docs/reference/official-mcp.md)

## 这是什么

赛狐**官方**托管的 MCP 端点 `https://api-mcp.sellfox.com/mcp` 的接入资料 + 探测脚本。

与相邻模块的区别：

| 模块 | 是什么 |
|---|---|
| `sellfox_mcp`（本模块） | 赛狐**官方托管** MCP；接入参考 + 探测 |
| `sellfox-api-proxy` | **我们自己的 VPS 代理**（`api.vilavi.cn/sellfox`），签发自己的 key |
| `SELLFOX_API` | 赛狐公开 OpenAPI 的客户端与 443 篇端点文档 |
| `sellfox_shipping` | 发货域业务 + 一个只覆盖发货的 FastMCP（7 工具） |

## 何时用

- 要接赛狐官方 MCP → 先读 [docs/reference/official-mcp.md](docs/reference/official-mcp.md)
- 要验证「key/MCP 是否通」→ `--smoke-reads` / `--probe-writes`
- 要查某个业务能力有没有发布 → `--discover` 或 `--catalog`

## 三条最容易错的

1. **协议已改版**。现在是 **3 个元工具 + 371 个业务工具目录、无状态**；
   9 月那套「23 个扁平工具 + mcp-session-id」的写法**不适用**。
2. **`sf_execute` 需要 `contract_version`**，且大契约会被切成 `contract_parts`，要按 `part_index` 拼接并校验 SHA-256。
   脚本已自动处理；手写调用别漏。
3. **写工具没有独立工具名**，全走 `sf_execute`。按工具名 deny 已经没用；本机采用「`sf_execute` 人工确认」+ 脚本写护栏。

## 安全纪律（硬要求）

- **凭证只从环境变量读**（`SF_MCP_KEY` / `SF_ID` / `SF_SECRET`），**绝不写进仓库文件或提交**。
- **业务数据不入库**。文档与提交里只留**结构**（字段名、分页形状），不留店铺名/订单号/金额。
- **不做真实写**。写能力只用空参数干探测；真实写测试需测试店铺 + 回滚 + 显式授权。

## 当前状态（2026-11-24）

| 项 | 状态 |
|---|---|
| 路径 A（API 账号凭证） | ✅ 可用 |
| 路径 B（`X-MCP-Key` 子账号） | ✅ 已开通，权限随子账号角色 |
| 只读能力 | ✅ 店铺/订单/利润/SP广告活动实测 `complete`；平台仓库存 `complete` 但默认 0 行 |
| 写能力 | ✅ 14 个样本干探测 `INVALID_PARAMS`（鉴权通、路由通、校验生效），**零变更**；真实执行未验证 |
| 接入动作 | ✅ 本机 Claude Code 用户级已加 `Sellfox-MCP` |

## 相关经验

- [赛狐官方 MCP 换协议——子账号 X-MCP-Key 开通 + 元工具发现目录（零副作用验证写能力）](../docs/solutions/integration-issues/sellfox-mcp-subaccount-key-metatool-protocol.md)
