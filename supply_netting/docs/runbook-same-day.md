---
okf: v0.1
type: Reference
title: 同日快照一条命令 runbook（快照→需求→净额→决策包→动作层）
description: 10-29 起每次新库存快照后的标准执行、校验、输出命名与失败回滚
tags: [runbook, pipeline, snapshot, netting, decision-pack]
date: 2026-10-27
status: implemented
---

# 同日快照 runbook

入口：`python -m supply_netting.scripts.run_same_day`（源码
[`../scripts/run_same_day.py`](../scripts/run_same_day.py)）。

一次调用完成：**快照校验 → 冻结副本 → 需求净额 → 供应净额 → 决策包 → 动作层**。
任何一步失败，正式目录与 `latest.json` 都不动（暂存目录改名 `.failed-*` 留证）。

## 1. 前置条件

| 项 | 要求 |
|---|---|
| 运行环境 | `uv run python`（项目 `.venv`）；Python ≥ 3.10 |
| 库存快照 | `en_stock.parquet`，至少含 `snapshot_date / snapshot_at / warehouse_name / sku / available / intransit` |
| 需求净额 | `demand_netting.parquet`（四列唯一、`netting_allowed` 全 true）；或 `--demand-mode rebuild` |
| 预测 | `forecast/CURRENT` 指向的 run；建议同时给 `--forecast-run-id` 与 `--forecast-manifest-sha256` |
| SKU 映射 | `sku_map.tsv`，默认校验冻结哈希 `7da3dfd6…d42e` |
| 动作层输入（可选） | EN SO JSONL、W1 缓存与 manifest；缺任一则动作步跳过并记录原因 |

## 2. 一条命令

```bash
uv run python -m supply_netting.scripts.run_same_day \
  --snapshot-date 2026-10-26 \
  --stock        "D:/Work/fzh-order-store/en_stock.parquet" \
  --demand       "D:/Work/fzh-order-store/en-demand-v1/canonical-r2/demand_netting.parquet" \
  --demand-blocked "D:/Work/fzh-order-store/en-demand-v1/canonical-r2/demand_blocked.parquet" \
  --forecast-run-id forecast-20261027-r2 \
  --label r1 \
  --out-root "D:/Work/fzh-order-store/en-demand-v1/supply-netting" \
  --test-count 193
```

10-29 当天：把 `--snapshot-date` 换成当天、`--label` 从 `r1` 起递增，
`--forecast-run-id` 换成当天的新预测版本（没有新预测则沿用旧版并在报告里注明）。

### 常用变体

```bash
# 只看校验与计划，不执行
... --dry-run

# 重建需求净额（离线，不拉 EN UOM；需要在线刷新 UOM 时另跑 canonical.py）
... --demand-mode rebuild --store D:/Work/fzh-order-store/en-demand-v1 \
    --gs-path D:/Work/fzh-order-store/gs_orders.parquet --demand-start 2022-12-01

# 只到决策包，不做动作层
... --skip-actions

# 动作层失败但保留已成功产物（会把 actions 步记为 failed）
... --allow-optional-failure
```

参数速查：`--as-of`（缺省由 `snapshot_at` 推）、`--tz +08:00`、`--protect-days 7`、
`--weeks 4`、`--force`（替换已存在的冻结快照/同号输出）。

## 3. 快照校验（执行前，失败直接退出）

- 文件存在、可读、非空；
- 必需列齐全；
- `snapshot_date` 含请求日期；`available` 全为数值且非负；`snapshot_at` 无空值；
- 仓库数 ≥ 3（实测 10 仓）；
- 计算 SHA-256 并冻结到 `_inputs/en_stock-<date>-backup.parquet`；
  已存在且哈希相同 → 复用；**哈希不同 → 拒绝**（除非 `--force`，旧副本归档为 `.superseded-<ts>`）。

`as_of` 缺省 = `snapshot_at` 按 `--tz` 解释（截到秒），与冻结快照的时刻一致；
`snapshot_at` 无时区是已知事实，manifest 会记录解释方式。

## 4. 输出与命名

所有产物在 `--out-root` 下，当天同版本号成套：

| 产物 | 名称 | 内容 |
|---|---|---|
| 冻结快照 | `_inputs/en_stock-<date>-backup.parquet` | 输入哈希与源行数 |
| 供应净额 | `run-<date>-<rN>/` | `supply_netting.parquet` 等 7 张表 + `supply_netting_manifest.json` |
| 决策包 | `decision-pack-<date>-<rN>/` | Parquet/严格 JSON/xlsx/排除明细 + `decision_pack_manifest.json` |
| 动作层输入 | `pack-<date>-<rN>/` | `conditional_decision_pack.csv`（供 join） |
| 动作层 | `actions-<date>-<rN>/` | `decision_pack_2026-10-29_actions.{parquet,csv,xlsx}` + manifest |
| 流水线记录 | `pipeline-manifest-<date>-<rN>.json` | 每步状态/耗时/Python 内存峰值/错误、输入与输出哈希 |
| 指针 | `latest.json` | **只在整条成功时更新**；失败保持上一版 |

