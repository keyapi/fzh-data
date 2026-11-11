"""只读历史库存：源间不去重相加，历史不能成为当前库存或销量。"""
from pathlib import Path

import duckdb
import pandas as pd

# 已确认的波兰历史改名。其他子仓保留角色，不合并进主仓可售数。
ALIASES = {
    "FZHPoland-covers": ("波兰-FZHPoland-covers", "波兰", "covers_alias"),
    "波兰-FZHPoland-covers": ("波兰-FZHPoland-covers", "波兰", "exact"),
    "波兰仓": ("波兰-FZHPoland-covers", "波兰", "brief_confirmed_consolidated_covers"),
    "CENTRADE": ("美东-CENTRADE", "USNJ", "legacy_alias"),
    "美东仓": ("美东-CENTRADE", "USNJ", "historical_consolidated"),
    "美东-CENTRADE": ("美东-CENTRADE", "USNJ", "exact"),
    "美中仓": ("美中-FZH-DANEEY", "USTX", "historical_consolidated"),
    "美中-FZH-DANEEY": ("美中-FZH-DANEEY", "USTX", "exact"),
}
for _warehouse in ("FZH-DANEEY-半成品仓", "FZH-DANEEY-成品仓", "FZH-DANEEY-皮壳仓库",
                   "FZH-DANEEY-退货产品仓", "美中-FZH-DANEEY-退货产品仓"):
    ALIASES[_warehouse] = (_warehouse, "USTX", "historical_subwarehouse_not_merged")
TABLES = {"wx_inventory_history.duckdb": "wx_inventory.observations",
          "pengjian_inventory_history.duckdb": "pengjian_inventory.daily_snapshot"}


def load_history(paths, as_of):
    frames, audits = [], []
    end = pd.Timestamp(as_of).date()
    for path in paths:
        path = Path(path)
        table = TABLES[path.name]  # 固定白名单；用户输入不拼入 SQL 表名
        with duckdb.connect(str(path), read_only=True) as con:
            columns = {r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()}
            required = {"source_file", "source_sha256", "snapshot_date", "warehouse_raw", "sku", "available"}
            if not required <= columns:
                raise ValueError(f"{path.name}: missing history columns {required-columns}")
            counts = con.execute(f"SELECT count(*), count(*) FILTER (WHERE snapshot_date > ?), "
                                 f"count(*) FILTER (WHERE snapshot_date IS NULL) FROM {table}",
                                 [end]).fetchone()
            provenance = ",".join(f'"{col}"' if col in columns else f'NULL AS "{col}"'
                                  for col in ["source_row", "sheet", "snapshot_at"])
            a = con.execute(f"SELECT source_file,source_sha256,snapshot_date,warehouse_raw,sku,available,{provenance} "
                            f"FROM {table} WHERE snapshot_date <= ?", [end]).fetchdf()
        a["source"] = f"{path.name}:{table}"
        a["warehouse"] = a.warehouse_raw.map(lambda s: ALIASES.get(s, (s, None, "unmapped"))[0])
        a["customer"] = a.warehouse_raw.map(lambda s: ALIASES.get(s, (s, None, "unmapped"))[1])
        a["warehouse_basis"] = a.warehouse_raw.map(lambda s: ALIASES.get(s, (s, None, "unmapped"))[2])
        a["warehouse_role"] = a.warehouse_raw.map(
            lambda s: "return" if "退货" in str(s) else "semi" if "半成品" in str(s)
            else "cover" if "皮壳" in str(s) or "covers" in str(s) else "historical_observation")
        a["node"] = "historical_available_observation"
        a["qty"] = a.available
        a["uom"] = None  # 历史导出未提供逐 SKU 的单位证明
        a["as_of"] = as_of
        a["additive_with_current"] = False
        key = ["source", "snapshot_date", "warehouse_raw", "sku"]
        duplicated = a.duplicated(key, keep=False)
        a["duplicate_observation"] = duplicated
        # 全部保留，不把重复/多源同日数据求和或当成流量。
        audits.append(dict(source=f"{path.name}:{table}", input_rows=counts[0],
                           retained_rows=len(a), future_rows=counts[1], unknown_date_rows=counts[2],
                           snapshot_dates=a.snapshot_date.nunique(),
                           first_date=str(a.snapshot_date.min()), last_date=str(a.snapshot_date.max()),
                           duplicate_rows=int(duplicated.sum()),
                           unmapped_warehouse_rows=int(a.customer.isna().sum()),
                           unknown_qty_rows=int(a.available.isna().sum()),
                           quantity_is_stock_observations_not_flow=True))
        if len(a) + counts[1] + counts[2] != counts[0]:
            raise ValueError("history input disposition does not conserve rows")
        frames.append(a)
    return pd.concat(frames, ignore_index=True), audits
