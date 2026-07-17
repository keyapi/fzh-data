"""ExportLizardUploadService / ImportLizardTrackingService tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
from sellfox_shipping.lizard_batch import (
    ExportLizardUploadService,
    ImportLizardTrackingService,
    LizardExportRequest,
    LizardImportRequest,
)
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _seed_approved(repo: PackageRepository, sn: str = "P2ATEST001") -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=sn,
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="Test",
                address_line_1="1 Main",
                city="Newark",
                state_or_region="NJ",
                postal_code="07101",
                country_code="US",
                phone="5551234567",
            ),
            logistics=SellfoxPackageLogistics(channel_name="蜴国际-FedEx"),
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="O1",
                    order_item_id="I1",
                    seller_sku="SKU-A",
                    commodity_sku="KS0248-HLR-60-BLACK",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key="sellfox-main",
        package_sn=sn,
        local_review_status="approved",
    )


def test_export_service_writes_xlsx_and_audit(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_approved(repo)
    dims = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60, width_cm=55, height_cm=5
            )
        }
    )
    out = tmp_path / "out.xlsx"
    result = ExportLizardUploadService(repo, dims).export(
        LizardExportRequest(
            account_key="sellfox-main",
            actor="user-1",
            output_path=out,
        )
    )
    assert result.exported == 1
    assert result.skipped == 0
    assert Path(result.output_path).is_file()
    assert len(result.file_sha256) == 64
    df = pd.read_excel(out)
    assert df.iloc[0]["参考编号/Reference Code"] == "P2ATEST001"
    events = repo.list_audit_events(limit=5)
    assert any(e.action == "lizard.upload_export" for e in events)


def test_import_service_reconciles_known_sns(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_approved(repo)
    ret = tmp_path / "return.xlsx"
    pd.DataFrame(
        [
            {
                "参考编号/Reference Code": "P2ATEST001",
                "物流单号": "TN1",
                "订单号": "M1",
            },
            {
                "参考编号/Reference Code": "NOPE",
                "物流单号": "TN2",
                "订单号": "M2",
            },
        ]
    ).to_excel(ret, index=False)

    result = ImportLizardTrackingService(repo).import_file(
        LizardImportRequest(
            account_key="sellfox-main",
            actor="user-1",
            input_path=ret,
        )
    )
    assert result.matched == 1
    assert result.unmatched == 1
    assert result.matched_rows[0]["tracking_number"] == "TN1"
