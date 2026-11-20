---
okf: v0.1
type: Reference
title: 自己重跑账期 Tax：只改桶名和汇率列，脚本不补 txt
date: 2026-11-11
category: workflow-issues
module: amazon_period_tax
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - "不用 Agent，自己跑 run_period_tax.py"
  - "判断文件名未改成规范名时 Tax 会不会漏"
  - "改了渠道账号别名但 Tax 账号没变"
tags: [amazon-period, tax, nas, channel-alias]
---

# 自己重跑账期 Tax

## Context

Tax 写入「附加费&Tax」的 `Tax{YYYYMM}` 是一条本地命令。它不访问赛狐，也不从钉钉下载附件。txt 必须已经在本地同步桶的人名文件夹里。

## Guidance（本学习沉淀的做法）

1. 在仓库根目录执行。`--bucket` 是 `LOCAL_NAS_PERIOD_ROOT` 下的文件夹名，`--exchange-month` 是「和财务部共享 / 汇率」的列名。

| 账期月 | `--bucket` | `--exchange-month` |
|--------|------------|--------------------|
| 8 月 | `账期20260804-20260903` | `202608` |
| 9 月 | `账期20260904-20261003` | `202609` |
| 10 月 | `账期20261004-20261103` | `202610` |

```powershell
cd d:\Work\赛狐\Cursor
uv run python amazon_period_tax/scripts/run_period_tax.py `
  --bucket 账期20260804-20260903 `
  --exchange-month 202608 `
  --phase1-only --write-gsheet --sort-gsheet-tabs
```

只看合计、不写表时用 `--dry-run`。写表用服务账号，不需要 Colab。

2. 脚本只读桶里已有的 `AMZ*.txt`（排除固定的三个人名夹）。缺文件不会补。赛狐结算组用来核对「应该有哪些期」；txt 正文来自钉钉附件。补文件用 `fetch_attachments.py` 或网页下载，不是这条命令。

3. 文件名不必先改成 `渠道账号-YYYY-MM-DD.txt`。脚本读 txt 内容，渠道账号从文件名前缀截取，再对照本地快照 `channel_account_sync/out/channel_account_gsheet.json`（「和运营部共享 / 渠道账号」的导出，含「渠道账号别名」）。对得上就写成表上的规范账号；对不上但以 `AMZ` 开头的仍会计入 Tax，账号名保持文件名写法。不以 `AMZ` 开头的 txt 会跳过。

4. 在 Google 表上新加的别名不会自动进入这次运行。快照是导出副本。表上改过别名后，要重新导出该 JSON，再跑 Tax。

## Why This Matters

近三个月的 txt 已经在桶里时，重算 Tax 不依赖 Agent。把「补附件」和「改文件名」当成 Tax 命令的前置，会让人不敢自己跑；反过来，桶里缺文件时只跑这条命令也补不齐。

## When to Apply

- 汇率列或 Tax 合计要重写。
- 有人问别名改了为什么 `Tax{YYYYMM}` 的账号没变。

## Examples

8 月桶 67 个 `AMZ*.txt`、47,705 行。规范文件名不是读入条件。正确汇率合并后 Tax 人民币合计 396,601.69。

## Related

- `docs/solutions/integration-issues/amazon-period-tax-fx-alias-multiplies.md`
- `docs/solutions/conventions/amazon-period-file-reconcile.md`
- `amazon_period_tax/AGENT_HANDOFF.md`
