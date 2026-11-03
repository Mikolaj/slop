#!/usr/bin/env python3
"""battery.py's tasty-papi counts of a package under label B against label A,
from the work directory's vpapi: containers' cres/LABEL/PROGRAM-I.csv,
megaparsec's mres/LABEL/bench-speed-I.csv, vector's res-LABEL-I.csv. The
labels are the results' names, cTREE-LABEL at -O2 and cTREE-o1-LABEL at -O1.

Usage: python3 tools/NCG-battery/pkgcmp.py [--work DIR] containers A B [N]
       python3 tools/NCG-battery/pkgcmp.py [--work DIR] megaparsec A B [N]
       python3 tools/NCG-battery/pkgcmp.py [--work DIR] vector A B
       python3 tools/NCG-battery/pkgcmp.py --self-test

containers and megaparsec mind the runs' spread: a benchmark whose runs agree
within 0.05% in both labels is compared by its minimum, moving if by more than
0.05%; any other moves only where the two labels' ranges do not overlap. Prints
how many rise and fall, the geometric mean of the minima's ratios over the
stable ones, and the N (20 by default) largest rises and falls, then every
benchmark whose lowest ALLOC differs, up to N each way. vector prints, per
benchmark, ALLOC's change and the minimum TOT_INS over each label's runs, with
the geometric mean of the TOT_INS ratios. tasty-papi's CSVs carry ALLOC beside
the counters and no collections or copied bytes, so a rise here cannot be told
mutator from collector. The work directory is battery.py's, dist-ghcho by
default."""
import csv
import glob
import math
import os
import re
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from battery import WORK  # noqa: E402

TOL = 0.0005
DIRS = {'containers': 'cres', 'megaparsec': 'mres'}


def rows(path):
    with open(path) as fh:
        return {r['benchmark']: r for r in csv.DictReader(fh)}


def load_spread(v, d, label, column='TOT_INS'):
    runs = defaultdict(list)
    for p in glob.glob(os.path.join(v, d, label, '*.csv')):
        prog = re.match(r'(.*)-\d+\.csv$', os.path.basename(p)).group(1)
        runs[prog].append(rows(p))
    if not runs:
        raise ValueError(f'no runs in {os.path.join(v, d, label)}')
    return {f'{prog}/{b}': [int(r[b][column]) for r in rs if b in r]
            for prog, rs in runs.items() for b in rs[0]}


def spread(v, d, a, b, n=20):
    A, B = load_spread(v, d, a), load_spread(v, d, b)
    stable, moved, logs = 0, [], []
    for k, va in A.items():
        vb = B.get(k)
        if not vb:
            continue
        la, ha, lb, hb = min(va), max(va), min(vb), max(vb)
        if ha <= la * (1 + TOL) and hb <= lb * (1 + TOL):
            stable += 1
            logs.append(math.log(lb / la))
            if abs(lb / la - 1) > TOL:
                moved.append((lb / la - 1, k, la, lb, 'stable'))
        elif lb > ha:
            moved.append((lb / ha - 1, k, f'{la}..{ha}', f'{lb}..{hb}', 'disjoint'))
        elif hb < la:
            moved.append((hb / la - 1, k, f'{la}..{ha}', f'{lb}..{hb}', 'disjoint'))
    rises = sorted((m for m in moved if m[0] > 0), reverse=True)
    falls = sorted(m for m in moved if m[0] < 0)
    gm = (f'{(math.exp(sum(logs) / len(logs)) - 1) * 100:+.3f}%' if logs
          else 'none')
    out = [f'{b} against {a}: {len(A)} benchmarks, {stable} stable in both; '
           f'{len(rises)} rise, {len(falls)} fall; geometric mean over the stable '
           + gm]
    for title, sel in (('rises', rises[:n]), ('falls', falls[:n])):
        out.append(title)
        for dd, k, x, y, how in sel:
            out.append(f'  {k[:80]:80} {x!s:>22} {y!s:>22} {dd * 100:+.3f}% {how}')
    return out + allocation(load_spread(v, d, a, 'ALLOC'),
                            load_spread(v, d, b, 'ALLOC'), n)


def allocation(A, B, n):
    """The lines of the benchmarks whose lowest ALLOC differs, rises then falls,
    a base of 0 counting as 1."""
    moved = sorted(((min(B[k]) / max(min(va), 1) - 1, k, min(va), min(B[k]))
                    for k, va in A.items() if B.get(k) and min(B[k]) != min(va)),
                   reverse=True)
    rises = [m for m in moved if m[0] > 0]
    falls = [m for m in moved if m[0] < 0]
    return ([f'allocation: {len(moved)} benchmarks differ in their lowest ALLOC,'
             f' {len(rises)} rise, {len(falls)} fall']
            + [f'  {k[:80]:80} {x!s:>22} {y!s:>22} {dd * 100:+.3f}%'
               for dd, k, x, y in rises[:n] + falls[-n:]])


def load_vector(v, label):
    runs = [rows(p) for p in sorted(glob.glob(os.path.join(v, f'res-{label}-*.csv')))]
    if not runs:
        raise ValueError(f'no runs {os.path.join(v, f"res-{label}-*.csv")}')
    return len(runs), {b: (min(int(r[b]['ALLOC']) for r in runs),
                           max(int(r[b]['ALLOC']) for r in runs),
                           min(int(r[b]['TOT_INS']) for r in runs))
                       for b in runs[0]}


