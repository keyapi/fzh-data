# erpnext/ — Agent Handoff

> ERPNext 生产工单数据排查模块。检测"一键完工"（虚拟员工 HR-EMP-00001）造成的工单数据异常。

## 快速操作

```bash
uv run python erpnext/scripts/setup.py                    # 凭证检查
uv run python erpnext/scripts/fetch.py --month 2026-06    # 拉取数据
uv run python erpnext/scripts/gen_report.py               # 生成报告
```

## 8 步排查法

| # | 步骤 | 检查内容 | 判断依据 |
|---|------|---------|---------|
| 1 | 产品分类 | `production_item` 前缀 | KS=成品fg, PK#/ND#=半成品 |
| 2 | 虚拟工序 | 工序是否含"缝制" | 有→BOM未更新 |
| 3 | 活动记录 | Version: owner=yangyisen92 | 有→一键完工触碰 |
| 4 | 开料量 | `open_material_qty` | 半成品=0异常 |
| 5 | JC员工 | `time_logs[].employee` | HR-EMP-00001=虚拟 |
| 6 | JC创建人 | JC `owner` | yangyisen92=虚拟 |
| 7 | 入库单 | SE `owner` | 杨义森=不可信 |
| 8 | 交叉验证 | 真实JC + SE + open_mat | 三者一致=可信 |

## 5 类工单

| 分类 | 特征 | 数据可信度 |
|------|------|-----------|
| 成品fg-正常 | KS, 0工序 | ✓ |
| 正常扫码 | 无杨义森JC | ✓ |
| 半成品-一键完工 | PK#/ND#, 全虚拟JC, open_mat=0 | ✗ |
| 混合-真实+虚拟 | 真实+虚拟JC, open_mat>0 | 以真实JC为准 |
| 虚拟工序残留 | 含"缝制" | BOM需更新 |

## 关键提醒

- **`fac` MCP 连接测试系统** (ensh.vilavi.cn)，排查必须用生产 API
- API 端点: `https://erpnext.vilavi.cn/api/resource/...`
- 认证: `Authorization: token <key>:<secret>`
- `owner` ≠ `employee` — employee 在 `time_logs` 子表里
- `time_logs` 只在单条 JC 查询时返回

## 详细文档

- 方法论: `docs/work-order-investigation-methodology.md`
- 脚本: `scripts/gen_report.py`
- OKF: `docs/index.md`
