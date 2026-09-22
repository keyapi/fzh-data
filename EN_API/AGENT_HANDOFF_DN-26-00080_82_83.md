# AGENT HANDOFF — DN-26-00080 / DN-26-00082 / DN-26-00083 缺货修复（SO-26-00097）

> ## ⚠️ 新会话开工前必读（用户反复强调）
> 1. **不要新建 worktree、不要新建分支**。所有读写 / git 操作都用**主检出绝对路径**
>    `D:\Claude Demo\fzh-data`（本模块 `EN_API\`），产物也落在这里，**不要放 `.claude\worktrees\<名字>\`**。
> 2. 若本会话被告知"当前在 git worktree"：**不要 `EnterWorktree`**，直接用主检出绝对路径工作即可（产物不会丢）。
> 3. **git 操作（commit / push / 建分支 / 开 PR）必须先经用户同意**。
> 4. **生产系统**：默认只读。要写生产必须先 dry、把清单给用户确认；临时脚本统一 `zz_` 前缀，用完即删并复查残留 0。

## 一、当前状态（2026-09-21）

**任务已完结**。同一张销售订单 **SO-26-00097** 下的三张出库单：

| DN | 出货计划 | 状态 | DNS 提交口径库存校验 |
|---|---|---|---|
| DN-26-00082 | 2609007-1 | **已提交**（同事操作，docstatus=1） | 提交前 0 缺口 |
| **DN-26-00080** | 2609006 | **草稿，已修好待提交** | **0 缺口（39 组全过）** |
| **DN-26-00083** | 2609008 | **草稿，已修好待提交** | **0 缺口（36 组全过）** |

- 件数 / 金额 / 净重 / bom 成本 **全部保持不变**（00080：440 件；00083：458 件）
- 生产上无 `zz_` 临时脚本残留（已复查为 0）

## 二、根因（与前两次 DN-26-00078/00079 同源，但多了第二个问题）

1. **主因**：菲号的 `Tracking Number.finished_product_work_order`（fp_wo）为空
   → 出货计划提交时 `_create_manufacture_for_finished_goods` **静默 return** → 成品入库跳过 → 成品仓无货。
   本次 00080 的 20 个菲号 / 00083 的 30 个菲号全部或部分为空。
   （菲号命名形如 `WO-26-028xx-00N`，即"皮壳工单 + 序号"式，与老单的随机串不同）
2. **新增问题**：**三张单共用同一批菲号**，合计需求超过菲号实际产出（`Tracking Number.qty`），
   即**同事重复扫码**导致。三单合计超出 **229 件**。
   含跨单竞争：A 单提交出库后，B 单同一菲号的可用量立刻减少（DN 校验按 SLE 的
   物料+仓库+跟踪单号维度，**多张单共享同一个池子**）。

## 三、本次在生产做的动作（全部已落库）

### 1. 前段（00082 + 00083）
- 回填 fp_wo **35 条**
- 带菲号投产 Manufacture **35 张**（`STE-26-15650` ~ `STE-26-15684`），单价来自系统自己的
  `_build_manufacture_stock_entry`（`from_bom + bom_no + set_stock_entry_type + get_items`）
- 无菲号投产 **9 张**（`STE-26-15685` ~ `STE-26-15693`）
- 调拨 **6 条全部失败**：ERPNext 报"仓库数量还缺 N"——原因是 **Bin 与 SLE 不一致**（见第七节）

### 2. 后段（00080/00083 按用户新方案改行）
用户决定的做法：**带菲号行只保留"成品仓现有"的数量（不投产），超出部分新增无菲号行（外箱号照抄）**。

- 无菲号投产 **15 张**（`STE-26-15695` ~ `STE-26-15709`，453 件）
- 手工入库 **2 张**：`STE-26-15694`（6 行 / 52 件 / 2387.60）、`STE-26-15710`（2 件 / 92.19）
  - 均按 `Item.valuation_rate` 填单价、**无跟踪单号**、收进「成品仓 - FZH」
  - **是无来源入库（不结转成本）**，与前两次一致 → 需财务知悉
- **改行**（`EN_API/dn_0080_83_edit_rows.py`）：
  - 00080：132 → **141** 行，带菲号保留 **89 件**，287 件转无菲号
  - 00083：132 → **138** 行，带菲号保留 **198 件**，126 件转无菲号
  - 数量跨界的那行：改小原行数量 + **紧随其后插入一条无菲号行**（`carton_group` /
    `outer_carton_no` 等字段照抄，已抽查核对）
  - 成本/重量字段不用手工算：**Delivery Note 的 `before_save` 钩子会自动重算**
    （`update_bom_cost_info` / `update_dn_item_cost_info` / `update_incoming_cost_info`）

## 四、验证（只读）

- **DN 提交口径**：按 `SUM(SLE.actual_qty)` 分组 (物料, 仓库, 跟踪单号) 逐组比对
  → 00080 39 组全过、00083 36 组全过
- **守恒**：两单的 `total` / `grand_total` / `total_net_weight` / `total_bom_cost` **改前改后完全一致**
- **成本口径对照**：本次凭证与 00078 那次已验收的凭证数值一致
  （例：出 83.64 / 入 108.04 与 `STE-26-15508` 完全相同 → 那个"溢价"是本环境 Manufacture 的固有形态）

## 五、⚠️ 两个操作失误与修复办法（重要经验）

1. **Server Script 的 `dry` 标记没生效** —— 传了 `dry=1` 但服务端仍执行了 `dn.save()`，
   所谓"dry-run"**实际写了生产**。教训：生产上的 dry 不能只靠自己的约定，要校验
   "改前/改后是否真的没变"，或让 dry 分支根本不碰 `save()`。
2. **拆行时把"保留行"的菲号也清掉了**（本应只清新行）→ 带菲号量少 32 件（89→69、198→186）。
   **修复办法（很好用，记下来）**：用 **frappe `Version` 记录**取回改动前后的真实值 ——
   `Version.data` 里有 `row_changed`（每行每个字段的 old/new，且带**行名**）与 `added`（新增行完整数据），
   据此**按行名**精确还原了 15 行的 `stock_tracking_number`，带菲号量回到 89 / 198 ✓。
   查询方式：`GET /api/resource/Version?filters=[["ref_doctype","=","Delivery Note"],["docname","=","<DN>"]]&order_by=creation desc`

## 六、遗留事项 / 注意事项

1. **计划 2609006 / 2609008 仍带重复行**（都是 docstatus=1）：**不要再从这两张计划"创建出货单"**，
   否则重复行会回来；计划侧要清理只能走取消/修改流程（单独立项）。
2. **带菲号库里未被消耗的皮壳**（如 `WO-26-02810-013` 22 件、`WO-26-02810-005` 24 件等）仍留在
   「待包装成品仓 - FZH」，将来仍可给别的单用 —— 这是"带菲号只保留现有量"做法的必然结果。
3. 新增的无菲号行**不与原行相邻**（frappe 保存时重排了行序），但每行 `carton_group` /
   `outer_carton_no` 正确，**装箱分组不受影响**。
4. `DN-26-00080` / `DN-26-00083` **尚未提交**，等用户/同事在界面提交；
   提交前如担心，可重跑 `EN_API/dn_0080_83_edit_rows.py` 之外的只读复核（见第八节命令）。

## 七、两个必须记住的库存口径（本次实测）

1. **Bin ≠ SLE**：皮壳 `PK#KS0001-HLR-194-OFFWHITE` 在半成品仓 **SLE 汇总 51 件、Bin 却是 0**。
   **ERPNext 出入库校验认 Bin** → 判断"能不能领/能不能调"必须看 Bin；
   而 **DN 提交前的库存维度校验看的是 SLE 的跟踪单号维度**。两个口径用途不同，别混用。
