"""Media player platform for Kokozi."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    BrowseError,
    BrowseMedia,
    MediaClass,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import arti_thumbnail_url, playlist_thumbnail_url, thumbnail_url
from .const import (
    ATTR_ARTI_ID,
    ATTR_ARTI_NAME,
    ATTR_PLAYLIST_ID,
    ATTR_PLAYLIST_NAME,
    ATTR_REPEAT,
    ATTR_SHUFFLE,
    ATTR_STORY_ID,
    DOMAIN,
)
from .coordinator import KokoziConfigEntry, KokoziDataUpdateCoordinator
from .entity import KokoziEntity, house_device_info

SUPPORT_KOKOZI_HOUSE = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.REPEAT_SET
    | MediaPlayerEntityFeature.SHUFFLE_SET
)

PLAYLIST_PREFIX = "kokozi://playlist/"
STORY_RE = re.compile(
    r"^kokozi://playlist/(?P<playlist_id>[^/]+)/story/(?P<story_id>[^/]+)$"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KokoziConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Kokozi media players."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KokoziHouseMediaPlayer(coordinator, house_id)
            for house_id in coordinator.data.houses
        ]
    )


class KokoziHouseMediaPlayer(KokoziEntity, MediaPlayerEntity):
    """Kokozi House media player."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = SUPPORT_KOKOZI_HOUSE

    def __init__(
        self, coordinator: KokoziDataUpdateCoordinator, house_id: str
    ) -> None:
        """Initialize the media player."""
        self.house_id = house_id
        super().__init__(
            coordinator,
            f"house_{house_id}_media_player",
            house_device_info(coordinator.data.houses[house_id]),
            MEDIA_PLAYER_DOMAIN,
        )
        self._attr_name = None

    @property
    def house(self) -> dict[str, Any]:
        """Return current house data."""
        return self.coordinator.data.houses[self.house_id]

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        if not self.house.get("connected"):
            return MediaPlayerState.OFF

        play = self.house.get("play") or {}
        house_play_state = self.house.get("house_play_state") or {}
        if house_play_state.get("stop"):
            return MediaPlayerState.IDLE
        if play.get("state") == "play":
            return MediaPlayerState.PLAYING
        if play.get("state") == "pause":
            return MediaPlayerState.PAUSED
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        """Return volume level from 0..1."""
        volume = self.house.get("volume") or {}
        current = volume.get("current")
        maximum = volume.get("max")
        if current is None or not maximum:
            return None
        return max(0, min(1, current / maximum))

    @property
    def is_volume_muted(self) -> bool | None:
        """Return if volume is muted."""
        volume = self.house.get("volume") or {}
        return volume.get("mute")

    @property
    def repeat(self) -> RepeatMode | str | None:
        """Return repeat mode."""
        repeat = (self.house.get("house_play_state") or {}).get("repeat")
        if repeat == "none":
            return RepeatMode.OFF
        if repeat in {"one", "all"}:
            return RepeatMode(repeat)
        return None

    @property
    def shuffle(self) -> bool | None:
        """Return shuffle mode."""
        return (self.house.get("house_play_state") or {}).get("shuffle")

    @property
    def media_content_id(self) -> str | None:
        """Return current story content ID."""
        playlist_id = self._current_playlist_id
        story_id = self._current_story_id
        if playlist_id and story_id:
            return _story_media_id(playlist_id, story_id)
        return playlist_id

    @property
    def media_content_type(self) -> MediaType | str | None:
        """Return current content type."""
        return MediaType.TRACK if self._current_story_id else MediaType.PLAYLIST

    @property
    def media_title(self) -> str | None:
        """Return current story title."""
        if story := self._current_story:
            return story.get("name")
        return self._current_playlist_name

    @property
    def media_album_name(self) -> str | None:
        """Return current playlist name."""
        return self._current_playlist_name

    @property
    def media_image_url(self) -> str | None:
        """Return current playlist image URL."""
        return playlist_thumbnail_url(self._current_playlist_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra media player attributes."""
        arti_id = (self.house.get("arti") or {}).get("artiId")
        arti = self.coordinator.data.arties.get(arti_id) if arti_id else None
        playlist = self._current_playlist
        return {
            ATTR_ARTI_ID: arti_id,
            ATTR_ARTI_NAME: arti.get("name") if arti else None,
            ATTR_PLAYLIST_ID: self._current_playlist_id,
            ATTR_PLAYLIST_NAME: playlist.get("name") if playlist else None,
            ATTR_STORY_ID: self._current_story_id,
            ATTR_SHUFFLE: self.shuffle,
            ATTR_REPEAT: (self.house.get("house_play_state") or {}).get("repeat"),
            "chapter_jump": (self.house.get("house_play_state") or {}).get(
                "chapter_jump"
            ),
            "volume_current": (self.house.get("volume") or {}).get("current"),
            "volume_min": (self.house.get("volume") or {}).get("min"),
            "volume_max": (self.house.get("volume") or {}).get("max"),
        }

    async def async_media_play(self) -> None:
        """Resume playback."""
        access_token = await self.coordinator.async_get_access_token()
        playlist_id = self._current_playlist_id
        story_id = self._current_story_id

        if not playlist_id or not story_id:
            return

        await self.coordinator.client.async_play_house_story(
            access_token,
            self.house_id,
            playlist_id,
            story_id=story_id,
        )
        await self.coordinator.async_refresh_after_command()

    async def async_media_pause(self) -> None:
        """Pause playback."""
        await self.coordinator.client.async_pause_house(
            await self.coordinator.async_get_access_token(), self.house_id, True
        )
        await self.coordinator.async_refresh_after_command()

    async def async_media_stop(self) -> None:
        """Stop playback."""
        await self.coordinator.client.async_stop_house(
            await self.coordinator.async_get_access_token(), self.house_id
        )
        await self.coordinator.async_refresh_after_command()

    async def async_media_next_track(self) -> None:
        """Play next story."""
        await self._async_jump("next")

    async def async_media_previous_track(self) -> None:
        """Play previous story."""
        await self._async_jump("prev")

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        maximum = (self.house.get("volume") or {}).get("max") or 24
        current = round(max(0, min(1, volume)) * maximum)
        await self.coordinator.client.async_set_house_volume(
            await self.coordinator.async_get_access_token(), self.house_id, current
        )
        await self.coordinator.async_refresh_after_command()

    @property
    def volume_step(self) -> float:
        """Return one Kokozi volume point as Home Assistant volume step."""
        maximum = (self.house.get("volume") or {}).get("max") or 24
        return 1 / maximum

    async def async_volume_up(self) -> None:
        """Increase volume by one Kokozi volume point."""
        await self._async_set_relative_volume(1)

    async def async_volume_down(self) -> None:
        """Decrease volume by one Kokozi volume point."""
        await self._async_set_relative_volume(-1)

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set repeat mode."""
        kokozi_repeat = "none" if repeat == RepeatMode.OFF else repeat.value
        if kokozi_repeat not in {"none", "one", "all"}:
            raise ValueError(f"Unsupported Kokozi repeat mode: {repeat}")

        await self.coordinator.client.async_set_house_repeat(
            await self.coordinator.async_get_access_token(),
            self.house_id,
            kokozi_repeat,
        )
        await self.coordinator.async_refresh_after_command()

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle mode."""
        await self.coordinator.client.async_set_house_shuffle(
            await self.coordinator.async_get_access_token(), self.house_id, shuffle
        )
        await self.coordinator.async_refresh_after_command()

    async def async_play_media(
        self,
        media_type: MediaType | str,
        media_id: str,
        **kwargs: Any,
    ) -> None:
        """Play a Kokozi story."""
        match = STORY_RE.match(media_id)
        if not match:
            raise BrowseError(f"Unsupported Kokozi media: {media_type} / {media_id}")

        playlist_id = match.group("playlist_id")
        if not self._can_play_playlist(playlist_id):
            raise BrowseError(
                "Kokozi House can only play the playlist for its current Arti"
            )

        await self.coordinator.client.async_play_house_story(
            await self.coordinator.async_get_access_token(),
            self.house_id,
            playlist_id,
            story_id=match.group("story_id"),
        )
        await self.coordinator.async_refresh_after_command()

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse Kokozi playlists and stories."""
        if not media_content_id:
            return await self._async_browse_root()

        if media_content_id.startswith(PLAYLIST_PREFIX):
            playlist_id = media_content_id.removeprefix(PLAYLIST_PREFIX)
            return await self._async_browse_playlist(playlist_id)

        raise BrowseError(f"Media not found: {media_content_type} / {media_content_id}")

    async def async_get_browse_image(
        self,
        media_content_type: str,
        media_content_id: str,
        media_image_id: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """Fetch a protected Kokozi browse image."""
        if not media_image_id:
            return None, None
        return await self.coordinator.client.async_fetch_image(
            await self.coordinator.async_get_access_token(), media_image_id
        )

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Fetch the current protected Kokozi media image."""
        image_url = self.media_image_url
        if image_url is None:
            return None, None
        return await self.coordinator.client.async_fetch_image(
            await self.coordinator.async_get_access_token(), image_url
        )

    async def _async_jump(self, jump: str) -> None:
        """Jump to the next or previous story."""
        playlist_id = self._current_playlist_id
        if not playlist_id:
            return

        await self.coordinator.client.async_play_house_story(
            await self.coordinator.async_get_access_token(),
            self.house_id,
            playlist_id,
            jump=jump,
        )
        await self.coordinator.async_refresh_after_command()

    async def _async_set_relative_volume(self, offset: int) -> None:
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

    async def _async_browse_root(self) -> BrowseMedia:
        """Browse the playlist for the Arti currently placed on the house."""
        children = []
        if (arti := self._current_arti) and (
            playlist_id := arti.get("currentPlaylistId")
        ):
            children.append(
                BrowseMedia(
                    title=arti.get("name") or playlist_id,
                    media_class=MediaClass.PLAYLIST,
                    media_content_id=f"{PLAYLIST_PREFIX}{playlist_id}",
                    media_content_type=MediaType.PLAYLIST,
                    can_play=False,
                    can_expand=True,
                    thumbnail=self.get_browse_image_url(
                        MediaType.PLAYLIST,
                        f"{PLAYLIST_PREFIX}{playlist_id}",
                        media_image_id=_arti_thumbnail_url(arti),
                    ),
                )
            )
        elif playlist_id := self._current_playlist_id:
            children.append(
                BrowseMedia(
                    title=self._current_playlist_name or playlist_id,
                    media_class=MediaClass.PLAYLIST,
                    media_content_id=f"{PLAYLIST_PREFIX}{playlist_id}",
                    media_content_type=MediaType.PLAYLIST,
                    can_play=False,
                    can_expand=True,
                    thumbnail=self.get_browse_image_url(
                        MediaType.PLAYLIST,
                        f"{PLAYLIST_PREFIX}{playlist_id}",
                        media_image_id=playlist_thumbnail_url(playlist_id),
                    ),
                )
            )

        return BrowseMedia(
            title="Kokozi",
            media_class=MediaClass.DIRECTORY,
            media_content_id="",
            media_content_type="",
            children_media_class=MediaClass.PLAYLIST,
            can_play=False,
            can_expand=True,
            children=children,
        )

    async def _async_browse_playlist(self, playlist_id: str) -> BrowseMedia:
        """Browse playlist stories."""
        if not self._can_play_playlist(playlist_id):
            raise BrowseError(
                "Kokozi House can only browse the playlist for its current Arti"
            )

        playlist = await self.coordinator.async_get_playlist(playlist_id)
        thumbnail = playlist_thumbnail_url(playlist_id)
        children = [
            BrowseMedia(
                title=story.get("name") or story["id"],
                media_class=MediaClass.TRACK,
                media_content_id=_story_media_id(playlist_id, story["id"]),
                media_content_type=MediaType.TRACK,
                can_play=True,
                can_expand=False,
                thumbnail=self.get_browse_image_url(
                    MediaType.TRACK,
                    _story_media_id(playlist_id, story["id"]),
                    media_image_id=thumbnail_url(story["id"]),
                ),
            )
            for story in playlist.get("stories", [])
            if story.get("id")
        ]

        return BrowseMedia(
            title=playlist.get("name") or playlist_id,
            media_class=MediaClass.PLAYLIST,
            media_content_id=f"{PLAYLIST_PREFIX}{playlist_id}",
            media_content_type=MediaType.PLAYLIST,
            children_media_class=MediaClass.TRACK,
            can_play=False,
            can_expand=True,
            thumbnail=self.get_browse_image_url(
                MediaType.PLAYLIST,
                f"{PLAYLIST_PREFIX}{playlist_id}",
                media_image_id=thumbnail,
            ),
            children=children,
        )

    @property
    def _current_playlist_id(self) -> str | None:
        play = self.house.get("play") or {}
        return play.get("playlistId")

    @property
    def _current_story_id(self) -> str | None:
        play = self.house.get("play") or {}
        return play.get("storyId")

    @property
    def _current_playlist(self) -> dict[str, Any] | None:
        playlist_id = self._current_playlist_id
        if playlist_id:
            return self.coordinator.data.playlists.get(playlist_id)
        return None

    @property
    def _current_arti(self) -> dict[str, Any] | None:
        arti_id = (self.house.get("arti") or {}).get("artiId")
        if not arti_id:
            return None
        return self.coordinator.data.arties.get(arti_id)

    def _can_play_playlist(self, playlist_id: str) -> bool:
        """Return whether the playlist belongs to the current Arti."""
        arti = self._current_arti
        if not arti:
            return playlist_id == self._current_playlist_id
        return playlist_id == arti.get("currentPlaylistId")

    @property
    def _current_playlist_name(self) -> str | None:
        playlist = self._current_playlist
        return playlist.get("name") if playlist else self._current_playlist_id

    @property
    def _current_story(self) -> dict[str, Any] | None:
        story_id = self._current_story_id
        playlist = self._current_playlist
        if not story_id or not playlist:
            return None
        for story in playlist.get("stories", []):
            if story.get("id") == story_id:
                return story
        return None


def _story_media_id(playlist_id: str, story_id: str) -> str:
    """Return a Kokozi story media id."""
    return f"{PLAYLIST_PREFIX}{playlist_id}/story/{story_id}"


def _arti_thumbnail_url(arti: dict[str, Any]) -> str | None:
    """Return the best known Arti thumbnail URL."""
    return arti_thumbnail_url(arti.get("typeId"))
