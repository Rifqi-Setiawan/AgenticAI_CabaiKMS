"""Keluarkan data cabai yang tidak sampai level varietas/kultivar (keputusan peneliti 4-5 Nov 2026).

Tidak menghapus permanen: berkas dipindah ke <akar>/_dikeluarkan_bukan_varietas/<path asli>.
Workbook yang hanya sebagian barisnya gagal disalin utuh ke arsip (salinan arsip yang sudah ada tidak
ditimpa, jadi arsip selalu berisi versi paling asli), lalu baris/kolom yang gagal dihapus.
Gold dan manifest tidak diubah. Rincian: data_evaluasi/KLASIFIKASI_LEVEL_VARIETAS.md.

Jalankan dari akar repo:
  python data_evaluasi/skrip/keluarkan_non_varietas.py --tahap1 [--jalankan]   # spesies / jenis umum / tanpa varietas (4 Nov)
  python data_evaluasi/skrip/keluarkan_non_varietas.py --tahap2 [--jalankan]   # nama tipe buah / cultivar group (5 Nov)
Tanpa --jalankan hanya menampilkan rencana (dry run).
"""
import csv, os, shutil, sys
import openpyxl

JALANKAN = "--jalankan" in sys.argv
TAHAP1 = "--tahap1" in sys.argv
TAHAP2 = "--tahap2" in sys.argv
AKAR = ["data_evaluasi", "dataset_eksperimen", "data_input_dummy"]
ARSIP = "_dikeluarkan_bukan_varietas"
DAFTAR = f"data_evaluasi/{ARSIP}/DAFTAR_DIKELUARKAN.csv"
log = []


def arsip_path(p):
    top, rest = p.split("/", 1)
    return f"{top}/{ARSIP}/{rest}"


def pindah(p, alasan):
    dst = arsip_path(p)
    log.append(("pindah", p, dst, alasan))
    if JALANKAN:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(p, dst)


def semua_file(nama):
    hasil = []
    for top in AKAR:
        for root, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d != ARSIP]
            if nama in files:
                hasil.append(os.path.join(root, nama).replace("\\", "/"))
    return hasil


def simpan_dengan_arsip(f, wb):
    dst = arsip_path(f)
    if JALANKAN:
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(f, dst)
        wb.save(f)
    return dst


def hapus_baris(nama, sheet_kolom, nilai_gagal, alasan):
    for f in semua_file(nama):
        wb = openpyxl.load_workbook(f)
        rinci = []
        for sheet, kol in sheet_kolom:
            ws = wb[sheet]
            idx = [c.row for c in ws[kol] if isinstance(c.value, str) and c.value.strip() in nilai_gagal]
            nilai = sorted({ws[f"{kol}{i}"].value for i in idx})
            rinci.append(f"{sheet}: {len(idx)} baris {nilai}")
            for i in sorted(idx, reverse=True):
                ws.delete_rows(i)
        log.append(("hapus baris", f, simpan_dengan_arsip(f, wb), alasan + " | " + "; ".join(rinci)))


def hapus_kolom(nama, sheet, baris_header, nilai_gagal, alasan):
    for f in semua_file(nama):
        wb = openpyxl.load_workbook(f)
        ws = wb[sheet]
        idx = [c.column for c in ws[baris_header] if isinstance(c.value, str) and c.value.strip() in nilai_gagal]
        for i in sorted(idx, reverse=True):
            ws.delete_cols(i)
        log.append(("hapus kolom", f, simpan_dengan_arsip(f, wb), alasan + f" | {sheet}: kolom {idx}"))


