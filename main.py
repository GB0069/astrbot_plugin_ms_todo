import json

import aiohttp
import msal
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core import AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

@register("ms-todo", "Grime", "Let astrbot help you manage your tasks in Microsoft To-Do", "0.0.1")
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.access_token = None
        self.cache_path = get_astrbot_data_path() / "plugin_data" / self.name

    @filter.command("todo-auth")
    async def auth(self, event: AstrMessageEvent):
        client_id = self.config.get("MS_CLIENT_ID")
        tenant_id = "consumers"
        scopes = ["Tasks.ReadWrite"]

        authority = f"https://login.microsoftonline.com/{tenant_id}"

        cache = self._load_cache()

        app = msal.PublicClientApplication(client_id=client_id, authority=authority, token_cache=cache)

        result = None
        accounts = app.get_accounts()

        if accounts:
            result = app.acquire_token_silent(scopes, account=accounts[0])

        if not result or "access_token" not in result:
            flow = app.initiate_device_flow(scopes=scopes)
            if "user_code" not in flow:
                yield event.plain_result("Failed to create device flow")
                return

            yield event.plain_result(flow["message"])
            result = app.acquire_token_by_device_flow(flow)

        if result and "access_token" in result:
            yield event.plain_result("Successfully get access token")
            self.access_token = result["access_token"]
            self._save_cache(cache)
            return

        if result:
            logger.error(
                f"Token request failed: {result.get('error')} | {result.get('error_description')}"
            )
            return

    @filter.command("todo-ls")
    async def list_lists(self, event: AstrMessageEvent):
        try:
            response = await Main.graph_request(method="GET", path="/me/todo/lists", timeout=10)
            if not response:
                yield event.plain_result("No lists found")
                return

            for item in response["value"]:
                yield event.plain_result(f"{item['displayName']}")
        except RuntimeError as exc:
            yield event.plain_result(str(exc))
            logger.error(exc)
            return

    @filter.command("list-tasks")
    async def list_tasks(self, event: AstrMessageEvent):
        yield event.plain_result("Not implemented")

    def _load_cache(self) -> msal.SerializableTokenCache:
        """Loads the MSAL token cache from the cache file.

        Returns:
            An MSAL SerializableTokenCache object.

        Raises:
            SystemExit: If the cache file is invalid.
        """
        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            try:
                cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise SystemExit(f"Invalid cache file: {self.cache_path} ({exc})") from exc
        return cache

    def _save_cache(self, cache: msal.SerializableTokenCache) -> None:
        """Saves the MSAL token cache to the cache file if it has changed.

        Args:
            cache: The MSAL SerializableTokenCache object to save.
        """
        if cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(cache.serialize(), encoding="utf-8")

    @staticmethod
    async def request_once(
            method: str,
            url: str,
            headers: dict,
            payload: dict | None,
            timeout_seconds: int,
    ) -> tuple[int, dict | str | None, str]:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        import asyncio
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, headers=headers, json=payload) as resp:
                    text = await resp.text()
                    parsed: dict | str | None
                    if not text.strip():
                        parsed = None
                    else:
                        try:
                            parsed = json.loads(text)
                        except ValueError:
                            parsed = text
                    return resp.status, parsed, text
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"Network timeout when calling Graph API: {exc}") from exc
        except aiohttp.ClientError as exc:
            raise RuntimeError(f"Network error when calling Graph API: {exc}") from exc

    async def graph_request(
            self,
            method: str,
            path: str,
            timeout: int,
            payload: dict | None = None,
            retry_on_401: bool = True
    ) -> dict | None:

        token = self.access_token

        if not token:
            raise RuntimeError("Access token required")

        url = f"{GRAPH_BASE}{path}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        status, parsed, text = await Main.request_once(method, url, headers, payload, timeout)

        if status == 401 and retry_on_401:
            if not token:
                raise RuntimeError("Access token required")

            headers["Authorization"] = f"Bearer {token}"
            status, parsed, text = await Main.request_once(method, url, headers, payload, timeout)

        if status >= 400:
            raise RuntimeError(f"Graph API error {status}: {parsed if parsed is not None else text}")

        if status == 204 or not text.strip():
            return None

        if isinstance(parsed, dict):
            return parsed

        raise RuntimeError(f"Unexpected non-JSON Graph response: {text}")


