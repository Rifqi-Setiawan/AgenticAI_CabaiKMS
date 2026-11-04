"""Buat gambar data paper (pgfplots/TikZ) dari hasil_eksperimen/analisis_paper.json.

Angka tidak diketik tangan: semua diambil dari JSON hasil skrip/analisis_paper.py.
Keluaran: paper_figs/fig_mapping_f1.tex dan paper_figs/fig_photo_routing.tex (di-\\input dari LaTeX).
Jalankan dari folder data_evaluasi:  ..\\.venv\\Scripts\\python.exe skrip\\buat_gambar_paper.py
"""
import json
from pathlib import Path

J = json.loads(Path("hasil_eksperimen/analisis_paper.json").read_text(encoding="utf-8"))
# Revisi 3 Nov 2026 (masukan dosen poin 2): Fig. 2 memakai CI bootstrap per workbook dari analisis_revisi_dosen.py.
_rev = Path("hasil_eksperimen/analisis_revisi_dosen.json")
MAPPING = json.loads(_rev.read_text(encoding="utf-8"))["mapping_cluster"] if _rev.exists() else J["mapping"]
OUT = Path("paper_figs")
OUT.mkdir(exist_ok=True)
COL = {"S1": "c1", "S2": "c2", "S2T": "c3", "S4": "c4"}
NAME = {"S1": "S1 exact-name", "S2": "S2 retrieval top-1", "S2T": r"S2+$\tau$ retrieval w/ threshold", "S4": "S4 full pipeline"}
HEAD = r"""% Dibuat otomatis oleh data_evaluasi/skrip/buat_gambar_paper.py — jangan diedit tangan.
\definecolor{c1}{HTML}{999999}\definecolor{c2}{HTML}{E69F00}\definecolor{c3}{HTML}{56B4E9}\definecolor{c4}{HTML}{009E73}
\definecolor{c5}{HTML}{D55E00}\definecolor{c6}{HTML}{CC79A7}
"""


def fig_mapping():
    groups = [("held-out", "All held-out"), ("held-out semantik", "Semantic held-out"), ("dev", "Dev (all)")]
    plots = []
    for v in ("S1", "S2", "S2T", "S4"):
        coords = []
        for key, lab in groups:
            m = MAPPING[key][v]
            coords.append(f"({{{lab}}},{m['f1']:.3f}) += (0,{m['f1_hi'] - m['f1']:.3f}) -= (0,{m['f1'] - m['f1_lo']:.3f})")
        plots.append(
            rf"\addplot+[fill={COL[v]},draw=black!70,error bars/.cd,y dir=both,y explicit,error bar style={{black!80}}] coordinates {{{' '.join(coords)}}};"
            + "\n" + rf"\addlegendentry{{{NAME[v]}}}")
    sym = ",".join("{" + lab + "}" for _, lab in groups)
    body = rf"""\begin{{tikzpicture}}
\begin{{axis}}[ybar, bar width=6.5pt, width=0.97\columnwidth, height=4.6cm, ymin=0, ymax=1.08,
  ylabel={{Mapping F1}}, symbolic x coords={{{sym}}}, xtick=data, enlarge x limits=0.22,
  ytick={{0,0.2,0.4,0.6,0.8,1.0}}, ymajorgrids, grid style={{dashed,gray!30}},
  tick label style={{font=\scriptsize}}, label style={{font=\footnotesize}},
  legend style={{font=\scriptsize, at={{(0.5,1.03)}}, anchor=south, legend columns=2, draw=none, /tikz/every even column/.append style={{column sep=4pt}}}},
  legend cell align=left]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
"""
    (OUT / "fig_mapping_f1.tex").write_text(HEAD + body, encoding="utf-8")


def fig_photo():
    a = J["photo"]["label_sumber"]["auto_link"]
    conds = [("INFORMATIF", "Informative"), ("NETRAL", "Neutral"), ("MENYESATKAN", "Misleading")]
    series = [("Auto-link, correct", "c4", lambda x: x["correct"]),
              ("Auto-link, wrong", "c5", lambda x: x["auto_link"] - x["correct"]),
              ("Human review", "c3", lambda x: x["review"]),
              ("New-variety candidate", "c2", lambda x: x["candidate"])]
    plots = []
    for name, col, fn in series:
        coords = " ".join(f"({fn(a[c]) / a[c]['n_photos'] * 100:.1f},{{{lab}}})" for c, lab in conds)
        plots.append(rf"\addplot+[fill={col},draw=black!70] coordinates {{{coords}}};" + "\n" + rf"\addlegendentry{{{name}}}")
    sym = ",".join("{" + f"{lab} (n={a[c]['n_photos']})" + "}" for c, lab in conds)
    # label y memakai n foto; koordinat harus sama persis dengan simbol
    plots = [p.replace("{Informative}", "{Informative (n=%d)}" % a["INFORMATIF"]["n_photos"])
              .replace("{Neutral}", "{Neutral (n=%d)}" % a["NETRAL"]["n_photos"])
              .replace("{Misleading}", "{Misleading (n=%d)}" % a["MENYESATKAN"]["n_photos"]) for p in plots]
    body = rf"""\begin{{tikzpicture}}
\begin{{axis}}[xbar stacked, bar width=9pt, width=0.86\columnwidth, height=3.9cm, xmin=0, xmax=100,
  xlabel={{Share of photos (\%)}}, symbolic y coords={{{sym}}}, ytick=data, y dir=reverse,
  enlarge y limits=0.28, xmajorgrids, grid style={{dashed,gray!30}},
  tick label style={{font=\scriptsize}}, label style={{font=\footnotesize}},
  legend style={{font=\scriptsize, at={{(0.5,1.04)}}, anchor=south, legend columns=2, draw=none, /tikz/every even column/.append style={{column sep=4pt}}}},
  legend cell align=left]
{chr(10).join(plots)}
\end{{axis}}
\end{{tikzpicture}}
"""
    (OUT / "fig_photo_routing.tex").write_text(HEAD + body, encoding="utf-8")


if __name__ == "__main__":
    fig_mapping()
    fig_photo()
    print("ok:", [p.name for p in OUT.iterdir()])