def vector(v, a, b):
    na, A = load_vector(v, a)
    nb, B = load_vector(v, b)
    out = [f'{b} against {a} ({nb} and {na} runs): benchmark, ALLOC change,'
           f' TOT_INS {a}, {b}, change']
    logs = []
    for k in A:
        if k not in B:
            out.append(f'missing in {b} {k}')
            continue
        (aa, ab, ia), (ba, bb, ib) = A[k], B[k]
        da = '' if aa == ab and ba == bb else ' (alloc varies)'
        ch = (ib / ia - 1) * 100
        logs.append(math.log(ib / ia))
        out.append(f'{k[:72]:72} alloc {(ba / aa - 1) * 100 if aa else 0:+.3f}%{da}'
                   f'  ins {ia} {ib} {ch:+.3f}%')
    gm = (f'{(math.exp(sum(logs) / len(logs)) - 1) * 100:+.3f}%' if logs
          else 'none')
    out.append(f'geometric mean TOT_INS {gm} over {len(logs)}')
    return out


ALLOCS = {('B', 'All.s'): 110, ('B', 'All.u'): 50, ('A', 'All.d'): 0,
          ('B', 'All.d'): 32768}


def write_csv(path, recs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write('benchmark,ALLOC,TOT_INS,TOT_CYC,BR_INS,BR_MSP\n')
        for name, alloc, ins in recs:
            fh.write(f'"{name}",{alloc},{ins},1,1,1\n')


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='pkgcmp-') as v:
        # TOT_INS of each benchmark in each label's two runs: s rises 1% and
        # stable, u stable and unmoved, d and f move with disjoint ranges, o
        # overlaps, m is A's alone.
        ins = {'A': {'All.s': (1000, 1000), 'All.u': (500, 500),
                     'All.d': (1000, 1010), 'All.o': (1000, 1010),
                     'All.f': (1000, 1010), 'All.m': (7, 7)},
               'B': {'All.s': (1010, 1010), 'All.u': (500, 500),
                     'All.d': (1100, 1105), 'All.o': (1005, 1020),
                     'All.f': (900, 950)}}
        for lab, bs in ins.items():
            for i in (0, 1):
                write_csv(f'{v}/cres/{lab}/p-{i + 1}.csv',
                          [(k, ALLOCS.get((lab, k), 100), x[i]) for k, x in bs.items()])
        got = spread(v, 'cres', 'A', 'B')
        want = ['B against A: 6 benchmarks, 2 stable in both; 2 rise, 1 fall;'
                ' geometric mean over the stable +0.499%', 'rises',
                ('p/All.d', '1000..1010', '1100..1105', '+8.911%', 'disjoint'),
                ('p/All.s', '1000', '1010', '+1.000%', 'stable'), 'falls',
                ('p/All.f', '1000..1010', '900..950', '-5.000%', 'disjoint'),
                'allocation: 3 benchmarks differ in their lowest ALLOC, 2 rise, 1 fall',
                ('p/All.d', '0', '32768', '+3276700.000%'),
                ('p/All.s', '100', '110', '+10.000%'),
                ('p/All.u', '100', '50', '-50.000%')]
        got = [x if not x.startswith('  ') else tuple(x.split()) for x in got]
        if got != want:
            bad.append(f'containers: {got}')
        # vector: a's allocation up 10% and instructions down 1%, b's
        # allocation varying in B, c A's alone.
        for lab, recs in (('A', [[('All.a', 100, 1000), ('All.b', 50, 2000),
                                  ('All.c', 1, 1)],
                                 [('All.a', 100, 1001), ('All.b', 50, 2000),
                                  ('All.c', 1, 1)]]),
                          ('B', [[('All.a', 110, 995), ('All.b', 50, 2000)],
                                 [('All.a', 110, 990), ('All.b', 51, 2001)]])):
            for i, r in enumerate(recs):
                write_csv(f'{v}/res-{lab}-{i + 1}.csv', r)
        got = vector(v, 'A', 'B')
        want = ['B against A (2 and 2 runs): benchmark, ALLOC change,'
                ' TOT_INS A, B, change',
                f'{"All.a":72} alloc +10.000%  ins 1000 990 -1.000%',
                f'{"All.b":72} alloc +0.000% (alloc varies)  ins 2000 2000 +0.000%',
                'missing in B All.c', 'geometric mean TOT_INS -0.501% over 2']
        if got != want:
            bad.append(f'vector: {got}')
    for x in bad:
        print('FAIL', x)
    print('ok   pkgcmp.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    work = WORK
    if argv[:1] == ['--work'] and len(argv) > 1:
        work, argv = argv[1], argv[2:]
    v = os.path.join(work, 'vpapi')
    try:
        if argv[:1] == ['vector'] and len(argv) == 3:
            out = vector(v, *argv[1:])
        elif argv[:1] and argv[0] in DIRS and len(argv) in (3, 4):
            n = int(argv[3]) if len(argv) == 4 else 20
            out = spread(v, DIRS[argv[0]], argv[1], argv[2], n)
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    print('\n'.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
