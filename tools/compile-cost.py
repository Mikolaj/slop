#!/usr/bin/env python3
"""The cost of compiling a set of modules with each of several GHCs: the
compiler's instructions, allocation and collections, counted natively, and
whether the assembly differs; or, under cachegrind, where in the compiler
the instructions go.

Usage: python3 tools/compile-cost.py [--cpu CPU] [--rounds R] [--rts OPTS]
           [--cells CELLS] [--tests DIR] [--cmm FILE] [--keep-s DIR]
           [--out FILE] LABEL=GHC[@LIBDIR] [LABEL=GHC[@LIBDIR] ...]
       python3 tools/compile-cost.py compare FILE...
       python3 tools/compile-cost.py cg [--cpu CPU] OUT -- COMMAND...
       python3 tools/compile-cost.py cg-show CG
       python3 tools/compile-cost.py cg-diff CG_A CG_B
       python3 tools/compile-cost.py --self-test

Each LABEL=GHC is a compiler, a stage-1 one such as a hadrian tree's
_build/stage0/bin/ghc or a copy of it, with `-B LIBDIR` passed where
@LIBDIR is given (a copied binary does not find its tree's libdir). Each
cell of CELLS, a comma-separated list of NAME:LEVEL, compiles NAME.hs of
--tests DIR (a GHC checkout's testsuite/tests/perf/compiler) or, for the
name MBB, the --cmm FILE (!16269's generated ManyBasicBlocks.cmm), at
LEVEL with -S: by default the fifteen of the NCG series' measurements, T3294,
T12707, T783 and T9961 at -O0, -O and -O2 and MBB at -O0, -O1 and -O2.
Every compile runs under `perf stat -e instructions:u`, with address-space
randomisation off (`setarch -R`) and, with --cpu, pinned to CPU, its RTS
options GHC's own followed by OPTS, `-A3G -V0` by default, and its RTS
statistics read from `+RTS -t --machine-readable`. R rounds (3 by
default), the compilers' order rotated by one from round to round, each
cell compiled by every compiler before the next cell.

Why -A3G: with GHC's own RTS options (-H, the heap sized after each major
collection), the collections fall at different points from one run to
the next at byte-equal allocation, and ManyBasicBlocks at -O1, 42% of
whose instructions are the collector's, spread 0.3% over three runs
of one compiler; with an allocation area larger than all a compile
allocates there is one collection, and the counts repeat within 0.003%
(rx-47 of the NCG series, 2026-11-03; -V0 alone did not settle them,
the collections numbering 229 to 232). A compile allocating
more than the area collects again, and its instructions then include
the collector's work at points that move: the report says so, and a
larger -A or the allocation alone is the remedy. Under it the
instructions are the mutator's: what a change saves or costs in
collection shows in the allocation, the copied bytes and the collections,
printed beside them, not in the instructions; and wall time and cycles
under it are not a user's, so neither is counted.

Prints, per cell, each compiler's lowest instruction count over the rounds,
its allocation and collections, and for every compiler after the first its
figures against the first's and whether its assembly is the same. With
--keep-s the first round's assembly is kept as DIR/LABEL-NAME-LEVEL.s;
with --out every run is appended to FILE as "label name level round
instructions allocated collections copied assembly-hash". compare reads such
files, of compilers counted at different times, and prints the same table,
the compilers in the order the files first name them, the first file's
first as the base. Exit 0 when the figures were
printed; 1 when they were and a run collected more than once, or a
compiler's allocation differed between its rounds, or its instructions
spread over more than SPAN of the lowest; 2 when they could not be: perf,
setarch or taskset missing, a compile failing, or a count or statistic
missing.

cg runs COMMAND, a compile, under cachegrind, instructions only, with
GHCRTS=-V0 appended, following exec into the real compiler where COMMAND
is a wrapper and leaving the assembler, linker and C compiler uncounted,
keeps the compiler's process as OUT and prints it as cg-show does: its
instructions in three buckets, the collector and storage manager, the
RTS's hand-written code with libc and the dynamic linker, and the rest,
the compiler's own code, with its heaviest functions. cg-diff prints the
rest's difference between two such files, function by function, beside
the other buckets' differences, which are not to be read as the compiler's:
under GHC's own RTS options the collector's share moves from run to run.
The buckets, the process choice and the z-decoding come from Simon
Jakobi's cgwork.py
(https://gist.github.com/sjakobi/eed39b23f41b06fc41337d137067bd8b,
2026-11-03); this tool adds the native counts, which run at the
compiler's own speed where cachegrind's take about twenty times as long.
cg exits 2 when no file names the compiler's process; cg-show and cg-diff
when a file is not cachegrind's output.
"""

