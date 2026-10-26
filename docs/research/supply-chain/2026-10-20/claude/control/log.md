---
okf: v0.1
type: Log
title: 项目控制面变更日志
date: 2026-10-23
---

# 控制面变更

## 2026-10-26 Codex 交接
- 按用户额度收尾要求固定 Jack 新交接，连接 JACK_ENTRY/JACK_QA：记录 app draft PR、测试部署、75 项验证、PO 秒级入库时间与来源不足；明确完整七阶段与库存自动修正尚未完成，生产不动。

## 2026-10-23

- **新增**：按用户授权固定整体交付计划、证据看板和老板简报；工头负责持续更新，外部监督核真实证据。
- **新增**：库存决策评价理论，区分误差、概率预测、服务/库存/成本，接入长短史、PB、Shipment与补货任务。
- **更正**：历史月初缺失只影响对应回放，不是前向补货的全局前提；1,328近期销售母集不冒充公司完整在售目录。
- **记录**：新前向稿与DN桥仍待提交/独立审查；SO需求守恒、疑似同批、未知在产、场景/验收混用列为优先风险。
- **新增（2026-10-23 晚）**：建立 Jack W1 只读协作通道 `docs/jack-w1-channel`（docs-only，无业务 CSV）：
  9 个冻结 SKU 更正（替代旧 8+2）、七问答复、数据/背景读取地图、SC14 可执行验收契约。
  行级业务数据仍留本地；公开仓库不放 CSV（D33）。
- **补充（2026-10-24）**：`docs/jack-w1-channel` 合并 `origin/main`（`3405ac10`，含 #291 履约查询统一入口）；
  Jack 的必读增加 `EN_API/fulfillment_query.py` 与 `supply_chain_visibility/AGENT_HANDOFF.md`，W1 不重写查询入口。
- **新增（2026-10-26）**：SC14 阶段扩为 7 个（`partially_received` / `unknown`），21/21 用例通过；
  首轮 8 问答复 `handoffs/2026-10-26-jack-w1-answers-r1.md`（阶段/WO/PO021735/映射/仓库/received + 10-22 冻结基准）。
- **新增（2026-10-26）**：固定 Jack 入口 `handoffs/JACK_ENTRY.md` + 唯一问答日志 `handoffs/JACK_QA.md`；
  所有后续答复只追加到 JACK_QA，不再分散在 commit/PR 评论。Q07 仓库相加口径已更正。
- **2026-10-26 W1 v0 复审**：`140bbee6`（代码进 docs 分支）已 revert 为 `bb87549a`；代码保留在
  `feature/jack-supply-timeline`（`9aea4cb6`）。复审 `[W1-Q09]` 写入 `JACK_QA.md`：6 项必改
  （代码位置、SC14 不 fork、PO status 4 标签、WO 审计、received 28 行、B_min/B_max 桥接）。#311 保持 draft。
- **2026-10-26 A09/Q10**：A09 已收（feature `f63af171` + `40d74491`，draft PR #312）；SC14 副本与 canonical
  逐字节一致，B 桥接自洽。`[W1-Q10]`：**阻塞** `config/frozen_20261022.json` 行级业务 JSON 进公开仓库（D33）；
  另需修 SC14 同步测试 skip、PR312 body 过期、WO 审计时点、B 桥接 per-PO 明细。
- **2026-10-26 Jack 答复 Q09**：`[W1-A09]` 已写入 `JACK_QA.md`；代码在 `feature/jack-supply-timeline`
  （`f63af171` SC14 同步、`40d74491` Q09 #3–#7），draft PR #312；#311 保持 docs-only / draft。
  验证：233 行 / SC14 21/21 + 0 error / 132 warning / SC04 差 0 / B_min 1,212 / B_max 2,762+433。
- **2026-10-26 Jack 答复 Q10**：`[W1-A10]` 已写入 `JACK_QA.md`；D33 行级配置移出公开仓库
  （只留 schema/sha256/聚合 summary），代码在 `feature/jack-supply-timeline`（`62546ea7`），draft PR #312。
  验证：233 行 / SC14 21/21 + 132 warning / SC04 差 0 / B_min 1,212 / B_max 2,762+433 / 单测 19 passed 0 skip。
  #311、#312 保持 draft，行级 JSON 清关前不合并。
- **2026-10-26 A10/Q11**：A10 已收；数量 JSON 清关解除（config 只剩 schema/sha256/summary）。
  `[W1-Q11]`：剩余 2 项必改（仓库 confidence/scope 一致性、SC14 同步默认仍可能 skip）+ 1 项用户决定
  （`sample_skus/warehouse_map` 标识 JSON 是否也移出公开仓库）。
- **2026-10-26 用户决定**：`sample_skus.json` / `warehouse_map.json` **保留**（无数量/金额，与 sample10 文档同级）；
  Q11 该项关闭，仍剩 2 项必改（仓库 confidence/scope、SC14 同步默认）。
- **2026-10-26 Jack 答复 Q11**：`[W1-A11]` 已写入 `JACK_QA.md`；仓库 scope 语义（operator）、波兰仓 confidence→assumed、
  SC14 离线同步 + `tests/run_canonical_tests.py`、`sample_skus.json` as_of_note 已落地。代码 `e15b1b91`；draft PR #312。
  验证：233 行 / SC14 21/21 + 132 warning / SC04 差 0 / B_min 1,212 / B_max 2,762+433 / 19 passed 0 skip。
- **2026-10-26 Jack P0 进展**：`[P0-A-2026-10-26]` 已写入 `JACK_QA.md`；入库证据/采集/对账/数据层/报表 UI 完成，
  fzh-data `f5bf3dcc`（#314）、key_test `e7a4f6d`（#2），113+22 测试；测试站未部署。待决项见条目。
- **2026-10-26 A11 验收**：工头判定通过；核心逻辑未改，数字沿用。合并顺序建议 `#311 → rebase #312 → #312`；
  #311/#312 仍 draft，等用户/审核会话批准。待业务确认：PO status=4、FZH-DANEEY 子仓运营方。
- **2026-10-26 合并就绪清单**：新增 `handoffs/2026-10-26-merge-readiness.md`（#311 → rebase #312 → #312、
  检查项、业务确认、禁止项），给审核/合并会话直接使用。
