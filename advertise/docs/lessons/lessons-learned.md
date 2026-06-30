---
okf: v0.1
type: Lesson
title: 经验教训
description: 12 条 Lessons Learned
tags: [amazon, advertising, lessons, best-practices]
---
# 经验教训 — Amazon 广告分析模块

> 何时读: 接手模块时、遇到类似问题时、做架构决策时参考。
> 最后更新: 2026-06-30 | 共 13 条

## Lesson 1: CSV 金额列格式 (已修复)

**问题**: 广告活动 CSV 的 spend/sales/budget/cpc 列值是 `$17.78` 格式的字符串，`pd.to_numeric` 全变 NaN。
**解决**: `__init__.py` 加载时 `str.replace(r"[$,\s]", "", regex=True)` 清洗后转换。
**文件**: [`advertise/__init__.py`](../../../advertise/__init__.py)

## Lesson 2: 去重列的存在

**问题**: 广告活动报告中有 impressions/clicks/spend/cpc 和去重版本。去重版本可能比非去重版本值大。
**决定**: 当前用非去重版本。去重版本保留在列映射中但未参与分析。

## Lesson 3: 广告位中文值精确匹配 (已修复)

**问题**: 最初用模糊关键词匹配广告位分类，未覆盖实际值。
**解决**: 从数据导出所有唯一值建立精确映射：站内搜索结果顶部/站内商品页面/站内搜索其余位置/站外。

## Lesson 4: 光环效应数据仅投放报告完整

**问题**: 广告 SKU vs 其他 SKU 数据只在投放报告中完整。
**解决**: 光环效应分析放在 `analyze_targeting.py`。

## Lesson 5: 搜索词报告是最大文件

4,928 行。纯 Python 循环 < 1 秒。>10 万行需预编译正则或并行。

## Lesson 6: 搜索词必须先聚合再分类 (v0.2 修复)

**问题**: 同一搜索词在原始报告中分散在多行（不同活动/匹配类型），逐行判断导致误判否定词。
**验证用例**: `bed wedge pillow for headboard` — 13 行合计 1 订单 + $65.99，但单行看有 0 订单的。聚合后正确分类为 Monitor。
**正确做法**: 先 `GROUP BY search_term` 汇总，再分类。
**来源**: [Trellis Workflow](https://gotrellis.com/resources/blog/amazon-search-term-report-workflow/)

## Lesson 7: 5 桶分类 > 3 分类 (v0.2 修复)

**问题**: 原来只有 Harvest/Negate/Waste 三个桶，缺少 Monitor（数据不足）和 Protect（战略词）。
**标准**: Trellis/WisePPC 一致推荐 Harvest/Negate/Monitor/Protect/Ignore。
**关键**: Negate < 15 点击是小样本，不是判决。

## Lesson 8: SP 7 天点击归因窗口 (v0.2 修复)

报告末尾 3-4 天归因不完整。最小报告期 14 天。数据保留仅 60 天。
**实现**: 报告期 < 14 天自动警告。

## Lesson 9: 否定词三个关键细节

1. SP 只有词组否定和精准否定，没有广泛否定
2. 收割后必须在源活动否定（否则新旧活动同时竞价→CPC 抬高）
3. 词组否定谨慎使用（一个不小心的词组否定可能屏蔽几十个长尾词）

## Lesson 10: 决策日志的重要性

每次运行覆盖上次结果，无法追溯变化。Treillis 标准：必须记录每次收割/否定/Monitor 决策。
**待实现**: `out/decision_log.json` 追加式记录 (Phase 3)。

## Lesson 11: 报告字段命名差异

中文后台"去年"开头的列实际是"去重"列（编码错位）。搜索词 `match_type` 对自动广告显示 `-`。

## Lesson 12: 文档架构 — 渐进披露

**问题**: AGENT_HANDOFF.md 一度膨胀到 350+ 行，Agent 难以快速定位。
**解决**: 按 Diátaxis 框架拆分: 入口(AGENT_HANDOFF) → 参考(reference/) → 调研(research/) → 设计(specs/)。
**原则**: 每个文件独立可读，底部有 "See also" 交叉引用，入口文件只放高频信息+导航。

## Lesson 13: 外部数据源声明必须先验证官方文档 (v0.3 修复)

**问题**: `data-sources.md` 列出了 9 种"缺失的 SP 报告"，每项分配了 API ID 和优先级。但这些声明来自二手资料推断，未经 Amazon 官方 API 文档验证。2026-06-30 三路并行 agent 校验后发现：3 种报告不存在（Budget、Ad Group for SP、Video），2 种仅 Console 无 API（Search Term Impression Share、Performance Over Time），仅 4 种确认正确。

**影响**: 错误的 API ID 和报告类型传导到 roadmap、AGENT_HANDOFF（"4/13 SP 报告"）、column-mappings，导致 phantom 任务项和膨胀的数据覆盖率指标。Agent 会基于不存在的报告给用户错误指引。

**解决**: 用官方文档逐项校验后重写表格，新增校验状态（✅/⚠️/❌）、实际获取方式、官方文档 URL 三列。校验时间戳 `2026-06-30` 作为后续重新校验的锚点。

**教训**: 任何引用外部系统能力的声明（API 端点、报告类型、数据源、工具支持矩阵）必须在写入仓库前对照官方文档逐条验证并附上出处 URL。从命名约定推断的 API ID（如认为"Ad Group 报告" = `spAdGroups`）不可信。

**详见**: [`docs/solutions/documentation-gaps/unverified-external-api-claims-in-docs.md`](../../../docs/solutions/documentation-gaps/unverified-external-api-claims-in-docs.md)

## See also
- [数据源全图](../reference/data-sources.md)
- [列名映射](../reference/column-mappings.md)
- [设计文档](../specs/2026-06-16-amazon-advertise-analysis-design.md)
