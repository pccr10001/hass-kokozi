"""Base entities for Kokozi."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import KokoziDataUpdateCoordinator


class KokoziEntity(CoordinatorEntity[KokoziDataUpdateCoordinator]):
    """Base Kokozi entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KokoziDataUpdateCoordinator,
        unique_id: str,
        device_info: DeviceInfo,
        entity_domain: str | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        if entity_domain is not None:
            self.entity_id = f"{entity_domain}.{slugify(unique_id)}"
        self._attr_device_info = device_info


def house_device_info(house: dict[str, Any]) -> DeviceInfo:
    """Return device info for a Kokozi House."""
    house_id = house["_id"]
    firmware = house.get("firmware") or {}
    return DeviceInfo(
        identifiers={(DOMAIN, f"house_{house_id}")},
        name=house.get("name") or "Kokozi House",
        manufacturer="Kokozi",
        model=house.get("device_type") or "kokozi-house",
        sw_version=firmware.get("version"),
    )


def arti_device_info(arti: dict[str, Any]) -> DeviceInfo:
    """Return device info for a Kokozi Arti."""
    arti_id = arti["id"]
    return DeviceInfo(
        identifiers={(DOMAIN, f"arti_{arti_id}")},
        name=arti.get("name") or f"Arti {arti_id[-6:]}",
        manufacturer="Kokozi",
        model=arti.get("typeId") or arti.get("type") or "Arti",
    )
