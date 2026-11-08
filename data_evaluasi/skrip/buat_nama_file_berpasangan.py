"""Desain nama file berpasangan (D23, 7 Nov 2026): foto yang SAMA diuji dengan beberapa nama berkas.

Varian nama berkas:
  NETRAL           IMG_xxxx (tanpa petunjuk varietas)
  BENAR            nama varietas foto yang benar (terdaftar atau tidak)
  SALAH_TERDAFTAR  nama varietas TERDAFTAR yang lain, dipilih yang paling mirip (keluarga nama sama, lalu jenis cabai
                   sama, lalu spesies sama; seri seed tetap) supaya sinyal nama file benar-benar menjebak
Aturan jawaban benar (tindakan fusi):
                    foto KNOWN                                   foto OTHER
  NETRAL            AUTO_LINK (varietas benar) atau REVIEW_*     CANDIDATE
  BENAR             AUTO_LINK                                    CANDIDATE
  SALAH_TERDAFTAR   REVIEW_MISMATCH                              REVIEW_MISMATCH
Foto PVT yang bagiannya tidak punya baris Gambar (HABITUS, BIJI, TIDAK_JELAS; D21) benar bila REVIEW_* pada semua varian
(SALAH_TERDAFTAR tetap REVIEW_MISMATCH); CANDIDATE/AUTO_LINK ikut diterima hanya bila bagian_boleh punya baris.

Set:
  pvt40   40 foto uji PVT versi kartu tertutup x 3 varian; registri = 24 varietas P01 (gold_kanonik_foto_pvt.csv).
  ind6    6 foto Indonesia x varian NETRAL (varian BENAR = nama berkas asli yang sudah dijalankan); registri = varietas
          spreadsheet S01/S02/S03 (gold_kombinasi_peneliti.csv), jadi status per spreadsheet.

Jalankan dari akar repo:  python data_evaluasi/skrip/buat_nama_file_berpasangan.py
Keluaran: dataset_eksperimen/2_input_foto/nama_file_berpasangan/<set>_<varian>/ (salinan foto dengan nama baru +
daftar_foto.csv) dan data_evaluasi/gold/nama_file_berpasangan/gold_nama_file_berpasangan.csv.
"""
import csv
import random
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "dataset_eksperimen" / "2_input_foto"
OUT_FOTO = DS / "nama_file_berpasangan"
OUT_GOLD = ROOT / "data_evaluasi" / "gold" / "nama_file_berpasangan" / "gold_nama_file_berpasangan.csv"
SEED = 20261107
REVIEW = {"REVIEW_UNCERTAIN", "REVIEW_MISMATCH"}


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def slug(nama):
    return re.sub(r"[^a-z0-9]+", "_", nama.lower()).strip("_")


def keluarga(nama):
    return slug(nama).split("_")[0]


def pilih_salah(benar, info, terdaftar, rnd):
    """Varietas terdaftar lain yang paling mirip dengan `benar`."""
    nu, sp = info[benar]
    kand = [v for v in terdaftar if v != benar]

    def skor(v):
        return (keluarga(v) == keluarga(benar), info[v][0].lower() == nu.lower(), info[v][1].lower() == sp.lower())

    best = max(skor(v) for v in kand)
    pilihan = sorted(v for v in kand if skor(v) == best)
    return rnd.choice(pilihan), best


def aksi_boleh(kind, varian, punya_baris, boleh_berbaris):
    if varian == "SALAH_TERDAFTAR":
        return {"REVIEW_MISMATCH"}
    if not punya_baris:  # D21: bagian tanpa baris Gambar
        return REVIEW | ({"AUTO_LINK"} if kind == "KNOWN" and boleh_berbaris else set()) | (
            {"CANDIDATE"} if kind == "OTHER" and boleh_berbaris else set())
    if kind == "KNOWN":
        return {"AUTO_LINK"} | (REVIEW if varian == "NETRAL" else set())
    return {"CANDIDATE"}


