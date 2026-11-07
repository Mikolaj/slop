#!/usr/bin/env python3
"""Instructions and estimated cycles per call of one criterion benchmark,
or of each cell of a list in several builds, from cachegrind: exact, and
for where `perf stat` cannot run.

Usage: python3 tools/cachegrind-per-call.py [--cpu CPU] [--arg ARG ...]
           BENCH_BINARY NAME N [--no-cache-sim]
       python3 tools/cachegrind-per-call.py [--cpu CPU] [--arg ARG ...]
           --cells FILE BIN [BIN ...] [--no-cache-sim]
       python3 tools/cachegrind-per-call.py [--cpu CPU] [--arg ARG ...]
           [--timeout S] [--top K] --callgrind PREFIX
           LABEL_A=BIN_A LABEL_B=BIN_B NAME N
       python3 tools/cachegrind-per-call.py --self-test

Runs the benchmark binary twice under `valgrind --tool=cachegrind`, with
`--iters 2N` and with `--iters N`, selecting NAME exactly (`-m glob NAME`),
and prints the difference over N: the instructions per call and, with the
cache simulation on (the default), the estimated cycles per call,

    Ir + 10 * (I1mr + D1mr + D1mw) + 100 * (ILmr + DLmr + DLmw)

the usual estimate from L1 and last-level misses. The difference of the two
runs cancels the process's setup, which for `shortProdForCI` alone is some
40 G instructions; cachegrind is deterministic up to the program's own
nondeterminism, so N need not be large --- the measured program runs about
50 times slower under it, the simulation slower still, so size N for well
under a second of native work. Both runs are under GHCRTS=-V0
(docs/perf-checklist.md, M). Two builds are compared by running this on
each; for a banned-or-not decision about a slowdown, this is the instrument
to back an interleaved wall-time A/B with (docs/perf-checklist.md).
Each `--arg` is passed to the benchmark before its `--iters`; with `--cpu`,
every run is pinned to CPU by `taskset -c`.

With `--cells`, every BIN, in the order given, is run so at each cell of
FILE in turn, a cell being a line `MODE NAME N`: MODE `forced` runs the
benchmark as it is and `summed` with `--summed` too, the switch of
orthotope's specialisation benchmark to its summing function; anything
from a `#` to the line's end is skipped, and blank lines. A line is
printed as each cell is counted, tab-separated: BIN, MODE, NAME, N, the
instructions per call, exact to two decimals, and, with the simulation,
the estimated cycles, or `-` where the runs failed. Give a cell N enough
to keep a collection from moving its count, a cell of large arrays 100
or more.

With `--callgrind`, the two runs of each binary are callgrind's instead,
`--dump-instr=yes --compress-pos=no` under `setarch -R`, the form
tools/cg-read.py reads, each run killed after S seconds where `--timeout`
is given, and kept: the output as PREFIX-LABEL-ITERS.cg and valgrind's
stderr beside it as .err. A run whose .cg is not empty and whose .err
holds callgrind's `Collected` line is taken as it is and not run again,
so a pair stopped halfway resumes. A line is printed for each binary,
LABEL and its instructions per call, tab-separated, and then
`cg-read.py incr` over the two (`--top K` passed to it), whose status is
the exit's.

The cachegrind output is written under the system temporary directory and
removed. Exit 0 when the figures were printed, 2 when they could not be:
valgrind missing, or taskset with `--cpu`, a run failing, or its output
without the counts; with `--cells`, a cells file that cannot be read, or
any cell's runs failing, the other cells' lines printed.
"""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

# Beside this file, which a path import (a defect case's unit) leaves off
# sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import measured_env  # noqa: E402

WEIGHTS = {'Ir': 1, 'I1mr': 10, 'D1mr': 10, 'D1mw': 10,
           'ILmr': 100, 'DLmr': 100, 'DLmw': 100}

# The self-test runs a fake in its place.
VALGRIND = ['valgrind']
CG_READ = [sys.executable,
           os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'cg-read.py')]

# A cell's mode -> the benchmark arguments it adds.
MODES = {'forced': [], 'summed': ['--summed']}


