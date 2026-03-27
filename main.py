from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import AstrBotConfig

import msal


@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.command("auth")
    async def auth(self, event: AstrMessageEvent):
        client_id = self.config.get("MS_CLIENT_ID")
        tenant_id = "consumers"
        scopes = ["Tasks.ReadWrite"]

        authority = f"https://login.microsoftonline.com/{tenant_id}"
        cache = msal.SerializableTokenCache()

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
            yield event.plain_result("")
            logger.info("Access token: " + result["access_token"])

        if result:
            yield event.plain_result(f"Token request failed: {result.get('error')} | {result.get('error_description')}")
            logger.error(f"Token request failed: {result.get('error')} | {result.get('error_description')}")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
