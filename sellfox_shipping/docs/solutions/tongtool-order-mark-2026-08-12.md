---
okf: v0.1
type: Solution
title: 通途订单标记 — 美东100.xls 上传 → EN 匹配 → 本地赛狐包裹标记
description: 读通途 xls 参考编号(P号) → ERPNext Tongtool Package → Amazon 订单号 → 本地包裹匹配 → is_tongtool 持久化标记 + Transactions 过滤
timestamp: 2026-08-12
tags: [sellfox-shipping, tongtool, en-erpnext, xls-upload, package-mark]
---

# 通途订单标记 — 美东100.xls → 赛狐包裹标记

## 需求

`D:\美东100.xls` 是通途导出的订单清单，`参考编号/Reference Code` 列是**通途包裹号**（P 开头，如 P81678873）。需求：

1. 用 P 号在 EN(ERPNext) 查到对应的**通途订单号**（Amazon 订单号）。
2. 在本地赛狐包裹列表里，找到**关联订单含该 Amazon 订单号**的包裹。
3. 把包裹**持久化标记为「通途订单」**（基本信息面板勾选/显示）。
4. **Transactions** 增加「有/无通途订单标记」过滤。
5. 匹配不到的 P 号**单独报告**（不静默丢弃）。

## 数据链路（2026-08-11 实测 114/114 全部匹配）

```
美东100.xls 参考编号 P81678873（通途包裹号）
  → ERPNext GET /api/resource/Tongtool Package/{P}
  → order_links[0].order_id = "CUS-112-9957834-2887428"（带渠道前缀）
  → 去前缀（正则 \d+-\d+-\d+ 匹配则原样；否则取第一个 '-' 之后）= Amazon 订单号
  → 本地包裹 shipping_orders.external_order_id 匹配 → 包裹 P2B9A9T734635
  → 标记 is_tongtool=1, tongtool_p_numbers='P81678873'
```

## 实现

| 文件 | 内容 |
|---|---|
| `migrations/0023_tongtool_mark.py` | `shipping_packages` 加 `is_tongtool`(bool) + `tongtool_p_numbers`(str)，防御性（表不存在跳过）|
| `package_repository.py` | PackageRow 两列；`mark_tongtool`/`clear_tongtool`/`get_tongtool_mark`/`index_packages_by_external_order`；list/count 加 `tongtool` 过滤 |
| `tongtool_service.py`（新）| 读 xls → EN 并行查询（ThreadPoolExecutor）→ 匹配 → 持久化；未匹配单独报告 |
| `cli.py` | `packages-mark-tongtool --xls <path>` |
| `app.py` | `/tongtool` 上传页 + `POST /tongtool/upload`；/packages 加 `tongtool` 过滤（**仅 Transactions tab 生效**）|
| `package_service.py` / `package_models.py` | PackageListRequest + PackageListItem 加 tongtool |
| 模板 | `tongtool_upload.html`（新上传页，带加载提示）、`packages.html`（通途列+过滤）、`package_detail.html`（基本信息面板通途标记）|
| `test_tongtool.py` | xls 读取去重、去前缀、匹配标记、列表过滤 |

## 关键设计决策

- **持久化**（非实时）：上传匹配一次，is_tongtool 落库，详情/列表直接查库，不反复调 EN。
- **Web/CLI 一致**：都调 `tongtool_service.match_and_mark`，目的都是读文件 + 匹配。
- **并行提速**：114 个 EN 查询串行需 60s+（Web 请求超时、预览跳首页），改为 `ThreadPoolExecutor(max_workers=4)` → **~7s**。
- **过滤只在 Transactions**：Dashboard/包裹 tab 默认显示全部，避免 URL 残留 `tongtool=yes` 误过滤其他页签。
- **前缀去法**：`order_id_to_amazon` 先判断是否已是 `\d+-\d+-\d+`（Amazon 格式），否则取第一个 '-' 之后。

## 验证

- `uv run pytest tests/sellfox_shipping`：**311 passed**。
- CLI / Web 上传 `D:/美东100.xls`：114 匹配 / 0 未匹配，~7s。
- Transactions `tongtool=yes` → 114 条；Dashboard 默认 4526 条。
- 详情页 P2B9A9T734635 显示「✓ 通途 (P81678873)」。

## 待办 / 边界

- 若后续通途清单变化，重新上传会**覆盖**标记（当前为叠加，可再上传）。未实现「清除旧标记后重建」。
- 某些 P 号 EN 查不到/无本地包裹时走 `unmatched_rows` 报告。
- 并发查 EN 有触发限流风险（frappe 通常宽松），如遇限流把 `max_workers` 调小或加 `en_interval_s`。
