---
okf: v0.1
type: Index
title: 经验教训
description: erpnext 模块排查过程中的经验教训
tags: [erpnext, lessons]
---

# 经验教训

## 2026-07-10 工单排查

### 1. MCP fac 工具连接测试系统

`fac` MCP 配置在 `.mcp.json` 中硬编码指向 `ensh.vilavi.cn` (测试)，不是生产系统。
排查生产工单必须用 REST API 直连 `erpnext.vilavi.cn`。
`.mcp.json` 中没有标注，导致初次查询返回 0 结果。

→ 建议: 在 `.mcp.json` 加注释标注系统环境。

### 2. owner ≠ employee

Job Card 的 `owner` 字段是创建记录的人 (钉钉账号)，`time_logs[].employee` 才是执行工作的员工。
一键完工的虚拟 Job Card 特征是 `time_logs[].employee = HR-EMP-00001`。
列表查询不返回 time_logs 子表，需要单独查询每条 JC。

### 3. 数据拉取时间窗口陷阱

按创建时间 (creation) 过滤 Job Card 会漏掉早期创建的真实工人 JC。
例如 WO-26-00082 的 98 条真实 JC 是 1 月创建的，按 6 月过滤只能拉到 7 条杨义森的虚拟 JC。
必须按 `work_order` 直接查询，不加时间过滤。

### 4. JSON 中文编码

Python 写 JSON 文件时必须用 `encoding='utf-8'` 和 `ensure_ascii=False`。
Windows 系统默认编码是 GBK，直接输出中文会导致 Excel 报告乱码。

### 5. 成品fg vs 半成品分类

`KS` 开头的产品编码 = 成品fg (0工序)，`open_material_qty=0` 正常。
`PK#`/`ND#` 开头 = 半成品 (多工序)，`open_material_qty=0` 异常。
不先分类就分析，会把正常的成品标记为问题。
