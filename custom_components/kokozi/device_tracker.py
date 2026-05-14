"""Device tracker platform for Kokozi."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, house_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi device trackers."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KokoziHouseDeviceTracker(coordinator, house_id)
            for house_id, house in coordinator.data.houses.items()
            if ((house.get("hardware") or {}).get("wifiMac"))
        ]
    )


class KokoziHouseDeviceTracker(KokoziEntity, ScannerEntity):
    """Kokozi House Wi-Fi device tracker."""

    _attr_name = "Wi-Fi"
    _attr_source_type = SourceType.ROUTER

    def __init__(
        self, coordinator: KokoziDataUpdateCoordinator, house_id: str
    ) -> None:
        """Initialize the tracker."""
        self.house_id = house_id
        super().__init__(
            coordinator,
            f"house_{house_id}_wifi",
            house_device_info(coordinator.data.houses[house_id]),
            DEVICE_TRACKER_DOMAIN,
        )

    @property
    def is_connected(self) -> bool:
        """Return if the house is online."""
        return self.house.get("connected") is True

    @property
    def mac_address(self) -> str | None:
        """Return Wi-Fi MAC address."""
        return (self.house.get("hardware") or {}).get("wifiMac")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return tracker attributes."""
        return {"ssid": self.house.get("ssid")}

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]
