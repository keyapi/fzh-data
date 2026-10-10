# AGENT_HANDOFF — 碎海绵 / 销售订单描述前缀 / 重量模板（2026-10-10）

> 新会话入口。先读本文件 + `MEMORY.md`（自动加载）。做完的、待办的、怎么改，都在这。

## 0. 工作方式（最高优先级，务必遵守）

- **主检出 = `D:\Claude Demo\fzh-data`**（模块 `EN_API\`）。所有产物落这里。
- **不要 EnterWorktree、不要新建 worktree、不要新建分支、不要开 PR**；git 任何写操作一律先问用户。
  - 会话可能被工具自动开在 `.claude/worktrees/<某名>` 里 → **无视它**，一律用**主检出绝对路径**。
- **生产 `https://erpnext.vilavi.cn`**（凭据 `EN_API/.env` 的 `PROD_ERP_API_KEY/SECRET`）：默认**只读**。
  - 写生产固定流程：**统计 → 用户确认 → dry-run → 写前快照 → 执行 → 独立回读**。
  - 临时脚本用 **`zz_` 前缀**（`Server Script`, `script_type=API`），**用完即删并复查残留 0**。生产**无 SSH**。
- **测试机**：`ssh dev01@8.133.254.66`（**站点名也叫 `erpnext.vilavi.cn`**，`bench --site` 用它）；
  `sudo -u frappe` 只放行 `bench`；改 app 的 `.py` 后必须 `bench restart`。

## 1. 本次完成的三件事

### A. 客户物料 `special_mark = 碎海绵`（数据 + 字段）
- **需求**：读 `EN_API/数据源/2026年下单表.xlsx` 工作表「2026年度FBA订单（新）」，按「通途SKU」列 → EN 物料，
  在其**客户物料子表**（doctype `Item Customer Detail`）打 `special_mark = 碎海绵`。
- **口径**：通途SKU == `Item.customer_items.ref_code`（全局唯一、大小写不敏感）。
  子表字段 `special_mark`（Data，标签「特殊标记」，`insert_after=ref_code`）走 **app `delivery_plan` 的 fixtures**。
- **结果**：47 SKU → 47 物料 / 54 行；**后按业务收敛为 item_group 含「三角」或「平条」的 42 行**（清掉 12 行）。
  生产已执行 + **独立 SQL 回读**（42 行、越界 0）。
- **产物**：`EN_API/item_customer_special_mark/`（`set_special_mark.py`：stats/dry-run/apply/verify/rollback/fix-scope；
  `AGENT_HANDOFF.md`、`fixtures_snippet.md`）。

### B. 销售订单明细 `description` / `custom_tongtool_item_name`(通途产品名) 加「碎海绵」前缀（key_test app）
- **条件（三者同时满足）**：① 该销售订单为 **FBA**（`customer`/`customer_name` 含「FBA」，如「美国FBA仓」）；
  ② 该行客户物料号(`ref_code`) 的 `special_mark = 碎海绵`；③ 该行**命中 EN 物料**。→ 两个字段前都加 `「碎海绵 」`。
- **改动**：
  - 后端 `key_test/item_utils.py::read_excel_file(file_url, customer=None, customer_name=None)`：算 `so_is_fba`，
    按 `ref_code` 查 `special_mark`，在**两个命中分支**给 description + 通途产品名加前缀。
  - 前端：原 Client Script（DB 记录）**迁进 app** → 新文件 `key_test/public/js/sales_order.js` +
    `hooks.py` 的 `doctype_js["Sales Order"]`；原 Client Script 置 `enabled=0`，并新增传参 `customer`/`customer_name`。
- **状态**：测试机已部署验证；**生产已部署**（用户 reboot 后生效）。
- **产物**：`EN_API/so_item_special_mark/`（`README.md`、`key_test__item_utils.special_mark_prefix.patch`、`client_script_upload.patch`）。

### C. 重量模板「带颜色」→ BOM Cost List V2「发成品尾程前成本 USFBA」= 0（数据修复）
- **现象**：`手臂支撑枕-荷兰绒-65X60X15-灰色`（`KS0322-HLR-65-GREY`）该列 = 0。
- **根因**：报表 `get_zlmb_info` 固定取 `item.name.split('-')[:3]` 拼 `ZLMB#{型号}-{面料}-{尺寸}`；
  而该产品的重量模板被建成 4 段带颜色 `ZLMB#KS0322-HLR-65-GREY` → 查 `ZLMB#KS0322-HLR-65` **查无** →
  成品单重/包装体积 = 0 → 计费重量 0 → 运费 0 → 尾程前成本「缺一即 0」。
  （带颜色的成因：一键创建配套物料时照搬「重量模板模板」自身属性；该模板自带「颜色」属性。现行代码已过滤颜色，
  但**只在新建模板时跑、模板已存在就跳过** → 老数据不自愈。）
