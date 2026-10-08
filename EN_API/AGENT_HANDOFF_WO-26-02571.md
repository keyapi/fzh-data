# AGENT HANDOFF — WO-26-02571 / WO-26-03197 完工归属更正

> ## ⚠️ 新会话开工前必读（用户反复强调）
> 1. **不要新建 worktree、不要新建分支**。所有读写 / git 操作都用**主检出绝对路径** `D:\Claude Demo\fzh-data`（本模块 `EN_API\`），产物也落在这里，**不要放 `.claude\worktrees\<名字>\`**。
> 2. 若本会话被告知"当前在 git worktree"：**不要 `EnterWorktree`**，直接用主检出绝对路径工作即可。
> 3. **git 操作（commit / push / 建分支 / 开 PR）必须先经用户同意**。

> 交接文档。对外版总结见 [docs/WO-26-02571_完工归属更正总结.md](docs/WO-26-02571_完工归属更正总结.md)。

## 一、当前状态（2026-09-21）

**生产更正已执行完毕，`verify` 全部通过，无临时 Server Script 残留。**

| | WO-26-02571 (SO-26-00101 皮壳) | WO-26-03197 (SO-26-00106 成品子件) |
|---|---|---|
| 计划 | 130 | 25 |
| 改前已产 | 78 | 78 |
| **改后已产** | **131**（超计划 1） | **25**（正好等于计划） |
| `open_material_qty` | 131 | 25 |
| 皮壳落仓 | 待包装半成品仓 131 | 待包装成品仓 25 |

改挂的 52 件 = 菲号 `WO-26-03197-001 + -002 + -003`；`-004` 留在 03197。
**超量的 1 件**另按用户要求归到 02571：`03197-001` 13→**14**、`03197-004` 26→**25**（含报工数量 ±1）。

## 二、这次改了什么（七层）

| 层 | 对象 | 动作 |
|---|---|---|
| 跟踪单号 | 3 个菲号 | `work_order`/`fp_wo` → 02571；`so_materials` → `PK#KS…` |
| 完工入库 | `STE-26-15207/15205/15201` | 取消；在 02571 下重做 → `STE-26-15626/15627/15628`（单价逐条一致） |
| **报工** | **21 张 Job Card** | `work_order` → 02571 **+ `operation_id` → 02571 的同名工序行**（真实员工/工时未动，仍 docstatus=1） |
| **工序数量** | 两工单各 7 道 `Work Order Operation` | `completed_qty` 78/78 → **131 / 25**，status → Completed（走系统 `job_card.update_work_order()` 重算） |
| 加工耗用 | 8 张 Material Consumption | `work_order` → 02571 |
| **开料工单 753** | 6 行 `Woker Order Allocation` + 2 个兄弟子表 | `work_order` + `wo_origion_fill_numb` + `is_or_exceed` 按算法重算；`work_order_batch_qtys` / `fg_qty_key_material_bns` 的 group1-3 一并改归属 |
| 工单 | 两工单 | `produced_qty` / `open_material_qty` → 131 / 25 |
| **超量 1 件归位** | `03197-001` 13→14、`03197-004` 26→25 | 菲号 qty + 报工数量 ±1 + 完工入库/加工耗用取消重做 + 开料工单 g1/g4 同步 |

> 三层是**用户逐轮指出后补的**：第一轮漏了报工层、第二轮漏了工序数量与开料勾稽、第三轮指出超量 1 件的归属错了。

## 三、⚠️ 踩坑清单（重做时务必照做）

