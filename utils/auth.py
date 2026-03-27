"""Authentication utilities for Microsoft To-Do plugin."""
import json
import os
import time
from pathlib import Path

import msal
from dotenv import load_dotenv

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

DEFAULT_SCOPE = "https://graph.microsoft.com/.default"
DEFAULT_STORAGE_DIR = Path("~/.ms-todo-auth").expanduser()

# Use constants for storage paths
STORAGE_DIR = get_astrbot_data_path() / "plugin_data" / "ms_todo"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

ENV_FILE = STORAGE_DIR / ".env"
TOKEN_FILE = STORAGE_DIR / "token.json"
CACHE_FILE = STORAGE_DIR / "msal_cache.bin"


def load_settings() -> tuple[str, str, list[str]]:
    """Loads authentication settings from the .env file.

    Returns:
        A tuple containing the client ID, tenant ID, and scopes.
    
    Raises:
        SystemExit: If the MS_CLIENT_ID is not found in the .env file.
    """
    load_dotenv(ENV_FILE)

    client_id = os.getenv("MS_CLIENT_ID", "").strip()
    tenant_id = os.getenv("MS_TENANT_ID", "common").strip() or "common"
    scopes = [s.strip() for s in os.getenv("MS_SCOPES", DEFAULT_SCOPE).split(",") if s.strip()]

    if not client_id:
        raise SystemExit(f"Missing MS_CLIENT_ID in env file: {ENV_FILE}")

    return client_id, tenant_id, scopes


def load_cache() -> msal.SerializableTokenCache:
    """Loads the MSAL token cache from the cache file.

    Returns:
        An MSAL SerializableTokenCache object.
    
    Raises:
        SystemExit: If the cache file is invalid.
    """
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        try:
            cache.deserialize(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"Invalid cache file: {CACHE_FILE} ({exc})") from exc
    return cache


def save_cache(cache: msal.SerializableTokenCache) -> None:
    """Saves the MSAL token cache to the cache file if it has changed.

    Args:
        cache: The MSAL SerializableTokenCache object to save.
    """
    if cache.has_state_changed:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(cache.serialize(), encoding="utf-8")


def load_token_file() -> dict:
    """Loads the access token from the token file.

    Returns:
        A dictionary containing the token data, or an empty dictionary if the file doesn't exist.
        
    Raises:
        SystemExit: If the token file is corrupted or has an invalid format.
    """
    if not TOKEN_FILE.exists():
        return {}
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Token file is corrupted: {TOKEN_FILE} ({exc})") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Token file format invalid: {TOKEN_FILE}")
    return data


def is_token_valid(token_data: dict, skew_seconds: int = 120) -> bool:
    """Checks if the access token is still valid.

    Args:
        token_data: A dictionary containing the token data.
        skew_seconds: A buffer in seconds to account for clock skew.

    Returns:
        True if the token is valid, False otherwise.
    """
    access_token = str(token_data.get("access_token", "")).strip()
    if not access_token:
        return False

    expires_on = token_data.get("expires_on")
    try:
        expires_on_int = int(expires_on)
    except (TypeError, ValueError):
        return False

    return expires_on_int - int(time.time()) > skew_seconds


def save_token(result: dict) -> None:
    """Saves the access token to the token file.

    Args:
        result: A dictionary containing the token acquisition result.
    """
    payload = {
        "access_token": result.get("access_token"),
        "token_type": result.get("token_type"),
        "expires_in": result.get("expires_in"),
        "expires_on": result.get("expires_on"),
        "scope": result.get("scope"),
        "obtained_at": int(time.time()),
    }
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def acquire_token(interactive: bool = True) -> dict:
    """Acquires a new access token.

    This function attempts to acquire a token silently using the cache first.
    If that fails and interactive mode is enabled, it initiates a device flow,
    prompting the user to log in.

    Args:
        interactive: If True, allows interactive user login via device flow.

    Returns:
        A dictionary containing the token acquisition result.

    Raises:
        SystemExit: If the token request fails.
    """
    client_id, tenant_id, scopes = load_settings()
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    cache = load_cache()

    app = msal.PublicClientApplication(client_id=client_id, authority=authority, token_cache=cache)

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])

    if (not result or "access_token" not in result) and interactive:
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise SystemExit(f"Failed to create device flow: {flow}")
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    save_cache(cache)

    if result and "access_token" in result:
        save_token(result)
        return result

    if result:
        raise SystemExit(
            "Token request failed: "
            f"{result.get('error')} | {result.get('error_description')}"
        )

    raise SystemExit("Token request failed and no cached account available")


def get_valid_access_token(allow_interactive: bool = True) -> str:
    """Gets a valid access token, refreshing if necessary.

    This is the main function to get a token. It first checks for a valid
    cached token, then tries to acquire one silently, and finally falls back
    to an interactive login if allowed.

    Args:
        allow_interactive: If True, allows interactive user login as a fallback.

    Returns:
        A valid access token string.
        
    Raises:
        SystemExit: If token acquisition fails and interactive mode is disabled.
    """
    token_data = load_token_file()
    if is_token_valid(token_data):
        return str(token_data.get("access_token"))

    try:
        result = acquire_token(interactive=False)
        return str(result.get("access_token"))
    except SystemExit:
        if not allow_interactive:
            raise

    result = acquire_token(interactive=True)
    return str(result.get("access_token"))


def get_cached_access_token() -> str:
    """Gets an access token from the cache without any network requests.

    This function first checks the simple token file, then tries to acquire
    a token silently from the MSAL cache. It does not perform any
    interactive login.

    Returns:
        The cached access token string, or an empty string if not found.
    """
    token_data = load_token_file()
    access_token = str(token_data.get("access_token", "")).strip()
    if access_token:
        return access_token

    if CACHE_FILE.exists():
        try:
            result = acquire_token(interactive=False)
            return str(result.get("access_token", "")).strip()
        except SystemExit:
            return ""

    return ""
