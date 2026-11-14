"""Jalankan ulang foto FAILED pada satu folder ulangan D24, lalu gabungkan (percobaan 2, maks. 3 putaran).
Salinan asli disimpan sebagai hasil_<label>_percobaan1.csv. Argumen run diambil dari meta_<label>.json.
  python ulang_gagal_m2.py /tmp/visi_m2_rep2"""
import csv, json, subprocess, sys
from pathlib import Path

R = Path("C:/Users/Rifqi/AppData/Local/Temp/cvr")
import shutil
B = Path(sys.argv[1])
for putaran in (1, 2, 3):
    sisa = 0
    for hasil in sorted(B.glob("*/hasil_*.csv")):
        if "_percobaan" in hasil.name:
            continue
        label = hasil.stem[len("hasil_"):]
        rows = list(csv.DictReader(open(hasil, encoding="utf-8", newline="")))
        gagal = [r for r in rows if r["status"] == "FAILED"]
        if not gagal:
            continue
        meta = json.loads((hasil.parent / f"meta_{label}.json").read_text(encoding="utf-8"))
        sub = B / "_ulang" / f"{hasil.parent.name}_{label}_p{putaran}"
        sub.mkdir(parents=True, exist_ok=True)
        if not (sub / "foto").exists():
            shutil.copytree(hasil.parent / "foto", sub / "foto")
        if (hasil.parent / "varietas.txt").exists():
            (sub / "varietas.txt").write_text((hasil.parent / "varietas.txt").read_text(encoding="utf-8"), encoding="utf-8")
        with open(sub / "daftar_foto.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["filename", "folder"])
            for r in gagal:
                w.writerow([r["filename"], r["folder"]])
        cmd = [sys.executable, "data_evaluasi/skrip/uji_visi_commons_vps.py", "--dasar", str(sub),
               "--label", label, "--mode", meta["vision_mode"], "--db-dari-meta", meta["db_dari_meta"]]
        cmd += ["--kanonik", meta["kanonik"]] if meta["kanonik"] else ["--varietas", "varietas.txt"]
        subprocess.run(cmd, cwd=R, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        baru = {r["filename"]: r for r in csv.DictReader(open(sub / f"hasil_{label}.csv", encoding="utf-8", newline=""))}
        asli = hasil.parent / f"hasil_{label}_percobaan1.csv"
        if not asli.exists():
            asli.write_bytes(hasil.read_bytes())
        cols = list(rows[0].keys())
        ok = 0
        for i, r in enumerate(rows):
            n = baru.get(r["filename"])
            if r["status"] == "FAILED" and n and n["status"] != "FAILED":
                rows[i] = {k: n.get(k, "") for k in cols}; ok += 1
        with open(hasil, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
        sisa += len(gagal) - ok
        print(f"putaran {putaran} {hasil.parent.name}/{label}: {ok}/{len(gagal)} berhasil", flush=True)
    if sisa == 0:
        break
print("SELESAI sisa_gagal", sisa, flush=True)
