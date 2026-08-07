"""Routing engine tests: routing_rules.yaml must remain the single source."""

from __future__ import annotations

from pathlib import Path

from sellfox_shipping import app as app_module
from sellfox_shipping.package_models import (
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.routing.engine import RuleEngine
from sellfox_shipping.routing.models import PackageRoutingData

RULES_PATH = Path(app_module.__file__).resolve().parent / "routing" / "routing_rules.yaml"


def _routing_data(shop_name: str) -> PackageRoutingData:
    return PackageRoutingData(
        shop_name=shop_name,
        warehouse_name="DANEEY",
        destination_country="US",
        destination_state="NJ",
        postal_code="07101",
        longest_side_cm=100,
        second_side_cm=80,
        third_side_cm=60,
        weight_kg=20.0,
        total_quantity=2,
    )


def _seed_shop(repo: PackageRepository, package_sn: str, shop_name: str) -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=package_sn,
            shop_id="shop-1",
            shop_name=shop_name,
            package_status="to_process",
            logistics=SellfoxPackageLogistics(channel_name="lizard"),
            orders=[SellfoxPackageOrderRecord(external_order_id=f"ORD-{package_sn}")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id=f"ORD-{package_sn}",
                    order_item_id=f"ITEM-{package_sn}",
                    seller_sku="SKU-A",
                    quantity=1,
                )
            ],
        )
    )


def test_yaml_exclude_shops_drive_route_engine() -> None:
    engine = RuleEngine.from_yaml(RULES_PATH)
    for shop in ("TT_Tooddly", "TTCozydozy"):
        result = engine.route(_routing_data(shop))
        assert result.carrier == "excluded"
        assert result.rule_name == "exclude_shops"

    # Non-excluded TikTok shops still fall through to the routing rules.
    result = engine.route(_routing_data("TTBNKC"))
    assert result.carrier == "vite"


def test_yaml_exclude_shops_drive_repository_filter(tmp_path) -> None:
    exclude_shops = app_module._routing_exclude_shops()
    assert "TT_Tooddly" in exclude_shops
    assert "TTCozydozy" in exclude_shops

    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_shop(repo, "P-TT-A", "TT_Tooddly")
    _seed_shop(repo, "P-TT-B", "TTCozydozy")
    _seed_shop(repo, "P-TT-C", "TTBNKC")

    total = repo.count_packages(account_key="sellfox-main")
    filtered = repo.count_packages(
        account_key="sellfox-main", exclude_shops=exclude_shops
    )
    assert total == 3
    assert filtered == 1
    rows = repo.list_packages(
        account_key="sellfox-main", exclude_shops=exclude_shops
    )
    assert [r.package_sn for r in rows] == ["P-TT-C"]
