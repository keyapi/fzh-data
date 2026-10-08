---
okf: v0.1
type: Reference
title: key_test 应用的两个结构性隐患：每次登录写元数据 + 打核心报表猴补丁，且生产/测试分支割裂
date: 2026-10-08
category: docs/solutions/workflow-issues/
module: key_test
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "调查 ERPNext 上「每个用户每次登录都报错/弹窗」这类全站性问题"
  - "要改 key_test 应用（它不在统一 git 管理内，生产/测试分支割裂）"
  - "评审 key_test 的 hooks.py / setup.py / monkey_patches"
tags: [key_test, erpnext, on-session-creation, monkey-patch, hooks, prod-test-divergence, login]
---

# key_test 的两个结构性隐患

## Context

2026-10-08「两台 ERPNext 每个用户每次登录都弹窗」的事故：坏字段在 `work_order_task` 的 fixtures 里，但**让每个用户都撞上**的是 `key_test` —— 它把 `setup.after_migrate` 挂在 `on_session_creation` 上，每次登录都写 Item 的元数据，于是那个坏字段每次登录都被重新校验一遍。

事故根因链与处置见 `docs/solutions/integration-issues/layout-field-in-list-view-breaks-metadata-writes.md`。本文记录同一次调查里查到的、**尚未处置**的结构性隐患（已开 issue：`keyapi/key_test#1`）。

## 隐患 1：每次登录都写元数据

```python
# key_test/hooks.py（测试、生产两台一致）
on_session_creation = [
    "key_test.setup.after_migrate",
    "key_test.monkey_patches.report_patches.apply_all_patches",
]
```

`key_test.setup.after_migrate()` = `create_custom_fields(get_custom_fields(), update=True)` + `make_property_setter('Item', 'weight_template_variant', ...)`。

- 实测代价：**0.75 s/次（生产）、1.05 s/次（测试）**；
- 每次登录都重写 Item 的 Custom Field / Property Setter（旁证：`Item-weight_template_variant-*` 的 `modified` 跟着登录时间走，如 14:48:00）；
- 放大效应：`CustomField.on_update` / `PropertySetter.on_update` 都会 `validate_fields_for_doctype(self.dt)` → **该 doctype 只要有一个非法字段，全站每次登录都报错**（已经发生过）。

## 隐患 2：猴补丁核心报表，且模块导入时就执行

`key_test/monkey_patches/report_patches.py` 把 `erpnext.buying.report.requested_items_to_order_and_receive.execute` 直接替换成 `key_test.overrides...execute`，并在**文件末尾**这样收尾：

```python
try:
    if hasattr(frappe, 'local') and frappe.local:
        apply_all_patches()
except:
    ...   # 裸 except，吞掉一切
```

即「模块一被导入就执行补丁 + 裸 `except` 静默吞异常」。后果：

- 猴补丁**按进程生效**：只有导入过该模块 / 处理过登录的 worker 才被打上，重启后各 worker 行为不一致；
- 生产 v15.43.3 与测试 v15.59.0 版本不同，被替换的内部函数可能已经变了 → **静默失效，无人知晓**；
- 两台补丁内容本身也不一样（`report_patches.py` md5 不同；测试多一个已注释的 light_mes 补丁）。

**要摘掉登录 hook 前请注意**：补丁其实**不依赖** `on_session_creation` —— `key_test/__init__.py` 里就有
`from key_test.monkey_patches.report_patches import apply_all_patches` + `apply_all_patches()`，
任何进程导入 `key_test` 包（hooks 加载即导入）时就会打上；`report_patches.py` 末尾还有一段「导入时执行」。
`after_migrate` 里也已有同样的两条。所以那两条登录 hook 是**纯重复**，删掉不会让报表补丁失效。

## 隐患 3：生产/测试分支割裂（变更无法追溯）

| | 测试 | 生产 |
|---|---|---|
| 分支 @ commit | `main` @ `132c1d0` | **`production-backup`** @ `6543a3a` |
| commit 数 | 74 | 28 |
| py+js 文件数（去掉 .git/pycache） | 94 | 64 |
| `hooks.py` / `setup.py` | 与生产 md5 均不同 | 同左 |

