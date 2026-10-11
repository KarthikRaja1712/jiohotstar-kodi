#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a Kodi repository for GitHub Pages.

Scans the project root for add-on folders (any directory containing addon.xml),
then writes into the output folder (default: ./docs):

    docs/addons.xml
    docs/addons.xml.md5
    docs/zips/<addon_id>/<addon_id>-<version>.zip
    docs/zips/<addon_id>/icon.png, fanart.jpg   (if present)
    docs/.nojekyll, docs/index.html

Usage:
    python tools/build_repo.py
    python tools/build_repo.py --github YOUR_USER/jiohotstar-kodi   # also rewrites repo URLs
    python tools/build_repo.py --out docs --root .

Then enable GitHub Pages (Settings > Pages > Deploy from branch > /docs).
Users install  https://<user>.github.io/<repo>/zips/repository.jiohotstar/repository.jiohotstar-<ver>.zip
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

EXCLUDE_DIRS = {".git", ".github", ".vscode", "__pycache__", ".idea", "node_modules", ".pytest_cache"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", ".gitignore"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".zip", ".swp", ".tmp")
ASSET_FILES = ("icon.png", "fanart.jpg")
XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)


def find_addons(root):
    addons = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and name not in EXCLUDE_DIRS and \
                os.path.isfile(os.path.join(path, "addon.xml")):
            addons.append(path)
    return addons


def read_addon_xml(path):
    xml_path = os.path.join(path, "addon.xml")
    with open(xml_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        elem = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        raise SystemExit("Invalid XML in %s: %s" % (xml_path, exc))
    addon_id, version = elem.get("id"), elem.get("version")
    if not addon_id or not version:
        raise SystemExit("%s: <addon> needs id and version" % xml_path)
    if addon_id != os.path.basename(path.rstrip("/\\")):
        raise SystemExit("%s: addon id '%s' must equal its folder name" % (xml_path, addon_id))
    return addon_id, version, XML_DECL.sub("", text).strip()


def rewrite_repo_urls(addon_dir, github):
    """Point the repository add-on's info/checksum/datadir at GitHub Pages."""
    user, _, repo = github.partition("/")
    if not user or not repo:
        raise SystemExit("--github must look like USER/REPO")
    base = "https://%s.github.io/%s/" % (user, repo)
    xml_path = os.path.join(addon_dir, "addon.xml")
    with open(xml_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"(<info[^>]*>)[^<]*(</info>)", r"\g<1>%saddons.xml\g<2>" % base, text)
    text = re.sub(r"(<checksum[^>]*>)[^<]*(</checksum>)", r"\g<1>%saddons.xml.md5\g<2>" % base, text)
    text = re.sub(r"(<datadir[^>]*>)[^<]*(</datadir>)", r"\g<1>%szips/\g<2>" % base, text)
    with open(xml_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("  rewrote repository URLs -> %s" % base)


def make_zip(addon_dir, addon_id, version, out_dir):
    dest_dir = os.path.join(out_dir, "zips", addon_id)
    if os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir)
    zip_path = os.path.join(dest_dir, "%s-%s.zip" % (addon_id, version))
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for current, dirs, files in os.walk(addon_dir):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for fname in sorted(files):
                if fname in EXCLUDE_FILES or fname.endswith(EXCLUDE_SUFFIXES):
                    continue
                full = os.path.join(current, fname)
                rel = os.path.relpath(full, os.path.dirname(addon_dir))
                zf.write(full, rel.replace(os.sep, "/"))
                count += 1
    for asset in ASSET_FILES:
        src = os.path.join(addon_dir, asset)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest_dir, asset))
    print("  %s (%d files)" % (os.path.relpath(zip_path), count))
    return zip_path


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Build Kodi repository files for GitHub Pages")
    parser.add_argument("--root", default=os.path.dirname(here), help="project root (default: parent of tools/)")
    parser.add_argument("--out", default=None, help="output folder (default: <root>/docs)")
    parser.add_argument("--github", default=None, help="USER/REPO: rewrite repository add-on URLs for GitHub Pages")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    out_dir = os.path.abspath(args.out or os.path.join(root, "docs"))
    addons = find_addons(root)
    if not addons:
        raise SystemExit("No add-on folders (with addon.xml) found in %s" % root)

    if args.github:
        for path in addons:
            if os.path.basename(path).startswith("repository."):
                rewrite_repo_urls(path, args.github)

    os.makedirs(out_dir, exist_ok=True)
    zips_dir = os.path.join(out_dir, "zips")
    if os.path.isdir(zips_dir):
        shutil.rmtree(zips_dir)

    print("Building into %s" % out_dir)
    blocks = []
    for path in addons:
        addon_id, version, xml_text = read_addon_xml(path)
        print("[%s] %s" % (addon_id, version))
        blocks.append(xml_text)
        make_zip(path, addon_id, version, out_dir)

    addons_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n%s\n</addons>\n' % \
                 "\n\n".join(blocks)
    data = addons_xml.encode("utf-8")
    with open(os.path.join(out_dir, "addons.xml"), "wb") as fh:
        fh.write(data)
    digest = hashlib.md5(data).hexdigest()
    with open(os.path.join(out_dir, "addons.xml.md5"), "w", encoding="ascii") as fh:
        fh.write(digest)  # Kodi expects the bare hash, no trailing newline

    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    links = []
    for path in addons:
        addon_id, version, _ = read_addon_xml(path)
        links.append('<li><a href="zips/%s/%s-%s.zip">%s-%s.zip</a></li>' % (addon_id, addon_id, version, addon_id, version))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset=utf-8><title>Kodi repository</title>"
                 "<h1>Kodi repository</h1><p>Install the repository zip in Kodi: "
                 "Add-ons &gt; Install from zip file.</p><ul>%s</ul>\n" % "".join(links))

    print("addons.xml.md5 = %s" % digest)
    print("Done. Commit '%s' and enable GitHub Pages (Deploy from branch, /docs)." % os.path.relpath(out_dir, root))


if __name__ == "__main__":
    sys.exit(main())
