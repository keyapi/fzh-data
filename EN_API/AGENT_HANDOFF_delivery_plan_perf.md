# AGENT HANDOFF — 出货计划（Delivery Plan）保存/扫码卡顿优化

> ## ⚠️ 新会话开工前必读（用户反复强调）
> 1. **不要新建 worktree、不要新建分支**。所有读写 / git 操作都用**主检出绝对路径** `D:\Claude Demo\fzh-data`（本模块 `EN_API\`），产物也落在这里，**不要放 `.claude\worktrees\<名字>\`**。
> 2. 若本会话被告知"当前在 git worktree"：**不要 `EnterWorktree`**，直接用主检出绝对路径工作即可（产物不会丢，见文末）。
> 3. **git 操作（commit / push / 建分支 / 开 PR）必须先经用户同意**。
> 4. 用户对"每次新会话都新开分支/worktree，以为会话数据丢了"很敏感 —— 会话开头就申明这一点。

## 一、当前状态（2026-09-20）

**测试机已改完并验证通过，等用户手动同步到生产**。下一步是：用户在**生产**做复验（只读，不改数据）。

- 改动只有一个文件（在测试机，本地检出**没有**这个 app 的源码）：
  `8.133.254.66:/home/frappe/frappe-bench/apps/delivery_plan/delivery_plan/delivery_plan/doctype/delivery_plan/delivery_plan.py`
- 该文件的 `git status` 应只显示这**一个** `M`（临时探针已删除）。

### 问题（用户同事报告）
出货计划行数大时，**扫跟踪单号 / 加明细行后点保存至少 10 秒**。

### 根因（已实测定位）
保存走 `validate()` → `create_items_from_planned_qties()`，其中：
1. **主因** `_allocate_actual_qty_strict()` 对**每一行**调 `get_strict_so_warehouse_and_stock(row.tracking_number)`
   —— **无预加载、无缓存** → 每行重新 `frappe.get_doc` 拉 TN→工单→**整个生产计划** + SO 查询。
   **实测 88ms/行**（对比：带预加载只要 1.3–1.6ms/行）。且保存路径在 `create_items_from_planned_qties`
   主体里**已经带缓存算过同一件事**，这里是**重复算第二遍**。
2. `_get_effective_warehouse_for_item_row()` 每行 2 条 `frappe.db.get_value`（生产类型 + SO 行仓库）。
3. `get_strict_so_for_tracking_number()` 每行（且每次调用两遍）`next()` 线性扫 `pp.po_items`(291) + `pp.sub_assembly_items`(54)。
4. 前端 `delivery_plan.js` 的 `tracking_number(frm)` handler：**每扫一次就 `frm.save()` 一次** → 成本 = 行数 × 扫码次数。

## 二、已做的改动（10 处补丁，仅上述一个文件）

| # | 改动 |
|---|---|
| 1 | 新增 `_dp_pp_child_index()`：按**文档实例**缓存 PP 子表索引（**请求级，无模块级缓存**，避免 worker 读到陈旧数据） |
| 2 | `get_strict_so_for_tracking_number` / `get_strict_so_warehouse_and_stock`：子表查找 `next()` 全扫 → 索引查 |
| 3 | 新增 `_dp_so_detail_warehouse()`；`_get_effective_warehouse_for_item_row` 改用它（SO 行仓库按 `so_detail` 缓存） |
| 4 | `_get_sales_order_manufacturing_type`：按 `(so_detail, sales_order)` 缓存 |
| 5–7 | `allocate_actual_qty(stock_map=…)` / `_allocate_actual_qty_strict(stock_map=…)`：**复用上游已算好的 TN 库存**；上游未给的才兜底查询 |
| 8–10 | `create_items_from_planned_qties` 主循环收集 `tn_stock` 并下传 |

**附带修掉一个隐患**：原 `_allocate_actual_qty_strict` 用**未 strip** 的菲号判断，纯空白菲号会去查不存在的 TN 而报错；
现与主循环一致按 strip 后判断。

## 三、验证结果（测试站计划 2607009）

| 行数 | 改前 | 改后 | 提升 |
|---|---|---|---|
| 222 | 3.773s | **0.494s** | 7.6× |
| 450 | 7.299s | **0.842s** | 8.7× |

一致性（证明未改业务逻辑）：
- 222 / 450 行输出 dump **逐行完全一致**（`diff` 无差异）
- `_get_effective_warehouse_for_item_row` 20 / 23 / 7 行全一致
- **全库 86 张计划 / 40 个菲号，0 不一致**
- 8 种形态计划（严格/非严格 × 草稿/已提交）全部正常
- 扫码路径正常（`WO-26-00024-001` 0.115s 成功；另一枚按业务规则正确拒绝"已无可用库存"）

**生产预期**：生产上被去掉的调用是 **88ms/行**（测试站只有 ~16ms/行，因为生产的生产计划文档大得多）
→ 114 行 ≈ 10s 预期降到 **<1s**。以生产实测为准。

## 四、下一步（待用户说"已同步"）

在生产做「耗时 + 一致性」复验，**只读、不改任何数据**：
- 生产 **SSH 可达**（`ssh 阿里云-FZH-ERPNext-frappe`，见 AGENTS.md「EN 服务器 SSH」）—— 下面这条
  **临时 API Server Script** 路线仍然可用（`zz_` 前缀、`script_type=API`、`api_method` 字段注册、
  调用路径 `/api/method/<api_method>`、**用完即删**），但不再是唯一选择。生产凭据 `EN_API/.env` 的 `PROD_ERP_API_KEY/SECRET`，
  base = `https://erpnext.vilavi.cn`。
