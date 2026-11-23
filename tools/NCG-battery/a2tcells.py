#!/usr/bin/env python3
"""The cells of orthotope's A2T that battery.py's parts a2t-full and
a2t-groups count (its setting 17), taken from an A2T binary's tables,
and their count.

Usage: python3 tools/NCG-battery/a2tcells.py cells [--groups] FORCED SUMMED
       python3 tools/NCG-battery/a2tcells.py count [--groups] [--meminfo FILE]
           CPUS BIN FORCED SUMMED OUT
       python3 tools/NCG-battery/a2tcells.py --self-test

FORCED and SUMMED are the tables an A2T binary prints, `GHCRTS=-V0 BIN`
and `GHCRTS=-V0 BIN --summed`, battery.py giving every label the pinned
pins/a2t-tables, so that each counts a cell at one N; a line a row
`Family/op/size/view`
with three times and three bytes, tools/census.py's form. The cells are those
of the sweep's count3.py: every row and kind to which a table gives a time,
the forced table's then the summed one's, in the tables' order, an operation
whose name holds a slash (`/=`) read by the kind after the last slash and
the size the row's last but one component. --groups takes one cell of each
group as the sweep's steps.py sample and dist-m535's cells-sample.py did with
seed 1 (Mikolaj's ruling 17, 2026-10-26): a group is the mode, family,
operation, size and kind, the views of a row its members, and the cell is
random.Random(1)'s choice over the groups in sorted order. cells prints them,
a line a cell, a summed cell's name `summed:` and the cell, then the count
of cells and groups.

count counts the cells by the binary BIN itself, orthotope's
bench:specialisation from the branch ncg-benchmark-a2t-cells on: in its own
process, `BIN --cells full` or `groups` `--count --reps 1 --tables FORCED
SUMMED`, at N and 2N calls, N by count3.py's rule from the table of the cell's
mode: N calls take about 20 ms, a call taken at 100 ns at least, N at least 10
and at most 300000. First `BIN --cells ... --list --tables FORCED SUMMED` must
print the cells and their N as above, a line a cell, or nothing is counted. The
cells are counted in SHARDS processes, BIN's --shard I/SHARDS, a number fixed
whatever CPUS is, so that every label counts a cell after the same cells: a
large cell's figure moved by 4% with the cells counted before it in the one
process. The shards are dealt to lanes, one a CPU of CPUS (a comma list), each
process pinned to its lane's CPU (BIN's --cpu), and before each shard a lane
waits while MemAvailable (--meminfo, /proc/meminfo by default) is under 8 GiB,
as count3.py did. Shard I appends its cells' lines to OUT.partI as they end and
passes over those it has counted, so that a count stopped resumes; OUT is then
written in the cells' order, battery.py's a2t-LABEL.tsv form, a line a cell: its
name, its instructions a call (- where none were counted), BIN's status, 0 where
counted and 2 where not, and its bytes allocated a call (- where none or
negative), and OUT.partI removed where every cell was counted. Address-space
randomisation is the caller's (battery.py runs count under setarch -R). count
exits 0 when every cell was counted and 2 when one was not, BIN's list differs
or an input is missing or unreadable.
"""

import collections
import contextlib
import io
import os
import random
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import census  # noqa: E402

MEMINFO = '/proc/meminfo'
MEM_FLOOR_KB = 8 * 1024 * 1024
SHARDS = 10
SEED = 1
SUMMED = 'summed:'


def cell_parts(cell):
    """count3.py's census.cell_parts: (row, kind index), an operation's name
    holding a slash allowed."""
    row, _, kind = cell.rpartition('/')
    if kind not in census.KINDS or row.count('/') < 3:
        raise census.Unreadable(f'{cell!r} is not a cell')
    return row, census.KINDS.index(kind)


def calls(tab, cell):
    """count3.py's census.calls by cell_parts above."""
    row, k = cell_parts(cell)
    if row not in tab or tab[row][k] == '-':
        raise census.Unreadable(f'no time of {cell} in the table')
    large = row.split('/')[-2] == 'large'
    ns = float(tab[row][k]) * (census.LARGE if large else 1)
    return max(10, min(300000, int(2e7 / max(ns, 100))))


def group(mode, cell):
    """steps.py's: the mode, family, operation, size and kind."""
    p = cell.split('/')
    return (mode, p[0], '/'.join(p[1:-3]), p[-3], p[-1])


def cells(tabs):
    """[(mode, cell)] of count3.py's cells, tabs {mode: census.table}."""
    return [(mode, f'{row}/{k}') for mode in ('forced', 'summed')
            for row, f in tabs[mode].items()
            for i, k in enumerate(census.KINDS) if f[i] != '-']


