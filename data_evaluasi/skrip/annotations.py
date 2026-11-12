"""Annotation rules (initial proposal) keyed by source attribute display label.

Each rule: (status, keys, ambiguous_keys, note, confidence). Statuses follow annotation_guidelines_v1.
Global rules apply to every dataset; DATASET_OVERRIDES win over global rules.
"""
import re


def O(key, c="H", note=""):
    return ("ONE_TO_ONE", key, "", note, c)


def N(note="", c="H"):
    return ("NO_MATCH", "", "", note, c)


def A(keys, note="", c="M"):
    return ("AMBIGUOUS", "", keys, note, c)


def C(keys, note="", c="H"):
    return ("COMPOSITE", keys, "", note, c)


ANCHOR = N("Kolom anchor/identitas varietas; bukan karakteristik kanonik.")
ADMIN = N("Metadata administratif/penetapan varietas; di luar skema karakteristik kanonik.")
NOCANON = N("Atribut valid tetapi tidak ada karakteristik kanonik yang sepadan.")
STIGMA = N("Kepala putik (stigma) berbeda dari tangkai putik (style) pada kanonik; tidak dipaksakan.", "M")
STAMEN = A("warna_tangkai_sari|warna_kepala_sari",
           "Benang sari (stamen) mencakup tangkai sari dan kepala sari; bagian yang diwarnai tidak disebut.", "M")
FRUITLEN = A("panjang_buah_muda|panjang_buah_masak",
             "Tahap kematangan buah tidak disebut sumber; kanonik memisahkan buah muda dan masak.", "M")
FRUITPOS = A("posisi_buah_muda|posisi_buah_masak", "Tahap buah tidak disebut.", "M")

