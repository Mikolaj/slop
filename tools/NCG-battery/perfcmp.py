#!/usr/bin/env python3
"""battery.py's perf part under label B against label A, from OUT/perf-LABEL.tsv
(the tables hadrian's test --summary-metrics writes): per metric the tests in
both, the geometric mean of B/A and the largest moves either way. A metric is
what GHC's testsuite reads off the compile or the run, such as
compile_time/bytes allocated, the bytes the compiler allocates on the heap.

Usage: python3 tools/NCG-battery/perfcmp.py [--work DIR] [--out DIR]
           A B [TREE [RANGE]]
       python3 tools/NCG-battery/perfcmp.py --self-test

With TREE, the rows outside the window GHC's CI would hold them to: each row's
tolerance is read off the all.T files of the work directory's ghc-TREE and
the bounds are those of the driver's RelativeMetricAcceptanceWindow around A's
figure. A row above is one a commit must name under `Metric Increase`, below
under `Metric Decrease`. A row with no tolerance read, its test named by
a variable in all.T, is only counted. With RANGE, a git range in that
tree, each row says whether a commit message in the range names its test in
that direction, by the driver's own expression. WORK is dist-ghcho by default
and OUT WORK/battery. Exits 0 when it compared, 2 when a table or the tree is
missing or RANGE fails."""

import math
import os
import re
import subprocess
import sys
import tempfile

WORK = '/home/mikolaj/slop/dist-ghcho'
RESIDENCY = ('max_bytes_used', 'peak_megabytes_allocated')  # the driver's
MOVES = 6


def table(path):
    """{(test, way, metric): value} of a --summary-metrics table."""
    out = {}
    with open(path) as fh:
        for line in fh:
            f = line.rstrip('\n').split('\t')
            if len(f) == 5 and f[0] == 'local':
                out[(f[1], f[2], f[3])] = float(f[4])
    return out


def metrics_of(block):
    """(metric, tolerance) of the statistics one test of an all.T collects."""
    names = r"(\[[^\]]*\]|'[^']*')"
    tol = r'([0-9.]+)'
    out = []
    for fun, tag in (('collect_compiler_stats', 'compile_time'),
                     ('collect_stats', 'runtime')):
        for m in re.finditer(rf'\b{fun}\(\s*{names}\s*,\s*{tol}\s*[,)]', block):
            for name in re.findall(r"'([^']*)'", m.group(1)):
                out.append((f'{tag}/{name}', float(m.group(2))))
    for m in re.finditer(rf'\bcollect_compiler_runtime\(\s*{tol}\s*\)', block):
        out.append(('compile_time/bytes allocated', float(m.group(1))))
    for fun, tag in (('collect_compiler_residency', 'compile_time'),
                     ('collect_runtime_residency', 'runtime')):
        for m in re.finditer(rf'\b{fun}\(\s*{tol}\s*\)', block):
            out += [(f'{tag}/{r}', float(m.group(1))) for r in RESIDENCY]
    return out


def tolerances(tree):
    """{(test, metric): tolerance} over the tree's all.T files."""
    out = {}
    for root in ('testsuite/tests', 'libraries'):
        for dp, _, fn in os.walk(os.path.join(tree, root)):
            if 'all.T' not in fn:
                continue
            with open(os.path.join(dp, 'all.T'), errors='replace') as fh:
                s = fh.read()
            marks = list(re.finditer(r'''^\s*test\s*\(\s*['"]([^'"]+)['"]''', s, re.M))
            for i, m in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(s)
                for metric, tol in metrics_of(s[m.end():end]):
                    out[(m.group(1), metric)] = tol
    return out


def bounds(base, tol):
    """RelativeMetricAcceptanceWindow.get_bounds of the driver's perf_notes.py."""
    return (math.trunc(base * ((100 - tol) / 100)),
            math.trunc(0.5 + math.ceil(base * ((100 + tol) / 100))))


def named(messages):
    """{(test, direction)} a text of commit messages allows, by the expression
    of the driver's parse_allowed_perf_changes."""
    s = r"(?:\s*\n?\s+)"
    qstr = r"(?:'(?:[^'\\]|\\.)*')"
    inner = r"(?:" + qstr + r"(?:" + s + r"?," + s + r"?" + qstr + r")*)?"
    qlist = r"(?:\[" + s + r"?" + inner + s + r"?\])"
    exp = (r"^\s*Metric" + s + r"(Increase|Decrease)"
           + s + r"?(" + qstr + r"|" + qlist + r")?"
           + s + r"?(\(" + r"(?:[^')]|" + qstr + r")*" + r"\))?"
           + s + r"?:?"
           + s + r"?((?:(?!\n\n)(?!\n[^\s])(?:.|\n))*)")
    return {(t, d) for d, _, _, ts in re.findall(exp, messages, re.M)
            for t in ts.split()}


