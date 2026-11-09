#!/usr/bin/env python3
"""battery.py's utf8 part: a Text scan shaped like megaparsec's decimal over
digits of UTF-8 width 1 to 4, compiled by one compiler at -O1 and -O2, and its
instructions a character, a row a level and width, in the form of tickets.py's
tables, so that two labels' tables compare row by row by `tickets.py compare`.

Usage: python3 tools/NCG-battery/utf8.py run GHC OUT CPU
       python3 tools/NCG-battery/utf8.py --self-test

utf8-scan/Main.hs beside this file is q2's c23/Main.hs (finding 910), byte
for byte: `Main N K W` scans N times K digits of width W (1: '7', 2: U+0667,
3: U+0967, 4: U+1D7D5), taken by T.takeWhile isNumber and folded by T.foldl',
so that text's UTF-8 decoder takes its paths for 2, 3 and 4 bytes, which
no other input of the battery reaches, megaparsec's benchmarks being ASCII.
`run` compiles it at each level and counts it as tickets.py counts its loops,
instructions:u by `perf stat` under setarch -R and the RTS's own options,
at CALLS calls of DIGITS digits, the difference over the characters added;
OUT gets a line a level and width: `W2 -O2`, `per-element` and the figure.
A level that fails to compile or a run that fails is a row `failed` with
the step, and run exits 1; 2 when it could not run at all (no compiler, no perf).
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tickets  # noqa: E402

SRC = os.path.join(HERE, 'utf8-scan')
LEVELS = ('-O1', '-O2')
WIDTHS = (1, 2, 3, 4)
CALLS = (20000, 40000)  # q2's price.sh's
DIGITS = 50


def run(ghc, out, cpu):
    for tool in (tickets.PERF[0], 'taskset', 'setarch'):
        if shutil.which(tool) is None:
            print(f'{tool} is not on PATH; nothing measured', file=sys.stderr)
            return 2
    if not os.access(ghc, os.X_OK):
        print(f'no compiler {ghc}; nothing measured', file=sys.stderr)
        return 2
    rows, bad = [], 0
    with tempfile.TemporaryDirectory(prefix='ncg-utf8-') as td:
        for lev in LEVELS:
            w = tempfile.mkdtemp(dir=td)
            shutil.copytree(SRC, w, dirs_exist_ok=True)
            ok = tickets.sh([ghc, lev, '-outputdir', 'b', '-o', 'scan', 'Main.hs'], w, cpu,
                            os.path.join(w, 'log')) == 0
            for width in WIDTHS:
                case = f'W{width} {lev}'
                if not ok:
                    rows.append((case, 'failed', 'build'))
                    bad += 1
                    continue
                bad += tickets.per_element(
                    case, lambda k: ['./scan', str(k), str(DIGITS), str(width)],
                    CALLS, DIGITS, w, cpu, rows)
    with open(out, 'w') as fh:
        fh.write(''.join(f'{c}\t{k}\t{v}\n' for c, k, v in rows))
    print(f'{len(rows)} rows, {bad} cases failed, in {out}')
    return 1 if bad else 0


# --- self-test: a fake compiler writing a stub program that names its level,
# a fake perf counting a setup and a cost a character of the width and level.

FAKE_GHC = r'''#!/bin/bash
o=; lev=; for a in "$@"; do
  case $prev in -o) o=$a;; esac
  case $a in -O*) lev=$a;; esac
  prev=$a
done
echo "$PWD $*" >> "$FAKELOG"
[ -f Main.hs ] || exit 1
[ -n "${FAKEFAILGHC:-}" ] && [ "$lev" = "$FAKEFAILGHC" ] && exit 1
printf '#!/bin/sh\n# %s\nexit 0\n' "$lev" > "$o"; chmod +x "$o"
'''
FAKE_PERF = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv
out, rest = a[a.index('-o') + 1], a[a.index('--') + 1:]
n, k, w = (int(x) for x in rest[1:])
if os.environ.get('FAKEFAILRUN') == str(w):
    sys.exit(1)
cost = {1: 63, 2: 84, 3: 102, 4: 112}[w] + (10 if '-O1' in open(rest[0]).read() else 0)
with open(out, 'w') as fh:
    fh.write('# started' + chr(10) + chr(10) + str(10**6 + cost * n * k) + ',,instructions:u,9,100.00,,' + chr(10))
'''


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='utf8-') as d:
        ghc, perf = os.path.join(d, 'ghc'), os.path.join(d, 'perf')
        for path, text in ((ghc, FAKE_GHC), (perf, FAKE_PERF)):
            with open(path, 'w') as fh:
                fh.write(text)
            os.chmod(path, 0o755)
        saved, tickets.PERF = tickets.PERF, [perf]
        cpu = str(sorted(os.sched_getaffinity(0))[0])
        os.environ['FAKELOG'] = os.path.join(d, 'log')
        try:
            out = os.path.join(d, 'a.tsv')
            rc = run(ghc, out, cpu)
            t = tickets.load(out)
            want = {(f'W{w} {lev}', 'per-element'): f'{c + (10 if lev == "-O1" else 0)}.000'
                    for lev in ('-O1', '-O2') for w, c in ((1, 63), (2, 84), (3, 102), (4, 112))}
            if rc != 0 or t != want:
                bad.append(f'the table: exit {rc}, {t}')
            with open(os.environ['FAKELOG']) as fh:
                calls = sorted(x.split(' ', 1)[1] for x in fh.read().split('\n') if x)
            if calls != [f'{lev} -outputdir b -o scan Main.hs' for lev in ('-O1', '-O2')]:
                bad.append(f'compiled {calls}')
            with open(os.path.join(SRC, 'Main.hs')) as fh:
                src = fh.read()
            if not all(x in src for x in ("T.takeWhile isNumber", "'\\x0667'", "'\\x0967'",
                                          "'\\x1D7D5'", 'T.foldl\'')):
                bad.append(f'{SRC}/Main.hs is not the Text scan over the four widths')
            # A failed compile and a failed run are rows, and exit 1.
            os.environ['FAKEFAILGHC'] = '-O1'
            os.environ['FAKEFAILRUN'] = '3'
            rc = run(ghc, os.path.join(d, 'b.tsv'), cpu)
            tb = tickets.load(os.path.join(d, 'b.tsv'))
            if (rc != 1 or tb.get(('W2 -O1', 'failed')) != 'build'
                    or tb.get(('W3 -O2', 'failed')) != 'run'
                    or tb.get(('W4 -O2', 'per-element')) != '112.000'):
                bad.append(f'failures: exit {rc}, {tb}')
            del os.environ['FAKEFAILGHC'], os.environ['FAKEFAILRUN']
            if run(os.path.join(d, 'nosuch'), out, cpu) != 2:
                bad.append('a missing compiler did not exit 2')
        finally:
            tickets.PERF = saved
    for x in bad:
        print('FAIL', x)
    print('ok   utf8.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    if len(argv) == 4 and argv[0] == 'run':
        return run(*argv[1:])
    print(__doc__.split('\n\n')[1], file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
