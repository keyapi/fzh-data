---
okf: v0.1
type: Research
title: Amazon 非 V2 账单账号、稳定键与法人证据技术验证
description: 2026 年 8 月 65 对账单与运营渠道账号、生产 EN、赛狐店铺的只读交叉检查
timestamp: 2026-10-10
resource: sellfox_settlement/account_validation.py
tags: [amazon, tax, account, legal-entity, read-only, technical-validation]
---

# 账号与法人证据技术验证

65 对 CSV/PDF 均保留，64 份可产生运营渠道账号唯一候选，62 份对应生产 EN；60 份通过运营表「赛狐店铺」精确匹配赛狐 shop，另 1 份通过原始 PDF 法定名称文字及稳定 Seller ID/marketplace 键补充定位。技术匹配不构成申报主体确认。

## 验证范围和证据

输入仅为 2026 年 8 月原始账单。读取权威运营表 gid 763421711、生产 EN 的 Amazon Channel Account 父文档及赛狐公开店铺查询接口。所有请求为查询，没有写表、创建主数据或修改账单。运营表为当前主数据；读取当时的现行状态不能推导 8 月的历史开卖、停卖或申报要求。

账号规则复用 [渠道账号交接](../../../channel_account_sync/AGENT_HANDOFF.md) 和 [共享表规则](../reference/gsheet-access-and-channel-account.md)。文件名族映射为已有账号族规则，只用于构造候选，再查询完整账户键；它不是品牌到法人的映射。站点来自文件名国家标记和 CSV marketplace 域名。EUR 与 `kr` 均不得单独推断国家。通用文件名以 PDF display name 的精确 EN account_code 和 CSV marketplace 证据恢复候选。

## 实测计数

| 检查 | 结果 | 含义 |
|---|---:|---|
| 运营表 Amazon 行 | 145 | 全部保留，不按现行状态删行 |
| 生产 EN Amazon 文档 | 143 | 父文档读取错误 0 |
| 运营标准账号重复 | 0 | 保持大小写语义 |
| 运营同别名跨账号冲突 / 行内重复 | 0 / 0 | 未调用去重掩盖冲突 |
| 运营别名在 EN 缺失 | 0 | 针对存在于 EN 的账号 |
| 表中有、EN 无 | 2 | 私有异常表列出完整账号 |
| CSV / 唯一配对 PDF | 65 / 65 | 无丢弃 |
| 交易行 | 11,580 | 全部原始账单读取完成 |
| PDF display / legal 字段提取 | 65 / 65 | 多语言字段兼容，包括截断标签 |
| 有非空 CSV marketplace 证据 | 49 | 其余 16 份不自动判失败：包含空账单和仅费用行 |
| 文件名国家与 CSV marketplace 冲突 | 0 | 国家候选仍须保留证据来源 |
| 账单匹配运营账号 / EN | 64 / 62 | 缺口明细保留 |
| 运营表精确匹配赛狐 shop | 60 | 无多候选歧义 |
| 补充稳定键匹配赛狐 shop | 1 | 标准渠道账号仍待补登 |
| 当前店铺 API 行 | 90 | 分页返回总数 90，下载 90 |
| Seller ID + marketplace ID 重复 | 0 | 店铺稳定键组合可用于后续桥接 |
| EN 账户 currency 非 CNY | 0 | 全 143 个为 CNY，不可当账单原币 |
| 原始 PDF legal 文字种类 | 15 | 不是 15 个已确认申报主体 |
| 已确认申报法人 | 0 | 等财务核定证件、主体和生效期 |

65 份输入的去向为 60 份精确 shop、1 份补充 shop、4 份未匹配 shop，总数仍为 65。标准渠道账号单独为 64 匹配、1 未匹配，不能拿 shop 补充候选冒充已登记账号。

## 缺口与边界

1. 运营表新加的 2 个加拿大账号尚不存在于生产 EN。另 1 份加拿大账单在运营表没有标准账号，不能自行造账号写系统。
2. 4 份账单找不到现有赛狐 shop。保留原文件、PDF 字段、国家证据和已知账号候选，不能以别国店铺代替。
3. 运营表及现有 EN Channel Account 没有 Seller ID/marketplace ID 或法人的稳定主键。赛狐店铺接口具备 Seller ID/marketplace ID，但没有登记证件、纳税识别号和法人变更历史。
4. 赛狐 `region` 实测值为大陆区域 `eu`/`na`，不能当国家站点；当前 `status` 值全部为字符串 `0`，本验证不解释其历史业务状态。
5. 同一渠道账号族出现不同 PDF legal 文字，有个人名和公司名并存；另有标点和拼写变体。原始文字逐文件保留，不用品牌或近似文字合并法人。需财务提供正式主体映射及有效期。
6. 当前运营表 81 个 Amazon 账号没有本批 8 月文件，当前 90 个 shops 中 29 个没有本批对应文件。私有报告列出每一项，标记 `current_inventory_only_historical_expected_scope_unconfirmed`。这些不是已经证实的历史漏报数量；历史应取清单仍需负责人核定。

