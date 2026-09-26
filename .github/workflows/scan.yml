name: Scan Enigma2 Plugins

on:
  schedule:
    - cron: '0 4 * * *'
  workflow_dispatch:
  push:
    paths:
      - 'OE2.0/**'
      - 'OE2.5/**'
      - 'scripts/scan.py'

concurrency:
  group: scan-catalog
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run scanner
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          echo "=== Başlangıç: $(date -u) ==="
          cp -f catalog.json catalog.prev.json 2>/dev/null || true
          python scripts/scan.py

      - name: Validate catalog
        run: |
          python - <<'PY'
          import json, os, sys, collections
          d = json.load(open("catalog.json"))
          p = d.get("plugins", [])
          print("Toplam:", len(p))
          print("Kategoriler:", collections.Counter(x["category"] for x in p).most_common())

          # plugin'in tanıdığı kategoriler - başka isim çıkarsa hata
          allowed = {"plugin", "skin", "tools", "media", "iptv", "softcam", "backup", "picon", "other"}
          bad = sorted({x["category"] for x in p} - allowed)
          if bad:
              sys.exit("HATA: bilinmeyen kategori(ler): %s" % bad)

          # zorunlu alanlar
          need = ("id", "name", "category", "url", "package", "arch")
          for x in p[:]:
              missing = [k for k in need if not x.get(k)]
              if missing:
                  sys.exit("HATA: %s -> eksik alan %s" % (x.get("id"), missing))

          # id tekrarı olmamalı
          ids = collections.Counter(x["id"] for x in p)
          dup = [k for k, v in ids.items() if v > 1]
          if dup:
              sys.exit("HATA: tekrar eden id: %s" % dup[:5])

          # ani daralma = bozuk tarama (API limiti vb.) -> eski katalogu koru
          if os.path.exists("catalog.prev.json"):
              old = len(json.load(open("catalog.prev.json")).get("plugins", []))
              if old and len(p) < old * 0.5:
                  sys.exit("HATA: paket sayısı %d -> %d düştü, commit edilmiyor" % (old, len(p)))
          if len(p) < 50:
              sys.exit("HATA: katalog çok küçük (%d)" % len(p))
          print("✅ Katalog geçerli")
          PY

      - name: Commit catalog
        run: |
          rm -f catalog.prev.json
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add catalog.json
          if git diff --staged --quiet; then
            echo "ℹ️  Değişiklik yok, commit atlanıyor"
            exit 0
          fi
          git commit -m "Update catalog $(date -u +%Y-%m-%d)"
          for i in 1 2 3; do
            if git push; then
              echo "✅ Push başarılı"
              exit 0
            fi
            echo "⚠️  Push denemesi $i başarısız, pull+rebase deniyor..."
            git pull --rebase origin main || true
            sleep 5
          done
          echo "❌ Push 3 denemede başarısız"
          exit 1
