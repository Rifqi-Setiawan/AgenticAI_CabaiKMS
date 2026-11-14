#!/bin/bash
# D24 (12 Nov 2026): rerun semua set foto D23 dengan visi DUA TAHAP (model tidak menerima nama berkas/caption;
# nama berkas dicocokkan deterministik lalu digabung di fuse_photo_signals(independent_signals=True)).
# Input, registri, deskripsi varietas, dan kanonik P01/S01-S03 SAMA dengan run 7 Nov (job_foto.sh + job.sh D23);
# varietas DB dikunci ke meta run lama (--db-dari-meta). Dijalankan sebagai hermes dari folder layanan.
# Pemakaian: job_m2.sh <kelompok>   kelompok = A (commons, indonesia, ind6_netral) | B (pvt kartu terlihat/tertutup)
#                                              | C (pvt40 netral/benar/salah_terdaftar)
# Tiga kelompok dijalankan paralel karena latensi provider 25-90 detik per foto; urutan foto tidak memengaruhi hasil.
R=C:/Users/Rifqi/AppData/Local/Temp/cvr
B=${B:-/tmp/visi_m2}
F=$R/dataset_eksperimen/2_input_foto
E=$R/data_evaluasi/hasil_eksperimen
OLD1=$E/foto_ulang_2026-11-07
OLD2=$E/foto_nama_berpasangan_2026-11-07
P01=$R/hasil_asli.xlsx
I=$R/dataset_eksperimen/4_hasil_sistem/I_atribut_bge-m3_39f4213
MODE=${MODE:-two_stage}
KEL=${1:?kelompok A, B atau C}
cd $R
set -a; . /c/Users/Rifqi/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/scratch-workspaces/3e941b6e-3067-4b17-94d4-caaf8d505808/31e5aff6-d2ed-4c0a-b22c-e9b1600000ca/scratch-2026-11-12-cd58a0/octa_lokal/eval_octa.env; NINEROUTER_API_KEY=tidak_dipakai_lokal; NINEROUTER_VISION_MODEL=ag/gemini-3.8-flash-high; CABAI_KMS_VISION_PROVIDER=9router; PYTHONPATH=.; PYTHONIOENCODING=utf-8; set +a
export KMS_DYNAMIC_SCHEMA=0 HF_HUB_OFFLINE=1 CABAI_KMS_VISION_MODE=$MODE
V="C:/Users/Rifqi/AppData/Local/Temp/cvo/Scripts/python.exe -B data_evaluasi/skrip/uji_visi_commons_vps.py --mode $MODE"

siapkan() {  # siapkan <set> <daftar_foto.csv lama> <folder foto sumber>
  mkdir -p $B/$1/foto
  cp $2 $B/$1/daftar_foto.csv
  for folder in $(tail -n +2 $2 | tr -d '\r' | awk -F, '{print $NF}' | sort -u); do
    if [ -d "$3/$folder" ]; then ln -sfn "$3/$folder" "$B/$1/foto/$folder"; else ln -sfn "$3" "$B/$1/foto/$folder"; fi
  done
}

echo "== kelompok $KEL mode $MODE lokal $(date)"
case $KEL in
A)
  siapkan commons $OLD1/commons/daftar_foto.csv $F/commons_8_folder
  cp $OLD1/commons/varietas.txt $B/commons/
  siapkan indonesia $OLD1/indonesia/daftar_foto.csv $F/foto_indonesia_drive1
  siapkan ind6_netral $OLD2/ind6_netral/daftar_foto.csv $F/nama_file_berpasangan
  echo "== commons $(date)"
  $V --dasar $B/commons --varietas varietas.txt --label commons35 --db-dari-meta $OLD1/commons/meta_commons35.json 2>&1 | grep --line-buffered -E "^commons35 |Error|Traceback"
  for s in S01_D01_transposed S02_D02_english S03_D03_bertingkat; do
    k=${s%%_*}
    echo "== indonesia $k $(date)"
    $V --dasar $B/indonesia --kanonik $I/$s/hasil_kanonik.xlsx --label $k --db-dari-meta $OLD1/indonesia/meta_$k.json 2>&1 | grep --line-buffered -E "^S0|Error|Traceback"
    echo "== ind6_netral $k $(date)"
    $V --dasar $B/ind6_netral --kanonik $I/$s/hasil_kanonik.xlsx --label $k --db-dari-meta $OLD2/ind6_netral/meta_$k.json 2>&1 | grep --line-buffered -E "^S0|Error|Traceback"
  done ;;
B)
  for k in terlihat tertutup; do
    siapkan pvt_$k $OLD1/pvt_$k/daftar_foto.csv $F/pvt_uji_40
    echo "== pvt $k $(date)"
    $V --dasar $B/pvt_$k --kanonik $P01 --label pvt40_$k --db-dari-meta $OLD1/pvt_$k/meta_pvt40_$k.json 2>&1 | grep --line-buffered -E "^pvt40|Error|Traceback"
  done ;;
C)
  for v in netral benar salah_terdaftar; do
    siapkan pvt40_$v $OLD2/pvt40_$v/daftar_foto.csv $F/nama_file_berpasangan
    echo "== pvt40_$v $(date)"
    $V --dasar $B/pvt40_$v --kanonik $P01 --label pvt40_$v --db-dari-meta $OLD2/pvt40_$v/meta_pvt40_$v.json 2>&1 | grep --line-buffered -E "^pvt40|Error|Traceback"
  done ;;
esac
echo "== SELESAI kelompok $KEL $(date)"
