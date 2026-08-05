"""Local Excel walkthrough: export approved 蜴 packages; optional import roundtrip."""
from __future__ import annotations

import json
from pathlib import Path

from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
from sellfox_shipping.lizard_batch import (
    ExportLizardUploadService,
    ImportLizardTrackingService,
    LizardExportRequest,
    LizardImportRequest,
)
from sellfox_shipping.package_repository import PackageRepository

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "shipping.db"
OUT = ROOT / "out" / "excel_walkthrough"
ACCOUNT = "sellfox-main"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    repo = PackageRepository(DB)
    # Prefer packages already approved with 蜴 in channel; else seed nothing — use real DB
    import sqlite3

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        """
        SELECT package_sn, local_review_status, channel_name, package_status
        FROM shipping_packages
        WHERE channel_name LIKE '%蜴%' OR channel_name LIKE '%lizard%'
           OR channel_name LIKE '%Lizard%'
        ORDER BY id DESC LIMIT 30
        """
    ).fetchall()
    print("lizard_channel_candidates", len(rows))
    for r in rows[:10]:
        print(dict(r))

    # Ensure at least one approved with dims for export smoke on a copy? Use StaticDimsLookup for all SKUs
    dims = StaticDimsLookup(
        {
            "*": CartonDims(
                weight_kg=2.0, length_cm=25, width_cm=20, height_cm=15
            )
        }
    )
    # StaticDimsLookup may not support *; check API
    from sellfox_shipping.carriers.lizard.dims import DimsLookup

    class AnyDims(DimsLookup):
        def get(self, commodity_sku: str) -> CartonDims | None:
            return CartonDims(
                weight_kg=2.0, length_cm=25, width_cm=20, height_cm=15
            )

    # Reset previously approved has_shipped so export only hits to_process empties
    for r in rows:
        if (
            r["package_status"] == "has_shipped"
            and r["local_review_status"] == "approved"
        ):
            repo.set_local_review_status(
                account_key=ACCOUNT,
                package_sn=r["package_sn"],
                local_review_status="pending",
            )

    # Prefer to_process without real tracking for clean persist roundtrip
    preferred = [r for r in rows if r["package_status"] == "to_process"]
    pool = preferred if preferred else list(rows)

    approved = []
    for r in pool:
        sn = r["package_sn"]
        rec = repo.get(ACCOUNT, sn)
        if rec and rec.logistics.tracking_number and rec.logistics.tracking_number != sn:
            print("skip_has_track", sn, rec.logistics.tracking_number)
            continue
        if (rec.local_review_status if rec else r["local_review_status"]) != "approved":
            try:
                repo.set_local_review_status(
                    account_key=ACCOUNT,
                    package_sn=sn,
                    local_review_status="approved",
                )
            except Exception as exc:  # noqa: BLE001
                print("approve_fail", sn, exc)
                continue
        approved.append(sn)
        if len(approved) >= 5:
            break
    print("approved_for_export", approved)

    out_xlsx = OUT / "lizard-upload-walkthrough.xlsx"
    result = ExportLizardUploadService(repo, AnyDims()).export(
        LizardExportRequest(
            account_key=ACCOUNT,
            actor="excel-walkthrough",
            output_path=out_xlsx,
            limit=50,
            shipper_code="S0143",
        )
    )
    summary = {
        "exported": result.exported,
        "skipped": result.skipped,
        "total_candidates": result.total_candidates,
        "batch_id": result.batch_id,
        "output": str(out_xlsx) if out_xlsx.exists() else None,
        "skipped_rows_sample": (result.skipped_rows or [])[:5],
    }
    print("export", json.dumps(summary, ensure_ascii=False, default=str))

    if result.exported == 0 or not out_xlsx.exists():
        (OUT / "REPORT.json").write_text(
            json.dumps({"export": summary, "import": None}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 0

    # Build a minimal return workbook from export for roundtrip (客户参考号 + 物流单号)
    import pandas as pd

    upload = pd.read_excel(out_xlsx)
    # Find reference + invent tracking
    ref_col = None
    for cand in ("参考编号", "Reference Code", "客户参考号"):
        if cand in upload.columns:
            ref_col = cand
            break
    if ref_col is None:
        # try first col containing 参考
        for col in upload.columns:
            if "参考" in str(col) or "Reference" in str(col):
                ref_col = col
                break
    print("upload_cols", list(upload.columns)[:15], "ref_col", ref_col)
    if ref_col is None:
        (OUT / "REPORT.json").write_text(
            json.dumps(
                {"export": summary, "import": {"error": "no ref col"}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return 1

    ret = pd.DataFrame(
        {
            "参考编号/Reference Code": upload[ref_col].astype(str),
            "物流单号": [f"WT{i:012d}" for i in range(1, len(upload) + 1)],
            "订单号": [f"M{i:010d}" for i in range(1, len(upload) + 1)],
            "重量(kg)": [2.0] * len(upload),
        }
    )
    ret_path = OUT / "lizard-return-walkthrough.xlsx"
    ret.to_excel(ret_path, index=False)

    imp = ImportLizardTrackingService(repo).import_file(
        LizardImportRequest(
            account_key=ACCOUNT,
            actor="excel-walkthrough",
            input_path=ret_path,
            batch_id=result.batch_id,
        )
    )
    # Import result fields — dump safely
    imp_summary = {
        k: getattr(imp, k, None)
        for k in (
            "matched",
            "unmatched",
            "conflicts",
            "persisted",
            "batch_id",
            "total_rows",
            "success",
            "skipped",
        )
        if hasattr(imp, k)
    }
    # fallback: __dict__
    if not imp_summary:
        imp_summary = {
            k: v
            for k, v in getattr(imp, "__dict__", {}).items()
            if not k.startswith("_") and not callable(v)
        }
        # trim long lists
        for k, v in list(imp_summary.items()):
            if isinstance(v, list) and len(v) > 5:
                imp_summary[k] = v[:5]
                imp_summary[f"{k}_len"] = len(v)

    report = {"export": summary, "import": imp_summary, "return_file": str(ret_path)}
    (OUT / "REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )
    print("import", json.dumps(imp_summary, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
