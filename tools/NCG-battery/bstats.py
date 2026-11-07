#!/usr/bin/env python3
"""The figures of a label's builds, taken before rebuild.py prunes them: each
module's compile time and allocation, from `-ddump-timings -ddump-to-file`,
and its object's size; each compiler process's instructions:u and bytes
allocated, from battery.py's compiler wrapper; GHC's own build's wall time
and instructions:u; and two labels' figures compared.

Usage: python3 tools/NCG-battery/bstats.py ghc TREEDIR OUT HPERF WALL
       python3 tools/NCG-battery/bstats.py pkgs WORK TREE LABEL OUT
       python3 tools/NCG-battery/bstats.py compare [--out DIR] A B
       python3 tools/NCG-battery/bstats.py --self-test

`ghc` walks a hadrian tree built with rebuild.py's settings, its _build's
stageBoot (utilities by the bootstrap compiler), stage0 (the stage-1
compiler and its libraries, by the bootstrap compiler) and stage1 (the
stage-2 compiler and the libraries, by the stage-1 compiler), and writes
OUT, GHC's build: a row a module and figure, and the build's wall time
(WALL, seconds) and instructions:u (HPERF, `perf stat -x,`'s file). `pkgs`
walks battery.py's builds of the label: containers, vector and megaparsec
at -O2 and -O1 and A2T, their build directories and the wrapper's records,
and writes OUT. rebuild.py writes OUT/ghcb-LABEL.tsv and OUT/pkgb-LABEL.tsv,
OUT being WORK/battery.

A row is `kind build key figure value`. kind module: key is the object's
path below the build's root (a hadrian stage directory, or a cabal build
directory with its `ghc-VERSION` component dropped, so that two compilers'
builds share keys), figure ms, alloc (the passes' sums, as
tools/ctime-diff.py sums them) or size (the object's bytes); a module's dump
is joined to the object of its module name (the dump's `[M]`) in the
nearest directory above the dump holding it, as GHC's -outputdir puts the
dump under the source's own path; an object without a dump, a C file's or
a .cmm's in another way, has its size alone. kind process: key is the
unit (`-this-unit-id` without its hash) and `link` where the run links,
figure instructions, alloc and peak_mb (the RTS's peak_megabytes_allocated);
for GHC's build, key hadrian, figures instructions and wall_s.

`compare` prints, per build, the modules and processes in both, the summed
figures' ratios B/A, and every row moving by its threshold either way:
a module's allocation by 0.1% and its size by 0.2%, a process's
instructions by 1% and its allocation by 0.1% (Mikolaj, 2026-11-07, for the
compile instructions and object size; the battery's compile-allocation bar
for the rest); time only summed. Builds of vector by one compiler, and by
two compilers of the same sources in trees of one path length (2026-11-07),
differed by at most 0.2% in a module's allocation, 0.003% in the sum, 0.83%
in a process's instructions and 0.17% in its allocation, the objects equal:
a lone row near its bar is noise until repeated. With a store's path of
another length a module moved by 2.25%, so compare labels whose paths are
equally long, as rebuild.py's are.
Exits 0 when it compared, 2 when a label has neither table.
"""

import glob
import math
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from battery import PKGS, WORK  # noqa: E402

# tools/ctime-diff.py's: a pass GHC timed, with its module in brackets.
PASS = re.compile(r'^.*? \[(.*?)\]: alloc=(\d+) time=([\d.]+)\s*$')
OBJ = re.compile(r'\.(?:[a-z_]*_)?o$')
VERSION_DIR = re.compile(r'^ghc-[0-9.]+$')
HASH = re.compile(r'-[0-9a-f]{64}$')
STAGES = ('stageBoot', 'stage0', 'stage1')
BARS = {'alloc': 0.001, 'size': 0.002, 'instructions': 0.01}
PLURAL = {'module': 'modules', 'process': 'processes'}


