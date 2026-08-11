---
okf: v0.1
type: Solution
title: 面单创建报 "No dimensions available for package" — upsert_package_dims 主键/外键查询混淆
description: shipping_package_dims 写入用 session.get(按自增主键 id) 而读取用 filter(package_id)，package_id 撞上既有 dims 行 id 时错写别家行，目标包裹尺寸永不落库
timestamp: 2026-08-10
tags: [sellfox-shipping, label-service, package-dims, sqlalchemy, data-integrity]
---

# 面单创建报 "No dimensions available for package" — upsert_package_dims 主键/外键查询混淆

## 现象

包裹 `P2B4A9T731770` 创建面单时报 `面单创建失败: No dimensions available for package`。
`LabelService.preflight()`（[label_service.py](../label_service.py)）在 `get_package_dims(db_id)`
返回 `None` 时抛出该错误。

## 根因

`shipping_package_dims` 表有两个键：

| 列 | 含义 |
|---|---|
| `id` | 自增主键（serial） |
| `package_id` | 外键，`unique`，指向 `shipping_packages.id` |

`upsert_package_dims`（[package_repository.py](../package_repository.py)）写入时用了：

```python
row = session.get(PackageDimsRow, package_db_id)   # 按主键 id 查！
```

但 `package_db_id` 是**外键 `package_id`**，不是主键。两个数字在多数情况下不相等，导致：

1. `session.get(PackageDimsRow, package_db_id)` 命中 `id == package_db_id` 的那行 —— 它可能属于**另一个包裹**
2. 把当前包裹的尺寸值写进那行，但 `package_id` 不变 → **错写别家**
3. 当前包裹自己的 `package_id == X` 行**永远不会被创建**

读侧 `get_package_dims` 用的是正确写法 `filter(PackageDimsRow.package_id == package_db_id)`（此前
已修过一次，见 docs/log.md），所以写错后读回永远 `None`。

### 对 P2B4A9T731770 的实际发生

该包裹 `package_id = 2`。数据库里 `shipping_package_dims` 恰好存在 `(id=2, package_id=3073)`
（属于 `P2BAA9T734992`）。每次给包裹 2 写尺寸（详情页渲染 / 创建面单都会调 `upsert_package_dims(2)`）：

- `session.get(PackageDimsRow, 2)` → 命中 `id==2` 的 P2BAA9T734992 行
- 覆盖其尺寸值，`package_id` 保持 3073
- 包裹 2 永远没有 `package_id==2` 的记录 → 预检报错

## 修复

把写入改为按外键过滤（与 `get_package_dims`、`upsert_package_routing` 一致）：

```python
row = (
    session.query(PackageDimsRow)
    .filter(PackageDimsRow.package_id == package_db_id)
    .first()
)
if row is None:
    row = PackageDimsRow(package_id=package_db_id)
    session.add(row)
```

## 教训

1. **读/写两侧的查询键必须一致**：历史上只修了读侧 `get_package_dims`（`session.get` 按主键
   id 查改为 `filter(package_id==)`），写侧 `upsert_package_dims` 漏掉同步。修一类 Bug 时，
   要 grep 同模式的其他调用点。
2. **`session.get(Row, value)` 是按主键查**：`PackageRepository` 里大量 `session.get(IntentRow,
   intent_id)` 是正确的（intent_id 就是主键），但一旦传的是外键值（如 `package_db_id`），
   `session.get` 就会按主键 id 匹配到错误行。按外键查询一律用
   `session.query(Row).filter(Row.fk == value).first()`。
3. **静默吞错掩盖数据问题**：`_compute_package_dims` 里 `upsert_package_dims` 包在
   `try/except Exception: pass`（best-effort），写失败不会报错，只在面单创建时才暴露
   数据缺失。宁可保留日志也不要静默。

## 验证

- 新增回归测试 `test_upsert_package_dims_keys_by_package_id_not_row_id`：构造 id/package_id
  碰撞，断言两个包裹尺寸各自独立正确（有 bug 时 FAIL，修复后 PASS）。
- 新增 `test_upsert_package_dims_updates_existing_row_in_place`：重复 upsert 不产生重复行。
- 全量 `tests/sellfox_shipping`：**302 passed, 2 warnings**。
- 数据修复：重新计算 `P2B4A9T731770`（3.6kg, 66×56×5cm）与 `P2BAA9T734992`（4.98kg,
  76×56×7.8cm）尺寸；前者从此有记录，后者从我诊断时误写的值还原。
- `LabelService.preflight(package=P2B4A9T731770, carrier=lizard)` → `PREFLIGHT OK`。