import ast
import contextlib
import io
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import measured_env, bucket, zdecode, demangle  # noqa: E402

CELLS = ('T3294:-O0,T3294:-O,T3294:-O2,T12707:-O0,T12707:-O,T12707:-O2,'
         'T783:-O0,T783:-O,T783:-O2,T9961:-O0,T9961:-O,T9961:-O2,'
         'MBB:-O0,MBB:-O1,MBB:-O2')
RTS = '-A3G -V0'
# How far one compiler's instructions may spread over its rounds, as a
# fraction of the lowest, before the tool says so.
SPAN = 1e-4
# The collections of a compile whose allocation fits in the area.
EXIT_GCS = 1

# The self-test runs fakes in their place.
PERF = ['perf']
SETARCH = ['setarch', '-R']


def command(ghc, lib, level, src, wdir, opts, cpu):
    """One counted compile, pinned to cpu unless it is None."""
    return (SETARCH + (['taskset', '-c', cpu] if cpu is not None else [])
            + PERF + ['stat', '-x,', '-e', 'instructions:u',
                      '-o', os.path.join(wdir, 'p.csv'), '--', ghc]
            + (['-B' + lib] if lib else [])
            + [level, '-v0', '-fforce-recomp', '-S',
               '-outputdir', os.path.join(wdir, 'o'),
               '-o', os.path.join(wdir, 'o', 'out.s'), src,
               '+RTS'] + opts.split()
            + ['-t' + os.path.join(wdir, 'rts'), '--machine-readable',
               '-RTS'])


def instructions(path):
    """The instructions:u count of a perf stat -x, file."""
    with open(path) as fh:
        for line in fh:
            f = line.strip().split(',')
            if len(f) > 2 and f[2].startswith('instructions'):
                if not f[0].isdigit():
                    raise ValueError(f'instructions not counted: {f[0]}')
                return int(f[0])
    raise ValueError(f'no instructions in {path}')


def rts_stats(path):
    """The allocation, collections and copied bytes of an RTS -t
    --machine-readable file."""
    with open(path) as fh:
        text = fh.read()
    body = text.split('\n', 1)[1] if '\n' in text else ''
    try:
        d = dict(ast.literal_eval(body))
        return (int(d['bytes allocated']), int(d['num_GCs']),
                int(d['copied_bytes']))
    except (ValueError, SyntaxError, KeyError) as e:
        raise ValueError(f'RTS statistics unreadable in {path}: {e}')


def sources(cells, tests, cmm):
    """Each cell's (name, level, source file)."""
    out = []
    for c in cells.split(','):
        name, sep, level = c.partition(':')
        if not sep or not name or not level.startswith('-O'):
            raise ValueError(f'a cell is NAME:LEVEL: {c!r}')
        if name == 'MBB':
            if not cmm:
                raise ValueError('MBB needs --cmm FILE')
            src = cmm
        else:
            if not tests:
                raise ValueError(f'{name} needs --tests DIR')
            src = os.path.join(tests, name + '.hs')
        if not os.path.isfile(src):
            raise ValueError(f'no such file: {src}')
        out.append((name, level, src))
    return out


