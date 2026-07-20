"""Try dims lookups in order; first complete hit wins."""

from __future__ import annotations

from sellfox_shipping.carriers.lizard.dims import CartonDims, DimsLookup


class CascadingDimsLookup:
    def __init__(self, *lookups: DimsLookup):
        if not lookups:
            raise ValueError("at least one DimsLookup required")
        self._lookups = lookups

    def get(self, commodity_sku: str) -> CartonDims | None:
        for lookup in self._lookups:
            dims = lookup.get(commodity_sku)
            if dims is not None and dims.is_complete:
                return dims
        return None

    def prefetch(self, commodity_skus: list[str]) -> None:
        for lookup in self._lookups:
            prefetch = getattr(lookup, "prefetch", None)
            if callable(prefetch):
                prefetch(commodity_skus)
