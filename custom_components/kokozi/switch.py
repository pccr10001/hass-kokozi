"""Switch platform for Kokozi."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, house_device_info


@dataclass(frozen=True, kw_only=True)
class KokoziHouseSwitchDescription(SwitchEntityDescription):
    """Kokozi house switch description."""

    value_fn: Callable[[dict[str, Any]], bool | None]
    set_fn: Callable[["KokoziHouseSwitch", bool], Awaitable[None]]


HOUSE_SWITCHES: tuple[KokoziHouseSwitchDescription, ...] = (
    KokoziHouseSwitchDescription(
        key="shuffle",
        name="Shuffle",
        icon="mdi:shuffle",
        value_fn=lambda house: (house.get("house_play_state") or {}).get("shuffle"),
        set_fn=lambda switch, enabled: switch.async_set_shuffle(enabled),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KokoziHouseSwitch(coordinator, house_id, description)
            for house_id in coordinator.data.houses
            for description in HOUSE_SWITCHES
        ]
    )


class KokoziHouseSwitch(KokoziEntity, SwitchEntity):
    """Kokozi House switch."""

    entity_description: KokoziHouseSwitchDescription

    def __init__(
        self,
        coordinator: KokoziDataUpdateCoordinator,
        house_id: str,
        description: KokoziHouseSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        self.house_id = house_id
        self.entity_description = description
        super().__init__(
            coordinator,
            f"house_{house_id}_{description.key}",
            house_device_info(coordinator.data.houses[house_id]),
            SWITCH_DOMAIN,
        )

    @property
    def is_on(self) -> bool | None:
        """Return if the switch is on."""
        value = self.entity_description.value_fn(self.house)
        return bool(value) if value is not None else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.entity_description.set_fn(self, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.entity_description.set_fn(self, False)

    async def async_set_shuffle(self, enabled: bool) -> None:
        """Set shuffle mode."""
        await self.coordinator.client.async_set_house_shuffle(
            await self.coordinator.async_get_access_token(), self.house_id, enabled
        )
        await self.coordinator.async_refresh_after_command()

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]