def counts(path):
    """Event name -> total, from a cachegrind output file."""
    events = summary = None
    with open(path) as fh:
        for line in fh:
            if line.startswith('events:'):
                events = line.split()[1:]
            elif line.startswith('summary:'):
                summary = [int(x) for x in line.split()[1:]]
    if events is None or summary is None or len(events) != len(summary):
        raise ValueError(f'{path} has no events and summary lines to match')
    return dict(zip(events, summary))


def cycles(c):
    """Estimated cycles, or None without the cache simulation's events."""
    if not all(k in c for k in WEIGHTS):
        return None
    return sum(w * c[k] for k, w in WEIGHTS.items())


def per_call(c1, c2, n):
    """(instructions, estimated cycles or None) per call from the N and 2N
    runs."""
    y1, y2 = cycles(c1), cycles(c2)
    return ((c2['Ir'] - c1['Ir']) / n,
            None if y1 is None or y2 is None else (y2 - y1) / n)


def command(binary, name, iters, sim, out, cpu=None, args=()):
    """One counted run, pinned to cpu unless it is None, args before the
    benchmark's own."""
    return ((['taskset', '-c', cpu] if cpu is not None else []) + VALGRIND
            + ['--tool=cachegrind', f'--cache-sim={"yes" if sim else "no"}',
               f'--cachegrind-out-file={out}', binary] + list(args)
            + ['--iters', str(iters), '-m', 'glob', name])


def callgrind_command(binary, name, iters, out, cpu=None, args=()):
    """One callgrind run as tools/cg-read.py reads it."""
    return ((['taskset', '-c', cpu] if cpu is not None else [])
            + ['setarch', '-R'] + VALGRIND
            + ['--tool=callgrind', '--dump-instr=yes', '--compress-pos=no',
               f'--callgrind-out-file={out}', binary] + list(args)
            + ['--iters', str(iters), '-m', 'glob', name])


def finished(out, err):
    """Whether a kept callgrind run ran to its end."""
    try:
        with open(err) as fh:
            return os.path.getsize(out) > 0 and 'Collected' in fh.read()
    except OSError:
        return False


def callgrind_pair(prefix, labelled, name, n, cpu, args, top, timeout):
    """--callgrind: each LABEL=BIN's runs at N and 2N, kept or reused, its
    instructions per call, then cg-read.py incr over the two."""
    pairs = []
    for lb in labelled:
        label, _, binary = lb.partition('=')
        if not label or not binary:
            print(f'{lb} is not LABEL=BIN', file=sys.stderr)
            return 2
        files = []
        for k in (n, 2 * n):
            out, err = f'{prefix}-{label}-{k}.cg', f'{prefix}-{label}-{k}.err'
            if not finished(out, err):
                cmd = callgrind_command(binary, name, k, out, cpu, args)
                with open(err, 'w') as fh:
                    try:
                        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                            stderr=fh, env=measured_env(),
                                            timeout=timeout).returncode
                    except subprocess.TimeoutExpired:
                        rc = f'killed after {timeout} s'
                if rc != 0:
                    print(f'{" ".join(cmd)}: {rc}, see {err}', file=sys.stderr)
                    return 2
            files.append(out)
        try:
            c1, c2 = counts(files[0]), counts(files[1])
        except (ValueError, OSError) as e:
            print(e, file=sys.stderr)
            return 2
        print(f'{label}\t{(c2["Ir"] - c1["Ir"]) / n:.2f}', flush=True)
        pairs += [binary] + files
    return subprocess.run(CG_READ + ['incr'] + (['--top', top] if top else [])
                          + pairs + [str(n)]).returncode


def run(binary, name, iters, sim, out, cpu=None, args=()):
    cmd = command(binary, name, iters, sim, out, cpu, args)
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       text=True, env=measured_env())
    if r.returncode != 0:
        raise ValueError(f'{" ".join(cmd)} exited {r.returncode}:\n'
                         + r.stderr[-2000:])
    return counts(out)


FAKE = '''#!/usr/bin/env python3
import os, sys
if os.environ.get('GHCRTS', '').split()[-1:] != ['-V0']:
    sys.exit(3)
a = sys.argv
out = [x for x in a if x.startswith('--cachegrind-out-file=')][0]
iters = int(a[a.index('--iters') + 1])
if a[a.index(out) + 1].endswith('F'):
    sys.exit(1)
# Summed, 7.5 instructions a call, which an integer division truncates.
per = (15 * iters) // 2 if '--summed' in a else 7 * iters
with open(out.split('=', 1)[1], 'w') as fh:
    fh.write('events: Ir' + chr(10) + 'summary: ' + str(1000 + per)
             + chr(10))
'''


