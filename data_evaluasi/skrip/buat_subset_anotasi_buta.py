"""Buat subset anotasi buta untuk memvalidasi gold atribut (kappa).

Subset = semua butir prioritas (perlu_adjudikasi = Y) + sampel acak butir non-prioritas,
distratifikasi menurut gold_status (alokasi proporsional). S04 dikeluarkan karena ditolak
sistem dan tidak ikut skor.

Keluaran (folder anotasi_buta/subset_v1/):
  lembar_anotator.xlsx   -> diberikan ke anotator. Tidak memuat gold, prediksi sistem,
                            keyakinan model, atau tanda prioritas. Urutan butir diacak.
  kunci_subset.csv       -> JANGAN diberikan ke anotator. Menghubungkan id_butir ke
                            mapping_item_id dan stratum.
  ringkasan_subset.md    -> komposisi subset (aman dibaca peneliti).

Jalankan dari folder data_evaluasi:
  ..\\.venv\\Scripts\\python.exe skrip\\buat_subset_anotasi_buta.py
"""
import argparse
import hashlib
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

SEED = 20261102
STATUSES = ["ONE_TO_ONE", "NO_MATCH", "AMBIGUOUS", "COMPOSITE", "EXCLUDE"]
KUNING = PatternFill("solid", fgColor="FFF2CC")
ABU = PatternFill("solid", fgColor="EDEDED")

PETUNJUK = [
    "PETUNJUK ANOTASI BUTA - PEMETAAN ATRIBUT CABAI-KMS",
    "",
    "Tujuan: menentukan baris kanonik (sheet 'Referensi Kanonik') yang paling tepat untuk setiap atribut sumber.",
    "Kerjakan sendiri. Jangan membuka berkas gold, hasil sistem, atau berdiskusi dengan orang lain sampai selesai.",
    "Gunakan nama atribut, konteks (judul induk kolom), dan contoh nilai. Contoh nilai dipisah dengan ' || '.",
    "",
    "Isi hanya kolom kuning:",
    "  status       ONE_TO_ONE  = tepat satu baris kanonik cocok; isi kunci_utama.",
    "               NO_MATCH    = atribut valid tetapi tidak ada baris kanonik yang cocok (mis. koordinat, nomor urut, nama pemohon).",
    "               AMBIGUOUS   = dua atau lebih baris sama-sama masuk akal; isi kunci_utama (pilihan terbaik) dan kunci_lain.",
    "               COMPOSITE   = satu atribut memuat beberapa konsep (mis. 'ukuran daun' = panjang dan lebar); isi semua kunci.",
    "               EXCLUDE     = tidak dapat dinilai sama sekali; wajib isi catatan.",
    "  kunci_utama  pilih dari daftar (canonical_key). Kosongkan bila NO_MATCH atau EXCLUDE.",
    "  kunci_lain   kunci tambahan untuk AMBIGUOUS/COMPOSITE, dipisah tanda '|', mis. panjang_daun|lebar_daun.",
    "  yakin        Ya atau Ragu.",
    "  catatan      opsional; wajib untuk EXCLUDE.",
    "",
    "Tidak ada jawaban yang dinilai benar atau salah untuk Anda; yang diukur adalah kesepakatan antar penilai.",
    "Perkiraan waktu: sekitar 1 menit per butir.",
]


def md_table(t: pd.DataFrame) -> str:
    head = "| " + " | ".join([str(t.index.name or "")] + [str(c) for c in t.columns]) + " |"
    sep = "|" + "---|" * (len(t.columns) + 1)
    body = ["| " + " | ".join([str(i)] + [str(v) for v in row]) + " |" for i, row in zip(t.index, t.values)]
    return "\n".join([head, sep, *body])


def load_priority(path: Path) -> pd.DataFrame:
    ws = openpyxl.load_workbook(path, read_only=True)["Verifikasi"]
    rows = list(ws.iter_rows(values_only=True))
    v = pd.DataFrame(rows[1:], columns=rows[0])
    return v[["mapping_item_id", "prioritas_periksa"]]


