#!/usr/bin/env python3
"""The measurement battery of the NCG series, for one compiler tree under one
label: nofib at -O2, -O1 and -O0, the tasty-papi benchmarks of containers,
vector and megaparsec at -O2 and -O1, and the fifteen compilations by the
tree's stage-1 and stage-2 compilers; or some of these parts alone.

Usage: python3 tools/NCG-battery/battery.py [--dry] [--work DIR] [--out DIR]
           TREE LABEL CPUS [PART...]
       python3 tools/NCG-battery/battery.py --self-test

TREE names the work directory's ghc-TREE, whose _build/stage0/bin/ghc is the
stage-1 compiler and _build/stage1/bin/ghc the stage-2 one. CPUS is a taskset
list of three CPUs or more. With no PART, the whole battery: it stops if any
of the label's results exist, copies both compilers to ghc-LABEL beside
themselves, and runs two lanes on CPUS, nofib in one and in the other the
packages at -O2, then at -O1, then the compilations, the stage-1 compiler's
on CPUS' second CPU beside the stage-2 compiler's on its third; its lines go
to OUT/meas-LABEL.log. A PART -- nofib-O2, nofib-O1, nofib-O0,
containers-O2, containers-O1, vector-O2, vector-O1, megaparsec-O2,
megaparsec-O1, comp1 or comp2 -- runs alone, in the order given, on CPUS,
with ghc-LABEL already in place. The battery is a bash script; --dry prints
it, every file it generates written out in it, and runs nothing. Run it
unsandboxed. It exits 0 when every part ran and 2 when it stopped over the
label's results or a part failed: a compiler missing, or a build, nofib-run,
a benchmark run or compile-cost.py failing, the part's log saying which;
compile-cost.py's warnings fail nothing.

The work directory (--work, dist-ghcho by default) holds the trees, nofib-r
(the nofib checkout and its built nofib-run), vpapi (the packages' sources
and tasty-papi-settle2, the tasty-papi built in place of Hackage's), ghc-g's
testsuite and the ManyBasicBlocks.cmm the compilations read; OUT (--out,
WORK/battery by default) the log and the compilations' files. The layout is
that of the scripts this replaces, so that their results stay comparable
through nbcmp.py and pkgcmp.py:

  nofib       nofib-r/nofib/_make/cTREE-LABEL, o1-LABEL and o0-LABEL, the
              compiler's figures in nofib-r/stats under the same names
  containers  vpapi/cres/cTREE-LABEL/PROGRAM-I.csv, cTREE-o1-LABEL at -O1
  vector      vpapi/res-cTREE-LABEL-I.csv, res-cTREE-o1-LABEL-I.csv at -O1
  megaparsec  vpapi/mres/cTREE-LABEL/bench-speed-I.csv, cTREE-o1-LABEL
  comp        OUT/compN-LABEL.txt, compile-cost.py's table, OUT/compN-LABEL.runs,
              its --out file, and its first round's assembly in OUT/pLABEL
              (stage 1) and OUT/pLABEL-2 (stage 2)

The settings, each stated here and nowhere else:
1. Benchmark programs, nofib's and the packages', run with their own default
   RTS options and the RTS clock running, as Mikolaj ruled on 2026-10-30:
   "no -V0 in any benchmarks". The packages' ghc-options carry no
   -with-rtsopts=-V0, and nothing here adds one.
2. Every benchmark program runs with address-space randomisation off
   (setarch -R), with it on runs of one program having differed by tens of
   instructions: the packages' programs each, and nofib-run, whose compiles
   and programs inherit it (Mikolaj, 2026-11-03, for the series' rebuild;
   the scripts replaced ran vector's and nofib's with it on).
3. Rounds: nofib runs each program once, nofib-run's default; containers'
   and vector's benchmark programs run 5 times and megaparsec's 10,
   pkgcmp.py reading their spread.
4. The fifteen compilations are counted by tools/compile-cost.py with its
   own defaults: its cells, its rounds and its RTS options, -A3G -V0 after
   GHC's own; `compile-cost.py compare` compares two labels' .runs files.
5. nofib's compiler wrapper passes +RTS -A3G -V0 -RTS before nofib-run's
   arguments, for the reason compile-cost.py runs under them: under GHC's
   own options (-H) the collections fall elsewhere from one run to the next
   at byte-equal allocation, and the compiler's instructions spread by 0.3%
   to 0.65%. A module whose compile allocates more than 3 GB collects again,
   which nbcmp.py's compiler collections show.
6. nofib-run at -j3 and cabal at -j2, the two lanes sharing CPUS, as the
   scripts replaced ran them.
"""

