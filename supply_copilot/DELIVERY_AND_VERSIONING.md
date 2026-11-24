---
type: Reference
title: 补货系统交付与版本化方案
description: 五轴版本模型、git/EN 私有存储边界、三类用户交付、champion/challenger 对比回滚、最小可行架构与 P0/P1/P2
tags: [supply-copilot, versioning, delivery, reproducibility]
---

# 补货系统交付与版本化方案

## 结论先行

1. **别上新平台**：forecast run 已有 `run_id`/`CURRENT`/`rule_version`/schema/依赖版本/git sha（`forecast.py:57-58,1906-1996`），decide 已输出库存/SO/PO/预测哈希（`decide.py:76-78`）。缺的是统一审计头、别名和校验，不是 MLflow。
2. **拆五轴**：代码、引擎规则、决策政策、数据包、预测 run 各自不可变、各自版本化，输出合成一个 `bundle_id`。
3. **数据只进 EN 私有存储**（已有鉴权、白名单下发、哈希）；git 只放代码、manifest、schema，不含客户数据。
4. **两个入口、一套计算**：CLI/Agent（我们、老板、同事的完整能力）与工作台（证据链+人工建议）。只读页不是当前目标，确有只读人群再补。老板默认只看结果，不选版本。
5. **升级走挑战者对比，回滚=别名翻转**；run 目录写一次，永不覆盖。

## 1 版本模型

| 轴 | 标识 | 何时变 |
|---|---|---|
| 代码 | `sc-vX.Y.Z` git tag + commit sha | 发布 |
| 引擎 | `rule_version`（如 `autoets_m3_naive@...`）+ `schema_version` | 任何数值变化 |
| 政策 | `policy-<date>.<n>` + sha256 | 补货口径/服务水平/交期 |
| 数据包 | `pack-<as_of>.<seq>`（如 2026-11-13.1）+ `combined_sha256` | 重出包 |
| 快照 | `orders-<as_of>.<seq>`、`live-<branch>-<ts>` | 每次导出 |
| 预测 run | 不可变 `run_id`；`CURRENT`/`champion` 为别名文件 | 每次训练 |

semver 管人读兼容，`rule_version` 管数值复现，两者都要。日期版号只表发布顺序，**哈希才是身份**。

每次输出（报告/JSON/页面）必须带：tool{version,git_sha,dirty}、engine{rule_version,schema}、policy{version,sha}、data{pack/orders/history 的 version+sha,as_of}、live{snapshot_at,stock/so/po sha}、forecast{run_id,as_of}、computed_at。对规范化 JSON 取 sha256 得 `bundle_id`；报告首行只引这一个串。

## 2 存放位置

- **git**：代码、`uv.lock`、manifest、schema、非敏感政策、文档、测试。
- **EN 私有**：包分卷 `private/files/`、快照 `private/supply-history/<v>/`、预测 `private/supply-forecast/<run_id>/`、`registry.json`（run 状态与别名）、`current.json`（发布指针）、只读页。
- **本地 `FZH_DATA_ROOT`**：只当缓存，可随时删，绝不成为事实源。

不上 MLflow/DVC/lakeFS：单写入者、单模型族、周级 run，收益低于运维成本。DVC 只解决 Git 原生钉版本，我们已有 manifest；lakeFS 解决多写入者/大对象分支，我们没有。若历史数据到几十 GB 或多团队并发写，再上 lakeFS 并复用现有 NAS MinIO，增量约 $0–50/月（仅实例/运维），不引 SaaS。

## 3 交付形态（按现状收敛）

| 用户 | 入口 | 约束 |
|---|---|---|
| 我们/老板/同事的 Agent | 同一 CLI + 私有包；`doctor --verify` 通过才算正式 | 可 rebuild；不选版本，默认用 champion |
| 人类决策/复核 | 工作台：证据链 + 人工建议 + 可执行性 | 与 CLI 用同一 JSON/bundle_id，不重算 |

只读页暂不作为交付目标；只有当出现“完全不需要工作台、只看结论”的人群时再补。统一一个 CLI、一份 JSON 契约、一个工作台；不做第二套计算。
防旧数据：`doctor --verify` 同时校验本地 sha256 与线上 `current.json`，不一致即非零退出并打印“本地 X / 线上 Y”；输出头部带 `as_of` 超期告警。`_latest_file` 现按 mtime 选包（`cli.py:245`），须改为按版本/as_of 选，避免后拷入的旧包冒充最新。

## 4 升级、回滚、对比

1. 用**同一输入快照**跑 `challenger`，不覆盖 `champion`。
2. `compare --runs A B` 固定输出：逐 SKU Δq50/q90、总量偏差、回测/覆盖率、决策翻转率、Top 变动；门槛先定（如覆盖率不降、翻转率 <5%）。
3. 影子运行 2–4 周，页面可切换；通过后 `champion` 指向新 run。
4. 回滚=别名指回旧 run，分钟级，不重算。
5. run 写一次；保留最近 12 个 + 12 个月；状态 `active/challenger/deprecated/retired`，记 `deprecated_at`/`replaced_by`，不删被已发布报告引用的产物。
6. `reproduce --run <id>` 按 registry 取回代码锁、数据哈希、政策，重跑比对聚合与哈希，不一致即失败。

## 5 安全与权限

- EN Key 一人一号（System User），只读白名单；禁共享、禁 admin key；凭证只在未跟踪 `.env`。
- 原始数据/预测产物仅内部账号可取；老板只看聚合页；同事取包需业务确认范围。
- 非技术用户不给：API Key、原始 parquet、发布/提升别名、`rebuild --publish`。
- 发布与别名变更写 append-only registry（人、时间、bundle_id），可审计。

## 6 架构与落地

```
EN DB ──定时作业(服务器)──> 快照/预测/打包
                              │ 写一次 + sha256
                              ▼
                 EN 私有存储: pack / history / forecast
                 registry.json(状态+别名) / current.json
                              │ 只读白名单 API
        ┌─────────────────────┼─────────────────────┐
     CLI(我们/同事)        只读页(老板)          Agent 技能
        └──────── 所有输出同一 bundle_id ────────┘
```

- **P0（1–2 天）**：统一审计头 + `bundle_id`；`doctor --verify` 哈希与新鲜度；按版本选包；`policy_version` 独立；registry 加状态/别名/保留字段。验收：旧包放本地过不了 doctor；任一输出可凭 `bundle_id` 定位全部输入；`reproduce` 通过。
- **P1（2–3 周）**：发布原子化（先产物后指针）；`champion/challenger` + `compare`；工作台展示 `bundle_id`/`as_of`/可执行性；完成首次挑战者升级。验收：对比报告自动产出；别名回滚 <1 分钟；同事一条命令跑通且无需 clone。
- **P2（触发式）**：仅在数据量/并发/模型数达阈值时评估 lakeFS/MLflow；加漂移与覆盖率监控、manifest 签名。验收绑定真实触发条件，不为平台而平台。

## 参考

- MLflow：stages 已弃用，改用 alias（`models:/...@champion`）— https://mlflow.org/docs/latest/ml/model-registry/workflow/
- Sculley et al., *Hidden Technical Debt in ML Systems*（CACE/配置债）— https://papers.nips.cc/paper/5656
- CMU *Versioning, Provenance, and Reproducibility* — https://mlip-cmu.github.io/book/24-versioning-provenance-and-reproducibility.html
- DVC vs lakeFS 选型 — https://lakefs.io/data-version-control/
- UV `uvx` 免安装运行与钉版本 — https://docs.astral.sh/uv/guides/tools/
- CLI 版本可发现 — https://clig.dev/