def measure(ghcs, cells, rounds, opts, cpu, keep, out):
    """runs[(name, level, label)] = [(instr, alloc, gcs, copied, sha), ...]
    by round."""
    runs = defaultdict(list)
    with tempfile.TemporaryDirectory(prefix='compile-cost-') as wdir:
        for r in range(rounds):
            order = ghcs[r % len(ghcs):] + ghcs[:r % len(ghcs)]
            for name, level, src in cells:
                for label, ghc, lib in order:
                    shutil.rmtree(os.path.join(wdir, 'o'), ignore_errors=True)
                    os.makedirs(os.path.join(wdir, 'o'))
                    for f in ('p.csv', 'rts'):
                        if os.path.exists(os.path.join(wdir, f)):
                            os.remove(os.path.join(wdir, f))
                    p = subprocess.run(
                        command(ghc, lib, level, src, wdir, opts, cpu),
                        cwd=wdir, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True)
                    if p.returncode != 0:
                        raise ValueError(f'{label} {name} {level} failed:'
                                         f' {p.stdout.strip()[-300:]}')
                    s = os.path.join(wdir, 'o', 'out.s')
                    with open(s, 'rb') as fh:
                        sha = hashlib.sha1(fh.read()).hexdigest()
                    if keep and r == 0:
                        shutil.copy(s, os.path.join(
                            keep, f'{label}-{name}{level}.s'))
                    got = ((instructions(os.path.join(wdir, 'p.csv')),)
                           + rts_stats(os.path.join(wdir, 'rts')) + (sha,))
                    runs[(name, level, label)].append(got)
                    if out:
                        with open(out, 'a') as fh:
                            fh.write(f'{label} {name} {level} {r} '
                                     + ' '.join(map(str, got)) + '\n')
    return runs


def pct(x, base):
    return f'{100 * (x / base - 1):+.3f}%'


def report(runs, ghcs, cells):
    """The table, and the warnings that make the exit 1."""
    lines, warn = [], []
    labels = [g[0] for g in ghcs]
    differ = {lab: 0 for lab in labels[1:]}
    for name, level, _ in cells:
        lines.append(f'{name} {level}')
        first = None
        for lab in labels:
            rs = runs[(name, level, lab)]
            ins = min(x[0] for x in rs)
            allocs = {x[1] for x in rs}
            gcs = max(x[2] for x in rs)
            sha = rs[0][4]
            if max(x[0] for x in rs) - ins > SPAN * ins:
                warn.append(f'{lab} {name} {level}: instructions spread over'
                            f' {pct(max(x[0] for x in rs), ins)} of the lowest')
            if len(allocs) > 1:
                warn.append(f'{lab} {name} {level}: allocation differs between'
                            f' rounds ({min(allocs)} to {max(allocs)})')
            if gcs > EXIT_GCS:
                warn.append(f'{lab} {name} {level}: {gcs} collections: its'
                            f' instructions include the collector\'s; raise -A')
            alloc = min(allocs)
            row = f'  {lab:12} {ins:>15,}'
            if first is None:
                first = (ins, alloc, sha)
                row += f'{"":9}  {alloc:>15,} B{"":9}  {gcs} GC'
            else:
                same = sha == first[2]
                differ[lab] += not same
                row += (f' {pct(ins, first[0]):>8}  {alloc:>15,} B'
                        f' {pct(alloc, first[1]):>8}  {gcs} GC'
                        f'  asm {"same" if same else "DIFFERS"}')
            lines.append(row)
    for lab, n in differ.items():
        lines.append(f'{lab}: assembly differs from {labels[0]}\'s'
                     f' in {n} of {len(cells)} cells')
    return lines, warn


def read_runs(paths):
    """The runs --out wrote to the given files, the compilers and the cells
    in the order the files first name them."""
    runs, ghcs, cells = defaultdict(list), [], []
    for path in paths:
        with open(path) as fh:
            for line in fh:
                f = line.split()
                if len(f) != 9 or not all(x.isdigit() for x in f[3:8]):
                    raise ValueError(f'not a run of --out: {line.strip()!r}')
                label, name, level = f[:3]
                runs[(name, level, label)].append(
                    tuple(int(x) for x in f[4:8]) + (f[8],))
                if label not in [g[0] for g in ghcs]:
                    ghcs.append((label, '', ''))
                if (name, level, '') not in cells:
                    cells.append((name, level, ''))
    if not runs:
        raise ValueError('no runs in ' + ' '.join(paths))
    missing = [(n, v, g[0]) for n, v, _ in cells for g in ghcs
               if (n, v, g[0]) not in runs]
    if missing:
        raise ValueError(f'cells without runs: {missing[:3]}')
    return runs, ghcs, cells


def parse_ghcs(args):
    out = []
    for a in args:
        label, sep, rest = a.partition('=')
        ghc, _, lib = rest.partition('@')
        if not sep or not label or not ghc:
            raise ValueError(f'a compiler is LABEL=GHC[@LIBDIR]: {a!r}')
        out.append((label, ghc, lib))
    if len({g[0] for g in out}) != len(out):
        raise ValueError('two compilers share a label')
    return out


