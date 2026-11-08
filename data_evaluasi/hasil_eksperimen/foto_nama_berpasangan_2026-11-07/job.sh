#!/bin/bash
R=/srv/hermes-control/services/agentic-ai-cabai-kms
B=/tmp/visi_berpasangan
P01=/srv/hermes-control/eval/cabai-ui-experiment/hasil_harness/2026-11-07_P01/rep1/atribut/P01/hasil_asli.xlsx
I=$R/dataset_eksperimen/4_hasil_sistem/I_atribut_bge-m3_39f4213
cd $R
set -a; . ./.env; . ./.env.kms.d/runtime.env; set +a
export KMS_DYNAMIC_SCHEMA=0 HF_HUB_OFFLINE=1
V="./.venv-kms/bin/python data_evaluasi/skrip/uji_visi_commons_vps.py"
for v in netral benar salah_terdaftar; do
  echo "== pvt40_$v $(date)"; $V --dasar $B/pvt40_$v --kanonik $P01 --label pvt40_$v 2>&1 | grep -E "^pvt40"
done
for s in S01_D01_transposed S02_D02_english S03_D03_bertingkat; do
  echo "== ind6_netral ${s%%_*} $(date)"; $V --dasar $B/ind6_netral --kanonik $I/$s/hasil_kanonik.xlsx --label ${s%%_*} 2>&1 | grep -E "^S0"
done
echo "== SELESAI $(date)"
