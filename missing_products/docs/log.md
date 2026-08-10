---
okf: v0.1
type: Log
title: missing_products 变更日志
tags: [missing_products, log]
---

# 变更日志

## 2026-08-10
- **更新**: `docs/solutions/conventions/erpnext-item-variant-creation-convention.md` — 新增「属性集完整性」「客户码唯一」「abbr 必带」「变体命名」等坑 + 审计确认（仅 KS0013 缺颜色已修复）
- **新增**: `fix_ks0013_color.py` — 修复方形枕套 KS0013 缺颜色（KS0013-HLR-80-COFFEE）
- **更新**: `AGENT_HANDOFF.md` — §4.5 EN 核心原则（防止 AI 犯错）
- **背景**: 审计确认其余物料属性完整；根因是 KS0013 历史属性集不完整
- **新增**: `AGENT_HANDOFF.md` — 完整交接文档（背景/当前状态/下一步/技术细节/经验教训）
- **新增**: `create_en_materials.py` — EN 老产品补齐脚本（星球/石头/张嘴熊/泰迪/方形枕套，幂等，--phase 1-6）
- **更新**: `specs/old-product-completion-plan.md` — 标记阶段1(EN)完成，更新实施记录
- **背景**: 通途未匹配 54→14；EN 老产品补齐完成；下一步赛狐侧
