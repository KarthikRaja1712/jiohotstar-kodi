# -*- coding: utf-8 -*-
"""Default configuration for the JioHotstar add-on.

JioHotstar's API is private, undocumented and changes without notice, so NO
endpoint URLs are hard-coded here. Instead, the add-on copies this default
config to ``endpoints.json`` in its addon_data folder on first run. You fill in
the URLs / request bodies / response field paths you observe from your own
authenticated session (browser dev tools or mitmproxy), and the add-on does the
rest. Anything you leave out falls back to the defaults below.

Placeholders usable inside any string of an endpoint definition:
  {device_id} {token} {refresh_token} {mobile} {country_code} {country_code_digits}
  {otp} {request_id} {id} {type} {slug} {page} {limit} {offset} {query} {languages}
"""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_EMPTY_EP = {"method": "GET", "url": "", "params": {}, "json": {}, "data": {}, "headers": {}}


def _ep(method="GET", **kw):
    ep = dict(_EMPTY_EP)
    ep["method"] = method
    ep.update(kw)
    return ep


DEFAULT_CONFIG = {
    "_readme": (
        "Fill in the 'url' (and params/json/headers) of each endpoint from your own "
        "authenticated traffic. Strings may contain {placeholders}. Response field "
        "locations are dotted paths; the first non-empty candidate wins."
    ),
    # Prefix used when an image value is a relative path.
    "image_base": "",
    # Sent with every request. A header containing {token} is skipped when logged out.
    "headers": {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Authorization": "Bearer {token}",
    },
    "endpoints": {
        # Step 1 of login: ask the service to send an OTP to the mobile number.
        "otp_request": _ep("POST", json={"mobile": "{mobile}", "countryCode": "{country_code}"}),
        # Step 2: submit the OTP.
        "otp_verify": _ep("POST", json={"otp": "{otp}", "requestId": "{request_id}",
                                        "mobile": "{mobile}", "countryCode": "{country_code}"}),
        # Optional: exchange refresh token for a new token. Leave url empty if unsupported.
        "token_refresh": _ep("POST", json={"refreshToken": "{refresh_token}"}),
        # Listing of a category / page by slug (supports paging).
        "page": _ep("GET", params={"slug": "{slug}", "page": "{page}", "limit": "{limit}",
                                   "languages": "{languages}"}),
        # Children of a show / season / collection.
        "children": _ep("GET", params={"id": "{id}", "type": "{type}"}),
        # Search.
        "search": _ep("GET", params={"q": "{query}", "page": "{page}", "limit": "{limit}"}),
        # Resolve playable manifest(s) + license info for a movie/episode/live item.
        "playback": _ep("GET", params={"id": "{id}", "type": "{type}"}),
    },
    # Slug passed to the "page" endpoint for each home category.
    "categories": {"live": "", "movies": "", "shows": "", "sports": ""},
    # Where to find things in JSON responses (dotted paths, first non-empty wins).
    "response": {
        "otp_request_id": ["request_id", "requestId", "data.request_id", "data.requestId"],
        "token": ["token", "access_token", "data.token", "data.access_token", "data.userToken"],
        "refresh_token": ["refresh_token", "refreshToken", "data.refresh_token", "data.refreshToken"],
        "expires_in": ["expires_in", "expiresIn", "data.expires_in", "data.expiresIn"],
        "user_id": ["user_id", "userId", "data.user_id", "data.userId"],
        "items": ["items", "results", "data.items", "data.results", "body.results.items", "body.items"],
        "next_page": ["next", "nextPage", "data.next", "data.nextPage", "body.next"],
        "streams": ["streams", "data.streams", "playbackSets", "data.playbackSets",
                    "data.playback.streams", "body.results.playBackSets"],
        # Where licence info lives if it is NOT inside each stream object.
        "license_url": ["license_url", "licenseUrl", "data.license_url", "data.licenseUrl",
                        "data.drm.licenseUrl", "drm.licenseUrl"],
    },
    # Candidate keys (dotted) inside each catalogue item.
    "item_fields": {
        "id": ["id", "contentId", "content_id", "assetId"],
        "title": ["title", "name"],
        "plot": ["description", "plot", "synopsis", "shortDescription"],
        "poster": ["poster", "posterUrl", "image", "imageUrl", "images.poster", "images.vertical"],
        "fanart": ["fanart", "backdrop", "backdropUrl", "images.horizontal", "images.backdrop", "imageUrl"],
        "type": ["type", "contentType", "assetType"],
        "season": ["seasonNo", "season", "seasonNumber"],
        "episode": ["episodeNo", "episode", "episodeNumber"],
        "duration": ["duration", "durationSeconds"],
        "year": ["year", "releaseYear"],
        "show_title": ["showName", "showTitle", "seriesName"],
        "genres": ["genres", "genre"],
    },
    # Service type string (case-insensitive) -> internal type.
    "type_map": {
        "movie": "movie", "movies": "movie", "film": "movie",
        "show": "show", "series": "show", "tvshow": "show",
        "season": "season",
        "episode": "episode", "clip": "episode", "sport": "episode", "match": "episode",
        "live": "live", "channel": "live", "livetv": "live", "live_event": "live",
        "collection": "collection", "tray": "collection", "carousel": "collection",
    },
    # Candidate keys inside each stream object returned by the playback endpoint.
    "stream_fields": {
        "url": ["url", "playbackUrl", "manifestUrl", "manifest", "streamUrl"],
        "license_url": ["licenseUrl", "license_url", "widevineLicenseUrl", "licenceUrl",
                        "drm.licenseUrl", "drm.widevine.licenseUrl"],
        "protocol": ["protocol", "streamType", "type", "format"],
        "codec": ["codec", "videoCodec", "tags"],
        "subtitles": ["subtitles", "subs", "captions"],
    },
    # Headers sent to the Widevine licence server (rendered with {token} etc.).
    "license_headers": {
        "Content-Type": "application/octet-stream",
        "User-Agent": USER_AGENT,
        "Authorization": "Bearer {token}",
    },
    # Headers sent when ISA downloads manifests / segments.
    "stream_headers": {"User-Agent": USER_AGENT},
    # inputstream.adaptive licence_key tail fields: url|headers|REQUEST|RESPONSE
    "license_request_format": "R{SSM}",
    "license_response_format": "",
}
