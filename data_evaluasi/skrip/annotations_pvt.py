"""Aturan anotasi pemetaan atribut untuk dataset PVT (P01, P02). Usulan awal, belum diverifikasi.

Urutan: (1) aturan lama di annotations.py yang sudah diverifikasi peneliti (persis, lalu tanpa satuan dan
tanpa membedakan huruf besar-kecil); (2) aturan baru PVT di bawah (regex, pertama yang cocok menang).
Aturan baru selalu ditandai rule_source="pvt_baru" agar peninjau bisa memeriksanya lebih dulu.
"""
from __future__ import annotations

import re

import annotations as BASE
from annotations import ADMIN, ANCHOR, FRUITLEN, FRUITPOS, NOCANON, STAMEN, STIGMA, A, N, O

FRUITSTALK = A("panjang_tangkai_buah_muda|panjang_tangkai_buah_masak",
               "Panjang tangkai buah tanpa tahap kematangan; kanonik memisahkan muda dan masak.", "M")
CALYX_FRUIT = A("bentuk_kelopak_buah_muda|kedudukan_kelopak_bunga",
                "Aspek kelopak pada buah (menutup/tidak menutup pangkal buah); bisa dibaca sebagai bentuk kelopak "
                "buah atau kedudukan kelopak.", "L")
AGRO = N("Atribut agronomi/hasil/penyimpanan/fase; tidak ada kanonik sepadan.")
UPOV = N("Karakter UPOV/PVT tanpa padanan pada 60 baris kanonik.", "H")

