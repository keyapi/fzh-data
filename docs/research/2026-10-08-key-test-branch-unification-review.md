---
type: Research
title: key_test 生产线 vs 测试线 逐文件评审清单（合并到新 main 前的取舍表）
description: 生产线(production-backup) 与测试线(main) 分叉已久；22 个双边都改的文件按「纯格式 / 测试侧变薄(功能已搬到别 app) / 测试侧领先 / 需人工看」分档，附体量、最后改动、证据与待决策点
---

# key_test 生产线 vs 测试线：逐文件评审清单

> 2026-10-08。母文档：`docs/solutions/workflow-issues/key-test-login-hook-and-prod-test-divergence.md`（隐患 3 / 评估）。
> 目的：为「以生产为基线建 main-new、再把测试侧仍需要的改动 port 过去」提供可直接过会的清单。

## 数据来源与方法

本地 `git clone --bare git@github.com:keyapi/key_test.git`（含全部 GitHub 分支）后：

- 生产线已补齐并推送：`production-backup` @ `c87759a`（含本次 `on_session_creation` 修复）；测试线备份为 `backup/test-main-20261008` @ `132c1d0`。
- 分叉度量：`git rev-list --left-right --count production-backup...backup/test-main-20261008` → 生产独有 **28** / 测试独有 **73**；共同祖先仅 1 个旧提交（`33b7012`）。
- 区分「格式噪声 vs 真实改动」：用 `git diff --ignore-all-space --numstat`；输出 `0/0` 的判为纯格式。
- 功能是否已迁走：在 `work_order_task`（GitHub `keyapi/work_order_task` @ main）里反查同名函数。

## 全局结论

- 两棵树：**41 个文件只在测试**、**22 个两边都改过**、**0 个只在生产**。
- **不能机械二选一**：22 个里至少有 2 个是「测试侧删掉了本地实现、改成引用 `work_order_task`」，若取生产侧会把已迁走的功能又抄一份回来；另有若干文件测试侧已加改进。
- 测试侧独有的 41 个文件里，约 20 个是试验件、约 11 个是 QR/批号功能的「另一套实现」。

## 分档表（22 个双边都改的文件）

### A. 纯格式差异 —— 取任一侧即可（建议生产侧，零风险）· 3 个

| 文件 | 依据 |
|---|---|
| `key_test/doc_events/work_order.py` | 忽略空白后 diff 为 0 |
| `key_test/key_test/doctype/logistic_price_list/logistic_price_list.json` | 同上 |
| `key_test/key_test/report/bom_cost_list/bom_cost_list.json` | 同上 |

### B. 测试侧「变薄」—— 生产侧代码更多，但可能是历史遗留 · 6 个

| 文件 | 生产行/测试行 | 生产侧独占的最后改动 | 说明 |
|---|---|---|---|
| `key_test/production_utils.py` | 1973 / 627 | 2025-08-20 修正…删除没用的引用 | **已证实**：测试侧 import 了 `work_order_task`，把本地实现删掉了 |
| `key_test/overrides.py` | 629 / 76 | 2025-08-14 | **已证实**：生产侧那份是 ERPNext Work Order / Production Plan 的方法猴补丁（`make_work_order`、`get_sub_assembly_items`…），这些现在在 `work_order_task/work_order_task/overrides/production_plan_override.py`（测试侧只留 1 个函数） |
| `key_test/bom_cost_updater.py` | 567 / 338 | 2025-08-14 | 待确认（`work_order_task` 里没找到同名实现） |
| `key_test/add_item_semi.py` | 556 / 392 | 2025-11-21 | 两边同一天同名提交（手工拷贝同步的痕迹）；两侧顶层 def 数相同(6)，差在函数体 → 需逐段比对 |
| `key_test/public/js/item_group.js` | 298 / 191 | 2025-08-14 | 待确认 |
| `key_test/bom_utils.py` | 637 / 554 | 2025-08-14 | 待确认 |

> **B 档的判定口径**：先问「这段代码是不是已经搬去 `work_order_task`/`light_mes` 等 app」——
> 是 → 取测试侧（薄版，避免双份维护）；否 → 才考虑保留生产侧并排期搬迁。

### C. 测试侧领先/更全 —— 逐个 review 后 port · 12 个