def dump_figures(path):
    """(module, ms, bytes) of a .dump-timings file; module None where no
    pass named one."""
    mod, ms, alloc = None, 0.0, 0
    with open(path, errors='replace') as fh:
        for line in fh:
            m = PASS.match(line)
            if m:
                if mod is None and '/' not in m.group(1):
                    mod = m.group(1)
                alloc += int(m.group(2))
                ms += float(m.group(3))
    return mod, ms, alloc


def normal(rel):
    return '/'.join(p for p in rel.split('/') if not VERSION_DIR.match(p))


def modules(root):
    """key -> {figure: value} of the objects and dumps under root."""
    out, dumps = {}, []
    for dp, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            if f.endswith('.dump-timings'):
                dumps.append(p)
            elif OBJ.search(f) and os.path.isfile(p):
                out.setdefault(normal(os.path.relpath(p, root)), {})['size'] = os.path.getsize(p)
    for p in sorted(dumps):
        mod, ms, alloc = dump_figures(p)
        key = None
        if mod:
            d = os.path.dirname(p)
            while key is None and len(d) >= len(root):
                o = os.path.join(d, *mod.split('.')) + '.o'
                if os.path.isfile(o):
                    key = normal(os.path.relpath(o, root))
                d = os.path.dirname(d)
        if key is None:
            key = normal(os.path.relpath(p, root))[:-len('.dump-timings')]
        f = out.setdefault(key, {})
        f['ms'] = f.get('ms', 0.0) + ms
        f['alloc'] = f.get('alloc', 0) + alloc
    return out


def perf_count(path):
    with open(path) as fh:
        for line in fh:
            x = line.split(',')
            if len(x) > 2 and x[2].startswith('instructions') and x[0].isdigit():
                return int(x[0])
    return None


def rts_stats(path):
    with open(path) as fh:
        text = fh.read()
    return {k: int(v) for k, v in re.findall(r'\("([a-z_ ]+)", "(\d+)"\)', text)}


def processes(sdir):
    """key -> {figure: value} of the wrapper's records in sdir."""
    out = {}
    for a in sorted(glob.glob(os.path.join(sdir, '*.args'))):
        with open(a) as fh:
            args = fh.read().split('\n')[1:]
        unit = (args[args.index('-this-unit-id') + 1] if '-this-unit-id' in args
                else os.path.basename(args[args.index('-o') + 1]) if '-o' in args else 'ghc')
        key = HASH.sub('', unit) + (' link' if '-o' in args and '-no-link' not in args else '')
        n = 2
        while key in out:
            key = f'{key.split(" #")[0]} #{n}'
            n += 1
        f = out[key] = {}
        stem = a[:-len('.args')]
        if os.path.exists(stem + '.csv'):
            c = perf_count(stem + '.csv')
            if c is not None:
                f['instructions'] = c
        if os.path.exists(stem + '.rts'):
            s = rts_stats(stem + '.rts')
            if 'bytes allocated' in s:
                f['alloc'] = s['bytes allocated']
            if 'peak_megabytes_allocated' in s:
                f['peak_mb'] = s['peak_megabytes_allocated']
    return out


def rows(kind, build, figs):
    return [(kind, build, k, fig, v) for k in sorted(figs) for fig, v in sorted(figs[k].items())]


def write(out, rs):
    with open(out, 'w') as fh:
        for r in rs:
            v = r[4]
            fh.write('\t'.join(r[:4]) + '\t' + (f'{v:.3f}' if isinstance(v, float) else str(v)) + '\n')


def ghc_rows(tree, hperf, wall):
    rs = []
    for s in STAGES:
        root = os.path.join(tree, '_build', s)
        if os.path.isdir(root):
            rs += rows('module', f'ghc/{s}', modules(root))
    f = {'wall_s': int(wall)}
    if hperf and os.path.exists(hperf):
        c = perf_count(hperf)
        if c is not None:
            f['instructions'] = c
    return rs + rows('process', 'ghc', {'hadrian': f})


