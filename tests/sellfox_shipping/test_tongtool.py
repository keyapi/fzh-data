"""通途订单标记服务测试：xls 读取、EN 匹配、持久化、列表过滤。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.package_service import (
    ListPackagesService,
    PackageListRequest,
)
from sellfox_shipping.tongtool_service import (
    match_and_mark,
    order_id_to_amazon,
    read_p_numbers_from_xls,
)


def _seed_pkg(
    repo: PackageRepository,
    sn: str,
    *,
    order_id: str = "112-9957834-2887428",
) -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=sn,
            shop_id="596754",
            package_status="to_process",
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="Test", address_line_1="1 Main", city="Newark",
                state_or_region="NJ", postal_code="07101", country_code="US",
                phone="5551234567",
            ),
            logistics=SellfoxPackageLogistics(channel_name="蜴国际-FedEx"),
            orders=[SellfoxPackageOrderRecord(external_order_id=order_id)],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id=order_id,
                    order_item_id="I1", seller_sku="SKU-A", quantity=1,
                )
            ],
        )
    )


def _make_xls(path: Path, rows: list[str]) -> None:
    pd.DataFrame({"参考编号/Reference Code": rows}).to_excel(path, index=False)


def test_read_p_numbers_from_xls_dedups(tmp_path: Path) -> None:
    xls = tmp_path / "tong.xlsx"
    _make_xls(xls, ["P81678873", "P81678873", "P81679838", ""])
    assert read_p_numbers_from_xls(xls) == ["P81678873", "P81679838"]


def test_order_id_to_amazon_strips_channel_prefix() -> None:
    assert order_id_to_amazon("CUS-112-9957834-2887428") == "112-9957834-2887428"
    assert order_id_to_amazon("TOODDLYUS-114-0404540-1361802") == "114-0404540-1361802"
    assert order_id_to_amazon("112-9957834-2887428") == "112-9957834-2887428"


def test_match_and_mark_marks_matched_and_reports_unmatched(
    tmp_path: Path, monkeypatch
) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_pkg(repo, "P2B9A9T734635", order_id="112-9957834-2887428")
    _seed_pkg(repo, "P2B9A9T999999", order_id="999-0000000-0000000")

    def _fake_lookup(p: str):
        if p == "P81678873":
            return "CUS-112-9957834-2887428", "ok"
        if p == "P81679838":
            return None, "en_http_404"
        if p == "P81679820":
            return "CUS-114-9127464-6333866", "ok"  # 无本地包裹
        return None, "no_order_links"

    monkeypatch.setattr(
        "sellfox_shipping.tongtool_service.lookup_tongtool_order", _fake_lookup
    )

    xls = tmp_path / "tong.xlsx"
    _make_xls(xls, ["P81678873", "P81679838", "P81679820"])

    result = match_and_mark(
        repo, account_key="sellfox-main", xls_path=xls, actor="test",
        en_interval_s=0,
    )

    assert result.total == 3
    assert result.matched == 1
    assert result.unmatched_count == 2
    # 匹配到 P2B9A9T734635 并持久化标记
    mark = repo.get_tongtool_mark(
        account_key="sellfox-main", package_sn="P2B9A9T734635"
    )
    assert mark["is_tongtool"] is True
    assert "P81678873" in mark["tongtool_p_numbers"]
    # 未匹配的包裹不标记
    unmarked = repo.get_tongtool_mark(
        account_key="sellfox-main", package_sn="P2B9A9T999999"
    )
    assert unmarked["is_tongtool"] is False
    # 未匹配原因明确列出
    reasons = {r["reason"] for r in result.unmatched_rows}
    assert "en_http_404" in reasons
    assert "no_local_package" in reasons


def test_list_packages_filters_by_tongtool(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_pkg(repo, "P2TT-YES", order_id="112-1111111-1111111")
    _seed_pkg(repo, "P2TT-NO", order_id="112-2222222-2222222")
    repo.mark_tongtool(account_key="sellfox-main", package_sn="P2TT-YES", p_numbers=["P1"])

    svc = ListPackagesService(repo)
    yes = svc.list(PackageListRequest(account_key="sellfox-main", tongtool="yes", limit=50))
    no = svc.list(PackageListRequest(account_key="sellfox-main", tongtool="no", limit=50))

    assert [i.package_sn for i in yes.items] == ["P2TT-YES"]
    assert [i.package_sn for i in no.items] == ["P2TT-NO"]
    assert yes.items[0].is_tongtool is True