import contextlib
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = '/home/mikolaj/slop/dist-ghcho'
COMPILE_COST = os.path.join(os.path.dirname(HERE), 'compile-cost.py')

# The settings of the docstring, by number.
ROUNDS = {'containers': 5, 'vector': 5, 'megaparsec': 10}  # 3
NOFIB_RTS = '+RTS -A3G -V0 -RTS'  # 5
NOFIB_J, CABAL_J = 3, 2  # 6

# Under the work directory.
NOFIB_RUN = ('nofib-r/nofib/dist-newstyle/build/x86_64-linux/ghc-9.12.4/'
             'nofib-0.1.0.0/x/nofib-run/build/nofib-run/nofib-run')
HSC2HS = 'nofib-r/c/f/_build/stage0/bin/hsc2hs'
PAPIPKG = 'vpapi/tasty-papi-settle2'
PERF_TESTS = 'ghc-g/testsuite/tests/perf/compiler'
MBB = 'tmp-save-2026-10-30/m9/gen/ManyBasicBlocks.cmm'
CONTAINERS_CABAL = 'vpapi/ctr/containers/containers-tests/containers-tests.cabal'
SPECTRAL_MAKEFILE = 'nofib-r/nofib/spectral/Makefile'
# nofib's GHCi, which no compiled benchmark runs.
GHCI = os.path.expanduser('~/.ghcup/bin/ghc-9.12.4')
# At -O0 spectral/minimax runs 43 minutes under any GHC, so it is left out.
O0_SKIP = 'minimax'

INDEX_STATE = 'hackage.haskell.org 2026-09-19T16:13:55Z'
ALLOW_NEWER = 'base, ghc-prim, ghc-bignum, template-haskell, containers, deepseq'
PKGS = {
    'containers': {
        'log': 'cb', 'src': 'ctr', 'builddir': 'cdist',
        'packages': 'containers/containers-tests tasty-bench-papi',
        'allow': '', 'constraints': '',
        'stanzas': ('containers-tests',), 'flags': {},
        'build': 'containers-tests:benchmarks',
        'bin': 'containers-tests:bench:{prog}',
        'resdir': 'cres/{lab}', 'csv': 'cres/{lab}/{prog}-$i.csv'},
    'vector': {
        'log': 'vb', 'src': 'src', 'builddir': 'dist',
        'packages': 'vector vector-stream vector-bench-papi',
        'allow': '', 'constraints': '',
        'stanzas': ('vector', 'vector-stream', 'vector-bench-papi'),
        'flags': {'vector-bench-papi': '+BenchPAPI'},
        'build': 'vector-bench-papi:bench:algorithms-papi',
        'bin': 'vector-bench-papi:bench:algorithms-papi',
        'progs': ('algorithms-papi',),
        'resdir': None, 'csv': 'res-{lab}-$i.csv'},
    'megaparsec': {
        'log': 'mb', 'src': 'mtr', 'builddir': 'mdist',
        # every tree but ghc-f also builds mtr's case-insensitive-1.2.1.0,
        # GHC's master rejecting the package's noncanonical mappend
        'packages': 'megaparsec-9.8.1 criterion-papi',
        'unless_f': ' case-insensitive-1.2.1.0',
        'allow': ', text, bytestring',
        'constraints': 'constraints: hashable ==1.5.0.0',
        'stanzas': ('megaparsec',), 'flags': {},
        'build': 'megaparsec:bench:bench-speed',
        'bin': 'megaparsec:bench:bench-speed', 'progs': ('bench-speed',),
        'resdir': 'mres/{lab}', 'csv': 'mres/{lab}/{prog}-$i.csv'},
}
PARTS = ('nofib-O2', 'nofib-O1', 'nofib-O0', 'containers-O2', 'vector-O2',
         'megaparsec-O2', 'containers-O1', 'vector-O1', 'megaparsec-O1',
         'comp1', 'comp2')
EOF = 'NCG_EOF'


def q(s):
    return shlex.quote(str(s))


def heredoc(path, text):
    return f'cat > {q(path)} <<\'{EOF}\'\n{text}{EOF}'


def read_lines(work, rel):
    path = os.path.join(work, rel)
    if not os.path.isfile(path):
        raise ValueError(f'no {path}')
    with open(path) as fh:
        return fh.read().split('\n')