def self_test():
    """The file parsing and the arithmetic, on two synthetic outputs, and
    two runs of a fake valgrind whose counts are a setup plus a fixed cost
    per call."""
    global VALGRIND, CG_READ
    bad = []
    with tempfile.TemporaryDirectory() as td:
        def write(name, ir, i1, d1r, d1w, il, dlr, dlw):
            p = os.path.join(td, name)
            with open(p, 'w') as fh:
                fh.write('desc: I1 cache: 32768 B, 64 B, 8-way associative\n'
                         'cmd: ./bench --iters 10\n'
                         'events: Ir I1mr ILmr Dr D1mr DLmr Dw D1mw DLmw\n'
                         'fl=x.c\nfn=main\n1 1 0 0 0 0 0 0 0 0\n'
                         f'summary: {ir} {i1} {il} 7 {d1r} {dlr} 9 {d1w} {dlw}\n')
            return p
        c1 = counts(write('n', 1000, 10, 20, 30, 1, 2, 3))
        c2 = counts(write('2n', 3000, 30, 60, 90, 3, 6, 9))
        if cycles(c1) != 1000 + 10 * 60 + 100 * 6:
            bad.append(f'cycles of the N run: {cycles(c1)}')
        got = per_call(c1, c2, 10)
        if got != (200.0, (3000 + 10 * 180 + 100 * 18 - 2200) / 10):
            bad.append(f'per call: {got}')
        nosim = os.path.join(td, 'nosim')
        with open(nosim, 'w') as fh:
            fh.write('events: Ir\nsummary: 500\n')
        if per_call(counts(nosim), {'Ir': 900}, 4) != (100.0, None):
            bad.append('without the cache simulation, cycles were not None')
        broken = os.path.join(td, 'broken')
        with open(broken, 'w') as fh:
            fh.write('events: Ir I1mr\nsummary: 5\n')
        try:
            counts(broken)
            bad.append('a summary shorter than its events was accepted')
        except ValueError:
            pass
        fake = os.path.join(td, 'valgrind')
        with open(fake, 'w') as fh:
            fh.write(FAKE)
        os.chmod(fake, 0o755)
        saved, VALGRIND = VALGRIND, [fake]
        try:
            got = per_call(run('x', 'g/x', 10, False, os.path.join(td, 'a')),
                           run('x', 'g/x', 20, False, os.path.join(td, 'b')),
                           10)
            if got != (7.0, None):
                bad.append(f'per call from two runs: {got}')
        except ValueError as e:
            bad.append(f'a run failed: {e}')
        cells = os.path.join(td, 'cells')
        with open(cells, 'w') as fh:
            fh.write('# mode cell N\nforced g/x 10\n\nsummed g/y 10\n')
        try:
            got = read_cells(cells)
            if got != [('forced', 'g/x', 10), ('summed', 'g/y', 10)]:
                bad.append(f'cells read: {got}')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(['--cells', cells, 'A', 'B', '--no-cache-sim'])
            if rc != 0 or out.getvalue() != ('A\tforced\tg/x\t10\t7.00\n'
                                             'A\tsummed\tg/y\t10\t7.50\n'
                                             'B\tforced\tg/x\t10\t7.00\n'
                                             'B\tsummed\tg/y\t10\t7.50\n'):
                bad.append(f'cells counted: {rc} {out.getvalue()!r}')
            out = io.StringIO()
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(io.StringIO()):
                rc = main(['--cells', cells, 'F', 'A', '--no-cache-sim'])
            if rc != 2 or out.getvalue().split('\n')[:3] != [
                    'F\tforced\tg/x\t10\t-', 'F\tsummed\tg/y\t10\t-',
                    'A\tforced\tg/x\t10\t7.00']:
                bad.append(f"a failing binary's cells: {rc}"
                           f' {out.getvalue()!r}')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(['--arg', '--summed', 'A', 'g/x', '10'])
            if rc != 0 or 'instructions/call 8' not in out.getvalue():
                bad.append(f'--arg not passed: {rc} {out.getvalue()!r}')
        finally:
            VALGRIND = saved
        if command('b', 'g/x', 5, False, 'o', '3', ['--summed'])[:3] != [
                'taskset', '-c', '3']:
            bad.append('--cpu did not pin the run')
        if command('b', 'g/x', 5, False, 'o', None, ['--summed'])[-7:] != [
                'b', '--summed', '--iters', '5', '-m', 'glob', 'g/x']:
            bad.append('benchmark arguments not between it and --iters')
        for text, what in (('forced g/x\n', 'a cell without N'),
                           ('mean g/x 10\n', 'an unknown mode'),
                           ('forced g/x ten\n', 'N not a number'),
                           ('forced g/x 0\n', 'N of 0'), ('', 'no cell')):
            with open(cells, 'w') as fh:
                fh.write(text)
            with contextlib.redirect_stderr(io.StringIO()):
                if main(['--cells', cells, 'A']) != 2:
                    bad.append(f'{what} did not exit 2')
        # --callgrind: a fake valgrind logging its runs, 7 instructions a
        # call, failing for a binary named F, and a fake cg-read.py.
        if callgrind_command('b', 'g/x', 5, 'o.cg', '3', ['--summed']) != [
                'taskset', '-c', '3', 'setarch', '-R'] + VALGRIND + [
                '--tool=callgrind', '--dump-instr=yes', '--compress-pos=no',
                '--callgrind-out-file=o.cg', 'b', '--summed', '--iters', '5',
                '-m', 'glob', 'g/x']:
            bad.append('--callgrind command')
        log, got = os.path.join(td, 'runs.log'), os.path.join(td, 'read')
        fakecg, reader = os.path.join(td, 'fakecg'), os.path.join(td, 'rd')
        with open(fakecg, 'w') as fh:
            fh.write('#!/usr/bin/env python3\nimport sys\na = sys.argv\n'
                     f'open({log!r}, "a").write(" ".join(a[1:]) + chr(10))\n'
                     'out = [x for x in a if x.startswith("--callgrind-out'
                     '-file=")][0].split("=", 1)[1]\n'
                     'if a[a.index("--compress-pos=no") + 2] == "F":\n'
                     '    sys.exit(1)\n'
                     'n = 1000 + 7 * int(a[a.index("--iters") + 1])\n'
                     'open(out, "w").write(f"events: Ir\\nsummary: {n}\\n")\n'
                     'print(f"==1== Collected : {n}", file=sys.stderr)\n')
        with open(reader, 'w') as fh:
            fh.write(f'import sys\nopen({got!r}, "w").write(" ".join('
                     'sys.argv[1:]))\n')
        os.chmod(fakecg, 0o755)
        saved, VALGRIND, CG_READ = (VALGRIND, CG_READ), [fakecg], [
            sys.executable, reader]
        pre = os.path.join(td, 'p')
        argv = ['--callgrind', pre, '--top', '8', 'a=binA', 'b=binB', 'g/x',
                '10']
        try:
            o = io.StringIO()
            with contextlib.redirect_stdout(o):
                rc = main(argv)
            if rc != 0 or o.getvalue() != 'a\t7.00\nb\t7.00\n':
                bad.append(f'--callgrind printed {o.getvalue()!r}, exit {rc}')
            want = (f'incr --top 8 binA {pre}-a-10.cg {pre}-a-20.cg binB'
                    f' {pre}-b-10.cg {pre}-b-20.cg 10')
            if open(got).read() != want:
                bad.append(f'cg-read given {open(got).read()!r}')
            with open(f'{pre}-b-20.err', 'w') as fh:
                fh.write('killed\n')
            with contextlib.redirect_stdout(io.StringIO()):
                main(argv)
            runs = open(log).read().splitlines()
            if len(runs) != 5 or '--iters 20' not in runs[-1]:
                bad.append(f'finished runs not reused, the unfinished one not'
                           f' rerun: {runs}')
            with contextlib.redirect_stderr(io.StringIO()), \
                    contextlib.redirect_stdout(io.StringIO()):
                rc = main(['--callgrind', pre, 'a=F', 'b=binB', 'g/x', '3'])
            if rc != 2:
                bad.append(f'a failing callgrind run exited {rc}')
        finally:
            VALGRIND, CG_READ = saved
        with mock.patch.dict(os.environ, GHCRTS='-V1'):
            if measured_env()['GHCRTS'] != '-V1 -V0':
                bad.append("-V0 not after the caller's GHCRTS")
    for b in bad:
        print('FAIL', b)
    print('self-test', 'FAILED' if bad else 'passed')
    return 1 if bad else 0


