#!/usr/bin/env python3
"""battery.py's nofib runs A and B, each NAME's tables in the work
directory's battery/nofib-NAME.tsv, or under nofib-r/nofib/_make/NAME where
that file is missing or empty, and its compiles' counts in
nofib-r/stats/NAME, compared
benchmark by benchmark over the benchmarks both ran: the program's instructions:u, bytes allocated, collections and
copied bytes, and, summed over the benchmark's modules, the compiler's bytes
allocated, its instructions:u (with the assembler it runs; stats/NAME, the
-c invocations), the objects' size, and the compiler's collections and copied
bytes. Instructions rising with the collections or the copied bytes are
the collector's at least in part; rising with both steady, the mutator's.
For each figure, the geometric mean of B/A, the total's ratio, the
benchmarks moving by 0.2% and 1% either way, the extremes.

Usage: python3 tools/NCG-battery/nbcmp.py [--work DIR] [--out DIR] A B
       python3 tools/NCG-battery/nbcmp.py [--work DIR] [--out DIR] --table A
       python3 tools/NCG-battery/nbcmp.py [--work DIR] [--out DIR] --keep A
       python3 tools/NCG-battery/nbcmp.py --self-test

A and B are the runs' names: cTREE-LABEL at -O2, o1-LABEL and o0-LABEL.
--table prints A's figures, a benchmark a line. --keep writes every .tsv
under _make/A into OUT/nofib-A.tsv, a line `PATH<TAB>LINE` a line of each,
PATH relative to _make/A, and exits 0 only once that file reads back to the
same tables; battery.py's nofib part runs it after nofib-run, and
rebuild.py's prune does the same and then removes _make/A. The work
directory is battery.py's, dist-ghcho by default, and OUT battery.py's
--out, WORK/battery by default."""
import contextlib
import glob
import io
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from battery import WORK  # noqa: E402

MOVE, BAR = 0.002 - 1e-12, 0.01 - 1e-12

# Appended in the order they were added, so that --table's columns stay.
NAMES = (('instr', 'program instructions'), ('alloc', 'program bytes allocated'),
         ('calloc', 'compiler bytes allocated'),
         ('cinstr', 'compiler instructions'), ('size', 'object size'),
         ('gcs', 'program collections'), ('copied', 'program copied bytes'),
         ('cgcs', 'compiler collections'), ('ccopied', 'compiler copied bytes'))
RUN = {'//run//perf//instructions:u': 'instr',
       '//run//rts stats//bytes allocated': 'alloc',
       '//run//rts stats//num_GCs': 'gcs',
       '//run//rts stats//copied_bytes': 'copied'}
COMPILE = {'//rts stats//bytes allocated': 'calloc', '//size': 'size',
           '//rts stats//num_GCs': 'cgcs',
           '//rts stats//copied_bytes': 'ccopied'}


def tsv(lines):
    for line in lines:
        k, _, v = line.rstrip('\n').partition('\t')
        if v:
            yield k, float(v)


def kept(n, out, outdir=None):
    """Where run out's tables are kept: OUT/nofib-out.tsv, OUT the work
    directory's battery unless given."""
    return os.path.join(outdir or os.path.join(os.path.dirname(os.path.abspath(n)), 'battery'),
                        f'nofib-{out}.tsv')


def made(n, out):
    """{path relative to _make/out: its lines} of every .tsv under it."""
    root = os.path.join(n, 'nofib', '_make', out)
    t = {}
    for p in glob.glob(os.path.join(glob.escape(root), '**', '*.tsv'), recursive=True):
        if os.path.isfile(p):
            with open(p) as fh:
                lines = fh.read().split('\n')
            t[os.path.relpath(p, root)] = lines[:-1] if lines[-1] == '' else lines
    return t


def read_kept(path):
    t = {}
    with open(path) as fh:
        for line in fh:
            rel, sep, rest = line.rstrip('\n').partition('\t')
            if not sep:
                raise ValueError(f'{path}: a line without a path, {line[:60]!r}')
            t.setdefault(rel, []).append(rest)
    return t


