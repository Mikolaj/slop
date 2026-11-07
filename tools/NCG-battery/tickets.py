#!/usr/bin/env python3
"""battery.py's tickets part: the reproducers of GHC's tickets on the NCG's
code, compiled by one compiler at the flags their tickets use, and the
figures each names, a row a figure, so that two labels' tables compare row
by row.

Usage: python3 tools/NCG-battery/tickets.py run GHC OUT CPU
       python3 tools/NCG-battery/tickets.py compare A.tsv B.tsv
       python3 tools/NCG-battery/tickets.py --self-test

`run` writes OUT, a line a figure: the case, the figure, its value. The
reproducers are in tickets/ beside this file, copied from the saved tickets
(dist-ghcho/tmp-save-2026-10-30/tix/T/src) and from the loops measured by
hand for the MR description (finding 726: tipall/rb/more/h30 and Repro742).

1. STATIC: each case compiled to assembly (-S) once at each level it runs
   at, -O1 and -O2 where its ticket or file sets neither (Mikolaj,
   2026-10-31: "all that runs at -O2 should also run at -O1 and the other way
   around"), a .cmm at -O, with -ddump-asm-stats; the figures: insns, the
   instruction lines; jmp, the unconditional jumps; jcc, the conditional
   ones; stack, the instructions reading or writing through %rbp, GHC's
   Sp; latches, the loops' back edges by the shape of their latch, `fused`
   a conditional jump back to the body (cmpq; jl body), `split` an
   unconditional one right after a conditional jump out (cmpq; jge exit;
   jmp body), `jmp` any other unconditional one; inner, the latch of the
   shortest back edge, the innermost loop's in a reproducer of one loop
   nest, `none` where there is no loop; regalloc, the linear allocator's
   spills-added-total, (allocs, clobbers, loads, joinRR, joinRM,
   reg_reg_moves_remaining). GHC #27799's latch is split or fused by its
   -fobject-determinism, so it is compiled both ways, as GHC #27981's Lib
   is with and without -DINL.
2. LOOPS: instructions an element of the loops counted by hand, instructions:u
   by `perf stat` at two counts of calls under setarch -R and the RTS's own
   options, differenced over the elements added: orthotope's rnfArrayFrom
   (A), GHC #8905's sum (T8905), a loop entered after a call (S3) and GHC
   #27991's example (27991) through one -O0 harness, 1000, 500, 500 and 1000
   elements a call at 2000 and 4000 calls; GHC #27742's fillA and fillB, 250357
   elements a call at 20 and 40 calls; GHC #27981's nf, noinline and inline,
   100000 elements a call at 100 and 200 calls; each at -O1 and -O2.

Left out: #27619, a wrong spill format its reproducer checks in a dump, and
#27638, a panic; #19656, #27437 and #27448, the compiler's own cost, which
the GHC build's records measure; #13763, a criterion benchmark needing
primitive; #12232, #13051, #13094, #13563, #26666 and #26680, no source saved.

A case that fails to compile or run is a row `failed` with the step, and run
exits 1; 2 when it could not run at all (no compiler, no perf). `compare`
prints every row whose value differs, a loop's instructions an element only
where they move by 0.2% or more, then how many rows one table has alone, with
the first; it exits 0.
"""

import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'tickets')
O12 = ('-O1', '-O2')
# case name, directory, file compiled, levels, variants (extra flags)
STATIC = [
    ('8336', '8336', 'HashStr.hs', ('-O2',), ('',)),  # its OPTIONS_GHC -O2
    ('8905', '8905', 'W.hs', O12, ('',)),
    ('10606', '10606', 'Bool.hs', O12, ('',)),
    ('17651', '17651', 'TestIpReserved.hs', ('-O2',), ('',)),  # OPTIONS_GHC -O2
    ('17823', '17823', 'M.hs', O12, ('',)),
    ('21084', '21084', 'Sink2.hs', O12, ('',)),
    ('24813', '24813', 'T24813.cmm', ('-O',), ('',)),
    ('26433', '26433', 'Foo.hs', O12, ('',)),
    ('26631', '26631', 'simd013.hs', O12, ('',)),
    ('27742', '27742', 'Repro.hs', O12, ('',)),
    ('27799', '27799', 'Repro.hs', O12, ('-fobject-determinism', '-fno-object-determinism')),
    ('27800', '27800', 'T27800.cmm', ('-O',), ('',)),
    ('27980', '27980', 'pref.cmm', ('-O',), ('',)),
    ('27981', '27981', 'Lib.hs', O12, ('', '-DINL')),
]
# The harness's loops: name, elements a call.
HARNESS = (('A', 1000), ('T8905', 500), ('S3', 500), ('27991', 1000))
HARNESS_ARG = {'27991': 'Repro'}
HARNESS_K = (2000, 4000)
F27742 = (('a', 250357), ('b', 250357))
F27742_K = (20, 40)
F27981_N, F27981_K = 100000, (100, 200)
MOVE = 0.002
TIMEOUT = 300
PERF = ['perf']  # the self-test's fake in its place
MEM = 8_000_000 * 1024  # ulimit -v 8000000


