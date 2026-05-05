import logging

import httpx

from .config import Settings

log = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """A call to sotra or libretranslate failed."""


class SotraClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._base = settings.sotra_url.rstrip("/")
        self._client = client

    async def translate(self, text: str, source: str, target: str) -> str:
        # The workaround_jitsi_limitation branch exposes a LibreTranslate-shaped
        # endpoint at /libretranslate. We use it so the response parsing mirrors
        # the libretranslate path below.
        url = f"{self._base}/libretranslate"
        payload = {"q": text, "source": source, "target": target, "format": "text"}
        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise BackendError(f"sotra request failed: {exc}") from exc
        if response.status_code != 200:
            raise BackendError(
                f"sotra returned {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        translated = data.get("translatedText")
        if not isinstance(translated, str):
            raise BackendError(f"sotra returned unexpected body: {data!r}")
        return translated


class LibreTranslateClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._base = settings.libretranslate_url.rstrip("/")
        self._api_key = settings.libretranslate_api_key
        self._client = client

    async def translate(self, text: str, source: str, target: str) -> str:
        url = f"{self._base}/translate"
        payload = {
            "q": text,
            "source": source,
            "target": target,
            "format": "text",
            "api_key": self._api_key,
        }
        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise BackendError(f"libretranslate request failed: {exc}") from exc
        if response.status_code != 200:
            raise BackendError(
                f"libretranslate returned {response.status_code}: "
                f"{response.text[:500]}"
            )
        data = response.json()
        translated = data.get("translatedText")
        if not isinstance(translated, str):
            raise BackendError(f"libretranslate returned unexpected body: {data!r}")
        return translated