def tables(n, out, outdir=None):
    """Run out's tables, {path: lines}, from its kept file where that is not
    empty, else from under _make."""
    k = kept(n, out, outdir)
    if os.path.isfile(k) and os.path.getsize(k):
        return read_kept(k)
    return made(n, out)


def load_from(t, n, out):
    """The figures of tables t, {path: lines}, and of stats/out, by benchmark."""
    root = os.path.join(n, 'nofib', '_make', out)
    figs = {}
    for p in t:
        if os.path.basename(p) != 'Main.perf.results.tsv':
            continue
        f = figs.setdefault(os.path.dirname(p) or '.', {})
        for k, v in tsv(t[p]):
            for suffix, key in RUN.items():
                if k.endswith(suffix):
                    f[key] = v
    tests = sorted(figs, key=len, reverse=True)

    def owner(rel):
        for test in tests:
            if rel.startswith(test + os.sep):
                return test
        return None

    def below(path):
        # A compile's paths are those of the nofib-r it ran in, which may
        # since have moved: below the run's _make directory they are n's.
        _, sep, rel = path.rpartition(os.sep + os.path.join('nofib', '_make', out) + os.sep)
        return rel if sep else os.path.relpath(path, root)
    for p in t:
        if not p.endswith('.compile.tsv'):
            continue
        test = owner(p)
        if test is None:
            continue
        f = figs[test]
        for k, v in tsv(t[p]):
            for suffix, key in COMPILE.items():
                if k.endswith(suffix):
                    f[key] = f.get(key, 0) + v
    sdir = os.path.join(n, 'stats', out)
    for a in glob.glob(os.path.join(glob.escape(sdir), '*.args')):
        with open(a) as fh:
            lines = fh.read().split('\n')
        cwd, args = lines[0], lines[1:]
        if '-c' not in args or '-o' not in args:
            continue
        test = owner(below(os.path.normpath(os.path.join(cwd, args[args.index('-o') + 1]))))
        csv = a[:-5] + '.csv'
        if test is None or not os.path.exists(csv):
            continue
        with open(csv) as fh:
            for line in fh:
                x = line.split(',')
                if len(x) > 2 and x[2] == 'instructions:u':
                    figs[test]['cinstr'] = figs[test].get('cinstr', 0) + float(x[0])
    return figs


def load(n, out, outdir=None):
    figs = load_from(tables(n, out, outdir), n, out)
    if not figs:
        raise ValueError(f'no Main.perf.results.tsv in {kept(n, out, outdir)}'
                         f' or under {os.path.join(n, "nofib", "_make", out)}')
    return figs


def keep(n, out, outdir=None, drop=False, say=print):
    """Run out's tables written to its kept file and read back; with drop,
    _make/out then removed. Where _make/out is gone, a kept file that
    reads is enough."""
    root, k = os.path.join(n, 'nofib', '_make', out), kept(n, out, outdir)
    if not os.path.isdir(root):
        load(n, out, outdir)
        say(f'{out}: no {root}, the tables kept in {k}')
        return
    t = made(n, out)
    load_made = load_from(t, n, out)
    if not load_made:
        raise ValueError(f'no Main.perf.results.tsv under {root}')
    os.makedirs(os.path.dirname(k), exist_ok=True)
    part = k + '.partial'
    with open(part, 'w') as fh:
        for rel in sorted(t):
            if '\t' in rel or '\n' in rel:
                raise ValueError(f'{root}/{rel}: a path a kept file cannot hold')
            fh.writelines(f'{rel}\t{line}\n' for line in t[rel])
    back = read_kept(part)
    if back != {r: ls for r, ls in t.items() if ls} or load_from(back, n, out) != load_made:
        os.unlink(part)
        raise ValueError(f'{part} does not read back to the tables under {root}')
    os.replace(part, k)
    say(f'{out}: {len(t)} tables under {root} kept in {k}')
    if drop:
        shutil.rmtree(root)
        say(f'{out}: removed {root}')


