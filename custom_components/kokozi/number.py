"""Number platform for Kokozi."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, house_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi numbers."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KokoziLedBrightnessNumber(coordinator, house_id)
            for house_id in coordinator.data.houses
        ]
    )


class KokoziLedBrightnessNumber(KokoziEntity, NumberEntity):
    """Kokozi House LED brightness number."""

    entity_description = NumberEntityDescription(
        key="led_brightness",
        name="LED Brightness",
        icon="mdi:led-on",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    )

    def __init__(
        self, coordinator: KokoziDataUpdateCoordinator, house_id: str
    ) -> None:
        """Initialize the number."""
        self.house_id = house_id
        super().__init__(
            coordinator,
            f"house_{house_id}_led_brightness",
            house_device_info(coordinator.data.houses[house_id]),
            NUMBER_DOMAIN,
        )

    @property
    def native_value(self) -> float | None:
        """Return current LED brightness."""
        value = self.house.get("led_lightness")
        if value is None:
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Set LED brightness."""
        lightness = round(max(0, min(100, value)))
        await self.coordinator.client.async_set_house_led_lightness(
            await self.coordinator.async_get_access_token(), self.house_id, lightness
        )
        await self.coordinator.async_refresh_after_command()

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]