1. **`fix-wo-qty` 必须排在 `redo` 之前** —— 否则 `update_work_order_qty` 用 `completed_qty = open_material_qty = 78` 判「91 > 78」抛 `StockOverProductionError`。
2. **redo 必须 `from_bom = 1`** —— `stock_entry.py:229` 会把 `fg_completed_qty` 清成 0。
3. **redo 成品行必须 `set_basic_rate_manually = 1` + 抄原凭证单价** —— 否则 Manufacture 单价被按「工单历史 outgoing」重算成 0。
4. **`frappe.client.submit` 要传完整单据** —— 只传 `{"doctype","name"}` 会被当成新文档、字段为空。
5. **`Woker Order Allocation` 是子表，REST list 403** —— 从父单据读；沙箱 `frappe.get_all` 可以。
6. **改挂后不能再按 `work_order` 查那些凭证**（已被改成目标工单）—— redo 取单价模板只能按菲号查。
7. **只改 `Job Card.work_order` 不会更新工序数量** —— 工序 `completed_qty` 聚合键是 `(work_order, operation_id)`，
   `operation_id` 必须换成目标工单同名工序行，再调 `job_card.update_work_order()` 让系统重算（别手工塞数字）。
8. **开料工单兄弟子表要一起改** —— `work_order_batch_qtys` / `fg_qty_key_material_bns` 同样带 `work_order`。
9. **子表 doctype 名 ≠ 字段名** —— 用 `row.doctype`（否则报 `Table '...tabwork_order_batch_qtys' doesn't exist`）。
10. **沙箱逐条容错 + 禁下标增强赋值** —— 每条删除单独 `try/except` + `frappe.db.rollback()`；`out["k"] += 1` 会报
    `Augmented assignment of object items and slices is not allowed`。
11. **取消「加工耗用」会被 Completed 工单拦**（`validate_work_order_status` 只对该 purpose 生效）
    → 临时把工单 `status` 降为 `In Process`，做完置回。
12. **加工耗用重做要带批次**：行上复制 `batch_no`/`use_serial_batch_fields`/`uom`/`basic_rate`/`cost_center`/`expense_account`/`custom_s_warehouse`，
    并临时打开 `Stock Settings.auto_create_serial_and_batch_bundle_for_outward`（完事关回 0）；**同批次要先全部取消再统一新建**。
13. **凭证号必须按菲号现查** —— 本次一度把 `-001` 的完工凭证写成 `-003` 的，误取消一张、多建一张。

## 四、遗留事项

1. **3 张遗留草稿耗用单** `STE-26-15208/15206/15202`（ds=0）未清理。
3. **`WO-26-03047`（SO-26-00106 成品工单）仍为 Draft** —— 剩 **25** 件皮壳在待包装成品仓，正好够做 25 件成品。
4. **防复发未做**：
   - `work_order_override.update_work_order_qty()` 的「`open_material_qty` 非 0 即短路」+ 开料工单缺 `on_trash` 重算
     → 残留值会放行/卡住入库（与 2026-09-20 的 `WO-26-02817`/`WO-26-02570` 同源）；
   - `_create_manufacture_for_finished_goods` 在 `finished_product_work_order` 为空时静默 return（DN-26-00078 同源）。

## 五、关键文件

| 用途 | 路径 |
|---|---|
| 对外总结 | `EN_API/docs/WO-26-02571_完工归属更正总结.md` |
| 生产执行脚本 | `EN_API/wo_02571_03197_reassign.py`（`probe/dry/apply --step/verify/cleanup`） |
| 测试演练脚本 | `EN_API/wo_02571_03197_rehearsal.py`（硬锁 `ensh.vilavi.cn`，`scout/run/report/cleanup/purge`） |
| 改前账面快照 | `EN_API/out/wo_02571_03197_before_20260921_110508.json` |
| 改后账面 | `EN_API/out/wo_02571_03197_after_probe.txt` |
| 凭据 | `EN_API/.env` → `PROD_ERP_API_KEY/SECRET`（生产）、`TEST_ERP_API_KEY/SECRET`（测试） |
| 服务器 SSH | 测试 `ssh 上海测试-阿里云-FZH-ERPNext-frappe`、生产 `ssh 阿里云-FZH-ERPNext-frappe`（别名见 `~/.ssh/config`，两台都通） |

## 六、环境注意

- **产物放主检出** `D:\Claude Demo\fzh-data`，不要放 `.claude/worktrees`。
- 生产写操作走**临时 API Server Script**（`zz_` 前缀，用完即删）。
- **git 操作（commit/push/建分支/开 PR）必须先经用户同意。**
