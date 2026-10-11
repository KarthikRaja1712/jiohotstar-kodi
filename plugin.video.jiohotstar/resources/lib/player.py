# -*- coding: utf-8 -*-
"""Playback: resolve a stream and hand it to inputstream.adaptive (Widevine)."""
from urllib.parse import urlencode

import xbmc
import xbmcgui
import xbmcplugin

from . import utils
from .api import ApiError, AuthError, ConfigError

DRM_SCHEME = "com.widevine.alpha"
MIME = {"dash": "application/dash+xml", "hls": "application/vnd.apple.mpegurl"}
ISA_PROTOCOL = {"dash": "mpd", "hls": "hls"}

# Android Mobile User-Agent Spoofing Header
MOBILE_USER_AGENT = "Hotstar;com.myplaylist.asiatv/24.03.04 (Android/12; SM-G998B)"


def _fail(handle, message):
    utils.notify(message, error=True)
    if handle >= 0:
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())


def _isa_ready(protocol, has_drm):
    """Check inputstream.adaptive + Widevine through InputStream Helper."""
    if not utils.get_bool("run_isa_helper"):
        return True
    try:
        import inputstreamhelper
    except ImportError:
        utils.log("inputstreamhelper not installed", xbmc.LOGWARNING)
        return True  # cannot verify; let Kodi try
    helper = inputstreamhelper.Helper(ISA_PROTOCOL[protocol], drm=DRM_SCHEME if has_drm else None)
    return bool(helper.check_inputstream())


def _build_license_key(api, license_url):
    cfg = api.cfg
    headers_dict = api.build_headers("license_headers")
    
    # Force Mobile User-Agent in DRM license request headers
    headers_dict["User-Agent"] = MOBILE_USER_AGENT
    
    headers = urlencode(headers_dict)
    return "%s|%s|%s|%s" % (
        license_url, headers,
        cfg.get("license_request_format", "R{SSM}"),
        cfg.get("license_response_format", ""),
    )


def _build_listitem(api, info, item_id):
    protocol = info.get("protocol", "dash")
    li = xbmcgui.ListItem(path=info["url"])
    li.setContentLookup(False)
    li.setMimeType(MIME.get(protocol, MIME["dash"]))
    li.setProperty("inputstream", "inputstream.adaptive")
    li.setProperty("inputstream.adaptive.manifest_type", ISA_PROTOCOL.get(protocol, "mpd"))

    # Force Mobile User-Agent on Manifest and Segment HTTP Stream Requests
    stream_headers_dict = api.build_headers("stream_headers")
    stream_headers_dict["User-Agent"] = MOBILE_USER_AGENT
    stream_headers = urlencode(stream_headers_dict)

    if stream_headers:
        li.setProperty("inputstream.adaptive.manifest_headers", stream_headers)
        li.setProperty("inputstream.adaptive.stream_headers", stream_headers)

    if info.get("license_url"):
        li.setProperty("inputstream.adaptive.license_type", DRM_SCHEME)
        li.setProperty("inputstream.adaptive.license_key", _build_license_key(api, info["license_url"]))

    max_res = utils.get_int("max_resolution", 1080)
    if max_res:
        li.setProperty("inputstream.adaptive.chooser_resolution_max", "%dp" % max_res)
        li.setProperty("inputstream.adaptive.chooser_resolution_secure_max", "%dp" % max_res)

    if info.get("subtitles"):
        li.setSubtitles(info["subtitles"])
    return li


def _apply_language_preferences(timeout=25):
    """After playback starts, select preferred audio/subtitle languages if available."""
    audio_pref = utils.get_setting("audio_language").strip().lower()
    sub_pref = utils.get_setting("subtitle_language").strip().lower()
    if not audio_pref and not sub_pref:
        return
    monitor = xbmc.Monitor()
    player = xbmc.Player()
    waited = 0.0
    while waited < timeout and not monitor.abortRequested():
        if player.isPlayingVideo() and player.getTime() > 0:
            break
        if monitor.waitForAbort(0.5):
            return
        waited += 0.5
    else:
        return
    try:
        if audio_pref:
            streams = [s.lower() for s in player.getAvailableAudioStreams()]
            for index, lang in enumerate(streams):
                if lang == audio_pref or lang.startswith(audio_pref):
                    player.setAudioStream(index)
                    break
        if sub_pref:
            subs = [s.lower() for s in player.getAvailableSubtitleStreams()]
            for index, lang in enumerate(subs):
                if lang == sub_pref or lang.startswith(sub_pref):
                    player.setSubtitleStream(index)
                    player.showSubtitles(True)
                    break
    except Exception as exc:
        utils.log("language preference failed: %s" % exc, xbmc.LOGWARNING)


def play(api, handle, item_id, item_type):
    if not api.is_logged_in():
        _fail(handle, utils.tr(30520))
        return
    try:
        info = api.get_playback(item_id, item_type)
    except AuthError:
        api.logout()
        _fail(handle, utils.tr(30520))
        return
    except ConfigError:
        _fail(handle, utils.tr(30517))
        return
    except ApiError as exc:
        utils.log("playback error: %s" % exc, xbmc.LOGERROR)
        _fail(handle, "%s: %s" % (utils.tr(30518), exc))
        return

    if not _isa_ready(info.get("protocol", "dash"), bool(info.get("license_url"))):
        _fail(handle, utils.tr(30519))
        return

    li = _build_listitem(api, info, item_id)
    xbmcplugin.setResolvedUrl(handle, True, li)
    _apply_language_preferences()