def limit():
    resource.setrlimit(resource.RLIMIT_AS, (MEM, MEM))


def sh(argv, cwd, cpu, log):
    """argv's status, pinned to cpu and capped, its output appended to log."""
    with open(log, 'a') as fh:
        try:
            return subprocess.run(['taskset', '-c', cpu] + argv, cwd=cwd, stdout=fh,
                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  preexec_fn=limit, timeout=TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            return 'timeout'


INSN = re.compile(r'^\t([a-z][a-z0-9]*)\b\s*(.*)$')
LABEL = re.compile(r'^(\.L[^\s:]*):')


def asm_figures(text):
    """The static figures of an assembly file's text."""
    insns, labels, out = [], {}, {'insns': 0, 'jmp': 0, 'jcc': 0, 'stack': 0}
    for line in text.split('\n'):
        m = LABEL.match(line)
        if m:
            labels[m.group(1)] = len(insns)
            continue
        m = INSN.match(line)
        if not m:
            continue
        op, args = m.groups()
        insns.append((op, args.strip()))
        out['insns'] += 1
        if op == 'jmp':
            out['jmp'] += 1
        elif op.startswith('j'):
            out['jcc'] += 1
        if '(%rbp)' in args:
            out['stack'] += 1
    shapes, inner = {'fused': 0, 'split': 0, 'jmp': 0}, None
    for i, (op, args) in enumerate(insns):
        if not op.startswith('j') or labels.get(args, i + 1) > i:
            continue
        if op != 'jmp':
            shape = 'fused'
        elif i and insns[i - 1][0].startswith('j') and insns[i - 1][0] != 'jmp':
            shape = 'split'
        else:
            shape = 'jmp'
        shapes[shape] += 1
        span = i - labels[args]
        if inner is None or span < inner[0]:
            inner = (span, shape)
    out['latches'] = ' '.join(f'{k} {v}' for k, v in shapes.items())
    out['inner'] = inner[1] if inner else 'none'
    return out


def regalloc(text):
    """The spills-added-total tuple of a -ddump-asm-stats dump, or '-'."""
    m = re.search(r'reg_reg_moves_remaining\)\n\(([^)]*)\)', text)
    return m.group(1).replace(' ', '') if m else '-'


def static(ghc, cpu, td, rows):
    bad = 0
    for name, d, f, levels, variants in STATIC:
        for lev in levels:
            for var in variants:
                case = ' '.join(x for x in (name, lev, var) if x)
                w = tempfile.mkdtemp(dir=td)
                shutil.copytree(os.path.join(SRC, d), w, dirs_exist_ok=True)
                st = sh([ghc, lev] + ([var] if var else []) + ['-S', f, '-o', 'out.s',
                        '-ddump-asm-stats', '-ddump-to-file', '-ddump-file-prefix=out'],
                        w, cpu, os.path.join(w, 'log'))
                if st != 0 or not os.path.isfile(os.path.join(w, 'out.s')):
                    rows.append((case, 'failed', f'compile {st}'))
                    bad += 1
                    continue
                with open(os.path.join(w, 'out.s')) as fh:
                    figs = asm_figures(fh.read())
                stats = os.path.join(w, 'out.dump-asm-stats')
                figs['regalloc'] = regalloc(open(stats).read()) if os.path.isfile(stats) else '-'
                rows += [(case, k, v) for k, v in figs.items()]
    return bad


def count(argv, cwd, cpu, log):
    """instructions:u of one run, or None."""
    out = os.path.join(cwd, 'perf.csv')
    st = sh(['setarch', '-R'] + PERF + ['stat', '-x,', '-e', 'instructions:u', '-o', out, '--']
            + argv, cwd, cpu, log)
    if st != 0 or not os.path.isfile(out):
        return None
    with open(out) as fh:
        for line in fh:
            x = line.split(',')
            if len(x) > 2 and x[2].startswith('instructions') and x[0].isdigit():
                return int(x[0])
    return None


def per_element(case, argv_of, ks, n, cwd, cpu, rows):
    """Instructions an element of a loop run at the counts ks, as a row."""
    log = os.path.join(cwd, 'log')
    got = [count(argv_of(k), cwd, cpu, log) for k in ks]
    if None in got:
        rows.append((case, 'failed', 'run'))
        return 1
    rows.append((case, 'per-element', f'{(got[1] - got[0]) / ((ks[1] - ks[0]) * n):.3f}'))
    return 0


def loops(ghc, cpu, td, rows):
    bad = 0
    for lev in O12:
        w = tempfile.mkdtemp(dir=td)
        shutil.copytree(os.path.join(SRC, 'loops'), w, dirs_exist_ok=True)
        log = os.path.join(w, 'log')
        ok = all(sh([ghc, lev, '-c', '-outputdir', 'b', m + '.hs'], w, cpu, log) == 0
                 for m in ('Mk', 'A', 'T8905', 'S3', 'Repro'))
        ok = ok and sh([ghc, '-O0', '-c', '-outputdir', 'b', '-ib', 'Main.hs'], w, cpu, log) == 0
        ok = ok and sh([ghc, '-o', 'H'] + [f'b/{m}.o' for m in
                       ('Mk', 'A', 'T8905', 'S3', 'Repro', 'Main')], w, cpu, log) == 0
        for name, n in HARNESS:
            case = f'{name} {lev}'
            if not ok:
                rows.append((case, 'failed', 'build'))
                bad += 1
                continue
            arg = HARNESS_ARG.get(name, name)
            bad += per_element(case, lambda k: ['./H', arg, str(k)], HARNESS_K, n, w, cpu, rows)
        w = tempfile.mkdtemp(dir=td)
        shutil.copytree(os.path.join(SRC, '27742'), w, dirs_exist_ok=True)
        ok = sh([ghc, lev, 'Repro.hs', '-o', 'repro'], w, cpu, os.path.join(w, 'log')) == 0
        for mode, n in F27742:
            case = f'27742 {lev} {mode}'
            if not ok:
                rows.append((case, 'failed', 'build'))
                bad += 1
                continue
            bad += per_element(case, lambda k: ['./repro', mode, str(k)], F27742_K, n, w, cpu, rows)
        w = tempfile.mkdtemp(dir=td)
        shutil.copytree(os.path.join(SRC, '27981'), w, dirs_exist_ok=True)
        for form, flags in (('noinline', []), ('inline', ['-DINL'])):
            case = f'27981 {lev} {form}'
            if sh([ghc, lev] + flags + ['-outputdir', form, '-o', f'Main-{form}', 'Main.hs'],
                  w, cpu, os.path.join(w, 'log')) != 0:
                rows.append((case, 'failed', 'build'))
                bad += 1
                continue
            bad += per_element(case, lambda k: [f'./Main-{form}', str(F27981_N), str(k)],
                               F27981_K, F27981_N, w, cpu, rows)
    return bad


def run(ghc, out, cpu):
    for tool in (PERF[0], 'taskset', 'setarch'):
        if shutil.which(tool) is None:
            print(f'{tool} is not on PATH; nothing measured', file=sys.stderr)
            return 2
    if not os.access(ghc, os.X_OK):
        print(f'no compiler {ghc}; nothing measured', file=sys.stderr)
        return 2
    rows = []
    with tempfile.TemporaryDirectory(prefix='ncg-tickets-') as td:
        bad = static(ghc, cpu, td, rows) + loops(ghc, cpu, td, rows)
    with open(out, 'w') as fh:
        fh.write(''.join(f'{c}\t{k}\t{v}\n' for c, k, v in rows))
    print(f'{len(rows)} rows, {bad} cases failed, in {out}')
    return 1 if bad else 0


def load(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            f = line.rstrip('\n').split('\t')
            if len(f) == 3:
                out[(f[0], f[1])] = f[2]
    return out


def compare(a, b, ta, tb):
    """Every row whose value differs, loops' figures by MOVE, then those one
    table has alone."""
    out, moved = [f'{b} against {a}: {len(set(ta) & set(tb))} rows in both'], []
    for k in sorted(set(ta) & set(tb), key=lambda k: (k[0], k[1])):
        x, y = ta[k], tb[k]
        if k[1] == 'per-element':
            r = float(y) / float(x) - 1 if float(x) else 0.0
            if abs(r) >= MOVE - 1e-12:
                moved.append(f'  {k[0]}: per-element {x} -> {y} {r * 100:+.2f}%')
        elif x != y:
            moved.append(f'  {k[0]}: {k[1]} {x} -> {y}')
    out.append(f'rows that differ: {len(moved)}')
    out += moved
    for lab, mine, other in ((a, ta, tb), (b, tb, ta)):
        alone = sorted(set(mine) - set(other))
        if alone:
            out.append(f'only in {lab}: {len(alone)}, the first {" ".join(alone[0])}')
    return out


# --- self-test: a fake compiler writing planted assembly and stub programs,
# a fake perf counting a setup and a cost an element.

FAKE_GHC = r'''#!/bin/bash
o=; s=0; prefix=; for a in "$@"; do
  case $prev in -o) o=$a;; esac
  case $a in -S) s=1;; -ddump-file-prefix=*) prefix=${a#*=};; esac
  prev=$a
done
echo "$*" >> "$FAKELOG"
[ -n "${FAKEFAILGHC:-}" ] && case "$*" in *"$FAKEFAILGHC"*) exit 1;; esac
if [ $s = 1 ]; then
  if case "$*" in *-fno-object-determinism*) true;; *) false;; esac; then
    printf '\t.text\nf:\n\tmovq 8(%%rbp),%%rax\n.Lb:\n\taddq $1,%%rax\n\tcmpq $9,%%rax\n\tjl .Lb\n.Lx:\n\tjmp *(%%rbp)\n' > "$o"
  else
    printf '\t.text\nf:\n\tmovq 8(%%rbp),%%rax\n.Lo:\n\tdecq %%rbx\n.Lb:\n\taddq $1,%%rax\n\tcmpq $9,%%rax\n\tjge .Lx\n\tjmp .Lb\n.Lx:\n\tjne .Lo\n\tjmp *(%%rbp)\n' > "$o"
  fi
  printf -- '-- spills-added-total\n--    (allocs, clobbers, loads, joinRR, joinRM, reg_reg_moves_remaining)\n(0, 0, 1, 2, 0, 7)\n' > "${prefix}.dump-asm-stats"
elif [ -n "$o" ]; then
  mkdir -p "$(dirname "$o")"; printf '#!/bin/sh\nexit 0\n' > "$o"; chmod +x "$o"
fi
exit 0
'''
FAKE_PERF = r'''#!/usr/bin/env python3
import os, sys
a = sys.argv
out, rest = a[a.index('-o') + 1], a[a.index('--') + 1:]
prog, k = os.path.basename(rest[0]), int(rest[-1])
cost = {'H': 7, 'repro': 30, 'Main-noinline': 6, 'Main-inline': 5}[prog]
n = {'H': 1000, 'repro': 250357, 'Main-noinline': 100000, 'Main-inline': 100000}[prog]
if prog == 'repro' and rest[1] == 'b':
    cost = 35
if os.environ.get('FAKEFAILRUN') == prog:
    sys.exit(1)
with open(out, 'w') as fh:
    fh.write('# started' + chr(10) + chr(10) + str(10**6 + cost * n * k) + ',,instructions:u,9,100.00,,' + chr(10))
'''


def self_test():
    global PERF
    bad = []
    with tempfile.TemporaryDirectory(prefix='tickets-') as d:
        ghc, perf = os.path.join(d, 'ghc'), os.path.join(d, 'perf')
        for path, text in ((ghc, FAKE_GHC), (perf, FAKE_PERF)):
            with open(path, 'w') as fh:
                fh.write(text)
            os.chmod(path, 0o755)
        saved, PERF = PERF, [perf]
        cpu = str(sorted(os.sched_getaffinity(0))[0])
        os.environ['FAKELOG'] = os.path.join(d, 'log')
        try:
            out = os.path.join(d, 'a.tsv')
            rc = run(ghc, out, cpu)
            t = load(out)
            want = {('27799 -O2 -fobject-determinism', 'inner'): 'split',
                    ('27799 -O2 -fno-object-determinism', 'inner'): 'fused',
                    ('27799 -O2 -fobject-determinism', 'latches'): 'fused 1 split 1 jmp 0',
                    ('27799 -O1 -fno-object-determinism', 'latches'): 'fused 1 split 0 jmp 0',
                    ('8905 -O1', 'stack'): '2', ('8905 -O1', 'insns'): '8',
                    ('8905 -O1', 'jmp'): '2', ('8905 -O1', 'jcc'): '2',
                    ('27800 -O', 'regalloc'): '0,0,1,2,0,7',
                    ('27981 -O2 -DINL', 'inner'): 'split',
                    ('A -O1', 'per-element'): '7.000', ('27991 -O2', 'per-element'): '7.000',
                    ('27742 -O1 b', 'per-element'): '35.000',
                    ('27981 -O2 inline', 'per-element'): '5.000'}
            got = {k: t.get(k) for k in want}
            if rc != 0 or got != want:
                bad.append(f'the table: exit {rc}, {got}')
            cases = {c for c, _ in t}
            if len(cases) != sum(len(s[3]) * len(s[4]) for s in STATIC) + 2 * (len(HARNESS) + 4):
                bad.append(f'{len(cases)} cases')
            calls = open(os.environ['FAKELOG']).read()
            if '-O0 -c -outputdir b -ib Main.hs' not in calls or '-O1 -S HashStr.hs' in calls:
                bad.append('the harness not at -O0, or a file setting -O2 compiled at -O1')
            # A failed compile and a failed run are rows, and exit 1.
            os.environ['FAKEFAILGHC'] = 'Sink2.hs'
            os.environ['FAKEFAILRUN'] = 'repro'
            rc = run(ghc, os.path.join(d, 'b.tsv'), cpu)
            tb = load(os.path.join(d, 'b.tsv'))
            if rc != 1 or tb.get(('21084 -O1', 'failed')) != 'compile 1' \
                    or tb.get(('27742 -O2 a', 'failed')) != 'run':
                bad.append(f'failures: exit {rc}')
            del os.environ['FAKEFAILGHC'], os.environ['FAKEFAILRUN']
            # compare: a shape, a count and a loop moved, a loop within 0.2%.
            tb = dict(t)
            tb[('27799 -O2 -fno-object-determinism', 'inner')] = 'split'
            tb[('8905 -O1', 'stack')] = '3'
            tb[('A -O1', 'per-element')] = '7.100'
            tb[('S3 -O1', 'per-element')] = '14.020'
            del tb[('10606 -O1', 'insns')]
            got = compare('a', 'b', t, tb)
            want = ['  27799 -O2 -fno-object-determinism: inner fused -> split',
                    '  8905 -O1: stack 2 -> 3', '  A -O1: per-element 7.000 -> 7.100 +1.43%']
            if got[1] != 'rows that differ: 3' or sorted(got[2:5]) != sorted(want) \
                    or got[5] != 'only in a: 1, the first 10606 -O1 insns':
                bad.append(f'compare: {got}')
            if run(os.path.join(d, 'nosuch'), out, cpu) != 2:
                bad.append('a missing compiler did not exit 2')
        finally:
            PERF = saved
    for x in bad:
        print('FAIL', x)
    print('ok   tickets.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    if len(argv) == 4 and argv[0] == 'run':
        return run(*argv[1:])
    if len(argv) == 3 and argv[0] == 'compare':
        try:
            ta, tb = load(argv[1]), load(argv[2])
        except OSError as e:
            print(e, file=sys.stderr)
            return 2
        print('\n'.join(compare(argv[1], argv[2], ta, tb)))
        return 0
    print(__doc__.split('\n\n')[1], file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
