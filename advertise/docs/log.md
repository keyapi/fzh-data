---
okf: v0.1
type: Log
title: 变更日志
description: Amazon 广告分析模块的时序变更记录
tags: [amazon, advertising, changelog]
---

# 变更日志

- **OKF 合规**: 补齐 4 个 .md 文件 YAML frontmatter (AGENT_HANDOFF/README/amazon-bulk-negative-keyword-format/Daneey Chat) + 6 个目录 index.md + docs/index.md 更新导航

## 2026-07-07 (v0.5.1) — P0-P3 改进

- **P0 配置+文档**: protected_terms 填入品牌词 (daneey/senight/rucen/bjryecltd), strategic_terms 三层关键词配置
- **P0 文档同步**: AGENT_HANDOFF.md v0.4→v0.5, README.md v0.2→v0.5, roadmap.md v0.3→v0.5.1, existing-codebase-audit.md 加 v0.5 修复标记
- **P1 搜索词战略分层**: nalyze_search_term.py 新增 classify_strategic_tier() — attack(主攻)/defense(防守)/long_tail(长尾)/general(通用) 四层标签, 产出 71主攻/142防守/12长尾
- **P1 行动建议时间线**: nalyze_cross.py harvest/negate 建议加 priority(P0/P1/P2) + suggested_week(W1/W2/W3) 字段
- **P1 品牌词安全校验**: generate_negatives.py 加品牌词保护逻辑 — brand/protected terms 自动跳过不否定
- **P2 产品线聚合**: 新建 nalyze_product_line.py — 按产品线(SKU前缀)聚合7条产品线, 计算结构健康度+缺失活动类型
- **P2 Campaign 结构蓝图**: 新建 suggest_campaign_structure.py — 基于 Daneey 策略输出7活动模板+预算分配建议
- **P3 决策日志**: 新建 decision_log.py — out/decision_log.jsonl 追加式记录, 含上期diff对比
- **参考归档**: Daneey ChatGPT 聊天记录 参考文档/Daneey_Amazon_Outdoor_Sofa_Optimization_Chat.md 作为产品策略参考正式纳入文档体系

## 2026-07-02 (Phase 3-4)

- **v0.5 Phase 3**: 跨报告集成分析 — `analyze_cross.py` 产出 Blended ACOS per campaign、Gateway ASIN 最终判定、搜索词收割/否定清单、账户健康度评分 (55/100 C级)
- **v0.5 Phase 3**: 输出正确 ACOS: 直接 51.8% → 含光环 **41.1%** (光环拯救 10.7 个百分点)
- **v0.5 Phase 3**: `build_full_report.py` 扩展为 10-sheet Excel (新增"跨报告集成"sheet) + 47 条行动建议
- **v0.5 Phase 4**: `calibrate_thresholds.py` — 基于实际数据分布的阈值基线标定 + 敏感度分析
- **v0.5 Phase 4**: `generate_negatives.py` — Amazon bulksheet .xlsx 否定词生成器 (16 候选词 → 53 行，含 campaign ID 映射)
- **v0.5 Phase 4**: 调研确认否定词格式为 .xlsx (非 CSV)，赛狐 API 仅支持查询否定词

## 2026-07-02 (Phase 1-2)

- **v0.5 Phase 1**: 基础设施重构 — `utils.py` (共享工具), `thresholds.py` (集中阈值), `column_maps.py` (API 8 种报告列名映射), `config/bjryecltd-us.json` (账户配置)
- **v0.5 Phase 1**: `__init__.py` 重写 — 双格式 (Console + API) 自动检测、多路径回退、多文件合并加载
- **v0.5 Phase 1**: 新增 3 个分析脚本: `analyze_purchased_item.py` (最高 ROI, 13 行 → Gateway ASIN), `analyze_advertised_product.py` (29 ASIN 效率排行), `analyze_ad_group.py` (29 组结构诊断)
- **v0.5 Phase 1**: 所有现有脚本适配 API 格式 — `_safe_num()` 去重到 utils, 列名从 Console 格式 (orders_7d) 修正为 API 格式 (orders), Placement 中/英文双支持
- **v0.5 Phase 1**: 消除 4 处 `_safe_num()` 重复, 硬编码阈值集中到 `thresholds.py`, `PROTECTED_TERMS` 等品牌词配置从空集变为可配置
- **v0.5 Phase 2**: `build_full_report.py` — 读 7 个分析 JSON, 产出 10-sheet Excel + 47 条行动建议
- **v0.5**: 调研产出 3 份深度报告: `sp-report-analysis-value.md` (734 行), `existing-codebase-audit.md` (651 行), `amazon-bulk-negative-keyword-format.md`
- **v0.5**: 创建 `2026-07-02-ad-analysis-master-plan.md` — 4 阶段总体规划