# --- cachegrind: the buckets, the process choice and the z-decoding of
# Simon Jakobi's cgwork.py (see the module's haddock), the GC bucket's
# difference printed rather than dropped.

# Tools a compile forks, run native and uncounted.
SKIP_CHILDREN = ['*/as', '*/ld', '*/ld.*', '*/ld.gold', '*/ld.lld', '*/lld',
                 '*/cc', '*/cc1', '*/gcc', '*/clang', '*/collect2',
                 '*/realgcc*', '*/ar', '*/ranlib', '*/strip', '*/llc',
                 '*/opt', '*/llvm*', '*/ghc-iserv*', '*/hsc2hs', '*/unlit']

def cg_parse(path):
    """Instructions by function of a cachegrind file, and its command."""
    fns, cmd, seen = defaultdict(int), '', False
    with open(path) as fh:
        for line in fh:
            if line.startswith('cmd:'):
                cmd = line[4:].strip()
            elif line.startswith('fn='):
                cur, seen = line[3:].strip(), True
            elif line[:1].isdigit() and seen:
                f = line.split()
                if len(f) >= 2:
                    fns[cur] += int(f[1])
    if not seen:
        raise ValueError(f'not cachegrind output: {path}')
    return fns, cmd


def cg_buckets(fns):
    b = defaultdict(int)
    for k, v in fns.items():
        b[bucket(k)] += v
    return b


def cg_show(path):
    fns, _ = cg_parse(path)
    b = cg_buckets(fns)
    total = sum(b.values())
    print(f'file:      {path}')
    print(f'total:     {total:>16,}')
    for k, what in (('gc', 'collector and storage manager, moves run to run'),
                    ('rts', "RTS code, libc, ld.so"),
                    ('comp', 'the compiler')):
        print(f'  {k:5}    {b[k]:>16,}  ({100 * b[k] / total:.1f}%)  {what}')
    print('\nheaviest functions of the compiler:')
    for k in sorted((k for k in fns if bucket(k) == 'comp'),
                    key=lambda k: fns[k], reverse=True)[:20]:
        print(f'  {fns[k]:>14,}  {demangle(k)[:80]}')


def cg_diff(pa, pb):
    a, _ = cg_parse(pa)
    b, _ = cg_parse(pb)
    ba, bb = cg_buckets(a), cg_buckets(b)
    for k, what in (('comp', 'the compiler'),
                    ('gc', 'the collector, moving run to run'),
                    ('rts', 'RTS code, libc, ld.so')):
        d = bb[k] - ba[k]
        rel = f'({100 * d / ba[k]:+.4f}%)' if ba[k] else ''
        print(f'{k:5} {ba[k]:>16,} -> {bb[k]:>16,}  {d:>+14,} {rel}'
              f'  {what}')
    keys = [k for k in set(a) | set(b) if bucket(k) == 'comp']
    keys.sort(key=lambda k: abs(b.get(k, 0) - a.get(k, 0)), reverse=True)
    print(f'\n{"delta":>14}  {"old":>14}  {"new":>14}  function')
    for k in keys[:25]:
        d = b.get(k, 0) - a.get(k, 0)
        if d == 0:
            break
        print(f'{d:>+14,}  {a.get(k, 0):>14,}  {b.get(k, 0):>14,}'
              f'  {demangle(k)[:64]}')


VALGRIND = ['valgrind']


