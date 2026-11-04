"""Tabel kasus L3: foto peneliti (Drive 1) x spreadsheet S01..S03, status yang diharapkan vs diamati (hasil UI, commit bc3c21b).

Dijalankan dari data_evaluasi/: python -I skrip/tabel_kasus_l3.py --out hasil_eksperimen/tabel_kasus_l3.md
"""
import argparse
import csv
from pathlib import Path


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    gold = read("gambar_id/gold_kombinasi_drive1.csv")
    out = ["# Tabel kasus L3: foto Indonesia (Drive 1) x spreadsheet (kualitatif, bukan F1)\n",
           "Sumber: hasil UI `hasil_eksperimen/hasil_ui/2026-10-31/kombinasi/`; gold `gambar_id/gold_kombinasi_drive1.csv` (label dari nama berkas peneliti). "
           "Status CANDIDATE di UI = OTHER. Nama berkas bertanda koma dicocokkan dengan versi bergaris bawah di gold. Hanya foto berkolom `dinilai=Y` yang dihitung; foto bagian daun, bunga, atau tangkai tidak dapat dibedakan varietasnya dari gambar, "
           "jadi UNCERTAIN pada foto itu bukan kesalahan otomatis. S04 ditolak sistem (struktur workbook). "
           "Kolom Diamati memakai status visual mentah (setara V1); skor di HASIL_SEMENTARA bagian 3 memakai status akhir V3 (review dihitung UNCERTAIN), sehingga S03 berbeda satu foto (daun cabai domba).\n"]
    for ds in ("S01", "S02", "S03"):
        vis = {r["filename"].replace(",", "_"): r for r in read(f"hasil_eksperimen/hasil_ui/2026-10-31/kombinasi/{ds}/vision.csv")}
        rows = [g for g in gold if g["spreadsheet"] == ds and g["dinilai"] == "Y"]
        out += [f"## {ds}\n", "| Foto | Varietas/jenis | Bagian (gold) | Harapan | Diamati (status, varietas) | Bagian diamati | Keyakinan | Cocok status | Ditulis ke KMS |",
                "|---|---|---|---|---|---|---|---|---|"]
        ok = 0
        for g in rows:
            v = vis.get(g["filename"])
            if v is None:
                out.append(f"| {g['filename']} | {g['varietas_atau_jenis']} | {g['bagian']} | {g['expected_status']} {g['expected_variety']} | tidak ada di hasil | | | tidak | |")
                continue
            st = "OTHER" if v["status"] == "CANDIDATE" else v["status"]  # UI menamai OTHER sebagai CANDIDATE
            match = st == g["expected_status"] and (g["expected_status"] != "KNOWN" or v["matched_variety"].lower() == g["expected_variety"].lower())
            ok += match
            out.append(f"| {g['filename']} | {g['varietas_atau_jenis']} | {g['bagian']} | {g['expected_status']} {g['expected_variety']} | {v['status']} {v['matched_variety']} | "
                       f"{v['identified_part']} | {v['confidence']} | {'ya' if match else 'tidak'} | {v['write_applied']} |")
        out.append(f"\nCocok: {ok} dari {len(rows)}.\n")
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
