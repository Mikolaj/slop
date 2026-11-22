#!/usr/bin/env python3
"""The cells of orthotope's A2T that battery.py's parts a2t-full and
a2t-groups count (its setting 17), taken from an A2T binary's tables,
and their count.

Usage: python3 tools/NCG-battery/a2tcells.py cells [--groups] FORCED SUMMED
       python3 tools/NCG-battery/a2tcells.py count [--groups] [--per-call PC]
           [--meminfo FILE] CPUS BIN FORCED SUMMED OUT
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

count counts each cell by tools/perf-per-call.py (--per-call PC) at N and 2N
calls, --reps 1 --alloc, N by count3.py's rule from the table of the cell's
mode: N calls take about 20 ms, a call taken at 100 ns at least, N at least 10
and at most 300000; a summed cell runs through a script passing --summed, as
census.py's count. The cells are dealt to lanes, one a CPU of CPUS (a comma
list), every run of a lane pinned to its CPU (perf-per-call.py's --cpu), and
before each cell a lane waits while MemAvailable (--meminfo, /proc/meminfo by
default) is under 8 GiB, as count3.py did. Each count is appended to OUT.part
as it ends, and a cell OUT.part has figures for is not counted again, so a
count stopped resumes; OUT is then written in the cells' order, battery.py's
a2t-LABEL.tsv form, a line a cell: its name, its instructions a call (-
where none were counted), perf-per-call.py's exit and its bytes allocated a
call (- where none or negative), and OUT.part removed where every cell was
counted. Address-space randomisation is the caller's (battery.py runs count
under setarch -R). count exits 0 when every cell was counted and 2 when one was
not or an input is missing or unreadable.
"""

import collections
import contextlib
import io
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import census  # noqa: E402

PER_CALL = census.PER_CALL
MEMINFO = '/proc/meminfo'
MEM_FLOOR_KB = 8 * 1024 * 1024
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


def parse(text):
    """(instructions, bytes) a call of build A in perf-per-call.py's output,
    None where absent, as battery.py's part a2t reads them."""
    n = re.search(r'^A instructions ([0-9.]+) ', text, re.M)
    a = re.search(r'^A .*  alloc ([0-9.]+) ', text, re.M)
    return n and n.group(1), a and a.group(1)


def count(cpus, binary, forced, summed, out, groups=False, pc=PER_CALL, meminfo=MEMINFO,
          poll=30):
    tabs, want, _ = wanted(forced, summed, groups)
    sized = {mc: calls(tabs[mc[0]], mc[1]) for mc in want}
    part = out + '.part'
    done = {}
    if os.path.exists(part):
        for line in census.lines_of(part):
            f = line.split('\t')
            if len(f) == 4:
                done[f[0]] = line
    names = {mc: name(*mc) for mc in want}
    todo = [mc for mc in want if done.get(names[mc], '\t-').split('\t')[1] == '-']
    lock = threading.Lock()
    with tempfile.TemporaryDirectory(prefix='a2tcells-') as td, open(part, 'a') as fo:
        run = census.wrappers(td, [binary])

        def work(mc, cpu):
            while mem_available_kb(meminfo) < MEM_FLOOR_KB:
                time.sleep(poll)
            mode, cell = mc
            r = subprocess.run([sys.executable, pc, '--cpu', cpu, '--reps', '1', '--alloc',
                                run[mode][0], cell, str(sized[mc])],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL)
            n, a = parse(r.stdout)
            line = f'{names[mc]}\t{n or "-"}\t{r.returncode}\t{a or "-"}'
            with lock:
                fo.write(line + '\n')
                fo.flush()
                done[names[mc]] = line
            if r.returncode or not n:
                text = (r.stdout + r.stderr).replace('\n', ' ')[-300:]
                print(f'{names[mc]}: exit {r.returncode}: {text}', file=sys.stderr)
            return r.returncode == 0 and n is not None
        ok = census.lanes(todo, cpus, work)
    with open(out, 'w') as fh:
        fh.write(''.join(done[names[mc]] + '\n' for mc in want))
    if ok:
        os.unlink(part)
    print(f'{len(want)} cells, {len(todo)} counted now into {out}'
          + ('' if ok else f', some without figures: {part} kept'))
    return 0 if ok else 2


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    cmd, a = (argv[0], argv[1:]) if argv else (None, [])
    groups, pc, meminfo = False, PER_CALL, MEMINFO
    while a[:1] and a[0] in ('--groups', '--per-call', '--meminfo'):
        if a[0] == '--groups':
            groups, a = True, a[1:]
        elif len(a) > 1:
            pc, meminfo = (a[1], meminfo) if a[0] == '--per-call' else (pc, a[1])
            a = a[2:]
        else:
            break
    try:
        if cmd == 'cells' and len(a) == 2:
            _, want, ngroups = wanted(*a, groups)
            sys.stdout.write(''.join(name(*mc) + '\n' for mc in want))
            print(f'{len(want)} cells, {ngroups} groups', file=sys.stderr)
            return 0
        if cmd == 'count' and len(a) == 5:
            return count(a[0].split(','), *a[1:], groups=groups, pc=pc, meminfo=meminfo)
    except census.Unreadable as e:
        print(e, file=sys.stderr)
        return 2
    print(__doc__.split('\n\n')[1], file=sys.stderr)
    return 2


