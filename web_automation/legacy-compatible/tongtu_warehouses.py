"""Shared Tongtu main-line warehouse names (2026-09 rename)."""

WAREHOUSES = [
    "美东-CENTRADE",
    "波兰-FZHPoland-covers",
    "美中-FZH-DANEEY",
    "美东-CENTRADE-退货产品仓",
    "波兰-FZHPoland-退货产品仓",
    "美中-FZH-DANEEY-退货产品仓",
]

MAIN_SHEETS = frozenset(WAREHOUSES)


def safe_prefix(name: str) -> str:
    return name.replace("/", "-").replace("\\", "-").replace(":", "-")


def inventory_download_matches_warehouse(filename: str, warehouse_name: str) -> bool:
    """Match inventory XLSX for exactly one warehouse (not a longer-prefix sibling)."""
    if not filename.endswith(".xlsx"):
        return False
    return filename.startswith(f"{safe_prefix(warehouse_name)}_")
