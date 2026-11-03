#!/usr/bin/env python3
"""run.sh's lines as ratios to the base, the first label, per shape, level
and measure (bytes allocated, the compiler's instructions, assembly lines), N
ascending.

Usage: python3 tools/NCG-scale/report.py OUT...
       python3 tools/NCG-scale/report.py --self-test

A row is flagged where the ratio rises at every doubling of N and by 2% or more
from the smallest N to the largest: the label's excess over the base then grows
faster than the base. An instr row is marked "(collections)" where a line of
its label or the base's, the eighth field being the compile's collections,
collected more than once: its instructions then include the collector's work.
"base^" is the base's own growth exponent over the last
doubling, so that the base's own super-linear shapes are told apart: on chain,
assembly grows about as N^1.9 and allocation as N^2.4. The self-test replays
the first scaling run's figures, in which mw's code on chain grew faster than
the base's (1.34 to 3.00) and lf8's compile cost on loops did (1.012 to 1.183),
while lf8's on chain did not (1.021 to 1.007)."""
import math
import subprocess
import sys
import tempfile


def report(lines):
    """The report's lines, and the set of flagged (label, shape, level,
    measure)."""
    rows, labels, fails, gcs = {}, [], [], {}
    for line in lines:
        f = line.split()
        if not f or f[0] == 'scale':
            continue
        if f[0] == 'FAILED' or len(f) < 7:
            fails.append(line.rstrip())
            continue
        lab, shape, lev, n = f[0], f[1], f[2], int(f[3])
        if lab not in labels:
            labels.append(lab)
        rows[(lab, shape, lev, n)] = [int(x) for x in f[4:7]]
        if len(f) > 7 and f[7].isdigit():
            gcs[(lab, shape, lev, n)] = int(f[7])
    out, flagged = [], set()
    if not labels:
        return ['no rows'] + fails, flagged
    base = labels[0]
    keys = sorted({(s, v) for (_, s, v, _) in rows})
    allns = sorted({n for (_, _, _, n) in rows})
    for lab in labels[1:]:
        for shape, lev in keys:
            ns = sorted(n for (b, s, v, n) in rows
                        if (b, s, v) == (base, shape, lev)
                        and (lab, shape, lev, n) in rows)
            if len(ns) < 2:
                continue
            for m, name in enumerate(('bytes', 'instr', 'asm')):
                r = [rows[(lab, shape, lev, n)][m] / rows[(base, shape, lev, n)][m]
                     for n in ns]
                b1 = rows[(base, shape, lev, ns[-2])][m]
                b2 = rows[(base, shape, lev, ns[-1])][m]
                exp = math.log(b2 / b1) / math.log(ns[-1] / ns[-2])
                flag = all(y > x for x, y in zip(r, r[1:])) and r[-1] >= r[0] * 1.02
                if flag:
                    flagged.add((lab, shape, lev, name))
                coll = name == 'instr' and any(
                    gcs.get((x, shape, lev, n), 0) > 1
                    for x in (lab, base) for n in ns)
                out.append(f"{'FLAG' if flag else '    '} {lab:6} {shape:9} {lev} {name:5} "
                           + ' '.join(f'{x:.3f}' for x in r) + f'  base^{exp:.2f}'
                           + ('  (collections)' if coll else ''))
    out += fails
    out.append(f'{len(flagged)} flagged; N = {" ".join(map(str, allns))}; base {base}')
    return out, flagged