GLOBAL = {
    # --- identity / admin
    "Varietas Cabai": ANCHOR, "Varietas": ANCHOR, "Jenis Cabai": ANCHOR, "Variety": ANCHOR,
    "Genotype name": ANCHOR,
    "Species": N("Label spesies; bukan karakteristik kanonik (varietas/spesies adalah kunci identitas).", "M"),
    "Kode Sampel": N("Kode sampel/baris; bukan karakteristik."), "Sample code": N("Kode sampel/baris; bukan karakteristik."),
    "No": N("Nomor urut lokasi; penanda baris, bukan karakteristik.", "M"),
    "Asal": ADMIN, "Silsilah": ADMIN, "Golongan varietas": ADMIN, "Pemohon": ADMIN, "Pemulia": ADMIN, "Peneliti": ADMIN,
    "Penciri utama": N("Teks ringkasan penciri varietas; bukan satu karakteristik kanonik."),
    "Keunggulan varietas": N("Teks klaim keunggulan; bukan karakteristik kanonik."),
    # --- vegetative
    "Plant growth habit": O("habitus"), "Habitus tanaman": O("habitus"), "Bentuk habitus tanaman": O("habitus"),
    "Tipe tumbuh tanaman": O("habitus", "M", "Tipe tumbuh (tegak) setara habitus."),
    "Bentuk pertumbuhan tanaman": O("habitus"), "Overall plant growth form": O("habitus"), "Bentuk tumbuh": O("habitus"),
    "Vegetatif / Bentuk tumbuh": O("habitus"),
    "Plant height": O("tinggi_tanaman"), "Tinggi tanaman": O("tinggi_tanaman"), "Tinggi tanaman (cm)": O("tinggi_tanaman"),
    "Tinggi keseluruhan tanaman": O("tinggi_tanaman"), "Vertical size at maturity": O("tinggi_tanaman"),
    "Vegetatif / Ukuran tinggi": O("tinggi_tanaman"), "Ukuran tinggi": O("tinggi_tanaman"),
    "Siklus hidup tanaman": O("umur"), "Productive plant lifespan": O("umur"), "Vegetatif / Lama hidup": O("umur"),
    "Kesesuaian lingkungan tumbuh": O("adaptasi_ekologi"), "Suitable growing environment": O("adaptasi_ekologi"),
    "Wilayah adaptasi": O("adaptasi_ekologi", "M", "Wilayah adaptasi (dataran/musim) setara adaptasi ekologi."),
    "Permukaan batang": O("batang"), "Hair coverage on the stem": O("batang"), "Vegetatif / Permukaan batang": O("batang"),
    "Bentuk penampang batang": N("Bentuk penampang batang; kanonik 'batang' berisi permukaan (berbulu/gundul).", "M"),
    "Bentuk batang": N("Bentuk batang; kanonik 'batang' berisi permukaan (berbulu/gundul).", "M"),
    "Diameter batang": NOCANON, "Diameter batang (cm)": NOCANON, "Stem diameter": NOCANON, "Stem length": NOCANON,
    "Warna batang": N("Warna batang tidak ada pada kanonik ('batang' = permukaan).", "M"),
    "Intensitas pewarnaan antosianin pada buku": NOCANON, "Pemendekan ruas-internode": NOCANON,
    "Panjang dikotomus": NOCANON, "Tinggi dikotomus": NOCANON, "Panjang ruas batang": NOCANON, "Lebar tajuk": NOCANON,
    "Crown diameter": NOCANON, "Branching density": NOCANON,
    # --- leaf
    "Leaf shape": O("bentuk_daun"), "Bentuk daun": O("bentuk_daun"),
    "Tekstur permukaan daun": O("tekstur_daun"), "Leaf surface feel": O("tekstur_daun"), "Daun / Tekstur": O("tekstur_daun"),
    "Warna daun": O("warna_daun"), "Warna dominan daun": O("warna_daun"), "Dominant foliage shade": O("warna_daun"),
    "Daun / Warna": O("warna_daun"), "Corak warna daun": O("warna_daun"),
    "Panjang daun": O("panjang_daun"), "Ukuran panjang helai daun": O("panjang_daun"), "Leaf blade longitudinal size": O("panjang_daun"),
    "Daun / Panjang": O("panjang_daun"), "Panjang helai": O("panjang_daun"), "Ukuran daun Panjang": O("panjang_daun"),
    "Lebar daun": O("lebar_daun"), "Lebar helai daun": O("lebar_daun"), "Leaf blade crosswise span": O("lebar_daun"),
    "Daun / Lebar": O("lebar_daun"), "Ukuran daun Lebar": O("lebar_daun"),
    "Ukuran daun": C("panjang_daun|lebar_daun", "Satu sel memuat panjang dan lebar daun."),
    "Leaf-tip profile": O("bentuk_ujung_daun"), "Bentuk pangkal daun": O("bentuk_pangkal_daun"),
    "Leaf arrangement along the stem": O("kedudukan_daun"),
    "Profil potongan melintang daun": N("Profil penampang daun; tidak ada kanonik sepadan.", "M"),
    "Profil potongan melintang": N("Profil penampang daun; tidak ada kanonik sepadan.", "M"),
    # --- flower
    "Bentuk bunga": O("bentuk_bunga"),
    "Warna mahkota bunga": O("warna_mahkota"), "Warna mahkota": O("warna_mahkota"), "Corolla colour": O("warna_mahkota"),
    "Petal pigmentation": O("warna_mahkota"), "Bunga / Warna mahkota": O("warna_mahkota"),
    "Mahkota": O("warna_mahkota", "M", "Label tunggal 'Mahkota' dengan nilai warna."),
    "Mahkota Bunga": O("warna_mahkota", "M", "Nilai berupa warna."),
    "Warna bunga": O("warna_mahkota", "M", "Warna bunga dengan nilai grup warna putih/RHS 155 setara warna mahkota."),
    "Jumlah helai mahkota": O("jumlah_mahkota_bunga"), "Petals found on each bloom": O("jumlah_mahkota_bunga"),
    "Bunga / Jumlah mahkota": O("jumlah_mahkota_bunga"),
    "Corolla diameter": A("lebar_mahkota_bunga|panjang_mahkota",
                          "Diameter mahkota tidak setara tepat dengan panjang atau lebar mahkota kanonik.", "L"),
    "Arah bunga pada tanaman": O("posisi_bunga"), "Flower orientation on the plant": O("posisi_bunga"),
    "Bunga / Posisi": O("posisi_bunga"), "Posisi bunga": O("posisi_bunga"),
    "Orientasi pedunkulus": A("posisi_bunga|posisi_buah_masak", "Orientasi tangkai (pedunkulus) dapat merujuk bunga atau buah.", "L"),
    "Warna kelopak bunga": O("warna_kelopak_bunga"), "Warna bunga kelopak": O("warna_kelopak_bunga", "M", "Urutan kata terbalik pada sumber."),
    "Kelopak": O("warna_kelopak_bunga", "M", "Nilai berupa warna."), "Kelopak Bunga": O("warna_kelopak_bunga", "M", "Nilai berupa warna."),
    "Warna kepala putik": STIGMA, "kepala putik": STIGMA, "Kepala Putik": STIGMA,
    "Warna benang sari": STAMEN, "Warna benangsari": STAMEN, "benang sari": STAMEN, "Benang sari": STAMEN,
    "Warna kotak sari": O("warna_kepala_sari", "M", "Kotak sari = anther = kepala sari."),
    "Kotak Sari": O("warna_kepala_sari", "M", "Kotak sari = anther = kepala sari."),
    "Posisi stigma terhadap anther": NOCANON,
    # --- fruit
    "Fruit shape": O("bentuk_buah"), "Bentuk buah": O("bentuk_buah"),
    "Bentuk ujung buah": O("bentuk_ujung_buah"), "Fruit-tip profile": O("bentuk_ujung_buah"), "Ujung buah": O("bentuk_ujung_buah"),
    "Tipe berbuah": FRUITPOS, "Tipe Berbuah": FRUITPOS,
    "Mature fruit colour": O("warna_buah_masak"), "Warna buah tua": O("warna_buah_masak", "H", "Buah tua = masak."),
    "Warna buah ketika matang": O("warna_buah_masak"), "Pigmentation of ripe pods": O("warna_buah_masak"),
    "Buah Masak / Warna": O("warna_buah_masak"), "Warna buah siap panen": O("warna_buah_masak"),
    "Immature fruit colour": O("warna_buah_muda"), "Warna buah muda": O("warna_buah_muda"),
    "Intermediate fruit colour": N("Warna buah tahap intermediate; kanonik hanya muda dan masak.", "M"),
    "Warna buah intermediate": N("Warna buah tahap intermediate; kanonik hanya muda dan masak.", "M"),
    "Mature fruit length": O("panjang_buah_masak"), "Panjang buah belum masak": O("panjang_buah_muda"),
    "Longitudinal size of the unripe pod": O("panjang_buah_muda"), "Buah Muda / Panjang": O("panjang_buah_muda"),
    "Buah Masak / Panjang": O("panjang_buah_masak"),
    "Keliling buah belum masak": O("keliling_buah_muda"), "Girth of the unripe pod": O("keliling_buah_muda"),
    "Buah Muda / Keliling": O("keliling_buah_muda"), "Buah Masak / Keliling": O("keliling_buah_masak"),
    "Buah Muda / Panjang tangkai": O("panjang_tangkai_buah_muda"), "Buah Masak / Panjang tangkai": O("panjang_tangkai_buah_masak"),
    "Buah Muda / Panjang kelopak": O("panjang_kelopak_buah_muda"), "Buah Masak / Panjang kelopak": O("panjang_kelopak_buah_masak"),
    "Buah Muda / Keliling kelopak": O("keliling_kelopak_buah_muda"), "Buah Masak / Keliling kelopak": O("keliling_kelopak_buah_masak"),
    "Buah Muda / Bentuk kelopak": O("bentuk_kelopak_buah_muda"),
    "Posisi buah matang": O("posisi_buah_masak"), "Orientation of ripe pods": O("posisi_buah_masak"),
    "Buah Masak / Posisi": O("posisi_buah_masak"), "Buah Muda / Posisi": O("posisi_buah_muda"),
    "Ukuran buah": A("panjang_buah_muda|panjang_buah_masak",
                     "Sel memuat panjang dan diameter buah tanpa tahap kematangan; diameter tidak punya kanonik.", "M"),
    "Ukuran buah Panjang": FRUITLEN, "Panjang buah": FRUITLEN,
    "Ukuran buah Diameter": N("Diameter buah tidak sama dengan keliling kanonik.", "M"),
    "Diameter buah": N("Diameter buah tidak sama dengan keliling kanonik.", "M"),
    "Fruit diameter": N("Diameter buah tidak sama dengan keliling kanonik.", "M"),
    "Tebal kulit buah": NOCANON, "Tebal kulit buah (cm)": NOCANON, "Tebal daging buah": NOCANON, "Pericarp thickness": NOCANON,
    "Rasa buah": NOCANON,
    # --- seed
    "Bentuk biji": NOCANON,
    "Warna biji": O("warna_biji"), "Warna kulit biji": O("warna_biji"), "Seed coat shade": O("warna_biji"), "Biji / Warna": O("warna_biji"),
    "Jumlah biji pada buah matang": O("jumlah_biji_buah_masak"), "Seed load in each ripe pod": O("jumlah_biji_buah_masak"),
    "Biji / Jumlah": O("jumlah_biji_buah_masak"), "Seeds per fruit": O("jumlah_biji_buah_masak"),
    # --- location
    "Lokasi Sampling": O("lokasi"), "Lokasi pengambilan sampel": O("lokasi"), "Specimen collection site": O("lokasi"),
    "Lokasi": O("lokasi"), "Tempat pengamatan": O("lokasi"),
    "Data Koordinat / S": N("Koordinat; tidak ada kanonik. Catatan: nilai 110.x berada di kolom S (tertukar dengan bujur).", "M"),
    "Data Koordinat / E": N("Koordinat; tidak ada kanonik.", "M"),
    "Ketinggian Lahan Sampling (mdpl = meter diatas permukaan laut)": N(
        "Ketinggian numerik lokasi sampel; kanonik 'adaptasi ekologi' adalah kategori dataran, bukan angka mdpl.", "L"),
    # --- measurements outside canonical
    "Kandungan klorofil (SPAD)": NOCANON, "Chlorophyll reading (SPAD)": NOCANON, "Soil acidity reading": NOCANON,
    "Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Chlorophyll Content (SPAD)": NOCANON,
    "Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Nitrogen content (mg/g)": NOCANON,
    "Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Humidity (%)": NOCANON,
    "Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Suhu permukaan daun(oC)": NOCANON,
    "Data ekologi tanah / Kelembaban tanah (%)": NOCANON, "Data ekologi tanah / pH tanah": NOCANON,
    "Data microclimate / Suhu udara (0C)": NOCANON, "Data microclimate / Kelembaban udara (%)": NOCANON,
    "Leaf size as recorded": C("panjang_daun|lebar_daun", "Sel memuat 'Panjang ...; Lebar ...'."),
    "Fresh mass of seedless fruit tissue": NOCANON, "Dry mass of seedless fruit tissue": NOCANON, "Mature fruit weight": NOCANON,
}

# Name patterns for yield / agronomy / storage attributes that never map to a canonical row.
NOCANON_PATTERNS = [
    r"^Umur", r"^Berat", r"^Bobot", r"^Jumlah buah per tanaman", r"^Daya simpan", r"^Hasil buah", r"^Produktivitas",
    r"^Populasi", r"^Kebutuhan benih", r"^Ketahanan terhadap", r"^Umur daya simpan",
]

DATASET_OVERRIDES = {
    "E08_zenodo_capsicum_en.xlsx": {
        "Leaf size as recorded": A("panjang_daun|lebar_daun",
                                   "Satu angka tunggal (cm) tanpa penjelasan dimensi daun.", "L"),
    },
}


def annotate(file_name: str, display: str):
    ov = DATASET_OVERRIDES.get(file_name, {})
    if display in ov:
        return ov[display]
    if display in GLOBAL:
        return GLOBAL[display]
    for pat in NOCANON_PATTERNS:
        if re.search(pat, display):
            return N("Atribut agronomi/hasil/penyimpanan/umur-tanaman-fase; tidak ada kanonik sepadan.")
    return None
