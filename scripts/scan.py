#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DreamosatX Store - GitHub Actions Scanner
Kategoriler skin ile uyumlu: plugin, skin, tools, media, iptv, softcam, backup, other
"""
import json
import os
import re
import time
from collections import Counter, defaultdict

try:
    import urllib.request as urlreq
    import urllib.parse as urlparse
except ImportError:
    import urllib2 as urlreq
    import urlparse

# ============================================================
# KAYNAKLAR
# ============================================================
SOURCES = [
    ("adrenalinnrw",  "DreamosatXStore",      "main"),
    ("Belfagor2005",  "LinuxsatPanel",        "main"),
    ("audi06",        "dreamosatdownloader",  "master"),
    ("wwwgoper77-wq", "MohamedStore",         "main"),
]

OUTPUT_FILE = "catalog.json"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ============================================================
# KATEGORİLER — skin ile uyumlu (sıra önemli!)
# ============================================================
CAT_PATTERNS = [
    ("iptv",     r"iptv|m3u|stalker|xtream|xstreamity|e2iplayer|xclass|tivimate|xcp|jedimaker"),
    ("softcam",  r"softcam|oscam|cccam|ncam|gcam|mgcamd|wicardd|doscam|supcam|revcam|powercam|ultracam|emu"),
    ("backup",   r"backup|flashbackup|dflash|dbackup|autobackup|backupsuite|meoboot|barryallen|neoboot|multiboot|openmultiboot"),
    ("media",    r"\bmedia\b|\bplayer\b|youtube|vavoo|plex|kodi|radio|music|audio|\bvideo\b|filmon|iptvplayer|tsmedia"),
    ("skin",     r"\bskin\b|theme|skincomponent"),
    ("tools",    r"utility|\btool\b|manager|cleaner|filecommander|\bepg\b|crossepg|xmltv|rytec|jediepg|setting|satellite|channel|\bpanel\b|\bmenu\b|luxsat|satvenus|tspanel|weather|foreca|\bmsn\b|yahoo|picon|locale|bitrate|oscamstatus|keyupdater|cammanager|script|feed"),
]

ARCH_PATTERNS = [
    ("aarch64", r"aarch64|arm64"),
    ("armhf",   r"arm|cortexa"),
    ("mipsel",  r"mips|mipsel"),
    ("sh4",     r"sh4"),
]


def detect_arch(name, folder=""):
    t = (name + " " + folder).lower()
    if "arm+mips" in t or "arm-mips" in t or "arm-mips" in t:
        return "all"
    for arch, pat in ARCH_PATTERNS:
        if re.search(pat, t):
            return arch
    return "all"


def detect_category(name, folder=""):
    t = (name + " " + folder).lower()
    for cat, pat in CAT_PATTERNS:
        if re.search(pat, t):
            return cat
    if "plugin" in t:
        return "plugin"
    return "other"


def version_key(name):
    m = re.search(r'[_-]v?(\d+(?:\.\d+)*)', name)
    if not m:
        return (0,)
    try:
        return tuple(int(p) for p in m.group(1).split("."))
    except Exception:
        return (0,)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:80]


def clean_name(pkg):
    clean = pkg
    for pre in ("enigma2-plugin-extensions-", "enigma2-plugin-skins-",
                "enigma2-plugin-systemplugins-", "enigma2-plugin-",
                "enigma2-skin-", "enigma2-"):
        if clean.startswith(pre):
            clean = clean[len(pre):]
            break
    return clean.replace("_", " ").replace("-", " ").strip()[:70]


def gh_tree(owner, repo, branch):
    url = "https://api.github.com/repos/%s/%s/git/trees/%s?recursive=1" % (owner, repo, branch)
    headers = {"User-Agent": "DreamosatXStore-Scanner"}
    if GITHUB_TOKEN:
        headers["Authorization"] = "token " + GITHUB_TOKEN
    try:
        req = urlreq.Request(url, headers=headers)
        data = json.loads(urlreq.urlopen(req, timeout=60).read().decode("utf-8"))
        return data.get("tree", [])
    except Exception as e:
        print("[!] %s/%s: %s" % (owner, repo, e))
        return []


def scan():
    plugins = []
    seen = set()

    for owner, repo, branch in SOURCES:
        print("[+] %s/%s @ %s" % (owner, repo, branch))
        tree = gh_tree(owner, repo, branch)
        base = "https://raw.githubusercontent.com/%s/%s/%s/" % (owner, repo, branch)

        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not path.lower().endswith((".ipk", ".deb", ".zip", ".tar.gz")):
                continue

            fname = path.rsplit("/", 1)[-1]
            folder = path.rsplit("/", 1)[0] if "/" in path else ""
            ext = fname.rsplit(".", 1)[-1].lower()
            pkg = fname.rsplit(".", 1)[0]

            pid = slug(pkg)
            bp, n = pid, 1
            while pid in seen:
                n += 1
                pid = "%s-%d" % (bp, n)
            seen.add(pid)

            plugins.append({
                "id":       pid,
                "name":     clean_name(pkg),
                "desc":     clean_name(pkg),
                "long_desc": clean_name(pkg),
                "category": detect_category(fname, folder),
                "arch":     detect_arch(fname, folder),
                "url":      base + urlparse.quote(path),
                "package":  pkg,
                "source":   "deb" if ext == "deb" else "ipk",
                "author":   "DreamOSat",
                "github":   "%s/%s" % (owner, repo),
                "size":     item.get("size", 0),
                "rating":   0,
                "downloads": 0,
                "votes":    0,
                "featured": False,
                "new":      False,
                "_vkey":    version_key(pkg),
                "_added":   int(time.time()),
            })

    # Her paket için en yeni 3 sürümü tut
    groups = defaultdict(list)
    for p in plugins:
        groups[p["package"].split("_")[0]].append(p)

    final = []
    for group in groups.values():
        group.sort(key=lambda x: x["_vkey"], reverse=True)
        final.extend(group[:3])

    # En yeni 20 tanesine "new" damgası
    final_sorted = sorted(final, key=lambda x: x["_vkey"], reverse=True)
    for p in final_sorted[:20]:
        p["new"] = True

    # Popüler kategorilerden 8 tanesine "featured"
    featured_count = 0
    for cat in ("iptv", "softcam", "media", "skin", "tools", "plugin"):
        for p in final:
            if p["category"] == cat and featured_count < 8:
                p["featured"] = True
                featured_count += 1
                break

    # Temizlik
    for p in final:
        del p["_vkey"]
        del p["_added"]

    return final


def save(plugins, path=OUTPUT_FILE):
    catalog = {
        "_info": "DreamosatX Store - auto generated by GitHub Actions",
        "version": 1,
        "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "plugins": plugins,
        "stats_url": ""
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    print("=== DreamosatX Scanner ===")
    plugins = scan()
    save(plugins)

    cats = Counter(p["category"] for p in plugins)
    archs = Counter(p["arch"] for p in plugins)

    print("\n[✓] Toplam: %d plugin" % len(plugins))
    print("\nKategoriler:")
    for k, v in cats.most_common():
        print("   %-15s %d" % (k, v))
    print("\nMimariler:")
    for k, v in archs.most_common():
        print("   %-12s %d" % (k, v))
    print("\n[✓] catalog.json yazildi")
