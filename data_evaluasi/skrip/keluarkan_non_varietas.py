"""Keluarkan data cabai yang tidak sampai level varietas/kultivar (keputusan peneliti 4-5 Nov 2026).

Tidak menghapus permanen: berkas dipindah ke <akar>/_dikeluarkan_bukan_varietas/<path asli>.
Workbook yang hanya sebagian barisnya gagal disalin utuh ke arsip (salinan arsip yang sudah ada tidak
ditimpa, jadi arsip selalu berisi versi paling asli), lalu baris/kolom yang gagal dihapus.
Gold dan manifest tidak diubah. Rincian: data_evaluasi/KLASIFIKASI_LEVEL_VARIETAS.md.

Jalankan dari akar repo:
  python data_evaluasi/skrip/keluarkan_non_varietas.py --tahap1 [--jalankan]   # spesies / jenis umum / tanpa varietas (4 Nov)
  python data_evaluasi/skrip/keluarkan_non_varietas.py --tahap2 [--jalankan]   # nama tipe buah / cultivar group (5 Nov)
  python data_evaluasi/skrip/keluarkan_non_varietas.py --tahap3 [--jalankan]   # jejak di gold dan berkas daftar (5 Nov)
  python data_evaluasi/skrip/keluarkan_non_varietas.py --tahap4 [--jalankan]   # Gendot, Domba, Bhut Jolokia, Poblano GRIN (5 Nov)
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

TAHAP3 = "--tahap3" in sys.argv


def saring_csv(p, kolom, buang, alasan):
    """Hapus baris CSV yang nilai `kolom`-nya memenuhi buang(row); BOM dan akhir baris dipertahankan."""
    if not os.path.exists(p):
        return
    raw = open(p, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    eol = "\r\n" if b"\r\n" in raw else "\n"
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    sisa = [r for r in rows if not buang(r)]
    n = len(rows) - len(sisa)
    if n == 0:
        return
    dst = arsip_path(p)
    log.append(("saring baris", p, dst, f"{alasan} | {n} baris dibuang, {len(sisa)} tersisa"))
    if JALANKAN:
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(p, dst)
        with open(p, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator=eol)
            w.writeheader()
            w.writerows(sisa)


def saring_xlsx(p, sheet, kolom, buang_nilai, alasan):
    if not os.path.exists(p):
        return
    wb = openpyxl.load_workbook(p)
    ws = wb[sheet]
    idx = [c.row for c in ws[kolom][1:] if c.value is not None and buang_nilai(str(c.value).strip())]
    if not idx:
        return
    for i in sorted(idx, reverse=True):
        ws.delete_rows(i)
    log.append(("saring baris", p, simpan_dengan_arsip(p, wb), f"{alasan} | {sheet}: {len(idx)} baris dibuang"))


if TAHAP3:
    # Buang jejak data yang sudah dikeluarkan dari gold dan berkas daftar (5 Nov 2026).
    daftar = list(csv.DictReader(open(DAFTAR, encoding="utf-8-sig")))
    foto = {r["path_asli"].split("/")[-1] for r in daftar if r["aksi"] == "pindah"
            and r["path_asli"].lower().endswith((".jpg", ".jpeg", ".png", ".webp"))}
    a = "[tahap 3] baris foto yang sudah dikeluarkan"
    for p in ["data_evaluasi/gambar/manifest/gold_gambar_manifest_final.csv",
              "data_evaluasi/gambar/manifest/gold_gambar_manifest.csv",
              "data_evaluasi/gambar/manifest/ATRIBUSI_LISENSI.csv",
              "data_evaluasi/gambar/manifest/pembagian_8_folder.csv",
              "dataset_eksperimen/2_input_foto/commons_8_folder/ATRIBUSI_LISENSI.csv",
              "dataset_eksperimen/2_input_foto/commons_8_folder/pembagian_8_folder.csv",
              "data_evaluasi/gold/bagian_foto_commons/gold_bagian_commons.csv",
              "data_evaluasi/gold/bagian_foto_commons/kunci_nomor.csv",
              "data_evaluasi/gambar_id/gold_kombinasi_drive1.csv",
              "data_evaluasi/gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv",
              "data_evaluasi/gambar_id/foto_peneliti/foto_peneliti.csv",
              "dataset_eksperimen/2_input_foto/foto_indonesia_drive1/daftar_foto.csv"]:
        saring_csv(p, "filename", lambda r: r["filename"] in foto, a)
    saring_xlsx("data_evaluasi/gambar/manifest/gold_gambar_manifest.xlsx", "Manifest", "A", lambda v: v in foto, a)
    # Lembar anotasi menyimpan foto di dalam berkas (termasuk foto yang dikeluarkan); gold-nya sudah ada sebagai CSV.
    for p in ["data_evaluasi/gold/bagian_foto_commons/lembar_bagian_160.xlsx",
              "data_evaluasi/gambar_id/gold_peneliti/lembar_gold_foto_indonesia.xlsx",
              "data_evaluasi/gambar/manifest/gold_gambar_manifest_final.bak_sebelum_ganti_label_2026-11-05.csv"]:
        if os.path.exists(p):
            pindah(p, "[tahap 3] lembar/cadangan yang memuat foto atau baris yang sudah dikeluarkan")
    # R01 dan varietas yang dikeluarkan di gold atribut dan kunci sel
    if os.path.exists("data_evaluasi/gold/gold_R01_data_input.xlsx"):
        pindah("data_evaluasi/gold/gold_R01_data_input.xlsx", "[tahap 3] gold R01 (workbook dikeluarkan)")
    for p in ["data_evaluasi/gold/gold_semua_dataset.csv", "data_evaluasi/gold/final/gold_semua_dataset_final.csv"]:
        saring_csv(p, "dataset_id", lambda r: r["dataset_id"] == "R01", "[tahap 3] butir gold R01")
    saring_xlsx("data_evaluasi/gold/gold_semua_dataset.xlsx", "Annotations", "G", lambda v: v == "R01", "[tahap 3] butir gold R01")
    saring_xlsx("data_evaluasi/gold/gold_semua_dataset.xlsx", "Ringkasan", "A", lambda v: v == "R01", "[tahap 3] ringkasan R01")
    var_keluar = {("S01", "Cabai tanjung"), ("S03", "Cabai tanjung"), ("S03", "Cabai rawit NTB")} | {
        ("N08", v) for v in ["Arari bode amarela", "Biquinho amarela", "Biquinho vermelha", "Cayenne", "Cheiro do Norte",
                             "Cumari do Pará", "Habanero amarela", "Habanero chocolate", "Habanero vermelha",
                             "Malagueta", "Murupi", "Peito de moça", "Piãozinho"]}
    saring_csv("data_evaluasi/gold/kunci_sel/kunci_sel_semua.csv", "dataset",
               lambda r: r["dataset"] == "R01" or (r["dataset"], r["varietas"]) in var_keluar,
               "[tahap 3] kunci sel R01 dan varietas yang dikeluarkan")

TAHAP4 = "--tahap4" in sys.argv

if TAHAP4:
    # Keputusan peneliti 5 Nov 2026: nama tanpa bukti pendaftaran/kultivar ikut dikeluarkan.
    # Gendot dan Domba = sebutan lokal untuk tipe; Bhut Jolokia = landrace; GRIN Poblano = "Tipo Poblano" (local name).
    # Foto Commons berlabel Poblano tetap (kultivar 'Mexican Ancho' syn. 'Poblano', lihat KLASIFIKASI_LEVEL_VARIETAS.md 2b).
    A_GENDOT = "[tahap 4] 'Gendot' = sebutan lokal untuk tipe habanero; tidak ada bukti pendaftaran varietas"
    A_DOMBA = "[tahap 4] 'Domba' = sebutan lokal untuk tipe rawit besar; tidak ada bukti pendaftaran varietas"
    A_BHUT = "[tahap 4] 'Bhut Jolokia' = landrace tanpa pendaftaran formal"
    A_POBLANO = "[tahap 4] GRIN PI 268105 'Tipo Poblano' = local name tanpa nama kultivar"
    A_UNC = "[tahap 4] Commons UNCERTAIN yang terlewat di tahap 1 (tidak ada di gold final): varietas tidak dapat ditentukan"
    foto4 = {"daun cabai gendot": A_GENDOT, "p9vb80t0ldt5cms.webp": A_GENDOT + " (label hanya tebakan AI)",
             "cabai domba.jpg": A_DOMBA, "daun cabai domba.webp": A_DOMBA}
    gfinal = "data_evaluasi/gambar/manifest/gold_gambar_manifest_final.csv"
    for r in csv.DictReader(open(gfinal, encoding="utf-8-sig")):
        if r["true_variety"] == "Bhut Jolokia":
            foto4[r["filename"]] = A_BHUT
    for r in csv.DictReader(open("data_evaluasi/gambar/manifest/gold_gambar_manifest.csv", encoding="utf-8-sig")):
        if r["label_kind"] == "UNCERTAIN":
            foto4[r["filename"]] = A_UNC
    for nama, alasan in sorted(foto4.items()):
        fs = semua_file(nama)
        if not fs:
            log.append(("TIDAK DITEMUKAN", nama, "", alasan))
        for f in fs:
            pindah(f, alasan)
    hapus_kolom("D01_transposed_indonesia_mixed.xlsx", "Data_Transposed", 1, {"Gendot"}, A_GENDOT + " (S01)")
    hapus_baris("D02_row_flat_english_semantic.xlsx", [("English_Flat_Data", "B")], {"Gendot"}, A_GENDOT + " (S02)")
    hapus_baris("D04_varietas_kosong_invalid.xlsx", [("Data_Invalid", "B")], {"Gendot"}, A_GENDOT + " (S04)")
    hapus_baris("D03_row_multilevel_indonesia.xlsx", [("Data_Bertingkat", "A")], {"Domba"}, A_DOMBA + " (S03)")
    for nama in ["E08_zenodo_capsicum_en.xlsx", "E08_zenodo_capsicum_en_variety.xlsx"]:
        hapus_baris(nama, [("Observed85_readable", "A")], {"Bhut Jolokia"}, A_BHUT + " (N08)")
    hapus_baris("spreadsheet_varietas_terdaftar_17.xlsx", [("Data Varietas", "A")], {"Bhut Jolokia"}, A_BHUT)
    hapus_baris("G02_grin_11_varietas.xlsx", [("GRIN Capsicum", "A"), ("sumber", "A")], {"Poblano"}, A_POBLANO)
    # Jejak foto dan varietas di gold / berkas daftar
    a = "[tahap 4] baris foto yang dikeluarkan"
    for p in ["data_evaluasi/gambar/manifest/gold_gambar_manifest_final.csv",
              "data_evaluasi/gambar/manifest/gold_gambar_manifest.csv",
              "data_evaluasi/gambar/manifest/ATRIBUSI_LISENSI.csv",
              "data_evaluasi/gambar/manifest/pembagian_8_folder.csv",
              "dataset_eksperimen/2_input_foto/commons_8_folder/ATRIBUSI_LISENSI.csv",
              "dataset_eksperimen/2_input_foto/commons_8_folder/pembagian_8_folder.csv",
              "data_evaluasi/gold/bagian_foto_commons/gold_bagian_commons.csv",
              "data_evaluasi/gold/bagian_foto_commons/kunci_nomor.csv",
              "data_evaluasi/gambar_id/gold_kombinasi_drive1.csv",
              "data_evaluasi/gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv",
              "data_evaluasi/gambar_id/foto_peneliti/foto_peneliti.csv",
              "dataset_eksperimen/2_input_foto/foto_indonesia_drive1/daftar_foto.csv"]:
        saring_csv(p, "filename", lambda r: r["filename"] in foto4, a)
    saring_xlsx("data_evaluasi/gambar/manifest/gold_gambar_manifest.xlsx", "Manifest", "A", lambda v: v in foto4, a)
    var4 = {("S01", "Gendot"), ("S02", "Gendot"), ("S03", "Domba"), ("N08", "Bhut Jolokia")}
    saring_csv("data_evaluasi/gold/kunci_sel/kunci_sel_semua.csv", "dataset",
               lambda r: (r["dataset"], r["varietas"]) in var4, "[tahap 4] kunci sel Gendot, Domba, Bhut Jolokia")
    # pembagian_8_folder.csv masih memakai label_kind usulan AI; samakan dengan gold final (setelah ganti label 2d).
    final = {r["filename"]: r["label_kind"] for r in csv.DictReader(open(gfinal, encoding="utf-8-sig"))
             if r["filename"] not in foto4}
    for p in ["data_evaluasi/gambar/manifest/pembagian_8_folder.csv",
              "dataset_eksperimen/2_input_foto/commons_8_folder/pembagian_8_folder.csv"]:
        if not os.path.exists(p):
            continue
        raw = open(p, "rb").read()
        bom = raw.startswith(b"\xef\xbb\xbf")
        eol = "\r\n" if b"\r\n" in raw else "\n"
        rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
        ubah = [r["filename"] for r in rows
                if r["filename"] in final and r["label_kind"] != final[r["filename"]] and r["filename"] not in foto4]
        if not ubah:
            continue
        log.append(("label_kind", p, arsip_path(p), f"[tahap 4] label_kind disamakan dengan gold final: {ubah}"))
        if JALANKAN:
            dst = arsip_path(p)
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(p, dst)
            for r in rows:
                if r["filename"] in final:
                    r["label_kind"] = final[r["filename"]]
            sisa = [r for r in rows if r["filename"] not in foto4]
            with open(p, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator=eol)
                w.writeheader()
                w.writerows(sisa)

if not (TAHAP1 or TAHAP2 or TAHAP3 or TAHAP4):
    sys.exit("Pilih --tahap1, --tahap2, --tahap3, atau --tahap4")
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
