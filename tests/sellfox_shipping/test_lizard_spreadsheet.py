"""P1B: lizard upload export + tracking return import (pure spreadsheet)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
from sellfox_shipping.carriers.lizard.spreadsheet import (
    LIZARD_TEMPLATE_VERSION,
    build_upload_dataframe,
    parse_tracking_return,
    write_upload_xlsx,
)
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)


def _pkg(
    sn: str = "P2AKA9T726212",
    *,
    commodity_sku: str = "KS0248-HLR-60-BLACK",
    seller_sku: str = "BNno1594-black-60",
    state: str = "Florida",
) -> SellfoxPackageRecord:
    return SellfoxPackageRecord(
        account_key="sellfox-main",
        package_sn=sn,
        local_review_status="approved",
        address=SellfoxPackageAddress(
            name="Eileen DeFeo",
            address_line_1="8142 SPRINGTREE RD",
            address_line_2="WHISPER WALK",
            city="BOCA RATON",
            state_or_region=state,
            postal_code="33496-5111",
            country="美国",
            country_code="US",
            phone="+1 602-671-6610 ext. 63502",
        ),
        logistics=SellfoxPackageLogistics(
            warehouse_name="DANEEY",
            channel_name="蜴国际-FedEx-蜴国际-FedEx",
        ),
        items=[
            SellfoxPackageItemRecord(
                external_order_id="113-1",
                order_item_id="1",
                seller_sku=seller_sku,
                commodity_sku=commodity_sku,
                quantity=1,
            )
        ],
    )


def test_build_upload_uses_package_sn_and_commodity_dims() -> None:
    dims = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60.0, width_cm=55.0, height_cm=5.0
            )
        }
    )
    result = build_upload_dataframe([_pkg()], dims_lookup=dims)

    assert result.template_version == LIZARD_TEMPLATE_VERSION
    assert result.total == 1
    assert result.exported == 1
    assert result.skipped == 0
    row = result.dataframe.iloc[0]
    assert row["参考编号/Reference Code"] == "P2AKA9T726212"
    assert row["州/Province"] == "FL"
    assert row["收件人国家/Consignee Country"] == "United States"
    assert row["重量"] == 2500.0
    assert row["长"] == 60.0
    assert row["宽"] == 55.0
    assert row["高"] == 5.0
    assert row["发货编码/shipper Code"] == "S0143"
    assert row["备注/Remark"] == "BNno1594-black-60"
    assert row["收件人电话/Consignee Phone"] == "6026716610"


def test_build_upload_skips_missing_dims_with_report_row() -> None:
    result = build_upload_dataframe([_pkg()], dims_lookup=StaticDimsLookup({}))

    assert result.exported == 0
    assert result.skipped == 1
    assert result.dataframe.empty
    assert result.skipped_rows[0].package_sn == "P2AKA9T726212"
    assert "dims" in result.skipped_rows[0].reason.lower()


def test_write_and_parse_tracking_return_roundtrip(tmp_path: Path) -> None:
    dims = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60.0, width_cm=55.0, height_cm=5.0
            )
        }
    )
    built = build_upload_dataframe([_pkg()], dims_lookup=dims)
    upload_path = tmp_path / "upload.xlsx"
    write_upload_xlsx(built.dataframe, upload_path)
    assert upload_path.is_file()

    # Simulate lizard return with tracking (extra unmatched row too)
    ret = pd.DataFrame(
        [
            {
                "参考编号/Reference Code": "P2AKA9T726212",
                "物流单号": "382619183572",
                "订单号": "M6180202607158934628",
                "派送方式/Delivery Style": "FedEx-Economy-10-HOU",
                "运费": 12.04,
                "订单状态": "已预报",
            },
            {
                "参考编号/Reference Code": "UNKNOWN-SN",
                "物流单号": "999",
                "订单号": "M1",
                "派送方式/Delivery Style": "FedEx-Economy-10-HOU",
                "运费": 1.0,
                "订单状态": "已预报",
            },
        ]
    )
    ret_path = tmp_path / "return.xlsx"
    ret.to_excel(ret_path, index=False)

    parsed = parse_tracking_return(
        ret_path,
        known_package_sns={"P2AKA9T726212", "P2AKA9T726299"},
    )
    assert parsed.total == 2
    assert parsed.matched == 1
    assert parsed.unmatched == 1
    assert parsed.rows[0].package_sn == "P2AKA9T726212"
    assert parsed.rows[0].tracking_number == "382619183572"
    assert parsed.rows[0].carrier_order_no == "M6180202607158934628"
    assert parsed.rows[0].matched is True
    assert parsed.unmatched_rows[0].package_sn == "UNKNOWN-SN"


def test_parse_tracking_return_requires_reference_and_tracking(tmp_path: Path) -> None:
    bad = pd.DataFrame([{"参考编号/Reference Code": "P1", "运费": 1}])
    path = tmp_path / "bad.xlsx"
    bad.to_excel(path, index=False)
    with pytest.raises(ValueError, match="物流单号"):
        parse_tracking_return(path, known_package_sns=set())