if TAHAP1:
    # Foto Commons: UNCERTAIN, Cabai Rawit (bird's eye), Cabai Korea generik (bukan Cheongyang)
    m = list(csv.DictReader(open("data_evaluasi/gambar/manifest/gold_gambar_manifest_final.csv", encoding="utf-8-sig")))
    for r in m:
        alasan = None
        if r["label_kind"] == "UNCERTAIN":
            alasan = "Commons UNCERTAIN: varietas tidak dapat ditentukan"
        elif r["true_variety"] == "Cabai Rawit":
            alasan = "Commons 'Cabai Rawit' (Bird's eye chili): nama jenis umum, bukan varietas"
        elif r["true_variety"] == "Cabai Korea" and "Cheongyang" not in r["source_category"]:
            alasan = "Commons 'Cabai Korea' generik: nama asal negara, bukan varietas"
        if alasan:
            fs = semua_file(r["filename"])
            if not fs:
                log.append(("TIDAK DITEMUKAN", r["filename"], "", alasan))
            for f in fs:
                pindah(f, alasan)
    for nama in ["C. annuum - bentuk buah_ warna bh_ posisi buah menggantung.jpg",
                 "warna tangkai daun C. chinense dan C. annuum permukaan bawah.jpg"]:
        for f in semua_file(nama):
            pindah(f, "Foto Indonesia hanya berlabel spesies (C. annuum / C. chinense)")
    if os.path.isdir("data_evaluasi/gambar_id/kandidat_inat"):
        pindah("data_evaluasi/gambar_id/kandidat_inat", "iNaturalist: 148 foto hanya level spesies (annuum/frutescens)")
    for f in semua_file("data_input.xlsx"):
        pindah(f, "R01: kolom Jenis Cabai hanya level spesies, tidak ada nama varietas")
    hapus_baris("D03_row_multilevel_indonesia.xlsx", [("Data_Bertingkat", "A")], {"Cabai rawit NTB"},
                "S03: 'Cabai rawit NTB' = jenis + asal daerah, bukan varietas")
    for nama in ["spreadsheet_varietas_terdaftar.xlsx", "spreadsheet_varietas_terdaftar_17.xlsx"]:
        hapus_baris(nama, [("Data Varietas", "A")], {"Cabai Rawit", "Cabai Korea"},
                    "Daftar varietas foto: 'Cabai Rawit' dan 'Cabai Korea' bukan varietas")
    for nama in ["G01_grin_8_varietas_terdaftar.xlsx", "G02_grin_11_varietas.xlsx"]:
        hapus_baris(nama, [("GRIN Capsicum", "A"), ("sumber", "A")], {"Cabai Rawit", "Cabai Korea"},
                    "GRIN: baris tipe 'Cabai Rawit' dan 'Cabai Korea' bukan varietas")

if TAHAP2:
    # Foto Commons berstatus TIPE di klasifikasi_varietas_foto_commons_abu_abu.csv
    k = list(csv.DictReader(open("data_evaluasi/klasifikasi_varietas_foto_commons_abu_abu.csv", encoding="utf-8-sig")))
    for r in k:
        if r["status_usulan"] == "TIPE":
            alasan = f"[tahap 2] Commons '{r['label_saat_ini']}': hanya tipe buah ({r['usulan_nama_level_varietas']})"
            fs = semua_file(r["filename"])
            if not fs:
                log.append(("TIDAK DITEMUKAN", r["filename"], "", alasan))
            for f in fs:
                pindah(f, alasan)
    TIPE_FOTO = {"Jalapeno", "Habanero", "Cayenne", "Paprika", "Serrano", "Scotch Bonnet", "Banana Pepper"}
    for nama in ["spreadsheet_varietas_terdaftar.xlsx", "spreadsheet_varietas_terdaftar_17.xlsx"]:
        hapus_baris(nama, [("Data Varietas", "A")], TIPE_FOTO,
                    "[tahap 2] Daftar varietas foto: nama tipe buah, bukan kultivar")
    for nama in ["G01_grin_8_varietas_terdaftar.xlsx", "G02_grin_11_varietas.xlsx"]:
        hapus_baris(nama, [("GRIN Capsicum", "A"), ("sumber", "A")], TIPE_FOTO,
                    "[tahap 2] GRIN: baris tipe buah, bukan kultivar")
    TIPE_ZENODO = {"Arari bode amarela", "Biquinho amarela", "Biquinho vermelha", "Cayenne", "Cheiro do Norte",
                   "Cumari do Pará", "Habanero amarela", "Habanero chocolate", "Habanero vermelha", "Malagueta",
                   "Murupi", "Peito de moça", "Piãozinho"}
    for nama in ["E08_zenodo_capsicum_en.xlsx", "E08_zenodo_capsicum_en_variety.xlsx"]:
        hapus_baris(nama, [("Observed85_readable", "A")], TIPE_ZENODO,
                    "[tahap 2] N08 Zenodo: genotipe bernama tipe/landrace, bukan kultivar")
    hapus_kolom("D01_transposed_indonesia_mixed.xlsx", "Data_Transposed", 1, {"Cabai tanjung"},
                "[tahap 2] S01: 'Cabai tanjung' = tipe; varietas resmi Tanjung-1/Tanjung-2 tidak dapat dipastikan")
    hapus_baris("D03_row_multilevel_indonesia.xlsx", [("Data_Bertingkat", "A")], {"Cabai tanjung"},
                "[tahap 2] S03: 'Cabai tanjung' = tipe; varietas resmi Tanjung-1/Tanjung-2 tidak dapat dipastikan")

if not (TAHAP1 or TAHAP2):
    sys.exit("Pilih --tahap1 atau --tahap2")
for a in log:
    print(" | ".join(a))
print("total aksi:", len(log), "(DRY RUN)" if not JALANKAN else "(DIJALANKAN)")
if JALANKAN:
    baru = not os.path.exists(DAFTAR)
    os.makedirs(os.path.dirname(DAFTAR), exist_ok=True)
    with open(DAFTAR, "a", newline="", encoding="utf-8-sig" if baru else "utf-8") as fh:
        w = csv.writer(fh)
        if baru:
            w.writerow(["aksi", "path_asli", "path_arsip", "alasan"])
        w.writerows(log)