| 文件 | 生产→测试 | 要点 |
|---|---|---|
| `key_test/hooks.py` | +79/-22 | 含本次 `on_session_creation` 修复；其余差异是测试侧启用了 `doc_events` 的 Batch / Purchase Receipt 等 |
| `key_test/setup.py` | +69/-62 | 测试侧多 QR 相关字段（`qrcode_section`/`qrcode_image`/`qrcode_display`/`batch_qrcode_image`）——与生产侧走 `erpnext_qrcode` app 是**两套实现**（见决策 1） |
| `key_test/key_test/report/work_order_merge_same_material.py` | +641/-944 | 大幅重写，需人工比对（测试侧 2025-07-29「测试修改EN原生报表」） |
| `key_test/key_test/report/work_order_merge_same_material.js` | +147/-11 | 同上 |
| `key_test/sales_order_utils.py` | +47/-0 | 测试侧新增的是**注释掉的死代码**（`# def get_sales_orders_with_items()`）→ 可不带 |
| `key_test/monkey_patches/report_patches.py` | +23/-0 | 测试侧多 light_mes 补丁（已注释）→ 可不带 |
| `key_test/key_test/doctype/logistic_price/logistic_price.js` | +31/-0 | 物流价格表单扩展 |
| `key_test/commands/__init__.py` | +19/-5 | 测试侧多 `setup_weight_template_fields(site=None)`（重量模板字段的站点安装助手） |
| `key_test/api/batch_qrcode.py` | +12/-0 | QR/批号两套实现的一部分（决策 1） |
| `key_test/item_alternative.py` | +1/-0 | 1 行 |
| `key_test/key_test/doctype/logistic_price/__init__.py` | +1/-0 | 1 行 |
| `key_test/key_test/doctype/logistic_price_list/__init__.py` | +1/-0 | 1 行 |

### D. 两边都改、体量相同 —— 人工看 · 1 个

| 文件 | 生产→测试 | 说明 |
|---|---|---|
| `key_test/public/js/bom_list.js` | +33/-33 | 356/356 行，改动量对称，非空白差异 |

## 测试侧独有的 41 个文件（分类）

| 类别 | 约数 | 处置建议 |
|---|---|---|
| QR / 批号功能一套（`qr_utils/`、`doc_events/batch.py`、`doc_events/purchase_receipt.py`、`commands/*qrcode*`、`public/js/purchase_receipt_qrcode.js`、`public/qrcodes/`） | ~11 | **两套实现二选一**（决策 1） |
| 试验/未启用（`doctype/excel_processing`、`doctype/item_cost`、`report/bom_cost`、`overrides/light_mes`） | ~20 | 不带（`report/bom_cost` 在测试 DB 里连 Report 记录都没有；`light_mes` 补丁已注释；`item_cost` 1 行数据、`excel_processing` 2 行数据） |
| 文档与生成物（`file_structure.md`、`key_test/README.md`、`docs/bom_cost_excel_cost_logic_for_claude.md`、`update_file_structure.sh`、`item.py`、`www/__init__.py`） | ~6 | 文档可留；`file_structure.md` 建议 gitignore（脚本产物） |
| 真实功能但仍少用（`report/bom_item_lead_time_days`） | ~3 | 需你定是否上生产 |
| fixtures（`fixtures/custom_field.json`、`fixtures/property_setter.json`） | 2 | 见下方事实 3 |

## 必须先定的三个决策

1. **QR / 批号功能留哪套？** 测试侧 = `setup.py` 加字段 + `qr_utils/` + `doc_events/batch|purchase_receipt` + `commands/*qrcode*`；生产侧 = 装 `erpnext_qrcode` app + `api/batch_qrcode.py` + `public/js/purchase_receipt_qrcode.js`。两套并存会互相打架（字段/钩子重复）。
2. **B 档里哪几个真的已经在别的 app 里实现了？**（已证实 `production_utils.py`、`overrides.py`；`add_item_semi.py`、`bom_cost_updater.py`、`bom_utils.py`、`item_group.js` 待确认）→ 建议问 Jack（他维护 `work_order_task`）。
3. **已搬到别处的功能，key_test 里还留不留一份？** 建议不留（双份维护 = 这次分叉的根因）。

## 核对过的事实（避免重复调查）

1. **测试侧 `key_test/fixtures/custom_field.json` 只含 Purchase Receipt 字段**，不含 2026-10-08 弹窗事故的那 6 个字段 → 弹窗修复**不会**因 key_test fixtures 复发（复发源是 `work_order_task` 的 fixtures，已修并合并）。
2. 生产侧 `key_test/fixtures/` 目录是空的，但 `hooks.py` 里声明了 fixtures → `bench migrate` 时是 no-op（无害，但也意味着生产这些字段只靠 `after_migrate` 钩子安装）。
3. 生产 remote 是 HTTPS 且服务器上无凭证 → `git push origin` 会卡 `could not read Username`；本次用显式 URL `git push git@github.com:keyapi/key_test.git <branch>` 推成功。切新 main 时建议把 remote 改成 SSH。
4. 测试机上 `file_structure.md` 常驻未提交改动（`update_file_structure.sh` 的产物）——2026-10-08 差点被卷进我的提交，已拆出。