def o0_tests(work):
    """The benchmarks nofib runs at -O0: every top-level directory but
    spectral, whose subdirectories are named but O0_SKIP."""
    lines = read_lines(work, SPECTRAL_MAKEFILE)
    words, on = [], False
    for line in lines:
        if line.startswith('SUBDIRS'):
            on = True
        if not on:
            continue
        if line == '':
            break
        line = re.sub(r'^SUBDIRS *=', '', line).replace('\\', '', 1)
        words += line.split()
    return (['imaginary', 'real', 'shootout']
            + ['spectral/' + w for w in words if w != O0_SKIP])


def containers_progs(work):
    out = []
    for line in read_lines(work, CONTAINERS_CABAL):
        m = re.match(r'benchmark ([a-z-]*)', line)
        if m and m.group(1):
            out.append(m.group(1))
    if not out:
        raise ValueError(f'no benchmark in {os.path.join(work, CONTAINERS_CABAL)}')
    return out


def wrapper(tree, label, ghc):
    return ('#!/bin/sh\n'
            f'# ghc-{tree}\'s ghc-{label} under perf stat, with the battery\'s'
            ' RTS options; GHCi is GHC 9.12.4\'s.\n'
            f'[ "$1" = --interactive ] && exec {GHCI} "$@"\n'
            'id=$$.$(date +%s%N)\n'
            'printf \'%s\\n\' "$PWD" "$@" > "${NB_STATS:?}/$id.args"\n'
            'exec perf stat -x, -e instructions:u -o "$NB_STATS/$id.csv" -- '
            f'{ghc} {NOFIB_RTS} "$@"\n')


def nofib_part(work, tree, label, level):
    n = f'{work}/nofib-r'
    f = f'{work}/ghc-{tree}/_build/stage0/bin'
    ghc = f'{f}/ghc-{label}'
    if level == 2:
        tag, wdir, res = f'nbf {label}', f'{n}/c{tree}/{label}', f'c{tree}-{label}'
        lines, log = f'{n}/nbf.log', f'{n}/nbf-{label}.log'
        tests, opt = [], []
    else:
        tag, wdir, res = f'nbo {level} {label}', f'{n}/co/{label}', f'o{level}-{label}'
        lines, log = f'{n}/nbo.log', f'{n}/nbo{level}-{label}.log'
        tests = o0_tests(work) if level == 0 else []
        opt = ['--compiler-arg', f'-O{level}']
    w, stats = f'{wdir}/w', f'{n}/stats/{res}'
    argv = ([f'{work}/{NOFIB_RUN}'] + tests
            + [f'-j{NOFIB_J}', '-w', f'{w}/ghc', '-o', res] + opt
            + ['--speed=Norm', '--perf', '--perf-arg=-e',
               '--perf-arg=instructions:u'])
    shootout = ' '.join(q(f'_make/{res}/shootout/{x}') for x in (
        'fasta/fasta.stdout',
        'reverse-complement/reverse-complement.stdin',
        'reverse-complement/reverse-complement.stdout'))
    return '\n'.join([
        f'# {tag}: nofib at -O{level}',
        f'[ -x {q(ghc)} ] || {{ echo "{tag}: no {ghc}" >> {q(lines)}; exit 2; }}',
        f'rm -rf {q(wdir)}; mkdir -p {q(w)}',
        heredoc(f'{w}/ghc', wrapper(tree, label, ghc)),
        f'chmod +x {q(w + "/ghc")}',
        f'ln -s {q(f + "/ghc-pkg")} {q(w + "/ghc-pkg")}',
        f'ln -s {q(work + "/" + HSC2HS)} {q(w + "/hsc2hs")}',
        f'cd {q(n + "/nofib")} || exit 2',
        f'rm -rf {q("_make/" + res)} {q(stats)}; mkdir -p {q(stats)}',
        f'echo "{tag} start $(date +%T)" >> {q(lines)}',
        f'NB_STATS={q(stats)} setarch -R {shlex.join(argv)} > {q(log)} 2>&1;'
        ' e=$?',
        f'echo "{tag} exit $e $(date +%T): run $(find {q("_make/" + res)}'
        f' -name Main.perf.results.tsv | wc -l) benchmarks" >> {q(lines)}',
        '# the shootout inputs and outputs a run generates, 1.1 GB, which'
        ' nothing reads after it',
        f'rm -f {shootout}',
        '[ $e = 0 ] || exit 2'])