- **修复（顺序关键，测试机演练后执行）**：① 删**变体**颜色行 → ② 删**模板**颜色属性 → ③ `rename_doc`
  `ZLMB#KS0322-HLR-65-GREY` → `ZLMB#KS0322-HLR-65`（重尺原样保留）。**反过来会被 ERPNext 拦（417 变体属性错误）**。
- **结果**：USFBA **0 → 83.546**（=绍兴总成本 58.896 + 成品运费 24.65）；`missing_weight_volume` 由「皮壳缺重尺」变空；
  `zz_` 残留 0。快照 `EN_API/out/ks0322_snapshot_20261010_114655.json`（可回滚）。
- **全站范围**：真正「带颜色」的重量模板**只有这 1 个**。
- **产物**：`EN_API/bom_weight_template/weight_template_tools.py`（`issues` 盘点导出 / `ks0322-dryrun` / `ks0322-apply --yes`）。

## 2. 待办 / 未完成（都没动）

- **C 的剩余**：`ZTGJ5525-*` 共 **6 个**（产品编码 4 段结构，报表写死的 3 段假设取错 → 需**改报表**）；
  **33 个产品缺重量模板**（需按 `ZLMB#型号-面料-尺寸` 补建）。清单 = `EN_API/out/weight_template_issues_*.xlsx`。
- **更早遗留（另一条线）**：皮壳调拨取消导致的 **Bin≠SLE 挂账**（待包装两仓 -300/-113 与 +300/+394）；
  **22 件未挂 SO**；**20 张孤儿报工工单**（工序 completed_qty 卡 0）；**worktree 清理**。
- 主检出持久分支 `feature/en-api-bom-fabric-and-dp-occupancy`：**远端已删、内容已在 main、本地落后 main 200+** —— 别再往上堆。

## 3. 提交 git / PR 前：敏感信息清理

- **已 gitignore（勿提交）**：`EN_API/.env`（含 `PROD_ERP_API_KEY/SECRET`、`TEST_*`、`DEEPSEEK_API_KEY`）、`EN_API/out/`。
- **计划提交的本仓库新增**：`EN_API/item_customer_special_mark/`、`EN_API/so_item_special_mark/`、`EN_API/bom_weight_template/`。
- **提交前自查**：脚本/文档里有无硬编码域名、真实单号/客户码/菲号；`out/` 与 `.env` 是否被误加（`.gitignore` 有锚定陷阱）。
- 另：仓库 remote 内嵌**明文 PAT 待轮换**（见 memory `reference_en_repo_git_pr.md`）。
- **注意**：B 的**代码本体在服务器上的 `key_test` app**（不是本仓库）；本仓库只存它的 patch/说明。
  C 的**数据修复**在生产库、无代码提交（脚本在本仓库）。

## 4. 关于「每次新会话都自动新建分支」的解法

- 仓库 `.claude/` 下**没有**控制它的 settings（只有 `launch.json` 预览配置）→ 应是**启动器/包装脚本**在建 worktree+分支。
- 处理（择一）：
  1. **根治**：改用 `D:\Claude Demo\fzh-data` 作为项目根**直接启动**（不带 worktree 参数）。
  2. **兜底（建议先做）**：新会话开头就 `git -C "D:/Claude Demo/fzh-data" checkout <持久分支>`，
     之后所有操作走主检出绝对路径、忽略 worktree。
- **持久分支名建议**：`feature/en-api-special-mark-and-weight-template`（一次性在主检出建好，之后所有会话复用它）。

## 5. 关键产物索引（本仓库）

| 用途 | 路径 |
|---|---|
| 碎海绵数据/字段 | `EN_API/item_customer_special_mark/`（`set_special_mark.py`、`AGENT_HANDOFF.md`）|
| SO 描述前缀（key_test） | `EN_API/so_item_special_mark/`（`README.md`、两个 `.patch`）|
| 重量模板工具 | `EN_API/bom_weight_template/weight_template_tools.py`（+ `EN_API/out/` 清单/快照；`out/` 已 gitignore）|
