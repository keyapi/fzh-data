# 「面料处理 → 变更物料」物料名称不自动带出 —— 修复

## 症状（生产）
1. 变更物料弹窗里选好物料，**物料名称不自动带出**；
2. 控制台报 `Uncaught TypeError: Cannot read properties of undefined (reading 'idx')`（`work_order__js` → `onchange`）；
3. 测试机：**弹窗出现后第一次新增能带出名称，之后再新增就没有了**。

## 根因（同一个 bug）

`public/js/work_order.js` → `show_update_required_items_dialog()` 里，`item_code` 列的 `onchange`：

```js
onchange: function() {
    const me = this;
    const row_data = dialog.fields_dict.trans_items.df.data.find(
        (doc) => doc.idx === me.doc.idx        // ← this.doc 为空时这里直接抛 TypeError
    );
    if (me.value && row_data) {
        frappe.call({ method: 'erpnext.stock.doctype.item.item.get_item_details', ... });
    }
}
```

- Frappe 是从 `grid_row.js` 直接调 `df.onchange` 的，**`this.doc` 不保证存在**；为空时
  `me.doc.idx` 抛 `TypeError` → **后面那次 `get_item_details` 根本不会发出** → 名称留空。
- 回调里调了 **`grid.refresh()`（整表刷新）**，会重建网格里的字段对象 → 之后 `this.doc` 就没了
  → **"第一次能带出、再新增就不行"**。
- 后端 `overrides/work_order_override.py:update_required_items` 只是**原样接收前端传来的
  `item_name`**（`new_row["item_name"] = item["item_name"]`），不回查 Item 主数据
  → 前端空着，工单上存下来的「物料名称」就是空的。

## 修复（三处，都在 `public/js/work_order.js`）

| # | 位置 | 改动 |
|---|---|---|
| 1 | `item_code` 列的 `onchange`（约 583 行） | 整段包 `try/catch`（**再不抛错**）；行定位改为 `this.doc → grid.current_row.doc → 按 item_code 找最后一条没有名称的行`，逐级回退 |
| 2 | `primary_action`（约 720 行） | **提交前兜底**：把 `item_name` 还是空白的行用 `frappe.db.get_value('Item', code, 'item_name')` 补齐，再弹确认框 |
| 3 | `dialog.show()` 之后（约 760 行） | **事件驱动 + 轮询兜底（主力）**：不再依赖网格列自己的 `onchange`。① 在弹窗上委托监听 `change/blur`；② 点「添加行/删除行」后补一次；③ **弹窗存活期间每 400ms 扫一遍**，凡是「选了物料但名称还空着」的行都补上名称并只刷新该行单元格 |

第 3 条是主力：网格列的 `onchange` 实测**只在弹窗刚打开时生效一次**，之后再新增行就不触发了。

- 只挂 `change/blur` 不够：从 Link 下拉里选物料是**程序化赋值，不会触发 `change`**，
  要等你点到别处、输入框失焦才触发 `blur` —— 表现就是"名称迟到"。
- 所以加了**轮询**：与事件无关，选完物料最多 0.4 秒就带出来。
  轮询只在弹窗可见期间运行，弹窗关闭即 `clearInterval`。

第 2 条是关键保险 —— 无论前面有没有补上，**存进工单的名称都不会再是空的**。

## 文件

| 文件 | 说明 |
|---|---|
| `work_order.js` | 改好的完整文件（已部署到测试机，md5 `3303efe753b1fb79fc1eb1a32122437b` 归一化 LF 前；重传后按 LF） |
| `work_order_item_name_fix.patch` | 相对 HEAD 的 unified diff（2 个 hunk，68 insertions / 22 deletions） |

## 部署

- **测试机**：已部署（`apps/work_order_task/work_order_task/public/js/work_order.js`），
  `bench clear-cache` 已执行，改前原件备份在 `/tmp/work_order.js.bak_20260914`。
  改动前整文件与生产**逐字节相同**（md5 `c779975f796921a538a826840bba408c`）。
- **生产**：同样替换该文件 + `bench clear-cache`（JS 走 `sites/assets` 软链，不用 `bench build`）；
  浏览器需 `Ctrl+Shift+R` 硬刷新。

## 验证清单

1. Chrome 硬刷新后打开任一生产工单 → 「面料处理 → 变更物料」
2. 新增一行、选物料 → **名称应立刻带出**
3. **再连续新增两行**、各选物料 → **名称都应带出**（旧版这里是坏的）
4. F12 Console → **不应再出现** `Cannot read properties of undefined (reading 'idx')`
5. 点「确认变更」→ 工单 `required_items` 里 `item_name` 均非空

## 备注（与本次无关，但同属两机差异）

- 测试机 ERPNext `15.59.0` / 生产 `15.43.3`（Frappe 都是 `15.48.0`）
- 测试机多一个自定义字段 `custom_s_warehouse`（指定发料仓库），在 `Work Order Item` 上**生产没有**；
  而 `utils/stock_entry.py` 里用到它 —— 生产上这条分支值得单独核一下
