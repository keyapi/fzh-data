---
okf: v0.1
type: Log
title: 2026-11-24 变更日志
date: 2026-11-24
---

# 变更

## 2026-11-24

- **新增**：`evidence-chain-and-human-loop.md`（Research）—— 补货证据链、人工判断留痕与闭环评估的设计与差距。
  来源分支 `keyapi/evidence-chain` @ `b70ab848`，内容逐字节拷贝。
- **新增**：`agent-data-interface.md`（Research）—— Agent 数据读写接口、权限、选型与 MVP。
  来源分支 `feature/agent-data-interface-research` @ `8682e6b7`，内容逐字节拷贝。
- **新增**：`decision-defaults.md`（Research）—— 补货与需求协同的可配置默认值建议（`proposed-not-activated`）。
  来源本地提交 `ea4bd16f`，内容逐字节拷贝。
- **新增**：`unified-data-contract.md`（Spec）—— 统一数据契约 v1（`supply-contract/v1`），把前三份研究合成一份可验收契约。
  来源本地提交 `0715f6d4`，内容逐字节拷贝。
- **合并说明**：四份文档此前分别在四个并行工作树产出，本目录是它们的**唯一入库位置**；正文（含 frontmatter）未做任何修改，
  仅重写本 `index.md` 与本 `log.md`，并在上一级 [供应链研究索引](../index.md) 登记本批次。
- **边界**：本轮为文档合并，不改业务代码、不部署、不写生产数据。
- **已知链接限制**：`decision-defaults.md` 正文引用本地绝对路径 `D:/private/demand/roadmap-review-20261124.md`
  （作者本机私有资产，不在仓库内，未随文入库）；其余相对链接均已在仓库内解析通过。
