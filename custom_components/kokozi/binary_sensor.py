"""Binary sensor platform for Kokozi."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, arti_device_info, house_device_info


@dataclass(frozen=True, kw_only=True)
class KokoziHouseBinarySensorDescription(BinarySensorEntityDescription):
    """Kokozi house binary sensor description."""

    value_fn: Callable[[dict[str, Any]], bool | None]


HOUSE_BINARY_SENSORS: tuple[KokoziHouseBinarySensorDescription, ...] = (
    KokoziHouseBinarySensorDescription(
        key="connected",
        name="Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda house: house.get("connected"),
    ),
    KokoziHouseBinarySensorDescription(
        key="arti_connected",
        name="Arti Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda house: (house.get("arti") or {}).get("connected"),
    ),
    KokoziHouseBinarySensorDescription(
        key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda house: (house.get("battery") or {}).get("chargingState")
        == "Charging",
    ),
    KokoziHouseBinarySensorDescription(
        key="plugged",
        name="Plugged",
        device_class=BinarySensorDeviceClass.PLUG,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda house: (house.get("battery") or {}).get("plugged"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        KokoziHouseBinarySensor(coordinator, house_id, description)
        for house_id in coordinator.data.houses
        for description in HOUSE_BINARY_SENSORS
    ]
    entities.extend(
        KokoziArtiConnectedBinarySensor(coordinator, arti_id)
        for arti_id in coordinator.data.arties
    )
    async_add_entities(entities)


class KokoziHouseBinarySensor(KokoziEntity, BinarySensorEntity):
    """Kokozi House binary sensor."""

    entity_description: KokoziHouseBinarySensorDescription

    def __init__(
        self,
        coordinator: KokoziDataUpdateCoordinator,
        house_id: str,
        description: KokoziHouseBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        self.house_id = house_id
        self.entity_description = description
        super().__init__(
            coordinator,
            f"house_{house_id}_{description.key}",
            house_device_info(coordinator.data.houses[house_id]),
            BINARY_SENSOR_DOMAIN,
        )

    @property
    def is_on(self) -> bool | None:
        """Return if the sensor is on."""
        value = self.entity_description.value_fn(self.house)
        return bool(value) if value is not None else None

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]


class KokoziArtiConnectedBinarySensor(KokoziEntity, BinarySensorEntity):
    """Arti connected binary sensor."""

    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: KokoziDataUpdateCoordinator, arti_id: str
    ) -> None:
        """Initialize the binary sensor."""
        self.arti_id = arti_id
        super().__init__(
            coordinator,
            f"arti_{arti_id}_connected",
            arti_device_info(coordinator.data.arties[arti_id]),
            BINARY_SENSOR_DOMAIN,
        )

    @property
    def is_on(self) -> bool:
        """Return if this Arti is currently connected to a house."""
        return any(
            (house.get("arti") or {}).get("connected") is True
            and (house.get("arti") or {}).get("artiId") == self.arti_id
            for house in self.coordinator.data.houses.values()
        )
