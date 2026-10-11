# -*- coding: utf-8 -*-
"""JioHotstar for Kodi - plugin entry point and router."""
import sys
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import player, utils
from resources.lib.api import ApiError, AuthError, ConfigError, JioHotstarAPI

BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 else -1

PLAYABLE = ("movie", "episode", "live")
CONTENT_FOR_TYPE = {
    "movie": "movies", "show": "tvshows", "season": "seasons",
    "episode": "episodes", "live": "videos", "collection": "videos",
}
MEDIA_TYPE = {"movie": "movie", "show": "tvshow", "season": "season", "episode": "episode"}
CATEGORIES = (  # (config key, string id, content hint)
    ("live", 30500),
    ("movies", 30501),
    ("shows", 30502),
    ("sports", 30503),
)


def build_url(**kwargs):
    return "%s?%s" % (BASE_URL, urlencode({k: v for k, v in kwargs.items() if v not in (None, "")}))


# ------------------------------------------------------------------ list items
def _set_info(li, item):
    media_type = MEDIA_TYPE.get(item["type"], "video")
    tag = li.getVideoInfoTag() if hasattr(li, "getVideoInfoTag") else None
    if tag is not None and hasattr(tag, "setTitle"):  # Kodi 20+
        tag.setTitle(item["title"])
        tag.setPlot(item["plot"])
        tag.setMediaType(media_type)
        if item["year"]:
            tag.setYear(item["year"])
        if item["duration"]:
            tag.setDuration(item["duration"])
        if item["genres"]:
            tag.setGenres(item["genres"])
        if item["type"] in ("episode", "season") and item["season"]:
            tag.setSeason(item["season"])
        if item["type"] == "episode":
            if item["episode"]:
                tag.setEpisode(item["episode"])
            if item["show_title"]:
                tag.setTvShowTitle(item["show_title"])
        return
    info = {"title": item["title"], "plot": item["plot"], "mediatype": media_type}  # Kodi 19
    if item["year"]:
        info["year"] = item["year"]
    if item["duration"]:
        info["duration"] = item["duration"]
    if item["genres"]:
        info["genre"] = ", ".join(item["genres"])
    if item["season"]:
        info["season"] = item["season"]
    if item["episode"]:
        info["episode"] = item["episode"]
    if item["show_title"]:
        info["tvshowtitle"] = item["show_title"]
    li.setInfo("video", info)


def _label(item):
    if item["type"] == "episode" and item["episode"]:
        return "%s. %s" % (item["episode"], item["title"]) if item["season"] else item["title"]
    return item["title"]


def add_items(items):
    for item in items:
        li = xbmcgui.ListItem(label=_label(item))
        _set_info(li, item)
        art = {}
        if item["poster"]:
            art["poster"] = art["thumb"] = item["poster"]
        if item["fanart"]:
            art["fanart"] = item["fanart"]
            art.setdefault("thumb", item["fanart"])
        if art:
            li.setArt(art)
        if item["type"] in PLAYABLE:
            li.setProperty("IsPlayable", "true")
            url = build_url(action="play", id=item["id"], type=item["type"])
            xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
        else:
            url = build_url(action="children", id=item["id"], type=item["type"])
            xbmcplugin.addDirectoryItem(HANDLE, url, li, True)


def add_folder(label, **params):
    li = xbmcgui.ListItem(label=label)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(**params), li, True)


def finish(items=None):
    content = "videos"
    if items:
        counts = {}
        for item in items:
            counts[item["type"]] = counts.get(item["type"], 0) + 1
        content = CONTENT_FOR_TYPE.get(max(counts, key=counts.get), "videos")
    xbmcplugin.setContent(HANDLE, content)
    xbmcplugin.endOfDirectory(HANDLE)


# ------------------------------------------------------------------ routes
def root(api, params):
    if not api.is_logged_in():
        add_folder("[B]%s[/B]" % utils.tr(30506), action="login_prompt")
    cats = api.cfg.get("categories") or {}
    for key, string_id in CATEGORIES:
        add_folder(utils.tr(string_id), action="category", slug=cats.get(key, ""), page=1,
                   title=utils.tr(string_id))
    add_folder(utils.tr(30504), action="search")
    xbmcplugin.setContent(HANDLE, "videos")
    xbmcplugin.endOfDirectory(HANDLE)


