#!/bin/bash
# Runs on gzy_4090: generates the samples for the project page, several seeds per setting.
source /inspire/hdd/global_user/hejunjun-24017/jinye/.bashrc >/dev/null 2>&1; conda activate ctgen
R=/inspire/hdd/global_user/hejunjun-24017/jinye/codes/submit/CT-Generation; cd "$R"
export T5_PATH=/inspire/hdd/global_user/hejunjun-24017/jinye/codes/submit_ctgen/downloads/t5-v1_1-xxl
export NUM_GPUS=$(nvidia-smi -L | wc -l)
OUT=/root/ctgen_final/homepage_gen
IN=/root/ctgen_final/homepage_inputs
echo "##### start $(date '+%F %T') gpus=$NUM_GPUS"
for seed in 1995 7 42; do
  echo "##### t2i custom reports seed $seed $(date +%T)"
  SEED=$seed OUT_ROOT=$OUT/seed_$seed DATA_LIST=$IN/custom_reports_chest.json bash scripts/demo.sh t2i_chest 2>&1 | grep -E "file\(s\) in|Traceback|Error|error" | head -5
  SEED=$seed OUT_ROOT=$OUT/seed_$seed DATA_LIST=$IN/custom_reports_abdomen.json bash scripts/demo.sh t2i_abdomen 2>&1 | grep -E "file\(s\) in|Traceback|Error|error" | head -5
done
for seed in 7 42 2024; do
  echo "##### pretrain seed $seed $(date +%T)"
  SEED=$seed OUT_ROOT=$OUT/seed_$seed bash scripts/demo.sh pretrain 2>&1 | grep -E "file\(s\) in|Traceback|Error|error" | head -5
  SEED=$seed OUT_ROOT=$OUT/seed_$seed bash scripts/demo.sh pretrain_mr 2>&1 | grep -E "file\(s\) in|Traceback|Error|error" | head -5
done
echo "##### done $(date '+%F %T')"
