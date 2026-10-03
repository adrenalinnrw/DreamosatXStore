#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DreamosatX Store - Otomatik Catalog Scanner (GitHub Actions)

v2: kategoriler DOĞRUDAN plugin'in tanıdığı isimlerle üretilir
    (plugin / skin / tools / media / iptv / softcam / backup / picon / other),
    ayrıca version, arch, icon ve 4 dilde kısa açıklama eklenir.
"""
import json
import os
import re
import time
from collections import Counter, defaultdict

try:
    import urllib.request as urlreq
    import urllib.parse as urlparse
except ImportError:                                    # py2
    import urllib2 as urlreq
    import urlparse

# ============================================================ KAYNAKLAR
SOURCES = [
    # (owner, repo, branch)
    ("adrenalinnrw",  "DreamosatXStore",      "main"),
    ("audi06",        "dreamosatdownloader",  "master"),
    ("wwwgoper77-wq", "MohamedStore",         "main"),
]

OUTPUT_FILE = "catalog.json"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
KEEP_VERSIONS = 3          # paket başına saklanan en yeni sürüm sayısı

# ============================================================ MİMARİ
# dosya adının son alanı (…_armhf.ipk) en güvenilir kaynak
ARCH_SUFFIX = {
    "all": "all", "noarch": "all",
    "aarch64": "aarch64", "arm64": "aarch64", "aarch64-3-14": "aarch64",
    "armhf": "armhf", "armv7ahf": "armhf", "armv7ahf-neon": "armhf", "arm": "armhf",
    "cortexa15hf-neon": "armhf", "cortexa9hf-neon": "armhf", "cortexa15hf-neon-vfpv4": "armhf",
    "mipsel": "mipsel", "mips32el": "mipsel", "mips": "mipsel", "mips32el-nf": "mipsel",
    "sh4": "sh4",
}
ARCH_WORDS = [                                        # yedek: ad içinde geçen kelime
    ("aarch64", r"(?:^|[\W_])(?:aarch64|arm64)(?:$|[\W_])"),
    ("armhf",   r"(?:^|[\W_])(?:armhf|armv7\w*|cortexa\d+\w*|arm)(?:$|[\W_])"),
    ("mipsel",  r"(?:^|[\W_])(?:mipsel|mips32el|mips)(?:$|[\W_])"),
    ("sh4",     r"(?:^|[\W_])sh4(?:$|[\W_])"),
]

# ============================================================ KATEGORİLER
# plugin'in (dxm_lang.py CAT_ORDER) tanıdığı isimler:
#   plugin | skin | tools | media | iptv | softcam | backup | picon | other
CAT_PATTERNS = [            # sıra önemli: yukarıdaki önce kazanır
    ("iptv",    r"iptv|m3u|stalker|xtream|xstreamity|e2iplayer|beengo|suptv|streamlink|vavoo|serienstream"),
    ("softcam", r"softcam|oscam|cccam|ncam|gcam|mgcamd|supcam|camnova|novacam|emu|keyupdater|softcams?"),
    ("backup",  r"backup|flashbackup|dflash|dbackup|backupsuite|imagemanager|multiboot|kexec"),
    ("picon",   r"picon|channels?[_\-\s]?backup|settings?[_\-\s]?(?:list|pack|backup)|lamedb|bouquet"),
    ("media",   r"media|player|youtube|plex|kodi|mediastream|audio|movie|subtitle|subssupport|radio"),
    ("tools",   r"epg|crossepg|xmltv|rytec|jediepg|utility|manager|cleaner|tool|filecommander|"
                r"satfinder|signal|cron|ftp|webif|openwebif|autotimer|autobouquet|settingsmaker|"
                r"satelliteeditor|weather|foreca|msn|panel|luxsat|satvenus|tspanel|ajpanel|linuxsat|"
                r"shutdown|update|install|script|cam|info|monitor|network|hdd|usb|log"),
]
SKIN_RE = r"enigma2-plugin-skins-|enigma2-skin-|[_\-]skin[_\-]|skincomponent|^skin[_\-]"
PICON_RE = (r"(?:^|[\W_])picons?(?:$|[\W_])|picon[\s_\-]?pack|picons?_?\d+|"
            r"channels?[_\-]?backup|lamedb|satellites\.xml|userbouquet")

# kategori -> plugin içindeki ikon dosyası (icons/ klasöründe mevcut olanlar)
CAT_ICON = {
    "iptv": "stream.png", "softcam": "softcam.png", "backup": "backup.png", "picon": "picon.png",
    "media": "mediaplayer.png", "tools": "tools.png", "skin": "skin.png",
    "plugin": "default.png", "other": "default.png",
}

# kategori -> 4 dilde kısa açıklama (kart ve liste için)
CAT_DESC = {
    "iptv":    ("IPTV / stream eklentisi", "IPTV / streaming plugin", "IPTV-/Streaming-Plugin", "Plugin IPTV / streaming"),
    "softcam": ("Softcam / emülatör", "Softcam / emulator", "Softcam / Emulator", "Softcam / émulateur"),
    "backup":  ("Yedekleme / image aracı", "Backup / image tool", "Backup-/Image-Werkzeug", "Outil de sauvegarde / image"),
    "picon":   ("Kanal listesi / picon", "Channel list / picons", "Senderliste / Picons", "Liste de chaînes / picons"),
    "media":   ("Medya eklentisi", "Media plugin", "Medien-Plugin", "Plugin multimédia"),
    "tools":   ("Sistem aracı", "System tool", "Systemwerkzeug", "Outil système"),
    "skin":    ("Arayüz skini", "Interface skin", "Oberflächen-Skin", "Skin d'interface"),
    "plugin":  ("Enigma2 eklentisi", "Enigma2 plugin", "Enigma2-Plugin", "Plugin Enigma2"),
    "other":   ("Diğer dosya", "Other file", "Sonstige Datei", "Autre fichier"),
}

# kütüphane / bağımlılık paketleri (eklenti değil)
LIB_RE = r"^(?:lib|python3?-|py-|gst|ffmpeg|openssl|curl|zlib|glib|tuxbox)"


# ============================================================ yardımcılar
def gh_tree(owner, repo, branch):
    url = "https://api.github.com/repos/%s/%s/git/trees/%s?recursive=1" % (owner, repo, branch)
    headers = {"User-Agent": "DreamosatXStore-Scanner"}
    if GITHUB_TOKEN:
        headers["Authorization"] = "token " + GITHUB_TOKEN
    try:
        req = urlreq.Request(url, headers=headers)
        data = json.loads(urlreq.urlopen(req, timeout=60).read().decode("utf-8"))
        if data.get("truncated"):
            print("[!] %s/%s: ağaç kırpıldı (repo çok büyük)" % (owner, repo))
        return data.get("tree", [])
    except Exception as e:
        print("[!] %s/%s: %s" % (owner, repo, e))
        return []


def split_name(fname):
    """'enigma2-plugin-skins-diana-fhd_3.3_all.ipk' -> (paket, sürüm, mimari)"""
    base = re.sub(r"\.(ipk|deb|zip|tar\.gz|tgz)$", "", fname, flags=re.I)
    parts = base.split("_")
    arch = ""
    if len(parts) >= 2 and parts[-1].lower() in ARCH_SUFFIX:
        arch = ARCH_SUFFIX[parts[-1].lower()]
        parts = parts[:-1]
    # sürüm = ilk rakamla başlayan alan; ondan öncekilerin tamamı paket adıdır
    vi = None
    for i, p in enumerate(parts[1:], 1):
        if re.search(r"\d", p):
            vi = i
            break
    if vi is None:
        return "_".join(parts), "", arch
    return "_".join(parts[:vi]), parts[vi].lstrip("vV"), arch


def detect_arch(fname, folder=""):
    _pkg, _ver, arch = split_name(fname)
    if arch:
        return arch
    t = (fname + " " + folder).lower()
    if "arm+mips" in t or "arm-mips" in t:
        return "all"
    for a, pat in ARCH_WORDS:
        if re.search(pat, t):
            return a
    return "all"


def detect_category(fname, folder=""):
    """Plugin'in tanıdığı kategori isimlerinden birini döndürür."""
    name = fname.lower()
    fold = folder.lower()
    full = name + " " + fold

    # 0) klasör adı en güçlü ipucu (kendi depomuz kategorilere göre ayrılmış)
    folder_map = {
        "plugin_iptv": "iptv", "plugin_epg": "tools", "plugin_weather": "tools",
        "plugin_utility": "tools", "plugin_settings": "picon", "plugin_backup": "backup",
        "plugin_softcam": "softcam", "plugin_media": "media", "plugin_ppanel": "plugin",
        "plugin_multiboot": "backup", "plugin_picon": "picon", "skin_all": "skin",
        "dependencies": "other", "channels": "picon", "picons": "picon",
    }
    for key, cat in folder_map.items():
        if key in fold:
            # klasör kategorisi, ama dosya adı açıkça skin diyorsa skin kazanır
            if re.search(SKIN_RE, name) and "picon" not in name:
                return "skin"
            return cat

    # 1) SKIN
    if re.search(SKIN_RE, name) and "picon" not in name:
        return "skin"

    # 2) PICON / kanal listesi (veri dosyaları)
    if re.search(PICON_RE, full) and "piconmanager" not in full and "piconcleaner" not in full:
        return "picon"

    # 3) kütüphaneler / bağımlılıklar
    if re.search(LIB_RE, name):
        return "other"

    # 4) anahtar kelimeler
    for cat, pat in CAT_PATTERNS:
        if re.search(pat, full):
            return cat

    # 5) enigma2 eklentisi ama tanınmadı
    if "enigma2-plugin" in name or "enigma2-systemplugins" in name:
        return "plugin"

    return "other"


