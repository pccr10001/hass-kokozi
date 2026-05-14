"""API client for Kokozi."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

from aiohttp import ClientError, ClientSession

from .const import (
    API_BASE_URL,
    API_V1_BASE_URL,
    ASSETS_BASE_URL,
    AUTH_BASE_URL,
    CLIENT_ID,
    CLIENT_NAME,
    CLIENT_SECRET,
    CLOUDFRONT_BASE_URL,
    DEFAULT_COUNTRY_CODE,
    DEFAULT_LOCALE,
    DEEP_LINK_AUTH_CODE,
    LOGGER,
    REDIRECT_URL,
)

LOGIN_INIT_URL = f"{API_BASE_URL}/auth/login/init"
TOKEN_URL = f"{API_BASE_URL}/auth/token"

APP_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 9; SM-A805N Build/PQ3B.190801.04221524) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Safari/537.36"
)
IMAGE_USER_AGENT = (
    "Dalvik/2.1.0 (Linux; U; Android 9; SM-A805N Build/PQ3B.190801.04221524)"
)

APP_HEADERS = {
    "Origin": AUTH_BASE_URL,
    "User-Agent": APP_USER_AGENT,
    "X-Requested-With": "com.boomdevice.kokozi",
    "Referer": f"{AUTH_BASE_URL}/",
}


class KokoziError(Exception):
    """Base Kokozi API error."""


class KokoziAuthError(KokoziError):
    """Kokozi authentication error."""


class KokoziCannotConnect(KokoziError):
    """Kokozi connection error."""


@dataclass(slots=True)
class KokoziToken:
    """Token response from Kokozi."""

    access_token: str
    refresh_token: str | None
    token_type: str | None
    expires_in: int | None
    issues_at: str | None
    expires_at: str | None
    refresh_expires_at: str | None
    raw: dict[str, Any]


class KokoziApiClient:
    """Small async client for the Kokozi auth API."""

    def __init__(self, session: ClientSession) -> None:
        """Initialize the API client."""
        self._session = session

    async def async_get_login_url(self, provider: str) -> str:
        """Start Kokozi login and return the browser URL."""
        data = {
            "provider": provider,
            "clientName": CLIENT_NAME,
            "locale": DEFAULT_LOCALE,
            "countryCode": DEFAULT_COUNTRY_CODE,
            "redirectUrl": REDIRECT_URL,
        }

        try:
            LOGGER.debug("Starting Kokozi login init for provider %s", provider)
            response = await self._session.post(
                LOGIN_INIT_URL,
                data=data,
                headers={
                    **APP_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                allow_redirects=False,
            )
        except (TimeoutError, ClientError) as err:
            raise KokoziCannotConnect("Timed out while starting login") from err

        async with response:
            LOGGER.debug(
                "Kokozi login init response: provider=%s status=%s location=%s",
                provider,
                response.status,
                response.headers.get("Location"),
            )
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if location:
                    return location

            body = await response.text()
            safe_body = _sanitize_response_body(body, {})
            LOGGER.warning(
                "Kokozi login init failed: provider=%s status=%s body=%s",
                provider,
                response.status,
                safe_body[:1000],
            )
            raise KokoziAuthError(
                f"Unexpected login init response: {response.status} {body[:200]}"
            )

    async def async_exchange_deep_link(self, callback_url: str) -> KokoziToken:
        """Exchange a Kokozi deep link callback URL for tokens."""
        auth_code = extract_deep_link_auth_code(callback_url)
        LOGGER.debug(
            "Exchanging Kokozi deep link auth code: code_length=%s",
            len(auth_code),
        )
        token = await self._async_request_token(
            {
                "grant_type": "authorization_code",
                "code": auth_code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        )
        if token is not None:
            return token

        token = await self._async_request_token(
            {
                "grant_type": "authorization_code",
                DEEP_LINK_AUTH_CODE: auth_code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        )
        if token is not None:
            return token

        raise KokoziAuthError("Unable to exchange deep link auth code for token")

    async def async_refresh_token(self, refresh_token: str) -> KokoziToken:
        """Refresh a Kokozi access token."""
        token = await self._async_request_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        )
        if token is None:
            raise KokoziAuthError("Unable to refresh token")
        return token

    async def async_get_houses(
        self, access_token: str, owner_id: str
    ) -> list[dict[str, Any]]:
        """Return houses for the owner."""
        data = await self._async_authenticated_request(
            "GET",
            f"{API_V1_BASE_URL}/houses/",
            access_token,
            params={"owner": owner_id},
        )
        if isinstance(data, list):
            return data
        raise KokoziAuthError("Unexpected houses response")

    async def async_get_arties(
        self, access_token: str, owner_id: str
    ) -> list[dict[str, Any]]:
        """Return arties for the user."""
        data = await self._async_authenticated_request(
            "GET",
            f"{API_V1_BASE_URL}/arties/",
            access_token,
            params={"user-id": owner_id},
        )
        if isinstance(data, dict) and isinstance(data.get("arties"), list):
            return data["arties"]
        raise KokoziAuthError("Unexpected arties response")

    async def async_get_playlist(
        self, access_token: str, playlist_id: str
    ) -> dict[str, Any]:
        """Return a playlist."""
        data = await self._async_authenticated_request(
            "GET",
            f"{API_V1_BASE_URL}/playlists/{playlist_id}",
            access_token,
        )
        if isinstance(data, dict):
            return data
        raise KokoziAuthError("Unexpected playlist response")

    async def async_pause_house(
        self, access_token: str, house_id: str, pause: bool
    ) -> None:
        """Pause or resume a house."""
        await self._async_authenticated_request(
            "POST",
            f"{API_V1_BASE_URL}/houses/{house_id}/state/pause",
            access_token,
            json_data={"pause": pause},
        )

    async def async_stop_house(self, access_token: str, house_id: str) -> None:
        """Stop a house."""
        await self._async_authenticated_request(
            "POST",
            f"{API_V1_BASE_URL}/houses/{house_id}/state/stop",
            access_token,
            json_data={"stop": True},
        )

    async def async_play_house_story(
        self,
        access_token: str,
        house_id: str,
        playlist_id: str,
        *,
        story_id: str | None = None,
        jump: str | None = None,
    ) -> None:
        """Play a story or jump within the active playlist."""
        payload = {"playlistId": playlist_id}
        if story_id is not None:
            payload["storyId"] = story_id
        if jump is not None:
            payload["jump"] = jump

        await self._async_authenticated_request(
            "POST",
            f"{API_V1_BASE_URL}/houses/{house_id}/state/story/play",
            access_token,
            json_data=payload,
        )

    async def async_set_house_repeat(
        self, access_token: str, house_id: str, repeat: str
    ) -> None:
        """Set house repeat mode."""
        await self._async_authenticated_request(
            "POST",
            f"{API_V1_BASE_URL}/houses/{house_id}/play-mode/repeat",
            access_token,
            json_data={"repeat": repeat},
        )

    async def async_set_house_shuffle(
        self, access_token: str, house_id: str, shuffle: bool
    ) -> None:
        """Set house shuffle mode."""
        await self._async_authenticated_request(
            "POST",
            f"{API_V1_BASE_URL}/houses/{house_id}/play-mode/shuffle",
            access_token,
            json_data={"shuffle": shuffle},
        )

    async def async_set_house_volume(
        self, access_token: str, house_id: str, current: int
    ) -> None:
        """Set house volume."""
        await self._async_authenticated_request(
            "PUT",
            f"{API_V1_BASE_URL}/houses/{house_id}/status/volume/current",
            access_token,
            json_data={"current": current},
        )

    async def async_set_house_led_lightness(
        self, access_token: str, house_id: str, lightness: int
    ) -> None:
        """Set house LED lightness."""
        await self._async_authenticated_request(
            "PUT",
            f"{API_V1_BASE_URL}/houses/{house_id}/led/lightness",
            access_token,
            json_data={"lightness": lightness},
        )

    async def async_fetch_image(
        self, access_token: str, image_url: str
    ) -> tuple[bytes, str]:
        """Fetch a protected Kokozi thumbnail."""
        try:
            response = await self._session.get(
                image_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": IMAGE_USER_AGENT,
                    "Accept-Encoding": "gzip",
                },
            )
        except (TimeoutError, ClientError) as err:
            raise KokoziCannotConnect("Timed out while fetching image") from err

        async with response:
            if response.status == 200:
                return await response.read(), response.headers.get(
                    "Content-Type", "image/png"
                )
            LOGGER.warning(
                "Kokozi image response failed: status=%s url=%s",
                response.status,
                image_url,
            )
            raise KokoziAuthError(f"Unexpected image response: {response.status}")

    async def _async_authenticated_request(
        self,
        method: str,
        url: str,
        access_token: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated Kokozi request."""
        try:
            response = await self._session.request(
                method,
                url,
                params=params,
                json=json_data,
                headers={
                    **APP_HEADERS,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
        except (TimeoutError, ClientError) as err:
            raise KokoziCannotConnect(f"Timed out while requesting {url}") from err

        async with response:
            body = await response.text()
            LOGGER.debug(
                "Kokozi API response: method=%s url=%s status=%s content_type=%s body_length=%s",
                method,
                url,
                response.status,
                response.headers.get("Content-Type"),
                len(body),
            )
            if response.status in (200, 201):
                if not body:
                    return None
                return json.loads(body)

            safe_body = _sanitize_response_body(body, {})
            LOGGER.warning(
                "Kokozi API request failed: method=%s url=%s status=%s body=%s",
                method,
                url,
                response.status,
                safe_body[:1000],
            )
            if response.status in (401, 403):
                raise KokoziAuthError(f"Authentication failed: {response.status}")
            raise KokoziAuthError(f"Unexpected API response: {response.status}")

    async def _async_request_token(self, payload: dict[str, Any]) -> KokoziToken | None:
        """Request a token, returning None for expected auth failures."""
        token = await self._async_post_token(payload, use_json=True)
        if token is not None:
            return token

        return await self._async_post_token(payload, use_json=False)

    async def _async_post_token(
        self, payload: dict[str, Any], *, use_json: bool
    ) -> KokoziToken | None:
        """Post a token request as JSON or form data."""
        request_kwargs: dict[str, Any]
        if use_json:
            request_kwargs = {
                "json": payload,
                "headers": {
                    **APP_HEADERS,
                    "Content-Type": "application/json",
                },
            }
        else:
            request_kwargs = {
                "data": payload,
                "headers": {
                    **APP_HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            }

        payload_log = _redact_token_payload(payload)
        try:
            LOGGER.debug(
                "Requesting Kokozi token: encoding=%s payload=%s",
                "json" if use_json else "form",
                payload_log,
            )
            response = await self._session.post(TOKEN_URL, **request_kwargs)
        except (TimeoutError, ClientError) as err:
            raise KokoziCannotConnect("Timed out while requesting token") from err

        async with response:
            content_type = response.headers.get("Content-Type")
            if response.status in (200, 201):
                data = await response.json(content_type=None)
                LOGGER.debug(
                    "Kokozi token response succeeded: encoding=%s status=%s keys=%s content_type=%s expires_at=%s refresh_expires_at=%s",
                    "json" if use_json else "form",
                    response.status,
                    sorted(data),
                    content_type,
                    data.get("expiresAt"),
                    data.get("refreshExpiresAt"),
                )
                return _token_from_response(data)

            body = await response.text()
            safe_body = _sanitize_response_body(body, payload)
            LOGGER.warning(
                "Kokozi token response failed: encoding=%s status=%s content_type=%s payload=%s body=%s",
                "json" if use_json else "form",
                response.status,
                content_type,
                payload_log,
                safe_body[:1000],
            )

            if response.status in (400, 401, 403):
                return None

            raise KokoziAuthError(
                f"Unexpected token response: {response.status} {body[:200]}"
            )


def extract_deep_link_auth_code(callback_url: str) -> str:
    """Extract deep_link_auth_code from a Kokozi callback URL."""
    parsed = urlparse(callback_url.strip())
    LOGGER.debug(
        "Parsing Kokozi callback URL: scheme=%s netloc=%s path=%s query_keys=%s fragment_keys=%s",
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        sorted(parse_qs(parsed.query)),
        sorted(parse_qs(parsed.fragment)),
    )
    if parsed.scheme != "kokozi":
        raise KokoziAuthError("Callback URL must start with kokozi://")

    for url_part in (parsed.query, parsed.fragment):
        values = parse_qs(url_part).get(DEEP_LINK_AUTH_CODE)
        if values and values[0]:
            return values[0]

    raise KokoziAuthError("Callback URL does not contain deep_link_auth_code")


def get_jwt_subject(access_token: str) -> str | None:
    """Return the JWT subject without verifying the signature."""
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)
    except (IndexError, ValueError, json.JSONDecodeError) as err:
        LOGGER.warning("Unable to decode Kokozi access token subject: %s", err)
        return None

    subject = data.get("sub")
    return subject if isinstance(subject, str) else None


def thumbnail_url(identifier: str | None) -> str | None:
    """Build a generic thumbnail URL."""
    if not identifier:
        return None
    return f"{CLOUDFRONT_BASE_URL}/thumbnails/{identifier}/thumbnail.png"


def arti_thumbnail_url(type_id: str | None) -> str | None:
    """Build an Arti thumbnail URL."""
    if not type_id:
        return None
    return (
        f"{ASSETS_BASE_URL}/arti/thumbnail/arti-upper-thumbnail/{type_id}.png"
    )


def playlist_thumbnail_url(playlist_id: str | None) -> str | None:
    """Build a playlist thumbnail URL."""
    if not playlist_id:
        return None
    return f"{CLOUDFRONT_BASE_URL}/playlists/thumbnails/{playlist_id}/thumbnail.png"


def _redact_token_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a log-safe view of token request payload."""
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"client_secret", "code", DEEP_LINK_AUTH_CODE, "refresh_token"}:
            redacted[key] = f"<redacted length={len(str(value))}>"
        else:
            redacted[key] = value
    return redacted


def _sanitize_response_body(body: str, payload: dict[str, Any]) -> str:
    """Remove secrets from response body before logging it."""
    safe_body = body.replace(CLIENT_SECRET, "<redacted client_secret>")
    for key in ("code", DEEP_LINK_AUTH_CODE, "refresh_token"):
        value = payload.get(key)
        if value:
            safe_body = safe_body.replace(str(value), f"<redacted {key}>")
    return safe_body


def _token_from_response(data: dict[str, Any]) -> KokoziToken:
    """Normalize a Kokozi token response."""
    access_token = data.get("access_token") or data.get("accessToken")
    if not access_token:
        raise KokoziAuthError("Token response does not contain access token")

    return KokoziToken(
        access_token=access_token,
        refresh_token=data.get("refresh_token") or data.get("refreshToken"),
        token_type=data.get("token_type") or data.get("tokenType"),
        expires_in=data.get("expires_in") or data.get("expiresIn"),
        issues_at=data.get("issuesAt") or data.get("issuedAt"),
        expires_at=data.get("expiresAt"),
        refresh_expires_at=data.get("refreshExpiresAt"),
        raw=data,
    )
