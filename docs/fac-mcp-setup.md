# FAC MCP 部署指南（开发人员）

> 最后更新：2026-06-09  
> 面向：B 类技术开发同事  
> 用途：在 Claude Desktop（3P 模式）上连接测试服务器 `ensh.vilavi.cn` 的 FAC MCP  
> ⚠️ 当前仅测试环境可用，普通用户不可用（生产服务器未部署 FAC App）

---

## 一句话

FAC（Frappe Assistant Core）把 ERPNext 的 CRUD/报表/工作流暴露为 MCP 工具，让 Claude Desktop 能直接操作 ERPNext。连接需要 OAuth 2.0 + `mcp-remote` 桥接。

---

## 前置条件

- [ ] 测试站 `ensh.vilavi.cn` 已安装 FAC App，且你有账号
- [ ] 本机 Node.js ≥ 20（`node --version`）
- [ ] Claude Desktop **3P 模式**（Microsoft Store 版，`deploymentMode: "3p"`）
- [ ] 知道 3P 配置文件路径（见下一步）

---

## 第一步：找到配置文件

3P 模式配置文件路径：

```
%APPDATA%\..\Local\Packages\Claude_*\LocalCache\Roaming\Claude-3p\claude_desktop_config.json
```

> `Claude_*` 是一串随机字符（如 `Claude_pzs8sxrjxfjjc`），你的机器上不同。

用任意文本编辑器打开它。

---

## 第二步：添加 FAC 配置

在 `mcpServers` 中添加 `fac` 条目（保留已有的配置不动）：

```json
{
  "mcpServers": {
    "fac": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://ensh.vilavi.cn/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp",
        "--transport", "http-first"
      ]
    }
  }
}
```

> ⚠️ **关键**：URL 必须在 `--transport` **前面**。写反了会报 `Invalid URL`。

如果你已经有 Playwright 或其他 MCP，加在一起即可：

```json
{
  "mcpServers": {
    "playwright": { "command": "npx", "args": ["@playwright/mcp@latest"] },
    "fac": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://ensh.vilavi.cn/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp",
        "--transport", "http-first"
      ]
    }
  }
}
```

---

## 第三步：重启 Claude Desktop

- **不是关窗口**，是系统托盘右键 → **Quit**（彻底退出）
- 重新打开 Claude Desktop
- Settings → Developer → 看到 `fac` 显示蓝色 ✓ 即成功

---

## 第四步：首次 OAuth 授权

重启后 `mcp-remote` 会**自动弹出浏览器**，跳转到 `ensh.vilavi.cn` 登录页：

1. 在浏览器中输入你的 ERPNext 账号密码
2. 点击 **授权**（Authorize）
3. 页面会自动关闭（回调到 `localhost:5535`）
4. Token 缓存到 `~/.mcp-auth/`，以后不再弹

> 如果弹窗后没点授权就关了：删掉 `~/.mcp-auth` 目录，重启 Claude Desktop 再试。

---

## 第五步：验证

**新开一个对话**（当前对话不会热加载 MCP 工具），输入：

> 帮我查一下系统里有哪些 DocType

或者：

> 列出我的待审批文档

如果能返回 ERPNext 数据，说明部署成功。

---

## 故障排除

| 症状 | 原因 | 解决 |
|------|------|------|
| `fac` 不出现 / `not a valid MCP server` | 3P 模式不支持 `url` 字段 | 必须用 `mcp-remote` 桥接，不能直接写 `"url"` |
| `Server disconnected` | OAuth 未完成 / 参数顺序错 | ① 清理 `~/.mcp-auth` ② 检查 URL 在 `--transport` 前 |
| `Invalid URL` / `Fatal error` | `--transport` 放在 URL 前面了 | URL 放最前面，`--transport http-first` 放最后 |
| `EADDRINUSE` 端口冲突 | 上次进程没杀干净 | `taskkill /F /IM node.exe` 然后删 `~/.mcp-auth` |
| fac 蓝色但工具不出现 | 当前对话创建时 FAC 还没连上 | **开新对话**，MCP 工具只在对话创建时加载 |
| 浏览器没弹出 | `mcp-remote` 未能打开浏览器 | 手动访问授权 URL（从日志中找 `Please authorize this client by visiting:` 开头的链接） |
| token 过期（1 小时后） | access_token 有效期 3600s | `mcp-remote` 会自动用 refresh_token 续期，无需手动处理 |

---

## 原理简述

```
Claude Desktop (stdio)
    │
    └─ npx mcp-remote (本地代理)
        │
        ├─ 首次：OAuth PKCE 流程
        │   ├─ 动态注册客户端 (RFC 7591)
        │   ├─ 弹出浏览器 → 用户登录授权
        │   └─ 获取 token → 缓存到 ~/.mcp-auth/
        │
        └─ 后续：用缓存 token 连接
            ├─ POST JSON-RPC 到 FAC endpoint
            └─ GET 接收 SSE 流
                │
                └─ https://ensh.vilavi.cn/api/method/
                    frappe_assistant_core.api.fac_endpoint.handle_mcp
```

`mcp-remote` 充当 stdio ↔ Streamable HTTP 的翻译层，同时管理 OAuth token 生命周期。

---

## 当前限制

| 环境 | FAC MCP 状态 | 用户范围 |
|------|-------------|---------|
| 测试站 `ensh.vilavi.cn` | ✅ 已部署 | 开发人员（B 类） |
| 生产站 | ❌ 未部署 | 不可用 |

- FAC App 安装需在生产服务器上 `bench get-app` + `bench install-app`
- 安装后配置 OAuth（`/.well-known/oauth-authorization-server` 自动生成）
- 普通用户（A 类）暂不涉及，等生产部署后再发通知

---

## 相关链接

- [Frappe Assistant Core GitHub](https://github.com/buildswithpaul/Frappe_Assistant_Core)
- [mcp-remote GitHub](https://github.com/geelen/mcp-remote)
- [MCP Streamable HTTP 规范](https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/transports/#streamable-http)
