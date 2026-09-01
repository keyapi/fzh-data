---
okf: v0.1
type: Research
title: 2026-08-25 EN Channel Account 生产写入
timestamp: 2026-08-25
---
# 2026-08-25 生产写入

环境：`https://erpnext.vilavi.cn`。Google 表已先把 `AMZFZHSXEUR` 拆成九国行。

## 计数

| 项 | 结果 |
|----|------|
| Canary `AMZFZHSXUS` + 林俊彪 @ 2026-07-01 | PUT 200 |
| Kaufland `supported_regions` | `DE,PL,CZ,SK,AT,IT,FR` |
| Sales Channel Illiosenergy | 新建，code `ILLIOS` |
| 新建 Channel Account | 18 / 18 |
| 补别名 | 10 / 10 |
| 已有账号补负责人 | 122 / 122，失败 0 |

## 新建账号

`AMZStruseryPL`, `AMZFZHSXDE`, `AMZFZHSXES`, `AMZFZHSXFR`, `AMZFZHSXIT`, `AMZFZHSXUK`, `AMZFZHSXPL`, `AMZFZHSXNL`, `AMZFZHSXBE`, `AMZFZHSXSE`, `WFDANEEYUS`, `WFRosoonUK`, `WFDaneeyUS`, `KFLAT`, `KFLIT`, `KFLFR`, `TTCozyDozyUS`, `ILLIOSPL`

## 补别名

| 账号 | 追加 |
|------|------|
| AMZBAINAMX | 墨西哥站-BAINAMX |
| AMZYTHDUS | Novelledo-US, AMZNovelledoUS |
| AMZFZHSXUS | FZHSXUS |
| WMRongnuoUS | WM-RongnuoUS |
| RueduCommerceFR | MRueduCFR |
| ePriceIT | MePriceIT |
| WortenPT | MWortenPT |
| KFLDE | KauflandDE |
| TTTOODDLYUS | TTTooddlyUS |
| BASEPPPL | BasePPPL |

## 未做

- `Operation Staff Settings` 补中文名与分公司
- 没有把 Amazon 渠道的 `supported_regions` 加上 EUR