def main():
    rnd = random.Random(SEED)
    rows = []
    # ---------------------------------------------------------------- PVT 40 (kartu tertutup) x 3 varian
    g317 = {r["berkas"].split("/")[-1]: r for r in read(ROOT / "data_evaluasi/gambar/manifest/gold_foto_pvt_317.csv")}
    kan = {r["berkas"].split("/")[-1]: r for r in read(ROOT / "data_evaluasi/gambar/manifest/gold_kanonik_foto_pvt.csv")}
    info = {r["true_variety"]: (r["nama_umum"], r["spesies"]) for r in g317.values()}
    terdaftar = sorted({r["true_variety"] for r in g317.values() if r["label_kind_skenario_P01"] == "KNOWN"})
    nomor = list(range(10, 100))
    rnd.shuffle(nomor)
    for i, p in enumerate(read(DS / "pvt_uji_40/pembagian_uji_40.csv")):
        src_name = p["berkas_sumber"].split("/")[-1]
        g, k = g317[src_name], kan[src_name]
        kind, var = g["label_kind_skenario_P01"], g["true_variety"]
        salah, mirip = pilih_salah(var, info, terdaftar, rnd)
        stem = p["filename"].rsplit(".", 1)[0]
        nn = nomor[i]
        punya_baris = k["bagian_utama"] in ("DAUN", "BATANG", "BUAH", "BUNGA")
        boleh_berbaris = bool(k["canonical_rows_boleh"])
        for varian, nama, hint in (("NETRAL", f"{stem}.webp", ""), ("BENAR", f"{slug(var)}_{nn}.webp", var),
                                   ("SALAH_TERDAFTAR", f"{slug(salah)}_{nn}.webp", salah)):
            rows.append({"set": "pvt40", "varian": varian, "folder": f"pvt40_{varian.lower()}", "filename": nama,
                         "foto_asal": f"pvt_uji_40/kartu_tertutup/{stem}.webp", "berkas_sumber_pvt": src_name,
                         "spreadsheet": "P01", "label_kind": kind, "true_variety": var, "hint_nama_file": hint,
                         "hint_terdaftar": "Y" if hint in terdaftar else ("N" if hint else ""),
                         "kemiripan_salah": "|".join(n for n, b in zip(("keluarga", "jenis", "spesies"), mirip) if b) if varian == "SALAH_TERDAFTAR" else "",
                         "bagian_utama": k["bagian_utama"], "bagian_boleh": k["bagian_boleh"],
                         "expected_fusion_boleh": "|".join(sorted(aksi_boleh(kind, varian, punya_baris, boleh_berbaris))),
                         "dinilai": k["dinilai_kanonik"], "sumber_bagian": k["annotation_source_part"]})
    # ---------------------------------------------------------------- Indonesia 6 x NETRAL (per spreadsheet)
    gi = read(ROOT / "data_evaluasi/gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv")
    foto = sorted({r["filename"] for r in gi})
    netral = {fn: f"IMG_{5101 + j}{Path(fn).suffix if Path(fn).suffix else '.jpg'}" for j, fn in enumerate(foto)}
    for r in gi:
        kind = r["expected_status"]
        rows.append({"set": "ind6", "varian": "NETRAL", "folder": "ind6_netral", "filename": netral[r["filename"]],
                     "foto_asal": f"foto_indonesia_drive1/{r['filename']}", "berkas_sumber_pvt": "",
                     "spreadsheet": r["spreadsheet"], "label_kind": kind,
                     "true_variety": r.get("expected_variety") or r["varietas_atau_jenis"], "hint_nama_file": "",
                     "hint_terdaftar": "", "kemiripan_salah": "", "bagian_utama": r["bagian"],
                     "bagian_boleh": r.get("bagian_boleh") or r["bagian"],
                     "expected_fusion_boleh": "|".join(sorted(aksi_boleh(kind, "NETRAL", True, True))),
                     "dinilai": r["dinilai"], "sumber_bagian": "peneliti"})

    # salin foto dengan nama baru
    if OUT_FOTO.exists():
        shutil.rmtree(OUT_FOTO)
    per_folder = {}
    for r in rows:
        d = OUT_FOTO / r["folder"]
        d.mkdir(parents=True, exist_ok=True)
        tujuan = d / r["filename"]
        if not tujuan.exists():
            shutil.copy2(DS / r["foto_asal"], tujuan)
        per_folder.setdefault(r["folder"], {})[r["filename"]] = r["foto_asal"]
    for folder, m in per_folder.items():
        with open(OUT_FOTO / folder / "daftar_foto.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["filename", "foto_asal"])
            w.writerows(sorted(m.items()))
    OUT_GOLD.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_GOLD, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(len(rows), "baris gold;", {f: len(m) for f, m in per_folder.items()})
    print(Counter((r["set"], r["label_kind"], r["varian"], r["expected_fusion_boleh"]) for r in rows))
    print("kemiripan SALAH:", Counter(r["kemiripan_salah"] for r in rows if r["varian"] == "SALAH_TERDAFTAR"))


if __name__ == "__main__":
    main()
