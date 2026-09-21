# chatgpt — Agent 交接

> **把 ChatGPT 接到我们自己的 MCP 服务器上（自定义连接器 / 智能体应用）**
> 人读：[README.md](README.md) ｜ OKF：[docs/index.md](docs/index.md)

## 这是什么

ChatGPT 网页版可以做 MCP 客户端，把外部 MCP 服务器挂成「应用/连接器」。
本子项目记录这条线的接入方法与实测结论 —— 目前只接了 FAC（ERPNext 测试站）。

## 何时用

- 要在 ChatGPT 里加我们某个 MCP 服务器 → 先看 [docs/reference/connector-requirements.md](docs/reference/connector-requirements.md)（通用要求），再看该服务器的专文
- 加的是 FAC / ERPNext → [docs/reference/fac-mcp-oauth-connect.md](docs/reference/fac-mcp-oauth-connect.md)
- ChatGPT 报错要定位 → 各专文的「报错阶梯」

## 三条最容易错的

1. **身份验证选 OAuth**。别选「访问令牌/API 密钥」（选它才冒出「标头方案」下拉，那条路是死的），别选「无身份验证」（401）。
2. **别照搬 Claude Desktop 的排错**。ChatGPT 没有本地进程 —— `~/.mcp-auth` 清理、`taskkill /F /IM node.exe`、`EADDRINUSE`、「URL 必须写在 `--transport` 前」**全都不适用**。
3. **`Allowed Public Client Origins` 不用为 ChatGPT 改**。那字段是纯 CORS（只约束浏览器侧 XHR），ChatGPT 是服务端注册 + 浏览器顶层跳转授权。该字段的语境是 MCP Inspector 那类浏览器客户端。

## 铁律

- **未验证的别写成已验证**。ChatGPT 官方文档我们拿不到一手访问，很多结论来自第三方检索 —— 这类内容必须标注来源与「检索所得」，参照 `docs/solutions/documentation-gaps/unverified-external-api-claims-in-docs.md`。
- **区分「服务端实测」与「OpenAI 侧推断」**。我们只能实测自家服务器；OpenAI 侧的行为（回调地址、开发者模式门槛）只能引用外部来源并标注。
- 新增 MCP 服务器时，**通用要求写进 `connector-requirements.md`，服务器特有的写新专文**，不要fork一份通用要求。

## 关联

- `docs/mcp-setup.md` — MCP 选型与安装（Claude Desktop / Codex / Cursor 宿主）
- `docs/fac-mcp-setup.md` — FAC 在 Claude Desktop 的接入（本子项目的对照路径）
- `docs/agent-guide.md` — Agent 行为规则与代码约定
