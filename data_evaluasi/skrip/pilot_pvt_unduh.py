"""Pilot dataset foto berlabel: unduh Berita Resmi PVT (Kementan) untuk komoditas cabai.

Langkah 1 dari pilot poin 8 (masukan dosen). Hanya pustaka standar.
- Mengambil daftar Berita Resmi dari portal PPVTPP lewat pencarian publik yang sama dengan halaman
  https://ppvtpp.setjen.pertanian.go.id/publikasi/berita-resmi-pvt (kata kunci "cabai").
- Mengunduh setiap PDF dengan jeda 1,5 detik, mencatat SHA-256.

Harus dijalankan dari jaringan yang tidak diblokir Cloudflare portal (laptop peneliti; IP VPS ditolak).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\pilot_pvt_unduh.py
Keluaran: pilot_foto_pvt/daftar_berita_resmi_cabai.tsv dan pilot_foto_pvt/pdf/*.pdf
"""
import csv
import hashlib
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://ppvtpp.setjen.pertanian.go.id/publikasi/berita-resmi-pvt"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) penelitian-cabai-kms (Telkom University)"
OUT = Path("pilot_foto_pvt")
PDF = OUT / "pdf"
JEDA = 1.5


def opener():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA)]
    return op


def daftar(op, kata="cabai"):
    html = op.open(BASE, timeout=60).read().decode("utf-8", "ignore")
    tok = re.search(r'params\._token = "([^"]+)"', html).group(1)
    rows, page = [], 1
    while True:
        data = urllib.parse.urlencode({
            "keywords": kata, "inputTanggalAwal": "", "inputTanggalAkhir": "", "category_id": "", "sumber": "",
            "sort": "desc", "sortBy": "post_date", "currentPage": page, "dataPerPage": 25, "_token": tok}).encode()
        req = urllib.request.Request(BASE + "/list/action/pagination", data=data,
                                     headers={"X-Requested-With": "XMLHttpRequest", "Referer": BASE})
        res = json.loads(op.open(req, timeout=60).read())["result"]
        items = res.get("data") or [] if isinstance(res, dict) else []
        for x in items:
            rows.append({"kategori": (x.get("category") or {}).get("category_name", ""),
                         "tanggal": (x.get("post_date") or x.get("created_at") or "")[:10],
                         "judul": " ".join(x.get("title", "").split()),
                         "url": (x.get("singleFile") or {}).get("mediaUrl", "")})
        if len(items) < 25:
            return rows
        page += 1
        time.sleep(JEDA)


def nama_berkas(judul):
    s = re.sub(r"^(Berita Resmi|BR)\s*", "", judul, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:90]


def main():
    PDF.mkdir(parents=True, exist_ok=True)
    op = opener()
    rows = daftar(op)
    print(f"{len(rows)} Berita Resmi ditemukan")
    for r in rows:
        r["berkas"] = nama_berkas(r["judul"]) + ".pdf"
        p = PDF / r["berkas"]
        if not p.exists() and r["url"]:
            body = op.open(r["url"], timeout=120).read()
            if not body.startswith(b"%PDF"):
                print("bukan PDF:", r["judul"])
                r["sha256"] = ""
                continue
            p.write_bytes(body)
            time.sleep(JEDA)
        r["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""
    with open(OUT / "daftar_berita_resmi_cabai.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kategori", "tanggal", "judul", "berkas", "sha256", "url"], delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    print("selesai:", sum(1 for r in rows if r["sha256"]), "PDF")


if __name__ == "__main__":
    main()
