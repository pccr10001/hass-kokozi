"""Coordinator for Kokozi."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    KokoziApiClient,
    KokoziAuthError,
    KokoziCannotConnect,
    get_jwt_subject,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_EXPIRES_IN,
    CONF_ISSUES_AT,
    CONF_OWNER_ID,
    CONF_POLLING_INTERVAL,
    CONF_REFRESH_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_TYPE,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    LOGGER,
)

TOKEN_REFRESH_MARGIN = timedelta(minutes=5)

type KokoziConfigEntry = ConfigEntry[KokoziDataUpdateCoordinator]


@dataclass(slots=True)
class KokoziData:
    """Runtime Kokozi data."""

    owner_id: str
    houses: dict[str, dict[str, Any]] = field(default_factory=dict)
    arties: dict[str, dict[str, Any]] = field(default_factory=dict)
    playlists: dict[str, dict[str, Any]] = field(default_factory=dict)


class KokoziDataUpdateCoordinator(DataUpdateCoordinator[KokoziData]):
    """Fetch Kokozi account data."""

    config_entry: KokoziConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: KokoziConfigEntry,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(
                    CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                )
            ),
        )
        self.client = KokoziApiClient(session or async_get_clientsession(hass))
        self.owner_id = entry.data.get(CONF_OWNER_ID) or get_jwt_subject(
            entry.data[CONF_ACCESS_TOKEN]
        )
        self._playlist_cache: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> KokoziData:
        """Update Kokozi data."""
        if not self.owner_id:
            raise ConfigEntryAuthFailed("Unable to determine Kokozi owner id")

        try:
            access_token = await self.async_get_access_token()
            houses = await self.client.async_get_houses(access_token, self.owner_id)
            arties = await self.client.async_get_arties(access_token, self.owner_id)
        except KokoziAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KokoziCannotConnect as err:
            raise UpdateFailed(str(err)) from err

        house_map = {house["_id"]: house for house in houses if house.get("_id")}
        arti_map = {arti["id"]: arti for arti in arties if arti.get("id")}

        playlist_ids = {
            playlist_id
            for house in house_map.values()
            for playlist_id in (
                _house_playlist_id(house),
                _house_current_arti_playlist_id(house, arti_map),
            )
            if playlist_id
        }
        playlists: dict[str, dict[str, Any]] = {}
        for playlist_id in playlist_ids:
            try:
                playlists[playlist_id] = await self.async_get_playlist(playlist_id)
            except (KokoziAuthError, KokoziCannotConnect) as err:
                LOGGER.debug("Unable to fetch Kokozi playlist %s: %s", playlist_id, err)

        LOGGER.debug(
            "Kokozi update complete: houses=%s arties=%s playlists=%s",
            len(house_map),
            len(arti_map),
            len(playlists),
        )
        return KokoziData(
            owner_id=self.owner_id,
            houses=house_map,
            arties=arti_map,
            playlists=playlists,
        )

    async def async_get_access_token(self) -> str:
        """Return a valid access token, refreshing when needed."""
        access_token = self.config_entry.data[CONF_ACCESS_TOKEN]
        refresh_token = self.config_entry.data.get(CONF_REFRESH_TOKEN)

        expires_at = self.config_entry.data.get(CONF_EXPIRES_AT)
        if not refresh_token or (
            expires_at is not None and not _token_should_refresh(expires_at)
        ):
            return access_token

        try:
            token = await self.client.async_refresh_token(refresh_token)
        except KokoziAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KokoziCannotConnect:
            return access_token

        new_data = {
            **self.config_entry.data,
            CONF_ACCESS_TOKEN: token.access_token,
            CONF_REFRESH_TOKEN: token.refresh_token or refresh_token,
            CONF_TOKEN_TYPE: token.token_type,
            CONF_EXPIRES_IN: token.expires_in,
            CONF_ISSUES_AT: token.issues_at,
            CONF_EXPIRES_AT: token.expires_at,
            CONF_REFRESH_EXPIRES_AT: token.refresh_expires_at,
            CONF_OWNER_ID: self.owner_id or get_jwt_subject(token.access_token),
        }
        self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
        LOGGER.info("Kokozi access token refreshed")
        return token.access_token

    async def async_get_playlist(self, playlist_id: str) -> dict[str, Any]:
        """Return playlist data, using a cache for repeated browse requests."""
        if playlist_id in self._playlist_cache:
            return self._playlist_cache[playlist_id]

        playlist = await self.client.async_get_playlist(
            await self.async_get_access_token(), playlist_id
        )
        self._playlist_cache[playlist_id] = playlist
        return playlist

    async def async_refresh_after_command(self) -> None:
        """Refresh data after a command."""
        await asyncio.sleep(0.5)
        await self.async_request_refresh()


def _house_playlist_id(house: dict[str, Any]) -> str | None:
    """Return current house playlist id."""
    play = house.get("play")
    if isinstance(play, dict):
        playlist_id = play.get("playlistId")
        if isinstance(playlist_id, str) and playlist_id:
            return playlist_id
    return None


def _house_current_arti_playlist_id(
    house: dict[str, Any], arties: dict[str, dict[str, Any]]
) -> str | None:
    """Return the playlist id for the Arti currently placed on the house."""
    arti_id = (house.get("arti") or {}).get("artiId")
    if not arti_id:
        return None

    playlist_id = arties.get(arti_id, {}).get("currentPlaylistId")
    return playlist_id if isinstance(playlist_id, str) and playlist_id else None


def _token_should_refresh(expires_at: str | None) -> bool:
    """Return if the access token should be refreshed."""
    if not expires_at:
        return False

    expires = dt_util.parse_datetime(expires_at)
    if expires is None:
        return False
    if expires.tzinfo is None:
        expires = dt_util.as_utc(expires)

    return expires - dt_util.utcnow() <= TOKEN_REFRESH_MARGIN