# --- self-test: planted tables, the cells and groups read from them, and
# a count by a fake perf-per-call.py.

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
# the fake: its arguments logged, A's figures from the cell's name, failing
# a cell named in FAKEFAIL
FAKE_PC = '''import os, sys
a = sys.argv[1:]
open(os.environ['FAKELOG'], 'a').write(' '.join(a) + '\\n')
if a[-2] == os.environ.get('FAKEFAIL'):
    sys.exit(2)
print(a[-2] + ', per call:')
print('A instructions %d.0 [1..2]  cycles 3.0 [3.0..3.0]  alloc 8.0 [8.0..8.0]  ' % len(a[-2])
      + a[-3])
'''


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='a2tcells-') as d, \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for f, t in (('forced', FORCED), ('summed', SUMMED_T), ('pc.py', FAKE_PC),
                     ('meminfo', 'MemAvailable:   9000000 kB\n'), ('bin', '')):
            with open(f'{d}/{f}', 'w') as fh:
                fh.write(t)
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
        # count: every cell counted on its lane's CPU, a summed one through
        # the wrapper, OUT in the cells' order and OUT.part gone.
        out, log = f'{d}/out.tsv', f'{d}/log'
        os.environ['FAKELOG'] = log
        try:
            argv = ['3,5', f'{d}/bin', f'{d}/forced', f'{d}/summed', out]
            r = main(['count', '--per-call', f'{d}/pc.py', '--meminfo', f'{d}/meminfo', *argv])
            rows = open(out).read().split('\n')[:-1] if os.path.isfile(out) else []
            ran = open(log).read().split('\n')[:-1]
            if r or [x.split('\t')[0] for x in rows] != [name(*mc) for mc in want] \
                    or rows[0] != f'Dynamic/fold/small/dense/boxed\t{30}.0\t0\t8.0' \
                    or os.path.exists(out + '.part'):
                bad.append(f'count exited {r}, wrote {rows}')
            cpus = sorted({x.split()[1] for x in ran})
            if cpus != ['3', '5'] or len(ran) != len(want) or not all(
                    x.startswith('--cpu ') and ' --reps 1 --alloc ' in x for x in ran):
                bad.append(f'perf-per-call ran {ran}')
            summed = [x for x in ran if 'A-summed' in x]
            if len(summed) != 1 or not summed[0].endswith(
                    ' Dynamic/fold/small/dense/boxed 200000'):
                bad.append(f'the summed cell ran {summed}')
            # A failed cell fails the count and keeps OUT.part; counting again
            # counts that cell alone.
            os.unlink(out)
            os.environ['FAKEFAIL'] = 'Dynamic/fold/large/dense/Unboxed'
            open(log, 'w').close()
            r = main(['count', '--groups', '--per-call', f'{d}/pc.py', '--meminfo',
                      f'{d}/meminfo', *argv])
            rows = open(out).read().split('\n')[:-1] if os.path.isfile(out) else []
            if r != 2 or len(rows) != 9 or 'Dynamic/fold/large/dense/Unboxed\t-\t2\t-' not in rows \
                    or not os.path.isfile(out + '.part'):
                bad.append(f'a failed cell: exit {r}, rows {rows}')
            del os.environ['FAKEFAIL']
            open(log, 'w').close()
            r = main(['count', '--groups', '--per-call', f'{d}/pc.py', '--meminfo',
                      f'{d}/meminfo', *argv])
            ran = open(log).read().split('\n')[:-1]
            if r or len(ran) != 1 or 'Dynamic/fold/large/dense/Unboxed' not in ran[0] \
                    or os.path.exists(out + '.part'):
                bad.append(f'resumed: exit {r}, ran {ran}')
        finally:
            os.environ.pop('FAKEFAIL', None)
        # The memory floor: a lane waits while MemAvailable is under it.
        with open(f'{d}/meminfo', 'w') as fh:
            fh.write('MemAvailable:   100 kB\n')

        def free():
            time.sleep(0.3)
            early.append(open(log).read())
            with open(f'{d}/meminfo', 'w') as fh:
                fh.write('MemAvailable:   9000000 kB\n')
        os.unlink(out)
        open(log, 'w').close()
        early = []
        th = threading.Thread(target=free)
        th.start()
        r = count(['3'], f'{d}/bin', f'{d}/forced', f'{d}/summed', out, pc=f'{d}/pc.py',
                  meminfo=f'{d}/meminfo', poll=0.05)
        th.join()
        if r or early != ['']:
            bad.append(f'counted under the memory floor: exit {r}, {early}')
    for x in bad:
        print('FAIL', x)
    print('ok   a2tcells.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