补充 shop 的唯一匹配要求同时满足：待匹配 PDF legal 原文与已精确匹配文件一致；该原文对应唯一 Seller ID；已匹配文件证明该国家对应唯一 marketplace ID；Seller ID + marketplace ID 在完整店铺列表唯一。即使满足，仍标记法人与标准账号待确认。

## 可复跑方法

在仓库运行时执行，`--data-root` 指向含 gitignored 凭证的主仓库，`--out` 指向仓库外私有目录。省略 `--refresh` 使用已有快照，带上它只读刷新 Google 表、EN 和赛狐店铺。

```powershell
uv --project <主仓库> run python sellfox_settlement/account_validation.py --data-root <主仓库> --raw <8月账单目录> --out <仓库外私有输出>
uv --project <主仓库> run pytest tests/sellfox_settlement/test_account_validation.py -q
```

生成 `account_validation.json`（65 份逐文件证据及异常）、`account_shop_scope.json`（60 份精确 shop）、`additional_shop_scope.json`（1 份补充 shop）。只读快照为 `account_sheet.json`、`account_en.json`、`account_shops.json`。私有明细不进 Git；输出路径在 Git 仓库内会报错。

验证用例覆盖别名冲突、重复别名、大小写账号区分、币种不能推断国家、国家冲突、补充匹配唯一性以及私有输出防入库。先观察测试缺实现而失败，再实现；本次 6 个测试通过。

技术读取、候选匹配、差异计数和稳定键可用性已验证。要进入最终申报仍需正式历史范围、标准账号补登、法人证件映射和财务生效期；本轮没有替财务选择任何口径。

## 银行实际到账证据补充验证

只读检查用户提供的共享账期资料中 `20260704–20260803`、`20260804–20260903`、`20260904–20261003` 三个目录的 6 份 PDF，以及根层 3 份合并 Amazon 账期工作簿。

| 材料 | 实测结果 | 对到账验证的用途 |
|---|---|---|
| 银行 PDF | 2 份，实际为同一笔交易的重复副本 | 保留两份来源并显式登记重复；只有 1 笔唯一银行交易 |
| 银行交易时间 | 操作日、起息日和单据日均为 2026-07-22；打印于 8 月 | 不是 8 月实际流水，不能依据文件名或目录日期改归属 |
| 银行币种及对方类型 | PLN，物流服务商 | 不是 Amazon 入账证据 |
| 平台付款截图 PDF | 3 份，PDF 无文字层，渲染后人工检查 | 显示平台结算与付款处理商信息；不能证明银行已经收到 |
| 平台付款通知 PDF | 1 份 | 付款通知不能替代银行入账流水 |
| 合并 Amazon 工作簿 | 3 份；原始数据分别 29,803、32,148、39,126 行 | 均是运营提交 `.txt` 的 Amazon settlement flatfile 合并 |
| 银行流水主键列 | 上述 3 份工作簿均没有 | `deposit-date` 为平台报表日期，不能冒充银行实际操作日 |
| 8 月 Amazon 银行实际到账可验证输入 | 0 | 银行实际到账仍明确缺输入 |

银行 PDF 的字段结构具备收支方向、操作日、起息日、单据日、金额与币种、交易对方、转账附言、银行交易标识，适合以后建立独立 `bank_actual` 证据表。它不是完整期间流水；当前唯一交易的银行标识和附言与已有 Settlement V2 `traceId` 没有精确匹配，且交易对方和月份均不在目标范围。

未来把平台付款与银行入账连接时，应保留银行附言原文及银行流水主键，再以实际包含的平台 reference/trace ID 建候选，并核对币种、到账时间、收款主体和付款处理商费用/换汇桥。不能假定「银行交易标识」与 Amazon `traceId` 天然相同，也不能用账期合并表中的 `settlement-id` 或 `deposit-date` 证明银行到账。

私有输出 `bank_evidence_validation.json` 保留逐文件摘要、原文、银行字段、明确的重复分组、工作簿列和数据来源。原始资料未修改。银行标识、账号、个人姓名和金额明细没有写入 Git。对话里曾提到 `bank_evidence_probe.py` 与 `bank_evidence_finish.py`，本分支文件清单里没有这两个脚本；若它们在私有验证目录，留在仓库外。
