---
okf: v0.1
type: Log
title: ai_access_poc 变更日志
---

# 变更日志

## 2026-07-28

- **板阶段收口**：按需 12/12 + Phase2 五杠杆已通；handoff/index/roadmap 可交接；ASIN 收割坑只文档化。solutions：`sellfox-ivyeaops-ondemand-fetch-parity.md`、`sellfox-search-term-asin-as-keyword-harvest.md`。
- **板 Phase2**：五杠杆 ingest 接线完成；ce-compound 写入 `docs/solutions/architecture-patterns/sellfox-ivyeaops-five-lever-ingest.md`；roadmap 勾选 ingest，下一步改为运营审 / 上游 merge / IvyeaAgent。

## 2026-07-24

- **双 PoC 收口**：壳 #113 + 板 #116 已合并；路线图改「运营审」为下一步；新增 `board/docs/specs/ops-review-brief.md`；main 上复跑 board runner（1922 行 → 候选 19）。
- **板 PoC B1–B6**：`ai_access_poc/board/` + 外部 `IvyeaOps-sellfox`；独立 runner 产出否词/收割候选；写禁。
- **壳 PoC 收口文档**：补齐 `open_webui/AGENT_HANDOFF.md`、OKF（roadmap / specs / lessons / reference）、README 补充 CI vs Terminal；全仓 solutions 写入 Tool summary + Open Terminal 模式。
- **壳 PoC 验证**：compose（OWUI + Terminal slim）、api.vilavi.cn 冒烟、赛狐代理拉 SP 搜索词、Tool v0.3 summary、Skill、自定义模型 `fzh-sellfox-ops`；Open Terminal 深挖与 Pyodide CI 对照演示。
- **壳 PoC 骨架**：`open_webui/` — docker compose、赛狐只读 Tool、Skill、CLI、`SELLFOX_API/client.py` 抽取（proxy + 限流重试）。
