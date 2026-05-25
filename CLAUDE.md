# CLAUDE.md

## 通用守则 (Andrej Karpathy)

> 源自 [Andrej Karpathy 对 LLM 编码陷阱的观察](https://x.com/karpathy/status/2015883857489522876)，由 [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) 整理。
> **权衡取舍**：这些准则偏向谨慎而非速度。对于琐碎任务，自行判断。

### 守则 1：编码前思考
**不假设。不隐藏困惑。呈现权衡。**
- 明确陈述你的假设。如果不确定，询问。
- 如果存在多种解释，呈现它们——不要默默选择。
- 如果有不清楚的地方，停下来。指出困惑之处。提问。

### 守则 2：简洁优先
**用最少代码解决问题。不做投机性工作。**
- 不添加未被要求的功能；不为一次性代码创建抽象。
- 不为不可能发生的场景做错误处理。
- 扪心自问："资深工程师会觉得这过于复杂吗？"如果是，就简化。

### 守则 3：精准修改
**只碰必须碰的。只清理自己造成的混乱。**
- 不"改进"相邻的代码、注释或格式；不重构没坏的东西。
- 匹配已有风格，即使你更倾向于不同的写法。
- 删除因你改动而不再使用的导入/变量/函数；不删除已存在的死代码。
- 检验标准：每一行被改动的代码都能直接追溯到用户的请求。

### 守则 4：目标驱动执行
**定义成功标准。循环验证直到达成。**
- "添加校验" → "先写非法输入测试用例，再让它们通过"
- "修 bug" → "先写一个能复现的测试，再让它通过"
- 多步骤任务陈述简要计划，每步标注验证点。

---

## 项目信息

Project: fzh-data — FZH 公司数据管道工具集。当前主要用于维护**赛狐 / ERPNext / 通途**三方数据一致性。

## 公司背景 (FZH)

**FZH** 是跨境电商公司，在北美和欧洲销售**家居纺织品**（填充物为 PP棉/海绵的靠枕、沙发等）。
销售平台：Amazon（北美+欧洲）、Wayfair、Home24、Shopify 等。

### 供应链架构

```
绍兴工厂 (中国)
  ├─ 生产皮壳、内胆、半成品
  ├─ 部分成品直接生产 → FBA / 直接发货
  │
  └─ → 海外分公司仓库：
       ├── USNJ (美东, NJ州) → 填充/压缩/包装/仓储/发货(2C+2B)
       ├── USTX (美中, TX州) → 同上
       └── POLAND (波兰)     → 同上
            │
            └─ → Amazon FBA / 第三方海外仓
```

### 赛狐仓库映射

| 公司仓库 | 赛狐仓库名 | 说明 |
|----------|-----------|------|
| USNJ 美东仓 | CENTRADE | 已启用 |
| USTX 美中仓 | DANEEY | 已启用 |
| POLAND 波兰仓 | POLAND | 已启用 |
| 绍兴工厂(本地) | — | 未启用（赛狐本地仓限制多） |

> 赛狐有两种仓库类型：**本地仓**（中国仓，更多限制，未启用）和**海外仓**（我们用的 3 个分公司仓）。

### 赛狐平台限制

- 海外仓不能直接通过库存调账修改库存数量和采购单价，需通过**其他入库/其他出库**实现成本调整
- 采购成本=0 的行赛狐静默跳过不导入
- 导入模板工作表名必须为 `商品`，Data Validation 丢失会被拒绝

### 赛狐库存核心策略（初期过渡阶段）

**当前阶段**：赛狐初期使用中，实际发货仍在通途操作。赛狐只用来获取订单成本（尾程前），暂不管理真实库存。

**关键认知：赛狐入库批次与成本**

- 赛狐使用**先进先出（FIFO）**逻辑：同一仓库+SKU 先后入库 A、B 两批，订单优先消耗 A 批次，A 耗尽后才用 B
- B 批次的成本**不能修正** A 批次的成本（后入库不等于覆盖）
- 赛狐允许修改历史入库单里的成本，但**只能逐行手动改**，无批量导入方式
- 因此初期一次性把 3 仓全套成本导入，后续主要做**成本修正**（手动），而非频繁新建入库

**库存数量策略**

| 决策 | 说明 |
|------|------|
| **不追求与通途数量一致** | 通途 SKU 体系混乱、2 套系统短期难以对齐 |
| **安全冗余数量（1000）** | 避免赛狐 0 库存导致订单无法标记发货，远超业务需要 |
| **仓库分布参考通途** | 通途"哪个仓有此 SKU"比"库存多少"更可信，避免跨仓虚构 |
| **不写回平台库存** | 赛狐暂未开通，虚假数量不会污染销售平台 |

**入库方式**

| 方式 | 状态 | 说明 |
|------|------|------|
| 期初库存导入 | 已用过 | 相同 SKU+仓库不可重复导入 |
| 其他入库/出库 | 已用过 | 可调整，但需逐仓操作 |
| **海外仓备货单** | 待使用 | 下一阶段主用方式，可带成本+数量一起入库 |

**下一步流程**：
1. 同事 PJ 补完成本数据后，重新跑 `build_saihu_stock_init.py` 确认成本缺口归零
2. 如需清零重建：先其他出库清空 → 海外仓备货单统一入库（数量=1000）
3. 后续成本修正：赛狐界面手动修改入库单成本行

---

## Skill 索引

每个模块对应一个 Skill（`.claude/skills/<name>/SKILL.md`），Claude 自动按用户触发词加载。详情见各 Skill 文件 + 模块的 `AGENT_HANDOFF.md`。

| Skill | 目录 | 功能 | 触发词特征 |
|-------|------|------|-----------|
| `stock-init` | `stock_init/` | 通途库存 + EN BOM 成本 → 赛狐库存初始值导入 | 库存初始值、库存导入、通途库存、EN BOM成本 |
| `item-cost` | `item_cost_sx/` | EN BOM 成本 → 赛狐采购成本导入 | 采购成本、BOM成本、绍兴发货 |
| `item-weight` | `item_weight_size/` | 重量模板匹配 → 赛狐商品重尺导入 | 重尺、重量、尺寸、装箱量 |
| `category` | `category/` | EN 物料属性 + 分类树 → 4 级分类导入 | 商品分类、四级分类、类目 |
| `multi-attr` | `multi_attr_saihu/` | ERP 纵向物料 → 赛狐多属性 + 通途配对 | 多属性、SPU、物料导出、通途配对 |

五个模块**相互独立**（`category` 仅动态导入 `multi_attr` 的一个函数）。

## Tech stack

- Python >= 3.10, managed with **uv** (`pyproject.toml` at root)
- `pandas` for DataFrame operations, `openpyxl` for Excel read/write
- No packaging — standalone scripts run with `python script.py` from module directories

```bash
uv sync                          # install pandas, openpyxl
cd <module_dir> && python <script>.py   # run any script
```

## Code conventions

- **Column names in Chinese**: Excel column headers use UPPER_CASE (e.g. `COL_SKU = "产品编号"`, `SAI_HU_SHEET = "商品"`)
- **`os.chdir()` pattern**: Each script changes `os.getcwd()` to the script's directory at startup
- **Auto file selection**: Scripts auto-select input files (latest by `st_mtime`, excluding `~$` lock files)
- **Excel output**: All `.xlsx` gitignored. Timestamped filenames (`*_YYYYMMDD_HHMMSS.xlsx`)

## Git conventions

- Commit messages in **Chinese**, format: `type(scope): description`
- Common types: `feat`, `fix`, `docs`, `init`, `refactor`

### Git workflow

1. Development happens on the **worktree branch** (e.g. `claude/xxx`), NOT directly on `main`
2. Verify the change works, then merge into `main`:
   ```bash
   cd D:\Work\赛狐\Cursor
   git checkout main
   git merge claude/xxx
   ```
3. Sync the worktree branch back:
   ```bash
   cd .claude/worktrees/xxx
   git merge main
   ```
4. Never commit directly to `main` from the worktree — use the branch

## Lessons learned

### 1. Auto file selection: keyword specificity
`_find_file("重尺")` matched template `模板 商品重尺-*.xlsx` because "商品重尺" contains "重尺". Use most specific keyword (e.g. `"重尺数据"`). Verify each pattern matches only one file.

### 2. Directory naming: 数据源/ subdirectory
Keep code and data under one module directory. Use `数据源/` for inputs, `out/` for outputs.

### 3. Module structure convention
```
module_dir/
├── <script>.py / README.md / AGENT_HANDOFF.md
├── __init__.py (empty, for uv build)
├── 数据源/ (gitignored) / out/ (gitignored)
```

### 4. 赛狐 import template: worksheet name must be `商品`
`openpyxl` defaults to `Sheet1` but 赛狐 requires `商品`. Always set `SAI_HU_SHEET = "商品"`.

### 5. 赛狐 purchase cost: zero equals empty
赛狐 treats `采购成本=0` as empty — won't import 0 values. Generate two output files: import (filter cost=0) + reference (keep all).

### 6. SKU matching by prefix (shared across modules)
SKU format: `款式ID-面料-尺寸-颜色` (4 segments). First 3 define a "group key". Weight template: strip `ZLMB#` prefix. Rule: ≥4 segments → key = `"-".join(parts[:3])`; =3 → whole SKU; <3 → no match.

### 7. Excel file locking
`~$*.xlsx` lock files appear when Excel is open → `PermissionError`. Always exclude `~$` prefixed files in auto-selection.

### 8. uv environment
`uv sync` can fail if old `.venv` has stale artifacts → `rm -rf .venv && uv sync`. ONE `.venv` at repo root shared by all modules.

### 9. openpyxl destroys Data Validation on save
`openpyxl.load_workbook() + wb.save()` silently drops Data Validation → 赛狐 rejects file. Fix: `shutil.copy(template) → pd.ExcelWriter(mode='a')` for template-based outputs; or `pd.ExcelWriter() → to_excel(sheet_name='商品')` for new files.

### 10. Windows + Chinese path encoding
Shell commands with Chinese paths fail with `UnicodeEncodeError`. Prefer Python (`shutil`, `pathlib`) over shell for file ops. `PYTHONIOENCODING=utf-8` env var helps.

### 11. Left-merge / SKU whitelist pattern
赛狐 has fixed SKU set → read 赛狐商品导出 → `set(SKU)` as whitelist. Left-join to source data. Unmatched source rows reported but excluded from import.

### 12. 输出文件拆分
Import file (filtered, cost>0) vs reference file (all). Clear filename distinction (`_导入_` vs `_全量参考_`).

### 13. 问题报告统一格式
Multi-sheet `.xlsx`: `汇总` + N detail sheets + `每仓统计`. Each sheet对应一个问题类别，空 sheet 写占位行 "（无数据）". Detail sheets 含产品名称列.

### 14. Data source origins (who provides each Excel)
When debugging column changes, know which system produces each file. See Lesson #14 details in previous CLAUDE.md versions or ask user.

### 15. Keep docs updated immediately
After every fix/discovery, write to CLAUDE.md/md files in the same session. Don't wait for reminders.

### 16. Git worktree: commit from worktree, not main repo
Shell CWD resets to worktree but git commands could operate on main repo. Verify `git branch` shows `* claude/<name>` before commit. If mistake: `git reset --hard <prev>` on main, `git cherry-pick <hash>` on worktree.

---

## Documentation enforcement

**These are NOT guidelines. They are commit-time requirements.** Derived from the principle that stale docs are worse than no docs — the next agent session relies on them being accurate.

### When you modify a `.py` script

1. **Check** if the change affects any of these in `AGENT_HANDOFF.md`:
   - Function names, signatures, or behavior
   - Column name constants (`COL_*`)
   - Field mappings or business rules
   - CLI arguments or default paths
   - Boundary conditions or known issues
2. **If yes** → update `AGENT_HANDOFF.md` **in the same commit**.
3. **If the module's purpose or scope changed** → update the corresponding SKILL.md `description` YAML field.

### When you fix a bug caused by incorrect assumptions

Add a lesson to the "Lessons learned" section above. Format: Problem → Root cause → Fix → Rule.

### Before committing

Run this self-check:

```
[ ] .py files changed? → Are corresponding AGENT_HANDOFF.md changes in the same diff?
[ ] New pitfall discovered? → Added to Lessons learned above?
[ ] Module scope changed? → SKILL.md description updated?
```

If a `.py` change intentionally does NOT require doc updates (typo fix, reformatting), explain why in the commit message.

### Why this matters

The next agent session (whether yours, GQ's, or a colleague's via Claude Desktop) starts by reading CLAUDE.md, SKILL.md, and AGENT_HANDOFF.md. If those files are stale, the agent will make decisions based on wrong information — wasting time and introducing bugs.

---

## Skill 管理规则

### 核心原则

1. **每个模块一个 Skill**，职责单一，不堆砌
2. **SKILL.md 是入口索引**（< 300 行），只放触发条件、约束、管道概要
3. **AGENT_HANDOFF.md 放详情**（函数表、字段映射、边界条件、踩坑），按需加载
4. **description 是触发命中的关键** — 必须包含用户真正会说的自然语言
5. **所有 skill 文件纳入 git**，可回滚、可协作

### description 编写规则

- 包含用户真正会说出口的词：模块名、动词、数据源名
- 中英文都要覆盖（如 "库存初始值"+"stock_init"+"通途库存"）
- 用自然语言短语而非关键词堆砌
- 明确 NOT 情况：什么情况下**不要**触发此 skill（如 "不要用于采购成本导入"）

### 触发词覆盖规则

description 中必须覆盖以下类型的触发词：

| 类型 | 示例 |
|------|------|
| 模块名中英文 | stock_init/库存初始值、item_cost/采购成本、multi_attr/多属性 |
| 核心动词 | 导入/导出/计算/匹配/生成/校验/配对 |
| 数据源名 | 通途库存/EN BOM/重量模板/物料属性/分类导出 |
| 用户习惯说法 | 库存初始化/成本借用/属性炸开/四级分类/通途配对 |

### 编写原则

| 原则 | 说明 |
|------|------|
| **SKILL.md < 300 行** | 只保留触发条件、约束、管道概要、输出文件 |
| **AGENT_HANDOFF.md 放细节** | 函数表、字段映射、CLI 参数、边界条件、踩坑记录 |
| **去重** | SKILL.md 不重复 CLAUDE.md 内容，不重复 AGENT_HANDOFF.md 内容，用引用代替 |
| **发现即更新** | 每次脚本修改或新发现边界条件，立即更新 AGENT_HANDOFF.md，不积累记忆负担 |

### 运行规则

- **永远用 `uv run python`** 或 `python`（uv 管理的 venv）
- **永远用 `uv add <包名>` 加依赖**，自动写入 `pyproject.toml`
- 每个脚本从模块目录运行：`cd <module_dir> && python <script>.py`

---

## Module docs location

Each module has `README.md` (human) + `AGENT_HANDOFF.md` (agent). Read both before modifying code. SKILL.md in `.claude/skills/<name>/` is the agent entry point and references AGENT_HANDOFF.md for details. Never duplicate content between SKILL.md and AGENT_HANDOFF.md — SKILL.md links to AGENT_HANDOFF.md, not copies from it.
