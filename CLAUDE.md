# CLAUDE.md

## 通用守则 (Andrej Karpathy)

> 源自 [Andrej Karpathy 对 LLM 编码陷阱的观察](https://x.com/karpathy/status/2015883857489522876)，由 [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) 整理。
> **权衡取舍**：这些准则偏向谨慎而非速度。对于琐碎任务，自行判断。

### 守则 1：编码前思考

**不假设。不隐藏困惑。呈现权衡。**

实施前：
- 明确陈述你的假设。如果不确定，询问。
- 如果存在多种解释，呈现它们——不要默默选择。
- 如果存在更简单的方法，说出来。在有必要时提出异议。
- 如果有不清楚的地方，停下来。指出困惑之处。提问。

### 守则 2：简洁优先

**用最少代码解决问题。不做投机性工作。**

- 不添加未被要求的功能。
- 不为一次性代码创建抽象。
- 不添加未被要求的"灵活性"或"可配置性"。
- 不为不可能发生的场景做错误处理。
- 如果你写了 200 行但 50 行就够了，重写它。

扪心自问："资深工程师会觉得这过于复杂吗？"如果是，就简化。

### 守则 3：精准修改

**只碰必须碰的。只清理自己造成的混乱。**

编辑已有代码时：
- 不要"改进"相邻的代码、注释或格式。
- 不要重构没坏的东西。
- 匹配已有风格，即使你更倾向于不同的写法。
- 如果注意到无关的死代码，提一下——不要删除它。

当你的改动产生孤儿时：
- 删除因你的改动而不再使用的导入/变量/函数。
- 不要删除已存在的死代码，除非被要求。

检验标准：每一行被改动代码都应该能直接追溯到用户的请求。

### 守则 4：目标驱动执行

**定义成功标准。循环验证直到达成。**

将任务转化为可验证的目标：
- "添加校验" → "先写非法输入测试用例，再让它们通过"
- "修 bug" → "先写一个能复现的测试，再让它通过"
- "重构 X" → "确保重构前后测试都通过"

对于多步骤任务，陈述简要计划：
```
1. [步骤] → 验证: [检查点]
2. [步骤] → 验证: [检查点]
3. [步骤] → 验证: [检查点]
```

强成功标准让你能独立循环推进。弱标准（"让它能工作"）需要不断澄清。

**这些准则生效的标志：** diff 中不必要的改动变少、因过度复杂导致的返工变少、澄清性问题在实施前出现而非在犯错后。

---

## 项目信息

Project: saihu-data-pipeline — 赛狐/ERPNext/通途 数据一致性维护 Python 工具集。

## Five independent modules

Each module runs from its own directory (`os.chdir()` on startup), has **no code dependencies** on each other (except `category` dynamically imports `_default_spu_from_sku` from `multi_attr_saihu/erpnext_to_saihu.py`).

| Module | Script(s) | Purpose |
|--------|-----------|---------|
| `multi_attr_saihu/` | `erpnext_to_saihu.py`, `erp_tongtu_bridge.py`, `tongtu_sku_explode.py` | ERPNext/Tongtu → Saihu multi-attribute product import |
| `category/` | `build_saihu_category_import.py` | EN material attributes + Saihu category tree → 4-level category import |
| `item_cost_sx/` | `bom_cost_to_saihu_item_cost.py` | EN BOM cost → Saihu purchase cost import |
| `item_weight_size/` | `build_saihu_weight_import.py` | EN weight template → Saihu product size/weight import |
| `stock_init/` | `build_saihu_stock_init.py` | Tongtu multi-warehouse inventory + EN BOM cost → Saihu stock initial-value import |

Each module has a `README.md` (for humans) and an `AGENT_HANDOFF.md` (for AI agents). Read both before modifying code.

## Tech stack

- Python >= 3.10, managed with **uv** (`pyproject.toml` at root)
- `pandas` for DataFrame operations, `openpyxl` for Excel read/write
- No packaging — standalone scripts run with `python script.py` from module directories

## Common commands

```bash
uv sync                          # install pandas, openpyxl
cd <module_dir> && python <script>.py   # run any script
```

## Code conventions

- **Column names in Chinese**: Excel column headers are Chinese strings. Column name constants use UPPER_CASE (e.g. `COL_SKU = "产品编号"`, `SAI_HU_SHEET = "商品"`).
- **`os.chdir()` pattern**: Each script changes `os.getcwd()` to the script's directory at startup. Run scripts from their own directory.
- **Cross-module imports**: `category/build_saihu_category_import.py` uses `importlib.util` to dynamically import `_default_spu_from_sku` from `multi_attr_saihu/erpnext_to_saihu.py`. No other cross-module dependencies exist.
- **Auto file selection**: Scripts auto-select input files (latest by `st_mtime`, excluding `~$` lock files) when CLI args are omitted.
- **Excel output**: All `.xlsx` outputs are gitignored. Scripts write timestamped filenames (`*_YYYYMMDD_HHMMSS.xlsx`).

## Git conventions

- Commit messages in **Chinese**
- Format: `type(scope): description` (conventional commits style)
- Common types: `feat`, `fix`, `docs`, `init`, `refactor`

### Git workflow (standard process)

1. Development happens on the **worktree branch** (e.g. `claude/romantic-chaplygin-47fe9f`), NOT directly on `master`
2. After verifying the change works, merge into `master`:
   ```bash
   cd D:\Work\赛狐\Cursor
   git checkout master
   git merge claude/romantic-chaplygin-47fe9f
   ```
3. Sync the worktree branch back to master so it stays current:
   ```bash
   cd .claude/worktrees/romantic-chaplygin-47fe9f
   git merge master
   ```
4. Never commit directly to `master` from the worktree — use the branch

## Lessons learned / Pitfalls

Recorded mistakes and gotchas to avoid repeating:

### 1. Auto file selection: keyword specificity
- **Problem**: `_find_file("重尺")` matched the template file `模板 商品重尺-*.xlsx` because "商品重尺" contains "重尺"
- **Fix**: Use the most specific keyword possible (e.g. `"重尺数据"` not `"重尺"`). Verify each keyword matches exactly one intended file
- **Rule**: When adding auto-selection, test that each file pattern matches only its intended file

### 2. Directory naming: similar names cause confusion
- **Problem**: Created `item_size_weight/` (code) alongside `item_weight_size/` (data) — names differ by one underscore position
- **Fix**: Unified to `item_weight_size/` only, with data in `./数据源/` subdirectory
- **Rule**: Keep code and data under one module directory. Use subdirectories like `数据源/` for inputs, `out/` for outputs

### 3. Module structure convention
Each module follows this layout:
```
module_dir/
├── <script>.py          # main script
├── README.md            # human documentation
├── AGENT_HANDOFF.md     # AI agent context
├── __init__.py          # empty, for uv build
├── 数据源/              # input Excel files (gitignored)
└── out/                 # output files (gitignored)
```

### 4. 赛狐 import template: worksheet name
- **Problem**: `openpyxl` defaults to writing a sheet named `Sheet1`, but 赛狐 requires exactly `商品`
- **Fix**: Always set the worksheet name to `商品` explicitly (constant `SAI_HU_SHEET = "商品"`)
- **Affects**: All modules that generate 赛狐 import files

### 5. 赛狐 purchase cost: zero equals empty
- **Rule**: 赛狐 treats `采购成本=0` the same as empty — it will NOT import 0 values
- **Fix**: Generate two output files: import file (filter out cost=0), reference file (keep all). Use clear filenames to prevent mix-up
- **Confirmed**: 2026-05-14 实测验证，赛狐导入文件含成本=0的行会静默跳过
- **Pattern used by**: `item_cost_sx`, `stock_init`

### 6. SKU matching by prefix (shared across modules)
- **Concept**: SKU format is `款式ID-面料-尺寸-颜色` (4 segments). The first 3 segments (`款式ID-面料-尺寸`) define a "group key"
- **Weight template**: `ZLMB#KS0368-CTTM-270x180x60` — strip `ZLMB#` → 3-segment key
- **Cost borrowing** (item_cost_sx): Same 3-segment key = same cost
- **Weight matching** (item_weight_size): Same 3-segment key = same weight/size
- **Rule for ≥4 segments**: key = `"-".join(parts[:3])`
- **Rule for exactly 3 segments**: key = whole SKU (no color)
- **Rule for <3 segments**: no match possible

### 7. Excel file locking
- **Problem**: `~$*.xlsx` lock files appear when Excel is open, causing `PermissionError`
- **Fix**: Always exclude `~$` prefixed files in auto-selection. If a file can't be moved/deleted, it's probably locked — close Excel first

### 8. uv environment
- **Problem**: `uv sync` can fail to rebuild if old `.venv` has stale build artifacts
- **Fix**: `rm -rf .venv && uv sync` to rebuild cleanly
- **Shared venv**: The entire project uses ONE `.venv` at repo root. All modules share the same pandas/openpyxl installation
- **`uv run` vs direct python**: `uv run python` creates the venv on first use; subsequent runs use cached venv

### 9. Keep this document updated
- **Rule**: Every time a new mistake is made and fixed, or a new convention is established, add an entry to this Lessons Learned section **immediately**
- **Rule**: When a module's behavior, data flow, or conventions change, update both this CLAUDE.md and the module's README.md / AGENT_HANDOFF.md
- **Rule**: This document is the first thing every AI agent reads. Stale information here causes repeated mistakes
- **Commit message**: `docs: CLAUDE.md <what changed>`

### 10. Module docs must follow code changes
- **Rule**: When modifying a module's `.py` script, check if its `README.md` or `AGENT_HANDOFF.md` need updating. At minimum:
  - Column name constants changed → update both docs
  - Default paths changed → update both docs
  - Business rules changed → update both docs
  - New CLI args added → update both docs
- **Consequence of not doing this**: Future agents (and humans) will use wrong column names, wrong paths, or misunderstand the business logic — causing bugs that look like "the script is broken" but are actually documentation drift
- **Checklist before committing any `.py` change**:
  1. Did I change any `COL_*` constant? → grep the md files for the old column name
  2. Did I change any `_DEFAULT_*` path? → grep the md files for the old path
  3. Did I add/remove a CLI argument? → update the usage section in README.md
  4. Did I change a calculation rule? → update the business rules section in both docs

### 11. Data source origins (who provides each Excel)
When debugging missing columns or format changes, knowing which system produces each file is essential:

| 数据文件 | 来源系统 | 导出/操作人 | 关键列可能变动 |
|----------|----------|------------|--------------|
| 物料导出 (含/不含 通途SKU) | ERPNext | 开发者导出 | 属性列名、物料编码格式 |
| 通途普通商品 | 通途 | 运营导出 | SKU别名格式 |
| 赛狐商品导出 | 赛狐 Saihu | 运营导出 | 列顺序、新增列 |
| 赛狐导入模板 | 赛狐 Saihu | 运营下载 | 列名固定（按赛狐规范） |
| 商品分类导出 | 赛狐 Saihu | 运营导出 | 分类层级列名 |
| EN物料属性 | ERPNext (EN) | 开发者维护 | 款式ID、在售、赛狐分类 |
| BOM 成本列表 | ERPNext (EN) | 开发者导出 | Query Report 列名 |
| 重量模板 (手工) | ERPNext + 人工 | 同事下载后手工填 | 手填列名由同事约定 |
| 通途合并库存结存清单 | 通途 | 运营导出 | 仓库列名、SKU格式 |

### 12. Left-merge / SKU whitelist pattern
- **Pattern used by**: `item_cost_sx`, `item_weight_size`, `stock_init`
- **Concept**: 赛狐 already has a fixed set of SKUs. The import file must contain exactly those SKUs — no more, no fewer
- **Implementation**: Read 赛狐商品导出 → get `set(SKU)` → use as whitelist. Left-join saihu SKUs to source data. Unmatched saihu rows get empty values; unmatched source rows are reported but excluded from the import sheet
- **Why**: 赛狐 will reject imports with SKUs not in its system, but will also skip updating SKUs not in the import file

### 13. openpyxl destroys Data Validation on save
- **Problem**: `openpyxl.load_workbook(template) → ws.delete_rows/write → wb.save()` caused 赛狐 import to fail silently. 赛狐 confirmed the xlsx "格式有问题". Manually opening in Excel and re-saving fixed it
- **Root cause**: openpyxl issues warning "Data Validation extension is not supported and will be removed" when loading, and does NOT preserve it on save. 赛狐 templates have data validation (dropdown cells for g/kg/oz/lb) that gets lost
- **Fix**: Do NOT use `openpyxl.load_workbook()` + `wb.save()` for 赛狐 import outputs. Instead:
  - For outputs needing hidden sheets: `shutil.copy(template) → pd.ExcelWriter(mode='a', if_sheet_exists='replace') → to_excel()`
  - For outputs NOT needing hidden sheets: just `pd.ExcelWriter() → to_excel(sheet_name='商品')`
- **Affects**: ALL modules that generate 赛狐 import files from templates
- **Verified fix**: `item_weight_size` — tested and confirmed working with 赛狐 import. Other modules with same pattern need the same fix

### 14. Template-based output writing (DEPRECATED — see #13)
- **Old pattern** (do NOT use): `openpyxl.load_workbook(template) → modify → wb.save()`
- **New pattern**: `shutil.copy(template, out) → pd.ExcelWriter(out, mode='a') → to_excel(sheet_name='商品')` or just `pd.ExcelWriter() → to_excel(sheet_name='商品')` if hidden sheets aren't needed
- **Rule**: 赛狐 templates may contain hidden sheets and data validation, but the data validation is NOT essential for import. What matters is the correct sheet name (`商品`) and column headers

### 15. Windows + Chinese path encoding
- **Problem**: Shell commands with Chinese paths fail with `UnicodeEncodeError` or garbled output
- **Fix**: Use `PYTHONIOENCODING=utf-8` env var, or use Python's `pathlib` to handle files instead of shell `mv`/`cp`
- **Rule**: For file operations involving Chinese filenames, prefer Python (`shutil`, `pathlib`) over shell commands
- **CRLF warnings**: Expected on Windows, harmless. Git auto-converts LF→CRLF on checkout

### 16. uv.lock is committed
- **Rule**: `uv.lock` IS tracked in git. It locks dependency versions for reproducibility
- **Regenerate**: Run `uv lock` (or `uv sync`) after changing `pyproject.toml` dependencies. Commit the updated `uv.lock`

### 17. 赛狐库存共享策略 (Shared Inventory)
- **Problem**: 入库时如果填了店铺/FNSKU（专属库存），后续成本补录单必须匹配全部字段（仓库+SKU+店铺+FNSKU）。补录导入时任一维度不匹配就失败（实测：加了店铺但缺FNSKU仍失败）
- **Fix**: 开局和日常入库一律使用**共享库存**——店铺、FNSKU 留空。这样成本补录单只需仓库+SKU即可定位并修正成本
- **Rule**: 如果不需要店铺/FNSKU 维度的库存区分，就不要在入库时填写它们。共享库存是"最简单调账"的基础
- **Confirmed by**: 赛狐客服回复 + POLAND仓实战测试验证（2026-05-14）+ 三次导入测试（2026-05-15）：A→成功，B新增→成功，B中已存在行→失败（库存初始值导入拒绝已有库存的SKU，符合预期）

### 18. 成本借用策略 (Cost Borrowing by Weight Template)
- **Problem**: EN BOM 成本列表中，部分产品在目标仓库的成本列为 0。但这些产品与有成本的产品共享同一个「重量模板, 编号」（同款式-面料-尺寸，仅颜色不同）
- **Source column**: EN 中的 `重量模板, 编号`（如 `ZLMB#KS0001-CMGDTH-100`），去除 `ZLMB#` 前缀得键
- **Rule**: 每列独立借用。同重量模板键、同成本列内 0→非零。**纯列内操作，不跨列，不限制发货方式**
- **⚠️ 不精确借用**：颜色变体可能有不同物流属性。借用记录在问题报告 `成本借用记录` sheet 中全量记录
- **Apply to**: `stock_init` 模块

### 19. 输出文件拆分
- **Problem**: 赛狐导入文件和参考查看文件混在一起容易用错，导入含0成本行会被赛狐静默跳过
- **Pattern**: 生成两个文件——导入用（过滤掉不允许的值）+ 参考用（全量）。文件名需有明确区分词（如 `_导入_` vs `_全量参考_`）
- **Applied by**: `stock_init` (过滤成本=0), `item_cost_sx` (过滤成本=0)

### 20. 问题报告统一格式
- **Problem**: 早期脚本输出 `.txt` 报告，信息扁平无结构，不方便筛选和分析
- **Fix**: 所有模块的问题报告统一为多 sheet 的 `.xlsx`，参照 `item_weight_size` 的 `_write_issues()` 模式：每个 sheet 对应一个问题类别，含明细列。空 sheet 写占位行「（无数据）」
- **Pattern**: `汇总` sheet（单行多列总览）+ N 个明细 sheet（每个处理节点可能产生的边界问题）+ `每仓统计` sheet（按仓库维度汇总）
- **Rule**: 新模块的问题报告都用此格式。不要用 txt/md/csv
- **Detail sheets 应包含产品名称列**：方便人工审核时定位产品

## Module docs location

Human-readable README.md and agent-oriented AGENT_HANDOFF.md live in each module directory. Read both files before modifying any script — they contain business rules, data flow details, CLI reference, and known issues that are not repeated here.

When you modify a module's `.py` script, check the module's README.md and AGENT_HANDOFF.md for stale content — see Lesson #10 above.
