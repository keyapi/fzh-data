---
okf: v0.1
type: Handoff
title: colab_kit — Agent 交接说明
description: Colab notebook 读写改工具箱：命令表、标准流程、私钥风险、实测坑
updated: 2026-09-22
---

# colab_kit — Agent 交接说明

> 人读文档: [README.md](README.md) ｜ 学习正文: [colab-notebook-drive-api-editing.md](../docs/solutions/developer-experience/colab-notebook-drive-api-editing.md)

## 这是什么

在 Google Drive 上**读 / 写 / 改** Colab notebook（`.ipynb`）的 CLI。
`.ipynb` 在 Drive 里就是一个 JSON 文件，没有专门 API —— 所以只能走 Drive API。

```bash
uv run python colab_kit/colab_kit.py <cmd> ...
```

## 命令表

| 类型 | 命令 | 说明 |
|------|------|------|
| 网络 | `meta <id>` | `modifiedTime` / `version` / `canEdit` / `canModifyContent` |
| 网络 | `fetch <id> --out P` | 下载 `.ipynb`（`alt=media`） |
| 网络 | `backup <id> [--dest D]` | 兜底备份到**仓库外**（默认 `~/.claude/backups/colab/`） |
| 网络 | `guard <id> --expect MT` | 并发守卫，不等则 exit 2 |
| 网络 | `write <id> --from P [--expect MT]` | 整份回写（multipart + 显式 mimeType） |
| 网络 | `verify <id> --from P [--expect-changed 8,9]` | 回读逐 cell 比对；`--expect-changed ""` 表示应无差异 |
| 本地 | `cells P` | 列每格序号/类型/首行 |
| 本地 | `dump P --index N` | 某格全文 |
| 本地 | `find P --text S` | 按内容找格（exit 1 = 没找到） |
| 本地 | `insert P --after N --from F [--cell-type code] [--title T]` | 插入新格 |
| 本地 | `backup-cell P --index N --after M` | 复制某格全文为新格（去 outputs、换新 id） |
| 本地 | `sed P --index N --old S --new S [--all]` | 格内替换；默认要求唯一命中 |
| 本地 | `syntax P [--index N]` | 语法自检（魔法行中和、**保留缩进**） |
| 本地 | `diff P_A P_B` | cell 级差异（exit 1 = 有差异） |

## 标准流程

见 [README.md](README.md) 的代码块。核心是 **`guard` → 本地改 → `syntax` → `write` → `verify --expect-changed`**。

## 私钥风险（务必遵守）

业务 notebook 常把**服务账号私钥**内嵌在「必点！安装依赖」那个 cell 里（本次处理的 Overstock notebook 就是）。

- `backup` 默认写到 `~/.claude/backups/colab/`，**在仓库外**；不要改到仓库里。
- **不要**把 notebook 原文粘进任何 commit 的文档。
- 提交前跑 `uv run python scripts/check_secrets.py`。

## 实测坑

1. **读必须 `alt=media`**。`/export?mimeType=application/x-ipynb+json` 对 Colab 文件返回 `403 Export only supports Docs editors files`（它的 mimeType 是 `application/vnd.google.colaboratory`，不算 Docs Editors 文件）。
2. **写要 multipart 并显式带 mimeType**，否则文件类型可能被改成普通 JSON。
3. **cell 定位要断言唯一命中**。notebook 里常见「生效代码 + 注释掉的老代码」，只差一个 `#`（`find` 会同时命中两格）；`sed` 因此默认拒绝多命中。
4. **语法自检的中和要保留缩进**。把 `!cmd` 换成 `pass  # !cmd` 时若丢掉缩进，会得到**假的 `IndentationError`**（实测白折腾一轮）。
5. **写前必 `guard`**。用户在 Colab 里跑一次 cell，Colab 会把执行输出存回文件 → `modifiedTime` 变了（代码没变也算）。
6. **改完提醒用户 F5**。否则他内存里还是旧代码；且 Colab 自动保存可能覆盖你的写回。
7. **本机 SSL 会抖**。`googleapis` 常发 `SSL: UNEXPECTED_EOF_WHILE_READING`，工具箱内置重试，看到 `[retry n/5]` 属正常。

## 测试

```bash
uv run pytest colab_kit/tests -q        # 14 例本地纯函数
```

网络命令对真实 notebook 只读手测（`meta`/`fetch`/`guard`/`verify`，不写）。