def project(work, tree, label, pkg, level):
    p = PKGS[pkg]
    g = f'{work}/ghc-{tree}/_build/stage0/bin'
    ci = '' if tree == 'f' else p.get('unless_f', '')
    head = [f'packages: {p["packages"]}{ci} {work}/{PAPIPKG}',
            f'with-compiler: {g}/ghc-{label}',
            f'with-hc-pkg: {g}/ghc-pkg',
            f'index-state: {INDEX_STATE}',
            f'allow-newer: {ALLOW_NEWER}{p["allow"]}']
    head += [p['constraints']] if p['constraints'] else []
    head += ['tests: False', 'benchmarks: True']
    stanzas = []
    for name in p['stanzas']:
        s = [f'package {name}']
        if name in p['flags']:
            s.append(f'  flags: {p["flags"][name]}')
        if level != 2:
            s.append(f'  ghc-options: -O{level}')
        if len(s) > 1:
            stanzas.append('\n'.join(s) + '\n')
    return '\n'.join(head) + '\n' + ''.join('\n' + s for s in stanzas)


def pkg_part(work, tree, label, pkg, level):
    p = PKGS[pkg]
    v = f'{work}/vpapi'
    ghc = f'{work}/ghc-{tree}/_build/stage0/bin/ghc-{label}'
    lab = f'c{tree}-{label}' if level == 2 else f'c{tree}-o{level}-{label}'
    # the -O1 builds share the -O2 store: the dependencies are built as there
    cabal = 'cabal --store-dir=' + q(f'{v}/store-c{tree}-{label}')
    opts = (f'--project-file=cabal.project.{lab} --builddir='
            + q(f'{v}/{p["builddir"]}-{lab}'))
    progs = p.get('progs') or containers_progs(work)
    out = [f'# {pkg} at -O{level}, label {lab}',
           'exec > ' + q(f'{v}/{p["log"]}-{lab}.log') + ' 2>&1',
           'echo "start $(date +%T)"',
           f'[ -x {q(ghc)} ] || {{ echo "no compiler {ghc}"; exit 2; }}',
           'cd ' + q(f'{v}/{p["src"]}') + ' || exit 2',
           heredoc(f'cabal.project.{lab}', project(work, tree, label, pkg, level)),
           f'{cabal} build -j{CABAL_J} {p["build"]} {opts}'
           f' || {{ echo "{p["log"]} {lab} build failed"; exit 2; }}',
           'echo "built $(date +%T)"', 'f=0']
    if p['resdir']:
        r = q(f'{v}/' + p['resdir'].format(lab=lab))
        out.append(f'rm -rf {r}; mkdir -p {r}')
    else:
        out.append(f'rm -f {q(v)}/' + p['csv'].format(lab=lab).replace('$i', '*'))
    pre = 'setarch -R '  # 2
    for prog in progs:
        csv = f'{q(v)}/' + p['csv'].format(lab=lab, prog=prog)
        out += [f'B=$({cabal} list-bin {p["bin"].format(prog=prog)} {opts})',
                f'for i in $(seq 1 {ROUNDS[pkg]}); do {pre}"$B" -j1 --csv {csv}'
                f' > /dev/null; e=$?; [ $e = 0 ] || {{ echo "{prog} run $i exit $e";'
                ' f=2; }; done',
                f'echo "ran {prog} $(date +%T)"']
    out += [f'echo "{p["log"]} {lab} DONE $(date +%T)"', 'exit $f']
    return '\n'.join(out)


def comp_part(work, tree, label, stage, cpu, outdir, cc=COMPILE_COST):
    ghc = f'{work}/ghc-{tree}/_build/stage{stage - 1}/bin/ghc-{label}'
    keep = f'{outdir}/p{label}' + ('' if stage == 1 else '-2')
    runs = f'{outdir}/comp{stage}-{label}.runs'
    txt = f'{outdir}/comp{stage}-{label}.txt'
    argv = ['python3', cc, '--cpu', cpu, '--tests', f'{work}/{PERF_TESTS}',
            '--cmm', f'{work}/{MBB}', '--keep-s', keep, '--out', runs,
            f'{label}={ghc}']
    return '\n'.join([
        f'# the compilations by the stage-{stage} compiler',
        f'[ -x {q(ghc)} ] || {{ echo "comp{stage} {label}: no {ghc}"; exit 2; }}',
        f'[ -e {q(runs)} ] && {{ echo "comp{stage} {label}: {runs} exists"; exit 2; }}',
        f'mkdir -p {q(outdir)}',
        f'{shlex.join(argv)} > {q(txt)} 2>&1',
        f'e=$?; echo "comp{stage} {label} exit $e:'
        f' $(grep -c \'^WARNING\' {q(txt)}) warnings"',
        '# 1 is figures printed with warnings, 2 none printed',
        '[ $e != 2 ] || exit 2'])


