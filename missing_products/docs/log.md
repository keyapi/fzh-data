---
okf: v0.1
type: Log
title: missing_products 变更日志
tags: [missing_products, log]
---

# 变更日志

## 2026-08-11
- **知识沉淀**: 新增根级解决方案 `docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md`、`missing-products` Skill 和 `docs/lessons` 全流程复盘；将完整码精确登记、赛狐产品映射、半成品边界及回读验证固化为可触发流程。
- **修正**: 三方审计改为完整通途 SKU 精确匹配，`-Cover/-Foam` 基码只作候选
- **更新**: 从 EN 产品 Item 完整 `customer_items` 回读，保留一码多产品关系
- **生产写入**: 3 条有库存皮壳 SKU 登记到对应 EN 产品并回读验证
- **结果**: 1411 个有库存通途 SKU 中 1397 已登记 EN 产品；剩余 14 全部是已知暂缓项
- **赛狐验证**: 皮壳 108 条、海绵 25 条对应的 EN 产品 SKU 全部存在
- **只读调查**: `PK#` 无客户码；`HM1510` 有 53 个唯一“物料+客户码”组合，本轮未清理

## 2026-08-10
- **更新**: `docs/solutions/conventions/erpnext-item-variant-creation-convention.md` — 新增「属性集完整性」「客户码唯一」「abbr 必带」「变体命名」等坑 + 审计确认（仅 KS0013 缺颜色已修复）
- **新增**: `fix_ks0013_color.py` — 修复方形枕套 KS0013 缺颜色（KS0013-HLR-80-COFFEE）
- **更新**: `AGENT_HANDOFF.md` — §4.5 EN 核心原则（防止 AI 犯错）
- **背景**: 审计确认其余物料属性完整；根因是 KS0013 历史属性集不完整
- **新增**: `AGENT_HANDOFF.md` — 完整交接文档（背景/当前状态/下一步/技术细节/经验教训）
- **新增**: `create_en_materials.py` — EN 老产品补齐脚本（星球/石头/张嘴熊/泰迪/方形枕套，幂等，--phase 1-6）
- **更新**: `specs/old-product-completion-plan.md` — 标记阶段1(EN)完成，更新实施记录
- **背景**: 通途未匹配 54→14；EN 老产品补齐完成；下一步赛狐侧
