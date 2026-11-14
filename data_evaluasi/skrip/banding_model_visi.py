"""Bandingkan model visi pada harness foto D24 yang sama (D26).

Baseline = Gemini 3.8 Flash high, beberapa ulangan (rerata ditampilkan, rentang di kolom terpisah). Kandidat = satu
atau lebih folder skor (keluaran skor.sh) per model.

  python skrip/banding_model_visi.py --baseline skor1 skor2 skor3 \
      --model "Claude Opus 5.5=skorA" "GPT-6 Astra=skorB" --out <folder>
"""
import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rekap_ulangan_m2 import fmt, metrik_bp, metrik_foto, muat, muat_bp  # noqa: E402


def semua_metrik(d):
    return {**metrik_bp(muat_bp(Path(d) / "berpasangan")), **metrik_foto(muat(d))}


def rerata(vals):
    if isinstance(vals[0], str):
        return vals[0] if len(set(vals)) == 1 else ", ".join(vals)
    m = st.mean(vals)
    d = 3 if isinstance(vals[0], float) else 2
    return f"{m:.{d}f}".replace(".", ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", nargs="+", required=True)
    ap.add_argument("--baseline-nama", default="Gemini 3.8 Flash high")
    ap.add_argument("--model", nargs="+", required=True, help="Nama=folder_skor (beberapa folder dipisah titik koma)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    base = [semua_metrik(d) for d in a.baseline]
    kand = []
    for spec in a.model:
        nama, dirs = spec.split("=", 1)
        kand.append((nama, [semua_metrik(d) for d in dirs.split(";")]))
    n_b = len(base)
    head = [f"{a.baseline_nama} (rerata {n_b} ulangan)", f"{a.baseline_nama} rentang"] + \
        [f"{n} ({len(ms)} ulangan)" if len(ms) > 1 else n for n, ms in kand]
    lines = ["# Perbandingan model visi (D26)", "",
             "Harness, input, registri, deskripsi varietas, kanonik, varietas DB, mode two_stage, dan skrip skor sama; yang "
             "berbeda hanya model visi (`CABAI_KMS_EVAL_VISION_MODEL`). Model teks tetap Gemini 3.8 Flash medium.", "",
             "| Metrik | " + " | ".join(head) + " |", "|---|" + "---|" * len(head)]
    out = {"baseline": {"nama": a.baseline_nama, "folder": a.baseline}, "kandidat": [], "metrik": {}}
    for k in base[0]:
        bv = [m[k] for m in base]
        rng = "-" if isinstance(bv[0], str) else f"{fmt(min(bv))}-{fmt(max(bv))}"
        cells = [rerata(bv), rng] + [rerata([m[k] for m in ms]) for _, ms in kand]
        lines.append(f"| {k} | " + " | ".join(cells) + " |")
        out["metrik"][k] = {"baseline": bv, **{n: [m[k] for m in ms] for n, ms in kand}}
    out["kandidat"] = [{"nama": n, "folder": spec.split("=", 1)[1]} for (n, _), spec in zip(kand, a.model)]
    o = Path(a.out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "banding_model.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (o / "banding_model.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