def compare(a, b):
    """The lines comparing two tables."""
    keys = sorted(set(a) & set(b))
    out = [f'{len(a)} and {len(b)} rows, {len(keys)} in both;'
           f' only in A: {sorted(set(a) - set(b))[:10]};'
           f' only in B: {sorted(set(b) - set(a))[:10]}']
    by = {}
    for k in keys:
        by.setdefault(k[2], []).append(k)

    def show(r, k):
        return f'{k[0]}({k[1]}) {100 * (r - 1):+.3f}%'
    for m, ks in sorted(by.items()):
        rs = sorted((b[k] / a[k], k) for k in ks if a[k] > 0 and b[k] > 0)
        if not rs:
            continue
        g = math.exp(sum(math.log(r) for r, _ in rs) / len(rs))
        out.append(f'{m}: {len(rs)} tests, geomean {100 * (g - 1):+.3f}%')
        out.append('  falls: ' + ', '.join(show(r, k) for r, k in rs[:MOVES]))
        out.append('  rises: ' + ', '.join(show(r, k) for r, k in rs[::-1][:MOVES]))
    return out


def outside(a, b, tols, allowed):
    """The lines of the rows outside their windows; allowed is None or the
    set named() returned."""
    keys = sorted(set(a) & set(b))
    have = [k for k in keys if (k[0], k[2]) in tols]
    rows = {'Increase': [], 'Decrease': []}
    for k in have:
        tol = tols[(k[0], k[2])]
        lo, hi = bounds(a[k], tol)
        d = 'Increase' if b[k] > hi else 'Decrease' if b[k] < lo else None
        if d:
            mark = ('' if allowed is None else
                    '  named' if (k[0], d) in allowed else '  NOT named')
            rows[d].append((abs(b[k] / a[k] - 1), f'  {k[0]}({k[1]}) {k[2]} tol {tol:g}%:'
                            f' {a[k]:.0f} -> {b[k]:.0f}'
                            f' {100 * (b[k] / a[k] - 1):+.2f}%{mark}'))
    out = [f'windows: {len(have)} of {len(keys)} rows have a tolerance']
    for d in ('Increase', 'Decrease'):
        out.append(f'Metric {d}, outside the window: {len(rows[d])}')
        out += [line for _, line in sorted(rows[d], reverse=True)]
    return out


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    work, outdir = WORK, None
    while argv[:1] and argv[0] in ('--work', '--out'):
        if len(argv) < 2:
            print(f'{argv[0]} needs a value', file=sys.stderr)
            return 2
        if argv[0] == '--work':
            work = argv[1]
        else:
            outdir = argv[1]
        argv = argv[2:]
    if not 2 <= len(argv) <= 4:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    outdir = outdir or os.path.join(work, 'battery')
    tabs = []
    for label in argv[:2]:
        path = os.path.join(outdir, f'perf-{label}.tsv')
        if not os.path.isfile(path):
            print(f'no {path}', file=sys.stderr)
            return 2
        tabs.append(table(path))
    a, b = tabs
    lines = compare(a, b)
    if len(argv) > 2:
        tree = os.path.join(work, f'ghc-{argv[2]}')
        if not os.path.isdir(tree):
            print(f'no {tree}', file=sys.stderr)
            return 2
        allowed = None
        if len(argv) > 3:
            p = subprocess.run(['git', '-C', tree, 'log', '--format=%B', argv[3]],
                               capture_output=True, text=True)
            if p.returncode:
                print(f'git log {argv[3]}: {p.stderr.strip()}', file=sys.stderr)
                return 2
            allowed = named(p.stdout)
        lines += outside(a, b, tolerances(tree), allowed)
    print('\n'.join(lines))
    return 0


ALL_T = """
test('Up', [ collect_compiler_stats('bytes allocated',2) ], compile, ['-O'])
test ('Down',
      [ collect_compiler_runtime(1),
        collect_compiler_residency(15) ],
      compile, [''])
test('Run', [ collect_stats(['bytes allocated', 'max_bytes_used'], 5) ],
     compile_and_run, [''])
test('Within', [ collect_stats('bytes allocated', 5, 'f.stats') ], x, [''])
test('Named', [ collect_compiler_stats('bytes allocated', 2) ], compile, [''])
for t in names:
    test(t, [ collect_compiler_stats('bytes allocated', 2) ], compile, [''])
"""
TSV_A = {'Up': 100000, 'Down': 100000, 'Run': 1000, 'Within': 1000, 'Named': 1000,
         'Free': 1000}
TSV_B = {'Up': 102001, 'Down': 98000, 'Run': 1060, 'Within': 1050, 'Named': 1100,
         'Free': 2000}