def builds(work, tree, label):
    """(build name, build directory, wrapper records) of the label's builds."""
    v = f'{work}/vpapi'
    out = []
    for lev, lab in (('O2', f'c{tree}-{label}'), ('O1', f'c{tree}-o1-{label}')):
        for pkg, p in PKGS.items():
            d = f'{v}/{p["builddir"]}-{lab}'
            out.append((f'{pkg}-{lev}', d, f'{v}/wstats-{p["builddir"]}-{lab}'))
    c = f'c{tree}-{label}'
    out.append(('a2t', f'{v}/adist-{c}', f'{v}/wstats-adist-{c}'))
    return out


def pkg_rows(work, tree, label):
    rs = []
    for name, d, sdir in builds(work, tree, label):
        if os.path.isdir(d):
            arch = glob.glob(os.path.join(d, 'build', '*-*'))
            rs += rows('module', name, modules(arch[0] if len(arch) == 1 else d))
        if os.path.isdir(sdir):
            rs += rows('process', name, processes(sdir))
    return rs


def load(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            f = line.rstrip('\n').split('\t')
            if len(f) == 5:
                out[tuple(f[:4])] = float(f[4])
    return out


def compare(ta, tb, a, b):
    out = [f'{b} against {a}']
    groups = sorted({(k[0], k[1]) for k in set(ta) | set(tb)})
    for kind, build in groups:
        ka = {k for k in ta if k[:2] == (kind, build)}
        kb = {k for k in tb if k[:2] == (kind, build)}
        keys = {k[2] for k in ka & kb}
        only = (len({k[2] for k in ka} - {k[2] for k in kb}),
                len({k[2] for k in kb} - {k[2] for k in ka}))
        figs = sorted({k[3] for k in ka & kb})
        tot = []
        for fig in figs:
            both = [k for k in ka & kb if k[3] == fig and ta[k] and tb[k]]
            sa, sb = sum(ta[k] for k in both), sum(tb[k] for k in both)
            if sa:
                tot.append(f'{fig} {sb / sa:.5f}')
        out.append(f'{PLURAL[kind]} of {build}: {len(keys)} in both (only {a}: {only[0]},'
                   f' only {b}: {only[1]}); totals B/A: {", ".join(tot) or "none"}')
        for fig in figs:
            bar = BARS.get(fig)
            if bar is None:
                continue
            moved = []
            for k in ka & kb:
                if k[3] != fig:
                    continue
                x, y = ta[k], tb[k]
                r = y / x - 1 if x else (math.inf if y else 0.0)
                if abs(r) >= bar - 1e-12:
                    moved.append((r, k[2], x, y))
            up = sorted((m for m in moved if m[0] > 0), reverse=True)
            dn = sorted(m for m in moved if m[0] < 0)
            out.append(f'  {fig} by {bar:.1%}: {len(up)} up, {len(dn)} down')
            out += [f'    {r * 100:+.3f}%  {key}  {x:.0f} {y:.0f}' for r, key, x, y in up + dn]
    return out


def load_label(out, label):
    t, found = {}, 0
    for kind in ('ghcb', 'pkgb'):
        p = os.path.join(out, f'{kind}-{label}.tsv')
        if os.path.exists(p):
            t.update(load(p))
            found += 1
    if not found:
        raise ValueError(f'no {out}/ghcb-{label}.tsv or pkgb-{label}.tsv')
    return t


# --- self-test: a planted hadrian tree and cabal build directories in their
# layouts, wrapper records, and the comparison of two labels.

def put(path, text=''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(text)


def tim(mod, *allocs):
    return ''.join(f'P{i} [{mod}]: alloc={x} time=1.5\n' for i, x in enumerate(allocs)) \
        + f'WriteIface [_build/x/{mod}.hi]: alloc=7 time=0.5\nsystool:as: alloc=99 time=9\n'


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='bstats-') as d:
        t = f'{d}/ghc-t/_build'
        # GHC.Core: its dump under the source's path, its object two levels up.
        put(f'{t}/stage0/compiler/build/compiler/GHC/Core.dump-timings', tim('GHC.Core', 100, 50))
        put(f'{t}/stage0/compiler/build/GHC/Core.o', 'x' * 40)
        put(f'{t}/stage0/compiler/build/GHC/Core.o-boot')
        put(f'{t}/stage1/libraries/base/build/libraries/base/src/Data/List.dump-timings',
            tim('Data.List', 10))
        put(f'{t}/stage1/libraries/base/build/Data/List.o', 'x' * 8)
        put(f'{t}/stage1/rts/build/cmm/Apply.thr_o', 'x' * 3)
        put(f'{t}/stage1/rts/build/c/Weak.o', 'x' * 5)
        put(f'{t}/stageBoot/utils/u/build/utils/u/Main.dump-timings', tim('Main', 2))
        put(f'{t}/stageBoot/utils/u/build/Main.o', 'x')
        put(f'{d}/hperf.csv', '# started\n\n12345,,instructions:u,9,100.00,,\n')
        got = {(r[1], r[2], r[3]): r[4] for r in ghc_rows(f'{d}/ghc-t', f'{d}/hperf.csv', 61.7)}
        want = {('ghc/stage0', 'compiler/build/GHC/Core.o', 'alloc'): 157,
                ('ghc/stage0', 'compiler/build/GHC/Core.o', 'ms'): 3.5,
                ('ghc/stage0', 'compiler/build/GHC/Core.o', 'size'): 40,
                ('ghc/stage1', 'libraries/base/build/Data/List.o', 'alloc'): 17,
                ('ghc/stage1', 'libraries/base/build/Data/List.o', 'size'): 8,
                ('ghc/stage1', 'rts/build/cmm/Apply.thr_o', 'size'): 3,
                ('ghc/stage1', 'rts/build/c/Weak.o', 'size'): 5,
                ('ghc/stageBoot', 'utils/u/build/Main.o', 'alloc'): 9,
                ('ghc', 'hadrian', 'instructions'): 12345, ('ghc', 'hadrian', 'wall_s'): 61}
        if {k: got.get(k) for k in want} != want or len(got) != 13 \
                or any('o-boot' in k[1] for k in got):
            bad.append(f'GHC build rows: {sorted(got.items())}')
        # Cabal's layout: a library and a benchmark, the version dropped.
        w = f'{d}/w'
        cd = f'{w}/vpapi/cdist-ct-x/build/x86_64-linux/ghc-10.1.20261107/containers-tests-0'
        put(f'{cd}/build/Data/Map.dump-timings', tim('Data.Map', 300))
        put(f'{cd}/build/Data/Map.o', 'x' * 30)
        put(f'{cd}/b/map-benchmarks/build/map-benchmarks/map-benchmarks-tmp/benchmarks/Map.dump-timings',
            tim('Main', 4))
        put(f'{cd}/b/map-benchmarks/build/map-benchmarks/map-benchmarks-tmp/Main.o', 'x' * 6)
        s = f'{w}/vpapi/wstats-cdist-ct-x'
        lib = ['--make', '-this-unit-id', 'containers-tests-0-inplace', 'Data.Map']
        dep = ['--make', '-this-unit-id', 'primitive-0.9.1.0-' + 'a' * 64]
        exe = ['--make', '-this-unit-id', 'containers-tests-0-inplace-map-benchmarks', '-o', 'x/m']
        for i, (args, ins, alloc) in enumerate(((lib, 1000, 500), (dep, 77, 66), (exe, 10, 5),
                                                (exe, 11, 6))):
            put(f'{s}/{i}.args', '\n'.join(['/x'] + args) + '\n')
            put(f'{s}/{i}.csv', f'# started\n\n{ins},,instructions:u,9,100.00,,\n')
            put(f'{s}/{i}.rts', f' [("bytes allocated", "{alloc}")\n ,("peak_megabytes_allocated", "9")\n ]\n')
        got = {(r[1], r[2], r[3]): r[4] for r in pkg_rows(w, 't', 'x')}
        want = {('containers-O2', 'containers-tests-0/build/Data/Map.o', 'alloc'): 307,
                ('containers-O2', 'containers-tests-0/b/map-benchmarks/build/map-benchmarks/'
                 'map-benchmarks-tmp/Main.o', 'size'): 6,
                ('containers-O2', 'containers-tests-0-inplace', 'instructions'): 1000,
                ('containers-O2', 'primitive-0.9.1.0', 'alloc'): 66,
                ('containers-O2', 'containers-tests-0-inplace-map-benchmarks link', 'instructions'): 10,
                ('containers-O2', 'containers-tests-0-inplace-map-benchmarks link #2', 'peak_mb'): 9}
        if {k: got.get(k) for k in want} != want:
            bad.append(f'package rows: {sorted(got.items())}')
        # Two labels: allocation and size by their bars, instructions by 1%.
        ta = {('module', 'g', 'm1', 'alloc'): 1000.0, ('module', 'g', 'm2', 'alloc'): 1000.0,
              ('module', 'g', 'm1', 'size'): 1000.0, ('module', 'g', 'm3', 'size'): 100.0,
              ('module', 'g', 'm1', 'ms'): 5.0,
              ('process', 'g', 'p', 'instructions'): 1000.0}
        tb = dict(ta)
        tb.update({('module', 'g', 'm1', 'alloc'): 1001.0, ('module', 'g', 'm2', 'alloc'): 999.0,
                   ('module', 'g', 'm1', 'size'): 1003.0, ('module', 'g', 'm1', 'ms'): 50.0,
                   ('process', 'g', 'p', 'instructions'): 989.0})
        del tb[('module', 'g', 'm3', 'size')]
        got = compare(ta, tb, 'A', 'B')
        want = ['B against A',
                'modules of g: 2 in both (only A: 1, only B: 0); totals B/A: alloc 1.00000,'
                ' ms 10.00000, size 1.00300',
                '  alloc by 0.1%: 1 up, 1 down', '    +0.100%  m1  1000 1001',
                '    -0.100%  m2  1000 999', '  size by 0.2%: 1 up, 0 down',
                '    +0.300%  m1  1000 1003',
                'processes of g: 1 in both (only A: 0, only B: 0); totals B/A: instructions 0.98900',
                '  instructions by 1.0%: 0 up, 1 down', '    -1.100%  p  1000 989']
        if got != want:
            bad.append('compare:\n  ' + '\n  '.join(got))
        put(f'{d}/out/ghcb-A.tsv')
        if main(['compare', '--out', f'{d}/out', 'A', 'Z']) != 2:
            bad.append('a label with no table did not exit 2')
    for x in bad:
        print('FAIL', x)
    print('ok   bstats.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    if len(argv) == 5 and argv[0] == 'ghc':
        write(argv[2], ghc_rows(argv[1], argv[3], float(argv[4])))
        return 0
    if len(argv) == 5 and argv[0] == 'pkgs':
        write(argv[4], pkg_rows(argv[1], argv[2], argv[3]))
        return 0
    if argv[:1] == ['compare']:
        out, rest = os.path.join(WORK, 'battery'), argv[1:]
        if rest[:1] == ['--out'] and len(rest) > 1:
            out, rest = rest[1], rest[2:]
        if len(rest) == 2:
            try:
                ta, tb = load_label(out, rest[0]), load_label(out, rest[1])
            except ValueError as e:
                print(e, file=sys.stderr)
                return 2
            print('\n'.join(compare(ta, tb, *rest)))
            return 0
    print(__doc__.split('\n\n')[1], file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