决策包 manifest 记录代码 commit、`git_dirty`、输入输出哈希、`partial` 与缺口清单；
流水线 manifest 另记每步退出码与失败点。

## 5. 失败与回滚

失败时脚本会：

1. 打印错误与失败步骤；
2. 把暂存目录 `.pipeline-<date>-<label>-<ts>` 改名为 `.failed-<ts>`（保留现场）；
3. **不创建**任何正式目录，**不更新** `latest.json`。

重试：修好原因后换 `--label`（如 `r2`）或加 `--force`；上一版正式目录保持可读。

手工回滚（若确认某版有问题）：

```bash
# 1) 看上一版指针
cat D:/Work/fzh-order-store/en-demand-v1/supply-netting/latest.json
# 2) 把有问题的正式目录改名归档（不要删除）
mv decision-pack-<date>-<rN> decision-pack-<date>-<rN>.rejected-<ts>
# 3) 重新指向上一版（手工编辑 latest.json，或直接以旧版目录为准）
```

`.failed-*` / `.rejected-*` 目录仅作证据，确认后可删除。

## 6. 演练记录（2026-10-27，10-26 快照）

- 命令：`--snapshot-date 2026-10-26 --label r1 --test-count 193`（`demand-mode reuse`）。
- 结果：**成功**，总耗时 **129.9 秒**（wall 2m11s）。
- 产出：`run-2026-10-26-r1`、`decision-pack-2026-10-26-r1`、`pack-2026-10-26-r1`、
  `actions-2026-10-26-r1`；决策包 4,014 行，去向 91 / 452 / 2 / 3,469；
  保护期缺口 34.867936（71 键）、视界末 449.966544；current 495 / higher 777 / +282；
  动作层：补单 53、核实到仓 ETA 19、催发运 12、催生产 5、核实 ETA 2、不需补 452、
  待核留空 3,469、不可算 2。
- 分步耗时 / Python 内存峰值（tracemalloc，**不是 RSS**）：

| 步 | 秒 | 峰值 MB | 备注 |
|---|---:|---:|---|
| freeze_snapshot | 0.0 | 0.1 | 备份已存在且哈希相同 → 复用 |
| demand_netting | 0.1 | 24.1 | reuse 模式，仅契约校验 |
| supply_netting | 58.4 | 387.9 | 最大耗时与内存；9,827 条供应事实 |
| decision_pack | 16.2 | 74.5 | 4,014 行 + 严格 JSON/xlsx |
| actions | 55.1 | 79.1 | pack.py（SO/W1）+ decision_join |

- 失败演练：`--label rfail --forecast-run-id DOES-NOT-EXIST` →
  预测版本校验失败，未产生 `run-/decision-pack-2026-10-26-rfail`，
  暂存归档 `.failed-2026-10-26-rfail-221443`，`latest.json` 仍指向 r1。✅
- 注意：演练时工作树含有未提交的新脚本，故 `decision-pack-2026-10-26-r1` manifest 记
  `git_dirty=true`；**正式日请在已提交的干净树运行**，否则 manifest 会如实标脏。

## 7. 已知限制

1. 步骤在**同进程**内调用各模块 `main()`，内存是 Python 堆峰值，不含 pandas 原生内存；
   需要 RSS 时用 `Get-Process -Id <pid>` 观察。
2. `--demand-mode rebuild` 默认 `--no-fetch-uom`（离线）；要刷新 EN UOM 需另跑
   `self_fulfilled_demand.canonical`（会读 EN，只读）。
3. 动作层依赖另一位维护者的 `decision_join.py`；失败默认让整条流水线失败，
   可用 `--allow-optional-failure` 保留前四步产物。
4. 决策包文件名固定为 `decision_pack_2026-10-29.parquet`（模块内常量）；
   换日期时该名称不变，靠目录 `decision-pack-<date>-<rN>` 区分。
5. `latest.json` 只指向最近一次成功；历史版本靠 `pipeline-manifest-<date>-<rN>.json` 追溯。

## 8. 10-29 当天检查清单

- [ ] 新快照已落到 `en_stock.parquet`，`--snapshot-date` 与文件内日期一致
- [ ] `forecast/CURRENT` 是否为新版本；`--forecast-run-id` 与它一致
- [ ] `sku_map.tsv` 未变动（冻结哈希校验会拦）
- [ ] `--label` 用下一个可用版本号（r1/r2/…）
- [ ] 跑完后检查 `pipeline-manifest`：`status=ok`、各步 `ok`、`latest.json` 已更新
- [ ] 决策包 manifest 的 `partial` 与限制清单随包转交；不批准自动下单
