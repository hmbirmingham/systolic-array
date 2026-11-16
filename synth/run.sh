#!/usr/bin/env bash
# Yosys cell counts for systolic_4x4 on iCE40 and ECP5, at DATA_W=8 and 16 with
# ACC_W=32. Writes one `stat` report per configuration into synth/reports/.
#
# Synthesis only. nextpnr has not run, so nothing here is placed, routed or
# timed, and there is no Fmax.
#
#   source env.sh && bash synth/run.sh

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

mkdir -p synth/build synth/reports

for target in ice40 ecp5; do
  for width in 8 16; do
    name="${target}_dw${width}"
    # -defer so chparam lands before elaboration; the array's default is DATA_W=8.
    yosys -q -l "synth/build/${name}.log" -p "
      read_verilog -sv -defer rtl/pe.sv rtl/systolic_4x4.sv
      chparam -set DATA_W ${width} -set ACC_W 32 systolic_4x4
      synth_${target} -top systolic_4x4
      tee -o synth/reports/${name}.txt stat
    "
    echo "${name}: synth/reports/${name}.txt"
  done
done
