---
name: erpnext-wo-audit
description: ERPNext 生产工单数据排查 — 检测一键完工虚拟 Job Card (HR-EMP-00001)，交叉验证真实产量，生成分类 Excel 报告。覆盖 erpnext/ 模块的 setup→fetch→report 流水线。
---

# ERPNext 生产工单数据排查

当用户提到 ERPNext 工单分析、一键完工检测、生产数据排查时加载此 skill。

## 流水线（3 步）

```
python erpnext/scripts/setup.py                  # ① 凭证检查
python erpnext/scripts/fetch.py --month 2026-06  # ② 拉取数据
python erpnext/scripts/gen_report.py             # ③ 生成 Excel
```

## 快速开始

同事 clone 项目后首次使用：

```bash
# 1. 初始化凭证（自动检查，不存在则引导创建）
uv run python erpnext/scripts/setup.py

# 2. 拉取目标月份数据
uv run python erpnext/scripts/fetch.py --month 2026-06

# 3. 生成排查报告
uv run python erpnext/scripts/gen_report.py
# 输出: erpnext/data/2026-06_工单排查报告.xlsx
```

## 8 步排查法速查

| 步骤 | 检查项 | 判断 |
|------|--------|------|
| 1 | `production_item` 前缀 | KS=成品fg, PK#/ND#=半成品 |
| 2 | 工序含"缝制" | 遗留虚拟工序, BOM未更新 |
| 3 | Version 活动 | owner=yangyisen92 → 疑似一键完工 |
| 4 | `open_material_qty` | 半成品=0异常, 成品=0正常 |
| 5 | JC `time_logs.employee` | HR-EMP-00001=虚拟, 其他=真实 |
| 6 | JC `owner` | yangyisen92=虚拟, 钉钉用户=扫码 |
| 7 | Stock Entry owner | 杨义森=不可信, 其他人=真实入库 |
| 8 | 交叉验证 | 真实JC ∪ SE ∪ open_mat → 可信产量 |

## 分类速查

| 分类 | 特征 | 处理 |
|------|------|------|
| 成品fg-正常 | KS, 0工序, open_mat=0 | 无需排查 |
| 正常扫码 | 无杨义森记录 | 工序瓶颈分析 |
| 半成品-一键完工 | PK#/ND#, 全HR-EMP-00001, open_mat=0 | 物理盘点 |
| 混合-真实+虚拟 | 真实JC+虚拟JC, open_mat>0 | 以真实JC为准 |
| 虚拟工序残留 | 含"缝制" | 更新BOM |

## 重要提醒

- `fac` MCP 连接**测试系统** (ensh.vilavi.cn)，生产用 REST API (erpnext.vilavi.cn)
- `owner` ≠ `employee`! employee 在 `time_logs` 子表
- `time_logs` 只在单条 JC 查询时返回，列表查询不包含子表
- API 凭证在 `EN_API/.env`，key/secret 不提交 git