生产缺测试上有的整块功能：`doc_events/`（batch、purchase_receipt）、`item.py`、`doctype/excel_processing`、`doctype/item_cost`、`report/bom_cost`、`report/bom_item_lead_time_days`、`overrides/light_mes` 等。

GitHub 仓库（`keyapi/key_test`，默认分支 `main`）最后推送是 **2026-07-22** —— 两台实际跑的都不是 GitHub 上那份。
⇒ **在测试系统验证通过，不代表生产行为一致**（与 `erpnext-version-api-compatibility.md` 同一类坑）。

### 补充：生产少的那些，实测影响多大

| 只测试有 | 生产状况 | 判定 |
|---|---|---|
| DocType `Item Cost` | 不存在（测试仅 1 行数据） | 试验 |
| DocType `Excel Processing` | 不存在（测试仅 2 行数据） | 试验 |
| `report/bom_cost/`（脚本报表目录） | 测试 DB 里连 Report 记录都没有 → 跑不起来 | 死代码（生产另有 Report Builder 的 “BOM Cost”） |
| `report/bom_item_lead_time_days` | 生产无（测试有 Script Report 记录） | 未上生产的真实差异 |
| `overrides/light_mes/*` | 测试里已注释（注释写「Light MES 已自修」） | 两边都不用 |
| `doc_events/batch.py`、`purchase_receipt.py` | 生产 `hooks.py` 里这两项**已注释**且文件不存在 | 一致、不会 ImportError；测试启用 |
| `item.py` | 测试 1 字节、生产缺失 | 无实质 |

结论：生产跑得正常，是因为差异集中在「试验件」与「生产主动禁用的项」。

### 这个 app 真正在做的功能（重量模板关联）

用户 2024 年的原始需求是「物料加字段 ↔ 重量模板自动关联」，落点是：

| 位置 | 作用 |
|---|---|
| `key_test/weight_template_utils.py` → `get_weight_template_variant()` | 按命名约定 `重量模板#{模板 item_name}` + 属性值匹配，找出物料的重量模板变体（whitelisted；同文件另有「已有物料批量回填」入口） |
| `key_test/doc_events/item.py:validate()` | 新物料保存时：若为变体且填了 `weight_template_variant`，从重量模板带出 `weight_per_unit`/`weight_uom`（缺重量时 alert） |
| `key_test/public/js/item_group.js` | 物料组页「批量」入口 → `key_test.batch_weight_template.start_batch_creation` |
| `setup.py` 那 4 条 Property Setter | 只把 `weight_template_variant` 设为「不进列表视图/不进标准筛选/不复制/提交后不许改」 |

**都与登录 hook 无关** —— 这也是判断「登录 hook 纯属多余」的依据之一。

## 建议（前两条各只改几行）

1. 把 `key_test.setup.after_migrate` 从 `on_session_creation` 摘掉（留在 `after_migrate` 就够）：去掉每次登录的元数据写入，也去掉这类事故的放大器，顺带每次登录省 ~1 s。
2. 报表补丁改用受支持的挂载点（`override_whitelisted_methods`，或直接改报表模块），去掉「导入时执行」与裸 `except:`；两台同版本各验证一次。
3. 分支归位：生产回到 `main`（或把 `production-backup` 合回 `main`），两台都 push 到 GitHub，确立可追溯真源；之后按 `CONTRIBUTING.md`「EN 自定义 app 的开发与发布流程」走。
4. 冒烟：改动后跑 `validate_fields_for_doctype("<它写过的 doctype>")` + `EN_API/check_layout_in_list_view.py`；生产另做一次真实登录确认不弹窗。

## 复现 / 测量

```bash
ssh <host> 'cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn console'
>>> import time; from key_test import setup
>>> t = time.time(); setup.after_migrate(); print("ELAPSED", round(time.time()-t, 2))
```

（该调用就是每次登录跑的那段，幂等；跑它等于复刻一次登录。）
