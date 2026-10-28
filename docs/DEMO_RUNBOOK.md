# CABAI-KMS Demo Runbook

## Pre-demo

1. Buat/aktifkan environment dan instal `requirements.txt`.
2. Pastikan instance 9Router lokal atau VPS aktif dan endpoint OpenAI-compatible-nya dapat dijangkau.
3. Buat `.env` dari `.env.example` hanya bila belum ada. Isi `NINEROUTER_BASE_URL` dengan endpoint yang berakhiran `/v1` dan `NINEROUTER_API_KEY` secara manual; jangan commit `.env`. Pertahankan model teks `ag/gemini-3.8-flash-medium` dan model vision `ag/gemini-3.8-flash-high`.
4. Jalankan `.\.venv\Scripts\python.exe -B -m scripts.ninerouter_preflight`. Preflight harus lulus untuk reachability, `/v1/models`, structured text, dan multimodal vision.
5. Siapkan service-account Drive read-only dan bagikan folder kepada service account sebagai Viewer.
6. Gunakan sampel `.xlsx` yang telah diperiksa, misalnya `data/samples/sample_transposed_sintetis.xlsx`.
7. Opsional: siapkan folder datar berisi beberapa citra tanaman yang nama/varietasnya sesuai skenario demo.
8. Jalankan `streamlit run src/ui/app.py` dan periksa panel **Runtime readiness**. Panel tidak melakukan network health check.

9Router mengelola routing, kuota, dan account fallback untuk tiga akun Antigravity. CABAI-KMS tidak memilih akun. Secondary vision consensus dinonaktifkan dalam mode 9Router karena semua akun melayani model yang sama; hasil tetap melewati validasi, abstention, dan manual review.

## Live demo

1. Unggah workbook `.xlsx`.
2. Pilih worksheet, orientasi, dan opsi header.
3. Opsional: masukkan URL/ID Drive dan pilih batas gambar.
4. Jalankan pipeline; ini memanggil runtime LangGraph nyata, bukan mode demo terpisah.
5. Pada **Progres**, jelaskan status SUCCESS, SKIPPED, WARNING, atau FAILED dan log rinci.
6. Pada **Hasil**, jelaskan ringkasan run dan inspektor selective mapping: prediksi belum tentu menjadi accepted canonical write.
7. Bila ada REVIEW, pilih Approve, Revise, atau NO_MATCH. Setelah semua selesai, klik **Terapkan Koreksi**; replay tidak memanggil model.
8. Tunjukkan hitungan dan baris vision, termasuk `write_applied` dan `write_reason`.
9. Unduh workbook corrected yang direkomendasikan bila tersedia; workbook asli tetap dapat diunduh.

## Failure fallback

- Drive bersifat opsional. Kosongkan folder Drive agar demo tetap berjalan tabular-only.
- Kegagalan provider vision atau satu citra tidak membatalkan hasil tabular; periksa alasan non-write dan Advanced / Debug.
- Kegagalan mapping individual mengikuti safe semantics yang sudah ada (`REVIEW`/`NO_WRITE`) dan tidak memaksa canonical write.
- Jika workbook gagal preflight, pilih `.xlsx` valid dan worksheet yang tersedia. Jangan mengganti ekstensi CSV menjadi `.xlsx`.
- Runtime/API menyediakan `resume_pipeline_ui()`, tetapi Streamlit tidak memiliki tombol Resume dan tidak otomatis melanjutkan setelah browser/proses restart.
- Jangan mengganti model ketika preflight gagal. Laporkan kategori tersanitasi dan perbaiki connectivity, auth, model availability, request format, structured-output, rate-limit, timeout, atau dukungan multimodal.

Rollback legacy harus eksplisit: set `CABAI_KMS_TEXT_PROVIDER=legacy` dan `CABAI_KMS_VISION_PROVIDER=legacy`, lalu isi key provider lama yang relevan. Mode 9Router tidak pernah otomatis memanggil Groq, Gemini langsung, OpenRouter, atau Ollama.

Runbook ini tidak menyatakan metrik akurasi model. Evaluasi manusia/Phase 7C2B tetap ditunda.
