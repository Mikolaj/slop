#!/usr/bin/env python3
"""Every comparison of battery.py's label B against label A, written to one
report: nofib's (nbcmp.py), containers', megaparsec's and vector's (pkgcmp.py),
A2T's sample's and groups' (a2tcmp.py), the fifteen compilations'
(compile-cost.py compare, comp1 and comp2), GHC's perf and size tests'
(perfcmp.py), the scaling probes' (NCG-scale/report.py), the tickets' and the
Text scan's (tickets.py compare), each label's random test (NCG-fuzz/run.py's
results) and the builds' (bstats.py compare); each section's summary, then
every row moving by its threshold, up and down. rebuild.py writes it for the
last label against the base's, fr00.

Usage: python3 tools/NCG-battery/runreport.py [--work DIR] A B OUT
       python3 tools/NCG-battery/runreport.py [--work DIR] --check [LABEL...]
       python3 tools/NCG-battery/runreport.py --self-test

The thresholds, taken up on 2026-11-07 where no other date is given, from
the outliers pass over the series' full rebuild, object size and compile
instructions set by Mikolaj's ruling 120 that day: nofib's instructions,
allocation, compile allocation and object size 0.2%, its compile
instructions 1%; containers' and megaparsec's instructions and allocation
0.1%, a benchmark's instructions moving by pkgcmp.py's rule (the minima
where both labels' runs agree within 0.05%, else the nearer ends where the
ranges are disjoint, else the minima, marked `overlap`); vector's 0.05%, by
the minima; the three packages' falls listed by those bars, where the
outliers pass took a fall for a gain to explain only from 0.5%; A2T's
instructions and allocation a call 0.2%, the bar of its cells' counts since
2026-10-20; a compilation's allocation 0.1% and its instructions 1%; the
perf tests by the windows GHC's CI holds them to, taken from the testsuite
of the work directory's ghc-TREE, TREE B's as below, the tree of the GHC
under test (Mikolaj's ruling 457, 2026-11-22), and said not checked where
it is absent; a scaling row where report.py flags it; the tickets' rows
tickets.py compare lists, instructions an element 0.2%, and the Text
scan's by the same rule since 2026-11-09; a module's allocation 0.1% and
size 0.2%, a compiler process's instructions 1%. A label's nofib -O2 and
package runs are battery.py's cTREE-LABEL (cTREE-o1-LABEL at -O1), TREE
the one tree they name or the label's own name where it is among several;
several without it leave the section not compared. A label's random test is
reported `pass` only where every seed battery.py's setting 16 runs has a line
and every line is ok or known, run.py's word for a seed whose only failures
are panics of the upstream issues it knows, these listed by issue beside it,
and `FAIL` otherwise, naming the failing seeds and those not run.
A section whose tables are missing says so and the others go on. The work
directory is battery.py's, dist-ghcho by default. Exits 0 when the report
was written.

--check tests for each LABEL, or for each label with a LABEL.done in
WORK/battery/rebuild where none is given, whether every record the report's
sections read is there and not empty, the tree's name taken to be the
label's, as rebuild.py's are: nofib's tables at each level, read as nbcmp.py
reads them, and its compiles' counts; containers', megaparsec's and vector's
runs at -O2 and -O1; the A2T, compilations', perf tests', scaling, tickets'
and Text scan's tables; the random test's lanes; and the builds' tables. It
prints a line for each label lacking any, naming what, then a count, and
exits 1 when any label lacks one, 0 otherwise.
"""

import glob
import io
import os
import re
import subprocess
import sys
import tempfile
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import a2tcmp  # noqa: E402
import bstats  # noqa: E402
import nbcmp  # noqa: E402
import pkgcmp  # noqa: E402
import tickets  # noqa: E402
from battery import (COMPILE_COST, FUZZ_FIRST, FUZZ_LANES, FUZZ_PER_LANE,  # noqa: E402
                     FUZZ_RUN, WORK)

