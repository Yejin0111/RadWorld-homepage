#!/bin/bash
source /inspire/hdd/global_user/hejunjun-24017/jinye/.bashrc >/dev/null 2>&1; conda activate ctgen
R=/inspire/hdd/global_user/hejunjun-24017/jinye/codes/submit/CT-Generation; cd "$R"
export T5_PATH=/inspire/hdd/global_user/hejunjun-24017/jinye/codes/submit_ctgen/downloads/t5-v1_1-xxl
N=$(nvidia-smi -L | wc -l); IN=/root/ctgen_final/homepage_inputs; OUT=/root/ctgen_final/homepage_gen4
echo "##### start $(date '+%F %T')"
echo "##### report $(date +%T)"
OUT_ROOT=$OUT CFG_SCALE=4 SEED=3030 bash scripts/sample/sample_t2i.sh t2i_chest t2i_chest $IN/gen4_report.json $N CT 2>&1 | grep -E "file\(s\)|Traceback|Error" | head -5
echo "##### mr $(date +%T)"
OUT_ROOT=$OUT CFG_SCALE=8 SEED=3030 bash scripts/sample/sample.sh pretrain pretrain $IN/gen4_mr.json $N MR 2>&1 | grep -E "file\(s\)|Traceback|Error" | head -5
echo "##### ct $(date +%T)"
OUT_ROOT=$OUT CFG_SCALE=8 SEED=3030 bash scripts/sample/sample.sh pretrain pretrain $IN/gen4_ct.json $N CT 2>&1 | grep -E "file\(s\)|Traceback|Error" | head -5
find $OUT -name "*.nii.gz" | wc -l
echo "##### done $(date '+%F %T')"
