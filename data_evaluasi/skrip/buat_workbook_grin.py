"""Susun workbook data asli (USDA GRIN-Global) sebagai pasangan spreadsheet untuk 160 foto Commons (4 Nov 2026).

Satu aksesi bank genetik per tipe varietas foto. Aturan pemilihan (deterministik): aksesi Capsicum di GRIN yang namanya
memuat nama tipe, dengan jumlah observasi morfologi terbanyak (seri: nomor PI terkecil). Pengecualian yang dicatat:
  - Cabai Korea: tidak ada aksesi bernama "Korea"; dipilih aksesi asal Korea Selatan yang namanya memuat "go chu"
    (gochu = cabai Korea) dengan observasi morfologi terbanyak (PI 433360 'Saego Chu').
  - Cabai Rawit: satu-satunya aksesi bernama rawit adalah PI 640908 'Rawit Kutoarjo' (Indonesia); tidak punya observasi
    karakter, sehingga barisnya hanya berisi identitas aksesi.
Kategori observasi yang diambil: MORPHOLOGY, GROWTH, PHENOLOGY, PRODUCTION, CHEMICAL (hasil uji penyakit/nematoda dan
penanda subset koleksi tidak diambil karena bukan karakter tanaman). Nama deskriptor dan nilai disalin persis dari GRIN;
deskriptor yang diamati di lebih dari satu studi digabung dengan "; " sesuai urutan di halaman sumber.

Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\buat_workbook_grin.py
Keluaran: inputs/G01_grin_8_varietas_terdaftar.xlsx, inputs/G02_grin_11_varietas.xlsx
"""
import json
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

G = Path("sumber_luar_negeri/grin")
KATEGORI = ["MORPHOLOGY", "GROWTH", "PHENOLOGY", "PRODUCTION", "CHEMICAL"]
TANGGAL = "4 November 2026"
# tipe foto -> (id GRIN, alasan pemilihan)
PILIH = {
    "Cabai Rawit": ("1572498", "satu-satunya aksesi bernama rawit (Rawit Kutoarjo, Indonesia); tanpa observasi karakter"),
    "Jalapeno": ("1201668", "nama memuat jalapeno, observasi morfologi terbanyak di antara aksesi C. annuum bernama jalapeno"),
    "Habanero": ("1333558", "nama memuat habanero, observasi morfologi terbanyak"),
    "Cayenne": ("1218576", "nama tepat 'Cayenne', observasi morfologi terbanyak di antara aksesi bernama cayenne"),
    "Paprika": ("1164568", "nama memuat paprika, observasi morfologi terbanyak di antara aksesi bernama paprika"),
    "Cabai Korea": ("1328296", "asal Korea Selatan, nama memuat 'go chu' (gochu), observasi morfologi terbanyak"),
    "Serrano": ("1209240", "nama memuat serrano, observasi morfologi terbanyak"),
    "Hungarian Wax": ("1572830", "satu-satunya aksesi bernama Hungarian ... Wax; hanya 3 observasi buah"),
    "Scotch Bonnet": ("1380529", "nama tepat 'Scotch Bonnet', observasi morfologi terbanyak di antara yang bernama tepat"),
    "Banana Pepper": ("1077911", "nama memuat banana (SWEET BANANA), observasi morfologi terbanyak"),
    "Poblano": ("1201670", "nama memuat poblano (Tipo Poblano), observasi morfologi terbanyak di antara yang bernama poblano"),
}
DELAPAN = ["Cabai Rawit", "Jalapeno", "Habanero", "Cayenne", "Paprika", "Cabai Korea", "Serrano", "Hungarian Wax"]
SEBELAS = DELAPAN + ["Scotch Bonnet", "Banana Pepper", "Poblano"]


def muat():
    obs = json.loads((G / "observasi.json").read_text(encoding="utf-8"))
    obs.update(json.loads((G / "observasi_negara.json").read_text(encoding="utf-8")))
    cari = json.loads((G / "hasil_cari.json").read_text(encoding="utf-8"))
    teks = {r["id"]: r["teks"] for v in cari.values() for r in v}
    return obs, teks


def identitas(gid, obs, teks):
    import html as _h
    page = (G / "aksesi" / f"{gid}.html").read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"Details for:(.*?)</h1>", page, re.S)
    judul = re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip() if m else ""
    # bentuk: "PI 268103, Capsicum annuum L., Tipo Jalapeno" (nama aksesi bisa kosong atau memuat koma)
    parts = [p.strip() for p in judul.split(",")]
    pi = parts[0] if parts else obs[gid]["judul"]
    spesies = parts[1] if len(parts) > 1 else ""
    nama = ", ".join(parts[2:]).strip()
    return pi, spesies, nama


def baris(tipe, obs, teks):
    gid, alasan = PILIH[tipe]
    pi, spesies, nama = identitas(gid, obs, teks)
    nilai, urut = {}, []
    for o in obs[gid]["observasi"]:
        if o["kategori"] not in KATEGORI:
            continue
        d = o["deskriptor"]
        if d not in nilai:
            nilai[d] = []
            urut.append((KATEGORI.index(o["kategori"]), d))
        if o["nilai"] not in nilai[d]:
            nilai[d].append(o["nilai"])
    return {"tipe": tipe, "gid": gid, "pi": pi, "spesies": spesies, "nama": nama, "alasan": alasan,
            "nilai": {d: "; ".join(v) for d, v in nilai.items()}, "urut": urut, "n_obs": len(obs[gid]["observasi"])}


def tulis(path, tipe_list, obs, teks):
    rows = [baris(t, obs, teks) for t in tipe_list]
    kolom = []
    for _, d in sorted({u for r in rows for u in r["urut"]}, key=lambda x: (x[0], x[1])):
        if d not in kolom:
            kolom.append(d)
    wb = Workbook()
    ws = wb.active
    ws.title = "GRIN Capsicum"
    ws.append(["Variety", "Accession", "Accession name", "Species"] + kolom)
    for r in rows:
        ws.append([r["tipe"], r["pi"], r["nama"], r["spesies"]] + [r["nilai"].get(d) for d in kolom])
    for c in ws[1]:
        c.font = Font(bold=True)
    s = wb.create_sheet("sumber")
    s.append(["Variety", "Accession", "Accession name", "Species", "GRIN id", "URL", "Observasi di GRIN (semua kategori)",
              "Deskriptor diambil", "Alasan pemilihan", "Diakses"])
    for r in rows:
        s.append([r["tipe"], r["pi"], r["nama"], r["spesies"], r["gid"], f"https://npgsweb.ars-grin.gov/gringlobal/accessiondetail?id={r['gid']}",
                  r["n_obs"], len(r["nilai"]), r["alasan"], TANGGAL])
    s.append([])
    s.append(["Sumber: USDA ARS National Plant Germplasm System, GRIN-Global (https://npgsweb.ars-grin.gov). Data pemerintah AS."])
    s.append(["Kategori diambil: " + ", ".join(KATEGORI) + ". Nama deskriptor dan nilai disalin persis; nilai ganda dari beberapa studi digabung '; '."])
    s.append(["Kolom Variety berisi nama tipe yang dipakai label foto Commons; nama aksesi asli di kolom 'Accession name'."])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(path, len(rows), "varietas,", len(kolom), "deskriptor;", {r["tipe"]: len(r["nilai"]) for r in rows})


def main():
    obs, teks = muat()
    tulis(Path("inputs/G01_grin_8_varietas_terdaftar.xlsx"), DELAPAN, obs, teks)
    tulis(Path("inputs/G02_grin_11_varietas.xlsx"), SEBELAS, obs, teks)


if __name__ == "__main__":
    main()
