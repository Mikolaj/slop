#!/usr/bin/env python3
"""A differential random test of GHC's code generation: gen.py's programs
compiled by a tree's stage-2 compiler under the flag sets below and by a base
tree's at -O0, -O1 and -O2, each program run with its own default RTS options and
under +RTS -A16k, which collects often, so that heap checks fail. Every compile
and run must succeed and all outputs be equal.

Usage: python3 tools/NCG-fuzz/run.py [--work DIR] [--out DIR] [--first N]
           [--count N] [--skip S,S...] [--tag T] [--quick] [--stage1]
           LANE CPU SECONDS TREE BASE
       python3 tools/NCG-fuzz/run.py --report RESULT...
       python3 tools/NCG-fuzz/run.py --self-test

TREE and BASE name the work directory's ghc-TREE and ghc-BASE (--work, dist-ghcho
by default), whose _build/stage1/bin/ghc is the stage-2 compiler, or, holding
a /, are compilers' paths. Seeds count up from --first, by default (LANE + 1)
* 100000, on CPU, until SECONDS have passed, or, with --count, until N seeds
have run: a lane that SECONDS stop short of them fails, naming the seeds left.
--skip passes over the seeds listed, which run nothing, write no line and count
among the N.
Each seed's line goes to OUT/result-TAG.txt (--out, WORK/fuzz by default; --tag,
LANE by default): `SEED ok (R runs, S s)`, S counted from the lane's start, or
`SEED FAIL` and each of `NAME panic[MESSAGE]`, `NAME compile EXIT`, `NAME run-d
EXIT` (default options), `NAME run-a EXIT` (-A16k) and `outputs differ:` with
the groups of runs agreeing, largest first, or `SEED known` and the same where
every one is a panic of an open upstream issue KNOWN names by its MESSAGE,
which fails no seed: such a panic falls at seeds that move from compiler
to compiler. A seed's program, logs and outputs stay under OUT/fail/TAG-sSEED
unless it is ok; a seed also names its program, through
gen.py. --quick takes the flag sets t-O1, t-O2 and b-O0 alone. Every compile and
run is under ulimit -v 8000000, and timed out at 600 s and 60 s. t-O1-llvm wants
opt-18 and llc-18 on PATH. Exits 0 when no seed failed, 1 when one did or --count's
seeds were not all reached, 2 on wrong arguments or a compiler missing. Run it
unsandboxed.

--report counts result files: seeds by verdict, the failing ones by what failed,
each panic's seeds by level (both compilers, TREE's only, BASE's only), the flag
sets outside a disagreement's largest group and each known issue's seeds
by compiler.

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
# The panics of open upstream issues, by MESSAGE, matched whole: CFG.hs's two
# (https://gitlab.haskell.org/ghc/ghc/-/work_items/27915,
# https://gitlab.haskell.org/ghc/ghc/-/work_items/28088) and JoinToTargets.hs's
# (https://gitlab.haskell.org/ghc/ghc/-/work_items/27638). The series' fix
# of the second keeps a panic, for a move with no free register, whose message
# differs and is not known.
KNOWN = {"Can't find weight for edge that should have one": 'GHC #27915',
         'getSuccessorEdges: Block does not exist': 'GHC #28088',
         "makeMove: we don't handle mem->mem moves": 'GHC #27638'}
PANIC = re.compile(r'(\S+) panic\[(.*)\]')


def verdict(bad):
    """A seed's word for what failed: ok where nothing did, known where each
    failure is a panic KNOWN names, else FAIL."""
    if not bad:
        return 'ok'
    msgs = [PANIC.fullmatch(x) for x in bad]
    return 'known' if all(m and m.group(2) in KNOWN for m in msgs) else 'FAIL'


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
    """{TIP: the compiler of TREE, BASE: the compiler of BASE}, a name
    holding a / taken as the compiler's path."""
    out = {TIP: f'{work}/ghc-{tree}/_build/stage{0 if stage1 else 1}/bin/ghc',
           BASE: f'{work}/ghc-{base}/_build/stage1/bin/ghc'}
    for k, name in ((TIP, tree), (BASE, base)):
        if '/' in name:
            out[k] = os.path.abspath(name)
    return out


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
    seeds = ok = known = 0
    kinds, disagree = collections.Counter(), collections.Counter()
    panics = collections.defaultdict(set)
    issues = collections.defaultdict(lambda: collections.defaultdict(set))
    for line in lines:
        f = line.split(maxsplit=2)
        if len(f) < 2 or not f[0].isdigit():
            continue
        seeds += 1
        if f[1] == 'ok':
            ok += 1
            continue
        known += f[1] == 'known'
        found = set()
        for part in f[2].rsplit(' (', 1)[0].split('; '):
            m = PANIC.fullmatch(part)
            if m:
                panics[m.group(2)].add((f[0], m.group(1)))
                found.add(f'panic[{m.group(2)}]')
                if m.group(2) in KNOWN:
                    issues[KNOWN[m.group(2)]][int(f[0])].add(m.group(1).split('-')[0])
            elif part.startswith('outputs differ: '):
                found.add('outputs differ')
                groups = part[len('outputs differ: '):].split(' | ')
                for g in groups[1:]:
                    disagree.update({x.split('/')[0] for x in g.split(',')})
            else:
                found.add(part.split()[1].split('-')[0])
        if f[1] != 'known':
            kinds.update(found)
    out = [f'{seeds} seeds, {ok} ok, {known} known, {seeds - ok - known} failing']
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
    for issue, where in sorted(issues.items()):
        sides = [(k, [s for s in sorted(where) if where[s] == v]) for k, v in
                 (('both', {TIP, BASE}), ('tree only', {TIP}), ('base only', {BASE}))]
        out.append(f'known {issue}, {len(where)} seeds: '
                   + '; '.join(f'{k} ' + ' '.join(map(str, s)) for k, s in sides if s))
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
    count, skip = None, set()
    while argv[:1] and argv[0].startswith('--'):
        a = argv.pop(0)
        if a == '--quick':
            quick = True
        elif a == '--stage1':
            stage1 = True
        elif a in ('--work', '--out', '--first', '--count', '--skip', '--tag') and argv:
            v = argv.pop(0)
            if a == '--work':
                work = v
            elif a == '--out':
                out = v
            elif a == '--tag':
                tag = v
            elif a == '--skip' and all(x.isdigit() for x in v.split(',')):
                skip = {int(x) for x in v.split(',')}
            elif v.isdigit() and a == '--first':
                first = int(v)
            elif v.isdigit() and int(v) > 0:
                count = int(v)
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
    t0, n, failing, known = time.time(), 0, 0, 0
    last = None if count is None else seed + count
    while (last is None or seed < last) and time.time() - t0 < int(secs):
        if seed in skip:
            seed += 1
            continue
        bad, runs = one(seed, sets, ghcs, cpu, f'{out}/fail/{tag}-s{seed}')
        word = verdict(bad)
        n += 1
        failing += word == 'FAIL'
        known += word == 'known'
        with open(f'{out}/result-{tag}.txt', 'a') as fh:
            text = f'{word} ' + '; '.join(bad) if bad else word
            fh.write(f'{seed} {text} ({runs} runs, {time.time() - t0:.0f}s)\n')
        seed += 1
    short = last is not None and seed < last
    print(f'lane {tag}: {n} seeds, {failing} failing, {known} known, {time.time() - t0:.0f}s'
          + (f'; seeds {seed} to {last - 1} not reached in {secs} s' if short else ''))
    return 1 if failing or short else 0


