"""Button platform for Kokozi."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.button import (
    DOMAIN as BUTTON_DOMAIN,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, house_device_info


@dataclass(frozen=True, kw_only=True)
class KokoziHouseButtonDescription(ButtonEntityDescription):
    """Kokozi house button description."""

    press_fn: Callable[["KokoziHouseButton"], Awaitable[None]]


HOUSE_BUTTONS: tuple[KokoziHouseButtonDescription, ...] = (
    KokoziHouseButtonDescription(
        key="volume_down",
        name="Volume Down",
        icon="mdi:volume-minus",
        press_fn=lambda button: button.async_set_relative_volume(-1),
    ),
    KokoziHouseButtonDescription(
        key="volume_up",
        name="Volume Up",
        icon="mdi:volume-plus",
        press_fn=lambda button: button.async_set_relative_volume(1),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KokoziHouseButton(coordinator, house_id, description)
            for house_id in coordinator.data.houses
            for description in HOUSE_BUTTONS
        ]
    )


class KokoziHouseButton(KokoziEntity, ButtonEntity):
    """Kokozi House button."""

    entity_description: KokoziHouseButtonDescription

    def __init__(
        self,
        coordinator: KokoziDataUpdateCoordinator,
        house_id: str,
        description: KokoziHouseButtonDescription,
    ) -> None:
        """Initialize the button."""
        self.house_id = house_id
        self.entity_description = description
        super().__init__(
            coordinator,
            f"house_{house_id}_{description.key}",
            house_device_info(coordinator.data.houses[house_id]),
            BUTTON_DOMAIN,
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.entity_description.press_fn(self)

    async def async_set_relative_volume(self, offset: int) -> None:
        """Set volume relative to the current Kokozi volume."""
        volume = self.house.get("volume") or {}
        minimum = volume.get("min", 0)
        maximum = volume.get("max", 24)
        current = volume.get("current", minimum)
        new_volume = max(minimum, min(maximum, current + offset))
        await self.coordinator.client.async_set_house_volume(
            await self.coordinator.async_get_access_token(), self.house_id, new_volume
        )
        await self.coordinator.async_refresh_after_command()

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]
