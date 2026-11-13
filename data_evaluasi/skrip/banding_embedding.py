"""Bandingkan model embedding untuk retrieval baris kanonik (Fase 3b) tanpa LLM.

Memakai jalur yang sama dengan pipeline: atribut dibaca dengan parser legacy (runtime_attribute_from_legacy),
query = SourceAttributeProfile.build_query(), dokumen = CanonicalRow.serialize() dari template yang dimuat.
Butir yang selesai lewat exact-name tidak masuk retrieval, jadi dipisah (subset "semantik").
Gold: gold_semua_dataset_final.csv (terverifikasi) dan gold_P01_P02_pvt.csv (P01 terverifikasi, P02 belum), butir ONE_TO_ONE.

  python data_evaluasi/skrip/banding_embedding.py [--model NAMA ...] [--cache DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.schema_matching.exact_match import ExactNameStatus, resolve_exact_name  # noqa: E402
from src.agents.schema_matching.retrieval import SourceAttributeProfile  # noqa: E402
from src.agents.schema_matching.source_parsing import load_row_oriented_columns, load_transposed_rows  # noqa: E402
from src.ingestion.runtime_source import runtime_attribute_from_legacy  # noqa: E402
from src.schema.canonical import CanonicalSchema  # noqa: E402

EV = ROOT / "data_evaluasi"
GOLDS = {"terverifikasi": EV / "gold" / "final" / "gold_semua_dataset_final.csv",
         "pvt_belum_diverifikasi": EV / "gold" / "gold_P01_P02_pvt.csv"}
# (nama, prefiks query, prefiks dokumen, prompt_name query)
MODELS = {
    "paraphrase-multilingual-MiniLM-L12-v2": ("", "", None),
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": ("", "", None),
    "intfloat/multilingual-e5-base": ("query: ", "passage: ", None),
    "intfloat/multilingual-e5-large": ("query: ", "passage: ", None),
    "BAAI/bge-m3": ("", "", None),
    "Qwen/Qwen3-Embedding-0.6B": ("", "", "query"),
    "microsoft/harrier-oss-v1-270m": ("INSTR", "", None),
    "microsoft/harrier-oss-v1-0.6b": ("INSTR", "", None),
}
# Instruksi tugas untuk model instruction-aware (format Qwen3/Harrier). Akhiran "+instr" pada nama model
# memakai instruksi ini menggantikan prompt bawaan.
INSTR = ("Instruct: Given a chili (Capsicum) variety spreadsheet attribute with its name, sample values and data "
         "type, retrieve the canonical plant descriptor row it maps to\nQuery: ")


def spek(nama):
    if nama.endswith("+instr"):
        return nama[: -len("+instr")], INSTR, "", None
    qp, dp, pn = MODELS.get(nama, ("", "", None))
    return nama, (INSTR if qp == "INSTR" else qp), dp, pn


def _tok(t):
    import re
    return re.findall(r"\w+", t.lower())


def bm25_skor(queries, docs, k1=1.2, b=0.75):
    import math
    dt = [_tok(d) for d in docs]
    avg = sum(len(d) for d in dt) / len(dt)
    df = defaultdict(int)
    for d in dt:
        for w in set(d):
            df[w] += 1
    n = len(dt)
    idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
    tf = [defaultdict(int) for _ in dt]
    for i, d in enumerate(dt):
        for w in d:
            tf[i][w] += 1
    S = np.zeros((len(queries), n))
    for qi, q in enumerate(queries):
        for w in set(_tok(q)):
            if w not in idf:
                continue
            for i in range(n):
                f = tf[i].get(w, 0)
                if f:
                    S[qi, i] += idf[w] * f * (k1 + 1) / (f + k1 * (1 - b + b * len(dt[i]) / avg))
    return S


def rrf(*mats, k=60):
    out = np.zeros_like(mats[0])
    for M in mats:
        order = np.argsort(-M, axis=1)
        for i in range(M.shape[0]):
            for r, j in enumerate(order[i]):
                out[i, j] += 1 / (k + r + 1)
    return out
KS = (1, 3, 5, 8)


def _rows(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def butir(schema):
    """Kumpulkan (dataset, display, profil, kunci gold, exact?) untuk butir ONE_TO_ONE."""
    out, tak_cocok = [], []
    for nama_gold, path in GOLDS.items():
        gold = _rows(path)
        per_berkas = defaultdict(list)
        for g in gold:
            per_berkas[(g["source_file_name"], g["source_sheet"], g["source_format"])].append(g)
        for (fn, sheet, fmt), gs in per_berkas.items():
            p = EV / "inputs" / fn
            if fmt == "transposed":
                parsed, _ = load_transposed_rows(p, sheet)
            else:
                parsed = load_row_oriented_columns(p, sheet)
            attrs = {a.display_name.strip(): runtime_attribute_from_legacy(a) for a in parsed}
            for g in gs:
                if g["gold_status"] != "ONE_TO_ONE":
                    continue
                a = attrs.get(g["source_attribute_display"].strip())
                if a is None:
                    tak_cocok.append((g["dataset_id"], g["source_attribute_display"]))
                    continue
                prof = SourceAttributeProfile(
                    attribute_name=a.attribute_name, structural_context=a.structural_context,
                    sample_values=a.sample_values, header_path=a.header_path,
                    source_value_type=a.detected_value_type, source_attribute_id=a.source_attribute_id)
                exact = resolve_exact_name(a.attribute_name, schema).status is ExactNameStatus.MATCH
                out.append({"gold": nama_gold, "dataset": g["dataset_id"], "display": g["source_attribute_display"],
                            "query": prof.build_query(), "key": g["gold_canonical_keys"].strip(), "exact": exact})
    return out, tak_cocok


def muat(nama, cache):
    from sentence_transformers import SentenceTransformer
    kw = {"device": "cpu"}
    if cache:
        kw["cache_folder"] = cache
    return SentenceTransformer(nama, **kw)


def enc(model, teks, prefiks, prompt_name):
    kw = {"normalize_embeddings": True, "batch_size": 16, "convert_to_numpy": True}
    if prompt_name:
        kw["prompt_name"] = prompt_name
    return model.encode([prefiks + t for t in teks], **kw)


def metrik(rank_list):
    n = len(rank_list)
    m = {f"hit@{k}": sum(1 for r in rank_list if r is not None and r < k) / n for k in KS}
    m["mrr"] = sum(1 / (r + 1) for r in rank_list if r is not None) / n
    m["n"] = n
    return m


def boot_ci(a, b, iters=2000, seed=20261105):
    """CI 95% selisih hit@1 dan MRR (b - a), resampling butir berpasangan."""
    rnd = random.Random(seed)
    n = len(a)
    def val(r, k):
        if k == "mrr":
            return 1 / (r + 1)
        return 1.0 if r == 0 else 0.0
    out = {}
    for k in ("h1", "mrr"):
        diffs = []
        for _ in range(iters):
            idx = [rnd.randrange(n) for _ in range(n)]
            diffs.append(sum(val(b[i], k) - val(a[i], k) for i in idx) / n)
        diffs.sort()
        out[k] = (sum(val(b[i], k) - val(a[i], k) for i in range(n)) / n, diffs[int(0.025 * iters)], diffs[int(0.975 * iters)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="*", default=list(MODELS))
    ap.add_argument("--cache", default=None, help="folder cache untuk model yang belum ada")
    ap.add_argument("--hybrid", action="store_true", help="tambahkan varian dense + BM25 (RRF) per model")
    ap.add_argument("--out",default=str(EV / "hasil_eksperimen" / "hasil_retrieval" / "banding_embedding"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    schema = CanonicalSchema.from_template()
    keys = [r.canonical_key for r in schema.rows]
    docs = [r.serialize() for r in schema.rows]
    items, tak_cocok = butir(schema)
    print(f"{len(items)} butir ONE_TO_ONE; tak cocok dengan parser: {len(tak_cocok)} {tak_cocok[:5]}")
    hilang = {i["key"] for i in items} - set(keys)
    if hilang:
        sys.exit(f"Kunci gold tidak ada di template: {sorted(hilang)}")

    ranks, ringkas, per_butir = {}, [], []
    base = args.model[0]
    B = bm25_skor([i["query"] for i in items], docs)
    varian = []
    for nama in args.model:
        if nama == "BM25":
            varian.append(("BM25", B, 0.0, 0.0, 0))
            continue
        asli, qp, dp, pn = spek(nama)
        t0 = time.time()
        model = muat(asli, args.cache)
        t_load = time.time() - t0
        t0 = time.time()
        D = enc(model, docs, dp, None)
        Q = enc(model, [i["query"] for i in items], qp, pn)
        t_enc = time.time() - t0
        S = Q @ D.T
        varian.append((nama, S, t_load, t_enc, int(D.shape[1])))
        if args.hybrid:
            varian.append((nama + " + BM25 (RRF)", rrf(S, B), t_load, t_enc, int(D.shape[1])))
        del model
    for nama, S, t_load, t_enc, dim in varian:
        order = np.argsort(-S, axis=1)
        rk = []
        for i, it in enumerate(items):
            pos = [keys[j] for j in order[i]].index(it["key"])
            rk.append(pos)
            per_butir.append({"model": nama, **{k: it[k] for k in ("gold", "dataset", "display", "key", "exact")},
                              "rank": pos + 1, "top1": keys[order[i][0]], "top1_skor": round(float(S[i, order[i][0]]), 4),
                              "skor_gold": round(float(S[i, keys.index(it["key"])]), 4)})
        ranks[nama] = rk
        for subset in ("terverifikasi", "pvt_belum_diverifikasi"):
            for jenis in ("semua", "semantik"):
                sel = [r for r, it in zip(rk, items) if it["gold"] == subset and (jenis == "semua" or not it["exact"])]
                ringkas.append({"model": nama, "gold": subset, "subset": jenis, **metrik(sel),
                                "detik_muat": round(t_load, 1), "detik_encode": round(t_enc, 1),
                                "dimensi": dim})
        print(nama, [(r["gold"], r["subset"], round(r["hit@1"], 3), round(r["hit@8"], 3), round(r["mrr"], 3))
                     for r in ringkas if r["model"] == nama])

    banding = []
    for nama in [v[0] for v in varian if v[0] != base]:
        for subset in ("terverifikasi", "pvt_belum_diverifikasi"):
            idx = [i for i, it in enumerate(items) if it["gold"] == subset and not it["exact"]]
            ci = boot_ci([ranks[base][i] for i in idx], [ranks[nama][i] for i in idx])
            banding.append({"model": nama, "vs": base, "gold": subset, "subset": "semantik",
                            "delta_hit1": ci["h1"], "delta_mrr": ci["mrr"]})

    with open(out / "ringkasan.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ringkas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(ringkas)
    with open(out / "per_butir.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_butir[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(per_butir)
    (out / "banding_vs_minilm.json").write_text(json.dumps(banding, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({
        "template_hash": schema.template_hash, "n_baris_kanonik": len(schema.rows), "n_butir": len(items),
        "tak_cocok": tak_cocok, "models": args.model, "k": KS,
        "catatan": "Retrieval murni (cosine, tanpa Chroma, tanpa LLM). Subset semantik = butir yang tidak selesai lewat exact-name."},
        indent=1, ensure_ascii=False), encoding="utf-8")
    print("tulis", out)


if __name__ == "__main__":
    main()
