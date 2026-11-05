"""Ekstrak deskripsi varietas dari PDF Berita Resmi PVT (lapisan teks, pdftotext -layout).

Dipakai oleh buat_dataset_pvt.py. Label dan nilai disalin apa adanya; yang dibuang hanya
footer dokumen elektronik, baris kosong, dan entri tanpa nilai (judul bagian seperti "Batang : ,").
Dokumen memakai dua tata letak:
  - baris: satu atribut per baris, "Label   : nilai" (kadang ": :"), baris lanjutan menjorok;
  - paragraf: semua atribut dalam satu paragraf, dipisah ", " (mis. Lemarsi, Tabia Sala 1 IPB).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

FOOTER = ("Dokumen ini merupakan", "tangan karena dihasilkan", "Terintegrasi (SIPERINTIS)", "tertera dalam dokumen")
# Nama orang tidak disalin ke spreadsheet; tidak dibutuhkan untuk uji pemetaan karakter.
PERSON_LABELS = {"Pemohon", "Pemulia", "Peneliti", "Pemulia Tanaman", "Pendeskripsi Varietas", "Pemilik Varietas"}
HEADER_KEYS = {
    "No. Publikasi": "no_publikasi", "Nama Umum": "nama_umum", "Nama Genus, Spesies, Author(s)": "spesies",
    "Nama Varietas": "varietas", "No. Pendaftaran": "no_pendaftaran", "Tanggal Pendaftaran": "tanggal_pendaftaran",
    "Sebaran Geografis": "sebaran_geografis", "Silsilah atau Asal Usul": "silsilah_header",
}


def pdf_text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True,
                          text=True).stdout


def _clean_lines(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        if not ln.strip() or any(f in ln for f in FOOTER):
            continue
        out.append(ln.rstrip())
    return out


def _join(a: str, b: str) -> str:
    a, b = a.rstrip(), b.strip()
    if not a:
        return b
    # Kata/angka yang terputus tanda hubung di akhir baris (mis. "87-" + "137").
    if a.endswith(("-", "–")):
        return a + b
    return a + " " + b


def _strip_value(v: str) -> str:
    v = re.sub(r"^:\s*", "", v.strip())  # format ": :"
    v = re.sub(r"\s+", " ", v).strip()
    return v.rstrip(".").strip() if v.endswith(".") and not re.search(r"\d\.$", v) else v


def parse_header(lines: list[str]) -> dict:
    meta = {}
    for ln in lines:
        m = re.match(r"^\s*(No\. Publikasi)\s*:\s*(.+)$", ln)
        if m:
            meta["no_publikasi"] = m.group(2).strip()
            continue
        m = re.match(r"^(\S.*?)\s{2,}:\s*(.*)$", ln)
        if m and m.group(1).strip() in HEADER_KEYS:
            meta[HEADER_KEYS[m.group(1).strip()]] = m.group(2).strip()
    m = re.search(r"Pendaftaran Varietas (Lokal|Hasil Pemuliaan)", "\n".join(lines[:5]))
    meta["jalur"] = "lokal" if m and m.group(1) == "Lokal" else "hasil_pemuliaan"
    return meta


def _description_block(lines: list[str]) -> list[str]:
    start = next(i for i, ln in enumerate(lines) if re.match(r"^\s*Deskripsi Varietas\s*:", ln))
    end = next(i for i, ln in enumerate(lines) if ln.strip().startswith("Foto yang Disebut"))
    return lines[start + 1:end]


def _parse_line_layout(block: list[str]) -> list[tuple[str, str]]:
    items: list[list[str]] = []
    for ln in block:
        m = re.match(r"^(\S.*?)\s+:\s?(.*)$", ln)
        if m and not ln.startswith(" "):
            items.append([m.group(1).strip(), m.group(2)])
        elif items and not ln.startswith(" "):
            # Label terbungkus ke baris berikutnya di kolom 0, mis. "...dan ruas" + "yang memendek pada tanaman".
            items[-1][0] = _join(items[-1][0], ln)
        elif items:
            items[-1][1] = _join(items[-1][1], ln)
    return [(lab, _strip_value(val)) for lab, val in items]


def _parse_paragraph(block: list[str]) -> list[tuple[str, str]]:
    text = ""
    for ln in block:
        text = _join(text, ln)
    parts = re.split(r"\s:\s?|:\s:\s", text)
    # parts[0] = label pertama; tiap bagian berikutnya = "nilai, Label berikut" (kecuali yang terakhir).
    pairs = []
    label = parts[0].strip()
    for seg in parts[1:-1]:
        idx = seg.rfind(", ")
        if idx < 0:  # nilai kosong lalu label langsung, mis. "Tanaman: : , Orientasi"
            value, nxt = "", seg
        else:
            value, nxt = seg[:idx], seg[idx + 2:]
        pairs.append((label, _strip_value(value.strip(" ,"))))
        label = nxt.strip()
    pairs.append((label, _strip_value(parts[-1].strip(" ,"))))
    return pairs


def parse_pdf(pdf: Path) -> dict:
    lines = _clean_lines(pdf_text(pdf))
    meta = parse_header(lines)
    block = _description_block(lines)
    paragraph = any(len(re.findall(r"\s:\s", ln)) >= 2 for ln in block)
    raw = _parse_paragraph(block) if paragraph else _parse_line_layout(block)
    attrs, seen, dropped = [], {}, []
    parent = None
    for lab, val in raw:
        lab = re.sub(r"\s+", " ", lab).rstrip(":").strip()
        lab = lab.replace("Ha?1", "Ha-1")  # superskrip "⁻¹" terbaca "?" oleh pdftotext
        if not val or val in {":", ","}:
            dropped.append(lab)  # judul bagian ("Batang", "Daun:") atau sel kosong
            parent = lab
            continue
        if lab.startswith("-"):
            # Sub-butir di bawah judul tanpa nilai, mis. "Warna bunga :" lalu "- Kelopak Bunga : Hijau".
            sub = lab.lstrip("- ").strip()
            lab = f"{parent}: {sub}" if parent else sub
        else:
            parent = None
        if lab in PERSON_LABELS:
            continue
        if lab in seen:  # label sama dua kali dalam satu dokumen (mis. Gemoy IPB "Warna tangkai sari")
            seen[lab] += 1
            lab = f"{lab} ({seen[lab]})"
        else:
            seen[lab] = 1
        attrs.append((lab, val))
    return {"meta": meta, "layout": "paragraf" if paragraph else "baris", "attrs": attrs,
            "dropped_empty": dropped, "pdf": pdf.name}
