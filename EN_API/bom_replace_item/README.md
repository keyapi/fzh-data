# BOM「替换面料」按钮 —— 实现与上线说明

把原来每次要跑控制台脚本的"换面料"操作，做成 BOM 表单上的一个按钮。

- **已在测试机 `ensh.vilavi.cn` 实现并验证通过**（2026-09-14）
- 生产 `erpnext.vilavi.cn` 需要 EN / 应用方按下面步骤部署

---

## 1. 功能

BOM 表单 → 按钮「替换面料」→ 弹窗选「旧物料 / 新物料」→ 只替换**当前这张 BOM** 的 `items` 子表里匹配的行。

- **「旧物料」下拉只列本 BOM 子表里出现过的物料**（去重），不再把全库物料都拉出来
  （`get_query: () => ({ filters: { name: ['in', bom_item_codes] } })`，`bom_item_codes` 取自 `frm.doc.items`）；
  输入时在这个范围内再做文本搜索。BOM 子表为空时直接提示、不弹窗。
- 「新物料」仍是全库物料下拉（不受限制）。

每个命中行会改：

| 字段 | 取值 |
|---|---|
| `item_code` | 新物料 |
| `item_name` | 新物料主数据（不手填，避免写错） |
| `description` | 新物料主数据（新料该字段为空时保留原值） |
| `image` | 新物料主数据（新料无图时保留原值） |
| `rate` | **按本 BOM 的 `rm_cost_as_per` 重新取价**（Valuation Rate / Price List / Last Purchase Rate） |
| `amount` / BOM `raw_material_cost` / `total_cost` 等 | 随之重算 |

`qty`、`uom`、`conversion_factor` 不变。

### 校验 / 边界
- `old_item == new_item`、新料不存在、新料已停用 → 拦截
- **新旧物料的 `stock_uom` 不一致 → 整单中止**（避免把"米"的用量当成"个"）
  - 判据用的是**新旧物料的 stock_uom**，不是 BOM 行的 `stock_uom`
    —— 后者可能是历史脏数据（测试机上就有 `uom=米, stock_uom=个` 的行），
    ERPNext 的 `validate() → set_default_uom()` 会自己纠正
- 命中 0 行 → 不做任何写入，只提示
- 多行命中 → 全部替换并逐行列出
- 已在内存改完最后一次性落库；中途异常不会留下半成品

---

## 2. 代码位置 / 改动

都在 `work_order_task` 应用里，**两个文件，不需要改 `hooks.py`**
（`hooks.py` 里本来就已有 `doctype_js = {"BOM": "public/js/bom.js"}`；
`sites/assets/work_order_task` 是指向该 app `public/` 的软链，改完 JS 立即生效，不用 `bench build`）。

| 文件 | 改动 |
|---|---|
| `work_order_task/work_order_task/utils/bom.py` | **追加** `replace_bom_item(bom_name, old_item, new_item)`（`@frappe.whitelist()`） |
| `work_order_task/work_order_task/public/js/bom.js` | `refresh` 里加一个「替换面料」按钮；文件末尾加 `replace_bom_item_dialog(frm)` |

> 路径说明：该 app 的 Python 包是套了两层的
> `apps/work_order_task/work_order_task/work_order_task/utils/bom.py`
> 对应导入路径 `work_order_task.work_order_task.utils.bom`（和现有
> `...utils.routing`、`...utils.bom.copy_bom_for_supporting_items` 一致）。

本目录里的 `bom.py` / `bom.js` 就是**测试机上已部署的完整文件**（可直接对比取差量）。

### 上线步骤（生产）
1. 把上面两个文件放到生产 app 对应路径（`bom.py` 是追加，`bom.js` 是两处插入；建议直接以本目录文件覆盖，二者与测试机 md5 一致）
2. `bench --site erpnext.vilavi.cn clear-cache`
3. `bench restart`（Python 改动需要重启，gunicorn `--preload` 有缓存；JS 是软链不用 build）
4. 浏览器硬刷新（`Ctrl+Shift+R`），打开任意 BOM 应能看到「替换面料」按钮