def category(api, params):
    slug = params.get("slug", "")
    page = int(params.get("page", 1))
    items, has_next = api.get_page(slug, page)
    add_items(items)
    if has_next:
        add_folder(utils.tr(30505), action="category", slug=slug, page=page + 1)
    if not items:
        utils.notify(utils.tr(30515))
    finish(items)


def children(api, params):
    items = api.get_children(params["id"], params.get("type", ""))
    add_items(items)
    if not items:
        utils.notify(utils.tr(30515))
    finish(items)


def search(api, params):
    query = params.get("query")
    if not query:
        query = xbmcgui.Dialog().input(utils.tr(30516), type=xbmcgui.INPUT_ALPHANUM)
        if not query:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return
    page = int(params.get("page", 1))
    items, has_next = api.search(query, page)
    add_items(items)
    if has_next:
        add_folder(utils.tr(30505), action="search", query=query, page=page + 1)
    if not items:
        utils.notify(utils.tr(30515))
    finish(items)


def play(api, params):
    player.play(api, HANDLE, params["id"], params.get("type", "movie"))


def login_prompt(api, params):
    # Directory-context entry: end the (empty) directory then run the login flow.
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    login(api, params)


def login(api, params):
    dialog = xbmcgui.Dialog()
    country = utils.get_setting("country_code").strip() or "+91"
    mobile = utils.get_setting("mobile_number").strip()
    if not mobile:
        mobile = dialog.input(utils.tr(30509), type=xbmcgui.INPUT_NUMERIC).strip()
        if not mobile:
            return
        utils.ADDON.setSetting("mobile_number", mobile)
    try:
        request_id = api.request_otp(country, mobile)
        otp = dialog.input(utils.tr(30508), type=xbmcgui.INPUT_NUMERIC).strip()
        if not otp:
            return
        api.verify_otp(otp, request_id, country, mobile)
    except ConfigError:
        dialog.ok(utils.ADDON_NAME, utils.tr(30517))
        return
    except ApiError as exc:
        utils.log("login failed: %s" % exc, xbmc.LOGERROR)
        dialog.ok(utils.ADDON_NAME, "%s\n%s" % (utils.tr(30511), exc))
        return
    utils.notify(utils.tr(30510))
    xbmc.executebuiltin("Container.Refresh")


def logout(api, params):
    api.logout()
    utils.notify(utils.tr(30512))
    xbmc.executebuiltin("Container.Refresh")


def clear_cache(api, params):
    utils.cache_clear()
    utils.notify(utils.tr(30513))


def reset_device(api, params):
    api.reset_device()
    utils.notify(utils.tr(30514))


ROUTES = {
    "root": root, "category": category, "children": children, "search": search,
    "play": play, "login": login, "login_prompt": login_prompt, "logout": logout,
    "clear_cache": clear_cache, "reset_device": reset_device,
}
DIRECTORY_ACTIONS = ("root", "category", "children", "search")


def router(paramstring):
    params = dict(parse_qsl(paramstring))
    action = params.get("action", "root")
    handler = ROUTES.get(action)
    if handler is None:
        utils.log("Unknown action: %s" % action, xbmc.LOGWARNING)
        return
    api = JioHotstarAPI()
    try:
        handler(api, params)
    except ConfigError as exc:
        utils.log(str(exc), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(utils.ADDON_NAME, utils.tr(30517))
        _abort_directory(action)
    except AuthError:
        api.logout()
        utils.notify(utils.tr(30520), error=True)
        _abort_directory(action)
    except ApiError as exc:
        utils.log("API error: %s" % exc, xbmc.LOGERROR)
        utils.notify("%s: %s" % (utils.tr(30521), exc), error=True)
        _abort_directory(action)


def _abort_directory(action):
    if action in DIRECTORY_ACTIONS and HANDLE >= 0:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


if __name__ == "__main__":
    router(sys.argv[2][1:] if len(sys.argv) > 2 else "")