def cpu_list(spec):
    out = []
    for item in spec.split(','):
        a, sep, b = item.partition('-')
        if not a.isdigit() or (sep and not b.isdigit()):
            raise ValueError(f'CPUS is a taskset list: {spec!r}')
        out += [str(c) for c in range(int(a), int(b if sep else a) + 1)]
    if len(out) < 3:
        raise ValueError(f'CPUS names fewer than three CPUs: {spec!r}')
    return out


def part(name, work, tree, label, cpus, outdir, cc):
    fam, _, lev = name.partition('-O')
    if fam == 'nofib':
        body = nofib_part(work, tree, label, int(lev))
    elif fam in PKGS:
        body = pkg_part(work, tree, label, fam, int(lev))
    else:
        stage = int(name[-1])
        body = comp_part(work, tree, label, stage, cpus[stage], outdir, cc)
    return f'(\n{body}\n) || f=2'


def script(work, tree, label, cpus_spec, outdir, parts=(), cc=COMPILE_COST):
    """The bash script of the battery, or of the parts named."""
    for x in (tree, label):
        if not re.fullmatch(r'[A-Za-z0-9_.]+', x):
            raise ValueError(f'a tree or label is letters, digits, _ and .: {x!r}')
    bad = [x for x in parts if x not in PARTS]
    if bad:
        raise ValueError(f'no such part: {" ".join(bad)}; the parts are'
                         f' {" ".join(PARTS)}')
    cpus = cpu_list(cpus_spec)
    pin = f'taskset -cp {q(cpus_spec)} $BASHPID > /dev/null || exit 2'

    def p(name):
        return part(name, work, tree, label, cpus, outdir, cc)
    head = ['#!/bin/bash',
            f'# NCG-battery: tree {tree}, label {label}, CPUs {cpus_spec},'
            f' work {work}, out {outdir}', 'set -u']
    if parts:
        return '\n'.join(head + ['(', pin, 'f=0'] + [p(x) for x in parts]
                         + ['exit $f', ')']) + '\n'
    n, v, g = f'{work}/nofib-r', f'{work}/vpapi', f'{work}/ghc-{tree}/_build'
    stop = [f'{n}/nofib/_make/c{tree}-{label}', f'{n}/nofib/_make/o1-{label}',
            f'{n}/nofib/_make/o0-{label}', f'{v}/cres/c{tree}-{label}',
            f'{v}/mres/c{tree}-{label}', f'{v}/store-c{tree}-{label}',
            f'{outdir}/comp1-{label}.txt', f'{outdir}/comp1-{label}.runs',
            f'{outdir}/comp2-{label}.runs']
    logs = ' '.join(q(f'{v}/{PKGS[k]["log"]}-c{tree}{o}-{label}.log')
                    for k in PKGS for o in ('', '-o1'))
    body = [
        f'mkdir -p {q(outdir)} || exit 2',
        f'exec >> {q(f"{outdir}/meas-{label}.log")} 2>&1',
        f'echo "== measure {label} (tree {tree}) $(date +%T)"',
        f'for p in {" ".join(q(x) for x in stop)}; do',
        '  [ -e "$p" ] && { echo "meas STOP, $p exists"; exit 2; }',
        'done',
        f'cp {q(g + "/stage0/bin/ghc")} {q(f"{g}/stage0/bin/ghc-{label}")}'
        f' && cp {q(g + "/stage1/bin/ghc")} {q(f"{g}/stage1/bin/ghc-{label}")}'
        ' || { echo "meas STOP, copies failed"; exit 2; }',
        '(', pin, 'f=0', p('nofib-O2'), p('nofib-O1'), p('nofib-O0'),
        f'echo "nofib DONE {label} $(date +%T)"', 'exit $f', ') & p1=$!',
        '(', pin, 'f=0', p('containers-O2'), p('vector-O2'), p('megaparsec-O2'),
        f'echo "packages -O2 DONE {label} $(date +%T)"',
        p('containers-O1'), p('vector-O1'), p('megaparsec-O1'),
        f'echo "packages -O1 DONE {label} $(date +%T)"',
        '(', p('comp1'), 'exit $f', ') & q1=$!',
        '(', p('comp2'), 'exit $f', ') & q2=$!',
        'wait $q1 || f=2; wait $q2 || f=2',
        f'echo "comp DONE {label} $(date +%T)"', 'exit $f', ') & p2=$!',
        'wait $p1; s1=$?; wait $p2; s2=$?',
        f'grep -h "^nbf {label} exit" {q(n + "/nbf.log")} | tail -1',
        f'grep -h -E "^nbo [01] {label} exit" {q(n + "/nbo.log")} | tail -2',
        f'for f in {logs}; do tail -1 "$f"; done',
        f'echo "measured {label} $(date +%T)"',
        '[ $s1 = 0 ] && [ $s2 = 0 ] || { echo "a part failed"; exit 2; }']
    return '\n'.join(head + body) + '\n'


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    dry, work, outdir = False, WORK, None
    while argv[:1] and argv[0] in ('--dry', '--work', '--out'):
        if argv[0] == '--dry':
            dry, argv = True, argv[1:]
        elif len(argv) < 2:
            print(f'{argv[0]} needs a value', file=sys.stderr)
            return 2
        else:
            if argv[0] == '--work':
                work = argv[1]
            else:
                outdir = argv[1]
            argv = argv[2:]
    if len(argv) < 3:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    work = os.path.abspath(work)
    outdir = os.path.abspath(outdir or os.path.join(work, 'battery'))
    try:
        text = script(work, argv[0], argv[1], argv[2], outdir, argv[3:])
    except ValueError as e:
        print(f'{e}; nothing run', file=sys.stderr)
        return 2
    if dry:
        sys.stdout.write(text)
        return 0
    return subprocess.run(['bash', '-c', text, 'NCG-battery']).returncode