### 回滚
测试机上改前的原件已备份为 `bom.py.bak_20260914` / `bom.js.bak_20260914`，
生产部署前也请先备份同样两个文件。

---

## 3. ⚠️ 关键坑（实测踩到的，务必保留 update_cost 那一行）

**只 `save()` 不会刷新单价。**

ERPNext v15.43.3 `calculate_rm_cost()` 里是：

```python
for d in self.get("items"):
    old_rate = d.rate
    if not self.bom_creator and d.is_stock_item:
        d.rate = self.get_rm_rate({...})
```

实测：把 BOM 行的 `item_code` 从 `DMML1010-CHEEKRED-150-320`（解析价 14.5）
换成 `DMML1010-ANTHRACITE-150-320`（解析价 15.4）之后 `save()`，
该行的 `rate` **仍然停在 14.5**，`raw_material_cost` 也没变。

必须显式调用 ERPNext 自己的 `bom.update_cost()` 才会真正重取单价并重算成本：

```
替换后（仅 save）:  row1 rate=14.5   raw=30.03    ← 错的
再调 update_cost:   row1 rate=15.4   raw=31.812   ← 对的
```

所以方法里是 `save()` → `update_cost(update_parent=False, from_child_bom=True, update_hour_rate=False)`。

- `update_parent=False`：**只动这一张 BOM**，父级 BOM 的成本不跟着级联。
  这与用户选定的范围（"只改当前这张 BOM"）一致；
  ERPNext 原生「更新成本」按钮默认是级联的，若要级联把这里改成 `True`。
- `from_child_bom=True`：只为压掉 ERPNext 那句 "成本已更新" 的 msgprint，无其他副作用。
- `update_hour_rate=False`：不动工序的工站费率（本功能不涉及工序）。

---

## 4. 测试机验证记录（2026-09-14）

| 用例 | 结果 |
|---|---|
| 已提交 BOM `BOM-PK#KS0001-DM-120-RED-001-1`：CHEEKRED(14.5) → ANTHRACITE | rate → **15.4**，raw 30.03 → 31.812，total 38.84 → 40.622 ✅ |
| 同单据还原 ANTHRACITE → CHEEKRED | item_code / item_name / description / rate / 成本 **与改前快照逐项一致** ✅ |
| 草稿 BOM `BOM-PK#KS0001-DM-140-BLUE-001`：BLUE(15.4) → CHEEKRED | rate → **14.5**，raw 35.072 → 33.11 ✅ |
| 同单据还原 | 逐项与改前一致，`docstatus` 仍为 0 ✅ |
| 方法探针（不存在的 BOM） | 正确抛出「BOM 不存在」，异常来源标记 `work_order_task (app)` ✅ |
| 「旧物料」下拉收窄 | `frappe.client.get_list(Item, filters=[["name","in", <本BOM物料>]])` 只返回该 BOM 的 2 个物料；叠加文本搜索后进一步收窄为 1 个 ✅ |
| `bom.js` 发布检查 | `/assets/work_order_task/js/bom.js` 200，含「替换面料」按钮 ✅ |
| 遗留检查 | 测试机无遗留 `zz_*` Server Script ✅ |

测试期间临时改过的两张测试 BOM 都已还原；测试机 `utils/bom.py.bak_20260914`、
`public/js/bom.js.bak_20260914` 为改前备份。

---

## 5. 已知取舍 / 后续可议

- **权限**：按用户选择，任何对 BOM 有写权限的人都能按（按钮非新建可见，服务端再校一次写权限）。
  若要收紧，可在 `bom.js` 的 `refresh` 里加 `frappe.user.has_role(...)` 判断，
  并在 `replace_bom_item` 里加 `frappe.only_for([...])`。
- **不收 `scrap_items`**：只处理 `items` 子表（与需求一致）。
- **不级联父级 BOM**：见上面 `update_parent` 说明。
- 旧的控制台脚本方式仍可用于批量场景；本按钮是"打开一张 BOM、点一下"的场景。
