"""Skor uji 40 foto Berita Resmi PVT (pilot poin 8): kartu nama terlihat vs tertutup.

Gold: pilot_foto_pvt/uji_visi_40/sampel.csv (status KNOWN = varietas terdaftar di spreadsheet run, OTHER = tidak terdaftar;
label varietas dari dokumen resmi). Prediksi: pilot_foto_pvt/uji_visi_40/hasil.csv dari run_visi40.py di VPS.
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe -I skrip\\skor_uji_visi_pvt.py [--bagian BERKAS.xlsx]
Bila lembar anotasi bagian tanaman sudah diisi (default pilot_foto_pvt/uji_visi_40/terisi_bagian.xlsx), skor bagian
tanaman ikut dihitung: ketat (prediksi = bagian_utama) dan longgar (prediksi = bagian_utama atau bagian_lain), hanya untuk
foto yang bagian utamanya salah satu kelas sistem (DAUN/BATANG/BUAH/BUNGA).
"""
import collections
import csv
import sys
from pathlib import Path

D = Path("pilot_foto_pvt/uji_visi_40")
KELAS = ("DAUN", "BATANG", "BUAH", "BUNGA")


def baca_bagian(path):
    """id_foto -> dict(utama, lain, kartu, yakin) dari lembar anotasi yang sudah diisi."""
    from openpyxl import load_workbook
    ws = load_workbook(path, data_only=True)["Anotasi"]
    head = [c.value for c in ws[1]]
    out, nama = {}, ""
    for row in ws.iter_rows(min_row=2, values_only=True):
        r = dict(zip(head, row))
        if not r.get("id_foto"):
            continue
        nama = nama or (r.get("nama_anotator") or "")
        up = lambda v: (str(v).strip().upper() if v else "")
        out[r["id_foto"]] = {"utama": up(r.get("bagian_utama")), "lain": up(r.get("bagian_lain")),
                             "kartu": (str(r.get("ada_kartu_nama") or "").strip()), "yakin": str(r.get("yakin") or "").strip()}
    return out, nama


def skor_bagian(pred, gold, bag, nama):
    kosong = [i for i, b in bag.items() if not b["utama"]]
    out = ["", f"## Bagian tanaman (anotator: {nama or '-'}; belum diisi: {len(kosong)})", "",
           "Hanya foto dengan bagian_utama DAUN/BATANG/BUAH/BUNGA yang dinilai, karena sistem hanya memakai empat kelas itu.", "",
           "| Metrik | Kartu terlihat | Kartu tertutup |", "|---|---|---|"]
    res = {}
    for k in ("terlihat", "tertutup"):
        ps = [p for p in pred if p["kondisi"] == k and bag.get(p["id"], {}).get("utama")]
        nilai = [p for p in ps if bag[p["id"]]["utama"] in KELAS]
        ketat = sum(p["identified_part"] == bag[p["id"]]["utama"] for p in nilai)
        longgar = sum(p["identified_part"] in (bag[p["id"]]["utama"], bag[p["id"]]["lain"]) for p in nilai)
        luar = collections.Counter((bag[p["id"]]["utama"], p["identified_part"]) for p in ps if bag[p["id"]]["utama"] not in KELAS)
        res[k] = {"n": f"{len(nilai)}", "ketat": f"{ketat}/{len(nilai)}" + (f" = {ketat / len(nilai):.2f}" if nilai else ""),
                  "longgar": f"{longgar}/{len(nilai)}" + (f" = {longgar / len(nilai):.2f}" if nilai else ""),
                  "luar": "; ".join(f"{g}->{p} {n}" for (g, p), n in sorted(luar.items())) or "-"}
    for key, lab in (("n", "Foto dinilai (gold 4 kelas)"), ("ketat", "Akurasi ketat"), ("longgar", "Akurasi longgar"),
                     ("luar", "Gold di luar 4 kelas -> prediksi")):
        out.append(f"| {lab} | {res['terlihat'][key]} | {res['tertutup'][key]} |")
    # matriks kebingungan, kartu terlihat
    ps = [p for p in pred if p["kondisi"] == "terlihat" and bag.get(p["id"], {}).get("utama") in KELAS]
    out += ["", "Matriks bagian (kartu terlihat; baris gold, kolom prediksi):", "", "| gold \\ prediksi | " + " | ".join(KELAS) + " |",
            "|---" * (len(KELAS) + 1) + "|"]
    for g in KELAS:
        out.append(f"| {g} | " + " | ".join(str(sum(1 for p in ps if bag[p['id']]['utama'] == g and p['identified_part'] == c)) for c in KELAS) + " |")
    # top-1 menurut keberadaan kartu (kondisi kartu terlihat)
    norm = lambda s: "".join(c for c in (s or "").lower() if c.isalnum())
    out += ["", "Top-1 varietas (kartu terlihat, foto KNOWN) menurut keberadaan kartu nama:", ""]
    for ada in ("Ya", "Tidak"):
        ks = [p for p in pred if p["kondisi"] == "terlihat" and gold[p["id"]]["gold_status"] == "KNOWN" and bag.get(p["id"], {}).get("kartu") == ada]
        ok = sum(p["status"] == "KNOWN" and norm(p["matched_variety"]) == norm(gold[p["id"]]["gold_variety"]) for p in ks)
        out.append(f"- kartu {ada}: {ok}/{len(ks)}")
    return out


def norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def main():
    gold = {r["id"]: r for r in csv.DictReader(open(D / "sampel.csv", encoding="utf-8"))}
    pred = list(csv.DictReader(open(D / "hasil.csv", encoding="utf-8")))
    out = ["# Uji 40 foto Berita Resmi PVT: kartu nama terlihat vs tertutup", "",
           "| Metrik | Kartu terlihat | Kartu tertutup |", "|---|---|---|"]
    res = {}
    for k in ("terlihat", "tertutup"):
        ps = [p for p in pred if p["kondisi"] == k]
        g = lambda p: gold[p["id"]]
        known = [p for p in ps if g(p)["gold_status"] == "KNOWN"]
        other = [p for p in ps if g(p)["gold_status"] == "OTHER"]
        ok_var = lambda p: p["status"] == "KNOWN" and norm(p["matched_variety"]) == norm(g(p)["gold_variety"])
        auto = [p for p in ps if p["fusion_action"] == "AUTO_LINK"]
        auto_ok = [p for p in auto if g(p)["gold_status"] == "KNOWN" and ok_var(p)]
        st_ok = sum(1 for p in ps if p["status"] == g(p)["gold_status"])
        res[k] = {
            "n": len(ps), "failed": sum(1 for p in ps if p["status"] == "FAILED"),
            "status_acc": f"{st_ok}/{len(ps)} = {st_ok / len(ps):.2f}",
            "top1": f"{sum(ok_var(p) for p in known)}/{len(known)} = {sum(ok_var(p) for p in known) / len(known):.2f}",
            "known_as_known": f"{sum(p['status'] == 'KNOWN' for p in known)}/{len(known)}",
            "other_recall": f"{sum(p['status'] == 'OTHER' for p in other)}/{len(other)}",
            "other_forced": f"{sum(p['status'] == 'KNOWN' for p in other)}/{len(other)}",
            "uncertain": str(sum(p["status"] == "UNCERTAIN" for p in ps)),
            "auto": f"{len(auto_ok)}/{len(auto)}" + (f" = {len(auto_ok) / len(auto):.2f}" if auto else ""),
            "aksi": dict(collections.Counter(p["fusion_action"] for p in ps)),
            "bagian": dict(collections.Counter(p["identified_part"] for p in ps)),
            "detik": sorted(float(p["detik"]) for p in ps)[len(ps) // 2],
        }
    lab = [("failed", "Gagal (FAILED)"), ("status_acc", "Status benar (KNOWN/OTHER)"), ("known_as_known", "Foto KNOWN diberi status KNOWN"),
           ("top1", "Top-1 varietas pada foto KNOWN"), ("other_recall", "Recall OTHER"), ("other_forced", "OTHER dipaksa ke varietas terdaftar"),
           ("uncertain", "UNCERTAIN"), ("auto", "AUTO_LINK benar / total"), ("aksi", "Tindakan fusi"), ("bagian", "Bagian tanaman diprediksi"),
           ("detik", "Median detik per foto")]
    for key, name in lab:
        out.append(f"| {name} | {res['terlihat'][key]} | {res['tertutup'][key]} |")
    out += ["", "## Per foto", "", "| ID | Gold | Varietas asli | Terlihat: status / varietas / aksi | Tertutup: status / varietas / aksi |", "|---|---|---|---|---|"]
    by = {(p["id"], p["kondisi"]): p for p in pred}
    for i, g in gold.items():
        a, b = by.get((i, "terlihat"), {}), by.get((i, "tertutup"), {})
        f = lambda p: f"{p.get('status', '')} / {p.get('matched_variety') or '-'} / {p.get('fusion_action') or '-'}"
        out.append(f"| {i} | {g['gold_status']} | {g['true_variety']} | {f(a)} | {f(b)} |")
    path = Path(sys.argv[sys.argv.index("--bagian") + 1]) if "--bagian" in sys.argv else D / "terisi_bagian.xlsx"
    extra = []
    if path.exists():
        bag, nama = baca_bagian(path)
        extra = skor_bagian(pred, gold, bag, nama)
    else:
        extra = ["", f"## Bagian tanaman", "", f"Belum dinilai: {path} belum ada (isi lembar_anotasi_bagian.xlsx lalu simpan dengan nama itu)."]
    (D / "hasil_skor.md").write_text("\n".join(out + extra) + "\n", encoding="utf-8")
    print("\n".join(out[:16] + extra))


if __name__ == "__main__":
    main()
