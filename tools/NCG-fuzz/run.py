#!/usr/bin/env python3
"""A differential random test of GHC's code generation: gen.py's programs
compiled by a tree's stage-2 compiler under the flag sets below and by a base
tree's at -O0, -O1 and -O2, each program run with its own default RTS options and
under +RTS -A16k, which collects often, so that heap checks fail. Every compile
and run must succeed and all outputs be equal.

Usage: python3 tools/NCG-fuzz/run.py [--work DIR] [--out DIR] [--first N]
           [--tag T] [--quick] [--stage1] LANE CPU SECONDS TREE BASE
       python3 tools/NCG-fuzz/run.py --report RESULT...
       python3 tools/NCG-fuzz/run.py --self-test

TREE and BASE name the work directory's ghc-TREE and ghc-BASE (--work, dist-ghcho
by default), whose _build/stage1/bin/ghc is the stage-2 compiler. Seeds count up
from --first, by default (LANE + 1) * 100000, on CPU, until SECONDS have passed.
Each seed's line goes to OUT/result-TAG.txt (--out, WORK/fuzz by default; --tag,
LANE by default): `SEED ok (R runs, S s)`, S counted from the lane's start, or
`SEED FAIL` and each of `NAME panic[MESSAGE]`, `NAME compile EXIT`, `NAME run-d
EXIT` (default options), `NAME run-a EXIT` (-A16k) and `outputs differ:` with
the groups of runs agreeing, largest first. A failing seed's program, logs and
outputs stay under OUT/fail/TAG-sSEED; a seed also names its program, through
gen.py. --quick takes the flag sets t-O1, t-O2 and b-O0 alone. Every compile and
run is under ulimit -v 8000000, and timed out at 600 s and 60 s. t-O1-llvm wants
opt-18 and llc-18 on PATH. Exits 0 when no seed failed, 1 when one did, 2 on
wrong arguments or a compiler missing. Run it unsandboxed.

--report counts result files: seeds by what failed, each panic's seeds by level
(both compilers, TREE's only, BASE's only) and the flag sets outside
a disagreement's largest group.

-fregs-graph and -fregs-iterative are left out (Mikolaj, 2026-11-03): on programs
with vector code their output differs from the default allocator's, at GHC's
master too, which fits https://gitlab.haskell.org/ghc/ghc/-/work_items/27993,
so that they would report only that.

This test is proved able to fail by breaking the register allocator in a tree
built from scratch, never in a copy, which keeps the original's absolute paths
and links its libraries: hadrian/build _build/stage0/bin/ghc, then --stage1
--quick, which takes that stage-1 compiler for TREE. Seeds must fail by wrong
output or a crash, a panic proving nothing: GHC's master panics on some of these
programs too. Otherwise the generator has to grow before a pass here means much.
"""

import collections
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = '/home/mikolaj/slop/dist-ghcho'
COMPILE_TIMEOUT, RUN_TIMEOUT = 600, 60
CAP = 'ulimit -v 8000000; exec "$@"'
LLVM = ['-pgmlo', 'opt-18', '-pgmlc', 'llc-18']
TIP, BASE = 't', 'b'
SETS = [  # name, compiler, flags, every k-th seed
    ('t-O0', TIP, ['-O0'], 1),
    ('t-O1', TIP, ['-O1'], 1),
    ('t-O2', TIP, ['-O2'], 1),
    ('t-O1-lint', TIP, ['-O1', '-dlint'], 1),
    ('t-O1-pic', TIP, ['-O1', '-fPIC'], 1),
    ('t-O1-g', TIP, ['-O1', '-g'], 1),
    ('t-O2-cpu', TIP, ['-O2', '-mavx2', '-mbmi2', '-mfma'], 1),
    ('t-O2-nospred', TIP, ['-O2', '-fno-cmm-static-pred'], 2),
    ('t-O1-nocfg', TIP, ['-O1', '-fno-block-layout-cfg'], 2),
    ('t-O2-nosink', TIP, ['-O2', '-fno-cmm-sink'], 3),
    ('t-O2-short', TIP, ['-O2', '-fasm-shortcutting'], 2),
    ('t-O1-llvm', TIP, ['-O1', '-fllvm'] + LLVM, 10),
    ('b-O0', BASE, ['-O0'], 1),
    ('b-O1', BASE, ['-O1'], 1),
    ('b-O2', BASE, ['-O2'], 1),
]
QUICK = ('t-O1', 't-O2', 'b-O0')
RUNS = (('d', []), ('a', ['+RTS', '-A16k', '-RTS']))


