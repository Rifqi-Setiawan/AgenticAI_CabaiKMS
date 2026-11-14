# D26: Perbandingan model visi (14 Nov 2026)

Harness, input, registri, deskripsi varietas, kanonik, varietas DB (`--db-dari-meta`), mode `two_stage`, dan skrip skor sama dengan D24; yang berbeda hanya model visi (`CABAI_KMS_EVAL_VISION_MODEL`, khusus eksperimen). Model teks tetap Gemini 3.8 Flash medium. Kandidat 1 ulangan, 271 panggilan visi per model, 0 gagal setelah percobaan ulang. Claude, GPT, dan Gemini lewat 9router dari VPS; Qwen3.8 Flash dan Grok 4.7 lewat gateway OpenAI-compatible Octa Telkomsel (`CABAI_KMS_EVAL_VISION_BASE_URL`), dijalankan dari PC di Indonesia karena gateway itu hanya melayani akses dari Indonesia (salinan harness yang sama, `runner_lokal_octa/`); skor dihitung di VPS.

Presisi/recall KNOWN dihitung dari `rincian_foto.csv` (`skrip/presisi_known_visi.py`): presisi = jawaban KNOWN dengan
varietas benar / semua jawaban KNOWN; recall = jawaban KNOWN benar / foto gold KNOWN (61).

| Metrik | Gemini 3.8 Flash high (D24, rerata 3 ulangan) | Qwen3.8 Flash | Grok 4.7 | Claude Opus 5.5 | GPT-6 Astra | GPT-6.1 Sol |
|---|---|---|---|---|---|---|
| Presisi jawaban KNOWN (Commons, Indonesia, PVT 2 kondisi) | 0,69-0,71 | 0,67 | 0,53 | 0,67 | 1,00 | 1,00 |
| Recall KNOWN (dari 61 foto KNOWN) | **0,51-0,56** | 0,26 | 0,15 | 0,16 | 0,08 | 0,10 |
| Dijawab KNOWN padahal bukan | 5-6 | 4 | 2 | 0 | 0 | 0 |
| PVT nama salah terdaftar: REVIEW_MISMATCH (dari 40) | 7 | **17** | 2 | 1 | 0 | 0 |
| PVT berpasangan: tindakan sesuai gold (dari 120) | 32,33 | **43** | 28 | 27 | 26 | 26 |
| PVT berpasangan: AUTO_LINK salah (dari 120) | 7,67 | 8 | 0 | 0 | 0 | 0 |
| Commons: status benar (dari 35) | **32,67** | 30 | 28 | 28 | 0 | 0 |
| Indonesia S01-S03: Top-1 KNOWN | **0,750** | 0,125 | 0,312 | 0,375 | 0,312 | 0,375 |
| PVT kartu terlihat: Top-1 KNOWN | **0,579** | 0,526 | 0,158 | 0,158 | 0 | 0 |
| PVT kartu tertutup: Top-1 KNOWN | **0,175** | 0,053 | 0 | 0 | 0 | 0 |
| PVT kartu tertutup: macro-F1 kelas gold | 0,263 | **0,406** | 0,087 | 0,095 | 0 | 0 |
| Workbook gabungan Indonesia F1 | **0,980** | 0,942 | 0,947 | 0,933 | 0,938 | 0,947 |

## Cara membaca

- **Gemini 3.8 Flash tetap paling seimbang:** recall KNOWN tertinggi dengan presisi setara, dan F1 workbook akhir tertinggi.
- **Qwen3.8 Flash paling sering menangkap nama berkas yang salah** (REVIEW_MISMATCH 17/40, tindakan sesuai gold 43/120) dan
  paling sering benar menjawab OTHER (macro-F1 kartu tertutup 0,406), tetapi hampir tidak mengenali foto Indonesia (Top-1
  0,125) dan tautan salahnya setara Gemini (8/120).
- **Claude Opus 5.5, GPT-6 Astra, GPT-6.1 Sol, dan Grok 4.7 sangat konservatif:** 0 tautan salah, tetapi recall 0,08-0,16,
  sehingga hampir semua foto masuk antrean tinjauan. Keyakinan visual yang dilaporkan model ini (sering 0,70-0,86) jarang
  melewati ambang AUTO_LINK 0,85; tanpa deskripsi morfologi (Commons, Hungarian Wax) GPT tidak menjawab KNOWN atau OTHER.
- **Kondisi kartu terlihat sebagian mengukur pembacaan label:** Gemini dan Qwen membaca tulisan kartu (mis. "TURIMA 2"),
  sedangkan model lain mematuhi instruksi prompt untuk tidak menjadikan tulisan kartu satu-satunya dasar.
- **Batas utama ada di data:** pada foto PVT 125 px kartu tertutup tidak ada model yang Top-1-nya melewati 0,21.
- **Catatan keadilan:** prompt dan ambang AUTO_LINK 0,85 dikembangkan bersama Gemini; presisi/recall KNOWN adalah pembanding
  yang tidak bergantung ambang. GLM 5.2 (Octa) tidak dinilai karena tidak menerima gambar.

## Berkas

- `<model>/hasil/`, `<model>/skor/`, log run per model (`claude-opus-5-5`, `gpt-6-astra`, `gpt-6_1-sol`, `qwen3_8-flash`, `grok-4_7`).
- `banding/banding_model.md` (semua metrik, `skrip/banding_model_visi.py`), `banding/presisi_known.txt`.
- `pilot.sh` (runner VPS), `runner_lokal_octa/` (runner PC untuk gateway Octa; API key tidak disimpan di repo).
