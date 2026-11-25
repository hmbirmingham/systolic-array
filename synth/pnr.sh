#!/usr/bin/env bash
# nextpnr place-and-route for systolic_4x4_top on ECP5 LFE5U-25F (ADR-0006).
# Writes one report per width and speed grade into synth/reports/.
#
# This routes `systolic_4x4_top`, not `systolic_4x4`. The bare array exposes all
# sixteen accumulators flat — 644 port bits — and places on nothing. The wrapper
# adds the shift-chain readout that makes the design fit a package (ADR-0005),
# so it is the only thing an Fmax can be quoted for.
#
# Unlike synth/run.sh this is placed, routed and timed, so these numbers are
# real Fmax rather than cell counts.
#
#   source env.sh && bash synth/pnr.sh

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

DEVICE=${DEVICE:---25k}
DEVICE_NAME=${DEVICE_NAME:-LFE5U-25F}
PACKAGE=${PACKAGE:-CABGA381}
WIDTHS=${WIDTHS:-"8 16"}
SPEEDS=${SPEEDS:-"6 7 8"}

mkdir -p synth/build synth/reports

for width in $WIDTHS; do
  json="synth/build/top_dw${width}.json"
  # -defer so chparam lands before elaboration; the top's default is DATA_W=8.
  yosys -q -l "synth/build/top_dw${width}_synth.log" -p "
    read_verilog -sv -defer rtl/pe.sv rtl/systolic_4x4.sv rtl/systolic_4x4_top.sv
    chparam -set DATA_W ${width} -set ACC_W 32 systolic_4x4_top
    synth_ecp5 -top systolic_4x4_top -json ${json}
  "

  for speed in $SPEEDS; do
    name="pnr_ecp5_dw${width}_s${speed}"
    # --timing-allow-fail: no --freq is given, so nextpnr uses its 12 MHz default
    # constraint and reports what it achieved. The achieved figure is the Fmax.
    nextpnr-ecp5 "$DEVICE" --package "$PACKAGE" --speed "$speed" \
      --json "$json" \
      --textcfg "synth/build/${name}.cfg" \
      --report "synth/reports/${name}.json" \
      --timing-allow-fail \
      > "synth/build/${name}.log" 2>&1

    python3 - "synth/reports/${name}.json" "$width" "$speed" "$DEVICE_NAME" "$PACKAGE" \
      > "synth/reports/${name}.txt" <<'PY'
import json, sys
path, width, speed, device_name, package = sys.argv[1:6]
d = json.load(open(path))
fmax = list(d["fmax"].values())[0]
u = d["utilization"]
cp = d["critical_paths"][0]["path"]

print("nextpnr-ecp5 place-and-route report")
print("===================================")
print(f"top        systolic_4x4_top")
print(f"DATA_W     {width}   ACC_W 32")
print(f"device     {device_name}  package {package}  speed grade {speed}")
print()
print(f"Fmax       {fmax['achieved']:.2f} MHz   (constraint {fmax['constraint']} MHz, nextpnr default)")
print()
print("Utilisation")
print("-----------")
for k, v in u.items():
    if isinstance(v, dict) and v.get("used"):
        print(f"  {k:<16}{v['used']:>6} / {v['available']:<7}{100*v['used']/v['available']:5.1f}%")
print()
total = sum(s.get("delay", 0) for s in cp)
agg = {}
for s in cp:
    agg[s.get("type", "?")] = agg.get(s.get("type", "?"), 0) + s.get("delay", 0)
print("Critical path")
print("-------------")
print(f"  total {total:.3f} ns over {len(cp)} segments")
for k, v in sorted(agg.items(), key=lambda kv: -kv[1]):
    print(f"  {k:<10}{v:>8.3f} ns{100*v/total:>7.1f}%")
print()
worst = sorted(cp, key=lambda s: -s.get("delay", 0))[:4]
print("  largest segments:")
for s in worst:
    to = s.get("to")
    name = to.get("cell") if isinstance(to, dict) else (to or "")
    print(f"    {s.get('type'):<9}{s.get('delay'):>7.3f} ns  {str(name)[:58]}")
PY
    printf '%-26s %s MHz\n' "$name" \
      "$(python3 -c "import json,sys;print(f\"{list(json.load(open('synth/reports/${name}.json'))['fmax'].values())[0]['achieved']:.2f}\")")"
  done
done