def version_key(ver, pkg):
    m = re.search(r"(\d+(?:\.\d+)*)", ver or "") or re.search(r"[_-]v?(\d+(?:\.\d+)*)", pkg)
    if not m:
        return (0,)
    try:
        return tuple(int(p) for p in m.group(1).split("."))
    except Exception:
        return (0,)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]


def clean_name(pkg):
    clean = pkg
    for pre in ("enigma2-plugin-extensions-", "enigma2-plugin-skins-",
                "enigma2-plugin-systemplugins-", "enigma2-plugin-",
                "enigma2-skin-", "enigma2-"):
        if clean.startswith(pre):
            clean = clean[len(pre):]
            break
    clean = clean.replace("_", " ").replace("-", " ").strip()
    return " ".join(w[:1].upper() + w[1:] for w in clean.split())[:70]


# ============================================================ tarama
def scan():
    plugins = []
    seen = set()

    for owner, repo, branch in SOURCES:
        print("[+] %s/%s @ %s" % (owner, repo, branch))
        tree = gh_tree(owner, repo, branch)
        base = "https://raw.githubusercontent.com/%s/%s/%s/" % (owner, repo, branch)
        n_before = len(plugins)

        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not path.lower().endswith((".ipk", ".deb", ".zip", ".tar.gz", ".tgz")):
                continue

            fname = path.rsplit("/", 1)[-1]
            folder = path.rsplit("/", 1)[0] if "/" in path else ""
            ext = "deb" if fname.lower().endswith(".deb") else (
                "ipk" if fname.lower().endswith(".ipk") else "archive")

            pkg, ver, _a = split_name(fname)
            cat = detect_category(fname, folder)
            arch = detect_arch(fname, folder)
            desc = CAT_DESC.get(cat, CAT_DESC["other"])

            pid = slug(pkg + ("-" + ver if ver else ""))
            bp, n = pid, 1
            while pid in seen:
                n += 1
                pid = "%s-%d" % (bp, n)
            seen.add(pid)

            plugins.append({
                "id":        pid,
                "name":      clean_name(pkg),
                "category":  cat,
                "arch":      arch,
                "version":   ver,
                "url":       base + urlparse.quote(path),
                "package":   pkg,                 # saf opkg adı (sürüm/mimari yok)
                "file":      fname,
                "source":    ext,
                "icon":      CAT_ICON.get(cat, "default.png"),
                "github":    "%s/%s" % (owner, repo),
                "github_asset": fname,
                "size":      item.get("size", 0),
                "desc":      desc[0], "desc_en": desc[1], "desc_de": desc[2], "desc_fr": desc[3],
                "added":     time.strftime("%Y-%m-%d"),
                "_vkey":     version_key(ver, pkg),
            })
        print("    %d dosya" % (len(plugins) - n_before))

    # paket başına en yeni N sürüm
    groups = defaultdict(list)
    for p in plugins:
        groups[(p["package"], p["arch"])].append(p)

    final = []
    for group in groups.values():
        group.sort(key=lambda x: x["_vkey"], reverse=True)
        final.extend(group[:KEEP_VERSIONS])

    for p in final:
        del p["_vkey"]

    final.sort(key=lambda x: (x["category"], x["name"].lower()))
    return final


def save(plugins, path=OUTPUT_FILE):
    catalog = {
        "_info": "DreamosatX Store - auto generated by GitHub Actions",
        "version": 2,
        "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "stats_url": "",
        "plugins": plugins,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    print("=== DreamosatX Scanner v2 ===")
    items = scan()
    save(items)

    print("\n[✓] Toplam: %d paket" % len(items))
    print("\nKategoriler (plugin ile birebir aynı isimler):")
    for k, v in Counter(p["category"] for p in items).most_common():
        print("   %-10s %d" % (k, v))
    print("\nMimariler:")
    for k, v in Counter(p["arch"] for p in items).most_common():
        print("   %-10s %d" % (k, v))
    print("\nSürümü okunamayan: %d" % sum(1 for p in items if not p["version"]))
    print("[✓] %s yazıldı" % OUTPUT_FILE)
