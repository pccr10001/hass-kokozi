"""Select platform for Kokozi."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, house_device_info

REPEAT_OPTIONS = ["none", "one", "all"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KokoziRepeatSelect(coordinator, house_id)
            for house_id in coordinator.data.houses
        ]
    )


class KokoziRepeatSelect(KokoziEntity, SelectEntity):
    """Kokozi House repeat select."""

    _attr_options = REPEAT_OPTIONS
    entity_description = SelectEntityDescription(
        key="repeat",
        name="Repeat",
        icon="mdi:repeat",
    )

    def __init__(
        self, coordinator: KokoziDataUpdateCoordinator, house_id: str
    ) -> None:
        """Initialize the select."""
        self.house_id = house_id
        super().__init__(
            coordinator,
            f"house_{house_id}_repeat",
            house_device_info(coordinator.data.houses[house_id]),
            SELECT_DOMAIN,
        )

    @property
    def current_option(self) -> str | None:
        """Return current repeat mode."""
        repeat = (self.house.get("house_play_state") or {}).get("repeat")
        return repeat if repeat in REPEAT_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        """Set repeat mode."""
        if option not in REPEAT_OPTIONS:
            raise ValueError(f"Unsupported Kokozi repeat mode: {option}")

        await self.coordinator.client.async_set_house_repeat(
            await self.coordinator.async_get_access_token(), self.house_id, option
        )
        await self.coordinator.async_refresh_after_command()

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]
