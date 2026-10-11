# -*- coding: utf-8 -*-
"""JioHotstar API client: auth, token cache, catalogue and playback resolution.

All URLs, request bodies and response field locations come from the config
(see constants.py / endpoints.json). This module contains no service-specific
endpoint knowledge.
"""
import time
import uuid

import requests

from . import utils

AUTH_FILE = "auth.json"
DEVICE_FILE = "device.json"
PLAYABLE_TYPES = ("movie", "episode", "live")


class ApiError(Exception):
    """Network / HTTP / parsing failure."""


class AuthError(ApiError):
    """Not logged in, or session rejected."""


class ConfigError(ApiError):
    """An endpoint is not configured in endpoints.json."""


class TokenStore(object):
    """Auth tokens persisted as JSON (mode 0600) in addon_data."""

    def __init__(self):
        import os
        self.path = os.path.join(utils.PROFILE, AUTH_FILE)

    def load(self):
        return utils.read_json(self.path, {}) or {}

    def save(self, data):
        utils.write_private_json(self.path, data)

    def clear(self):
        import os
        try:
            os.remove(self.path)
        except OSError:
            pass


class JioHotstarAPI(object):
    def __init__(self):
        self.cfg = utils.load_config()
        self.session = requests.Session()
        self.tokens = TokenStore()
        self.timeout = utils.get_int("request_timeout", 20)
        self.device_id = self._device_id()

    # ------------------------------------------------------------ device id
    def _device_id(self):
        import os
        path = os.path.join(utils.PROFILE, DEVICE_FILE)
        data = utils.read_json(path, {}) or {}
        if not data.get("device_id"):
            data = {"device_id": str(uuid.uuid4())}
            utils.write_private_json(path, data)
        return data["device_id"]

    def reset_device(self):
        import os
        self.tokens.clear()
        try:
            os.remove(os.path.join(utils.PROFILE, DEVICE_FILE))
        except OSError:
            pass
        utils.cache_clear()

    # ------------------------------------------------------------ low level
    def _request(self, name, ctx=None, auth=True, _retried=False):
        ep = (self.cfg.get("endpoints") or {}).get(name) or {}
        url = ep.get("url")
        if not url:
            raise ConfigError("Endpoint '%s' has no url in endpoints.json" % name)

        tokens = self.tokens.load()
        if auth:
            if not tokens.get("token"):
                raise AuthError("Not logged in")
            self._ensure_fresh(tokens)
            tokens = self.tokens.load()

        context = {
            "device_id": self.device_id,
            "token": tokens.get("token", "") if auth else "",
            "refresh_token": tokens.get("refresh_token", ""),
        }
        for key, value in (ctx or {}).items():
            context[key] = "" if value is None else value

        headers = {}
        for key, value in (self.cfg.get("headers") or {}).items():
            if "{token}" in str(value) and not context["token"]:
                continue
            headers[key] = utils.render(value, context)
        for key, value in (ep.get("headers") or {}).items():
            headers[key] = utils.render(value, context)

        kwargs = {"headers": headers, "timeout": self.timeout}
        if ep.get("params"):
            kwargs["params"] = utils.render(ep["params"], context)
        if ep.get("json"):
            kwargs["json"] = utils.render(ep["json"], context)
        if ep.get("data"):
            kwargs["data"] = utils.render(ep["data"], context)

        method = (ep.get("method") or "GET").upper()
        rendered_url = utils.render(url, context)
        utils.log("%s %s (%s)" % (method, rendered_url.split("?")[0], name), 0)  # LOGDEBUG
        try:
            resp = self.session.request(method, rendered_url, **kwargs)
        except requests.RequestException as exc:
            raise ApiError("Network error: %s" % exc)

        if resp.status_code in (401, 403) and auth:
            if not _retried and self._refresh():
                return self._request(name, ctx, auth, True)
            raise AuthError("Session rejected (HTTP %d)" % resp.status_code)
        if resp.status_code >= 400:
            raise ApiError("HTTP %d from %s" % (resp.status_code, name))
        try:
            return resp.json()
        except ValueError:
            raise ApiError("Invalid JSON from %s" % name)

    # ------------------------------------------------------------ auth
    def is_logged_in(self):
        tokens = self.tokens.load()
        if not tokens.get("token"):
            return False
        expires_at = tokens.get("expires_at", 0)
        if expires_at and time.time() > expires_at and not tokens.get("refresh_token"):
            return False
        return True

    def request_otp(self, country_code, mobile):
        digits = "".join(ch for ch in country_code if ch.isdigit())
        resp = self._request("otp_request", {
            "mobile": mobile, "country_code": country_code, "country_code_digits": digits,
        }, auth=False)
        return utils.first(resp, self.cfg["response"]["otp_request_id"]) or ""

    def verify_otp(self, otp, request_id, country_code, mobile):
        digits = "".join(ch for ch in country_code if ch.isdigit())
        resp = self._request("otp_verify", {
            "otp": otp, "request_id": request_id, "mobile": mobile,
            "country_code": country_code, "country_code_digits": digits,
        }, auth=False)
        self._save_tokens(resp, {})

    def logout(self):
        self.tokens.clear()
        utils.cache_clear()

    def _save_tokens(self, resp, previous):
        rcfg = self.cfg["response"]
        token = utils.first(resp, rcfg["token"])
        if not token:
            raise ApiError("No token found in response (check response.token paths)")
        refresh = utils.first(resp, rcfg["refresh_token"]) or previous.get("refresh_token", "")
        expires_at = 0
        raw_exp = utils.first(resp, rcfg["expires_in"])
        if raw_exp:
            try:
                value = float(raw_exp)
                if value > 1e12:      # epoch milliseconds
                    expires_at = value / 1000.0
                elif value > 1e9:     # epoch seconds
                    expires_at = value
                else:                 # seconds from now
                    expires_at = time.time() + value
            except (TypeError, ValueError):
                pass
        data = {
            "token": str(token),
            "refresh_token": str(refresh or ""),
            "expires_at": expires_at,
            "user_id": str(utils.first(resp, rcfg["user_id"]) or ""),
            "saved_at": time.time(),
        }
        self.tokens.save(data)

    def _refresh(self):
        ep = (self.cfg.get("endpoints") or {}).get("token_refresh") or {}
        tokens = self.tokens.load()
        if not ep.get("url") or not tokens.get("refresh_token"):
            return False
        try:
            resp = self._request("token_refresh", auth=False)
            self._save_tokens(resp, tokens)
            return True
        except ApiError as exc:
            utils.log("Token refresh failed: %s" % exc)
            return False

    def _ensure_fresh(self, tokens):
        expires_at = tokens.get("expires_at", 0)
        if expires_at and time.time() > expires_at - 60:
            self._refresh()

    # ------------------------------------------------------------ catalogue
    def _image(self, value):
        if isinstance(value, dict):
            value = utils.first(value, ["url", "src", "href"]) or ""
        elif isinstance(value, list):
            value = value[0] if value else ""
            if isinstance(value, dict):
                value = utils.first(value, ["url", "src", "href"]) or ""
        value = str(value or "")
        if value and not value.startswith(("http://", "https://")):
            base = self.cfg.get("image_base", "")
            value = base.rstrip("/") + "/" + value.lstrip("/") if base else ""
        return value

    @staticmethod
    def _int(value):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _normalize(self, raw):
        fields = self.cfg["item_fields"]
        item_id = utils.first(raw, fields["id"])
        if item_id is None:
            return None
        raw_type = str(utils.first(raw, fields["type"]) or "").lower()
        item_type = (self.cfg.get("type_map") or {}).get(raw_type, "movie")
        genres = utils.first(raw, fields["genres"]) or []
        if isinstance(genres, str):
            genres = [g.strip() for g in genres.split(",") if g.strip()]
        elif isinstance(genres, list):
            genres = [g.get("name", "") if isinstance(g, dict) else str(g) for g in genres]
        return {
            "id": str(item_id),
            "type": item_type,
            "title": str(utils.first(raw, fields["title"]) or "Unknown"),
            "plot": str(utils.first(raw, fields["plot"]) or ""),
            "poster": self._image(utils.first(raw, fields["poster"])),
            "fanart": self._image(utils.first(raw, fields["fanart"])),
            "season": self._int(utils.first(raw, fields["season"])),
            "episode": self._int(utils.first(raw, fields["episode"])),
            "duration": self._int(utils.first(raw, fields["duration"])),
            "year": self._int(utils.first(raw, fields["year"])),
            "show_title": str(utils.first(raw, fields["show_title"]) or ""),
            "genres": [g for g in genres if g],
        }

    def _parse_items(self, resp):
        raw = utils.first(resp, self.cfg["response"]["items"])
        if isinstance(resp, list) and not raw:
            raw = resp
        items = []
        for entry in raw if isinstance(raw, list) else []:
            if isinstance(entry, dict):
                item = self._normalize(entry)
                if item:
                    items.append(item)
        return items

    def _has_next(self, resp, items, limit):
        flag = utils.first(resp, self.cfg["response"]["next_page"])
        if flag is not None:
            return bool(flag) and flag not in ("false", "False", 0)
        return len(items) >= limit

    def _listing(self, endpoint, ctx, cache_key):
        ttl = utils.get_int("cache_minutes", 30)
        cached = utils.cache_get(cache_key, ttl)
        if cached is not None:
            return cached["items"], cached["has_next"]
        limit = utils.get_int("items_per_page", 30)
        page = int(ctx.get("page", 1))
        ctx = dict(ctx, limit=limit, offset=(page - 1) * limit,
                   languages=utils.get_setting("content_languages"))
        resp = self._request(endpoint, ctx)
        items = self._parse_items(resp)
        has_next = self._has_next(resp, items, limit)
        utils.cache_set(cache_key, {"items": items, "has_next": has_next}, ttl)
        return items, has_next

    def get_page(self, slug, page=1):
        key = "page|%s|%d|%s|%d" % (slug, page, utils.get_setting("content_languages"),
                                    utils.get_int("items_per_page", 30))
        return self._listing("page", {"slug": slug, "page": page}, key)

    def get_children(self, item_id, item_type):
        key = "children|%s|%s" % (item_id, item_type)
        items, _ = self._listing("children", {"id": item_id, "type": item_type, "page": 1}, key)
        return items

    def search(self, query, page=1):
        # Searches are not cached.
        limit = utils.get_int("items_per_page", 30)
        resp = self._request("search", {
            "query": query, "page": page, "limit": limit, "offset": (page - 1) * limit,
            "languages": utils.get_setting("content_languages"),
        })
        items = self._parse_items(resp)
        return items, self._has_next(resp, items, limit)

    # ------------------------------------------------------------ playback
    @staticmethod
    def _detect_protocol(value, url):
        text = ("%s %s" % (value or "", url or "")).lower()
        if "mpd" in text or "dash" in text:
            return "dash"
        if "m3u8" in text or "hls" in text:
            return "hls"
        return ""

    @staticmethod
    def _subtitle_urls(raw):
        urls = []
        for entry in raw if isinstance(raw, list) else []:
            if isinstance(entry, str):
                urls.append(entry)
            elif isinstance(entry, dict):
                url = utils.first(entry, ["url", "src", "href", "path"])
                if url:
                    urls.append(url)
        return urls

    def get_playback(self, item_id, item_type):
        """Return dict: url, protocol ('dash'|'hls'), license_url, subtitles."""
        resp = self._request("playback", {"id": item_id, "type": item_type})
        rcfg = self.cfg["response"]
        sf = self.cfg["stream_fields"]

        streams = utils.first(resp, rcfg["streams"])
        if isinstance(streams, dict):
            streams = list(streams.values()) if all(isinstance(v, dict) for v in streams.values()) else [streams]
        if not streams:
            streams = [resp]
        top_license = utils.first(resp, rcfg["license_url"])

        want = "dash" if utils.get_int("stream_protocol", 0) == 0 else "hls"
        want_hevc = utils.get_bool("prefer_hevc")
        candidates = []
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            url = utils.first(stream, sf["url"])
            if not url or not isinstance(url, str):
                continue
            protocol = self._detect_protocol(utils.first(stream, sf["protocol"]), url)
            if not protocol:
                continue
            codec = str(utils.first(stream, sf["codec"]) or "").lower()
            is_hevc = any(tag in codec for tag in ("hevc", "h265", "h.265"))
            candidates.append({
                "url": url,
                "protocol": protocol,
                "license_url": utils.first(stream, sf["license_url"]) or top_license or "",
                "subtitles": self._subtitle_urls(utils.first(stream, sf["subtitles"])),
                "_rank": (protocol == want, is_hevc == want_hevc),
            })
        if not candidates:
            raise ApiError("No playable stream found in playback response")
        candidates.sort(key=lambda c: c["_rank"], reverse=True)
        best = candidates[0]
        best.pop("_rank", None)
        return best

    def build_headers(self, key):
        """Render license_headers / stream_headers with the current token."""
        tokens = self.tokens.load()
        ctx = {"token": tokens.get("token", ""), "device_id": self.device_id}
        out = {}
        for name, value in (self.cfg.get(key) or {}).items():
            if "{token}" in str(value) and not ctx["token"]:
                continue
            out[name] = utils.render(value, ctx)
        return out