NOFIB = {'instr': 0.002, 'alloc': 0.002, 'calloc': 0.002, 'size': 0.002, 'cinstr': 0.01}
PKG = {'containers': 0.001, 'megaparsec': 0.001, 'vector': 0.0005}
A2T, COMP_ALLOC, COMP_INSTR = 0.002, 0.001, 0.01
SCALE = os.path.join(os.path.dirname(HERE), 'NCG-scale', 'report.py')
# compile-cost.py compare's line of a label: instructions, their change,
# bytes allocated, their change
CELL = re.compile(r'^\s+(\S+)\s+([\d,]+)\s+([+-][\d.]+)%\s+([\d,]+) B\s+([+-][\d.]+)%')


def moved(rs, bar):
    """[(ratio - 1, name, a, b)] moving by bar either way, rises first."""
    m = [(y / x - 1, k, x, y) for k, x, y in rs if x and abs(y / x - 1) >= bar - 1e-12]
    return sorted((r for r in m if r[0] > 0), reverse=True) + sorted(r for r in m if r[0] < 0)


def listing(title, rs, bar):
    m = moved(rs, bar)
    up = sum(r[0] > 0 for r in m)
    return ([f'{title} by {bar:.2%}: {up} up, {len(m) - up} down']
            + [f'  {r * 100:+.3f}%  {k}  {x:.0f} {y:.0f}' for r, k, x, y in m])


def nofib_runs(label, tree=None):
    """Label's nofib runs, by level, as battery.py names them, its tree
    named as the label, as rebuild.py's are, unless tree is given."""
    return (('-O2', f'c{tree or label}-{label}'), ('-O1', f'o1-{label}'), ('-O0', f'o0-{label}'))


def run_name(names, label, o1=''):
    """battery.py's name of label's run, cTREE-LABEL or with o1 cTREE-o1-LABEL,
    among names: TREE the label's own name where one is there, else the one
    tree they name, as p103's ct103-p103; several without the label's are a
    ValueError."""
    pat = re.compile(rf'c([^-]+)-{o1}{re.escape(label)}')
    trees = sorted({m.group(1) for x in names for m in [pat.fullmatch(x)] if m})
    if len(trees) > 1 and label not in trees:
        raise ValueError(f'runs of {label} on trees {", ".join(trees)}')
    return f'c{trees[0] if len(trees) == 1 else label}-{o1}{label}'


def listed(path, pattern=r'(.*)'):
    """The names in directory path, each matching pattern whole, its group."""
    names = os.listdir(path) if os.path.isdir(path) else []
    return [m.group(1) for x in names for m in [re.fullmatch(pattern, x)] if m]


def nofib_names(work, outdir=None):
    """The names of nofib's runs, its kept tables' and its _make's."""
    n = os.path.join(work, 'nofib-r')
    return (listed(os.path.dirname(nbcmp.kept(n, 'x', outdir)), r'nofib-(.*)\.tsv')
            + listed(os.path.join(n, 'nofib', '_make')))


def nofib(work, a, b, outdir=None):
    n = os.path.join(work, 'nofib-r')
    names = nofib_names(work, outdir)
    out = []
    for (lev, ra), (_, rb) in zip(nofib_runs(a), nofib_runs(b)):
        out.append(f'nofib {lev}')
        try:
            if lev == '-O2':
                ra, rb = run_name(names, a), run_name(names, b)
            out += nbcmp.compare(n, ra, rb, outdir)
            fa, fb = nbcmp.load(n, ra, outdir), nbcmp.load(n, rb, outdir)
        except (ValueError, OSError) as e:
            out.append(f'  not compared: {e}')
            continue
        for key, name in nbcmp.NAMES:
            if key in NOFIB:
                rs = [(t, fa[t][key], fb[t][key]) for t in sorted(set(fa) & set(fb))
                      if fa[t].get(key) and fb[t].get(key)]
                out += ['  ' + x for x in listing(name, rs, NOFIB[key])]
    return out