MESSAGE = ('Subject\n\nMetric Increase:\n    Named\n    Another\n\n'
           "Metric Decrease 'bytes allocated':\n    Down\n\nMetric Increase: Inline\n"
           'Not a metric line: Up\n\nMetric Decrease:\n    Run\n')


def plant_table(path, values, residency):
    with open(path, 'w') as fh:
        fh.write('\n')
        for t, v in values.items():
            tag = 'runtime' if t in ('Run', 'Within') else 'compile_time'
            fh.write(f'local\t{t}\tnormal\t{tag}/bytes allocated\t{v}\n')
        fh.write(f'local\tDown\tnormal\tcompile_time/max_bytes_used\t{residency}\n')
        fh.write('local\tRun\tnormal\truntime/max_bytes_used\t500\n')
        fh.write('other\tRun\tnormal\truntime/max_bytes_used\t999\n')


def self_test():
    bad = []

    def check(what, have, want):
        if have != want:
            bad.append(f'{what}: {have!r}, not {want!r}')
    check('bounds', bounds(1000, 2), (980, 1020))
    n = named(MESSAGE)
    check('named', n, {('Named', 'Increase'), ('Another', 'Increase'),
                       ('Down', 'Decrease'), ('Inline', 'Increase'),
                       ('Run', 'Decrease')})
    with tempfile.TemporaryDirectory(prefix='perfcmp-') as d:
        out = f'{d}/battery'
        tree = f'{d}/ghc-t'
        os.makedirs(out)
        os.makedirs(f'{tree}/testsuite/tests/perf')
        with open(f'{tree}/testsuite/tests/perf/all.T', 'w') as fh:
            fh.write(ALL_T)
        plant_table(f'{out}/perf-a.tsv', TSV_A, 1000)
        plant_table(f'{out}/perf-b.tsv', TSV_B, 1100)
        tols = tolerances(tree)
        check('tolerances', tols, {
            ('Up', 'compile_time/bytes allocated'): 2.0,
            ('Down', 'compile_time/bytes allocated'): 1.0,
            ('Down', 'compile_time/max_bytes_used'): 15.0,
            ('Down', 'compile_time/peak_megabytes_allocated'): 15.0,
            ('Run', 'runtime/bytes allocated'): 5.0,
            ('Run', 'runtime/max_bytes_used'): 5.0,
            ('Within', 'runtime/bytes allocated'): 5.0,
            ('Named', 'compile_time/bytes allocated'): 2.0})
        a, b = table(f'{out}/perf-a.tsv'), table(f'{out}/perf-b.tsv')
        check('other rows', a[('Run', 'normal', 'runtime/max_bytes_used')], 500.0)
        lines = compare(a, b)
        check('rows', lines[0], '8 and 8 rows, 8 in both; only in A: []; only in B: []')
        g = math.exp(sum(math.log(b[k] / a[k]) for k in a
                         if k[2] == 'compile_time/bytes allocated') / 4)
        check('geomean', lines[1], 'compile_time/bytes allocated: 4 tests, geomean '
              f'{100 * (g - 1):+.3f}%')
        check('falls', lines[2].split(', ')[0], '  falls: Down(normal) -2.000%')
        check('rises', lines[3].split(', ')[0], '  rises: Free(normal) +100.000%')
        lines = outside(a, b, tols, n)
        check('windows', lines, [
            'windows: 7 of 8 rows have a tolerance',
            'Metric Increase, outside the window: 3',
            '  Named(normal) compile_time/bytes allocated tol 2%: 1000 -> 1100'
            ' +10.00%  named',
            '  Run(normal) runtime/bytes allocated tol 5%: 1000 -> 1060 +6.00%'
            '  NOT named',
            '  Up(normal) compile_time/bytes allocated tol 2%: 100000 -> 102001'
            ' +2.00%  NOT named',
            'Metric Decrease, outside the window: 1',
            '  Down(normal) compile_time/bytes allocated tol 1%: 100000 -> 98000'
            ' -2.00%  named'])
        check('no range', outside(a, b, tols, None)[2].endswith('+10.00%'), True)
        for args, want in ((['a', 'missing'], 2), (['a'], 2), (['a', 'b', 'nosuch'], 2),
                           (['a', 'b'], 0), (['a', 'b', 't'], 0)):
            with open(os.devnull, 'w') as null:
                so, se = sys.stdout, sys.stderr
                sys.stdout, sys.stderr = null, null
                try:
                    rc = main(['--work', d] + args)
                finally:
                    sys.stdout, sys.stderr = so, se
            check(f'exit of {args}', rc, want)
    for x in bad:
        print('FAIL', x)
    print('ok   perfcmp.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
