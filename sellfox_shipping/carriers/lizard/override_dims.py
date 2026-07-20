"""DimsLookup backed by PackageRepository carton overrides."""

from __future__ import annotations

from sellfox_shipping.carriers.lizard.dims import CartonDims
from sellfox_shipping.package_repository import PackageRepository


class RepositoryDimsLookup:
    def __init__(self, repository: PackageRepository, account_key: str):
        self._repo = repository
        self._account_key = account_key

    def get(self, commodity_sku: str) -> CartonDims | None:
        sku = (commodity_sku or "").strip()
        if not sku:
            return None
        record = self._repo.get_carton_override(self._account_key, sku)
        if record is None:
            return None
        dims = record.dims
        if not dims.is_complete:
            return None
        return dims