def sh(argv, cpu, cwd, out, timeout):
    """argv under the memory cap on cpu: its exit, or 'timeout'."""
    with open(out, 'w') as fh:
        try:
            return subprocess.run(['taskset', '-c', cpu, 'bash', '-c', CAP, '_'] + argv,
                                  cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return 'timeout'


def compilers(work, tree, base, stage1):
    """{TIP: the compiler of TREE, BASE: the compiler of BASE}."""
    return {TIP: f'{work}/ghc-{tree}/_build/stage{0 if stage1 else 1}/bin/ghc',
            BASE: f'{work}/ghc-{base}/_build/stage1/bin/ghc'}


def one(seed, sets, ghcs, cpu, keep, run_timeout=RUN_TIMEOUT):
    """Compile and run one seed's program: what failed, and the runs made."""
    with tempfile.TemporaryDirectory(prefix='ncg-fuzz-') as w:
        with open(f'{w}/Main.hs', 'w') as fh:
            subprocess.run([sys.executable, f'{HERE}/gen.py', str(seed)], stdout=fh,
                           check=True)
        outs, bad = {}, []
        for name, who, flags, k in sets:
            if seed % k:
                continue
            d = f'{w}/{name}'
            os.makedirs(d)
            e = sh([ghcs[who]] + flags + ['-fforce-recomp', '-rtsopts', '-outputdir', d,
                                          '-o', f'{d}/p', f'{w}/Main.hs'],
                   cpu, w, f'{d}/compile.log', COMPILE_TIMEOUT)
            if e != 0:
                with open(f'{d}/compile.log', errors='replace') as fh:
                    m = re.search(r"the 'impossible' happened\)\n.*\n\s*(.*)", fh.read())
                bad.append(f'{name} panic[{m.group(1)[:60]}]' if m
                           else f'{name} compile {e}')
                continue
            for mode, rts in RUNS:
                e = sh([f'{d}/p'] + rts, cpu, w, f'{d}/out-{mode}', run_timeout)
                if e != 0:
                    bad.append(f'{name} run-{mode} {e}')
                    continue
                with open(f'{d}/out-{mode}', 'rb') as fh:
                    outs[f'{name}/{mode}'] = fh.read()
        groups = {}
        for k, v in outs.items():
            groups.setdefault(v, []).append(k)
        if len(groups) > 1:
            ranked = sorted(groups.values(), key=len, reverse=True)
            bad.append('outputs differ: ' + ' | '.join(','.join(g) for g in ranked))
        if bad:
            shutil.rmtree(keep, ignore_errors=True)
            shutil.copytree(w, keep, ignore=shutil.ignore_patterns('*.o', '*.hi', 'p'))
    return bad, len(outs)


def report(lines):
    """The --report lines of result lines."""
    seeds = ok = 0
    kinds, disagree = collections.Counter(), collections.Counter()
    panics = collections.defaultdict(set)
    for line in lines:
        f = line.split(maxsplit=2)
        if len(f) < 2 or not f[0].isdigit():
            continue
        seeds += 1
        if f[1] == 'ok':
            ok += 1
            continue
        found = set()
        for part in f[2].rsplit(' (', 1)[0].split('; '):
            m = re.fullmatch(r'(\S+) panic\[(.*)\]', part)
            if m:
                panics[m.group(2)].add((f[0], m.group(1)))
                found.add(f'panic[{m.group(2)}]')
            elif part.startswith('outputs differ: '):
                found.add('outputs differ')
                groups = part[len('outputs differ: '):].split(' | ')
                for g in groups[1:]:
                    disagree.update({x.split('/')[0] for x in g.split(',')})
            else:
                found.add(part.split()[1].split('-')[0])
        kinds.update(found)
    out = [f'{seeds} seeds, {ok} ok, {seeds - ok} failing']
    out += [f'  {n} {k}' for k, n in sorted(kinds.items(), key=lambda x: (-x[1], x[0]))]
    for msg, where in sorted(panics.items()):
        cells = []
        for level in ('O0', 'O1', 'O2'):
            t = {s for s, n in where if n == f't-{level}'}
            b = {s for s, n in where if n == f'b-{level}'}
            cells.append(f'{level} both {len(t & b)}, tree only {len(t - b)},'
                         f' base only {len(b - t)}')
        out.append(f'panic[{msg}]: ' + '; '.join(cells))
    if disagree:
        out.append('outside the largest group: '
                   + ', '.join(f'{k} {n}' for k, n in
                               sorted(disagree.items(), key=lambda x: (-x[1], x[0]))))
    return out


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    if argv[:1] == ['--report'] and argv[1:]:
        lines = []
        for path in argv[1:]:
            with open(path) as fh:
                lines += fh.read().split('\n')
        print('\n'.join(report(lines)))
        return 0
    work, out, first, tag, quick, stage1 = WORK, None, None, None, False, False
    while argv[:1] and argv[0].startswith('--'):
        a = argv.pop(0)
        if a == '--quick':
            quick = True
        elif a == '--stage1':
            stage1 = True
        elif a in ('--work', '--out', '--first', '--tag') and argv:
            v = argv.pop(0)
            if a == '--work':
                work = v
            elif a == '--out':
                out = v
            elif a == '--tag':
                tag = v
            elif v.isdigit():
                first = int(v)
            else:
                argv = []
        else:
            argv = []
    if len(argv) != 5 or not argv[0].isdigit() or not argv[2].isdigit():
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    lane, cpu, secs, tree, base = argv
    work = os.path.abspath(work)
    out = os.path.abspath(out or f'{work}/fuzz')
    tag = tag or lane
    seed = (int(lane) + 1) * 100000 if first is None else first
    ghcs = compilers(work, tree, base, stage1)
    for ghc in ghcs.values():
        if not os.access(ghc, os.X_OK):
            print(f'no {ghc}', file=sys.stderr)
            return 2
    sets = [x for x in SETS if x[0] in QUICK] if quick else SETS
    os.environ.pop('GHC_PACKAGE_PATH', None)
    os.makedirs(f'{out}/fail', exist_ok=True)
    t0, n, failing = time.time(), 0, 0
    while time.time() - t0 < int(secs):
        bad, runs = one(seed, sets, ghcs, cpu, f'{out}/fail/{tag}-s{seed}')
        n += 1
        failing += bool(bad)
        with open(f'{out}/result-{tag}.txt', 'a') as fh:
            verdict = 'FAIL ' + '; '.join(bad) if bad else 'ok'
            fh.write(f'{seed} {verdict} ({runs} runs, {time.time() - t0:.0f}s)\n')
        seed += 1
    print(f'lane {tag}: {n} seeds, {failing} failing, {time.time() - t0:.0f}s')
    return 1 if failing else 0


# --- self-test: compilers, taskset and programs faked, the fake compiler's
# behaviour chosen by the environment.

FAKE_GHC = r'''#!/bin/bash
echo "ghc $0 $*" >> "$FAKELOG"
args=" $* "; out=; prev=
for a in "$@"; do [ "$prev" = -o ] && out=$a; prev=$a; done
case "$args" in
  *" ${FAKEPANIC:-NONE} "*) printf "x: error:\n    panic! (the 'impossible' happened)\n"
    printf "  GHC version 1:\n\tBlock gone\n  more\n"; exit 1;;
  *" ${FAKEFAIL:-NONE} "*) echo "x.hs:1:1: error"; exit 3;;
esac
word=same; code=0; pause=0
case "$args" in *" ${FAKEODD:-NONE} "*) word=odd;; esac
case "$args" in *" ${FAKECRASH:-NONE} "*) code=7;; esac
case "$args" in *" ${FAKEHANG:-NONE} "*) pause=30;; esac
[ "$0" = "${FAKEBASE:-NONE}" ] && [ -n "${FAKEBASEODD:-}" ] && word=base
cat > "$out" <<EOF
#!/bin/bash
echo "run \$(ulimit -v) \$*" >> "$FAKELOG"
echo $word
sleep $pause
exit $code
EOF
chmod +x "$out"
'''
FAKE_TASKSET = '#!/bin/bash\necho "taskset $1 $2" >> "$FAKELOG"\nshift 2\nexec "$@"\n'
RESULTS = """\
100 ok (20 runs, 3s)
101 FAIL t-O1 panic[Block gone]; b-O1 panic[Block gone]; t-O0 panic[Other one] (20 runs, 4s)
102 FAIL t-O2 panic[Block gone]; outputs differ: a/d,a/a,c/d | t-O1-pic/d,t-O1-pic/a (20 runs, 5s)
103 FAIL b-O0 panic[Other one]; t-O1 run-a timeout (20 runs, 6s)
104 FAIL t-O1 compile 3 (20 runs, 7s)
not a seed line
"""


def self_test():
    bad = []

    def check(what, have, want):
        if have != want:
            bad.append(f'{what}: {have!r}, not {want!r}')
    names = [x[0] for x in SETS]
    for x in SETS:
        if '-fregs-graph' in x[2] or '-fregs-iterative' in x[2]:
            bad.append(f'{x[0]} takes {x[2]}, left out by ruling')
    if len(set(names)) != len(names):
        bad.append(f'a flag set named twice: {names}')
    check('--quick sets', [x for x in QUICK if x not in names], [])
    check('compilers', compilers('/w', 'x', 'y', False),
          {TIP: '/w/ghc-x/_build/stage1/bin/ghc', BASE: '/w/ghc-y/_build/stage1/bin/ghc'})
    check('--stage1 compilers', compilers('/w', 'x', 'y', True),
          {TIP: '/w/ghc-x/_build/stage0/bin/ghc', BASE: '/w/ghc-y/_build/stage1/bin/ghc'})
    saved = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix='ncg-fuzz-test-') as d:
        fb, w, log = f'{d}/bin', f'{d}/w', f'{d}/fake.log'
        os.makedirs(fb)
        with open(f'{fb}/taskset', 'w') as fh:
            fh.write(FAKE_TASKSET)
        os.chmod(f'{fb}/taskset', 0o755)
        for tree, stage in (('t', 1), ('t', 0), ('b', 1)):
            os.makedirs(f'{w}/ghc-{tree}/_build/stage{stage}/bin')
            path = f'{w}/ghc-{tree}/_build/stage{stage}/bin/ghc'
            with open(path, 'w') as fh:
                fh.write(FAKE_GHC)
            os.chmod(path, 0o755)
        ghcs = compilers(w, 't', 'b', False)
        os.environ.update(PATH=fb + os.pathsep + os.environ['PATH'], FAKELOG=log)

        def run(seed, sets=SETS, timeout=RUN_TIMEOUT, **env):
            for k in ('FAKEPANIC', 'FAKEFAIL', 'FAKEODD', 'FAKECRASH', 'FAKEHANG',
                      'FAKEBASE', 'FAKEBASEODD'):
                os.environ.pop(k, None)
            os.environ.update(env)
            open(log, 'w').close()
            keep = f'{d}/keep-{seed}'
            shutil.rmtree(keep, ignore_errors=True)
            got = one(seed, sets, ghcs, '5', keep, timeout)
            with open(log) as fh:
                return got, keep, fh.read().split('\n')[:-1]
        (b, n), keep, lines = run(30)
        check('all agree', (b, n), ([], 30))
        if os.path.exists(keep):
            bad.append('a passing seed was kept')
        comp = [x for x in lines if x.startswith('ghc ')]
        check('compiles at seed 30', len(comp), len(SETS))
        check('compiles by base', sum(f'{w}/ghc-b/' in x for x in comp), 3)
        check('compiles by stage 2', sum('/_build/stage1/bin/ghc ' in x for x in comp),
              len(SETS))
        rn = [x for x in lines if x.startswith('run ')]
        check('runs', len(rn), 30)
        check('memory cap', {x.split()[1] for x in rn}, {'8000000'})
        check('-A16k runs', sum(x.endswith('+RTS -A16k -RTS') for x in rn), 15)
        check('default runs', sum(len(x.split()) == 2 for x in rn), 15)
        if not all(x == 'taskset -c 5' for x in lines if x.startswith('taskset')):
            bad.append('a command off the CPU')
        check('every k-th seed', run(31)[0], ([], 20))
        (b, n), keep, _ = run(31, FAKEODD='-fPIC')
        check('one flag set off', b, ['outputs differ: ' + ','.join(
            f'{x}/{m}' for x in ('t-O0', 't-O1', 't-O2', 't-O1-lint', 't-O1-g', 't-O2-cpu',
                                 'b-O0', 'b-O1', 'b-O2') for m in 'da')
                                      + ' | t-O1-pic/d,t-O1-pic/a'])
        if not os.path.isfile(f'{keep}/Main.hs') or not os.path.isfile(f'{keep}/t-O1-pic/out-d'):
            bad.append('a failing seed not kept')
        if os.path.exists(f'{keep}/t-O1-pic/p'):
            bad.append('a kept seed holds its binary')
        (b, n), _, _ = run(31, FAKEPANIC='-fPIC')
        check('a panic', (b, n), (['t-O1-pic panic[Block gone]'], 18))
        (b, n), _, _ = run(31, FAKEFAIL='-dlint')
        check('a failed compile', (b, n), (['t-O1-lint compile 3'], 18))
        (b, n), _, _ = run(31, FAKECRASH='-g')
        check('a crash', (b, n), (['t-O1-g run-d 7', 't-O1-g run-a 7'], 18))
        quick = [x for x in SETS if x[0] in QUICK]
        (b, n), _, _ = run(31, quick, 1, FAKEHANG='-O2')
        check('a program that hangs', (b, n), (['t-O2 run-d timeout', 't-O2 run-a timeout'], 4))
        (b, n), _, lines = run(31, quick)
        check('--quick', ((b, n), sum(x.startswith('ghc ') for x in lines)), (([], 6), 3))
        (b, n), _, _ = run(31, quick, FAKEBASE=ghcs[BASE], FAKEBASEODD='1')
        check('the base off', b, ['outputs differ: t-O1/d,t-O1/a,t-O2/d,t-O2/a | b-O0/d,b-O0/a'])
        check('report', report(RESULTS.split('\n')), [
            '5 seeds, 1 ok, 4 failing',
            '  2 panic[Block gone]',
            '  2 panic[Other one]',
            '  1 compile',
            '  1 outputs differ',
            '  1 run',
            'panic[Block gone]: O0 both 0, tree only 0, base only 0;'
            ' O1 both 1, tree only 0, base only 0; O2 both 0, tree only 1, base only 0',
            'panic[Other one]: O0 both 0, tree only 1, base only 1;'
            ' O1 both 0, tree only 0, base only 0; O2 both 0, tree only 0, base only 0',
            'outside the largest group: t-O1-pic 1'])
        for k in ('FAKEPANIC', 'FAKEFAIL', 'FAKEODD', 'FAKECRASH', 'FAKEHANG', 'FAKEBASE',
                  'FAKEBASEODD'):
            os.environ.pop(k, None)
        o = f'{d}/out'

        def cli(*a, **env):
            return subprocess.run([sys.executable, os.path.abspath(__file__)] + list(a),
                                  capture_output=True, text=True, env=dict(os.environ, **env))
        p = cli('--work', w, '--out', o, '--first', '31', '--tag', 'x', '0', '5', '1', 't', 'b')
        have = open(f'{o}/result-x.txt').read().split('\n')[0] if p.returncode == 0 else ''
        if p.returncode or not re.fullmatch(r'31 ok \(20 runs, \d+s\)', have):
            bad.append(f'a lane: {p.returncode} {have!r} {p.stderr[-200:]}')
        p = cli('--work', w, '--out', o, '--first', '131', '--tag', 'y', '0', '5', '1', 't', 'b',
                FAKEODD='-g')
        have = open(f'{o}/result-y.txt').read().split('\n')[0] if p.returncode == 1 else ''
        if p.returncode != 1 or not have.startswith('131 FAIL outputs differ: '):
            bad.append(f'a lane with a failure: {p.returncode} {have!r}')
        if not os.path.isfile(f'{o}/fail/y-s131/Main.hs'):
            bad.append('a lane kept no failure')
        p = cli('--report', f'{o}/result-x.txt')
        if p.returncode or not p.stdout.endswith(' failing\n'):
            bad.append(f'--report: {p.returncode} {p.stdout!r}')
        for args in (['0', '5', '1', 't'], ['x', '5', '1', 't', 'b'], ['--first', 'x', '0', '5', '1',
                                                                      't', 'b'],
                     ['--work', w, '0', '5', '1', 'none', 'b'], ['--nosuch', '0', '5', '1', 't', 'b']):
            p = cli(*args)
            if p.returncode != 2:
                bad.append(f'{args} exited {p.returncode}, not 2')
    os.environ.clear()
    os.environ.update(saved)
    for x in bad:
        print('FAIL', x)
    print('ok   run.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
