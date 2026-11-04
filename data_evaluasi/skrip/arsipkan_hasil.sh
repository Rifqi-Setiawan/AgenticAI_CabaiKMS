#!/bin/sh
# Tarik semua hasil eksperimen dari VPS ke laptop (UI dan harness), lalu buat SHA256SUMS lokal.
# Pemakaian: sh skrip/arsipkan_hasil.sh   (dijalankan dari folder data_evaluasi)
set -e
BASE=/srv/hermes-control/eval/cabai-ui-experiment
for kind in hasil_ui hasil_harness hasil_atribut_baru hasil_dinamis; do
  mkdir -p "hasil_eksperimen/$kind"
  ssh myvps "sudo tar -C $BASE/$kind -cf - ." | tar -C "hasil_eksperimen/$kind" -xf -
done
(cd hasil_eksperimen && find . -type f ! -name SHA256SUMS_lokal.txt -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS_lokal.txt)
echo "arsip selesai: $(find hasil_eksperimen -type f | wc -l) berkas"
