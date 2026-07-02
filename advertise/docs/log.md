---
okf: v0.1
type: Log
title: 变更日志
description: Amazon 广告分析模块的时序变更记录
tags: [amazon, advertising, changelog]
---

# 变更日志

## 2026-07-02

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