2. **菲号产能上限 = `Tracking Number.qty`**：需求超过它的部分永远凑不出来，不是"多投产"能解决的，
   那是重复扫码/重复规划造成的。多张 DN 共用同一批菲号时，**先提交的把量用掉，后面的必然缺**。

## 八、关键文件与命令

| 用途 | 路径 |
|---|---|
| 本次脚本（00082/00083 主流程） | `EN_API/dn_2600082_83_fix.py`（probe / dry / apply --part fill\|tagged\|untagged / verify） |
| 本次脚本（00080/00083 改行） | `EN_API/dn_0080_83_edit_rows.py`（plan / edit [--apply]） |
| 性能探针（生产只读） | `EN_API/dp_perf_probe.py` |
| 缺料清单（对外） | `EN_API/out/dn_0080_0083_conversion_plan.md` |
| 重复扫行清单 | `EN_API/out/dn_0080_0083_duplicate_rows.md` |
| 改行逐行明细 | `EN_API/out/dn_0080_83_edit_plan.txt` |
| 菲号还原记录 | `EN_API/out/dn_0080_83_restore.json` |
| 前两次同类修复参考 | `EN_API/AGENT_HANDOFF_DN-26-00078.md`、`EN_API/dn_2600079_fix.py`、`EN_API/dn_stock_fix_apply.py` |
| 对外总结（00078） | `EN_API/docs/DN-26-00078_缺货排查与修复总结.md` |

**只读复核命令**（不写库）：
```bash
cd "D:/Claude Demo/fzh-data"
python EN_API/dn_0080_83_edit_rows.py plan        # 打印逐行改动指令（改完应显示空）
```

## 九、环境 / 规矩

- **生产**：`https://erpnext.vilavi.cn`，凭据 `EN_API/.env` → `PROD_ERP_API_KEY/SECRET`；**无 SSH**。
  写生产只能走**临时 API Server Script**（`zz_` 前缀、`script_type=API`、`api_method` 注册，
  调用 `/api/method/<api_method>`，**用完即删**）。
- **测试机**：`ssh dev01@8.133.254.66`，站点 `erpnext.vilavi.cn`（与 API `https://ensh.vilavi.cn` 同库），
  改 `.py` 后 `cd /home/frappe/frappe-bench && sudo -u frappe bench restart`。
- **Server Script 沙箱限制**（实测）：禁 `import`（`json` 已注入）；禁 `_` 开头的变量/属性名；
  禁 `+=`；不支持 `a, b = f()` 解包；`frappe.get_attr` 不可用；
  可用 `frappe.get_doc/get_all/new_doc/db.sql/db.set_value/db.commit/utils.flt`。
- **ops 很长时必须走 POST body**（放 query string 会被 nginx 414）。
