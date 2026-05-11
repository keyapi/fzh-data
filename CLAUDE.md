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
- Common types: `feat`, `fix`, `docs`, `init`

## Module docs location

Human-readable README.md and agent-oriented AGENT_HANDOFF.md live in each module directory. Read both files before modifying any script — they contain business rules, data flow details, CLI reference, and known issues that are not repeated here.