def allocate(counts: pd.Series, n: int) -> dict:
    """Alokasi proporsional dengan metode sisa terbesar; tiap strata non-kosong minimal 1."""
    total = counts.sum()
    raw = counts / total * n
    alloc = raw.astype(int).clip(lower=1)
    while alloc.sum() < n:
        rem = (raw - alloc).sort_values(ascending=False)
        alloc[rem.index[0]] += 1
        raw[rem.index[0]] = -1  # jangan dipilih dua kali dalam satu putaran
    while alloc.sum() > n:
        alloc[alloc.idxmax()] -= 1
    return alloc.to_dict()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-acak", type=int, default=43)
    ap.add_argument("--out", default="anotasi_buta/subset_v1")
    args = ap.parse_args()

    base = Path(".")
    gold = pd.read_csv(base / "gold/final/gold_semua_dataset_final.csv")
    prio = load_priority(base / "verifikasi_gold/verifikasi_atribut_terisi.xlsx")
    df = gold.merge(prio, on="mapping_item_id", how="left")
    assert df.prioritas_periksa.notna().all(), "ada butir tanpa tanda prioritas"
    df = df[df.dataset_id != "S04"].copy()

    pri = df[df.prioritas_periksa == "Y"].assign(stratum="prioritas")
    pool = df[df.prioritas_periksa == "N"]
    alloc = allocate(pool.gold_status.value_counts(), args.n_acak)
    acak = pd.concat(
        [pool[pool.gold_status == s].sample(n=k, random_state=SEED) for s, k in alloc.items()]
    ).assign(stratum="acak")

    sub = pd.concat([pri, acak]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    sub["id_butir"] = [f"B{i:03d}" for i in range(1, len(sub) + 1)]

    out = base / args.out
    out.mkdir(parents=True, exist_ok=True)

    # Kunci: hanya untuk peneliti
    sub[["id_butir", "mapping_item_id", "dataset_id", "stratum"]].to_csv(
        out / "kunci_subset.csv", index=False, encoding="utf-8-sig"
    )

    # Lembar anotator
    ref_src = openpyxl.load_workbook(base / "anotasi_buta/anotator_A_atribut.xlsx", read_only=True)
    ref_rows = list(ref_src["Canonical Reference"].iter_rows(values_only=True))
    keys = [r[0] for r in ref_rows[1:] if r[0]]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Petunjuk"
    for line in PETUNJUK:
        ws.append([line])
    ws["A1"].font = Font(bold=True, size=12)
    ws.column_dimensions["A"].width = 130

    wa = wb.create_sheet("Anotasi")
    cols_info = ["id_butir", "dataset", "format_sumber", "atribut_sumber", "konteks", "contoh_nilai"]
    cols_isi = ["status", "kunci_utama", "kunci_lain", "yakin", "catatan", "nama_anotator"]
    wa.append(cols_info + cols_isi)
    for _, r in sub.iterrows():
        wa.append([
            r.id_butir, r.dataset_id, r.source_format, r.source_attribute_display,
            "" if pd.isna(r.source_context) else r.source_context,
            "" if pd.isna(r.contoh_nilai_sumber) else r.contoh_nilai_sumber,
        ] + [""] * len(cols_isi))
    n = len(sub) + 1
    for c in wa[1]:
        c.font = Font(bold=True)
    for row in wa.iter_rows(min_row=2, max_row=n):
        for c in row[: len(cols_info)]:
            c.fill = ABU
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for c in row[len(cols_info):]:
            c.fill = KUNING
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for col, w in zip("ABCDEFGHIJKL", [8, 8, 12, 34, 28, 50, 14, 26, 26, 8, 30, 16]):
        wa.column_dimensions[col].width = w
    wa.freeze_panes = "B2"

    wr = wb.create_sheet("Referensi Kanonik")
    for r in ref_rows:
        wr.append(list(r))
    for c in wr[1]:
        c.font = Font(bold=True)
    for col, w in zip("ABCDE", [28, 30, 14, 50, 40]):
        wr.column_dimensions[col].width = w
    wr.freeze_panes = "A2"

    dv_status = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    dv_key = DataValidation(type="list", formula1=f"='Referensi Kanonik'!$A$2:$A${len(keys) + 1}", allow_blank=True)
    dv_yakin = DataValidation(type="list", formula1='"Ya,Ragu"', allow_blank=True)
    for dv, col in [(dv_status, "G"), (dv_key, "H"), (dv_yakin, "J")]:
        wa.add_data_validation(dv)
        dv.add(f"{col}2:{col}{n}")

    sheet_path = out / "lembar_anotator.xlsx"
    wb.save(sheet_path)

    # Ringkasan (tanpa label gold per butir)
    sha = hashlib.sha256(sheet_path.read_bytes()).hexdigest()
    pop = df.groupby("prioritas_periksa").size().to_dict()
    lines = [
        "# Subset anotasi buta v1",
        "",
        f"Seed {SEED}. Populasi skor (tanpa S04): {len(df)} butir; prioritas {pop.get('Y', 0)}, non-prioritas {pop.get('N', 0)}.",
        f"Subset: {len(sub)} butir = {len(pri)} prioritas (semua) + {len(acak)} acak terstratifikasi gold_status.",
        f"Alokasi acak per gold_status: {alloc}",
        "",
        "Komposisi per dataset:",
        "",
        md_table(sub.groupby(["dataset_id", "stratum"]).size().unstack(fill_value=0)),
        "",
        f"SHA-256 lembar_anotator.xlsx: `{sha}`",
        "",
        "Berikan hanya `lembar_anotator.xlsx` ke anotator. `kunci_subset.csv` dan gold tetap pada peneliti.",
        "Bobot estimasi untuk seluruh gold: prioritas "
        f"{pop.get('Y', 0)}/{len(df)}, non-prioritas {pop.get('N', 0)}/{len(df)}.",
    ]
    (out / "ringkasan_subset.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
