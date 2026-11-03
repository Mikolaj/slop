#!/usr/bin/env python3
"""containers' PROGRAM benchmark BENCHMARK (the CSV's name, as `All.x.y`) run
alone, tasty's -p matching the whole name, N times (3 by default) with
address-space randomisation off, under battery.py's builds vpapi/cdist-A and
vpapi/cdist-B of the work directory (the results' names, cTREE-LABEL or
cTREE-o1-LABEL); prints each run's TOT_INS and B's lowest against A's. A rise
in the battery's runs, where every benchmark of a program runs in one
process, is the code's only if it holds alone.

Usage: python3 tools/NCG-battery/alone.py [--work DIR] A B PROGRAM BENCHMARK [N]
       python3 tools/NCG-battery/alone.py --self-test

The work directory is battery.py's, dist-ghcho by default."""
import csv
import glob
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from battery import WORK  # noqa: E402

SETARCH = ['setarch', '-R']


def binary(v, label, prog):
    g = glob.glob(f'{v}/cdist-{label}/build/x86_64-linux/*/containers-tests-0'
                  f'/b/{prog}/build/{prog}/{prog}')
    if len(g) != 1:
        raise ValueError(f'{len(g)} binaries of {prog} under {v}/cdist-{label}')
    return g[0]


def pattern(bench):
    return '$0 == "%s"' % bench.replace('\\', '\\\\').replace('"', '\\"')


def runs(v, label, prog, bench, n):
    out, b = [], binary(v, label, prog)
    for _ in range(n):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, 'r.csv')
            subprocess.run(SETARCH + [b, '-j1', '-p', pattern(bench), '--csv', f],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True)
            with open(f) as fh:
                rows = [r for r in csv.DictReader(fh) if r['benchmark'] == bench]
            if len(rows) != 1:
                raise ValueError(f'{label}: {len(rows)} rows named {bench}')
            out.append(int(rows[0]['TOT_INS']))
    return out


def alone(v, a, b, prog, bench, n=3):
    ra, rb = runs(v, a, prog, bench, n), runs(v, b, prog, bench, n)
    return f'{prog} {bench}: {a} {ra} {b} {rb} {100 * (min(rb) / min(ra) - 1):+.3f}%'


# A fake benchmark program: its -p pattern decoded as tasty's $0 == "..."
# reads, a row for that name, TOT_INS from its build's label and a counter.
FAKE = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
p, f = a[a.index('-p') + 1], a[a.index('--csv') + 1]
assert p.startswith('$0 == "') and p.endswith('"'), p
name, it = '', iter(p[7:-1])
for ch in it:
    if ch == '"':
        sys.exit('a quote unescaped: ' + p)
    if ch == '\\':
        ch = next(it)
        if ch not in '"\\':
            sys.exit('no such escape: ' + p)
    name += ch
here = os.path.dirname(os.path.abspath(__file__))
k = len(open(os.environ['FAKELOG']).read().split('\n')) - 1
base = 1000 if '/cdist-A/' in here else 1010
ins = base + (k % 3 if base == 1000 else 0)
open(f, 'w').write('benchmark,ALLOC,TOT_INS\n"%s",1,%d\n"other",1,5\n'
                   % (name.replace('"', '""'), ins))
open(os.environ['FAKELOG'], 'a').write('bench\n')
'''
FAKE_SETARCH = ('#!/bin/sh\necho "setarch $1" >> "$FAKELOG"\n'
                'shift\nexec "$@"\n')


def self_test():
    bad = []
    bench = 'All.q "r" \\s'
    with tempfile.TemporaryDirectory(prefix='alone-') as d:
        for lab in ('A', 'B'):
            p = f'{d}/v/cdist-{lab}/build/x86_64-linux/ghc-9/containers-tests-0/b/m/build/m'
            os.makedirs(p)
            with open(f'{p}/m', 'w') as fh:
                fh.write(FAKE)
            os.chmod(f'{p}/m', 0o755)
        os.makedirs(f'{d}/bin')
        with open(f'{d}/bin/setarch', 'w') as fh:
            fh.write(FAKE_SETARCH)
        os.chmod(f'{d}/bin/setarch', 0o755)
        log = f'{d}/log'
        open(log, 'w').close()
        env = dict(os.environ)
        os.environ.update(FAKELOG=log, PATH=f'{d}/bin' + os.pathsep + env['PATH'])
        try:
            got = alone(f'{d}/v', 'A', 'B', 'm', bench)
        except (ValueError, subprocess.CalledProcessError) as e:
            got = repr(e)
        finally:
            os.environ.clear()
            os.environ.update(env)
        want = (f'm {bench}: A [1001, 1000, 1002] B [1010, 1010, 1010] +1.000%')
        if got != want:
            bad.append(f'{got!r}, not {want!r}')
        calls = open(log).read().split('\n')[:-1]
        if calls != ['setarch -R', 'bench'] * 6:
            bad.append(f'the runs were {calls}')
        try:
            binary(f'{d}/v', 'C', 'm')
            bad.append('a missing build raised nothing')
        except ValueError:
            pass
    for x in bad:
        print('FAIL', x)
    print('ok   alone.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    work = WORK
    if argv[:1] == ['--work'] and len(argv) > 1:
        work, argv = argv[1], argv[2:]
    if len(argv) not in (4, 5) or (len(argv) == 5 and not argv[4].isdigit()):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(alone(os.path.join(work, 'vpapi'), *argv[:4],
                    int(argv[4]) if len(argv) == 5 else 3))
    except (ValueError, subprocess.CalledProcessError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
