"""Migrated script inventory: entrypoints exist, parse, and carry no external repo path."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_AUTO = ROOT / "web_automation"

EXPECTED = [
    "legacy-compatible/tongtu_auto_export.py",
    "legacy-compatible/tongtu_sales_report.py",
    "legacy-compatible/process_sales_report.py",
    "legacy-compatible/generate_tongtu_import.py",
    "legacy-compatible/merge_inventory.py",
    "legacy-compatible/inspect_warehouse.py",
    "legacy-compatible/mcp_to_output.py",
    "legacy-compatible/sellfox_auto_export.py",
    "legacy-compatible/sellfox_import_update.py",
    "legacy-compatible/sellfox_restock_api.py",
    "legacy-compatible/commodity_import_template.py",
    "legacy-compatible/ddddocr_login.py",
    "legacy-compatible/tongtu_login_ocr.py",
    "legacy-compatible/sellfox_login_ocr.py",
    "legacy-compatible/tongtu_export_ocr.py",
    "legacy-compatible/test_ocr.py",
    "click-based/sellfox_import_other_inbound.py",
    "click-based/sellfox_import_other_outbound.py",
    "click-based/sellfox_import_warehouse_restock.py",
    "click-based/sellfox_restock_allocate_ship.py",
    "click-based/sellfox_restock_receive.py",
    "click-based/sellfox_import_update.py",
    "click-based/commodity_import_template.py",
]


def test_expected_scripts_exist_and_parse():
    missing = [rel for rel in EXPECTED if not (WEB_AUTO / rel).is_file()]
    assert not missing, f"missing: {missing}"
    for rel in EXPECTED:
        ast.parse((WEB_AUTO / rel).read_bytes(), filename=rel)


def test_no_python_file_references_external_repo():
    offenders = []
    for py in WEB_AUTO.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="replace")
        if "D:\\Work\\赛狐\\网页自动化" in text or "D:/Work/赛狐/网页自动化" in text:
            offenders.append(str(py.relative_to(ROOT)))
    assert not offenders, f"external path references: {offenders}"


def test_capability_implementations_exist():
    import yaml

    matrix = yaml.safe_load((WEB_AUTO / "capabilities.yaml").read_text(encoding="utf-8"))
    missing = []
    for task, body in matrix["capabilities"].items():
        for impl in (body.get("implementation") or {}).values():
            if not isinstance(impl, str) or impl in {"playwright"}:
                continue
            target = WEB_AUTO / impl
            if not target.is_file():
                missing.append(f"{task}: {impl}")
    assert not missing, f"capability impl missing: {missing}"
