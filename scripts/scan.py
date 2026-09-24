#!/usr/bin/env python3
"""
DreamosatX Store - GitHub Actions Scanner
Cihazdan bağımsız, GitHub sunucusunda çalışır.
"""
import json
import re
import os
import sys
from collections import Counter, defaultdict

try:
    import urllib.request as urlreq
    import urllib.parse as urlparse
except ImportError:
    import urllib2 as urlreq
    import urlparse

# ============================================================
# KAYNAKLAR — Buraya yeni repo ekle
# ============================================================
SOURCES = [
    # (owner, repo, branch)
    ("adrenalinnrw",  "DreamosatXStore",      "main"),
    ("Belfagor2005",  "LinuxsatPanel",        "main"),
    ("audi06",        "dreamosatdownloader",  "master"),
    ("wwwgoper77-wq", "MohamedStore",         "main"),
]

OUTPUT_FILE = "catalog.json"

# GitHub Actions token (otomatik gelir)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ============================================================
# Kategori ve mimari kalıpları
# ============================================================
ARCH_PATTERNS = {
    "aarch64": r"aarch64|arm64",
    "armhf":   r"arm|cortexa",
    "mipsel":  r"mips|mipsel",
    "sh4":     r"sh4",
}

CAT_PATTERNS = {
    "plugin_iptv":     r"iptv|m3u|stalker|xtream|xstreamity|e2iplayer",
    "plugin_epg":      r"epg|crossepg|xmltv|rytec|jediepg",
    "plugin_weather":  r"weather|foreca|msn|yahoo",
    "plugin_utility":  r"utility|manager|cleaner|tool|filecommander",
    "plugin_backup":   r"backup|flashbackup|dflash|dbackup",
    "plugin_softcam":  r"softcam|oscam|cccam|ncam|gcam|mgcamd",
    "plugin_media":    r"media|player|youtube|vavoo|plex",
    "plugin_settings": r"setting|satellite|channel",
    "plugin_ppanel":   r"panel|menu|luxsat|satvenus|tspanel",
    "skin":            r"skin",
    "dependencies":    r"python-|libc|libssl|libcrypto|gstreamer|libusb",
}

# ============================================================
# Yardımcılar
# ============================================================
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

def detect_arch(name, folder=""):
    t = (name + " " + folder).lower()
    if "arm+mips" in t or "arm-mips" in t:
        return "all"
    for arch, pat in ARCH_PATTERNS.items():
        if re.search(pat, t):
            return arch
    return "all"

def detect_category(name, folder=""):
    t = (name + " " + folder).lower()
    for cat, pat in CAT_PATTERNS.items():
        if re.search(pat, t):
            return cat
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

# ============================================================
# Tarama
# ============================================================
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
                "category": detect_category(fname, folder),
                "arch":     detect_arch(fname, folder),
                "url":      base + urlparse.quote(path),
                "package":  pkg,
                "source":   "deb" if ext == "deb" else "ipk",
                "github":   "%s/%s" % (owner, repo),
                "size":     item.get("size", 0),
                "_vkey":    version_key(pkg),
            })

    # Her paket için en yeni 3 sürüm
    groups = defaultdict(list)
    for p in plugins:
        groups[p["package"].split("_")[0]].append(p)

    final = []
    for group in groups.values():
        group.sort(key=lambda x: x["_vkey"], reverse=True)
        final.extend(group[:3])

    for p in final:
        del p["_vkey"]

    return final

def save(plugins, path=OUTPUT_FILE):
    catalog = {
        "_info": "DreamosatX Store - auto generated by GitHub Actions",
        "version": 1,
        "generated": __import__("time").strftime("%Y-%m-%d %H:%M UTC", __import__("time").gmtime()),
        "plugins": plugins,
        "stats_url": ""
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("=== DreamosatX Scanner ===")
    plugins = scan()
    save(plugins)

    cats = Counter(p["category"] for p in plugins)
    archs = Counter(p["arch"] for p in plugins)

    print("\n[✓] Toplam: %d plugin" % len(plugins))
    print("\nKategoriler:")
    for k, v in cats.most_common():
        print("   %-20s %d" % (k, v))
    print("\nMimariler:")
    for k, v in archs.most_common():
        print("   %-12s %d" % (k, v))
    print("\n[✓] catalog.json yazıldı")
