---
name: work-order-audit
description: ERPNext 生产工单数据排查 — 检测一键完工虚拟 Job Card，交叉验证真实产量
---

# ERPNext 生产工单数据排查

检测"一键完工"（虚拟员工 HR-EMP-00001）造成的工单数据异常，
区分成品fg/半成品，交叉验证真实生产数据。

## 触发条件

按需触发：当用户提到以下任一短语时加载本 skill：

- 工单排查、工单分析、工单审计、工单异常
- 一键完工、虚拟工单、虚拟 job card
- 生产数据排查、生产工单分析
- work order audit、work order investigation

## 8 步排查法

详细方法论见 `erpnext/docs/work-order-investigation-methodology.md`。
英文版见 `docs/solutions/best-practices/erpnext-work-order-investigation-methodology.md`。

### 步骤速查

1. **产品类型判断** — KS开头=成品fg(0工序), PK#/ND#=半成品(多工序)
2. **遗留虚拟工序** — 检查工序是否含"缝制"(一键完工时代残留)
3. **Version活动记录** — 查 `yangyisen92@dingtalk.com` 的修改记录
4. **open_material_qty** — 半成品=0异常，成品fg=0正常
5. **JC time_logs.employee** — `HR-EMP-00001`=虚拟，其他=真实
6. **JC owner** — `yangyisen92`=虚拟，真实钉钉用户=扫码
7. **Stock Entry 入库** — 查 Manufacture 类型，owner=杨义森不可信
8. **交叉验证分类** — 综合真实JC/SE/open_mat 判定可信产量

### 分类

| 分类 | 特征 | 数据可信度 |
|------|------|-----------|
| 成品fg-正常 | KS, 0工序, open_mat=0 | 可信 |
| 正常扫码 | 无杨义森记录 | 可信 |
| 半成品-一键完工 | PK#/ND#, 全HR-EMP-00001, open_mat=0 | 不可信 |
| 混合-真实+虚拟 | 真实JC+虚拟JC, open_mat>0 | 以真实JC为准 |
| 虚拟工序残留 | 工序含"缝制" | BOM需更新 |

## 工具

### gen_report.py

自动生成 Excel 排查报告：

```bash
# 前置：拉取 ERPNext API 数据到 /tmp/
# 1. 工单数据 → /tmp/zero_mat_full2.json
# 2. Job Card 数据 → /tmp/all_job_cards3.json
# 3. 运行脚本
uv run python erpnext/scripts/gen_report.py
# 输出: erpnext/data/2026-06_工单排查报告.xlsx
```

### 快速 API 查询

```bash
# 查询某时间段所有工单（不限状态）
curl -s -H "Authorization: token <key:secret>" \
  "https://erpnext.vilavi.cn/api/resource/Work%20Order?\
filters=[["actual_end_date",">=","2026-06-01"],["actual_end_date","<=","2026-06-30"]]\
&fields=[...]&limit=500"

# 查询单个工单完整数据（含工序子表）
curl -s -H "Authorization: token <key:secret>" \
  "https://erpnext.vilavi.cn/api/resource/Work%20Order/WO-26-XXXXX"

# 查询工单关联的 Job Card
curl -s -H "Authorization: token <key:secret>" \
  "https://erpnext.vilavi.cn/api/resource/Job%20Card?\
filters=[["work_order","=","WO-26-XXXXX"]]&fields=[...]&limit=500"

# 单条 JC 查 time_logs.employee（确认虚拟/真实）
curl -s -H "Authorization: token <key:secret>" \
  "https://erpnext.vilavi.cn/api/resource/Job%20Card/PO-JOBXXXXX"
```

## 重要提醒

- **MCP `fac` 工具连接的是测试系统** (`ensh.vilavi.cn`)，不是生产！
- 生产系统必须用 REST API (`erpnext.vilavi.cn`)
- API key/secret 在 `EN_API/.env` 或环境变量中
- `time_logs.employee` 只在单条 JC 查询时返回，列表查询不包含子表
- `owner` ≠ `employee`！owner 是创建记录的人，employee 在 time_logs 子表
- gen_report.py 依赖 `/tmp/` 下的中间 JSON 文件，先拉数据再运行
