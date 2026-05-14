"""Constants for the Kokozi integration."""

from __future__ import annotations

from logging import Logger, getLogger

DOMAIN = "kokozi"
LOGGER: Logger = getLogger(__package__)

API_BASE_URL = "https://api.kokozi.co.kr/v1.1"
API_V1_BASE_URL = "https://api.kokozi.co.kr/v1.0"
AUTH_BASE_URL = "https://auth.kokozi.co.kr"

CLIENT_NAME = "kokozi-mobile"
CLIENT_ID = "kokozi-mobile"
CLIENT_SECRET = "S5-gUDrpKoJ6IGRvgOM1BvFk4RZdtxaQYUGiZacmQrs"
DEFAULT_COUNTRY_CODE = "TW"
DEFAULT_LOCALE = "zh-TW"
REDIRECT_URL = "kokozi://BottomTab"

CONF_ACCESS_TOKEN = "access_token"
CONF_EXPIRES_IN = "expires_in"
CONF_EXPIRES_AT = "expires_at"
CONF_ISSUES_AT = "issues_at"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_REFRESH_EXPIRES_AT = "refresh_expires_at"
CONF_TOKEN_TYPE = "token_type"
CONF_LOGIN_PROVIDER = "login_provider"
CONF_LOGIN_URL = "login_url"
CONF_OWNER_ID = "owner_id"

CLOUDFRONT_BASE_URL = "https://drh0pw6ntc7tp.cloudfront.net"
ASSETS_BASE_URL = "https://assets-s3.kokozi.co.kr"

ATTR_ARTI_ID = "arti_id"
ATTR_ARTI_NAME = "arti_name"
ATTR_PLAYLIST_ID = "playlist_id"
ATTR_PLAYLIST_NAME = "playlist_name"
ATTR_STORY_ID = "story_id"
ATTR_SHUFFLE = "shuffle"
ATTR_REPEAT = "repeat"

CONF_POLLING_INTERVAL = "polling_interval"
DEFAULT_POLLING_INTERVAL = 60
MIN_POLLING_INTERVAL = 10
MAX_POLLING_INTERVAL = 3600

LOGIN_PROVIDER_EMAIL = "email"
LOGIN_PROVIDER_GOOGLE = "google"

DEEP_LINK_AUTH_CODE = "deep_link_auth_code"