# --- self-test: the script run in a planted work directory, every program it
# names faked by one that records its arguments.

FAKE = r'''#!/bin/bash
me=$(basename "$0")
case $me in
  nofib-run) echo "nofib-run|$PWD|$NB_STATS|$*" >> "$FAKELOG";;
  cabal) echo "cabal|$PWD|$*" >> "$FAKELOG"
         case " $* " in *" list-bin "*) echo "$FAKEBIN/bench";; esac;;
  setarch) echo "setarch|$*" >> "$FAKELOG"; shift; exec "$@";;
  taskset) echo "taskset|$1 $2" >> "$FAKELOG"; [ "$1" = -cp ] && exit 0
           shift 2; exec "$@";;
  *) echo "$me|$*" >> "$FAKELOG"; exit "${FAKEFAIL:-0}";;
esac
'''
FAKE_CC = ('import os, sys\nopen(os.environ["FAKELOG"], "a").write('
           '"compile-cost|" + " ".join(sys.argv[1:]) + "\\n")\n')
MAKEFILE = 'TOP = ..\nSUBDIRS = ansi \\\n  minimax \\\n  fish\n\ninclude x\n'
CABAL = 'name: c\nbenchmark map-benchmarks\n  x\nbenchmark set-benchmarks\n'


def plant(d):
    w, fb = os.path.join(d, 'w'), os.path.join(d, 'bin')
    for x in (fb, f'{w}/nofib-r/nofib/spectral', f'{w}/vpapi/ctr',
              f'{w}/vpapi/src', f'{w}/vpapi/mtr',
              f'{w}/ghc-t/_build/stage0/bin', f'{w}/ghc-t/_build/stage1/bin',
              os.path.dirname(f'{w}/{NOFIB_RUN}'),
              os.path.dirname(f'{w}/{CONTAINERS_CABAL}')):
        os.makedirs(x, exist_ok=True)
    for name in ('nofib-run', 'cabal', 'setarch', 'taskset', 'bench', 'ghc'):
        path = f'{w}/{NOFIB_RUN}' if name == 'nofib-run' else f'{fb}/{name}'
        with open(path, 'w') as fh:
            fh.write(FAKE)
        os.chmod(path, 0o755)
    for s in ('stage0', 'stage1'):
        shutil.copy(f'{fb}/ghc', f'{w}/ghc-t/_build/{s}/bin/ghc')
    for rel, text in ((SPECTRAL_MAKEFILE, MAKEFILE), (CONTAINERS_CABAL, CABAL)):
        with open(f'{w}/{rel}', 'w') as fh:
            fh.write(text)
    with open(f'{d}/cc.py', 'w') as fh:
        fh.write(FAKE_CC)
    return w, fb


