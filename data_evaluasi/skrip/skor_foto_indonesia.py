"""Skor foto Indonesia (12 foto koleksi peneliti, run kombinasi S01-S03, UI 31 Okt 2026) dengan metrik yang sama dengan
160 foto Commons, plus gabungan Commons + Indonesia.

Gold: gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv (gold peneliti 4 Nov 2026, buat_gold_foto_indonesia.py; 12 foto per run).
Prediksi: dataset_eksperimen/4_hasil_sistem/B_kombinasi_spreadsheet_foto/S0x_*/klasifikasi_foto.csv.
Nama file dicocokkan tanpa tanda baca (di Drive memakai koma, di gold diganti garis bawah).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\skor_foto_indonesia.py
Keluaran: hasil_eksperimen/foto_indonesia/hasil_skor.md
"""
import glob
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import skor_foto_grin as s  # noqa: E402

B = Path("../dataset_eksperimen/4_hasil_sistem/B_kombinasi_spreadsheet_foto")
RUNS = {"S01": "S01_D01_transposed", "S02": "S02_D02_english", "S03": "S03_D03_bertingkat"}
OUT = Path("hasil_eksperimen/foto_indonesia")


def kunci(f):
    return re.sub(r"[^a-z0-9]", "", f.lower())


def butir_indonesia():
    gold = s.read("gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv")
    out = []
    for run, d in RUNS.items():
        pred = {kunci(r["filename"]): r for r in s.read(B / d / "klasifikasi_foto.csv")}
        for g in gold:
            if g["spreadsheet"] != run or g["dinilai"] != "Y":
                continue
            p = pred[kunci(g["filename"])]
            st = (p["status"] or "").upper()
            aksi = "CANDIDATE" if st.startswith("CANDIDATE") else ("AUTO_LINK" if str(p.get("write_applied")).lower() == "true" else "REVIEW")
            if st in ("CANDIDATE", "FAILED_CANDIDATE_RECORD"):
                st = "OTHER"
            out.append({"run": run, "fn": g["filename"], "cond": "INDONESIA", "orig": g["expected_status"], "gold": g["expected_status"],
                        "gold_var": g["expected_variety"], "pred": st, "pred_var": p["matched_variety"] or "", "aksi": aksi,
                        "conf": p.get("confidence", "")})
    return out


def macro_kelas_ada(xs):
    """Macro-F1 hanya atas kelas yang muncul di gold (gold peneliti Indonesia tidak punya UNCERTAIN; macro-F1 tiga kelas
    akan menghitung F1 UNCERTAIN = 0 dan menurunkan skor tanpa dasar)."""
    f1s = []
    for c in sorted({i["gold"] for i in xs}):
        tp = sum(1 for i in xs if i["gold"] == c and i["pred"] == c)
        fp = sum(1 for i in xs if i["gold"] != c and i["pred"] == c)
        fn = sum(1 for i in xs if i["gold"] == c and i["pred"] != c)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1s) / len(f1s)


def baris(lab, xs):
    m = s.metr(xs)
    al = [i for i in xs if i["aksi"] == "AUTO_LINK"]
    ok = sum(1 for i in al if i["gold"] == "KNOWN" and s.benar(i))
    return (f"| {lab} | {len(xs)} | {sum(s.benar(i) for i in xs)}/{len(xs)} | {m['macro_f1']:.3f} | {macro_kelas_ada(xs):.3f} | "
            f"{m['top1_known']:.3f} | {ok}/{len(al)} = {ok / len(al):.3f} |")


def main():
    ind = butir_indonesia()
    gold = s.read(s.GOLD)
    ui = {}
    for f in glob.glob(s.UI):
        for r in s.read(f):
            ui[r["filename"]] = r
    com = s.items(ui, gold)
    out = ["# Foto Indonesia (S01-S03) dan gabungan dengan 160 foto Commons", "",
           "Metrik sama dengan foto Commons (hitung_metrik.img_metrics): status KNOWN/OTHER/UNCERTAIN, Top-1 pada foto KNOWN, "
           "presisi AUTO_LINK. Foto Indonesia: 12 foto unik yang sama di tiga run (spreadsheet berbeda), jadi 36 keputusan tidak "
           "independen. Gold Indonesia = isian peneliti 4 Nov 2026 (3 varietas tebakan AI atas persetujuan peneliti) dan tidak memuat "
           "UNCERTAIN, sehingga untuk foto Indonesia yang adil adalah macro-F1 atas kelas yang ada di gold (KNOWN, OTHER).", "",
           "| Himpunan | Keputusan | Status benar | Macro-F1 3 kelas | Macro-F1 kelas di gold | Top-1 KNOWN | AUTO_LINK benar |",
           "|---|---|---|---|---|---|---|"]
    for run in RUNS:
        out.append(baris(f"Indonesia {run}", [i for i in ind if i["run"] == run]))
    out.append(baris("Indonesia, 3 run", ind))
    out.append(baris("Commons 160 (UI 1 Nov, terkoreksi D18)", com))
    out.append(baris("Gabungan Commons + Indonesia", com + ind))
    out += ["", "## Per foto (Indonesia)", "", "| Run | Foto | Gold | Sistem | Confidence | Tindakan | Benar |", "|---|---|---|---|---|---|---|"]
    for i in ind:
        out.append(f"| {i['run']} | {i['fn'][:60]} | {i['gold']} {i['gold_var']} | {i['pred']} {i['pred_var']} | {i['conf']} | {i['aksi']} | "
                   f"{'ya' if s.benar(i) else 'tidak'} |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hasil_skor.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:12]))


if __name__ == "__main__":
    main()
