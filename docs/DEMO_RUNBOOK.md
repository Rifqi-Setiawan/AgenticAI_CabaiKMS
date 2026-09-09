# CABAI-KMS Demo Runbook

## Pre-demo

1. Buat/aktifkan environment dan instal `requirements.txt`.
2. Isi `GROQ_API_KEY` untuk provider teks. Siapkan Ollama hanya bila fallback lokal akan digunakan, lalu verifikasi model secara manual.
3. Untuk vision, isi `GOOGLE_API_KEY`, siapkan service-account Drive read-only, dan bagikan folder kepada service account sebagai Viewer.
4. Gunakan sampel `.xlsx` yang telah diperiksa, misalnya `data/samples/sample_transposed_sintetis.xlsx`.
5. Opsional: siapkan folder datar berisi beberapa citra tanaman yang nama/varietasnya sesuai skenario demo.
6. Jalankan `streamlit run src/ui/app.py` dan periksa panel **Runtime readiness**. Panel tidak melakukan network health check.

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

Runbook ini tidak menyatakan metrik akurasi model. Evaluasi manusia/Phase 7C2B tetap ditunda.