def self_test():
    bad = []
    with tempfile.TemporaryDirectory(prefix='ncg-battery-') as d:
        w, fb = plant(d)
        o, log = f'{d}/out', f'{d}/fake.log'
        env = dict(os.environ, PATH=fb + os.pathsep + os.environ['PATH'],
                   FAKELOG=log, FAKEBIN=fb)
        text = script(w, 't', 'x', '4-6', o, cc=f'{d}/cc.py')
        open(log, 'w').close()

        def run():
            return subprocess.run(['bash', '-c', text, 'test'], env=env,
                                  capture_output=True, text=True)
        p = run()
        with open(log) as fh:
            got = fh.read().split('\n')[:-1]
        if p.returncode != 0 or p.stderr:
            bad.append(f'the script exited {p.returncode}: {p.stderr[-300:]}')

        def of(prog):
            return [x.split('|', 1)[1] for x in got if x.startswith(prog + '|')]
        perf = '--speed=Norm --perf --perf-arg=-e --perf-arg=instructions:u'
        nb = f'{w}/nofib-r'
        want = [f'{nb}/nofib|{nb}/stats/ct-x|-j3 -w {nb}/ct/x/w/ghc -o ct-x {perf}',
                f'{nb}/nofib|{nb}/stats/o1-x|-j3 -w {nb}/co/x/w/ghc -o o1-x'
                f' --compiler-arg -O1 {perf}',
                f'{nb}/nofib|{nb}/stats/o0-x|imaginary real shootout'
                f' spectral/ansi spectral/fish -j3 -w {nb}/co/x/w/ghc -o o0-x'
                f' --compiler-arg -O0 {perf}']
        if of('nofib-run') != want:
            bad.append(f'nofib-run ran {of("nofib-run")}')
        if sum(1 for x in got if x.startswith(f'setarch|-R {w}/{NOFIB_RUN} '))\
                != 3:
            bad.append('nofib-run not under setarch -R')
        line = (f'exec perf stat -x, -e instructions:u -o "$NB_STATS/$id.csv"'
                f' -- {w}/ghc-t/_build/stage0/bin/ghc-x +RTS -A3G -V0 -RTS "$@"')
        for wr in (f'{nb}/ct/x/w/ghc', f'{nb}/co/x/w/ghc'):
            if not os.path.isfile(wr) or line not in open(wr).read().split('\n'):
                bad.append(f'{wr} lacks the line {line!r}')
        builds = [x for x in of('cabal') if ' build ' in x]
        s = f'--store-dir={w}/vpapi/store-ct-x'
        want = [f'{w}/vpapi/{src}|{s} build -j2 {t} --project-file=cabal.project.{lab}'
                f' --builddir={w}/vpapi/{bd}-{lab}'
                for o1 in ('', 'o1-')
                for src, t, bd in (('ctr', 'containers-tests:benchmarks', 'cdist'),
                                   ('src', 'vector-bench-papi:bench:algorithms-papi', 'dist'),
                                   ('mtr', 'megaparsec:bench:bench-speed', 'mdist'))
                for lab in [f'ct-{o1}x']]
        if builds != want:
            bad.append(f'cabal built {builds}')
        runs = [x for x in got if x.startswith(('setarch|', 'bench|'))
                and NOFIB_RUN not in x]
        want = []
        for o1 in ('', 'o1-'):
            for prog in ('map-benchmarks', 'set-benchmarks'):
                for i in range(1, 6):
                    c = f'-j1 --csv {w}/vpapi/cres/ct-{o1}x/{prog}-{i}.csv'
                    want += [f'setarch|-R {fb}/bench {c}', f'bench|{c}']
            for i in range(1, 6):
                c = f'-j1 --csv {w}/vpapi/res-ct-{o1}x-{i}.csv'
                want += [f'setarch|-R {fb}/bench {c}', f'bench|{c}']
            for i in range(1, 11):
                c = f'-j1 --csv {w}/vpapi/mres/ct-{o1}x/bench-speed-{i}.csv'
                want += [f'setarch|-R {fb}/bench {c}', f'bench|{c}']
        if runs != want:
            extra = [x for x in runs if x not in want][:2]
            bad.append(f'benchmark runs: {len(runs)}, not {len(want)}; first'
                       f' unexpected {extra}')
        want = [f'--cpu {c} --tests {w}/{PERF_TESTS} --cmm {w}/{MBB}'
                f' --keep-s {o}/px{k} --out {o}/comp{s}-x.runs'
                f' x={w}/ghc-t/_build/stage{s - 1}/bin/ghc-x'
                for s, c, k in ((1, 5, ''), (2, 6, '-2'))]
        if sorted(of('compile-cost')) != want:
            bad.append(f'compile-cost ran {of("compile-cost")}')
        if of('taskset') != ['-cp 4-6'] * 2:
            bad.append(f'taskset ran {of("taskset")}')
        # A whole file, an -O1 file's stanzas and megaparsec's packages.
        g = f'{w}/ghc-t/_build/stage0/bin'
        want = [('ctr/cabal.project.ct-x', str.__eq__,
                 'packages: containers/containers-tests tasty-bench-papi'
                 f' {w}/vpapi/tasty-papi-settle2\nwith-compiler: {g}/ghc-x\n'
                 f'with-hc-pkg: {g}/ghc-pkg\n'
                 'index-state: hackage.haskell.org 2026-09-19T16:13:55Z\n'
                 'allow-newer: base, ghc-prim, ghc-bignum, template-haskell,'
                 ' containers, deepseq\ntests: False\nbenchmarks: True\n'),
                ('src/cabal.project.ct-o1-x', str.endswith,
                 'benchmarks: True\n\npackage vector\n  ghc-options: -O1\n'
                 '\npackage vector-stream\n  ghc-options: -O1\n\npackage'
                 ' vector-bench-papi\n  flags: +BenchPAPI\n  ghc-options: -O1\n'),
                ('mtr/cabal.project.ct-x', str.startswith,
                 'packages: megaparsec-9.8.1 criterion-papi'
                 f' case-insensitive-1.2.1.0 {w}/vpapi/tasty-papi-settle2\n')]
        for rel, how, piece in want:
            path = f'{w}/vpapi/{rel}'
            have = open(path).read() if os.path.isfile(path) else ''
            if not how(have, piece):
                bad.append(f'{rel} is {have!r}')
        for d2 in ('ctr', 'src', 'mtr'):
            for f in os.listdir(f'{w}/vpapi/{d2}'):
                if not f.startswith('cabal.project.'):
                    continue
                t = open(f'{w}/vpapi/{d2}/{f}').read()
                if 'V0' in t or 'rtsopts' in t:
                    bad.append(f'{d2}/{f} sets RTS options')
        for s in ('stage0', 'stage1'):
            if not os.path.isfile(f'{w}/ghc-t/_build/{s}/bin/ghc-x'):
                bad.append(f'no copy of the {s} compiler')
        open(log, 'w').close()
        p = run()
        meas = open(f'{o}/meas-x.log').read()
        if p.returncode != 2 or open(log).read() or 'meas STOP' not in meas:
            bad.append(f'a second run over the results exited {p.returncode}'
                       ' and did not stop')
        p = subprocess.run(['bash', '-c', script(w, 't', 'x', '4-6', o, ('vector-O2',)),
                            'test'], env=dict(env, FAKEFAIL='3'),
                           capture_output=True, text=True)
        if (p.returncode != 2 or 'algorithms-papi run 5 exit 3'
                not in open(f'{w}/vpapi/vb-ct-x.log').read()):
            bad.append(f'failing benchmark runs exited {p.returncode}, not 2')
        open(log, 'w').close()
        p = subprocess.run([sys.executable, os.path.abspath(__file__), '--dry',
                            '--work', w, '--out', o, 't', 'x', '4-6',
                            'nofib-O1', 'comp2'], capture_output=True, text=True)
        if (p.returncode or open(log).read()
                or '--compiler-arg -O1' not in p.stdout
                or f'{o}/comp2-x.runs' not in p.stdout or '-o ct-x' in p.stdout):
            bad.append(f'--dry of two parts: {p.returncode} {p.stderr[-200:]}')
        for args in (['t', 'x', '4-5'], ['t', 'x', '4-6', 'nofib-O3'],
                     ['t', 'x/y', '4-6']):
            with contextlib.redirect_stderr(io.StringIO()):
                rc = main(['--dry', '--work', w] + args)
            if rc != 2:
                bad.append(f'{args} did not exit 2')
    for x in bad:
        print('FAIL', x)
    print('ok   battery.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
