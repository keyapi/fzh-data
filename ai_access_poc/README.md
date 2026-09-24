# ai_access_poc

统一 AI 接入 **C′** 的 PoC 代码区（壳 Open WebUI + 板 IvyeaOps 只读）。

| 角色 | 入口 |
|------|------|
| 人（壳） | [open_webui/README.md](open_webui/README.md) |
| Agent（壳） | [open_webui/AGENT_HANDOFF.md](open_webui/AGENT_HANDOFF.md) |
| 人（板） | [board/README.md](board/README.md) |
| Agent（板） | [board/AGENT_HANDOFF.md](board/AGENT_HANDOFF.md) |
| OKF | [docs/index.md](docs/index.md) |
| 计划 | [docs/research/2026-07-24-unified-ai-access-poc-plan.md](../docs/research/2026-07-24-unified-ai-access-poc-plan.md) |

**状态（2026-07-24）**：壳 S1–S4（[#113](https://github.com/keyapi/fzh-data/pull/113)）+ 板 B1–B6（[#116](https://github.com/keyapi/fzh-data/pull/116)）均已合并。  
**下一步**：运营审候选与偏差清单（见 [board/docs/specs/ops-review-brief.md](board/docs/specs/ops-review-brief.md)）；通过后再开 Portal 专题。

## 相关经验（docs/solutions）

踩过的坑与设计取舍，动手前先读：

- `docs/solutions/integration-issues/ivyeaops-assistant-deepseek-v4-model-name.md` —— IvyeaOps AI 问答 503 — deepseek-chat 无渠道，改用 deepseek-v4-flash
## 相关经验（docs/solutions）

踩过的坑与设计取舍，动手前先读：

- `docs/solutions/workflow-issues/mcp-to-chatgpt-bringup-lessons.md` —— 把 FAC / 赛狐 / NAS 三个 MCP 接上 ChatGPT —— 一次串起来的方法与四个教训
