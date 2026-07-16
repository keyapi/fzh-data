"""Carrier abstraction layer — Proxy + Provider pattern inspired by Karrio."""

from abc import ABC, abstractmethod

from sellfox_shipping.models import Address, Label, Package, Rate, ShipmentRequest, TrackingInfo


class AbstractCarrier(ABC):
    """Unified carrier interface. Each carrier implements this.

    Pattern borrowed from Karrio's Proxy class and verbb/shippy's AbstractCarrier.
    """

    carrier_name: str = ""

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Check that API credentials are valid."""
        ...

    @abstractmethod
    def get_rates(
        self,
        origin: Address,
        destination: Address,
        packages: list[Package],
        service_level: str | None = None,
    ) -> list[Rate]:
        """Fetch available rates from the carrier."""
        ...

    @abstractmethod
    def create_shipment(
        self,
        request: ShipmentRequest,
    ) -> Label:
        """Create a shipment and return the shipping label."""
        ...

    def get_tracking(self, tracking_number: str) -> TrackingInfo:
        """Track a shipment. Override for carriers that support this."""
        raise NotImplementedError(f"{self.carrier_name} does not support tracking")

    def supports_country(self, country_code: str) -> bool:
        """Override for geo-routing restrictions."""
        return True


class CarrierRegistry:
    """Registry of carrier instances, lazy-loaded from config."""

    def __init__(self):
        self._carriers: dict[str, AbstractCarrier] = {}

    def register(self, name: str, carrier: AbstractCarrier):
        self._carriers[name] = carrier

    def get(self, name: str) -> AbstractCarrier:
        if name not in self._carriers:
            raise KeyError(f"Carrier '{name}' not registered. Available: {list(self._carriers)}")
        return self._carriers[name]

    def list_all(self) -> list[str]:
        return list(self._carriers.keys())

    def list_for_country(self, country_code: str) -> list[str]:
        return [
            name for name, c in self._carriers.items()
            if c.supports_country(country_code)
        ]

    def __getitem__(self, name: str) -> AbstractCarrier:
        return self.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._carriers
