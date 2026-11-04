"""Build the two new evaluation inputs (E07 Kementan SK extension, E08 Zenodo Capsicum readable) and copy existing ones."""
import shutil
from pathlib import Path
import openpyxl

OUT = Path(r"D:\college\Semester 6\Penulisan Proposal\project\data_evaluasi")
INP = OUT / "inputs"
INP.mkdir(parents=True, exist_ok=True)

SRC = Path(r"D:\college\Semester 6\Penulisan Proposal\project\data_input_dummy")
SCR = Path(r"C:\Users\Rifqi\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\scratch-workspaces\3e941b6e-3067-4b17-94d4-caaf8d505808\31e5aff6-d2ed-4c0a-b22c-e9b1600000ca\scratch-2026-10-26-8570f7")

# ---- copy existing inputs unchanged
for f in SRC.glob("*.xlsx"):
    shutil.copy2(f, INP / f.name)
shutil.copy2(SCR / "dataset_cabai_deskripsi_varietas.xlsx", INP / "dataset_cabai_deskripsi_varietas.xlsx")

# ---- E07: Kementan descriptions (labels exactly as printed in each document)
BIO = {
    "Varietas Cabai": "Biocalya Agrihorti",
    "Asal": "Dalam Negeri",
    "Silsilah": "Kencana x AVPP 0207",
    "Golongan varietas": "Bersari bebas",
    "Tinggi tanaman": "50,67-65,67 cm",
    "Bentuk penampang batang": "Bulat",
    "Bentuk habitus tanaman": "Semi-tegak",
    "Diameter batang": "1,02-1,27 cm",
    "Warna batang": "Hijau zaitun sedang (MOG 146A)",
    "Intensitas pewarnaan antosianin pada buku": "Sedang",
    "Bentuk daun": "Lanceolate",
    "Ukuran daun": "P : 9,73-6,03 cm; L : 2,53-2,77 cm",
    "Warna daun": "Hijau zaitun sedang (MOG 147A)",
    "Bentuk bunga": "Bintang",
    "Warna bunga kelopak": "Hijau kekuningan kuat (SYG 144A)",
    "Mahkota": "Putih kekuningan (YW NN155A)",
    "kepala putik": "Kuning kuat (SY N144B)",
    "benang sari": "Ungu gelap (DV N92C)",
    "Umur mulai berbunga": "33-35 hst",
    "Umur mulai panen": "96-115 hst",
    "Bentuk buah": "Memanjang",
    "Ukuran buah": "P : 11,75-14,73 cm; L : 1,05-1,32 cm",
    "Warna buah muda": "Hijau zaitun sedang (MOG 137A)",
    "Warna buah tua": "Merah sedang (MR N45A)",
    "Tebal kulit buah": "0,78-1,11 mm",
    "Rasa buah": "Pedas",
    "Bentuk biji": "Bulat pipih",
    "Warna biji": "Kuning terang (YL 10C)",
    "Berat 1000 biji": "9,41-5,48 g",
    "Berat per buah": "5,60-6,85 g",
    "Jumlah buah per tanaman": "127-157",
    "Berat buah per tanaman": "0,65-0,92 kg",
    "Ketahanan terhadap penyakit": "Tahan terhadap antraknos",
    "Daya simpan buah pada suhu 24-27°C": "11-14 hsp",
    "Hasil buah per hektar": "12,08-18,25 ton/ha",
    "Populasi per hektar": "25.000 tanaman",
    "Kebutuhan benih per hektar": "0,23-0,25 kg",
    "Penciri utama": "1. Kedalaman rongga tangkai buah termasuk sedang, kelopak buah non enveloping, sinuasi perikarp pada bagian basal buah termasuk kuat 2. Bentuk ujung buah agak runcing 3. Warna buah muda hijau zaitun sedang (MOG 137A)",
    "Keunggulan varietas": "Tahan terhadap antraknos",
    "Wilayah adaptasi": "Sesuai untuk dataran menengah hingga dataran tinggi pada musim hujan",
}
ENNO = {
    "Varietas Cabai": "ENNO009",
    "Asal": "Dalam Negeri (CV. Enno Corporation)",
    "Silsilah": "CR (02X05)-7-9-2-3-2-1-#",
    "Tinggi tanaman": "83,00-100,42 cm",
    "Golongan varietas": "Bersari bebas",
    "Bentuk penampang batang": "Bulat",
    "Diameter batang": "1,23-1,44 cm",
    "Warna batang": "Hijau (RHS 146A)",
    "Warna daun": "Hijau (RHS NN137A)",
    "Bentuk daun": "Lanset (Lanceolate)",
    "Ukuran daun": "Panjang : 9,32-10,12 cm ; Lebar : 4,20-5,03 cm",
    "Bentuk bunga": "Seperti bintang",
    "Warna kelopak bunga": "Hijau (RHS 143A)",
    "Warna mahkota bunga": "Hijau keputihan (RHS 145C)",
    "Warna kepala putik": "Kuning kehijauan (RHS 153B)",
    "Warna benangsari": "Kuning (RHS 4C)",
    "Umur mulai berbunga": "37,17-40,83 hari setelah tanam",
    "Umur mulai panen": "96,83-101,00 hari setelah tanam",
    "Bentuk buah": "Segitiga sedang",
    "Ukuran buah": "Panjang: 4,35-4,79 cm; Diameter: 1,18-1,53 cm",
    "Warna buah muda": "Hijau muda (RHS 150B)",
    "Warna buah tua": "Merah (RHS 42A)",
    "Tebal kulit buah": "1,33-1,43 mm",
    "Rasa buah": "Pedas",
    "Bentuk biji": "Bulat pipih",
    "Warna biji": "Krem (RHS 162D)",
    "Berat 1000 biji": "4,96-4,99 gram",
    "Berat per buah": "3,47-4,29 gram",
    "Jumlah buah per tanaman": "182,00-218,75 buah",
    "Berat buah per tanaman": "0,51-0,69 kg",
    "Daya simpan buah pada suhu 25-31°C": "4-6 hari setelah panen",
    "Hasil buah per hektar": "9,19-11,68 ton/ha",
    "Populasi per hektar": "26000-27000 tanaman",
    "Kebutuhan benih per hektar": "143,19-149,80 gram",
    "Penciri utama": "Bentuk pangkal buah bulat dengan warna buah tua merah (RSH 42A)",
    "Keunggulan varietas": "Potensi hasil buah per hektar tinggi (9,19-11,68 ton/ha)",
    "Wilayah adaptasi": "Beradaptasi dengan baik di dataran rendah di Kabupaten Jember pada musim penghujan",
    "Pemohon": "CV. Enno Corporation",
    "Pemulia": "Nur Wachid",
    "Peneliti": "Edi Santoso, M. Anasrul Arifin dan Aditya Ananda Putra",
}
ARISA = {
    "Varietas Cabai": "Arisa IPB",
    "Asal": "Dalam Negeri (PKHT IPB)",
    "Silsilah": "IPB. 136074-1-4-3-1-1",
    "Golongan varietas": "Bersari bebas",
    "Tinggi tanaman": "65.00-83.23 cm",
    "Tinggi dikotomus": "20.17-35.00 cm",
    "Lebar tajuk": "67.30-75.70 cm",
    "Tipe tumbuh tanaman": "Tegak",
    "Diameter batang": "10.96-11.32 mm",
    "Warna batang": "Hijau (RHS 143A) dengan semburat ungu (RHS N92A)",
    "Bentuk batang": "Silindris",
    "Pemendekan ruas-internode": "Tidak ada",
    "Panjang daun": "6.33-14.35 cm",
    "Lebar daun": "2.23-3.70 cm",
    "Warna daun": "Hijau (RHS NN137A)",
    "Bentuk daun": "Lanceolate",
    "Umur berbunga": "28.33-36.00 HST",
    "Posisi bunga": "Pendant",
    "Warna mahkota bunga": "Putih (RHS 155A)",
    "Warna kotak sari": "Putih (RHS N77C)",
    "Posisi stigma terhadap anther": "Exserted",
    "Umur panen": "62.33-85.57 HST",
    "Panjang buah": "12.10-16.04 cm",
    "Diameter buah": "10.70-15.69 mm",
    "Tebal daging buah": "1.24-1.64 mm",
    "Bentuk buah": "Segitiga menyempit",
    "Ujung buah": "Sangat lancip",
    "Warna buah muda": "Hijau tua (RHS 143A)",
    "Warna buah intermediate": "Hijau kecoklatan (RHS 200C)",
    "Warna buah tua": "Merah (RHS 45A)",
    "Bobot per buah": "7.36-13.15 g",
    "Jumlah buah per tanaman": "53.33-86.14 buah",
    "Bobot buah pertanaman": "390.01-595.55 g",
    "Umur daya simpan": "6-12 hari",
    "Produktivitas (Potensi hasil)": "7.63-11.64 Ton/Ha",
    "Populasi Tanaman per hektar": "25.000 tanaman",
    "Penciri utama": "Keberadaan antosianin pada batang, Warna buah muda hijau tua (RHS 143A), kemengkilapan buah kusam",
    "Keunggulan varietas": "Produktivitas tinggi",
    "Wilayah adaptasi": "Sesuai di dataran rendah di musim hujan",
    "Pemohon": "Pusat Kajian Hortikultura Tropika IPB",
    "Pemulia": "Muhamad Syukur, Sobir, Awang Maharijaya, Arya Widura Ritonga, Sulassih, Muhamad Ridha Alfarabi Istiqlal, Abdul Hakim, dan Zulfikar Damaralam Sahid",
    "Peneliti": "Yudiwanti Wahyu EK (IPB), Tobias Moniz Vicente (IPB), Deka Rosalinda Maulidya (IPB), Karlin Agustina (UIBA), Evriani Mareza (UIBA), Junaidi Hutasuhut (UIBA), Siti Hafsah (UNSYIAH), Nura (UNSYIAH), dan Yerna Safitri (UNSYIAH)",
}
rows = [BIO, ENNO, ARISA]
cols = []
for r in rows:
    for k in r:
        if k not in cols:
            cols.append(k)
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Deskripsi Varietas"
ws.append(cols)
for r in rows:
    ws.append([r.get(c) for c in cols])
wb.save(INP / "E07_kementan_deskripsi_ext.xlsx")
print("E07", len(cols), "columns")

# ---- E08: Zenodo Capsicum (English descriptors, real observations)
z = openpyxl.load_workbook(SCR / "struktur_src" / "Capsicum_Supplementary_Data.xlsx", data_only=True)
desc = {}
for r in z["Descriptors"].iter_rows(min_row=2, values_only=True):
    if r[1] and r[3]:
        desc[r[1]] = r[3]
obs = z["Observed85"]
hdr = [c.value for c in obs[1]]
keep = [("genotype_name_standard", "Genotype name"), ("species_label", "Species")]
keep += [(c, desc[c]) for c in hdr if c in desc]
idx = {h: i for i, h in enumerate(hdr)}
out = openpyxl.Workbook()
w = out.active
w.title = "Observed85_readable"
w.append([n for _, n in keep])
for r in obs.iter_rows(min_row=2, values_only=True):
    if r[idx["row_id"]] is None:
        continue
    w.append([None if r[idx[c]] is None else str(r[idx[c]]) for c, _ in keep])
out.save(INP / "E08_zenodo_capsicum_en.xlsx")
print("E08", len(keep), "columns", w.max_row - 1, "rows")