def read_cells(path):
    """[(mode, name, N)] of a cells file, or ValueError."""
    out = []
    with open(path) as fh:
        for k, line in enumerate(fh, 1):
            f = line.split('#', 1)[0].split()
            if not f:
                continue
            if (len(f) != 3 or f[0] not in MODES or not f[2].isdigit()
                    or int(f[2]) < 1):
                raise ValueError(f'{path}:{k}: not `MODE NAME N`, MODE one of'
                                 f' {", ".join(MODES)}: {line.strip()!r}')
            out.append((f[0], f[1], int(f[2])))
    if not out:
        raise ValueError(f'{path} lists no cell')
    return out


def count_cells(bins, cells, sim, cpu, args):
    """Print a line for every BIN and cell; 2 when any cell's runs failed."""
    failed = False
    with tempfile.TemporaryDirectory() as td:
        o1, o2 = os.path.join(td, 'n.out'), os.path.join(td, '2n.out')
        for b in bins:
            for mode, name, n in cells:
                a = list(args) + MODES[mode]
                try:
                    c1 = run(b, name, n, sim, o1, cpu, a)
                    c2 = run(b, name, 2 * n, sim, o2, cpu, a)
                except (ValueError, OSError) as e:
                    print(e, file=sys.stderr)
                    print(f'{b}\t{mode}\t{name}\t{n}\t-', flush=True)
                    failed = True
                    continue
                ins, cyc = per_call(c1, c2, n)
                print(f'{b}\t{mode}\t{name}\t{n}\t{ins:.2f}'
                      + (f'\t{cyc:.2f}' if cyc is not None else ''),
                      flush=True)
    return 2 if failed else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    sim = '--no-cache-sim' not in argv
    argv = [a for a in argv if a != '--no-cache-sim']
    cpu, cells, args, prefix, top, timeout = None, None, [], None, None, None
    while argv[:1] in (['--cpu'], ['--cells'], ['--arg'], ['--callgrind'],
                       ['--top'], ['--timeout']):
        if len(argv) < 2:
            print(f'{argv[0]} needs a value', file=sys.stderr)
            return 2
        if argv[0] == '--cpu':
            cpu = argv[1]
        elif argv[0] == '--cells':
            cells = argv[1]
        elif argv[0] == '--callgrind':
            prefix = argv[1]
        elif argv[0] == '--top':
            top = argv[1]
        elif argv[0] == '--timeout':
            timeout = float(argv[1])
        else:
            args.append(argv[1])
        argv = argv[2:]
    single = len(argv) == 3 and argv[2].isdigit() and int(argv[2]) >= 1
    pair = len(argv) == 4 and argv[3].isdigit() and int(argv[3]) >= 1
    if ((prefix is not None and (not pair or cells is not None))
            or (prefix is None and cells is None and not single)
            or (cells is not None and not argv)):
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    for t in ([VALGRIND[0]] + (['taskset'] if cpu is not None else [])
              + (['setarch'] if prefix is not None else [])):
        if shutil.which(t) is None:
            print(f'{t} is not on PATH; nothing measured', file=sys.stderr)
            return 2
    if prefix is not None:
        return callgrind_pair(prefix, argv[:2], argv[2], int(argv[3]), cpu,
                              args, top, timeout)
    if cells is not None:
        try:
            got = read_cells(cells)
        except (ValueError, OSError) as e:
            print(e, file=sys.stderr)
            return 2
        return count_cells(argv, got, sim, cpu, args)
    binary, name, n = argv[0], argv[1], int(argv[2])
    with tempfile.TemporaryDirectory() as td:
        try:
            c1 = run(binary, name, n, sim, os.path.join(td, 'n.out'), cpu,
                     args)
            c2 = run(binary, name, 2 * n, sim, os.path.join(td, '2n.out'), cpu,
                     args)
        except (ValueError, OSError) as e:
            print(e, file=sys.stderr)
            return 2
    ins, cyc = per_call(c1, c2, n)
    print(f'{name}: instructions/call {ins:.0f}'
          + (f'  estimated cycles/call {cyc:.0f}' if cyc is not None else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
