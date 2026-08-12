# tongtool_order_cost — 通途订单特殊规则本地审计（1.7.0）

把 Colab notebook **1.7.0**（订单改销售额及成本）落成本地 pandas 引擎，输出可穿透的多 Sheet 审计 Excel，用于和同事核对「特殊规则到底改了什么」。

## 做什么 / 不做什么

- **做**：按规则时间窗、去重、系数/参考值写入、FBA 跳过尾程、衍生列重算；导出 before/after/Δ。
- **不做**：完整复刻 1.4–1.5；不改 Google Sheet；不裁决「参考成本是否合理」。

## 快速开始

```bash
cd tongtool_order_cost

uv run python scripts/run_audit_170.py \
  --orders "D:/Work/王忠于/成本核算/特殊规则AMZBAINAUS_2026年6月FBA订单和非FBA订单_order_cost_2026-08-06_15-00-53.xlsx" \
  --rules "D:/Work/王忠于/成本核算/Jeck特殊规则-订单改销售额成本 20260812.xlsx" \
  --month 202606 \
  --account AMZBAINAUS \
  --fx-usd 6.8167 \
  --out out/AMZBAINAUS_202606_audit.xlsx
```

汇率优先级：`--fx-file` > `--fx-usd` > 订单表 `汇率` 众数（会 WARN）。

## 审计簿 Sheet

| Sheet | 用途 |
|-------|------|
| `00_总览` | 账号级科目 before/after/Δ |
| `01_科目瀑布` | 哪科升、哪科降 |
| `02_按规则汇总` | 每条规则命中行数与科目合计 |
| `03_订单明细` | 订单行穿透 |
| `04_变更事件` | 列级变更审计轨 |
| `05_未命中规则` | 生效但匹配 0 行 |
| `06_架构说明` | ref 模式与科目架构差异说明 |

## 测试

```bash
cd tongtool_order_cost
uv run pytest tests/test_engine_170_ref.py -q
```

## 数据文件

`数据源/` 与 `out/` 默认 gitignore，大 xlsx **不要**提交进仓库。用 CLI 绝对路径即可。

## Agent 入口

见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md) 与 [docs/](docs/)。
