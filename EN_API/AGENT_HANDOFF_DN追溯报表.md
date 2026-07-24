# 销售出库→物料移动追溯报表 — Agent Handoff

> **脚本**: `EN_API/dn_trace_report.py`
> **输出**: `EN_API/out/{month}_DN追溯报表_{ts}.xlsx`

## 快速操作

```bash
# 7月数据
uv run python EN_API/dn_trace_report.py --month 2026-07

# 指定单号
uv run python EN_API/dn_trace_report.py --dn DN-2407-00001
```

## 数据链

```
DN (docstatus=1) → DN Item.against_sales_order → SO
  → WO.sales_order → WO (status: In Process/Completed)
    → SE.work_order → SE (type: Material Consumption for Manufacture, docstatus 0/1)
      → SE Item (s_warehouse, item_code, item_name, qty, uom)
```

## Excel 输出

| Sheet | 内容 | 列范围 |
|-------|------|--------|
| 追溯明细 | 非成品工单(非KS开头) → 完整链路含发料明细 | 18列(DN→SO→WO→SE→SE Item) |
| 成品工单 | 成品工单(KS开头, 不涉及耗用) | 10列(DN→SO→WO) |

## 关键设计

1. **仅 DN 按日期过滤** — SO/WO/SE 不受日期限制，避免跨月遗漏
2. **操作人姓名解析** — 通过 User 表将邮箱转换为 full_name
3. **成品/半成品分离** — WO.production_item 是否 KS 开头自动分流
4. **工单耗用类型** — `Material Consumption for Manufacture`，含草稿+已提交

## 技术要点

- **API**: ERPNext REST API，`requests` 直连（无 session，避免 keep-alive 417）
- **URL 编码**: `urllib.parse.urlencode` 全量编码，避免 nginx 拦截特殊字符
- **分页**: `paginated_get` 内置 offset 分页，默认每页 100 条
- **SE 批量获取**: 不按 work_order 过滤（URL 过长），全量拉取后 Python 侧过滤

## 已知限制

- 仅支持 `Material Consumption for Manufacture` 类型（非 `Material Issue` 或 `Material Consumption`）
- 操作人解析依赖 User 表存在对应记录，无匹配则显示原始邮箱
