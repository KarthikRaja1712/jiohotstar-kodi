# JioHotstar for Kodi (unofficial)

```
plugin.video.jiohotstar/   the video add-on
repository.jiohotstar/     repository add-on (auto-updates)
tools/build_repo.py        builds addons.xml, addons.xml.md5 and zips into docs/ for GitHub Pages
```

## IMPORTANT: configure the API endpoints first
JioHotstar's API is private and undocumented, so no URLs are hard-coded. On first run the add-on
writes `endpoints.json` to Kodi's addon_data folder:

- Linux: `~/.kodi/userdata/addon_data/plugin.video.jiohotstar/endpoints.json`
- Windows: `%APPDATA%\Kodi\userdata\addon_data\plugin.video.jiohotstar\endpoints.json`
- Android: `Android/data/org.xbmc.kodi/files/.kodi/userdata/addon_data/plugin.video.jiohotstar/`

Fill in, from your own logged-in browser/app session (DevTools Network tab or mitmproxy):

1. `endpoints.otp_request`, `otp_verify` (and optionally `token_refresh`): url, method, body.
2. `endpoints.page`, `children`, `search`, `playback`: url + params.
3. `categories`: the slug passed to `page` for Live TV, Movies, Shows, Sports.
4. `response.*`, `item_fields`, `stream_fields`: where the data sits in the JSON (dotted paths,
   several candidates allowed). Enable *Advanced > Debug logging* to see requests in kodi.log.

Placeholders available in any string: `{mobile} {country_code} {country_code_digits} {otp}
{request_id} {token} {refresh_token} {device_id} {id} {type} {slug} {page} {limit} {offset}
{query} {languages}`. See `endpoints.example.json` for the shape.

## Run it from VS Code
1. `pip install -r requirements-dev.txt` (autocomplete only).
2. Copy/symlink `plugin.video.jiohotstar` into Kodi's `addons` folder
   (Linux: `ln -s "$PWD/plugin.video.jiohotstar" ~/.kodi/addons/`), or zip it and use
   *Add-ons > Install from zip*. Restart Kodi.
3. Needs `script.module.requests`, `script.module.inputstreamhelper` and `inputstream.adaptive`
   (Kodi installs these dependencies automatically from the official repo).
4. Open the add-on > Log in (mobile number + OTP). Tokens are stored in `auth.json` (mode 600) in addon_data, never in settings.

## Publish a repository on GitHub Pages
```
python tools/build_repo.py --github YOUR_USER/jiohotstar-kodi
git add . && git commit -m "build" && git push
```
Then GitHub: Settings > Pages > Deploy from branch > `main` / `/docs`. Users install
`https://YOUR_USER.github.io/jiohotstar-kodi/zips/repository.jiohotstar/repository.jiohotstar-1.0.0.zip`.
Bump `version` in addon.xml and re-run the script for each release.
Before publishing replace `YourName` / `YOUR_USER` and the placeholder icons.

## Notes
- DRM: licences are requested from the service's own Widevine server with your session. Nothing is bypassed; a working CDM is required (InputStream Helper installs it where supported).
- Unofficial; may violate the service's Terms of Use. Personal use with your own subscription only.
- Audio/subtitle language preference is applied best-effort a few seconds after playback starts.