# (pola regex pada label huruf kecil tanpa satuan, aturan). Pola diuji berurutan.
PVT_RULES: list[tuple[str, tuple]] = [
    # --- identitas / administrasi
    (r"^nama umum$", N("Nama umum jenis cabai; identitas, bukan karakteristik.", "M")),
    (r"^spesies$", N("Nama spesies; identitas, bukan karakteristik.", "M")),
    (r"^sebaran geografis$", O("lokasi", "M", "Sebaran geografis varietas lokal (kecamatan/kabupaten) setara Lokasi.")),
    (r"^golongan( varietas)?$", ADMIN),
    (r"^keunggulan", N("Teks klaim keunggulan; bukan karakteristik kanonik.")),
    (r"^penciri utama$", N("Teks ringkasan penciri varietas; bukan satu karakteristik kanonik.")),
    # --- habitus / batang
    (r"^(karakter pertanaman|orientasi( tanaman|/bentuk tanaman)?)$",
     O("habitus", "M", "Orientasi/tipe tumbuh tanaman (tegak, semi tegak) setara habitus.")),
    (r"^bulu pada batang$", O("batang", "H", "Kanonik 'batang' berisi berbulu/gundul.")),
    (r"^bulu pada buku$", O("batang", "M", "Bulu pada buku batang; kanonik 'batang' berisi berbulu/gundul.")),
    (r"^tekstur kulit batang$", O("batang", "L", "Tekstur permukaan batang; kanonik 'batang' berisi permukaan.")),
    (r"^warna (batang|cabang|ruas|node)", N("Warna batang/cabang tidak ada pada kanonik ('batang' = permukaan).", "M")),
    (r"(antosi|anthosi)", UPOV),  # termasuk salah ketik "antosinin"
    (r"^(panjang batang|lebar kanopi|lebar tajuk|diameter tajuk|letak cabang|tinggi batang hingga|pola tumbuh|"
     r"bentuk sebaran batang|panjang ruas|pemendekan|jumlah ruas|diameter batang)", NOCANON),
    # --- daun
    (r"^panjang helai daun$", O("panjang_daun")),
    (r"^panjang tangkai daun$", O("panjang_tangkai_daun")),
    (r"^lebar helai daun$", O("lebar_daun")),
    (r"^warna daun (atas|permukaan atas|bagian atas)$",
     O("warna_daun", "M", "Warna permukaan atas daun; kanonik hanya satu warna daun.")),
    (r"^warna daun (bawah|permukaan bawah|bagian bawah)$",
     N("Warna permukaan bawah daun; kanonik 'warna daun' diisi warna permukaan atas.", "M")),
    (r"^intensitas warna hijau daun$", O("warna_daun", "L", "Nilai pada sumber berupa grup warna RHS.")),
    (r"^intensitas warna hijau$", N("Intensitas warna (lemah/sedang/gelap), bukan warna daun.", "M")),
    (r"^warna tulang daun$", NOCANON),
    (r"^warna tangkai daun$", A("warna_pangkal_tangkai_daun_bag_atas|warna_pangkal_tangkai_daun_bag_bawah",
                                "Warna tangkai daun tanpa bagian pangkal atas/bawah.", "L")),
    (r"^(bentuk )?ujung daun$", O("bentuk_ujung_daun")),
    (r"^pangkal daun$", O("bentuk_pangkal_daun")),
    (r"^tepi daun$", O("tepi_daun")),
    (r"(undulasi|gelombang).*tepi daun", O("tepi_daun", "M", "Undulasi tepi daun dicatat pada baris tepi daun.")),
    (r"^tingkat bergelombang$", O("tepi_daun", "L", "Tercantum di bagian daun; diduga undulasi tepi daun.")),
    (r"^permukaan daun", O("tekstur_daun", "M", "Permukaan daun (rata) setara tekstur daun.")),
    (r"^lepuhan daun$", O("tekstur_daun", "L", "Lepuhan (blistering) adalah sifat permukaan daun.")),
    (r"^(kilapan daun|lapisan lilin|kepadatan daun|arah daun)$", UPOV),
    (r"potongan mel[i]+ntang daun", N("Profil penampang daun; tidak ada kanonik sepadan.", "M")),
    # --- bunga
    (r"^bentuk mahkota bunga$", O("bentuk_bunga", "M", "Bentuk mahkota menentukan bentuk bunga (bintang).")),
    (r"^(bentuk petal|bentuk ujung helaian mahkota)", UPOV),
    (r"^jumlah mahkota bunga$", O("jumlah_mahkota_bunga")),
    (r"^jumlah bunga per nodus$", O("jumlah_gagang_bunga_ruas", "M", "Jumlah bunga per buku setara gagang per ruas.")),
    (r"^jumlah benangsari", NOCANON),
    (r"^(warna bunga: )?mahkota bunga$|^warna mahkota bunga \(petal\)$", O("warna_mahkota")),
    (r"^(warna|pewarnaan) sekunder", NOCANON),
    (r"^warna tangkai bunga$", O("warna_gagang_bunga", "M", "Tangkai bunga (pedicel) = gagang bunga.")),
    (r"^(keberadaan pigmen di tangkai bunga|tepi tangkai bunga)$", UPOV),
    (r"^orientasi pedunkel$", A("posisi_bunga|posisi_buah_masak",
                                "Orientasi tangkai (pedunkel) tanpa menyebut bunga atau buah.", "L")),
    (r"^(posisi bunga terhadap batang|orientasi bunga|posisi tangkai bunga|orientasi/ ?letak tangkai bunga|"
     r"orientasi pedunkel (pada )?bunga)$", O("posisi_bunga", "M", "Orientasi bunga/tangkai bunga = posisi bunga.")),
    (r"^(sudut antara bunga|jadwal bunga|lama bunga|mandul jantan|pemunculan stigma|posisi putik)", UPOV),
    (r"^warna bunga: kelopak bunga$|^warna kelopak$", O("warna_kelopak_bunga", "M", "Kelopak bunga (konteks bunga).")),
    (r"^warna bunga: kepala putik$|^warna kepala putik$", STIGMA),
    (r"^warna tangkai kepala putik$", O("warna_tangkai_putik", "M", "Tangkai kepala putik = style = tangkai putik.")),
    (r"^warna antera sebelum pecah$", O("warna_kepala_sari", "M", "Antera = kepala sari; dipakai warna sebelum pecah.")),
    (r"^warna antera setelah pecah$", N("Warna antera setelah pecah; kanonik diisi warna sebelum pecah.", "M")),
    (r"^warna (antera|anther|kepala sari|antera/kepala sari)$", O("warna_kepala_sari", "M", "Antera = kepala sari.")),
    (r"^warna (filamen|filament|bunga: tangkai sari)$", O("warna_tangkai_sari", "M", "Filamen = tangkai sari.")),
    (r"^warna tangkai sari \(2\)$", O("warna_tangkai_sari", "L", "Label muncul dua kali di dokumen sumber (Gemoy IPB).")),
    (r"^warna tangkai sari$", O("warna_tangkai_sari")),
    (r"^warna bunga: benang sari$", STAMEN),
    (r"^warna serbuk sari$", N("Warna serbuk sari (pollen), bukan kepala sari.", "M")),
    (r"^panjang benang sari dan filament", O("panjang_benangsari", "M")),
    # --- buah
    (r"^panjang buah$", FRUITLEN),
    (r"^panjang tangkai buah$", FRUITSTALK),
    (r"^(diameter|lebar buah|tebal buah|diameter buah lebar)", N("Diameter/lebar buah tidak sama dengan keliling kanonik.", "M")),
    (r"^posisi buah( terhadap batang)?$", FRUITPOS),
    (r"^posisi buah muda$", O("posisi_buah_muda")),
    (r"^warna (buah (matang|tua|tua/ ?matang|matang buah)|kulit buah tua)$", O("warna_buah_masak", "H", "Buah tua/matang = masak.")),
    (r"^warna (buah sebelum matang|kulit buah muda)$", O("warna_buah_muda")),
    (r"^warna buah (antara|intermedi)", N("Warna buah tahap intermediate; kanonik hanya muda dan masak.", "M")),
    (r"^warna daging buah", N("Warna daging buah, bukan warna kulit buah.", "M")),
    (r"^intensitas warna buah", UPOV),
    (r"^warna (tangkai|tangkai buah|kelopak buah)", NOCANON),
    (r"^(ujung buah|penampilan ujung buah)$", O("bentuk_ujung_buah")),
    (r"^(bentuk )?pangkal buah$|^leher pangkal buah$", NOCANON),
    (r"^bentuk buah \(2\)$", O("bentuk_buah", "L", "Label muncul dua kali di dokumen sumber.")),
    (r"^(bentuk potongan (buah )?membujur( buah)?|penampang membujur buah)$",
     O("bentuk_buah", "M", "Bentuk potongan membujur (UPOV) = bentuk buah.")),
    (r"(potongan|penampang) melintang", N("Bentuk penampang melintang buah; tidak ada kanonik sepadan.", "M")),
    (r"^(kelopak buah|aspek kelopak buah|tipe kelopak buah|kelopak buah \(calyx\))$", CALYX_FRUIT),
    (r"^tepi kaliks$", UPOV),
    (r"^(sinuasi|tekstur permukaan|kilapan buah|rongga|kedalaman|jumlah lokul|ketebalan|tebal (daging|kulit)|"
     r"daging buah tebal|puntiran|rasio|capsaisin|capcaisin|intensitas capsaisin|panjang plasenta|tingkat|"
     r"kemudahan|lekuk|garis melintang|keberadaan titik|fruit set|jumlah buah per dompol|penggolongan|"
     r"penampakan kerutan)", UPOV),
    # --- biji
    (r"^jumlah biji per buah$", O("jumlah_biji_buah_masak", "M", "Biji dihitung dari buah masak; tahap tidak disebut.")),
    (r"^warna biji kupas kering$", O("warna_biji", "M")),
    (r"^(panjang|lebar|tebal|ukuran|permukaan) biji", NOCANON),
    # --- agronomi / hasil
    (r"^(produksi|potensi hasil|jumlah buah|jumlah populasi|kadar kepedasan|kandungan|waktu mulai|"
     r"panjang masa|lama|priode|periode|rasa)", AGRO),
]

