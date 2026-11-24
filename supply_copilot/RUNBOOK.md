# 补货决策 Runbook（给运营/采购/IT 同事）

> 目标：不依赖数据组重跑，你自己就能：拉最新订单 → 重算需求/预测 → 看当天补货候选。
> 只读，不下单；最终由采购/运营复核。

## 0. 一次性准备（约 10 分钟）

```bash
git clone https://github.com/keyapi/fzh-data.git
cd fzh-data && uv sync

# 用自己的 EN 内部账号（System User）API Key；不要用别人的
# Windows PowerShell:
$env:ERP_API_KEY="..."
$env:ERP_API_SECRET="..."
$env:FZH_DATA_ROOT="D:\fzh-pack"; mkdir D:\fzh-pack
# macOS/Linux:
# export ERP_API_KEY=... ERP_API_SECRET=... FZH_DATA_ROOT=~/fzh-pack; mkdir -p ~/fzh-pack

uv run python -m supply_copilot pull          # 私有规则/决策包
uv run python -m supply_copilot pull-orders   # 最新订单（到 11-22）
uv run python -m supply_copilot pull-history  # 一次性：UOM/历史（rebuild 需要）
uv run python -m supply_copilot doctor        # 期望 status=ok
```

## 1. 每天/每周的流程

```bash
# ① 更新实时供给（库存、开放 SO、开放 PO）→ <FZH_DATA_ROOT>/live/
uv run python -m supply_copilot supply --branch USNJ

# ② 用最新订单重算需求/预测（本地，不写 EN）
uv run python -m supply_copilot rebuild \
  --orders <FZH_DATA_ROOT>/orders/<版本>/orders_unified.parquet \
  --out <FZH_DATA_ROOT>/rebuild/<日期>

# ③ 出当天候选
uv run python -m supply_copilot decide --branch USNJ \
  --forecast-root <FZH_DATA_ROOT>/rebuild/<日期>/forecast
```

`rebuild` 首次 AutoETS 约 4 分钟（2,588 个 SKU）；加 `--no-statsforecast` 约 20 秒（精度较低，只用于试跑）。

## 2. 结果怎么看

- 报告第一段：**可执行性：是/否** + 原因。**「否」时只能当候选，不能直接下单。**
- 每行：
  - `结论`：补 / 不补 / 待核
  - `新补`：建议新下单数量；`最坏`：在途/无 ETA 的 PO 迟到时要补的上限
  - `为什么`：需求 − 已知供给的算式
  - `需求`：中位（p50）/ 保守（p90，约 90% 情形）；D6 历史包是 95% 档，只作对照
  - `供给`：期初 / 在途 / PO / SO / CG
  - `需要日 / 下单日`：按 D6 计划交期倒排；过期会标 `past_due`
- 时点：库存快照（如 05:17）、预测 run、文件 sha256 都在报告里。

## 3. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `缺少数据目录` | 没设 `FZH_DATA_ROOT` | 设环境变量，先建目录 |
| `下载被拒（403）` | 匿名/门户账号/凭证失效 | 用自己 EN 内部账号的 Key；不要借别人的 |
| `找不到订单 parquet` | 没 `pull-orders` | 先拉；或 `--orders` 指定 |
| `缺少 item_uom_cache` | 没 `pull-history` | 一次性拉，或 `--uom-cache` 指定 |
| `预测未覆盖` 行 | 该 SKU 无净额资格/无近月销量 | 退回 D6 历史 95% 档并计数；不要当已刷新 |
| 可执行性=否 | 见原因列表 | 需求派生/CG/PO/日期未满足，不能下单 |
| 库存快照 >12h | EN 上游 run 未更新 | 报告会警告；等新 run 或复核 |

## 4. 不要做的事

- 不要把 API Key 写进本仓库、聊天记录或报告。
- 不要把 `可执行性=否` 的候选直接下单。
- 不要把缺失/未知当成 0。
- 不要用 `--like` 模糊匹配做正式决策（可能命中相似 SKU）。

## 5. 当前边界（会随版本减少）

- 需求：订单到 2026-11-22；预测用「保守档（约 90% 情形）」，未做覆盖率回测。
- 单位：EN 不维护 UOM，统一按“个”；套件/多件按订单件数换算。
- 按周数量：正在加，下一版提供（当前是 60/90/120/180 天总量）。
- 供给：PO 目前多为物料仓，未接通途采购单；CG 仅用实时库存封顶 D6 上限。
- 日期：按 D6 计划交期倒排，不是实际路线交期。
- 不写 EN、不下单。

有问题先看报告里的原因列表，再找系统负责人。