# The first scaling run: chain and loops at -O by a base (x2), a change whose
# code grows faster than the base's (mw) and one whose compile cost does on
# loops (lf8).
CONTROL = """\
x2 chain O1 50 173518808 702230393 8166
x2 chain O1 100 423615968 1297571650 26180
x2 chain O1 200 1539473288 4138428522 91884
x2 chain O1 400 7901250904 19328225305 344090
x2 loops O1 50 190264256 677332727 3349
x2 loops O1 100 370021096 1502096181 6599
x2 loops O1 200 769855032 3282360327 13099
x2 loops O1 400 1752228576 7831471199 26099
mw chain O1 50 233342536 884614638 14547
mw chain O1 100 760050872 2498123554 53726
mw chain O1 200 3728229600 10435666374 206760
mw chain O1 400 23703650288 58591734877 813626
mw loops O1 50 190369624 677315462 3353
mw loops O1 100 370143400 1500573376 6603
mw loops O1 200 769944040 3283778478 13103
mw loops O1 400 1752481528 7649254974 26103
lf8 chain O1 50 177183664 707025858 8190
lf8 chain O1 100 431696912 1323983293 26204
lf8 chain O1 200 1559457920 4224651644 91908
lf8 chain O1 400 7956272376 19751093641 344114
lf8 loops O1 50 192546856 682835703 2854
lf8 loops O1 100 384008448 1532339506 5604
lf8 loops O1 200 839478096 3492315982 11104
lf8 loops O1 400 2072058096 8473187896 22104
"""


def self_test():
    bad = []
    lines = CONTROL.splitlines() + ['FAILED lf8 nest O1 50: out of memory',
                                    'lf8 nest O1 100 1 2']
    out, flagged = report(lines)
    want = {('mw', 'chain', 'O1', m) for m in ('bytes', 'instr', 'asm')} \
        | {('lf8', 'loops', 'O1', m) for m in ('bytes', 'instr')}
    if flagged != want:
        bad.append(f'flagged {sorted(flagged)}, not {sorted(want)}')
    for x in lines[-2:]:
        if x not in out:
            bad.append(f'{x!r} not reported as a failure')
    same = [x for x in CONTROL.splitlines() if x.startswith('x2 ')]
    _, flagged = report(same + ['x3' + x[2:] for x in same])
    if flagged:
        bad.append(f'a base against itself flagged {sorted(flagged)}')
    # Up 4% in all but down at one doubling, as noise can be: not flagged.
    loops = [x.split() for x in same if ' loops ' in x]
    # answered filtered-zip: CONTROL's x2 loops rows are four, N ascending,
    # one for each ratio
    noisy = [' '.join(['nz'] + f[1:4] + [str(round(int(v) * q)) for v in f[4:7]])
             for f, q in zip(loops, (1.0, 1.05, 1.03, 1.04))]
    _, flagged = report(same + noisy)
    if flagged:
        bad.append(f'a ratio not rising at every doubling flagged {sorted(flagged)}')
    # The eighth field: one collection everywhere but x2 loops at N = 400.
    gl = [x + (' 3' if x.startswith('x2 loops O1 400') else ' 1') for x in same]
    out, _ = report(gl + ['x3' + x[2:] for x in gl])
    marked = [[t for t in x.split() if t != 'FLAG'][:3]
              for x in out if x.endswith('(collections)')]
    if marked != [['x3', 'loops', 'O1']]:
        bad.append(f'collections marked on {marked}, not x3 loops instr')
    # Several files read as one: battery.py writes a file per compiler.
    other = ['x3' + x[2:] for x in same]
    with tempfile.TemporaryDirectory(prefix='ncg-report-') as d:
        for name, part in (('a', same), ('b', other)):
            with open(f'{d}/{name}', 'w') as fh:
                fh.write('\n'.join(part) + '\nscale DONE 12:00:00\n')
        p = subprocess.run([sys.executable, __file__, f'{d}/a', f'{d}/b'],
                           capture_output=True, text=True)
        with open(f'{d}/a') as a, open(f'{d}/b') as b:
            whole = '\n'.join(report(list(a) + list(b))[0]) + '\n'
    if p.returncode or p.stdout != whole or 'x3' not in p.stdout:
        bad.append(f'two files, exit {p.returncode}: {p.stdout[:200]!r}')
    for x in bad:
        print('FAIL', x)
    print('ok   report.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        sys.exit(self_test())
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    lines = []
    for path in sys.argv[1:]:
        with open(path) as f:
            lines += f
    print('\n'.join(report(lines)[0]))
