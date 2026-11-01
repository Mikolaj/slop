#!/bin/bash
# run.sh OUT BASE LABEL...: the scaling probes, gen.py's shapes at N =
# $SCALEN (default 50 100 200 400), compiled to assembly at -O1 and -O2
# by each compiler, BASE first; a compiler is LABEL=PATH, or LABEL for
# ghc-LABEL/_build/stage0/bin/ghc under the working directory. Appends to OUT
# one line per compile, "label shape level N bytes instructions asm-lines", for
# report.py; the sources and outputs go under /tmp/claude-1000/scale/, named
# after OUT. On CPU $SCALECPU (default 10), memory capped.
set -u
H=$(dirname "$(realpath "$0")")
OUT=$(realpath -m "$1"); shift
W=/tmp/claude-1000/scale/$(basename "$OUT" .txt)
NS=${SCALEN:-50 100 200 400}
ulimit -v 8000000
mkdir -p "$W" && (cd "$W" && python3 "$H/gen.py" $NS) || exit 1
for spec in "$@"; do
  l=${spec%%=*}; g=${spec#*=}
  [ "$g" = "$spec" ] && g=$PWD/ghc-$l/_build/stage0/bin/ghc
  for O in 1 2; do for p in $(python3 "$H/gen.py" --shapes); do for n in $NS; do
    src=$W/$p$n.hs; ext=-XBangPatterns
    [ -f "$src" ] || { src=$W/$p$n.cmm; ext=; }
    w=$W/$l-O$O-$p$n; rm -rf "$w"; mkdir -p "$w"
    timeout 1200 taskset -c "${SCALECPU:-10}" perf stat -x, -e instructions:u -o "$w/p.csv" -- \
      "$g" -O$O $ext -fforce-recomp -S -outputdir "$w" -o "$w/out.s" "$src" \
      +RTS -t"$w/rts" --machine-readable -RTS > "$w/log" 2>&1 \
      || { echo "FAILED $l $p O$O $n: $(tail -1 "$w/log")" >> "$OUT"; continue; }
    b=$(command grep -o '"bytes allocated", "[0-9]*"' "$w/rts" | command grep -o '[0-9]*' | tail -1)
    i=$(command grep instructions "$w/p.csv" | cut -d, -f1)
    echo "$l $p O$O $n $b $i $(wc -l < "$w/out.s")" >> "$OUT"
  done; done; done
done
echo "scale DONE $(date +%T)" >> "$OUT"
