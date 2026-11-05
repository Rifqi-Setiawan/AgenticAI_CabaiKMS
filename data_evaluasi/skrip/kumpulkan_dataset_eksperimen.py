"""Kumpulkan semua data input eksperimen dan hasil olahan sistem ke satu folder: <project>/dataset_eksperimen/.

Hanya MENYALIN (berkas asli tidak dipindah atau diubah). Gold label tidak ikut disalin.
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe skrip\\kumpulkan_dataset_eksperimen.py
Tambahan 3 Nov 2026 (foto Berita Resmi PVT dan uji 40 foto) ke folder yang sudah ada:
  ..\\.venv\\Scripts\\python.exe skrip\\kumpulkan_dataset_eksperimen.py --tambah-pvt
Tambahan 4 Nov 2026 (rerun N07/R02 commit ac4f2e4 untuk akurasi sel):
  ..\\.venv\\Scripts\\python.exe skrip\\kumpulkan_dataset_eksperimen.py --tambah-sel
Tambahan 4 Nov 2026 (spreadsheet data asli GRIN untuk 160 foto; boleh diulang setelah hasil run tersedia):
  ..\\.venv\\Scripts\\python.exe skrip\\kumpulkan_dataset_eksperimen.py --tambah-grin
"""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

EV = Path(".").resolve()
PROJ = EV.parent
OUT = PROJ / "dataset_eksperimen"
UI = EV / "hasil_eksperimen" / "hasil_ui"

INPUTS = [
    "data_input.xlsx", "input_cabai_kms.xlsx", "E07_kementan_deskripsi_ext.xlsx", "E08_zenodo_capsicum_en.xlsx",
    "E08_zenodo_capsicum_en_variety.xlsx", "dataset_cabai_deskripsi_varietas.xlsx",
    "D01_transposed_indonesia_mixed.xlsx", "D02_row_flat_english_semantic.xlsx",
    "D03_row_multilevel_indonesia.xlsx", "D04_varietas_kosong_invalid.xlsx",
]
# (folder tujuan, sumber hasil UI, berkas yang disalin {asal: nama baru})
RUNS = [
    ("A_atribut/R01_data_input", UI / "2026-10-31/atribut/R01"),
    ("A_atribut/R02_input_cabai_kms", UI / "2026-10-31/atribut/R02"),
    ("A_atribut/N07_kementan", UI / "2026-10-31/atribut/N07"),
    ("A_atribut/N08_zenodo_variety", UI / "2026-10-31/atribut_n08var/N08"),
    ("A_atribut/N09_deskripsi_varietas", UI / "2026-10-31/atribut/N09"),
    ("B_kombinasi_spreadsheet_foto/S01_D01_transposed", UI / "2026-10-31/kombinasi/S01"),
    ("B_kombinasi_spreadsheet_foto/S02_D02_english", UI / "2026-10-31/kombinasi/S02"),
    ("B_kombinasi_spreadsheet_foto/S03_D03_bertingkat", UI / "2026-10-31/kombinasi/S03"),
] + [(f"C_foto_commons/F{i}", UI / f"2026-11-01/gambar/F{i}") for i in range(1, 9)]
RENAME = {"hasil_asli.xlsx": "hasil_kanonik.xlsx", "mapping.csv": "pemetaan_atribut.csv", "vision.csv": "klasifikasi_foto.csv"}


def copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def salin_pvt():
    """Foto Berita Resmi PVT (34 varietas) dan uji 40 foto kartu terlihat/tertutup. Kolom gold varietas tidak disalin."""
    pv = EV / "pilot_foto_pvt"
    uji = pv / "uji_visi_40"
    dst = OUT / "2_input_foto" / "pvt_kementan_34_varietas"
    for f in sorted((pv / "foto").rglob("*.png")):
        copy(f, dst / f.relative_to(pv / "foto"))
    copy(pv / "manifest_foto_pvt.csv", dst / "daftar_foto.csv")
    copy(pv / "daftar_berita_resmi_cabai.tsv", dst / "daftar_berita_resmi_cabai.tsv")
    used = {r["sumber_pdf"] for r in csv.DictReader(open(pv / "manifest_foto_pvt.csv", encoding="utf-8"))}
    for name in sorted(used):
        copy(pv / "pdf" / name, dst / "sumber_pdf" / name)
    # uji 40 foto: input
    d40 = OUT / "2_input_foto" / "pvt_uji_40"
    for k, nama in (("terlihat", "kartu_terlihat"), ("tertutup", "kartu_tertutup")):
        for f in sorted((uji / "img" / k).glob("*.webp")):
            copy(f, d40 / nama / f.name)
    copy(uji / "varietas_terdaftar.txt", d40 / "varietas_terdaftar.txt")
    copy(uji / "kotak_penutup_kartu.json", d40 / "kotak_penutup_kartu.json")
    rows = list(csv.DictReader(open(uji / "sampel.csv", encoding="utf-8")))
    d40.mkdir(parents=True, exist_ok=True)
    with open(d40 / "pembagian_uji_40.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "label_kind", "berkas_sumber", "sha256_sumber"])
        for r in rows:
            w.writerow([r["id"] + ".jpg", r["gold_status"], r["berkas_sumber"], r["sha256"]])
    # uji 40 foto: hasil sistem
    h = OUT / "4_hasil_sistem" / "E_foto_pvt_uji40"
    h.mkdir(parents=True, exist_ok=True)
    meta = json.load(open(uji / "meta.json", encoding="utf-8"))
    pred = list(csv.DictReader(open(uji / "hasil.csv", encoding="utf-8")))
    cols = ["filename", "status", "matched_variety", "identified_part", "confidence", "visual_confidence", "signals_consistent",
            "fusion_action", "fusion_reason", "visual_evidence", "detik", "galat", "options_evaluated"]
    for k, nama in (("terlihat", "klasifikasi_foto_kartu_terlihat.csv"), ("tertutup", "klasifikasi_foto_kartu_tertutup.csv")):
        with open(h / nama, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for p in pred:
                if p["kondisi"] == k:
                    w.writerow({**{c: p.get(c, "") for c in cols}, "filename": p["id"] + ".jpg",
                                "options_evaluated": "; ".join(meta["options"])})
    meta["commit"] = (uji / "commit.txt").read_text().strip()
    (h / "meta_run.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    copy(uji / "run.log", h / "log_run.txt")


def salin_rerun_sel():
    """Rerun N07 dan R02 pada commit ac4f2e4 (perbaikan deteksi kolom varietas) untuk metrik akurasi sel (poin 3)."""
    src = EV / "hasil_eksperimen" / "hasil_harness" / "2026-11-04_sel_ac4f2e4" / "rep1" / "atribut"
    for ds, nama in (("N07", "N07_kementan"), ("R02", "R02_input_cabai_kms")):
        for f in ("hasil_asli.xlsx", "mapping.csv"):
            copy(src / ds / f, OUT / "4_hasil_sistem" / "F_rerun_kolom_varietas_ac4f2e4" / nama / RENAME[f])
        copy(src / ds / "meta.json", OUT / "4_hasil_sistem" / "F_rerun_kolom_varietas_ac4f2e4" / nama / "meta_run.json")


def salin_grin():
    """Spreadsheet data asli USDA GRIN (pasangan 160 foto Commons) dan, bila sudah ada, hasil run VPS. Boleh dijalankan ulang."""
    sys.path.insert(0, str(EV / "skrip"))
    import buat_workbook_grin as bw
    for f in ("G01_grin_8_varietas_terdaftar.xlsx", "G02_grin_11_varietas.xlsx"):
        copy(EV / "inputs" / f, OUT / "1_input_spreadsheet" / f)
    g = EV / "sumber_luar_negeri" / "grin"
    obs = json.loads((g / "observasi.json").read_text(encoding="utf-8"))
    obs.update(json.loads((g / "observasi_negara.json").read_text(encoding="utf-8")))
    sumber = OUT / "1_input_spreadsheet" / "sumber_grin"
    terpilih = {}
    for tipe, (gid, alasan) in bw.PILIH.items():
        pi, spesies, nama_aksesi = bw.identitas(gid, obs, {})
        copy(g / "aksesi" / f"{gid}.html", sumber / f"{pi.replace(' ', '_')}_{gid}.html")
        terpilih[tipe] = {"accession": pi, "accession_name": nama_aksesi, "species": spesies, "grin_id": gid, "alasan": alasan,
                          "url": f"https://npgsweb.ars-grin.gov/gringlobal/accessiondetail?id={gid}", "observasi": obs[gid]["observasi"]}
    sumber.mkdir(parents=True, exist_ok=True)
    (sumber / "observasi_aksesi_terpilih.json").write_text(json.dumps(terpilih, indent=1, ensure_ascii=False), encoding="utf-8")
    hasil = EV / "hasil_eksperimen" / "foto_grin"
    if (hasil / "hasil_grin8.csv").exists():
        dst = OUT / "4_hasil_sistem" / "G_grin_160_foto"
        for ds in ("G01", "G02"):
            for f, nama in (("hasil_asli.xlsx", "hasil_kanonik.xlsx"), ("mapping.csv", "pemetaan_atribut.csv"), ("meta.json", "meta_run.json")):
                copy(hasil / "sheet" / "rep1" / "grin" / ds / f, dst / ds / nama)
        for lab in ("grin8", "grin11"):
            copy(hasil / f"hasil_{lab}.csv", dst / f"klasifikasi_foto_{lab}.csv")
            copy(hasil / f"meta_{lab}.json", dst / f"meta_foto_{lab}.json")
        for f in ("kms_sebelum.json", "kms_setelah_sheet.json", "kms_setelah.json", "commit.txt"):
            copy(hasil / f, dst / f)
        copy(hasil / "run.log", dst / "log_run.txt")


def salin_koreksi_mock():
    """Koreksi D18 (4 Nov 2026): 19 foto run UI 1 Nov yang dijawab mock dijalankan ulang dengan model; hasil per folder
    F1-F8 = run UI dengan 19 baris itu diganti (koreksi_foto_mock.py). C_foto_commons/ tetap keluaran asli UI."""
    ul = EV / "hasil_eksperimen" / "ulang_foto_mock"
    ko = EV / "hasil_eksperimen" / "hasil_ui" / "2026-11-04_koreksi_mock"
    dst = OUT / "4_hasil_sistem" / "H_koreksi_foto_commons_D18"
    for i in range(1, 9):
        copy(ko / "gambar" / f"F{i}" / "vision.csv", dst / f"F{i}" / "klasifikasi_foto_terkoreksi.csv")
    copy(ko / "daftar_baris_diganti.csv", dst / "daftar_baris_diganti.csv")
    rerun = dst / "rerun_19_foto"
    for src, nama in (("daftar_foto.csv", "daftar_foto.csv"), ("hasil_ulang19.csv", "klasifikasi_19_foto.csv"),
                      ("hasil_ulang19_percobaan1.csv", "klasifikasi_percobaan1.csv"),
                      ("hasil_coba2_foto_gagal.csv", "klasifikasi_percobaan2_foto_gagal.csv"),
                      ("meta_ulang19.json", "meta_run.json"), ("meta_coba2.json", "meta_run_percobaan2.json"),
                      ("run.log", "log_run.txt"), ("commit.txt", "commit.txt"), ("perubahan_kode.txt", "perubahan_kode.txt")):
        copy(ul / src, rerun / nama)


def tulis_checksum():
    lines = []
    for f in sorted(OUT.rglob("*")):
        # ~$*.xlsx = berkas kunci Excel saat workbook sedang dibuka; bukan data.
        # _dikeluarkan_bukan_varietas/ = arsip lokal data yang dikeluarkan (D19), punya checksum sendiri.
        if "_dikeluarkan_bukan_varietas" in f.relative_to(OUT).parts:
            continue
        if f.is_file() and f.name != "SHA256SUMS.txt" and not f.name.startswith("~$"):
            lines.append(hashlib.sha256(f.read_bytes()).hexdigest() + "  " + f.relative_to(OUT).as_posix())
    # LF eksplisit agar `sha256sum -c SHA256SUMS.txt` langsung jalan (write_text di Windows menulis CRLF)
    (OUT / "SHA256SUMS.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(len(lines), "berkas tercatat di", OUT / "SHA256SUMS.txt")


def main():
    if "--tambah-koreksi" in sys.argv:
        salin_koreksi_mock()
        tulis_checksum()
        return
    if "--tambah-grin" in sys.argv:
        salin_grin()
        tulis_checksum()
        return
    if "--tambah-sel" in sys.argv:
        if (OUT / "4_hasil_sistem" / "F_rerun_kolom_varietas_ac4f2e4").exists():
            raise SystemExit("Rerun kolom varietas sudah ada di dataset_eksperimen.")
        salin_rerun_sel()
        tulis_checksum()
        return
    if "--tambah-pvt" in sys.argv:
        if not OUT.exists():
            raise SystemExit(f"{OUT} belum ada; jalankan tanpa --tambah-pvt dulu.")
        if (OUT / "2_input_foto" / "pvt_kementan_34_varietas").exists() or (OUT / "4_hasil_sistem" / "E_foto_pvt_uji40").exists():
            raise SystemExit("Data PVT sudah ada di dataset_eksperimen; hapus folder PVT dulu bila ingin menyalin ulang.")
        salin_pvt()
        tulis_checksum()
        return
    if OUT.exists():
        raise SystemExit(f"{OUT} sudah ada; hapus atau ganti nama dulu agar tidak tercampur.")
    for f in INPUTS:
        copy(EV / "inputs" / f, OUT / "1_input_spreadsheet" / f)
    copy(EV / "gambar" / "spreadsheet_varietas_terdaftar.xlsx", OUT / "1_input_spreadsheet" / "spreadsheet_varietas_terdaftar.xlsx")
    for d in sorted((EV / "gambar" / "drive_8folder").iterdir()):
        for f in sorted(d.iterdir()):
            copy(f, OUT / "2_input_foto" / "commons_8_folder" / d.name / f.name)
    copy(EV / "gambar" / "manifest" / "ATRIBUSI_LISENSI.csv", OUT / "2_input_foto" / "commons_8_folder" / "ATRIBUSI_LISENSI.csv")
    copy(EV / "gambar" / "manifest" / "pembagian_8_folder.csv", OUT / "2_input_foto" / "commons_8_folder" / "pembagian_8_folder.csv")
    for f in sorted((EV / "gambar_id" / "foto_peneliti").iterdir()):
        name = "daftar_foto.csv" if f.name == "foto_peneliti.csv" else f.name
        copy(f, OUT / "2_input_foto" / "foto_indonesia_drive1" / name)
    copy(PROJ / "data" / "canonical" / "template_kanonik.xlsx", OUT / "3_template_kanonik" / "template_kanonik.xlsx")
    for dest, src in RUNS:
        for f in ("hasil_asli.xlsx", "mapping.csv", "vision.csv"):
            if (src / f).exists():
                copy(src / f, OUT / "4_hasil_sistem" / dest / RENAME[f])
    dyn = UI / "2026-11-02"
    copy(dyn / "run3" / "data_input_cabai_kms.xlsx", OUT / "4_hasil_sistem" / "D_skema_dinamis_R01" / "hasil_kanonik_68_baris.xlsx")
    if (dyn / "LAPORAN_UJI_UI_SKEMA_DINAMIS.md").exists():
        copy(dyn / "LAPORAN_UJI_UI_SKEMA_DINAMIS.md", OUT / "4_hasil_sistem" / "D_skema_dinamis_R01" / "laporan_uji.md")
    if (EV / "pilot_foto_pvt" / "uji_visi_40" / "hasil.csv").exists():
        salin_pvt()
    if (EV / "hasil_eksperimen" / "hasil_harness" / "2026-11-04_sel_ac4f2e4").exists():
        salin_rerun_sel()
    if (EV / "inputs" / "G01_grin_8_varietas_terdaftar.xlsx").exists():
        salin_grin()
    tulis_checksum()


if __name__ == "__main__":
    main()