# --- self-test: compilers, taskset and programs faked, the fake compiler's
# behaviour chosen by the environment.

FAKE_GHC = r'''#!/bin/bash
echo "ghc $0 $*" >> "$FAKELOG"
args=" $* "; out=; prev=
for a in "$@"; do [ "$prev" = -o ] && out=$a; prev=$a; done
case "$args" in
  *" ${FAKEPANIC:-NONE} "*) printf "x: error:\n    panic! (the 'impossible' happened)\n"
    printf "  GHC version 1:\n\t%s\n  more\n" "${FAKEPANICMSG:-Block gone}"; exit 1;;
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
105 known t-O1 panic[Can't find weight for edge that should have one]; b-O1 panic[Can't find weight for edge that should have one] (16 runs, 8s)
106 known t-O2 panic[Can't find weight for edge that should have one]; b-O0 panic[makeMove: we don't handle mem->mem moves] (16 runs, 9s)
107 FAIL b-O2 panic[Can't find weight for edge that should have one]; t-O1 run-d 7 (17 runs, 9s)
not a seed line
"""
# The upstream panics' messages as GHC's master prints them, and the series'
# own panic beside #27638's fix, which must fail.
W27915 = "Can't find weight for edge that should have one"
M27638 = "makeMove: we don't handle mem->mem moves"
G28088 = 'getSuccessorEdges: Block does not exist'
MSERIES = 'makeMove: no free register for a mem->mem move'


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
    check('compilers by path', compilers('/w', '/x/ghc', 'y/ghc', True),
          {TIP: '/x/ghc', BASE: os.path.abspath('y/ghc')})
    # A seed is known only where each failure is a panic of a known MESSAGE,
    # whole: the series' own panic, and any other failure beside one, fail it.
    kw, km = f't-O1 panic[{W27915}]', f'b-O2 panic[{M27638}]'
    for what, b, want in (('nothing failed', [], 'ok'),
                          ('two known panics', [kw, km], 'known'),
                          ("#28088's panic", [f'b-O0 panic[{G28088}]'], 'known'),
                          ("the series' own panic", [f't-O1 panic[{MSERIES}]'], 'FAIL'),
                          ('a known message cut short', [f't-O1 panic[{W27915[:26]}]'], 'FAIL'),
                          ('beside a disagreement', [kw, 'outputs differ: t-O0/d | b-O0/d'],
                           'FAIL'),
                          ('beside an unknown panic', [kw, 't-O0 panic[Block gone]'], 'FAIL'),
                          ('beside a failed compile', [km, 't-O1-lint compile 3'], 'FAIL'),
                          ('beside a crash', [kw, 't-O1-g run-d 7'], 'FAIL'),
                          ('beside a timeout', [kw, 't-O2 run-a timeout'], 'FAIL')):
        check(f'verdict, {what}', verdict(b), want)
    check('known messages past the 60 characters one() keeps', [k for k in KNOWN if len(k) > 60],
          [])
    fakes = ('FAKEPANIC', 'FAKEPANICMSG', 'FAKEFAIL', 'FAKEODD', 'FAKECRASH', 'FAKEHANG',
             'FAKEBASE', 'FAKEBASEODD')
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
            for k in fakes:
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
        (b, n), _, _ = run(31, FAKEPANIC='-fPIC', FAKEPANICMSG=W27915)
        check('a known panic', (b, verdict(b)), ([f't-O1-pic panic[{W27915}]'], 'known'))
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
            '8 seeds, 1 ok, 2 known, 5 failing',
            '  2 panic[Block gone]',
            '  2 panic[Other one]',
            '  2 run',
            '  1 compile',
            '  1 outputs differ',
            f'  1 panic[{W27915}]',
            'panic[Block gone]: O0 both 0, tree only 0, base only 0;'
            ' O1 both 1, tree only 0, base only 0; O2 both 0, tree only 1, base only 0',
            f'panic[{W27915}]: O0 both 0, tree only 0, base only 0;'
            ' O1 both 1, tree only 0, base only 0; O2 both 0, tree only 1, base only 1',
            'panic[Other one]: O0 both 0, tree only 1, base only 1;'
            ' O1 both 0, tree only 0, base only 0; O2 both 0, tree only 0, base only 0',
            f'panic[{M27638}]: O0 both 0, tree only 0, base only 1;'
            ' O1 both 0, tree only 0, base only 0; O2 both 0, tree only 0, base only 0',
            'outside the largest group: t-O1-pic 1',
            'known GHC #27638, 1 seeds: base only 106',
            'known GHC #27915, 3 seeds: both 105; tree only 106; base only 107'])
        check("report of #28088's panic", report([f'108 known b-O1 panic[{G28088}] (16 runs, 9s)'])[-1],
              'known GHC #28088, 1 seeds: base only 108')
        for k in fakes:
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
        # A lane whose one failure is a known panic passes and counts it; beside
        # a disagreement, or as the series' own panic, it fails.
        for tag, env, code, head in (
                ('k', {'FAKEPANICMSG': W27915}, 0, f'31 known t-O1-pic panic[{W27915}] ('),
                ('m', {'FAKEPANICMSG': W27915, 'FAKEODD': '-g'}, 1,
                 f'31 FAIL t-O1-pic panic[{W27915}]; outputs differ: '),
                ('s', {'FAKEPANICMSG': MSERIES}, 1, f'31 FAIL t-O1-pic panic[{MSERIES}] (')):
            p = cli('--work', w, '--out', o, '--first', '31', '--count', '1', '--tag', tag,
                    '0', '5', '30', 't', 'b', FAKEPANIC='-fPIC', **env)
            have = open(f'{o}/result-{tag}.txt').read()
            if (p.returncode != code or not have.startswith(head)
                    or f': 1 seeds, {code} failing, {1 - code} known, ' not in p.stdout):
                bad.append(f'lane {tag}: {p.returncode} {have!r} {p.stdout!r}')
        p = cli('--report', f'{o}/result-k.txt')
        check('--report of a known seed', (p.returncode, p.stdout.split('\n')[0],
                                            p.stdout.split('\n')[-2]),
              (0, '1 seeds, 0 ok, 1 known, 0 failing', 'known GHC #27915, 1 seeds: tree only 31'))
        p = cli('--report', f'{o}/result-x.txt')
        if p.returncode or not p.stdout.endswith(' failing\n'):
            bad.append(f'--report: {p.returncode} {p.stdout!r}')
        # --count: N seeds and no more, the tree a path; a lane short of them fails.
        g0 = f'{w}/ghc-t/_build/stage0/bin/ghc'
        open(log, 'w').close()
        p = cli('--work', w, '--out', o, '--first', '40', '--count', '3', '--skip', '41,99',
                '--tag', 'c', '0', '5', '30', g0, 'b')
        have = open(f'{o}/result-c.txt').read().split('\n')[:-1] if p.returncode == 0 else []
        if (p.returncode or [x.split()[:2] for x in have] != [['40', 'ok'], ['42', 'ok']]
                or f'ghc {g0} -O1 ' not in open(log).read()):
            bad.append(f'--count 3 --skip 41 over a path: {p.returncode} {have!r} {p.stderr[-200:]}')
        p = cli('--work', w, '--out', o, '--first', '50', '--count', '100000', '--tag', 'd',
                '0', '5', '1', 't', 'b')
        if p.returncode != 1 or 'seeds 5' not in p.stdout or ' to 100049 not reached' not in p.stdout:
            bad.append(f'a lane short of its count: {p.returncode} {p.stdout!r}')
        for args in (['0', '5', '1', 't'], ['x', '5', '1', 't', 'b'], ['--first', 'x', '0', '5', '1',
                                                                      't', 'b'],
                     ['--work', w, '0', '5', '1', 'none', 'b'], ['--nosuch', '0', '5', '1', 't', 'b'],
                     ['--count', '0', '0', '5', '1', 't', 'b'], ['--count', 'x', '0', '5', '1', 't', 'b'],
                     ['--skip', '4,x', '0', '5', '1', 't', 'b'],
                     ['--work', w, '0', '5', '1', 't', f'{d}/nosuch/ghc']):
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
