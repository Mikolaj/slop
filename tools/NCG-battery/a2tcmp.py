#!/usr/bin/env python3
"""battery.py's A2T counts under label B against label A, OUT/a2t-LABEL.tsv:
the cells counted in both, how many are worse by 0.2% and by 1% and the N
(20 by default) worst, how many are better by 0.2% with their median ratio
and the best, and the cells either label has no count of; then the same of
the bytes allocated a call, where both labels' tables carry them (a fourth
column, from 2026-11-07). The thresholds are those the full A2T runs were
read by.

Usage: python3 tools/NCG-battery/a2tcmp.py [--out DIR] A B [N]
       python3 tools/NCG-battery/a2tcmp.py --self-test

OUT is battery.py's, WORK/battery by default."""
import os
import statistics
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from battery import WORK  # noqa: E402

MOVE, BAR = 0.002, 0.01


def load(path, column=1):
    """cell -> instructions a call (column 1) or bytes allocated a call
    (column 3), or None where none were counted."""
    out = {}
    with open(path) as fh:
        for line in fh:
            f = line.rstrip('\n').split('\t')
            if len(f) in (3, 4):
                v = f[column] if column < len(f) else '-'
                out[f[0]] = float(v) if v != '-' else None
    return out


def compare(a, b, ca, cb, n, what='cells counted'):
    both = {c: cb[c] / ca[c] for c in ca if ca[c] and cb.get(c)}
    worse = sorted(((r, c) for c, r in both.items() if r - 1 >= MOVE - 1e-12), reverse=True)
    better = sorted((r, c) for c, r in both.items() if 1 - r >= MOVE - 1e-12)
    out = [f'{a} to {b}: {what} in both {len(both)} of {len(set(ca) | set(cb))}',
           f'  worse by 0.2%: {len(worse)}, by 1%: {sum(r - 1 >= BAR - 1e-12 for r, _ in worse)}']
    out += [f'    {r:.4f}  {c}  {ca[c]} {cb[c]}' for r, c in worse[:n]]
    if better:
        out.append(f'  better by 0.2%: {len(better)}, median ratio'
                   f' {statistics.median(r for r, _ in better):.4f},'
                   f' best {better[0][0]:.4f} ({better[0][1]})')
    else:
        out.append('  better by 0.2%: 0')
    for lab, mine in ((a, ca), (b, cb)):
        miss = sorted(c for c in set(ca) | set(cb) if not mine.get(c))
        if miss:
            out.append(f'  no count under {lab}: {len(miss)}, the first {miss[0]}')
    return '\n'.join(out)


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='a2tcmp-') as d:
        rows = {'a': [('x', '100', 0), ('y', '100', 0), ('z', '100', 0), ('u', '100', 0),
                      ('v', '-', 2)],
                'b': [('x', '101.5', 0), ('y', '99', 0), ('z', '100.1', 0), ('u', '-', 2),
                      ('v', '7', 0)]}
        for lab, rs in rows.items():
            with open(f'{d}/a2t-{lab}.tsv', 'w') as fh:
                fh.write(''.join(f'{c}\t{i}\t{e}\n' for c, i, e in rs))
        # c and e, with the bytes allocated: x allocating 10% more in e.
        for lab, k in (('c', 1.0), ('e', 1.1)):
            with open(f'{d}/a2t-{lab}.tsv', 'w') as fh:
                fh.write(f'x\t100\t0\t{80 * k}\ny\t100\t0\t64.0\nz\t100\t0\t-\n')
        p = subprocess.run([sys.executable, os.path.abspath(__file__), '--out', d, 'a', 'b'],
                           capture_output=True, text=True)
        want = ('a to b: cells counted in both 3 of 5\n'
                '  worse by 0.2%: 1, by 1%: 1\n'
                '    1.0150  x  100.0 101.5\n'
                '  better by 0.2%: 1, median ratio 0.9900, best 0.9900 (y)\n'
                '  no count under a: 1, the first v\n'
                '  no count under b: 1, the first u\n')
        if p.returncode or p.stdout != want:
            bad.append(f'exit {p.returncode}, printed {p.stdout!r} {p.stderr[-200:]}')
        p = subprocess.run([sys.executable, os.path.abspath(__file__), '--out', d, 'c', 'e'],
                           capture_output=True, text=True)
        want = ('c to e: cells counted in both 3 of 3\n  worse by 0.2%: 0, by 1%: 0\n'
                '  better by 0.2%: 0\n'
                'c to e: cells allocating, bytes a call, in both 2 of 3\n'
                '  worse by 0.2%: 1, by 1%: 1\n    1.1000  x  80.0 88.0\n'
                '  better by 0.2%: 0\n  no count under c: 1, the first z\n'
                '  no count under e: 1, the first z\n')
        if p.returncode or p.stdout != want:
            bad.append(f'allocation: exit {p.returncode}, printed {p.stdout!r}')
    for x in bad:
        print('FAIL', x)
    print('ok   a2tcmp.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    out = os.path.join(WORK, 'battery')
    if argv[:1] == ['--out'] and len(argv) > 1:
        out, argv = argv[1], argv[2:]
    if len(argv) not in (2, 3) or (len(argv) == 3 and not argv[2].isdigit()):
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    a, b = argv[:2]
    n = int(argv[2]) if len(argv) == 3 else 20
    try:
        ca, cb = (load(os.path.join(out, f'a2t-{x}.tsv')) for x in (a, b))
        aa, ab = (load(os.path.join(out, f'a2t-{x}.tsv'), 3) for x in (a, b))
    except OSError as e:
        print(e, file=sys.stderr)
        return 2
    print(compare(a, b, ca, cb, n))
    if any(aa.values()) and any(ab.values()):
        print(compare(a, b, aa, ab, n, 'cells allocating, bytes a call,'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
