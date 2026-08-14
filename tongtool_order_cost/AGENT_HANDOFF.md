# tongtool_order_cost — Agent 交接

> **CLI**: `scripts/run_audit_170.py`  
> **人读**: [README.md](README.md)

## 业务背景

运营对「特殊规则改成本」有异议时，需要证明 Colab **1.7.0** 逻辑：匹配哪些订单、各科目 before→after→Δ。六月 AMZBAINAUS 多为 **ref（参考值）** 模式。

## 管道

```
订单xlsx(未改成本) + 规则xlsx + FX
  → 时间窗过滤 → 6列去重 → attach FX → ￥参考值
  → backup_* → coeff/ref 写入（FBA 正数尾程跳过；负数账期差异写入）
  → 重算产品成本/订单总成本/利润
  → change_events → 多 Sheet 审计 xlsx
```

## 关键模块

| 文件 | 作用 |
|------|------|
| `tongtool_order_cost/engine_170.py` | 与 notebook Cell 22 对齐的应用引擎 |
| `tongtool_order_cost/audit.py` | 事件 → 审计簿 |
| `tongtool_order_cost/io_loaders.py` | 订单/规则/汇率加载 |
| `tongtool_order_cost/pp_cotton.py` | 美中 DANEEY 订单 × BOM Cost List → PP 棉 kg 估算 |
| `scripts/run_audit_170.py` | 1.7.0 特殊规则审计 CLI |
| `scripts/estimate_pp_cotton.py` | PP 棉用量估算 CLI |

## 去重键（6 列）

`运营人员` + `发货区域` + `通途SKU` + `渠道账号不含国家` + `渠道账号` + `发货仓按销售汇总分类`（`keep=last|first`）

## 验证要点

1. `ref_usd × fx × 发货数量` = 数量列 after  
2. FBA 尾程：参考值 **>0 或 =0** 不改 `运费`；参考值 **<0** 按账期差异写入 `运费`
3. `01_科目瀑布` 各科 Δ 与总览一致  

## 禁止

- 不要把订单/规则大 xlsx 提交进 git  
- 不要直接 push main；走 `feature/...` + PR  