def cg_run(out, cmd, cpu):
    """COMMAND under cachegrind; the compiler's file kept as OUT."""
    for stale in glob.glob(glob.escape(out) + '.*'):
        os.remove(stale)
    vg = ((['taskset', '-c', cpu] if cpu is not None else []) + VALGRIND
          + ['--tool=cachegrind', '--cache-sim=no', '--branch-sim=no',
             '--trace-children=yes',
             '--trace-children-skip=' + ','.join(SKIP_CHILDREN),
             f'--cachegrind-out-file={out}.%p'] + cmd)
    rc = subprocess.call(vg, env=measured_env())
    produced = sorted(glob.glob(glob.escape(out) + '.*'))
    totals = {}
    for p in produced:
        fns, c = cg_parse(p)
        totals[p] = (sum(fns.values()), c)
    ghc = [p for p in produced
           if 'ghc' in os.path.basename(totals[p][1].split(' ')[0])]
    if not ghc:
        print('no cachegrind file names a compiler process', file=sys.stderr)
        return 2
    chosen = max(ghc, key=lambda p: totals[p][0])
    for p in produced:
        if p != chosen:
            os.remove(p)
    shutil.move(chosen, out)
    cg_show(out)
    return 0 if rc == 0 else 2


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    try:
        if argv[:1] == ['cg-show'] and len(argv) == 2:
            cg_show(argv[1])
            return 0
        if argv[:1] == ['compare'] and len(argv) > 1:
            runs, ghcs, cells = read_runs(argv[1:])
            lines, warn = report(runs, ghcs, cells)
            print('\n'.join(lines))
            for w in warn:
                print('WARNING', w)
            return 1 if warn else 0
        if argv[:1] == ['cg-diff'] and len(argv) == 3:
            cg_diff(argv[1], argv[2])
            return 0
        if argv[:1] == ['cg']:
            cpu, rest = None, argv[1:]
            if rest[:1] == ['--cpu'] and len(rest) > 1:
                cpu, rest = rest[1], rest[2:]
            if len(rest) < 3 or rest[1] != '--':
                print(__doc__.split('\n\n')[1], file=sys.stderr)
                return 2
            if shutil.which(VALGRIND[0]) is None:
                print('valgrind is not on PATH; nothing measured',
                      file=sys.stderr)
                return 2
            return cg_run(rest[0], rest[2:], cpu)
    except (ValueError, OSError) as e:
        print(e, file=sys.stderr)
        return 2
    opts = {'--cpu': None, '--rounds': '3', '--rts': RTS, '--cells': CELLS,
            '--tests': None, '--cmm': None, '--keep-s': None, '--out': None}
    while argv[:1] and argv[0] in opts:
        if len(argv) < 2:
            print(f'{argv[0]} needs a value', file=sys.stderr)
            return 2
        opts[argv[0]], argv = argv[1], argv[2:]
    if not argv or not opts['--rounds'].isdigit() or int(opts['--rounds']) < 1:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    tools = [PERF[0]] + SETARCH[:1] + (['taskset'] if opts['--cpu'] else [])
    for t in tools:
        if shutil.which(t) is None:
            print(f'{t} is not on PATH; nothing measured', file=sys.stderr)
            return 2
    try:
        ghcs = parse_ghcs(argv)
        cells = sources(opts['--cells'], opts['--tests'], opts['--cmm'])
        if opts['--keep-s']:
            os.makedirs(opts['--keep-s'], exist_ok=True)
        runs = measure(ghcs, cells, int(opts['--rounds']), opts['--rts'],
                       opts['--cpu'], opts['--keep-s'], opts['--out'])
    except (ValueError, OSError) as e:
        print(f'{e}; nothing measured', file=sys.stderr)
        return 2
    lines, warn = report(runs, ghcs, cells)
    print('\n'.join(lines))
    for w in warn:
        print('WARNING', w)
    return 1 if warn else 0


