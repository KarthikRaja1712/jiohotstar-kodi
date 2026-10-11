# -*- coding: utf-8 -*-
"""Logging, settings, JSON/cache helpers and config loading."""
import copy
import hashlib
import json
import os
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from . import constants

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
CACHE_DIR = os.path.join(PROFILE, "cache")
ENDPOINTS_FILE = os.path.join(PROFILE, "endpoints.json")


# ----------------------------------------------------------------- basics
def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def tr(string_id):
    return ADDON.getLocalizedString(string_id)


def get_setting(key):
    return ADDON.getSetting(key)


def get_bool(key):
    return ADDON.getSettingBool(key)


def get_int(key, default=0):
    try:
        return ADDON.getSettingInt(key)
    except Exception:
        try:
            return int(ADDON.getSetting(key))
        except (TypeError, ValueError):
            return default


def log(message, level=xbmc.LOGINFO):
    """Log to kodi.log. Never pass tokens/OTPs here."""
    if level == xbmc.LOGDEBUG:
        if not get_bool("debug_logging"):
            return
        level = xbmc.LOGINFO
    xbmc.log("[%s] %s" % (ADDON_ID, message), level)


def notify(message, error=False, time_ms=5000):
    icon = xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO
    xbmcgui.Dialog().notification(ADDON_NAME, message, icon, time_ms)


# ----------------------------------------------------------------- JSON files
def write_private_json(path, data):
    """Atomically write JSON, readable only by the current user where supported."""
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


# ----------------------------------------------------------------- cache
def _cache_path(key):
    return os.path.join(CACHE_DIR, hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")


def cache_get(key, ttl_minutes):
    if ttl_minutes <= 0:
        return None
    data = read_json(_cache_path(key))
    if not data or time.time() - data.get("t", 0) > ttl_minutes * 60:
        return None
    return data.get("v")


def cache_set(key, value, ttl_minutes):
    if ttl_minutes <= 0:
        return
    ensure_dir(CACHE_DIR)
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as fh:
            json.dump({"t": time.time(), "v": value}, fh)
    except (OSError, TypeError) as exc:
        log("cache write failed: %s" % exc, xbmc.LOGWARNING)


def cache_clear():
    if not os.path.isdir(CACHE_DIR):
        return
    for name in os.listdir(CACHE_DIR):
        try:
            os.remove(os.path.join(CACHE_DIR, name))
        except OSError:
            pass


# ----------------------------------------------------------------- config
def deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """Defaults merged with the user's endpoints.json (created on first run)."""
    if not os.path.exists(ENDPOINTS_FILE):
        ensure_dir(PROFILE)
        try:
            with open(ENDPOINTS_FILE, "w", encoding="utf-8") as fh:
                json.dump(constants.DEFAULT_CONFIG, fh, indent=2, ensure_ascii=False)
            log("Created %s" % ENDPOINTS_FILE)
        except OSError as exc:
            log("Could not write endpoints.json: %s" % exc, xbmc.LOGERROR)
    user = read_json(ENDPOINTS_FILE, {})
    return deep_merge(constants.DEFAULT_CONFIG, user)


# ----------------------------------------------------------------- JSON helpers
def dig(data, path):
    """Fetch a value by dotted path ('a.b.0.c') or list path. None if missing."""
    parts = path.split(".") if isinstance(path, str) else list(path)
    cur = data
    for part in parts:
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            else:
                return None
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def first(data, paths):
    """First non-empty value among candidate paths."""
    for path in paths or []:
        value = dig(data, path)
        if value not in (None, "", [], {}):
            return value
    return None


def render(obj, ctx):
    """Substitute {placeholders} in strings, recursively (no str.format: JSON braces are safe)."""
    if isinstance(obj, str):
        for key, value in ctx.items():
            obj = obj.replace("{%s}" % key, "" if value is None else str(value))
        return obj
    if isinstance(obj, dict):
        return {k: render(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render(v, ctx) for v in obj]
    return obj
