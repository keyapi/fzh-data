"""Carton weight/dims lookup for lizard Excel export.

Primary source: Sellfox commodity pageList (carton*). ERPNext is a future
fallback injected via the same DimsLookup protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CartonDims:
    weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float

    @property
    def is_complete(self) -> bool:
        return (
            self.weight_kg > 0
            and self.length_cm > 0
            and self.width_cm > 0
            and self.height_cm > 0
        )


class DimsLookup(Protocol):
    def get(self, commodity_sku: str) -> CartonDims | None: ...


class StaticDimsLookup:
    """In-memory map for tests and offline fixtures."""

    def __init__(self, mapping: dict[str, CartonDims]):
        self._mapping = dict(mapping)

    def get(self, commodity_sku: str) -> CartonDims | None:
        dims = self._mapping.get(commodity_sku)
        if dims is None or not dims.is_complete:
            return None
        return dims

    def get_item_name(self, commodity_sku: str) -> str:
        return ""