def compare(n, a, b, outdir=None):
    out = []
    fa, fb = load(n, a, outdir), load(n, b, outdir)
    both = sorted(set(fa) & set(fb))
    out.append(f'{a} to {b}: benchmarks run by both {len(both)}'
               f' (only {a}: {len(set(fa) - set(fb))}, only {b}:'
               f' {len(set(fb) - set(fa))})')
    for key, name in NAMES:
        rs = [(fb[t][key] / fa[t][key], t) for t in both
              if fa[t].get(key) and fb[t].get(key)]
        if not rs:
            out.append(f'  {name}: no figures')
            continue
        gm = math.exp(sum(math.log(r) for r, _ in rs) / len(rs))
        up = sorted(((r, t) for r, t in rs if r - 1 >= MOVE), reverse=True)
        dn = sorted((r, t) for r, t in rs if 1 - r >= MOVE)
        tot = (sum(fb[t][key] for _, t in rs) / sum(fa[t][key] for _, t in rs))
        same = sum(r == 1 for r, _ in rs)
        out.append(f'  {name} ({len(rs)}): geomean {gm:.5f}, total {tot:.5f},'
                   f' equal {same}; up by 0.2% {len(up)}, by 1%'
                   f' {sum(r - 1 >= BAR for r, _ in up)}; down by 0.2% {len(dn)},'
                   f' by 1% {sum(1 - r >= BAR for r, _ in dn)}')
        for r, t in up[:5]:
            out.append(f'      {r:.4f} {t}')
        for r, t in dn[:5]:
            out.append(f'      {r:.4f} {t}')
    return out


def table(n, a, outdir=None):
    fa = load(n, a, outdir)
    out = ['benchmark\t' + '\t'.join(k for k, _ in NAMES)]
    for t in sorted(fa):
        out.append(t + '\t' + '\t'.join(str(int(fa[t][k])) if k in fa[t] else '-'
                                        for k, _ in NAMES))
    return out