# A fake ghc: writes the assembly (its text the compiler's label, one cell's
# odd for B) and RTS statistics whose allocation, collections and copied
# bytes come from its name; a fake perf runs the command and counts
# instructions by the compiler and the round, recording the order.
FAKE_GHC = r'''#!/usr/bin/env python3
import sys, os
a = sys.argv[1:]
me = os.path.basename(sys.argv[0])
out = a[a.index('-o') + 1]
src = [x for x in a[:a.index('+RTS')] if x.endswith(('.hs', '.cmm'))][0]
rts = [x[2:] for x in a if x.startswith('-t')][0]
opts = a[a.index('+RTS') + 1:a.index('-RTS')]
open(os.path.join(os.path.dirname(sys.argv[0]), 'rtsopts'), 'w').write(
    ' '.join(x for x in opts if not x.startswith('-t')))
asm = 'asm' + ('x' if me == 'B' and src.endswith('two.hs') else '')
open(out, 'w').write(asm)
alloc = {'A': 1000, 'B': 1100, 'F': 1000, 'G': 1000, 'S': 1000, 'M': 1000,
         'U': 1000}[me]
gcs = 3 if me == 'G' else 1
rest = '' if me == 'M' else ' ,("num_GCs", "%d")\n' % gcs
open(rts, 'w').write("'ghc' '+RTS'\n [(\"bytes allocated\", \"%d\")\n%s"
                     " ,(\"copied_bytes\", \"0\")\n ]\n" % (alloc, rest))
sys.exit(1 if me == 'F' else 0)
'''
FAKE_PERF = r'''#!/usr/bin/env python3
import sys, os, subprocess
a = sys.argv[1:]
o = a[a.index('-o') + 1]
cmd = a[a.index('--') + 1:]
me = os.path.basename(cmd[0])
src = [x for x in cmd if x.endswith(('.hs', '.cmm'))][0]
calls = os.path.join(os.path.dirname(cmd[0]), 'calls')
n = sum(1 for _ in open(calls)) if os.path.exists(calls) else 0
open(calls, 'a').write('%s %s\n' % (me, os.path.basename(src)))
rc = subprocess.call(cmd)
base = {'A': 100000, 'B': 101000, 'G': 100000, 'S': 100000, 'M': 1}[me] \
    if me in 'ABGSM' else 1
extra = 50 if (me == 'S' and n % 2) else 0
count = '<not counted>' if me == 'U' else str(base + extra)
open(o, 'w').write('%s,,instructions:u,1,100.00,,\n' % count)
sys.exit(rc)
'''


def self_test():
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        bad = checks()
    for b in bad:
        print('FAIL', b)
    print('self-test', 'FAILED' if bad else 'passed')
    return 1 if bad else 0


