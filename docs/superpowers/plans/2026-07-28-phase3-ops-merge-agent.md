# Phase3 下一阶段计划 — 运营审 / 上游 merge / IvyeaAgent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Checkbox tasks.

**Goal:** Phase2 五杠杆 ingest 已通（E2E 标定店 35 候选含降/加 bid）。本阶段做人审阈值、上游同步、知识库 Agent，写路径仍硬禁。

**Architecture:** fzh-data 只持脚本/文档/OKF；AGPL 应用仍在 `IvyeaOps-sellfox`。E2E 只用 Cursor 内置浏览器；`start_ivyeaops_sellfox.ps1` 默认不弹系统浏览器。

---

## 已验证基线（2026-07-28 E2E）

| 项 | 结果 |
|----|------|
| 店 | 北京如泱-BJRYECLTD-US `596841` |
| UI `run_store` | **候选 35**；否词/收割/降bid/加bid 可见 |
| 加预算 | **0**（正确）：最高预算利用率 ~0.77 < 0.85，且近满活动 ACOS 高于目标 |
| 启动脚本 | 默认不 `Start-Process` 开 Chrome；`-OpenBrowser` 可选 |
| 环境 | 子进程显式注入 `SELLFOX_*` / `FZH_DATA_ROOT` |

经验：[docs/solutions/architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md](../../solutions/architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md)

---

## File map

| 文件 | 职责 |
|------|------|
| `ai_access_poc/board/docs/specs/ops-review-brief.md` | 运营审简报刷新（含 bid 类样本） |
| `IvyeaOps-sellfox` | `git fetch upstream` + merge |
| 新专题 / 文档 | IvyeaAgent 启动与 `/brain` 验收 |

---

### Task 1: 运营审（人）

- [ ] 从 UI 导出/截取 BJRYECLTD 35 候选，按「可直接用 / 阈值要改 / 不适用家纺」三类标注  
- [ ] 重点抽查：降bid 17、加bid 1、否词 15；加预算空是否接受（利用率阈值 85%）  
- [ ] 更新 `ops-review-brief.md` 签字栏 — **未签字不得谈自动执行**

### Task 2: 上游 IvyeaOps merge（fork 内）

- [ ] `cd IvyeaOps-sellfox && git fetch upstream && git merge upstream/main`  
- [ ] 冲突优先：`lingxing_data.py` / `optimizer` / `operate`；保留 `sellfox_*` 与写禁  
- [ ] 复跑：`ingest_sellfox_phase2.ps1`（可 `SKIP_REPORTS` 若 cache 新）+ 内置浏览器 E2E

### Task 3: IvyeaAgent

- [ ] clone/启动 https://github.com/Hector-xue/ivyea-agent `:8765`  
- [ ] `/brain` 从关键词降级 → 语义检索冒烟  
- [ ] 与广告杠杆解耦；失败不阻断 `/assistant`

### Task 4: 启动/DX 小修（本轮可做）

- [x] `start_ivyeaops_sellfox.ps1`：默认不弹系统浏览器；显式传 PoC env  
- [ ] handoff/README 写明：Agent E2E 用内置浏览器；人手可 `-OpenBrowser`

## 不做

- 广告写 / operate 放开  
- 为凑「加预算」而改阈值（除非运营审要求）  
- AGPL vendoring 进 fzh-data  
