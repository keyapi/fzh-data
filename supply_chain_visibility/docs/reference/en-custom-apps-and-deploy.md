---
okf: v0.1
type: Reference
title: EN 自定义 app 拓扑与「改单据/报表」落地链路
description: ERPNext(生产) 上有哪些自定义 app、SO 表单定制与 Script Report 各放哪、发布/缓存/重启的完整链路与实测坑
date: 2026-10-13
category: reference
module: supply_chain_visibility
tags: [erpnext, frappe, custom-app, key_test, light_mes, hooks, fixtures, script-report,
       deploy, bench-restart, clear-cache]
---

# EN 自定义 app 拓扑与落地链路

> 记录「在 EN 上加一个 SO 表单区块 / 一个报表」这件事**具体怎么落地**，以及 2026-10-13 实测踩到的坑。

## 1. app 拓扑（各自独立仓库）

自定义 app 是**各自独立的 GitHub 仓库**（组织 `keyapi`），源码在各服务器 `frappe-bench/apps/<app>/`。

| app | 作用 | 备注 |
|---|---|---|
| **`key_test`** | **house app**（SO/Item 定制主战场） | 分支割裂例外，历史曾生产/测试分叉（2026-10-08 统一到 `main`） |
| `light_mes` | 车间 MES | `Initial Work Order`、`Tracking Number`、`Job Card Scan Input`、`Wip Transfer`… |
| `work_order_task` | 工单任务 | `Cutting Plan/Task`、`Work Order Split`（生产未用） |
| `delivery_plan` | 出货计划 | `Delivery Plan`、`Outer Box Number` |
| `tongtool_integration` | 通途/平台 | `Tongtool Order/Package` |
| `vilavi_pim` | PIM | 物料组/属性 |

**SSH**：生产 `阿里云-FZH-ERPNext-frappe`、测试 `上海测试-阿里云-FZH-ERPNext-frappe`（见 `EN_API/docs/reference/en-server-access.md`）。
两台 bench 都在 `/home/frappe/frappe-bench`；**测试机的站点目录也叫 `erpnext.vilavi.cn`**（别重启错 bench）。

## 2. 三种「改 EN」的落点

| 要加的东西 | 放在哪 | 关键点 |
|---|---|---|
| 单据**自定义字段** | app 的 **fixtures**（`fixtures/custom_field.json` + `hooks.py` fixtures 白名单）或 `setup.py`/`after_migrate` | 必须走 fixtures/迁移，否则生产不会有该字段；**勿跑 `export-fixtures` 整份重写** |
| 单据**表单 JS** | `hooks.py` 的 `doctype_js = {"Sales Order": "public/js/sales_order.js"}` + `public/js/*.js` | **每个 doctype 只允许一个文件**；Frappe 允许对同一 doctype 多次 `frappe.ui.form.on(...)`，故新逻辑要**追加**进该文件 |
| **Script Report** | `<app>/<module>/report/<name>/<name>.{py,json,js}` | 见 §3 路径陷阱 |

**服务端取值**统一用 `@frappe.whitelist()` 方法（如 `key_test.so_chain.get_so_chain`）；JS 用 `frappe.call` 调，**不要**让前台直连外部服务。

## 3. 实测的两个大坑（2026-10-13）

1. **Script Report 路径要「多一层 module」**：Frappe 的 report 路径 = `<app>.<module>.report.<name>.<name>`；
   当**模块名 == app 名**（`key_test`）时，磁盘路径是 `apps/key_test/key_test/**key_test**/report/<name>/`。
   放少一层，Frappe 找不到 → `bench migrate` 会**悄悄生成一个返回 `([],[])` 的桩文件**，
   现象是「报表端点返回 0 行、耗时 ~0」，很难查。
2. **改/加 `.py` 后必须 `bench restart`** —— `clear-cache` **不重载 Python 模块**。
   同上，现象也是端点返回 0 行。JS 改动只需 `clear-cache` + 浏览器硬刷新（清 `localStorage` 的 `_doctype:<dt>`）。

## 4. 发布链路（`CONTRIBUTING.md`）

```
① 测试系统给 app 建分支 → 改 → 提交
② 测试验证：bench --site erpnext.vilavi.cn migrate / clear-cache（必要时 restart）
③ 合并 main → git push
④ 生产：git pull → bench --site erpnext.vilavi.cn migrate && clear-cache && bench restart
⑤ 极少数要 sudo reboot
```
- 生产该 app 的 git 远端名是 **`upstream`**（不是 origin）。
- **不要**拿本地 clone → 直接 PR 代替 ①②：fixtures/patch/after_migrate 的效果**只有 migrate 才暴露**。

## 5. 其它已知坑

- **布局类字段带 `in_list_view=1` 会锁死整个 DocType 的元数据写入**（曾致两台全站每次登录弹窗）
  —— 见 `docs/solutions/integration-issues/layout-field-in-list-view-breaks-metadata-writes.md`。
- **生产不跑 `bench setup requirements`** → app 新增 pip 依赖不会自动装，要定向 `env/bin/pip install`。
- **`key_test` 有历史猴补丁/登录钩子**（`monkey_patches/report_patches.py` 等），改动时留意。
- **REST 用专用 API 账号**（`EN_API/.env` 的 `ERP_API_KEY/SECRET`），**勿用 System Manager 密钥**。

## 6. 移植到别的 app（本次产物）

本次 Stage 1/2 产物暂放 `key_test`，移植到别的 app 只需三件事：
1. 把 `so_chain.py` / `report/so_chain_overview/` 放到目标 app 的同名模块下；
2. 把表单 JS 追加进目标 app 的 `doctype_js` 所指文件（或改 hooks 指向）；
3. 若跨 app，`frappe.call` 的方法路径 `key_test.so_chain.get_so_chain` 要改成目标 app 的路径；
   Report 记录的 `module` 字段同步改。**加/改 .py 后 `bench restart`。**