- 探针逻辑（可重建）：加载目标计划 → `doc.run_method("create_items_from_planned_qties")`（**不保存**）→ 计时 + dump 关键字段；
  另有「改造前 vs 改造后」逐菲号对比函数。
- 生产上先用只读 GET 取计划（e.g. `2609006` 114 行 / `2608011` 452 行）做基线，再看同步后的耗时。
  **注意：生产不要执行 `save`/`submit`**。
- 复验完把临时脚本删掉（生产上不应留 `zz_` 残留）。

## 五、回滚 / 材料

| 用途 | 位置 |
|---|---|
| 改动前原文件 | `8.133.254.66:/tmp/zz_bak_delivery_plan.py` |
| 10 处补丁脚本（可重放） | `8.133.254.66:/tmp/zz_patch_dp.py` |
| 改后的文件 | `8.133.254.66:/home/frappe/frappe-bench/apps/delivery_plan/delivery_plan/delivery_plan/doctype/delivery_plan/delivery_plan.py` |

## 六、未做（等用户决定）

1. **无菲号行的批量 SQL + 逐行写 Error Log**（`delivery_plan.py:613`）：无菲号行多时才明显。
2. **前端"每扫一次就 save 一次"**：属交互策略改动、验证成本高，建议后端提速后先观察体感。

## 七、环境 / 规矩

- **测试站**：`ssh 上海测试-阿里云-FZH-ERPNext-frappe`（`8.133.254.66`，别名见 `~/.ssh/config`），站点 `erpnext.vilavi.cn`（库名 `_133d3237c7c4c70b`），
  与 API `https://ensh.vilavi.cn`（凭据 `TEST_ERP_API_KEY/SECRET`）是**同一个库**。
  改 `.py` 后必须 `cd /home/frappe/frappe-bench && sudo -u frappe bench restart`。
  `dev01` 在 `frappe` 组、app 文件组可写。
- **测试库是约 2026-08-25 的快照**（86 张计划、最大 23 行、SLE 仅 4024 条）→ 不能直接复现生产的 10 秒，
  耗时要靠"把真实菲号行放大到 ~450 行"的内存基准来测。
- 生产**不产生数据**、不改代码；git 操作先问用户。

---

## 八、2026-09-21 进展（生产复验）

### 结论：**生产仍然跑旧码**（未生效）
用临时探针判定：调 `doc.allocate_actual_qty(stock_map={})` → 生产返回
`DeliveryPlan.allocate_actual_qty() got an unexpected keyword argument 'stock_map'`
（只有旧签名会这样报错）；同一探针在测试站返回 `new`。→ **"推送到远程"没让生产的工作副本更新**。

**用户需在生产服务器上确认**：
```bash
sha256sum /home/frappe/frappe-bench/apps/delivery_plan/delivery_plan/delivery_plan/doctype/delivery_plan/delivery_plan.py
# 期望 7b2a708fefbb56fec48dd3981bf2a6e1e3de6915d09a3a88b394504a0a0bac5c
cd /home/frappe/frappe-bench && sudo -u frappe bench restart
```
（`bench restart` 权限不对会静默失败；注意别重启错 bench —— 测试机上也有个同名站点。）

### 已验证的生产实测数据（只读）
| 计划 | 菲号行 | 旧码那条路（无预加载，按行） | 新码那条路（带预加载，按行） |
|---|---|---|---|
| 2609007 | 105 | 88.52 ms/次 × 105 = **9.29s** | 0.44 ms/次 × 105 = **0.05s** |
| 2608011 | 451 | 30.63 ms/次 × 451 = **13.81s** | 0.38 ms/次 × 451 = **0.17s** |

- 改造前整单实测：2609006（114 行）**13.15s**、2608011（452 行）**18.68s**（dump 见 `EN_API/out/dp_prod_*_before.json`）
- 预加载那段（TN/WO/PP 批量加载 + batch_sle_cache）**本来就是既有逻辑**，10 处补丁做的是让
  `_allocate_actual_qty_strict` **复用**它，不再逐行重算

### 改成"只读复验"的原因（重要）
- 跑 `create_items_from_planned_qties` 会触发"无菲号行余额为 0 写 Error Log"（`delivery_plan.py:660`，用户要求保留），
  而 **`frappe.log_error` 会立即提交，`frappe.db.rollback()` 丢不掉**（实测）；`frappe.flags.read_only` 也只是推迟到 Redis。
  → 生产的整单复验**不做**（除非用户明确同意写几行 Error Log）。
- 生产 Error Log 总行数**随时在涨**（实测 10 分钟 +245 行），**不能**当"数据未变"的判据。

### 待决
1. 版本判定 = `new` 后，用 `dp_perf_probe.py hotpath` 复测；「整单 10s→<1s」由用户正常保存一次来观测
2. `delivery_plan.py:613` 无菲号行的批量 SQL（用户此前说先保持现有 Error Log 逻辑）
3. 前端"每扫一次就 save"（用户决定暂缓）
