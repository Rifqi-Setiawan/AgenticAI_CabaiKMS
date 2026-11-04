"""Cari aksesi Capsicum di USDA GRIN-Global (npgsweb) per nama tipe varietas, lalu ambil observasi setiap aksesi.

Dipakai untuk menyusun workbook data asli pasangan 160 foto Commons (4 Nov 2026).
Hanya pustaka standar. Mengirim formulir pencarian sederhana GRIN (ASP.NET) seperti peramban biasa, dengan jeda antar-permintaan.
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\grin_cari_aksesi.py
Keluaran: sumber_luar_negeri/grin/hasil_cari.json, sumber_luar_negeri/grin/aksesi/<id>.html, sumber_luar_negeri/grin/observasi.json
"""
import html
import http.cookiejar
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://npgsweb.ars-grin.gov/gringlobal/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) penelitian-cabai-kms (Telkom University)"
OUT = Path("sumber_luar_negeri/grin")
JEDA = 2.0
ISTILAH = ["jalapeno", "habanero", "cayenne", "paprika", "serrano", "hungarian", "wax", "rawit", "korea", "korean",
           "jolokia", "bhut", "scotch bonnet", "trinidad", "black pearl", "banana", "padron", "poblano", "shishito"]


def opener():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", UA)]
    return op


def hidden_fields(page):
    return {m.group(1): html.unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page)}


def cari(op, istilah):
    page = op.open(BASE + "search", timeout=60).read().decode("utf-8", "ignore")
    data = hidden_fields(page)
    data.update({"__EVENTTARGET": "ctl00$MainContent$btnSimple", "__EVENTARGUMENT": "",
                 "ctl00$MainContent$txtSearch": istilah, "ctl00$MainContent$ddlimit": "100"})
    req = urllib.request.Request(BASE + "search", data=urllib.parse.urlencode(data).encode(),
                                 headers={"Referer": BASE + "search"})
    res = op.open(req, timeout=90).read().decode("utf-8", "ignore")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", res, re.S):
        m = re.search(r'accessiondetail(?:\.aspx)?\?id=(\d+)', tr)
        if m:
            teks = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", tr))).strip()
            rows.append({"id": m.group(1), "teks": teks})
    return rows


def observasi(page):
    i = page.find('id="observation"')
    if i < 0:
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page[i:i + 200000], re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) >= 5 and cells[0] != "Category":
            desc = cells[1].split('">')[-1]  # buang sisa atribut title yang ikut terbaca
            out.append({"kategori": cells[0], "deskriptor": desc, "deskripsi": cells[2], "nilai": cells[3], "n_sampel": cells[4],
                        "studi": cells[5].split('">')[-1] if len(cells) > 5 else ""})
    return out


def judul(page):
    m = re.search(r"Details for:\s*([^<]+)", page)
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""


def main():
    (OUT / "aksesi").mkdir(parents=True, exist_ok=True)
    op = opener()
    cache = OUT / "hasil_cari.json"
    if cache.exists():
        hasil = json.loads(cache.read_text(encoding="utf-8"))
    else:
        hasil = {}
        for t in ISTILAH:
            hasil[t] = cari(op, t)
            print(t, len(hasil[t]), [r["teks"][:50] for r in hasil[t][:2]], flush=True)
            time.sleep(JEDA)
        cache.write_text(json.dumps(hasil, indent=1, ensure_ascii=False), encoding="utf-8")
    # hanya aksesi Capsicum yang teks barisnya memuat kata kunci (pencarian sederhana GRIN juga mencocokkan genus lain)
    relevan = {t: [r for r in v if "Capsicum" in r["teks"] and t.lower() in r["teks"].lower()] for t, v in hasil.items()}
    (OUT / "hasil_cari_capsicum.json").write_text(json.dumps(relevan, indent=1, ensure_ascii=False), encoding="utf-8")
    for t, v in relevan.items():
        print(f"{t}: {len(v)} aksesi Capsicum", flush=True)
    ids = sorted({r["id"] for v in relevan.values() for r in v}, key=int)
    obs = {}
    for i in ids:
        p = OUT / "aksesi" / f"{i}.html"
        if not p.exists():
            p.write_bytes(op.open(BASE + f"accessiondetail?id={i}", timeout=90).read())
            time.sleep(JEDA)
        page = p.read_text(encoding="utf-8", errors="ignore")
        obs[i] = {"judul": judul(page), "url": BASE + f"accessiondetail?id={i}", "observasi": observasi(page)}
    (OUT / "observasi.json").write_text(json.dumps(obs, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(ids), "aksesi;", sum(1 for v in obs.values() if v["observasi"]), "punya observasi")


if __name__ == "__main__":
    main()
