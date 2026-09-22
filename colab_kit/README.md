---
okf: v0.1
type: Guide
title: colab_kit — Colab notebook 读写改工具箱
description: 在 Google Drive 上取/备份/读格/插格/替换/语法自检/回写/回读比对/并发守卫 Colab notebook
updated: 2026-09-22
---

# colab_kit — Colab notebook 读写改工具箱

> 本文给人看。Agent 请直接读 [AGENT_HANDOFF.md](AGENT_HANDOFF.md)。

## 这是什么

业务同事的流水线（Overstock 订单处理、PB 订单处理…）都跑在 **Google Colab notebook** 里。
要改它们的代码，只能在登录墙后面手点，或者走 **Drive API**。这套工具箱把后者固化下来：

**网络命令**（读写 Drive）

| 命令 | 干什么 |
|------|--------|
| `meta <id>` | 看 `modifiedTime` / `version` / `canEdit` / `canModifyContent` |
| `fetch <id> --out P` | 下载 `.ipynb` |
| `backup <id>` | 下载到仓库**外**的带时间戳兜底备份 |
| `guard <id> --expect MT` | 并发守卫：`modifiedTime` 不等于期望值就退出非 0 |
| `write <id> --from P` | 整份回写（multipart，保留 Colab mimeType） |
| `verify <id> --from P --expect-changed 8,9` | 回读逐 cell 比对，断言"只有这几格变了" |

**本地命令**（纯文件操作，可离线）

| 命令 | 干什么 |
|------|--------|
| `cells P` | 列每格序号 / 类型 / 首行 |
| `dump P --index N` | 打印某格全文 |
| `find P --text S` | 按内容找格（定位锚点） |
| `insert P --after N --from F` | 在第 N 格之后插入新格 |
| `backup-cell P --index N --after M` | 把某格全文复制成新格（「先备份再改」用） |
| `sed P --index N --old S --new S` | 格内精确替换；**默认要求 old 唯一命中** |
| `syntax P [--index N]` | 语法自检（IPython 魔法行中和，保留缩进） |
| `diff P_A P_B` | 两个 `.ipynb` 的 cell 级差异 |

## 标准流程（改一格的安全姿势）

```bash
ID=1nnpuKfOjfF0rixqNGWnkRrL-QvY_UzP0     # 换成目标 notebook id

uv run python colab_kit/colab_kit.py fetch  $ID --out /tmp/nb.ipynb
uv run python colab_kit/colab_kit.py guard  $ID --expect <fetch 打印出来的 modifiedTime>
uv run python colab_kit/colab_kit.py cells  /tmp/nb.ipynb
uv run python colab_kit/colab_kit.py backup-cell /tmp/nb.ipynb --index 5 --after 7
uv run python colab_kit/colab_kit.py sed    /tmp/nb.ipynb --index 5 --old '<旧>' --new '<新>'
uv run python colab_kit/colab_kit.py syntax /tmp/nb.ipynb --index 5
uv run python colab_kit/colab_kit.py write  $ID --from /tmp/nb.ipynb
uv run python colab_kit/colab_kit.py verify $ID --from /tmp/nb.ipynb --expect-changed 8,9
```

`verify` 那一步是**最便宜的保险**：它证明"只动了我该动的那一格，其余 cell 逐字未变"。

## 三条从实测来的注意

1. **改完必须让用户在 Colab 里 F5 刷新**。Drive 写回的是文件；用户开着的标签页内存里还是旧代码，直接重跑会跑旧代码，而且 Colab 的自动保存可能把你的改动覆盖回去。
2. **写前先 `guard`**。用户跑一次 cell，Colab 会把**执行输出**存回文件 —— 即使代码没改，`modifiedTime` 也会变。
3. **兜底备份别放仓库里**。业务 notebook 常把服务账号私钥内嵌在「安装依赖」那个 cell 里（见 AGENT_HANDOFF 的「私钥风险」）。默认备份目录是 `~/.claude/backups/colab/`，在仓库外。

## 依赖与凭证

- 依赖 `google-auth`、`google-api-python-client`（都已在根 `pyproject.toml`）。
- 凭证：服务账号私钥，取 `GSPREAD_SERVICE_ACCOUNT_FILE`；没设就沿目录向上找 `secrets/gsheets-service-account.json`（worktree 里凭证在父仓库）。
- 本机对 `googleapis` 常发 `SSL: UNEXPECTED_EOF_WHILE_READING` —— 工具箱内置 6 次退避重试，看到 `[retry n/5]` 是正常的。

## 测试

```bash
uv run pytest colab_kit/tests -q      # 本地纯函数（14 例）
```

网络命令用真实 notebook 只读手测：`meta` → `fetch` → `guard` → `verify`（`verify` 不写任何东西）。

## 为什么单独成模块

「读 / 写 / 改 / 回读校验」是一套**跨项目复用**的动作：本次是 Overstock 的 notebook，下次可能是 PB 订单处理本地化、或另一个同事的 notebook。此前每次都现写 Drive 调用，既慢又容易在"改完不校验"上翻车（`!zip` 那次就是静默失败、报错点离根因很远）。做成 CLI 后，改 notebook 的每一步都有对应命令与退出码。
