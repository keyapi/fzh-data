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

## Module docs location

Human-readable README.md and agent-oriented AGENT_HANDOFF.md live in each module directory. Read both files before modifying any script — they contain business rules, data flow details, CLI reference, and known issues that are not repeated here.
