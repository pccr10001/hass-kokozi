"""Sensor platform for Kokozi."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import ATTR_ARTI_ID, ATTR_PLAYLIST_ID, ATTR_STORY_ID
from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, house_device_info


@dataclass(frozen=True, kw_only=True)
class KokoziHouseSensorDescription(SensorEntityDescription):
    """Kokozi house sensor description."""

    value_fn: Callable[[dict[str, Any], KokoziDataUpdateCoordinator], StateType]
    attrs_fn: (
        Callable[[dict[str, Any], KokoziDataUpdateCoordinator], dict[str, Any]] | None
    ) = None


HOUSE_SENSORS: tuple[KokoziHouseSensorDescription, ...] = (
    KokoziHouseSensorDescription(
        key="arti_name",
        name="Arti Name",
        value_fn=lambda house, coordinator: _current_arti_name(house, coordinator),
        attrs_fn=lambda house, coordinator: {
            ATTR_ARTI_ID: (house.get("arti") or {}).get("artiId")
        },
    ),
    KokoziHouseSensorDescription(
        key="playlist",
        name="Playlist",
        value_fn=lambda house, coordinator: _current_playlist_name(house, coordinator),
        attrs_fn=lambda house, coordinator: {
            ATTR_PLAYLIST_ID: (house.get("play") or {}).get("playlistId"),
            ATTR_STORY_ID: (house.get("play") or {}).get("storyId"),
        },
    ),
    KokoziHouseSensorDescription(
        key="battery",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda house, coordinator: (house.get("battery") or {}).get(
            "percentage"
        ),
    ),
    KokoziHouseSensorDescription(
        key="firmware_version",
        name="Firmware Version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda house, coordinator: (house.get("firmware") or {}).get(
            "version"
        ),
        attrs_fn=lambda house, coordinator: house.get("firmware") or {},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KokoziHouseSensor(coordinator, house_id, description)
            for house_id in coordinator.data.houses
            for description in HOUSE_SENSORS
        ]
    )


class KokoziHouseSensor(KokoziEntity, SensorEntity):
    """Kokozi House sensor."""

    entity_description: KokoziHouseSensorDescription

    def __init__(
        self,
        coordinator: KokoziDataUpdateCoordinator,
        house_id: str,
        description: KokoziHouseSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        self.house_id = house_id
        self.entity_description = description
        super().__init__(
            coordinator,
            f"house_{house_id}_{description.key}",
            house_device_info(coordinator.data.houses[house_id]),
            SENSOR_DOMAIN,
        )

    @property
    def native_value(self) -> StateType:
        """Return native sensor value."""
        return self.entity_description.value_fn(self.house, self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return sensor attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.house, self.coordinator)

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]


def _current_arti_name(
    house: dict[str, Any], coordinator: KokoziDataUpdateCoordinator
) -> str | None:
    """Return the currently connected Arti name."""
    arti_id = (house.get("arti") or {}).get("artiId")
    if not arti_id:
        return None
    arti = coordinator.data.arties.get(arti_id)
    return arti.get("name") if arti else arti_id


def _current_playlist_name(
    house: dict[str, Any], coordinator: KokoziDataUpdateCoordinator
) -> str | None:
    """Return current playlist name."""
    playlist_id = (house.get("play") or {}).get("playlistId")
    if not playlist_id:
        return None
    playlist = coordinator.data.playlists.get(playlist_id)
    return playlist.get("name") if playlist else playlist_id
