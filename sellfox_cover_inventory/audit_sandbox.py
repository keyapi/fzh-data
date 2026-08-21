"""Read-only audit for one Sellfox cover shared-inventory sandbox."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SELLFOX_API_DIR = ROOT / "SELLFOX_API"
if str(SELLFOX_API_DIR) not in sys.path:
    sys.path.insert(0, str(SELLFOX_API_DIR))


REQUIRED_FIELDS = (
    "warehouse_name",
    "tongtool_base_sku",
    "sellfox_bottom_sku",
    "sellfox_cover_sku",
)


@dataclass(frozen=True)
class SandboxConfig:
    warehouse_name: str
    tongtool_base_sku: str
    sellfox_bottom_sku: str
    sellfox_cover_sku: str
    tongtool_cover_sku: str = ""
    listing_msku: str = ""
    shop_name: str = ""


def parse_config(raw: Any) -> SandboxConfig:
    if not isinstance(raw, dict):
        raise ValueError("config must be one JSON object, not a list or batch")
    missing = [name for name in REQUIRED_FIELDS if not str(raw.get(name) or "").strip()]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    unknown = sorted(set(raw) - set(SandboxConfig.__dataclass_fields__))
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(unknown)}")
    values = {name: str(raw.get(name) or "").strip() for name in SandboxConfig.__dataclass_fields__}
    cfg = SandboxConfig(**values)
    if cfg.sellfox_bottom_sku == cfg.sellfox_cover_sku:
        raise ValueError("bottom and cover Sellfox SKUs must differ")
    return cfg


def is_combo_group(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true"}


def is_normal_group(value: Any) -> bool:
    return str(value).strip().lower() in {"0", "false"}


def page_total(data: Any) -> Any:
    if not isinstance(data, dict):
        return None
    for key in ("totalSize", "total", "totalCount"):
        if data.get(key) is not None:
            return data[key]
    return None


def validate_warehouse(warehouse: dict[str, Any] | None, name: str) -> list[str]:
    if warehouse is None:
        return []
    problems: list[str] = []
    wh_type = str(warehouse.get("type") if warehouse.get("type") is not None else "")
    if wh_type == "2":
        problems.append(f"warehouse {name!r} is FBA (type=2); cover shared pool cannot use FBA")
    if "退货" in name or "不良" in name:
        problems.append(f"warehouse {name!r} looks like a return/defective warehouse")
    return problems


def warehouse_cautions(name: str) -> list[str]:
    """Flag branch warehouses that are not the confirmed cover pool.

    USTX: names containing DANEEY without 皮壳/cover may be main/finished.
    Poland: Sellfox POLAND maps to Tongtu covers, not finished; only warn
    when the name looks like the finished warehouse.
    """
    raw = (name or "").strip()
    if not raw:
        return []
    lower = raw.casefold()
    if any(token in raw for token in ("皮壳", "退货", "不良")):
        return []
    if "cover" in lower:
        return []
    notes: list[str] = []
    if "daneey" in lower:
        notes.append(
            "USTX/DANEEY 主仓或成品仓未必存放三角皮壳；通途另有皮壳仓库，须用户确认后再当共享池"
        )
    if ("poland" in lower or "fzhpoland" in lower) and (
        "finished" in lower or "成品" in raw
    ):
        notes.append(
            "波兰成品仓 FZHPoland-finished 不是皮壳共享池；赛狐 POLAND 对应通途 covers 仓"
        )
    return notes


def rows_from_page(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("rows", "list", "records"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def find_unique(rows: list[dict[str, Any]], field: str, value: str) -> tuple[str, dict[str, Any] | None]:
    matches = [row for row in rows if str(row.get(field) or "") == value]
    if not matches:
        return "missing", None
    if len(matches) > 1:
        return "blocked_duplicate", None
    return "matched", matches[0]


def validate_cover_relation(
    cover: dict[str, Any] | None, bottom_sku: str
) -> list[str]:
    if cover is None:
        return ["cover SKU does not exist; creation requires separate user approval"]
    problems: list[str] = []
    if not is_combo_group(cover.get("isGroup")):
        problems.append(f"cover isGroup must be 1, got {cover.get('isGroup')!r}")
    children = cover.get("childSkus")
    if not isinstance(children, list) or len(children) != 1:
        problems.append("cover must have exactly one child SKU")
        return problems
    child = children[0] if isinstance(children[0], dict) else {}
    if str(child.get("sku") or "") != bottom_sku:
        problems.append("cover child SKU does not match the configured bottom SKU")
    qty = child.get("num", child.get("qty"))
    try:
        if float(qty) != 1:
            problems.append(f"cover child quantity must be 1, got {qty!r}")
    except (TypeError, ValueError):
        problems.append(f"cover child quantity is invalid: {qty!r}")
    return problems


def make_plan(cfg: SandboxConfig) -> dict[str, Any]:
    return {
        "input": 1,
        "mode": "config_only",
        "config": asdict(cfg),
        "proposed_model": {
            "inventory_source": cfg.tongtool_base_sku,
            "sellfox_stocked_product": cfg.sellfox_bottom_sku,
            "sellfox_cover_alias": cfg.sellfox_cover_sku,
            "required_relation": f"{cfg.sellfox_cover_sku} -> {cfg.sellfox_bottom_sku} x1",
        },
        "matched": 0,
        "missing": 0,
        "blocked": 0,
        "cautions": warehouse_cautions(cfg.warehouse_name),
        "notes": [
            "No production reads or writes were performed.",
            "Tongtool target-pool arithmetic is intentionally not inferred.",
        ],
    }


def live_audit(cfg: SandboxConfig) -> dict[str, Any]:
    from client import SellfoxClient, SellfoxConfig

    client = SellfoxClient(SellfoxConfig.from_env(ROOT / ".env", ROOT / "SELLFOX_API" / ".env"))
    warehouse_data = client.signed_post(
        "/api/warehouseManage/warehouseList.json",
        {"pageNo": 1, "pageSize": 200},
    )
    product_data = client.signed_post(
        "/api/commodity/pageList.json",
        {
            "pageNo": "1",
            "pageSize": "50",
            "skus": [cfg.sellfox_bottom_sku, cfg.sellfox_cover_sku],
        },
    )
    processing_data = client.signed_post(
        "/api/commodity/pageList.json",
        {"pageNo": "1", "pageSize": "1", "isGroup": "2"},
    )

    warehouses = rows_from_page(warehouse_data)
    products = rows_from_page(product_data)
    warehouse_status, warehouse = find_unique(warehouses, "name", cfg.warehouse_name)
    bottom_status, bottom = find_unique(products, "sku", cfg.sellfox_bottom_sku)
    cover_status, cover = find_unique(products, "sku", cfg.sellfox_cover_sku)
    problems = validate_cover_relation(cover, cfg.sellfox_bottom_sku)
    problems.extend(validate_warehouse(warehouse, cfg.warehouse_name))
    if bottom is not None and not is_normal_group(bottom.get("isGroup")):
        problems.append(f"bottom isGroup must be 0, got {bottom.get('isGroup')!r}")
    if warehouse_status.startswith("blocked") or bottom_status.startswith("blocked") or cover_status.startswith("blocked"):
        problems.append("duplicate Sellfox records block the sandbox")

    missing = sum(status == "missing" for status in (warehouse_status, bottom_status, cover_status))
    processing_total = page_total(processing_data)

    return {
        "input": 1,
        "mode": "sellfox_read_only",
        "config": asdict(cfg),
        "checks": {
            "warehouse": {
                "status": warehouse_status,
                "id": (warehouse or {}).get("id"),
                "type": (warehouse or {}).get("type"),
            },
            "bottom_sku": {"status": bottom_status, "isGroup": (bottom or {}).get("isGroup")},
            "cover_sku": {"status": cover_status, "isGroup": (cover or {}).get("isGroup")},
            "processing_product_account_count": processing_total,
        },
        "matched": sum(status == "matched" for status in (warehouse_status, bottom_status, cover_status)),
        "missing": missing,
        "blocked": len(problems),
        "blocked_reasons": problems,
        "cautions": warehouse_cautions(cfg.warehouse_name),
        "next_actions": [
            "Confirm the ordinary warehouse contains saleable covers.",
            "Confirm Tongtool available-stock reservation and synchronization timing.",
            "Obtain approval before any create, pairing, inventory adjustment, or test order.",
            "Do not treat child KS warehouse FIFO or PK# purchaseCostLock as cover profit; EN Cost Review suffix slices are out of scope for this audit.",
        ],
        "write_operations": 0,
    }


def write_report(report: dict[str, Any], output: Path | None) -> Path:
    if output is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = ROOT / "sellfox_cover_inventory" / "out" / f"sandbox_audit_{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="single-sandbox JSON config")
    parser.add_argument("--live", action="store_true", help="perform Sellfox read-only API checks")
    parser.add_argument("--output", type=Path, help="report JSON path")
    args = parser.parse_args()

    cfg = parse_config(json.loads(args.config.read_text(encoding="utf-8-sig")))
    report = live_audit(cfg) if args.live else make_plan(cfg)
    path = write_report(report, args.output)
    print(json.dumps({"report": str(path), **{k: report[k] for k in ("input", "matched", "missing", "blocked") if k in report}, "cautions": len(report.get("cautions") or [])}, ensure_ascii=False))
    return 2 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
