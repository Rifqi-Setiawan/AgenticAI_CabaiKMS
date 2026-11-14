#!/bin/bash
# D26 pilot lokal (PC di Indonesia, gateway Octa). Pemakaian: pilot_lokal.sh <model> <outdir>
L=$(cd "$(dirname "$0")" && pwd)
M=$1; OUT=$2
mkdir -p $OUT
set -a; . $L/eval_octa.env; NINEROUTER_API_KEY=tidak_dipakai_lokal; NINEROUTER_VISION_MODEL=ag/gemini-3.8-flash-high
CABAI_KMS_VISION_PROVIDER=9router; PYTHONPATH=.; PYTHONIOENCODING=utf-8; KMS_DYNAMIC_SCHEMA=0; HF_HUB_OFFLINE=1
CABAI_KMS_VISION_MODE=two_stage; CABAI_KMS_EVAL_VISION_MODEL=$M; B=$OUT; set +a
echo "model $M gateway $CABAI_KMS_EVAL_VISION_BASE_URL mulai $(date) lokal" > $OUT/status.log
for k in A B C; do bash $L/job_lokal.sh $k > $OUT/job_$k.log 2>&1 & done
wait
echo "job selesai $(date)" >> $OUT/status.log
cd C:/Users/Rifqi/AppData/Local/Temp/cvr && C:/Users/Rifqi/AppData/Local/Temp/cvo/Scripts/python.exe $L/ulang_gagal_lokal.py $OUT > $OUT/ulang.log 2>&1
echo "SEMUA_SELESAI $(date)" >> $OUT/status.log
