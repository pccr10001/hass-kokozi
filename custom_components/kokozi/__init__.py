"""The Kokozi integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .const import DOMAIN, LOGGER

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: KokoziConfigEntry
) -> bool:
    """Set up Kokozi from a config entry."""
    coordinator = KokoziDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _async_migrate_entity_ids(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: KokoziConfigEntry
) -> bool:
    """Unload a Kokozi config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _async_migrate_entity_ids(hass: HomeAssistant, entry: KokoziConfigEntry) -> None:
    """Rename existing Kokozi entities to ID based entity IDs."""
    entity_registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if registry_entry.platform != DOMAIN or registry_entry.unique_id is None:
            continue

        desired_entity_id = (
            f"{registry_entry.domain}.{slugify(registry_entry.unique_id)}"
        )
        if registry_entry.entity_id == desired_entity_id:
            continue

        existing = entity_registry.async_get(desired_entity_id)
        if existing is not None and existing.id != registry_entry.id:
            LOGGER.warning(
                "Cannot rename Kokozi entity %s to %s because it already exists",
                registry_entry.entity_id,
                desired_entity_id,
            )
            continue

        LOGGER.debug(
            "Renaming Kokozi entity %s to %s",
            registry_entry.entity_id,
            desired_entity_id,
        )
        entity_registry.async_update_entity(
            registry_entry.entity_id, new_entity_id=desired_entity_id
        )
