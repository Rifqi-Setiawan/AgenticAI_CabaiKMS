#!/bin/bash
# D26 pilot: set foto D24 (271 panggilan visi, two_stage) dengan model visi lain lewat CABAI_KMS_EVAL_VISION_MODEL.
# Pemakaian (sebagai hermes): pilot.sh <model> <outdir>
R=/srv/hermes-control/services/agentic-ai-cabai-kms
M=$1; OUT=$2
J=$R/data_evaluasi/hasil_eksperimen/foto_two_stage_2026-11-12/job_m2.sh
mkdir -p $OUT
export CABAI_KMS_EVAL_VISION_MODEL=$M B=$OUT
echo "model $M mulai $(date) rev $(cd $R && git rev-parse --short HEAD)$(cd $R && git diff --quiet || echo +belum_commit)" > $OUT/status.log
for k in A B C; do bash $J $k > $OUT/job_$k.log 2>&1 & done
wait
echo "job selesai $(date)" >> $OUT/status.log
cd $R && set -a && . ./.env && . ./.env.kms.d/runtime.env && set +a
export KMS_DYNAMIC_SCHEMA=0 HF_HUB_OFFLINE=1 CABAI_KMS_VISION_MODE=two_stage
.venv-kms/bin/python /tmp/bersih/ulang_gagal_m2.py $OUT > $OUT/ulang.log 2>&1
echo "SEMUA_SELESAI $(date)" >> $OUT/status.log
