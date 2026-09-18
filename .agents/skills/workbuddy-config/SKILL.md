---
name: workbuddy-config
description: >
  在 WorkBuddy（腾讯桌面 Agent / CodeBuddy Code）里配置公司 new-api 网关
  (api.vilavi.cn) 的自定义模型（deepseek-v4-flash / deepseek-v4-pro），
  自动写入/更新 %USERPROFILE%\.workbuddy\models.json。流程：要 sk- key →
  备份 → 合并写入 → 提示重启 WorkBuddy → 可选 curl 验证。
  当用户提到"WorkBuddy 配置"、"workbuddy 模型"、"models.json"、
  "deepseek 模型"、"deepseek-v4-flash"、"公司 AI 网关"、"任务完成没下文"、
  "workbuddy 接 api.vilavi.cn"、"配置 deepseek" 等时触发。
  不要用于 Codex++ / Codex Desktop（另一套供应商配置，见 codex-desktop-setup-guide.md）；
  不要用于赛狐 / ERPNext / 通途 / 库存成本等业务模块。
compatibility: >
  目标文件在用户本机：Windows %USERPROFILE%\.workbuddy\models.json；
  macOS/Linux ~/.workbuddy/models.json。不涉及仓库内文件。
metadata:
  module: docs
  doc: docs/solutions/developer-experience/workbuddy-custom-model-newapi-config.md
  updated: 2026-09-03
---

# WorkBuddy 接公司 new-api 自定义模型 — 自动配置

让用户的 WorkBuddy 用上公司 `deepseek-v4-flash`。Skill 固定流程：
**要 key → 备份 → 合并写入 models.json → 提示重启 → 可选连通性验证**。

## 关键事实（决定成败）

- WorkBuddy 自定义模型配置在 `%USERPROFILE%\.workbuddy\models.json`，是一个 **JSON 数组**，可能已有其它模型条目，**必须保留**。
- 两个必对字段：
  - `url` 必须带 `/v1`：`https://api.vilavi.cn/v1`。WorkBuddy 只会自动补 `/chat/completions`，**不会**补 `/v1`。
  - `useCustomProtocol` 必须 `false`。`true` = URL 原样透传，会打不到 `/chat/completions` → 发消息只回「任务完成」无正文。
- 模型名 `deepseek-v4-flash` 生产渠道可用；历史名 `deepseek-chat` 无渠道会 503。
- WorkBuddy 内部用 `custom-local:` 前缀但在发请求时会自动剥掉，配置里**不要**写 `custom-local:`。
- 现象对照与兜底见 [配置文档](docs/solutions/developer-experience/workbuddy-custom-model-newapi-config.md)。

## 执行流程

1. **确认目标机器**：先确认是在"用户当前这台电脑"上配置。若是帮别人远程配置，让对方在目标机器上执行本流程，或提供该机器的可写路径。

2. **要 key**：向用户索要 `sk-` 开头的令牌（公司 new-api 后台 https://api.vilavi.cn → 钉钉登录 → 左侧「令牌管理」→ 复制/新建）。用户没有 key 时，引导其去后台领取后再回来。**绝不猜测或编造 key。**

3. **定位并备份 models.json**：
   - 路径：Windows `%USERPROFILE%\.workbuddy\models.json`；macOS/Linux `~/.workbuddy/models.json`。
   - 先备份：`Copy-Item`/`cp` 复制为 `models.json.bak-<YYYY-MM-DD>`（与原件同目录）。
   - 用 Read 读取现有内容。文件不存在 → 从空数组 `[]` 开始。

4. **合并写入**（关键：保留已有其它模型条目，不覆盖）：
   - 解析现有数组。若已有 `id == "deepseek-v4-flash"` 的条目 → 只更新其字段；否则 **append** 一条。
   - 目标条目：

```json
{
  "id": "deepseek-v4-flash",
  "name": "deepseek-v4-flash",
  "vendor": "Custom",
  "url": "https://api.vilavi.cn/v1",
  "apiKey": "<用户的 sk- 令牌>",
  "supportsToolCall": true,
  "supportsImages": false,
  "supportsReasoning": true,
  "useCustomProtocol": false,
  "reasoning": {
    "supportedEfforts": ["low", "medium", "high"]
  }
}
```

   - 用 Write 把整个数组写回 `models.json`（UTF-8，**无 BOM**）。

5. **验证写入**：重新 Read `models.json`，确认：deepseek-v4-flash 条目在、`url`/`useCustomProtocol` 正确、**其它原有条目仍在**。

6. **提示重启**：让用户**完全退出** WorkBuddy（右下角托盘图标也要右键退出）再重新打开；然后在模型下拉里选 `deepseek-v4-flash`，发一句「你好」验证有正常回复。

7. **可选连通性验证**：若用户愿意，用 curl 直测网关（不要把完整 key 打进聊天/文档）：

```bash
curl.exe -s -w "\nHTTP:%{http_code}" -X POST https://api.vilavi.cn/v1/chat/completions \
  -H "Authorization: Bearer <key>" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":8}'
```

   期望 `HTTP:200` 且有 `choices`。`503` = 模型名无渠道；`404` = url 少了 `/v1`；`401` = key 无效。

## 安全边界

- **key 只写进用户本机 `models.json`；绝不写进仓库文件、聊天记录或文档。**
- 不覆盖 `models.json` 里已有的其它模型条目。
- 备份文件留在用户主目录，不进仓库。
- 不做任何会改动仓库内文件的步骤（本 skill 只碰用户主目录的 models.json）。

## 排错速查

| 现象 | 原因 |
|------|------|
| 发消息只显示「任务完成」无正文 | `useCustomProtocol=true` 或 `url` 缺 `/v1` → 打到裸根 |
| 请求到 `.../chat/completions` 但返回错误页 | `url` 少了 `/v1`（应为 `https://api.vilavi.cn/v1`） |
| curl `/v1/chat/completions` 返回 401 | key 无效或令牌额度异常 |
| curl 返回 503 | 模型名无渠道，确认是 `deepseek-v4-flash` |
| 改完仍无正文 | 试把 `supportsReasoning` 设为 `false` 复测（reasoning 参数可能被网关拒） |

## 相关

- [WorkBuddy 配置文档](docs/solutions/developer-experience/workbuddy-custom-model-newapi-config.md) — 现象对照表 + 兜底
- 勿混淆 Codex++/Codex Desktop（[codex-desktop-setup-guide.md](docs/codex-desktop-setup-guide.md)），那是另一套「供应商配置」体系