def plant(n, out, test, run, modules, compiles):
    """A run's files: run = {figure: value} of the program, modules =
    [(module, {figure: value})], compiles = [(args, instructions)]."""
    d = os.path.join(n, 'nofib', '_make', out, test)
    os.makedirs(d, exist_ok=True)
    # nofib-run's own names, kept apart from RUN and COMPILE
    keys = {'instr': '//run//perf//instructions:u',
            'alloc': '//run//rts stats//bytes allocated',
            'gcs': '//run//rts stats//num_GCs',
            'copied': '//run//rts stats//copied_bytes'}
    with open(os.path.join(d, 'Main.perf.results.tsv'), 'w') as fh:
        fh.write(f'{test}//run//rts stats//GC_cpu_seconds\t1.0e-2\n')
        for k, v in run.items():
            fh.write(f'{test}{keys[k]}\t{v:e}\n')
    keys = {'calloc': '//rts stats//bytes allocated', 'size': '//size',
            'cgcs': '//rts stats//num_GCs', 'ccopied': '//rts stats//copied_bytes'}
    for mod, figs in modules:
        with open(os.path.join(d, f'{mod}.o.compile.tsv'), 'w') as fh:
            fh.write(f'{test}//objects//{mod}.o//rts stats//major_gcs\t5.0\n')
            for k, v in figs.items():
                fh.write(f'{test}//objects//{mod}.o{keys[k]}\t{v:e}\n')
    s = os.path.join(n, 'stats', out)
    os.makedirs(s, exist_ok=True)
    for i, (args, ins) in enumerate(compiles):
        stem = os.path.join(s, f'{test.replace("/", "_")}.{i}')
        with open(stem + '.args', 'w') as fh:
            fh.write('\n'.join([os.path.join(n, 'nofib')] + args) + '\n')
        with open(stem + '.csv', 'w') as fh:
            fh.write(f'# started\n\n{ins},,instructions:u,9,100.00,,\n')


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='nbcmp-') as d:
        n = os.path.join(d, 'nofib-r')
        def c(out, test, mod):
            return ['-Rghc-timing', '-c', f'{test}/{mod}.hs', '-o',
                    f'_make/{out}/{test}/{mod}.o']
        for out, k in (('A', 1.0), ('B', 1.01)):
            # x: the program's instructions up by k, its collections and
            # copied bytes doubled in B; the compiler's of Foo up by k.
            g = 1 if out == 'A' else 2
            plant(n, out, 'spectral/x',
                  {'instr': 1000 * k, 'alloc': 100, 'gcs': 10 * g, 'copied': 50 * g},
                  [('Main', {'calloc': 1000, 'size': 200, 'cgcs': 1, 'ccopied': 7}),
                   ('Foo', {'calloc': 500, 'size': 100, 'cgcs': 2, 'ccopied': 3 * g})],
                  [(c(out, 'spectral/x', 'Main'), 4000),
                   (c(out, 'spectral/x', 'Foo'), 2000 * k),
                   (['-o', f'_make/{out}/spectral/x/Main'], 999)])
            # xx: a name x prefixes, unchanged
            plant(n, out, 'spectral/xx', {'instr': 3000, 'alloc': 300, 'gcs': 4,
                                          'copied': 9},
                  [('Main', {'calloc': 10, 'size': 20, 'cgcs': 1, 'ccopied': 1})],
                  [(c(out, 'spectral/xx', 'Main'), 30)])
        plant(n, 'B', 'real/y', {'instr': 5, 'alloc': 5, 'gcs': 1, 'copied': 1},
              [], [])
        got = compare(n, 'A', 'B')
        want = ['A to B: benchmarks run by both 2 (only A: 0, only B: 1)',
                '  program instructions (2): geomean 1.00499, total 1.00250,'
                ' equal 1; up by 0.2% 1, by 1% 1; down by 0.2% 0, by 1% 0',
                '      1.0100 spectral/x',
                '  program bytes allocated (2): geomean 1.00000, total 1.00000,'
                ' equal 2; up by 0.2% 0, by 1% 0; down by 0.2% 0, by 1% 0',
                '  compiler bytes allocated (2): geomean 1.00000, total 1.00000,'
                ' equal 2; up by 0.2% 0, by 1% 0; down by 0.2% 0, by 1% 0',
                '  compiler instructions (2): geomean 1.00167, total 1.00332,'
                ' equal 1; up by 0.2% 1, by 1% 0; down by 0.2% 0, by 1% 0',
                '      1.0033 spectral/x',
                '  object size (2): geomean 1.00000, total 1.00000,'
                ' equal 2; up by 0.2% 0, by 1% 0; down by 0.2% 0, by 1% 0',
                '  program collections (2): geomean 1.41421, total 1.71429,'
                ' equal 1; up by 0.2% 1, by 1% 1; down by 0.2% 0, by 1% 0',
                '      2.0000 spectral/x',
                '  program copied bytes (2): geomean 1.41421, total 1.84746,'
                ' equal 1; up by 0.2% 1, by 1% 1; down by 0.2% 0, by 1% 0',
                '      2.0000 spectral/x',
                '  compiler collections (2): geomean 1.00000, total 1.00000,'
                ' equal 2; up by 0.2% 0, by 1% 0; down by 0.2% 0, by 1% 0',
                '  compiler copied bytes (2): geomean 1.14018, total 1.27273,'
                ' equal 1; up by 0.2% 1, by 1% 1; down by 0.2% 0, by 1% 0',
                '      1.3000 spectral/x']
        for i, (g, w) in enumerate(zip(got + [''] * len(want), want)):
            if g != w:
                bad.append(f'line {i}: {g!r}, not {w!r}')
                break
        if len(got) != len(want):
            bad.append(f'{len(got)} lines, not {len(want)}')
        got = table(n, 'B')
        want = ['real/y\t5\t5\t-\t-\t-\t1\t1\t-\t-',
                'spectral/x\t1010\t100\t1500\t6020\t300\t20\t100\t3\t13']
        if got[1:3] != want:
            bad.append(f'table {got[1:3]}, not {want}')
        # Moved elsewhere, the compiles' recorded paths name the old place.
        shutil.copytree(n, os.path.join(d, 'moved', 'nofib-r'))
        if table(os.path.join(d, 'moved', 'nofib-r'), 'B') != table(n, 'B'):
            bad.append('the moved results lost figures')
        with contextlib.redirect_stderr(io.StringIO()) as err:
            rc = main(['--work', d, 'A', 'C'])
        if rc != 2 or f'no Main.perf.results.tsv in {d}/battery/nofib-C.tsv or under' not in err.getvalue():
            bad.append(f'a run with no results exited {rc}, not 2: {err.getvalue()!r}')
        # Kept: B's tables in battery/nofib-B.tsv, _make/B removed, and the
        # figures as they were; A's kept without the removal, the kept file
        # read before _make, here missing a benchmark.
        before, said = table(n, 'B'), []
        keep(n, 'B', drop=True, say=said.append)
        k = os.path.join(d, 'battery', 'nofib-B.tsv')
        if os.path.exists(os.path.join(n, 'nofib', '_make', 'B')) or not os.path.isfile(k) \
                or table(n, 'B') != before or len(said) != 2 or 'removed' not in said[1]:
            bad.append(f'kept B: {said}, {table(n, "B") if os.path.isfile(k) else "no file"}')
        if sorted(read_kept(k)) != ['real/y/Main.perf.results.tsv', 'spectral/x/Foo.o.compile.tsv',
                                    'spectral/x/Main.o.compile.tsv',
                                    'spectral/x/Main.perf.results.tsv',
                                    'spectral/xx/Main.o.compile.tsv',
                                    'spectral/xx/Main.perf.results.tsv']:
            bad.append(f'kept B holds {sorted(read_kept(k))}')
        keep(n, 'B', say=said.append)  # _make/B gone, the kept file enough
        keep(n, 'A', say=said.append)
        shutil.rmtree(os.path.join(n, 'nofib', '_make', 'A', 'spectral', 'xx'))
        if [x.split('\t')[0] for x in table(n, 'A')[1:]] != ['spectral/x', 'spectral/xx']:
            bad.append(f'kept A read after _make: {table(n, "A")}')
        # Nothing to keep: no _make, or one with no program's table.
        os.makedirs(os.path.join(n, 'nofib', '_make', 'E', 'spectral', 'x'))
        with open(os.path.join(n, 'nofib', '_make', 'E', 'spectral', 'x', 'Main.link.tsv'), 'w') as fh:
            fh.write('spectral/x//size\t1.0\n')
        for out in ('C', 'E'):
            with contextlib.redirect_stderr(io.StringIO()):
                rc = main(['--work', d, '--keep', out])
            if rc != 2 or os.path.exists(os.path.join(d, 'battery', f'nofib-{out}.tsv')):
                bad.append(f'--keep {out}, nothing to keep: {rc}')
    for x in bad:
        print('FAIL', x)
    print('ok   nbcmp.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    work, outdir = WORK, None
    if argv[:1] == ['--work'] and len(argv) > 1:
        work, argv = argv[1], argv[2:]
    if argv[:1] == ['--out'] and len(argv) > 1:
        outdir, argv = argv[1], argv[2:]
    n = os.path.join(work, 'nofib-r')
    try:
        if argv[:1] == ['--table'] and len(argv) == 2:
            print('\n'.join(table(n, argv[1], outdir)))
        elif argv[:1] == ['--keep'] and len(argv) == 2:
            keep(n, argv[1], outdir)
        elif len(argv) == 2 and not argv[0].startswith('--'):
            print('\n'.join(compare(n, *argv, outdir)))
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (ValueError, OSError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
