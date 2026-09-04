---
okf: v0.1
type: Log
title: fedex_track 变更日志
tags: [fedex, track, module]
---

# 变更日志

## 2026-09-04（续）
- **新增**: `ops_report.py` 运营异常报表生成器（多Sheet/配色/中文/EN/Amazon营业日口径）；`docs/ops-report-runbook.md`；`AGENT_HANDOFF.md`；skill `.agents/skills/fedex-track/SKILL.md`。
- **修正**: "已取消"仅当最终状态为取消且未交付（FedEx 事件流可能残留 CA 节点但已交付）；支持同号多票(复用跟踪号)。
- **背景**: 全量 6752 FedEx 号重跑(v2)；Python 异常分类计数与报表阈值见 docs/ops-report-runbook.md。

## 2026-09-04
- **新增**: `fedex_track` 模块（仿 ups_track）— client/models/batch/cli，官方 Track API OAuth2 批量（≤30/请求），保留完整 `scanEvents` 历史 + 三时点（建标/站点收件/交付）。输出 summary.csv / timeline.csv / raw.json。
- **新增**: `docs/index.md`（模块说明）、`.env.example`（FEDEX_* 凭证）。
- **背景**: FedEx 官方账号/组织乱局理清（879197228 在 2023 主组织 Centrade(10548976)，非赛狐）；腾讯企业邮箱管理员收重置码打通 lihui@ 登录；在 Centrade(10548976) 建 `fzh_fedex_track` 项目（Basic Integrated Visibility=Track）生成 production key。全量实测 6752 个 FedEx 号（Delivered 6644 / 在途 91 / 取消 5 / 查无 16），0 失败。