def spread_rows(A, B):
    """(name, a, b, how) of each benchmark both have, by pkgcmp.py's rule."""
    out = []
    for k, va in A.items():
        vb = B.get(k)
        if not vb:
            continue
        la, ha, lb, hb = min(va), max(va), min(vb), max(vb)
        if ha <= la * (1 + pkgcmp.TOL) and hb <= lb * (1 + pkgcmp.TOL):
            out.append((k, la, lb, 'stable'))
        elif lb > ha:
            out.append((k, ha, lb, 'disjoint'))
        elif hb < la:
            out.append((k, la, hb, 'disjoint'))
        else:
            out.append((k, la, lb, 'overlap'))
    return out


def packages(work, a, b):
    v = os.path.join(work, 'vpapi')
    out = []
    for pkg, bar in PKG.items():
        names = (listed(v, r'res-(.*)-\d+\.csv') if pkg == 'vector'
                 else listed(os.path.join(v, pkgcmp.DIRS[pkg])))
        for lev, o1 in (('-O2', ''), ('-O1', 'o1-')):
            out.append(f'{pkg} {lev}')
            try:
                la, lb = run_name(names, a, o1), run_name(names, b, o1)
                if pkg == 'vector':
                    _, A = pkgcmp.load_vector(v, la)
                    _, B = pkgcmp.load_vector(v, lb)
                    ins = [(k, A[k][2], B[k][2]) for k in A if k in B]
                    alloc = [(k, A[k][0], B[k][0]) for k in A if k in B]
                    out += pkgcmp.vector(v, la, lb)[-1:]
                else:
                    d = pkgcmp.DIRS[pkg]
                    rs = spread_rows(pkgcmp.load_spread(v, d, la), pkgcmp.load_spread(v, d, lb))
                    ins = [(f'{k} ({how})', x, y) for k, x, y, how in rs]
                    A, B = (pkgcmp.load_spread(v, d, x, 'ALLOC') for x in (la, lb))
                    alloc = [(k, min(A[k]), min(B[k])) for k in A if B.get(k)]
                    out += pkgcmp.spread(v, d, la, lb, 0)[:1]
            except (ValueError, OSError) as e:
                out.append(f'  not compared: {e}')
                continue
            out += ['  ' + x for x in listing('instructions', ins, bar)]
            out += ['  ' + x for x in listing('allocation', alloc, bar)]
    return out


def a2t(outdir, a, b, variant=''):
    """The sample's counts, or with variant groups those of part a2t-groups."""
    out = [f'A2T {variant}'.rstrip()]
    pre = f'a2t-{variant}-' if variant else 'a2t-'
    try:
        ca, cb = (a2tcmp.load(os.path.join(outdir, f'{pre}{x}.tsv')) for x in (a, b))
        aa, ab = (a2tcmp.load(os.path.join(outdir, f'{pre}{x}.tsv'), 3) for x in (a, b))
    except OSError as e:
        return out + [f'  not compared: {e}']
    out.append(a2tcmp.compare(a, b, ca, cb, 0))
    for title, x, y in (('instructions a call', ca, cb), ('bytes allocated a call', aa, ab)):
        rs = [(c, x[c], y[c]) for c in sorted(x) if x[c] and y.get(c)]
        out += ['  ' + line for line in listing(title, rs, A2T)]
    return out