def checks():
    """The order of the runs, the lowest count, the figures against the
    first compiler, the assembly comparison, the warnings and the exits,
    with a fake ghc and a fake perf; the cell parsing; the z-decoding and
    the buckets, over a made-up cachegrind file."""
    global PERF, SETARCH
    bad = []
    with tempfile.TemporaryDirectory() as td:
        for name, text in (('perf', FAKE_PERF),) + tuple(
                (g, FAKE_GHC) for g in 'ABFGMSU'):
            p = os.path.join(td, name)
            with open(p, 'w') as fh:
                fh.write(text)
            os.chmod(p, 0o755)
        for m in ('one.hs', 'two.hs', 'm.cmm'):
            open(os.path.join(td, m), 'w').close()
        saved, PERF, SETARCH = (PERF, SETARCH), [os.path.join(td, 'perf')], []
        g = {x: f'{x}={os.path.join(td, x)}' for x in 'ABFGMSU'}
        cells = ['--tests', td, '--cmm', os.path.join(td, 'm.cmm'),
                 '--cells', 'one:-O0,two:-O,MBB:-O1', '--rounds', '2']
        try:
            ghcs = parse_ghcs([g['A'], g['B']])
            cs = sources('one:-O0,two:-O,MBB:-O1', td,
                         os.path.join(td, 'm.cmm'))
            runs = measure(ghcs, cs, 2, RTS, None, None, None)
            lines, warn = report(runs, ghcs, cs)
            text = '\n'.join(lines)
            if not re.search(r'\n  B +101,000 +\+1\.000% ', text):
                bad.append(f'B against A not +1.000%: {text}')
            if not re.search(r' 1,100 B +\+10\.000% ', text):
                bad.append('allocation against A not +10.000%')
            if text.count('asm DIFFERS') != 1 or text.count('asm same') != 2:
                bad.append('the assembly comparison is wrong')
            if 'B: assembly differs from A\'s in 1 of 3 cells' not in text:
                bad.append('the assembly summary is wrong')
            if warn:
                bad.append(f'a clean reading warned: {warn}')
            with open(os.path.join(td, 'calls')) as fh:
                order = [line.split()[0] for line in fh]
            if order != ['A', 'B'] * 3 + ['B', 'A'] * 3:
                bad.append(f'not rotated: {order}')
            if main(cells + [g['A'], g['B']]) != 0:
                bad.append('a clean reading did not exit 0')
            with open(os.path.join(td, 'rtsopts')) as fh:
                if fh.read().split() != ['-A3G', '-V0', '--machine-readable']:
                    bad.append('the default RTS options are not -A3G -V0')
            oa, ob = os.path.join(td, 'oa'), os.path.join(td, 'ob')
            main(cells + ['--out', oa, g['A']])
            main(cells + ['--out', ob, g['B']])
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = main(['compare', oa, ob])
            got = buf.getvalue()
            if rc != 0 or not re.search(r'\n  B +101,000 +\+1\.000% ', got) \
                    or got.count('asm DIFFERS') != 1:
                bad.append(f'compare of two --out files: {rc} {got}')
            with open(oa, 'a') as fh:
                fh.write('A one -O0 9 x\n')
            if main(['compare', oa, ob]) != 2:
                bad.append('a line not --out\'s did not exit 2')
            if main(cells + [g['A'], g['G']]) != 1:
                bad.append('collections beyond the exit did not exit 1')
            if main(cells + [g['S']]) != 1:
                bad.append('a spread of instructions did not exit 1')
            os.remove(os.path.join(td, 'calls'))
            runs = measure(parse_ghcs([g['S']]), cs[:1], 3, RTS, None,
                           None, None)
            if min(x[0] for x in runs[('one', '-O0', 'S')]) != 100000:
                bad.append('not the lowest count')
            c1 = [('one', '-O0', 'x')]
            lines, warn = report(
                {('one', '-O0', 'A'): [(100100, 7, 1, 0, 's'),
                                       (100000, 8, 1, 0, 's')]},
                [('A', '', '')], c1)
            if '100,000' not in lines[1] or len(warn) != 2:
                bad.append(f'not the lowest, or a spread unwarned: {lines}'
                           f' {warn}')
            for tag, what in (('F', 'a failing compile'),
                              ('U', 'an instruction count not counted'),
                              ('M', 'a statistic missing')):
                if main(cells + [g['A'], g[tag]]) != 2:
                    bad.append(f'{what} did not exit 2')
            if main(['--cells', 'one'] + cells[:4] + [g['A']]) != 2:
                bad.append('a cell without a level did not exit 2')
            if main(['--cells', 'MBB:-O0', g['A']]) != 2:
                bad.append('MBB without --cmm did not exit 2')
            if main(cells + ['A=x', 'A=y']) != 2:
                bad.append('a shared label did not exit 2')
            c = command('ghc', 'L', '-O1', 's.hs', 'w', '-A3G -V0', '3')
            if c[:3] != ['taskset', '-c', '3'] or '-BL' not in c \
                    or c[c.index('+RTS') + 1:c.index('+RTS') + 3] \
                    != ['-A3G', '-V0']:
                bad.append(f'the command is wrong: {c}')
        finally:
            PERF, SETARCH = saved
        cg = os.path.join(td, 'cg')
        with open(cg, 'w') as fh:
            fh.write('desc: I1 cache:\ncmd: ghc -O\nevents: Ir\n'
                     'fn=evacuate\n1 500\n2 100\n'
                     'fn=stg_ap_p_fast\n1 70\n'
                     'fn=ghczminplace_GHCziCmmToAsmziRegziLinear_'
                     'zdwallocRegsAndSpill_info\n3 300\n'
                     'fn=main\n4 30\nsummary: 1000\n')
        fns, cmd = cg_parse(cg)
        if dict(cg_buckets(fns)) != {'gc': 600, 'rts': 70, 'comp': 330} \
                or cmd != 'ghc -O':
            bad.append(f'buckets: {dict(cg_buckets(fns))} {cmd}')
        for z, want in (('ghczminplace_GHCziCmmToAsmziRegziLinear_'
                         'zdwallocRegsAndSpill_info',
                         'GHC.CmmToAsm.Reg.Linear.$wallocRegsAndSpill_info'),
                        ('base_GHCziBase_ZC_con_info',
                         'GHC.Base.:_con_info'),
                        ('base_GHCziTuple_Z3T_con_info',
                         'GHC.Tuple.(,,)_con_info'),
                        ('evacuate', 'evacuate')):
            if demangle(z) != want:
                bad.append(f'demangle {z}: {demangle(z)}, not {want}')
        if zdecode('z2219U') != '∙' or zdecode('Z1H') != '(##)':
            bad.append('unicode or unboxed-tuple decoding')
        nota = os.path.join(td, 'nota')
        with open(nota, 'w') as fh:
            fh.write('hello\n')
        if main(['cg-show', nota]) != 2:
            bad.append('a file not cachegrind\'s did not exit 2')
    return bad


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
