# sellfox_settlement — 赛狐自动拉取 Amazon 结算（试点）

用赛狐 OpenAPI「财务/结算中心V2」+ 紫鸟/赛狐插件列式报表取回 Amazon 结算，与运营钉钉提交的收款确认单比对，评估能否替代人工提交。

> 只做 **Amazon**；账期月归属 = 结算周期结束日(`groupEndStr`)所在自然月。目前为试点原型。

## 文档入口
- **交接** → [AGENT_HANDOFF.md](AGENT_HANDOFF.md)（背景/数据源/关键结论/文件位置/运行/交接清单）
- **深度调研** → [docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md](docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md)
- **端点/字段** → [docs/reference/settlement-v2-endpoints.md](docs/reference/settlement-v2-endpoints.md)；**科目映射** → [docs/reference/column-mapping.md](docs/reference/column-mapping.md)
- **技能**（Repo `.agents/skills/`，跨会话发现）：`sellfox-amazon-settlement`
- 全模块文档索引 → [docs/index.md](docs/index.md)

## 前置
- 赛狐 API Key：在 `D:\Work\赛狐\Cursor\.env` 写 `SELLFOX_API_KEY=sk-xxx`（代理）或 `SELLFOX_APP_ID/APP_SECRET`（VPS 直连）。
  没有 Key 时先打开 https://api.vilavi.cn/sellfox/admin 钉钉登录取 `sk-xxx`。
- 依赖已由仓库 `pyproject.toml` 提供（`pandas`, `openpyxl`）；用 `uv run python` 运行。

## 步骤
```bash
# 1) 建 渠道账号 映射（打印店铺名/站点/市场）
uv run python sellfox_settlement/reconcile_amazon.py shops

# 2) 拉取某账期月 Amazon 汇总+明细（startTime/endTime 覆盖该月）
#    加 --currency 可取原币（默认 CNY 是赛狐折算汇率）；多币种需按币种分别拉
uv run python sellfox_settlement/reconcile_amazon.py fetch \
    --start 2026-06-01 --end 2026-07-10 --out data/saihu_amazon_202606 --currency USD

# 3) 打印未识别科目候选 → 人工确认后用 SUBJ 映射校准（或改表驱动）
uv run python sellfox_settlement/reconcile_amazon.py candidates \
    --detail data/saihu_amazon_202606/detail.csv

# 4) 与钉钉定稿文件比对，输出差异 xlsx
uv run python sellfox_settlement/reconcile_amazon.py reconcile \
    --settlement data/saihu_amazon_202606 \
    --dingtalk "D:/Work/王忠于/成本核算/Amazon&新平台成本 20260604-20260703 销售收款确认单-20260706111631_合并汇率&账号_2026-07-06_11-52-51.xlsx" \
    --month 202606 --out out/amazon_compare_202606.xlsx
```

## 科目映射（SUBJ，需实跑校准）
| 钉钉科目 | 赛狐匹配线索（初步） |
|---|---|
| 销售额 | `amountType`/`amountDescription` = Principal（Order） |
| 佣金 | amountDescription 含 commission；amountType = Commission / Marketplacefacilitatorfee |
| 广告费 | amountDescription 含 advertising / sponsored |
| 退款 | transactionType / amountType = Refund（负） |
| 税 | amountType = Tax；amountDescription 含 withholding / tax |
| 平台月租 | 含 subscription / 月租 |
| 其他/未识别 | 其余（candidates 里人工补） |

> 注意符号口径：赛狐 `amount` 有符号，正=收入、负=费用/退款；钉钉各列多为绝对值。映射需对齐后取绝对值/按方向取值，试点阶段先直接比对并记录差异。

## 端点
- 汇总：`POST /api/financial/v2/settlementSummary/groupPage.json`
- 明细：`POST /api/financial/v2/settlementSummary/detailPage.json`
- 参考 API 文档：`../SELLFOX_API/docs/api-reference/财务/结算中心V2/` 及 `llms.txt`
