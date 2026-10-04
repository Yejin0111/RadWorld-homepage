#!/usr/bin/env bash
# Run on the GPU server inside a checkout of the RadWorld code release (the one with
# weights/ and demo_data/ unpacked). Produces every sample the project page still needs.
#
#   bash generate_samples.sh /path/to/RadWorld-code /path/to/this/tools/server
#
# Then copy the results back to the laptop:
#   rsync -av gzy_4090:/path/to/RadWorld-code/outputs_homepage/ ~/Desktop/radworld_server_outputs/
set -euo pipefail
CODE=${1:?path to the RadWorld code release}
HERE=${2:?path to tools/server (for custom_reports_chest.json)}
cd "$CODE"
export OUT_ROOT=outputs_homepage
bash scripts/demo.sh --list
# whole-volume generation, organ-mask CT, translation settings (inputs come with demo_data)
for task in pretrain pretrain_mr m2i_organ cbct2ct mr2ct mr2mr ct_arterial ct_venous; do
  bash scripts/demo.sh "$task"
done
# report-guided chest CT from reports written by the authors, so the page may show the full text
DATA_LIST="$HERE/custom_reports_chest.json" bash scripts/demo.sh t2i_chest
echo "done: $CODE/$OUT_ROOT"
