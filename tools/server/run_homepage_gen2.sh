#!/bin/bash
# Second batch: longer report prompts, four samples per report in one model load, CFG 4 and 8.
until grep -q "##### done" /root/ctgen_final/homepage_gen.log; do sleep 30; done
source /inspire/hdd/global_user/hejunjun-24017/jinye/.bashrc >/dev/null 2>&1; conda activate ctgen
R=/inspire/hdd/global_user/hejunjun-24017/jinye/codes/submit/CT-Generation; cd "$R"
export T5_PATH=/inspire/hdd/global_user/hejunjun-24017/jinye/codes/submit_ctgen/downloads/t5-v1_1-xxl
N=$(nvidia-smi -L | wc -l); IN=/root/ctgen_final/homepage_inputs; OUT=/root/ctgen_final/homepage_gen2
echo "##### start $(date '+%F %T')"
for cfg in 4 8; do
  echo "##### chest cfg $cfg $(date +%T)"
  OUT_ROOT=$OUT/cfg_$cfg CFG_SCALE=$cfg SEED=1995 bash scripts/sample/sample_t2i.sh t2i_chest t2i_chest $IN/reports_chest_v2.json $N CT 2>&1 | grep -E "file\(s\)|Traceback|Error" | head -5
done
echo "##### abdomen cfg 4 $(date +%T)"
OUT_ROOT=$OUT/cfg_4 CFG_SCALE=4 SEED=1995 bash scripts/sample/sample_t2i.sh t2i_abdomen t2i_abdomen $IN/reports_abdomen_v2.json $N CT 2>&1 | grep -E "file\(s\)|Traceback|Error" | head -5
find $OUT -name "*.nii.gz" | wc -l
echo "##### done $(date '+%F %T')"