## 2026-07-02 (v0.4)

- **v0.4**: 赛狐 API 全量广告报告拉取 — BJRYECLTD-US (June 2026) 20 个报告 (SP 8 + SB 7 + SD 5)
- **v0.4**: 新增 3 个拉取脚本: `SELLFOX_API/fetch_ad_reports.py` (4 核心 SP), `fetch_extra_reports.py` (3 额外 SP), `fetch_sb_sd_reports.py` (12 SB+SD)
- **v0.4**: 新增 `sp-report-column-reference.md` (40KB) — SP 8 种报告 162 字段完整定义，18 个来源交叉验证
- **v0.4**: 新增 `sb-sd-report-column-reference.md` — SB 7 种 + SD 5 种报告 419 字段定义，12 个来源交叉验证
- **v0.4**: 新增 `amazon-official-docs/` — 官方来源归档 (sources-summary, field-definitions-quick-reference, sb-sd-sources)
- **v0.4**: 更新 `AGENT_HANDOFF.md` — 凭证路径修正为 `SELLFOX_API/.env`，添加 API 拉取入口
- **v0.4**: 确认 SB/SD 投放极少: SB 0 行数据, SD 仅 1 个再营销 campaign (7 天 × 3-5 KB)
- **v0.4**: 关键发现:requests 在中文 Windows 签名失败→改用 urllib; 下载文件为 xlsx 非 csv; taskIds 为数组非单值; 中文状态字符串; URL 需百分号编码; 任务间需 2s 延时

## 2026-06-30

- **v0.3 修正**: 9 种 SP 报告类型官方文档逐项校验（3 并行 agent），修正 5 处错误声明
- **v0.3 修正**: `data-sources.md` 重写缺失报告表 — 增加校验状态(✅/⚠️/❌)、实际获取方式、官方文档 URL
- **v0.3 修正**: 新增 Lesson 13（外部数据源声明必须先验证官方文档）+ `docs/solutions/documentation-gaps/unverified-external-api-claims-in-docs.md`
- **v0.3 修正**: AGENT_HANDOFF.md 修复 merge conflict + 清理过时引用 + 添加 Agent 首次接手检查清单
- **v0.3 修正**: README.md 添加非技术同事入口 + troubleshooting section
- **v0.3 修正**: 创建 `advertise/数据源/.gitkeep` + `README.txt` 确保目录在仓库中可见

## 2026-06-17

- **v0.3**: 文档架构重构 — 按 OKF v0.1 标准加 frontmatter, 文档从 `docs/superpowers/` 移至 `advertise/docs/`（co-location）
- **v0.3**: 6 维度专家级深度调研完成（通用数据分析 + Amazon 广告策略 + 数据生态 + 行业趋势 + 工具 + 系统架构）
- **v0.3**: 工具修正 — 优麦云替换卖家精灵作为主要工具, 卖家精灵保留用于竞品情报 MCP
- **v0.3**: Skills/MCP 调研 — 7 个可复用资源目录
- **v0.3**: TACoS 方法论 + AMC 自服务化 + COSMO/Alexa for Shopping 深度研究

## 2026-06-16

- **v0.2**: 搜索词聚合修复 — 先 GROUP BY search_term 再分类 (修复 `bed wedge pillow for headboard` 误判)
- **v0.2**: 5 桶分类体系 — Harvest/Negate/Monitor/Protect/Ignore
- **v0.2**: 阈值对齐行业标准 — Harvest≥2单, Negate≥15点击, Monitor<15点击
- **v0.2**: 归因窗口检查 — 报告期<14天自动警告
- **v0.1**: 基础框架 — 数据加载 + 4 分析脚本 + Excel 6 sheet 报告
- **v0.1**: AGENT_HANDOFF.md 初始版 + 26 个资料来源 URL
