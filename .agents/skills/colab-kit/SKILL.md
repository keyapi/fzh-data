---
name: colab-kit
description: >
  在 Google Drive 上读写改 Colab notebook（.ipynb）的工具箱：取/备份/列格/找格/插格/
  格内替换/语法自检/回写/回读比对/并发守卫。用户提到 Colab、notebook、ipynb、
  改 Colab 代码、备份 cell、改同事的 notebook、Drive API 改 notebook、
  notebook 本地化迁移 时触发。不要用于 Google 表格/Colab 的共享权限
  （那是 google-drive-permissions），也不要用于通途/赛狐的网页自动化导出（那是 web-automation）。
metadata:
  module: colab_kit
  docs: docs/solutions/developer-experience/colab-notebook-drive-api-editing.md
  updated: 2026-09-22
---

# Colab notebook 读写改

完整做法见 `docs/solutions/developer-experience/colab-notebook-drive-api-editing.md`。这里是可复跑清单。

## 必须先做

1. 读 `colab_kit/AGENT_HANDOFF.md`（命令表 + 7 条实测坑）。
2. 凭证在**父仓库**：`secrets/gsheets-service-account.json`（或设 `GSPREAD_SERVICE_ACCOUNT_FILE`）。worktree 里没有。
3. **一律 `uv run python`**，不要在本机系统 python 上 pip 装包。
4. 写回前先 **`guard`**，改完让用户在 Colab 里 **F5 刷新**。

## 改一格的安全姿势

```bash
ID=<notebook id>
uv run python colab_kit/colab_kit.py fetch  $ID --out /tmp/nb.ipynb
uv run python colab_kit/colab_kit.py guard  $ID --expect <fetch 打印的 modifiedTime>
uv run python colab_kit/colab_kit.py cells  /tmp/nb.ipynb
uv run python colab_kit/colab_kit.py backup-cell /tmp/nb.ipynb --index N --after M   # 先备份
uv run python colab_kit/colab_kit.py sed    /tmp/nb.ipynb --index N --old '旧' --new '新'
uv run python colab_kit/colab_kit.py syntax /tmp/nb.ipynb --index N
uv run python colab_kit/colab_kit.py write  $ID --from /tmp/nb.ipynb
uv run python colab_kit/colab_kit.py verify $ID --from /tmp/nb.ipynb --expect-changed M,N
```

## 铁律

- **`alt=media` 读**：`/export?mimeType=` 对 Colab 文件 403。
- **multipart 写 + 显式 mimeType**（`application/vnd.google.colaboratory`），否则类型可能被改。
- **`sed` 要求唯一命中**：notebook 里「生效代码 + 注释掉的老代码」常只差一个 `#`。
- **`syntax` 中和魔法行必须保留缩进**（丢缩进 = 假 IndentationError）。
- **`verify --expect-changed` 是必做步骤**，不是可选项 —— 它是"只动了我该动的"唯一证据。
- **兜底备份放仓库外**：业务 notebook 常内嵌服务账号私钥。

## 不要做

- 不要把 notebook 原文（可能含私钥）粘进文档或 commit。
- 不要在用户还开着 Colab 标签页、没刷新时就说"改好了"。
- 不要跳过 `verify`。
- 不要用本机系统 python。

## 相关经验（docs/solutions）

踩过的坑与设计取舍，动手前先读：

- `docs/solutions/tooling-decisions/colab-kit-notebook-edit-toolbox.md` —— 为什么把「改同事的 Colab notebook」做成独立工具箱 colab_kit（而不是塞进 google_drive_permissions）
