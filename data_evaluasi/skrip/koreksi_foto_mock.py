"""Susun hasil foto Commons terkoreksi: run UI 1 Nov 2026 dengan 19 baris jawaban mock diganti hasil model sungguhan (4 Nov).

Latar: sebelum D18, default_lvm_call diam-diam memakai mock saat panggilan model gagal; 19 dari 160 foto run UI 1 Nov
ternyata jawaban mock (dikenali dari visual_evidence). Ke-19 foto dijalankan ulang di VPS dengan uji_visi_commons_vps.py
(8 varietas terdaftar yang sama, nama berkas asli, tanpa mock, tanpa tulis KMS); hasilnya di
hasil_eksperimen/ulang_foto_mock/hasil_ulang19.csv.

Keluaran: hasil_eksperimen/hasil_ui/2026-11-04_koreksi_mock/gambar/F1..F8/vision.csv (format sama dengan unduhan UI, sehingga
konversi_ui.py dan analisis_paper.py dapat dipakai tanpa perubahan) + daftar_baris_diganti.csv.
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\koreksi_foto_mock.py
"""
import csv
import re
from pathlib import Path

ASAL = Path("hasil_eksperimen/hasil_ui/2026-11-01/gambar")
TUJUAN = Path("hasil_eksperimen/hasil_ui/2026-11-04_koreksi_mock/gambar")
ULANG = Path("hasil_eksperimen/ulang_foto_mock/hasil_ulang19.csv")
POLA_MOCK = re.compile(r"^(Ciri morfologi visual \w+ cocok dengan deskripsi |Morfologi \w+ tidak cocok dengan varietas run aktif|"
                       r"Bukan organ tanaman cabai atau citra tidak meyakinkan)")


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def baris_ui(lama, u):
    """Bentuk baris unduhan UI dari hasil runner (meniru vision_hook: status/write_reason per tindakan fusi)."""
    r = dict(lama)
    aksi = u["fusion_action"]
    if u["status"] == "FAILED":
        r.update(status="FAILED", matched_variety="", identified_part="", confidence="", visual_evidence="",
                 write_applied="False", write_reason="Vision provider/contract failed.", signals_consistent="False")
        return r
    r.update(matched_variety=u["matched_variety"] or "", identified_part=u["identified_part"] or "", confidence=u["confidence"],
             visual_evidence=u["visual_evidence"], signals_consistent=u["signals_consistent"])
    if aksi == "AUTO_LINK":
        r.update(status=u["status"], write_applied="True", write_reason="")
    elif aksi == "CANDIDATE":
        r.update(status="CANDIDATE", write_applied="False", write_reason="CANDIDATE: " + u["fusion_reason"])
    else:
        r.update(status=u["status"], write_applied="False", write_reason="PHOTO_VARIETY_MISMATCH: " + u["fusion_reason"])
    return r


def main():
    ulang = {r["filename"]: r for r in read(ULANG)}
    diganti = []
    for d in sorted(ASAL.iterdir()):
        rows = read(d / "vision.csv")
        cols = list(rows[0].keys())
        out = []
        for r in rows:
            if POLA_MOCK.match(r.get("visual_evidence") or ""):
                u = ulang[r["filename"]]  # wajib ada: setiap baris mock harus punya hasil ulang
                baru = baris_ui(r, u)
                diganti.append({"folder": d.name, "filename": r["filename"], "lama_status": r["status"],
                                "lama_varietas": r["matched_variety"], "lama_bagian": r["identified_part"],
                                "baru_status": baru["status"], "baru_varietas": baru["matched_variety"],
                                "baru_bagian": baru["identified_part"], "baru_confidence": baru["confidence"],
                                "baru_tindakan": u["fusion_action"] or u["status"]})
                out.append(baru)
            else:
                out.append(r)
        (TUJUAN / d.name).mkdir(parents=True, exist_ok=True)
        with open(TUJUAN / d.name / "vision.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(out)
    with open(TUJUAN.parent / "daftar_baris_diganti.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(diganti[0].keys()))
        w.writeheader()
        w.writerows(diganti)
    assert len(diganti) == len(ulang), f"{len(diganti)} baris mock vs {len(ulang)} hasil ulang"
    print(len(diganti), "baris diganti ->", TUJUAN)


if __name__ == "__main__":
    main()
