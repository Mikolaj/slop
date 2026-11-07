#!/bin/bash
# memguard.sh [-s GB] [-c GB] [-i SECONDS] PGID DONEFILE LOG: while DONEFILE
# is absent and the process group PGID lives (a chain started by setsid),
# every SECONDS (3), stop the group once MemAvailable falls under the -s GB
# (6) and continue it once it is over the -c GB (14), so that a chain beside
# a 25 GB A2T build grows no further (Mikolaj, 2026-11-06: "you OOMed my
# Firefox"). It continues a group it stopped before it exits. Lines in LOG.
# MemAvailable is read from $MEMINFO, /proc/meminfo by default, in whole GB.
#
# memguard.sh --self-test: a fake meminfo and a dummy process group taken
# through stop, the gap between the bars, continue, a second stop and the
# exit at DONEFILE; exit 0 when every step held.
set -u
STOP=6; CONT=14; EVERY=3
avail() { awk '/^MemAvailable:/{print int($2/1048576)}' "${MEMINFO:-/proc/meminfo}"; }

self_test() {
  local d pg bad=0
  d=$(mktemp -d) || return 1
  meminfo() { printf 'MemTotal: 64000000 kB\nMemAvailable: %d kB\n' $(($1 * 1048576)) > "$d/meminfo"; }
  state() { awk '{print $3}' "/proc/$pg/stat" 2>/dev/null; }
  # Up to 5 s for the group's state to be $1.
  wait_for() { for _ in $(seq 50); do [ "$(state)" = "$1" ] && return 0; sleep 0.1; done; return 1; }
  meminfo 20
  setsid sleep 60 > /dev/null 2>&1 & pg=$!
  sleep 0.2
  MEMINFO="$d/meminfo" bash "$0" -s 8 -c 12 -i 0.1 "$pg" "$d/done" "$d/log" > /dev/null 2>&1 & local g=$!
  meminfo 7;  wait_for T || { echo "self-test: not stopped at 7 GB, under -s"; bad=1; }
  meminfo 10; sleep 0.5; [ "$(state)" = T ] || { echo "self-test: continued at 10 GB, under -c"; bad=1; }
  meminfo 13; wait_for S || { echo "self-test: not continued at 13 GB, over -c"; bad=1; }
  meminfo 10; sleep 0.5; [ "$(state)" = S ] || { echo "self-test: stopped at 10 GB, over -s"; bad=1; }
  meminfo 3;  wait_for T || { echo "self-test: not stopped again at 3 GB"; bad=1; }
  touch "$d/done"
  for _ in $(seq 50); do kill -0 "$g" 2>/dev/null || break; sleep 0.1; done
  kill -0 "$g" 2>/dev/null && { echo "self-test: still running after DONEFILE"; bad=1; kill "$g"; }
  wait_for S || { echo "self-test: the group left stopped at the exit"; bad=1; }
  grep -q 'stopped at 7 GB' "$d/log" && grep -q 'continued at 13 GB' "$d/log" \
    && grep -q 'memguard done' "$d/log" || { echo "self-test: log lacks a line:"; cat "$d/log"; bad=1; }
  kill -KILL -- -"$pg" 2>/dev/null; wait "$pg" 2>/dev/null
  rm -rf "$d"
  [ $bad = 0 ] && echo "memguard self-test: ok"
  return $bad
}

[ "${1:-}" = --self-test ] && { self_test; exit; }
while getopts s:c:i: o; do
  case $o in s) STOP=$OPTARG;; c) CONT=$OPTARG;; i) EVERY=$OPTARG;; *) exit 2;; esac
done
shift $((OPTIND - 1))
[ $# = 3 ] || { echo "usage: memguard.sh [-s GB] [-c GB] [-i SECONDS] PGID DONEFILE LOG" >&2; exit 2; }
P=$1; F=$2; G=$3; stopped=0
until [ -e "$F" ] || ! kill -0 -- -"$P" 2>/dev/null; do
  a=$(avail)
  if [ $stopped = 0 ] && [ "$a" -lt "$STOP" ]; then
    kill -STOP -- -"$P"; stopped=1
    echo "$(date +%T) stopped at ${a} GB" >> "$G"
  elif [ $stopped = 1 ] && [ "$a" -gt "$CONT" ]; then
    kill -CONT -- -"$P"; stopped=0
    echo "$(date +%T) continued at ${a} GB" >> "$G"
  fi
  sleep "$EVERY"
done
[ $stopped = 1 ] && kill -CONT -- -"$P"
echo "$(date +%T) memguard done" >> "$G"
