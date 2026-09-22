---
okf: v0.1
type: Index
title: pb_orders — 文档索引
tags: [pb, orders, sps, packslip, ups, label, tongtu, index]
timestamp: 2026-09-22
---

# pb_orders 文档索引

| 你需要... | 读这个 |
|----------|--------|
| Agent 完整交接（背景/文件/运行/函数表/坑/清单） | [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) |
| 人读模块说明（怎么用、出错怎么办） | [../README.md](../README.md) |
| 工作流细节：五步流程、列映射、坐标表、命名规则、数量对账 | [reference/workflow.md](reference/workflow.md) |
| 部署到 EN 测试服务器：前端、队列、离线缓存、Frappe 对比、**落地实现与实测** | [reference/server-deployment-architecture.md](reference/server-deployment-architecture.md) |
| 迁移踩坑记录 | [lessons/index.md](lessons/index.md) |
| 变更历史 | [log.md](log.md) |
| 编排总入口（CLI 与网页共用） | [../service.py](../service.py) |
| 命令行入口（薄适配器） | [../run_pb_orders.py](../run_pb_orders.py) |
| 网页服务（FastAPI 路由） | [../web/app.py](../web/app.py) |
| 任务库（SQLite 状态机与恢复） | [../web/repository.py](../web/repository.py) |
| 队列 worker | [../web/tasks.py](../web/tasks.py) |
| 容器编排（独立 Compose 栈） | [../docker-compose.yml](../docker-compose.yml) |
| 自动化测试 | [../tests/](../tests/) |
| 步骤 1-2：PDF 抽取 PO/Item | [../sps_pb_pdf.py](../sps_pb_pdf.py) |
| 步骤 3：通途导入 Excel | [../pb_tongtu_excel.py](../pb_tongtu_excel.py) |
| 步骤 4：标签 PDF | [../pb_label_pdf.py](../pb_label_pdf.py) |
| 步骤 4.2：背贴 PDF | [../pb_back_label_pdf.py](../pb_back_label_pdf.py) |
| 与 Colab 产物的一致性对比 | [../compare_runs.py](../compare_runs.py) |