DATASET_OVERRIDES = {
    # DH 3: "Kelopak" bernilai "Menutup" (aspek kelopak buah), bukan warna seperti pada aturan lama.
    "Kelopak": CALYX_FRUIT,
}

UNIT = re.compile(r"\s*\((cm|mm|g|gr|gram|kg|hst|HST|hari|buah|helai|butir|derajat|minggu|bulan|ppm|SHU|ton/ha|"
                  r"Ton Ha-1|ton|tanaman|cm²)\)\s*$")


def _strip_units(label: str) -> str:
    prev = None
    while prev != label:
        prev, label = label, UNIT.sub("", label).strip()
    return re.sub(r"(\S)\((cm|mm)\)$", r"\1", label).strip()


def annotate(display: str):
    """Kembalikan (status, keys, ambiguous, note, confidence, rule_source) atau None."""
    if display in DATASET_OVERRIDES:
        return (*DATASET_OVERRIDES[display], "pvt_baru")
    base = BASE.annotate("pvt", display)
    if base:
        return (*base, "lama_terverifikasi")
    bare = _strip_units(display)
    lower_global = {k.lower(): v for k, v in BASE.GLOBAL.items()}
    if bare.lower() in lower_global:
        return (*lower_global[bare.lower()], "lama_terverifikasi")
    base = BASE.annotate("pvt", bare[:1].upper() + bare[1:])
    if base:
        return (*base, "lama_terverifikasi")
    for pat, rule in PVT_RULES:
        if re.search(pat, bare.lower()):
            return (*rule, "pvt_baru")
    return None
