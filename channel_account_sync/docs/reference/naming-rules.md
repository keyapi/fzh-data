---
okf: v0.1
type: Reference
title: Channel Account 命名规则
resource: channel_account_sync/names.py
timestamp: 2026-08-25
---
# Channel Account 命名规则

## EN name

`{channel_code}{account_code}{region}`。`allow_empty_account_code=1` 时没有 `account_code`。

| 例 | 拆分 |
|----|------|
| AMZFZHSXDE | AMZ + FZHSX + DE |
| AMZStruseryPL | AMZ + Strusery + PL |
| KFLAT | KFL + 空 + AT |
| ILLIOSPL | ILLIOS + 空 + PL |
| WFEU | WF + 空 + EU（Wayfair 允许 EU） |
| WFDANEEYUS | WF + DANEEY + US |
| WFDaneeyUS | WF + Daneey + US（另一个账号，不要合并） |

## Amazon 欧洲

禁止区域 `EUR`、`EU` 以及账号名以 `EUR` 结尾。按 Johna 拆九国：

`DE ES FR IT UK PL NL BE SE`

FZHSX 旧名 `AMZFZHSXEUR` **只**作为 `AMZFZHSXDE` 的别名，其它八国不要重复挂。2026-08-25 表上约第 72–80 行：

| 账号 | 别名 |
|------|------|
| AMZFZHSXDE | FZHSXDE, FZHSX欧洲, AMZFZHSXEUR |
| AMZFZHSXES/FR/IT/UK/PL/NL/BE/SE | FZHSX{国家} |

运营分组仍是事业四部；九国负责人时间轴从原 EUR 行原样带过来（当时：202608 陈立彬 / 202607 林俊彪 / 此前于彬）。

## Illiosenergy

Sales Channel：`channel_name=Illiosenergy`，`channel_code=ILLIOS`（完整英文当不了 code）。账号 `ILLIOSPL`，表上的 `Illiosenergy` 进别名。

## 跳过

表行 `渠道账号=null`（其它渠道 / 样品）不建 EN 记录。