def run_tool(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def comp(outdir, a, b):
    out = []
    for stage in (1, 2):
        out.append(f'comp{stage}')
        ra, rb = (os.path.join(outdir, f'comp{stage}-{x}.runs') for x in (a, b))
        if not (os.path.exists(ra) and os.path.exists(rb)):
            out.append(f'  not compared: no {ra if not os.path.exists(ra) else rb}')
            continue
        rc, text = run_tool([sys.executable, COMPILE_COST, 'compare', ra, rb])
        out += ['  ' + x for x in text.rstrip('\n').split('\n')]
        cell, rows = None, []
        for line in text.split('\n'):
            if line and not line.startswith(' '):
                cell = line.strip()
            m = CELL.match(line)
            if m and cell and m.group(1) == b:
                ins, alloc = float(m.group(3)) / 100, float(m.group(5)) / 100
                if abs(alloc) >= COMP_ALLOC - 1e-12 or abs(ins) >= COMP_INSTR - 1e-12:
                    rows.append(f'    {cell}: instructions {ins * 100:+.3f}%, allocation {alloc * 100:+.3f}%')
        out.append(f'  cells moving by {COMP_ALLOC:.1%} in allocation or {COMP_INSTR:.0%} in'
                   f' instructions: {len(rows)}')
        out += rows
    return out


def perf(work, outdir, a, b):
    """The perf and size tests, by the windows of the testsuite of the tree
    b's nofib -O2 run names (run_name), b's own name where it names none."""
    argv = [sys.executable, os.path.join(HERE, 'perfcmp.py'), '--work', work, '--out', outdir, a, b]
    try:
        tree = run_name(nofib_names(work, outdir), b)[1:-len(b) - 1]
    except ValueError:
        tree = b
    have = os.path.isdir(os.path.join(work, f'ghc-{tree}', 'testsuite'))
    if have:
        argv.append(tree)
    rc, text = run_tool(argv)
    return (['perf and size tests'] + ['  ' + x for x in text.rstrip('\n').split('\n')]
            + ([] if have else [f'  windows: not checked, no ghc-{tree}/testsuite in {work}']))


def scale(outdir, a, b):
    fa, fb = (os.path.join(outdir, f'scale-{x}.txt') for x in (a, b))
    if not (os.path.exists(fa) and os.path.exists(fb)):
        return ['scaling probes', '  not compared: a table is missing']
    rc, text = run_tool([sys.executable, SCALE, fa, fb])
    flagged = [x for x in text.split('\n') if 'FLAG' in x]
    return (['scaling probes', f'  flagged rows: {len(flagged)}'] + ['    ' + x for x in flagged]
            + ['  ' + x for x in text.rstrip('\n').split('\n')])


def tix(outdir, a, b, title='tickets', stem='tix'):
    """Two labels' tables in tickets.py's form, the tickets' or utf8.py's."""
    try:
        ta, tb = (tickets.load(os.path.join(outdir, f'{stem}-{x}.tsv')) for x in (a, b))
    except OSError as e:
        return [title, f'  not compared: {e}']
    return [title] + ['  ' + x for x in tickets.compare(a, b, ta, tb)]


def spans(xs):
    """Integers as runs, `a-b` or `a`, in order."""
    runs = []
    for x in sorted(xs):
        if runs and runs[-1][1] == x - 1:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    return ' '.join(f'{x}-{y}' if y > x else f'{x}' for x, y in runs)


def fuzz(outdir, a, b):
    """Each label's random test: a pass only where every seed battery.py's
    setting 16 runs has a line and every line is ok or known; the failing seeds
    named, with run.py --report's count of what failed and of each known issue's
    seeds."""
    top = FUZZ_FIRST + FUZZ_LANES * FUZZ_PER_LANE
    want = set(range(FUZZ_FIRST, top))
    out = [f'fuzz, the {len(want)} seeds from {FUZZ_FIRST} to {top - 1}']
    for lab in (a, b):
        d = os.path.join(outdir, f'fuzz-{lab}')
        files = sorted(glob.glob(os.path.join(glob.escape(d), 'result-*.txt')))
        if not files:
            out.append(f'  {lab}: FAIL, no results in {d}')
            continue
        ran, known, failing = set(), set(), set()
        for path in files:
            with open(path) as fh:
                for line in fh:
                    f = line.split(maxsplit=2)
                    if len(f) >= 2 and f[0].isdigit():
                        ran.add(int(f[0]))
                        if f[1] == 'known':
                            known.add(int(f[0]))
                        elif f[1] != 'ok':
                            failing.add(int(f[0]))
        short = want - ran
        line = (f'  {lab}: {"FAIL" if failing or short else "pass"}, {len(ran)} seeds run,'
                f' {len(ran - known - failing)} ok, {len(known)} known, {len(failing)} failing')
        line += f': {spans(failing)}' if failing else ''
        line += f'; not run: {spans(short)}' if short else ''
        out.append(line)
        if failing or known:
            rc, text = run_tool([sys.executable, FUZZ_RUN, '--report', *files])
            out += ['    ' + x for x in text.rstrip('\n').split('\n')[1:]]
    return out


def builds(outdir, a, b):
    try:
        ta, tb = bstats.load_label(outdir, a), bstats.load_label(outdir, b)
    except ValueError as e:
        return ['builds', f'  not compared: {e}']
    return ['builds'] + ['  ' + x for x in bstats.compare(ta, tb, a, b)]


def report(work, a, b, path, outdir=None):
    outdir = outdir or os.path.join(work, 'battery')
    lines = [f'{b} against {a}, work directory {work}', '']
    for sec in (lambda: nofib(work, a, b, outdir), lambda: packages(work, a, b),
                lambda: a2t(outdir, a, b), lambda: a2t(outdir, a, b, 'groups'),
                lambda: comp(outdir, a, b),
                lambda: perf(work, outdir, a, b), lambda: scale(outdir, a, b),
                lambda: tix(outdir, a, b), lambda: tix(outdir, a, b, 'utf8 Text scan', 'utf8'),
                lambda: fuzz(outdir, a, b), lambda: builds(outdir, a, b)):
        try:
            lines += sec()
        except Exception as e:  # a section that cannot run leaves the others
            lines.append(f'  section failed: {type(e).__name__}: {e}')
        lines.append('')
    with open(path, 'w') as fh:
        fh.write('\n'.join(lines))
    return path


def missing(work, label, outdir=None, sections=None, tree=None):
    """What of label's records the report reads is absent or empty, a line
    each, of the sections named or of all, its runs on ghc-TREE, the label's
    own name unless given."""
    outdir = outdir or os.path.join(work, 'battery')
    n, v = os.path.join(work, 'nofib-r'), os.path.join(work, 'vpapi')
    t = tree or label
    c, o1, e = f'c{t}-{label}', f'c{t}-o1-{label}', glob.escape
    out = []

    def need(section, pattern):
        if sections and section not in sections:
            return
        files = sorted(glob.glob(pattern))
        empty = [p for p in files if os.path.isfile(p) and not os.path.getsize(p)]
        if not files:
            out.append(f'{section}: no {pattern}')
        elif empty:
            out.append(f'{section}: {len(empty)} of {len(files)} {pattern} empty, the first {empty[0]}')
    for lev, r in nofib_runs(label, tree):
        if not sections or 'nofib' in sections:
            try:
                nbcmp.load(n, r, outdir)
            except (ValueError, OSError) as x:
                out.append(f'nofib {lev}: {x}')
        need('nofib', os.path.join(e(n), 'stats', e(r), '*.csv'))
    for lab in (c, o1):
        need('containers', os.path.join(e(v), 'cres', e(lab), '*.csv'))
        need('megaparsec', os.path.join(e(v), 'mres', e(lab), '*.csv'))
        need('vector', os.path.join(e(v), f'res-{e(lab)}-*.csv'))
    o, b = e(outdir), e(label)
    for section, name in (('A2T', f'a2t-{b}.tsv'), ('comp', f'comp1-{b}.runs'),
                          ('comp', f'comp2-{b}.runs'), ('perf', f'perf-{b}.tsv'),
                          ('scale', f'scale-{b}.txt'), ('tickets', f'tix-{b}.tsv'),
                          ('utf8', f'utf8-{b}.tsv'), ('fuzz', f'fuzz-{b}/result-*.txt'),
                          ('builds', f'ghcb-{b}.tsv'), ('builds', f'pkgb-{b}.tsv')):
        need(section, os.path.join(o, name))
    return out


def check(work, labels):
    """--check's lines and status."""
    logs = os.path.join(work, 'battery', 'rebuild')
    labels = labels or sorted(os.path.basename(p)[:-5]
                              for p in glob.glob(os.path.join(glob.escape(logs), '*.done')))
    if not labels:
        return [f'no label given and no LABEL.done in {logs}'], 2
    lines = [f'{lab}: {"; ".join(m)}' for lab in labels for m in [missing(work, lab)] if m]
    return lines + [f'{len(labels)} labels checked, {len(lines)} lacking records'], 1 if lines else 0


# --- self-test: two labels' tables planted by the tools' own planters,
# the report's rows checked.

def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='runreport-') as w:
        n, o = f'{w}/nofib-r', f'{w}/battery'
        os.makedirs(o)
        for lab, k in (('A', 1.0), ('B', 1.01)):
            nbcmp.plant(n, f'c{lab}-{lab}', 'spectral/x', {'instr': 1000 * k, 'alloc': 100},
                        [('Main', {'calloc': 1000, 'size': 200 * k})],
                        [(['-c', 'x.hs', '-o', f'_make/c{lab}-{lab}/spectral/x/Main.o'], 4000 * k * k)])
            for lev in ('O2', 'O1'):
                lb = f'c{lab}-{lab}' if lev == 'O2' else f'c{lab}-o1-{lab}'
                for i in (1, 2):
                    pkgcmp.write_csv(f'{w}/vpapi/cres/{lb}/p-{i}.csv',
                                     [('All.s', 100, int(1000 * k)), ('All.q', 50, 500)])
                    pkgcmp.write_csv(f'{w}/vpapi/res-{lb}-{i}.csv', [('All.v', int(100 * k), 2000)])
            with open(f'{o}/a2t-{lab}.tsv', 'w') as fh:
                fh.write(f'c\t{100 * k}\t0\t{50 * k * k}\nd\t{100 * (2 - k)}\t0\t20\n')
            with open(f'{o}/a2t-groups-{lab}.tsv', 'w') as fh:
                fh.write(f'summed:c\t{200 * k}\t0\t30\n')
            with open(f'{o}/tix-{lab}.tsv', 'w') as fh:
                fh.write(f'27799 -O2\tinner\t{"fused" if lab == "A" else "split"}\n')
            with open(f'{o}/ghcb-{lab}.tsv', 'w') as fh:
                fh.write(f'module\tghc/stage1\tM.o\talloc\t{1000 * k}\nmodule\tghc/stage1\tN.o\tsize\t10\n')
            with open(f'{o}/utf8-{lab}.tsv', 'w') as fh:
                fh.write(f'W1 -O2\tper-element\t63.000\nW2 -O2\tper-element\t{84 * k:.3f}\n'
                         f'W3 -O2\tper-element\t{100 * (1 + (k - 1) / 10):.3f}\n')
        # The random test: A whole, a seed known, B a seed failing and its last
        # ten seeds not run, S its last seed not run, F its first seed failing.
        top = FUZZ_FIRST + FUZZ_LANES * FUZZ_PER_LANE
        want = list(range(FUZZ_FIRST, top))
        first, kseed, failed, tail = want[0], want[5], want[-11], want[-10:]
        w27915 = "panic[Can't find weight for edge that should have one]"

        def plant_fuzz(lab, fail=(), drop=(), known=()):
            os.makedirs(f'{o}/fuzz-{lab}')
            for i in range(FUZZ_LANES):
                with open(f'{o}/fuzz-{lab}/result-{i}.txt', 'w') as fh:
                    for s in range(FUZZ_FIRST + i * FUZZ_PER_LANE, FUZZ_FIRST + (i + 1) * FUZZ_PER_LANE):
                        if s in drop:
                            continue
                        fh.write(f'{s} FAIL outputs differ: t-O1/d,b-O0/d | t-O2/d (20 runs, 5s)\n'
                                 if s in fail else f'{s} known t-O1 {w27915} (18 runs, 5s)\n'
                                 if s in known else f'{s} ok (20 runs, 5s)\n')
        plant_fuzz('A', known=(kseed,))
        plant_fuzz('B', (failed,), tail)
        plant_fuzz('S', (), tail[-1:])
        plant_fuzz('F', (first,))
        # Label Q measured on tree T, as p103 on t103, and label A's -O2 runs
        # on a tree U too, beside its own.
        for run in ('cT-Q', 'cU-A'):
            nbcmp.plant(n, run, 'spectral/x', {'instr': 1010, 'alloc': 100}, [], [])
            pkgcmp.write_csv(f'{w}/vpapi/cres/{run}/p-1.csv', [('All.s', 100, 1010), ('All.q', 50, 500)])
        pkgcmp.write_csv(f'{w}/vpapi/res-cT-o1-Q-1.csv', [('All.v', 101, 2000)])
        n9 = len(want)
        path = report(w, 'A', 'B', f'{w}/r.txt')
        text = open(path).read()
        text += '\n'.join([''] + fuzz(o, 'S', 'F') + fuzz(o, 'A', 'C'))
        qt = '\n'.join(nofib(w, 'A', 'Q', o)[:3] + packages(w, 'A', 'Q') + [''])
        for piece in ('nofib -O2\ncA-A to cT-Q: benchmarks run by both 1 (only cA-A: 0, only cT-Q: 0)\n',
                      'containers -O2\ncT-Q against cA-A: 2 benchmarks',
                      '+1.000%  p/All.s (stable)  1000 1010\n  allocation by 0.10%: 0 up, 0 down\n'
                      f'containers -O1\n  not compared: no runs in {w}/vpapi/cres/cQ-o1-Q\n',
                      'vector -O1\ngeometric mean TOT_INS',
                      '  allocation by 0.05%: 1 up, 0 down\n    +1.000%  All.v  100 101\n'):
            if piece not in qt:
                bad.append(f'the report of Q on tree T lacks {piece!r}')
        for names, o1, want_name in ((['cT-Q', 'cU-Q'], '', None),
                                     (['cT-Q', 'cQ-Q', 'cU-Q'], '', 'cQ-Q'),
                                     (['cT-o1-Q'], '', 'cQ-Q'), (['cT-o1-Q'], 'o1-', 'cT-o1-Q')):
            try:
                got = run_name(names, 'Q', o1)
            except ValueError as e:
                got = None if str(e) == 'runs of Q on trees T, U' else e
            if got != want_name:
                bad.append(f'run_name({names}, Q, {o1!r}): {got!r}, not {want_name!r}')
        for piece in ('  program instructions by 0.20%: 1 up, 0 down\n    +1.000%  spectral/x  1000 1010',
                      '  compiler instructions by 1.00%: 1 up, 0 down\n    +2.010%  spectral/x  4000 4080',
                      '  object size by 0.20%: 1 up, 0 down',
                      'containers -O2\ncB-B against cA-A: 2 benchmarks, 2 in both, 2 stable in both;'
                      ' geometric mean of the medians over the 2 in both +0.499%; 1 rise, 0 fall;'
                      ' geometric mean over the stable +0.499%\n',
                      '  instructions by 0.10%: 1 up, 0 down\n    +1.000%  p/All.s (stable)  1000 1010',
                      'vector -O1\n',
                      '  allocation by 0.05%: 1 up, 0 down\n    +1.000%  All.v  100 101',
                      '  bytes allocated a call by 0.20%: 1 up, 0 down\n    +2.010%  c  50 51',
                      '  instructions a call by 0.20%: 1 up, 1 down\n    +1.000%  c  100 101\n'
                      '    -1.000%  d  100 99',
                      'A2T groups\nA to B: cells counted in both 1 of 1\n  worse by 0.2%: 1, by 1%: 1\n'
                      '  better by 0.2%: 0\n  instructions a call by 0.20%: 1 up, 0 down\n'
                      '    +1.000%  summed:c  200 202\n',
                      'megaparsec -O2\n  not compared:',
                      '  27799 -O2: inner fused -> split',
                      '  alloc by 0.1%: 1 up, 0 down\n      +1.000%  M.o  1000 1010',
                      'comp1\n  not compared:',
                      'utf8 Text scan\n  B against A: 3 rows in both\n  rows that differ: 1\n'
                      '    W2 -O2: per-element 84.000 -> 84.840 +1.00%\n\n',
                      f'  A: pass, {n9} seeds run, {n9 - 1} ok, 1 known, 0 failing\n'
                      f'    {w27915}: O0 both 0, tree only 0, base only 0; O1 both 0, tree only 1,'
                      ' base only 0; O2 both 0, tree only 0, base only 0\n'
                      f'    known GHC #27915, 1 seeds: tree only {kseed}\n',
                      f'  B: FAIL, {n9 - 10} seeds run, {n9 - 11} ok, 0 known, 1 failing: {failed};'
                      f' not run: {tail[0]}-{tail[-1]}\n      1 outputs differ\n'
                      '    outside the largest group: t-O2 1\n',
                      f'  S: FAIL, {n9 - 1} seeds run, {n9 - 1} ok, 0 known, 0 failing;'
                      f' not run: {tail[-1]}\n',
                      f'  F: FAIL, {n9} seeds run, {n9 - 1} ok, 0 known, 1 failing: {first}\n',
                      f'  C: FAIL, no results in {o}/fuzz-C'):
            if piece not in text:
                bad.append(f'the report lacks {piece!r}')
        # a label without groups, as any before ruling 473: not compared
        got = a2t(o, 'A', 'S', 'groups')
        if got[:1] != ['A2T groups'] or got[1:2] != [f'  not compared: [Errno 2] No such file'
                                                      f' or directory: {o + "/a2t-groups-S.tsv"!r}']:
            bad.append(f'groups against a label without them: {got}')
    # --check: a label K with every record, nofib's tables kept in battery/,
    # passes; each record emptied in turn fails it, naming the record; a
    # label with none fails by every section.
    with tempfile.TemporaryDirectory(prefix='runreport-') as w:
        n, v, o = f'{w}/nofib-r', f'{w}/vpapi', f'{w}/battery'
        recs = [f'{o}/nofib-{r}.tsv' for _, r in nofib_runs('K')]
        recs += [f'{n}/stats/{r}/1.csv' for _, r in nofib_runs('K')]
        for lab in ('cK-K', 'cK-o1-K'):
            recs += [f'{v}/cres/{lab}/p-1.csv', f'{v}/mres/{lab}/bench-speed-1.csv',
                     f'{v}/res-{lab}-1.csv']
        recs += [f'{o}/{x}' for x in ('a2t-K.tsv', 'comp1-K.runs', 'comp2-K.runs', 'perf-K.tsv',
                                      'scale-K.txt', 'tix-K.tsv', 'utf8-K.tsv',
                                      'fuzz-K/result-0.txt', 'ghcb-K.tsv', 'pkgb-K.tsv',
                                      'rebuild/K.done')]
        for p in recs:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w') as fh:
                fh.write('spectral/x/Main.perf.results.tsv\tspectral/x//run//perf//instructions:u\t1.0e3\n'
                         if '/nofib-' in p else 'x\n')
        got = check(w, [])
        if got != (['1 labels checked, 0 lacking records'], 0):
            bad.append(f'--check of a whole label: {got}')
        for p in recs[:-1]:
            os.rename(p, p + '.aside')
            open(p, 'w').close()
            (lines, rc), rel = check(w, ['K']), os.path.relpath(p, w)
            if rc != 1 or len(lines) != 2 or not lines[0].startswith('K: ') \
                    or os.path.basename(os.path.dirname(rel) if '/stats/' in p else rel)[:6] not in lines[0]:
                bad.append(f'--check with {rel} empty: {rc} {lines}')
            os.replace(p + '.aside', p)
        lines, rc = check(w, ['Z'])
        if rc != 1 or len(lines[0].split('; ')) != len(recs) - 1:
            bad.append(f'--check of a label with nothing: {rc} {lines[0].split("; ")}')
    for x in bad:
        print('FAIL', x)
    print('ok   runreport.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    work = WORK
    if argv[:1] == ['--work'] and len(argv) > 1:
        work, argv = os.path.abspath(argv[1]), argv[2:]
    if argv[:1] == ['--check']:
        lines, rc = check(work, argv[1:])
        print('\n'.join(lines))
        return rc
    if len(argv) != 3:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    with contextlib.redirect_stderr(io.StringIO()):
        print(report(work, *argv))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
