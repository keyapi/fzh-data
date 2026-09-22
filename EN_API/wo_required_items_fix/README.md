# 「变更物料」新增行的 `include_item_in_manufacturing` 丢失 —— 修复

## 症状
通过生产工单「面料处理 → 变更物料」弹窗**新增**的物料行，`include_item_in_manufacturing`
（纳入工单发料）**没有勾选**；从 BOM 带出来的老行都是勾选的。

## 这个字段是什么逻辑

ERPNext 生成**工单发料 / 工单耗用**的 Stock Entry 时，会把工单 `required_items` 逐行过一遍，
**只带勾选了的那些**：

`erpnext/stock/doctype/stock_entry/stock_entry.py:2391-2412`
```python
for d in work_order.get("required_items"):
    ...
    if d.include_item_in_manufacturing:      # ← 没勾的直接跳过
        entry.append("items", d.as_dict())
```

字段自带的说明（系统里已配的 Property Setter）也印证：

> 不勾选 → 该物料**不会随工单送制造**，需要**手工调到 WIP 仓、且不挂工单**。

正常取值应当是勾选：面料 `Item.include_item_in_manufacturing` 两台机器都是 **1**；
生产现有工单 `required_items` **36/36 全勾选**。

## 根因

`work_order_task/work_order_task/overrides/work_order_override.py` 的 `update_required_items()`：

- **新增行**只 append 了 5 个字段（`item_code / item_name / required_qty / source_warehouse / operation`），
  **没有 `include_item_in_manufacturing`** → 落到默认值 **0（不勾）**。
- **更新已有行**走 `_work_order_item_as_child_dict(original_row)`（复用原行全部字段）→ 勾选保留 ✓。

所以**只有"弹窗新增的行"会丢这个勾**。前端弹窗的列里也没有这一项，用户无法自己补勾。

## 修复（在 `work_order_override.py`）

| 位置 | 改动 |
|---|---|
| 新增 `_resolve_item_rate()`（模块级） | 按**本工单 BOM 的取价方式**（`rm_cost_as_per`）解析单价：Price List 查该 BOM 的 `buying_price_list`，Valuation Rate 取库存估值；取不到回落到物料主数据的 `valuation_rate` |
| `items_to_add.append({...})`（约 186 行） | 带出 `rate` / `amount = rate × qty` / `include_item_in_manufacturing`（后者按物料主数据） |
| `wo.append("required_items", {...})`（约 228 行） | 把上面这三个值写进新行 |

> ERPNext 自己在工单里手动加行时**并不会带单价**（`work_order.get_item_details` 只返回 uom/名称/描述等），
> 所以必须自己按本工单 BOM 的口径解析，才跟从 BOM 带出来的老行一致。

改动前该文件与生产**逐字节相同**，补丁可直接用于生产。
改前原件备份在测试机 `/tmp/work_order_override.py.bak_20260914`。

## 部署
- **测试机**：已部署 + `bench clear-cache` + `bench restart`（Python 改动必须重启）
- **生产**：同样替换该文件 + `bench restart`（由 EN 执行）

## 验证（测试机实跑）
在 `WO-26-00059` 上用不存在的口径新增一行 `DMML1010-BLUE-150-320`（qty 3.5）：

```json
{"item_code": "DMML1010-BLUE-150-320", "required_qty": 3.5,
 "rate": 15.4, "amount": 53.9, "include_item_in_manufacturing": 1}
```

- `rate=15.4` —— 与该 BOM `get_rm_rate` 的解析值一致 ✅
- `amount = 3.5 × 15.4 = 53.9` ✅
- 勾选 = 1 ✅

验证后该工单已还原（2 行、内容一致）。

另：探针用不存在的工单号调用 → 正常返回「工单不存在」（`_exc_source: work_order_task (app)`），模块加载正常。

## 备注
- 前端弹窗的 payload 里没有 `item_name / rate / amount / include_item_in_manufacturing` 这几项，
  名称由前端那段 JS 兜底（见 `EN_API/work_order_item_name_fix/`），单价/金额/勾选由本后端补。
  如希望更保险，后端也可以在新增行时用 Item 主数据补一次 `item_name`（目前**没做**）。
