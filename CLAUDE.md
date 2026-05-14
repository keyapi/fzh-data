# CLAUDE.md

Project: saihu-data-pipeline — 赛狐/ERPNext/通途 数据一致性维护 Python 工具集。

## Four independent modules

Each module runs from its own directory (`os.chdir()` on startup), has **no code dependencies** on each other (except `category` dynamically imports `_default_spu_from_sku` from `multi_attr_saihu/erpnext_to_saihu.py`).

| Module | Script(s) | Purpose |
|--------|-----------|---------|
| `multi_attr_saihu/` | `erpnext_to_saihu.py`, `erp_tongtu_bridge.py`, `tongtu_sku_explode.py` | ERPNext/Tongtu → Saihu multi-attribute product import |
| `category/` | `build_saihu_category_import.py` | EN material attributes + Saihu category tree → 4-level category import |
| `item_cost_sx/` | `bom_cost_to_saihu_item_cost.py` | EN BOM cost → Saihu purchase cost import |
| `item_weight_size/` | `build_saihu_weight_import.py` | EN weight template → Saihu product size/weight import |

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
- **Fix**: Use `_openpyxl_clear_column_nan()` to post-process and nullify zeros in the cost column before saving

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

### 12. Left-merge / SKU whitelist pattern
- **Pattern used by**: `item_cost_sx`, `item_weight_size`
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

## Module docs location

Human-readable README.md and agent-oriented AGENT_HANDOFF.md live in each module directory. Read both files before modifying any script — they contain business rules, data flow details, CLI reference, and known issues that are not repeated here.

When you modify a module's `.py` script, check the module's README.md and AGENT_HANDOFF.md for stale content — see Lesson #10 above.
