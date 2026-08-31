---
okf: v0.1
type: Log
title: 变更日志
---

# 变更日志

## 2026-07-10

- **初始化模块**: 创建 erpnext/ 目录结构，含 scripts/ + docs/
- **setup.py**: 凭证自动检查脚本，引导创建 .env
- **fetch.py**: 模块化数据拉取 (WO / JC / SE / Version)
- **gen_report.py**: 8步排查法 → 5类工单 Excel 报告
- **Skill**: 创建 `erpnext-wo-audit` skill (触发词: 工单排查/一键完工/生产工单分析)
- **CONCEPTS.md**: 创建项目领域词汇 (一键完工, 成品fg, 半成品, etc.)
- **OKF docs**: 按 OKF v0.1 标准创建 index.md, log.md, reference/, research/, lessons/

## 2026-07-10 (会话中)

- **探案过程**: 发现 `fac` MCP 指向测试系统 (ensh.vilavi.cn) 而非生产 (erpnext.vilavi.cn)
- **8步方法论形成**: 产品分类 → 虚拟工序检查 → Version活动 → open_mat分析 → JC time_logs → JC owner → SE分析 → 交叉验证
- **数据发现**: 153条6月工单中 55 条被一键完工影响 (36%)
- **关键洞察**: open_material_qty=0 对半成品异常但成品fg正常; time_logs.employee 是真正的虚拟/真实判断标准
