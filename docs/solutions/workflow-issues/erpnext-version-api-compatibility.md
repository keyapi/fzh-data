---
title: ERPNext Custom App 跨版本 API 兼容性检查
date: 2026-07-15
category: docs/solutions/workflow-issues/
module: erpnext_custom_app
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "deploying ERPNext custom apps across test and production environments"
  - "debugging bugs that reproduce on test but not production (or vice versa)"
  - "using Cursor Agent or other AI tools to diagnose ERPNext issues"
  - "planning ERPNext version upgrades"
symptoms:
  - "custom validation functions succeed on test but fail silently on production"
  - "Cursor Agent cannot discover root causes tied to version-specific API field differences"
  - "production bugs that are difficult to reproduce locally or on test systems"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
related_components:
  - database
tags:
  - erpnext
  - version-compatibility
  - frappe-framework
  - api-diff
  - cross-version
  - dev-workflow
  - cursor-agent
---

# ERPNext Custom App 跨版本 API 兼容性检查

## Context

ERPNext 测试系统 (v15.59.0) 和生产系统 (v15.43.3) 运行不同版本。过去已多次出现因版本差异导致的问题：自定义 app 代码在测试系统正常工作，部署到生产后却静默失败。最近一次案例中，`delivery_plan` app 的库存维度验证函数在生产上完全不执行，而 Cursor Agent（仅能 SSH 测试系统）花了大量时间却未能定位根因——因为根因藏在生产系统 ERPNext 的 API 字段差异里。

## Guidance

### 1. 调用 ERPNext 内部 API 前，必须在两个版本上验证返回结构

ERPNext 的 `frappe.get_all()` / 内部函数在不同小版本间可能返回不同的字段集合。编写 custom app 代码调用这些 API 时，不要假设所有版本返回相同的字段。

**验证方法：**
```bash
# 在两个服务器上分别执行 bench console，对比 API 返回结构
ssh test-server
cd /home/frappe/frappe-bench && bench console
>>> from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
>>> import json
>>> print(json.dumps(get_inventory_dimensions(), indent=2, default=str))
# 检查每个 dict 的 keys 是否一致
```

**实际案例** — `get_inventory_dimensions()` 在两个版本的 SELECT 字段差异：

```python
# v15.43.3 (生产) — 缺少 source_fieldname
fields = [
    "distinct target_fieldname as fieldname",
    "reference_document as doctype",
    "validate_negative_stock",
]

# v15.59.0 (测试) — 包含 source_fieldname
fields = [
    "distinct target_fieldname as fieldname",
    "source_fieldname",              # v15.59.0 新增
    "reference_document as doctype",
    "validate_negative_stock",
]
```

### 2. 优先使用跨版本稳定的替代 API

当发现某个 API 在不同版本间字段不一致时，寻找同模块中字段集合在两个版本都稳定的替代方案。

**实际案例修复** — 将 `get_inventory_dimensions()` 替换为 `get_document_wise_inventory_dimensions("Delivery Note")`：

```python
# 修复前 — get_inventory_dimensions 在 v15.43.3 不返回 source_fieldname
def _get_tracking_number_dimension_meta():
    from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
    dimensions = get_inventory_dimensions()
    # dim.get("source_fieldname") 在生产上返回 None → 函数返回 None → 验证静默跳过

# 修复后 — get_document_wise_inventory_dimensions 在两个版本都包含 source_fieldname
def _get_tracking_number_dimension_meta():
    from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_document_wise_inventory_dimensions
    dimensions = get_document_wise_inventory_dimensions("Delivery Note")
    # dim.get("source_fieldname") 在两个版本都返回 "stock_tracking_number"
```

### 3. 给 AI Agent 明确的跨版本检查指令

AI 编码助手（Cursor Agent 等）通常只能访问单个环境。它们无法自动发现"这个 API 在另一个版本返回不同字段"的问题。当让 Agent 排查测试与生产行为不一致的 bug 时，需要明确指示：

- "这个 bug 只在生产出现，可能是 API 版本差异——请 SSH 到**两个**服务器对比相关函数的返回结构"
- 提供两个服务器的地址和 ERPNext 版本号
- 要求 Agent 用 `bench console` 对比 API 输出

### 4. 文档化已知的版本差异

将本学习文档和具体 bug 的修复文档放在仓库中，方便未来的自己和同事回溯。对应的具体 bug 修复已记录在 `delivery_plan/docs/fix-tracking-dimension-stock-validation.md`。

## Why This Matters

- **静默失败难以排查**：当自定义验证函数因 API 字段缺失而返回 None 时，不会抛出异常，只是静默跳过。ERPNext 随后使用内置默认逻辑，表面上"功能正常"但实际行为不同。
- **AI 工具有盲区**：Cursor Agent 只能 SSH 测试系统，它读到的代码（测试环境的 ERPNext v15.59.0）本身就包含 `source_fieldname`，因此不会意识到生产版本缺失该字段。
- **反复出现**：这已经不是第一次因版本不一致导致问题。每次排查都耗费大量时间（本次从怀疑数据库配置错误、到对比 Inventory Dimension UI、到最终发现 API 字段差异）。
- **计划升级但需谨慎**：将生产升级到与测试一致的版本可以根治此类问题，但升级本身有风险（自定义 app 兼容性、数据库迁移、停机时间）。

## When to Apply

- 编写调用 ERPNext 内部 API（非 REST API）的新 custom app 代码时
- 排查"测试正常、生产异常"的 bug 时
- 让 AI Agent 协助 ERPNext 问题排查时
- 规划 ERPNext 版本升级时——优先评估当前 custom app 对目标版本 API 的兼容性

## Examples

### 完整的排查过程

**症状**：销售出库提交时，测试系统显示分组的库存不足汇总表，生产系统只显示默认的单条提示。

**走错的路径**：
1. 怀疑数据库配置错误 — UI 确认两个系统的 Inventory Dimension 配置完全一致
2. 怀疑 hooks.py 注册问题 — 两个系统的 `before_submit` 钩子完全一致
3. 怀疑 delivery_plan app 代码不同 — SSH 对比确认代码完全相同

**关键突破** — 在两个服务器上同时执行 bench console 对比 API 输出：
```python
# 生产 (v15.43.3)
>>> get_inventory_dimensions()
# source_fieldname=None  ← 关键差异！

# 测试 (v15.59.0)
>>> get_inventory_dimensions()
# source_fieldname=stock_tracking_number
```

**修复**：将代码中的 `get_inventory_dimensions()` 替换为 `get_document_wise_inventory_dimensions("Delivery Note")`，后者在两个版本都包含 `source_fieldname`。

## Related

- `delivery_plan/docs/fix-tracking-dimension-stock-validation.md` — 本次具体 bug 的完整修复文档
- 原始问题发生环境：生产 8.223.4.206 (ERPNext v15.43.3) / 测试 8.133.254.66 (ERPNext v15.59.0)
- 修复分支：`fix/tracking-dimension-source-fieldname`（delivery_plan repo）
