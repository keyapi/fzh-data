---
okf: v0.1
type: Index
module: colab_kit
created: 2026-09-22
updated: 2026-09-22
---

# colab_kit — 文档索引

| 文档 | 说明 |
|------|------|
| [../README.md](../README.md) | 人读：工具箱是什么、命令表、标准流程 |
| [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) | Agent 交接：命令表、私钥风险、7 条实测坑 |
| [log.md](log.md) | 变更日志 |
| [../../docs/solutions/developer-experience/colab-notebook-drive-api-editing.md](../../docs/solutions/developer-experience/colab-notebook-drive-api-editing.md) | 学习正文：Drive API 读写 .ipynb 的做法与踩坑 |
| [../../docs/solutions/developer-experience/colab-shell-out-filename-spaces.md](../../docs/solutions/developer-experience/colab-shell-out-filename-spaces.md) | 学习正文：notebook 里别用 `!shell` 做文件操作（文件名含空格会让 `!zip` 静默失败） |

## 相关

- `.agents/skills/colab-kit/SKILL.md` — 触发词入口
- `google_drive_permissions/` — 只管 **共享权限**；本模块管 **内容读写改**（两套 API 面不同）