def one_a_group(all_cells, seed=SEED):
    """steps.py's sample: one cell a group, in all_cells' order."""
    members = collections.defaultdict(list)
    for mc in all_cells:
        members[group(*mc)].append(mc)
    rng = random.Random(seed)
    chosen = {rng.choice(v) for k, v in sorted(members.items())}
    return [mc for mc in all_cells if mc in chosen], len(members)


def name(mode, cell):
    return (SUMMED if mode == 'summed' else '') + cell


def wanted(forced, summed, groups):
    """(tables, cells, groups' count) of the two tables."""
    tabs = {'forced': census.table(forced), 'summed': census.table(summed)}
    all_cells = cells(tabs)
    picked, ngroups = one_a_group(all_cells)
    return tabs, picked if groups else all_cells, ngroups


def mem_available_kb(meminfo):
    with open(meminfo) as fh:
        for line in fh:
            if line.startswith('MemAvailable:'):
                return int(line.split()[1])
    return 0


def count(cpus, binary, forced, summed, out, groups=False, shards=SHARDS, meminfo=MEMINFO,
          poll=30):
    tabs, want, _ = wanted(forced, summed, groups)
    sel = 'groups' if groups else 'full'
    tables = ['--tables', forced, summed]
    listed = [f'{name(*mc)}\t{calls(tabs[mc[0]], mc[1])}' for mc in want]
    r = subprocess.run([binary, '--cells', sel, '--list', *tables],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    have = r.stdout.split('\n')[:-1]
    if r.returncode or have != listed:
        first = next((f'{a!r} where {b!r}' for a, b in zip(have, listed) if a != b),
                     f'{len(have)} cells where {len(listed)}')
        print(f'{binary} --cells {sel} --list: exit {r.returncode}, {first}'
              + ''.join(f'; {x}' for x in r.stderr.split('\n')[:3] if x), file=sys.stderr)
        return 2
    parts = [f'{out}.part{i}' for i in range(shards)]

    def work(i, cpu):
        while mem_available_kb(meminfo) < MEM_FLOOR_KB:
            time.sleep(poll)
        r = subprocess.run([binary, '--cells', sel, '--count', '--reps', '1', *tables,
                            '--shard', f'{i}/{shards}', '--out', parts[i]]
                           + (['--cpu', cpu] if cpu is not None else []),
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if r.returncode:
            text = r.stderr.strip().replace('\n', '; ')[-300:]
            print(f'shard {i}/{shards}: exit {r.returncode}: {text}', file=sys.stderr)
        return r.returncode == 0
    ok = census.lanes(list(range(shards)), cpus, work)
    done = {}
    for p in parts:
        if os.path.exists(p):
            for line in census.lines_of(p):
                f = line.split('\t')
                if len(f) == 4:
                    done[f[0]] = line
    rows = [done.get(n, f'{n}\t-\t2\t-') for n in (name(*mc) for mc in want)]
    ok = ok and all(x.split('\t')[2] != '2' for x in rows)
    with open(out, 'w') as fh:
        fh.write(''.join(x + '\n' for x in rows))
    if ok:
        for p in parts:
            if os.path.exists(p):
                os.unlink(p)
    print(f'{len(want)} cells in {shards} shards into {out}'
          + ('' if ok else f', some without figures: {out}.part0 to .part{shards - 1} kept'))
    return 0 if ok else 2


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    cmd, a = (argv[0], argv[1:]) if argv else (None, [])
    groups, meminfo = False, MEMINFO
    while a[:1] and a[0] in ('--groups', '--meminfo'):
        if a[0] == '--groups':
            groups, a = True, a[1:]
        elif len(a) > 1:
            meminfo, a = a[1], a[2:]
        else:
            break
    try:
        if cmd == 'cells' and len(a) == 2:
            _, want, ngroups = wanted(*a, groups)
            sys.stdout.write(''.join(name(*mc) + '\n' for mc in want))
            print(f'{len(want)} cells, {ngroups} groups', file=sys.stderr)
            return 0
        if cmd == 'count' and len(a) == 5:
            return count(a[0].split(','), *a[1:], groups=groups, meminfo=meminfo)
    except census.Unreadable as e:
        print(e, file=sys.stderr)
        return 2
    print(__doc__.split('\n\n')[1], file=sys.stderr)
    return 2


# --- self-test: planted tables, the cells and groups read from them, and
# a count by a fake binary.

HEADER = '                          ns, then bytes\n'
FORCED = HEADER + '''\
Dynamic/fold/small/dense      10.00   20.00     -   48   48    -
Dynamic/fold/small/runs       11.00   21.00     -   48   48    -
Dynamic/fold/small/window     13.00   22.00     -   48   48    -
Dynamic/fold/large/dense       0.50    0.60  0.70    8    8    8
Dynamic//=/small/dense       320.00  120.00     -    0    0    -
Shaped/fold/small/dense       12.00      -      -   48    -    -
'''
SUMMED_T = HEADER + '''\
Dynamic/fold/small/dense      10.00      -      -   16    -    -
'''
# the fake binary: its arguments logged; --list printing the file list-SEL
# beside it, one N wrong where FAKELISTBAD; a count appending to --out
# a line for each cell of its shard that the file has no figures for, its
# instructions the length of the cell's name, the cell FAKEFAIL names
# failing, and a line `counted CELL` to the log for each
FAKE_BIN = '''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
log = open(os.environ['FAKELOG'], 'a')
log.write(' '.join(a) + '\\n')
sel = a[a.index('--cells') + 1]
listed = open(os.path.join(os.path.dirname(sys.argv[0]), 'list-' + sel)).read().split('\\n')[:-1]
if '--list' in a:
    if os.environ.get('FAKELISTBAD'):
        listed[-1] += '0'
    print('\\n'.join(listed))
    sys.exit(0)
i, k = map(int, a[a.index('--shard') + 1].split('/'))
out = a[a.index('--out') + 1]
have = open(out).read().split('\\n')[:-1] if os.path.exists(out) else []
kept = [x for x in have if x.split('\\t')[2] != '2']
done = {x.split('\\t')[0] for x in kept}
e = 0
with open(out, 'w') as fh:
    fh.write(''.join(x + '\\n' for x in kept))
    for j, x in enumerate(listed):
        c = x.split('\\t')[0]
        if j % k != i or c in done:
            continue
        log.write('counted ' + c + '\\n')
        if c == os.environ.get('FAKEFAIL'):
            fh.write(c + '\\t-\\t2\\t-\\n')
            e = 2
        else:
            fh.write('%s\\t%d.0\\t0\\t8.0\\n' % (c, len(c)))
sys.exit(e)
'''


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='a2tcells-') as d, \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for f, t in (('forced', FORCED), ('summed', SUMMED_T), ('bin', FAKE_BIN),
                     ('meminfo', 'MemAvailable:   9000000 kB\n')):
            with open(f'{d}/{f}', 'w') as fh:
                fh.write(t)
        os.chmod(f'{d}/bin', 0o755)
        try:
            tabs, full, ngroups = wanted(f'{d}/forced', f'{d}/summed', False)
        except census.Unreadable as e:
            print('FAIL', e, file=sys.__stdout__)
            return 1
        # Every cell with a time, the forced then the summed, `/=` among them.
        want = [('forced', c) for c in (
            'Dynamic/fold/small/dense/boxed', 'Dynamic/fold/small/dense/Storable',
            'Dynamic/fold/small/runs/boxed', 'Dynamic/fold/small/runs/Storable',
            'Dynamic/fold/small/window/boxed', 'Dynamic/fold/small/window/Storable',
            'Dynamic/fold/large/dense/boxed', 'Dynamic/fold/large/dense/Storable',
            'Dynamic/fold/large/dense/Unboxed', 'Dynamic//=/small/dense/boxed',
            'Dynamic//=/small/dense/Storable', 'Shaped/fold/small/dense/boxed')] \
            + [('summed', 'Dynamic/fold/small/dense/boxed')]
        if full != want or ngroups != 9:
            bad.append(f'cells {full}, groups {ngroups}')
        # N: 20 ms over a call, under 100 ns taken as 100, large an element's.
        ns = {c: calls(tabs[m], c) for m, c in want}
        if (ns['Dynamic/fold/small/dense/boxed'], ns['Dynamic//=/small/dense/boxed'],
                ns['Dynamic/fold/large/dense/boxed']) != (200000, 62500, 200):
            bad.append(f'sized {ns}')
        # One a group: the views of a row its members, seeded.
        picked, _ = one_a_group(full)
        groups = [group(*mc) for mc in picked]
        if len(picked) != 9 or len(set(groups)) != 9 or [mc for mc in picked if mc not in full] \
                or picked[:2] != [('forced', 'Dynamic/fold/small/runs/boxed'),
                                  ('forced', 'Dynamic/fold/small/runs/Storable')]:
            bad.append(f'one a group {picked}')
        if group('forced', 'Dynamic//=/small/dense/boxed') != \
                ('forced', 'Dynamic', '/=', 'small', 'boxed'):
            bad.append('a slashed operation grouped wrong')
        for sel, g in (('full', False), ('groups', True)):
            t, cs, _ = wanted(f'{d}/forced', f'{d}/summed', g)
            with open(f'{d}/list-{sel}', 'w') as fh:
                fh.write(''.join(f'{name(*mc)}\t{calls(t[mc[0]], mc[1])}\n' for mc in cs))
        out, log = f'{d}/out.tsv', f'{d}/log'
        os.environ['FAKELOG'] = log

        def parts():
            return [p for p in os.listdir(d) if p.startswith('out.tsv.part')]

        def logged():
            return open(log).read().split('\n')[:-1]
        try:
            # count: the binary's list checked, then every cell counted once
            # in ten shards over the lanes' CPUs, a summed cell by its name,
            # OUT in the cells' order and the shards' files gone.
            argv = ['3,5', f'{d}/bin', f'{d}/forced', f'{d}/summed', out]
            r = main(['count', '--meminfo', f'{d}/meminfo', *argv])
            rows = open(out).read().split('\n')[:-1] if os.path.isfile(out) else []
            if r or [x.split('\t')[0] for x in rows] != [name(*mc) for mc in want] \
                    or rows[0] != f'Dynamic/fold/small/dense/boxed\t{30}.0\t0\t8.0' or parts():
                bad.append(f'count exited {r}, wrote {rows}')
            ran = logged()
            runs = [x for x in ran if ' --count ' in x]
            cpus = sorted({x.split('--cpu ')[1] for x in runs})
            shards = sorted(int(x.split('--shard ')[1].split('/')[0]) for x in runs)
            tables = f' --tables {d}/forced {d}/summed '
            if cpus != ['3', '5'] or shards != list(range(10)) or not all(
                    x.startswith('--cells full --count --reps 1' + tables) for x in runs) \
                    or [x for x in ran if ' --list ' in x] != [f'--cells full --list{tables[:-1]}'] \
                    or sorted(x for x in ran if x.startswith('counted ')) \
                    != sorted(f'counted {name(*mc)}' for mc in want):
                bad.append(f'the binary ran {ran}')
            # A failed cell fails the count and keeps the shards' files;
            # counting again counts that cell alone.
            os.unlink(out)
            os.environ['FAKEFAIL'] = 'Dynamic/fold/large/dense/Unboxed'
            open(log, 'w').close()
            r = main(['count', '--groups', '--meminfo', f'{d}/meminfo', *argv])
            rows = open(out).read().split('\n')[:-1] if os.path.isfile(out) else []
            if r != 2 or len(rows) != 9 or 'Dynamic/fold/large/dense/Unboxed\t-\t2\t-' not in rows \
                    or not parts():
                bad.append(f'a failed cell: exit {r}, rows {rows}')
            del os.environ['FAKEFAIL']
            open(log, 'w').close()
            r = main(['count', '--groups', '--meminfo', f'{d}/meminfo', *argv])
            counted = [x for x in logged() if x.startswith('counted ')]
            if r or counted != ['counted Dynamic/fold/large/dense/Unboxed'] or parts():
                bad.append(f'resumed: exit {r}, counted {counted}')
            # A list that differs from the tables' counts nothing.
            os.environ['FAKELISTBAD'] = '1'
            os.unlink(out)
            open(log, 'w').close()
            r = main(['count', '--meminfo', f'{d}/meminfo', *argv])
            if r != 2 or [x for x in logged() if ' --count ' in x] or os.path.exists(out):
                bad.append(f'a wrong list: exit {r}, ran {logged()}')
        finally:
            os.environ.pop('FAKEFAIL', None)
            os.environ.pop('FAKELISTBAD', None)
        # The memory floor: a lane waits while MemAvailable is under it.
        with open(f'{d}/meminfo', 'w') as fh:
            fh.write('MemAvailable:   100 kB\n')

        def free():
            time.sleep(0.3)
            early.append(open(log).read())
            with open(f'{d}/meminfo', 'w') as fh:
                fh.write('MemAvailable:   9000000 kB\n')
        open(log, 'w').close()
        early = []
        th = threading.Thread(target=free)
        th.start()
        r = count(['3'], f'{d}/bin', f'{d}/forced', f'{d}/summed', out, shards=1,
                  meminfo=f'{d}/meminfo', poll=0.05)
        th.join()
        if r or len(early) != 1 or ' --count ' in early[0] or ' --list ' not in early[0]:
            bad.append(f'counted under the memory floor: exit {r}, {early}')
    for x in bad:
        print('FAIL', x)
    print('ok   a2tcells.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
