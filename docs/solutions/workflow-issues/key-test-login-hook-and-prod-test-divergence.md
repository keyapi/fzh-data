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

事故根因链与处置见 `docs/solutions/integration-issues/layout-field-in-list-view-breaks-metadata-writes.md`。本文记录同一次调查里查到的结构性隐患，以及 2026-10-08 已执行的处置（见「处置记录」）与分支归位方案（见「评估」）。

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

**2026-10-08 实测（`keyapi/key_test`，私有）：**

| | 测试线 | 生产线 | GitHub `main` |
|---|---|---|---|
| 分支 @ commit | `main` @ `132c1d0` | `production-backup` @ `c87759a` | `main` @ `2612db4` |
| commit 数 | 74 | 28（**全部为生产独有**） | — |
| 与别的线的关系 | 与 GitHub main 只差 1–2 个提交（≈ 同一条线） | 与测试线**分叉**（共同祖先只有一个 2025-08 前的提交） | 最后推送 2026-07-22 |

- `git rev-list --left-right --count production-backup...test-main` → 生产独有 **28** 个提交 / 测试独有 **73** 个。
- 两棵树差异：**41 个文件只在测试**、**22 个两边都改过**、0 个只在生产（生产没有测试缺的文件）。
- 生产那 28 个提交是**真实的生产侧修复**（BOM Cost List 的一连串改动、销售订单 Excel 导入、物料批号管理、一键完工…），其中多条提交名直接写着「**复制测试系统代码 / 手动复制测试系统代码**」——说明生产是用**手工拷贝文件**的方式同步的；线本身起于 `213a0ed 生产环境代码备份，合并之前 20250814`。
- ⇒ **两条线都含真实工作，且已分叉**：「测试系统验证通过」不代表生产行为一致（与 `erpnext-version-api-compatibility.md` 同一类坑）。

### 评估：以生产为基线建新 main —— 结论是可行的，但必须做「逐文件评审」这一步

**为什么以生产为基线**：① 生产是用户实际在跑的，行为已验证；② 生产没有测试缺的文件，反向以测试为基线会丢掉生产侧在 22 个核心文件里的改动；③ 测试侧独有的 41 个文件里多是试验件（见下）。

**但不要整树覆盖**：那 **22 个两边都改过**的文件（`hooks.py`、`setup.py`、`report_patches.py`、`production_utils.py`、`bom_cost_list` 报表、`sales_order_utils.py`…）是双方意图交汇处，直接任选一边都会**静默丢掉另一边的工作**。必须逐文件评审、只挑仍需要的改动 port 过去。

**建议执行顺序**（先备份，任何一步都可回退）：

1. 备份（已完成 2026-10-08）：测试线 → `backup/test-main-20261008`；生产线补推齐 → `production-backup` @ `c87759a`（含本次登录 hook 修复）；建议再给 GitHub `main` 打 `backup/github-main-20261008`（`2612db4`）。
2. 建 `main-new` = `production-backup` 的树（含本次 fix）。
3. **逐文件评审 22 个 M 文件**（test → main-new），只把仍需要的改动 port 过去。其中 `doc_events/batch.py`、`doc_events/purchase_receipt.py`（测试启用、生产 hooks 已注释）与 `report/bom_item_lead_time_days` 是「测试在用、生产没有」的少数真实功能，需明确要不要上生产；`Item Cost`、`Excel Processing`（试验）、`report/bom_cost`（测试 DB 里连 Report 记录都没有的死代码）、`overrides/light_mes`（已注释）建议不带。
4. 两台切到 `main-new`：
   - **测试**：`git checkout main-new && git pull` —— 会**删掉** 41 个 test-only 文件；若第 3 步没把 `doc_events/batch.py`、`purchase_receipt.py` 带过来，测试的 hooks 里那两项必须同步注释，否则 Batch / Purchase Receipt 保存会 ImportError。
   - **生产**：先把 remote 从 HTTPS 改成 SSH（`git remote set-url origin git@github.com:keyapi/key_test.git`），否则 `git pull` 每次都被凭证挡住（2026-10-08 实测：`git push origin` 报 `could not read Username`，只能用显式 URL `git push git@github.com:keyapi/key_test.git <branch>` 推）。
5. GitHub `main` 指向 `main-new`（旧 main 留备份分支），之后走标准流程：测试分支 → 验证 → 合并 main → push → 生产 `git pull` + `migrate` + `clear-cache` + `restart`。
6. 顺手：`file_structure.md` 是 `update_file_structure.sh` 的产物（测试机上常年有未提交的整文件改动，极易被误提交——本次差点被带进提交），建议 gitignore 或只在需要时提交。

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

## 处置记录（2026-10-08，两台已执行并验证）

**改动**：`hooks.py` 里 `on_session_creation = [...]` → `on_session_creation = []`（附原因注释）；`after_migrate` 保持不动。
测试提交 `20e26bd`（分支 `fix/remove-on-session-creation`，已推）；生产提交 `c87759a`（`production-backup`，已推）。

**验证**（改前 → 改后）：

| 指标 | 测试 | 生产 |
|---|---|---|
| 登录耗时（热进程 4 次） | 1.15–1.32 s → **0.12–0.29 s** | 0.59–0.81 s → **0.11–0.19 s** |
| 登录是否重写 Item 的 4 条 Property Setter | 是 → **否**（`modified` 停在改前时刻） | 是 → **否** |
| 猴补丁是否仍生效 | 是（`bench restart` 后 web.log 新增 14 行补丁标记，**无任何登录**） | 是（+15 行） |
| web 进程里的 hook 配置 | `on_session_creation` 只剩 Frappe/ERPNext 自带 3 条 | 同左 |

## 建议

1. **已完成**（见上）：停用 `on_session_creation`。
2. 报表补丁改用受支持的挂载点（`override_whitelisted_methods`，或直接改报表模块），去掉「导入时执行」与裸 `except:`；两台同版本各验证一次。（现在它靠 `key_test/__init__.py` 导入时打，能用但不体面）
3. **分支归位**：见上面「评估：以生产为基线建新 main」的执行顺序。
4. 冒烟：改动后跑 `validate_fields_for_doctype("<它写过的 doctype>")` + `EN_API/check_layout_in_list_view.py`；生产另做一次真实登录确认不弹窗。

## 复现 / 测量

```bash
ssh <host> 'cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn console'
>>> import time; from key_test import setup
>>> t = time.time(); setup.after_migrate(); print("ELAPSED", round(time.time()-t, 2))
```

（该调用就是每次登录跑的那段，幂等；跑它等于复刻一次登录。）
