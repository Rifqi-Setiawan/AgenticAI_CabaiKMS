#!/bin/bash
# Run ulang foto + gabungan (7 Nov 2026). Dijalankan sebagai hermes dari folder layanan.
R=/srv/hermes-control/services/agentic-ai-cabai-kms
B=/tmp/visi_ulang
H=/srv/hermes-control/eval/cabai-ui-experiment/hasil_harness/2026-11-07_P01
I=$R/dataset_eksperimen/4_hasil_sistem/I_atribut_bge-m3_39f4213
cd $R
set -a; . ./.env; . ./.env.kms.d/runtime.env; set +a
export KMS_DYNAMIC_SCHEMA=0 HF_HUB_OFFLINE=1
PY=./.venv-kms/bin/python
V="$PY data_evaluasi/skrip/uji_visi_commons_vps.py"
echo "== P01 $(date)"
$PY -B data_evaluasi/skrip/harness_vps.py --inputs /srv/hermes-control/eval/cabai-ui-experiment/inputs_d22 --out $H --reps 1 --only A --ids P01 2>&1 | grep -E " rep | ok | gagal" 
echo "== commons $(date)"
$V --dasar $B/commons --varietas varietas.txt --label commons35 2>&1 | grep -E "^commons35 "
for s in S01_D01_transposed S02_D02_english S03_D03_bertingkat; do
  echo "== indonesia $s $(date)"
  $V --dasar $B/indonesia --kanonik $I/$s/hasil_kanonik.xlsx --label ${s%%_*} 2>&1 | grep -E "^S0"
done
for k in terlihat tertutup; do
  echo "== pvt $k $(date)"
  $V --dasar $B/pvt_$k --kanonik $H/rep1/atribut/P01/hasil_asli.xlsx --label pvt40_$k 2>&1 | grep -E "^pvt40"
done
echo "== SELESAI $(date)"
