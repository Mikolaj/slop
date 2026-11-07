#!/usr/bin/env python3
"""The measurement battery of the NCG series, for one compiler tree under one
label: nofib at -O2, -O1 and -O0, the tasty-papi benchmarks of containers,
vector and megaparsec at -O2 and -O1, a thin sample of orthotope's A2T, the
fifteen compilations by the tree's stage-1 and stage-2 compilers, GHC's perf and
size tests, the scaling probes and the tickets' reproducers; or some of these
parts alone.

Usage: python3 tools/NCG-battery/battery.py [--dry] [--work DIR] [--out DIR]
           [--compilers GHC0|full] [--a2t-lock FILE] TREE LABEL CPUS [PART...]
       python3 tools/NCG-battery/battery.py --self-test

TREE names the work directory's ghc-TREE, whose _build/stage0/bin/ghc
is the stage-1 compiler and _build/stage1/bin/ghc the stage-2 one. CPUS
is a taskset list of three CPUs or more. With no PART, the whole battery:
it stops if any of the label's results exist, copies both compilers to ghc-LABEL
beside themselves, writes the wrapper ghcw-LABEL (setting 12), and on CPUS
builds A2T's dependencies, then the packages one after another and A2T
beside them, with only the probes and then the tickets' reproducers beside
the builds, on its first CPU; then, all built, runs six lanes at once:
containers' rounds at -O2; containers' at -O1; vector's at -O2, then at -O1; megaparsec's at -O2,
then at -O1; A2T's sample; and nofib; those ended, the compilations, the stage-1
compiler's on CPUS' second CPU beside the stage-2 compiler's on its third;
and then the perf and size tests. Its lines go to OUT/meas-LABEL.log. A PART --
nofib-O2, nofib-O1, nofib-O0, containers-O2, containers-O1, vector-O2,
vector-O1, megaparsec-O2, megaparsec-O1, a2t, comp1, comp2, perf, scale or
tickets --
runs alone, in the order given, on CPUS, with ghc-LABEL already in place
unless --compilers puts it there. A package's part may name its steps, build
or run, and a2t its steps, deps, build or run, as NAME:STEP,STEP
(containers-O2:build, a2t:deps,build): only those run, in the part's own order
whatever the order written, so that a build and its runs can go in separate
calls. --compilers full copies the tree's two compilers to ghc-LABEL beside
themselves where the copies differ, as the whole battery does;
--compilers GHC0, a path, makes both of the label's compilers GHC0, a stage-1
compiler built elsewhere: _build/stage0/bin/ghc-LABEL a copy of it, for comp1,
and _build/stage1/bin/ghc-LABEL a wrapper running it with -B over the tree's
_build/stage0/lib, so that every other part measures GHC0 with the libraries
the tree's stage-1 compiler built. GHC0 is refused with perf, which tests
the tree's own stage-2 compiler, and so with the whole battery. --a2t-lock
FILE takes a lock over A2T's builds, setting 13.
The battery is a bash script; --dry prints it, every file it generates written
out in it, and runs nothing. Run it unsandboxed. It exits 0 when every part ran
and 2 when it stopped over the tree's flavour or the label's results or a part
failed: a compiler missing, or a build, nofib-run, a benchmark run, an A2T
count, compile-cost.py, a perf or size test or a probe failing or tickets.py
measuring nothing, the part's log saying which, or hadrian rebuilding the
compiler the perf tests were to run;
compile-cost.py's warnings fail nothing, nor does a case of tickets.py's
failing, its row saying so, nor nofib-run's exit 1 over real/eff alone, some
of whose programs GHC rejects.

The work directory (--work, dist-ghcho by default) holds the trees, nofib-r
(the nofib checkout and its built nofib-run), vpapi (the packages' sources
and tasty-papi-settle2, the tasty-papi built in place of Hackage's), ghc-g's
testsuite and the ManyBasicBlocks.cmm the compilations read; OUT (--out,
WORK/battery by default) the log and the files of the compilations, the perf
tests and the probes. The layout, perf and scale apart, is that of the scripts
this replaces, so that their results stay comparable through nbcmp.py
and pkgcmp.py:

  nofib       nofib-r/nofib/_make/cTREE-LABEL, o1-LABEL and o0-LABEL, the
              compiler's figures in nofib-r/stats under the same names
  containers  vpapi/cres/cTREE-LABEL/PROGRAM-I.csv, cTREE-o1-LABEL at -O1
  vector      vpapi/res-cTREE-LABEL-I.csv, res-cTREE-o1-LABEL-I.csv at -O1
  megaparsec  vpapi/mres/cTREE-LABEL/bench-speed-I.csv, cTREE-o1-LABEL
  a2t         OUT/a2t-LABEL.tsv, a line a cell: its name, its instructions
              a call (- where none were counted), perf-per-call.py's exit
              and its bytes allocated a call (-), for a2tcmp.py; built in
              vpapi/adist-cTREE-LABEL, its log vpapi/ab-cTREE-LABEL.log
  comp        OUT/compN-LABEL.txt, compile-cost.py's table, OUT/compN-LABEL.runs,
              its --out file, and its first round's assembly in OUT/pLABEL
              (stage 1) and OUT/pLABEL-2 (stage 2)
  perf        OUT/perf-LABEL.tsv, hadrian's --summary-metrics table of both
              runs, for perfcmp.py; OUT/perf-LABEL-summary.txt and
              OUT/perf-LABEL.log and, of the size tests,
              OUT/perf-LABEL-size-summary.txt and OUT/perf-LABEL-size.log
  scale       OUT/scale-LABEL.txt, tools/NCG-scale/run.sh's lines, for
              tools/NCG-scale/report.py with the base's file first
  tickets     OUT/tix-LABEL.tsv, tickets.py's table, for tickets.py compare
  builds      each build's module dumps in its build directory and the
              wrapper's records in vpapi/wstats-BUILDDIR-cTREE-LABEL
              (BUILDDIR cdist, dist, mdist or adist), for bstats.py

The settings, each stated here and nowhere else:
1. Benchmark programs, nofib's, the packages' and A2T's, run with their own
   default RTS options and the RTS clock running, as Mikolaj ruled
   on 2026-10-30: "no -V0 in any benchmarks". The packages' ghc-options carry
   no -with-rtsopts=-V0, nothing here adds one, and perf-per-call.py gives A2T
   the caller's GHCRTS, which the battery does not set.
2. Every benchmark program runs with address-space randomisation off
   (setarch -R), with it on runs of one program having differed by tens of
   instructions: the packages' programs each, A2T's counts each, and nofib-run,
   whose compiles and programs inherit it (Mikolaj, 2026-11-03, for the series'
   rebuild; the scripts replaced ran vector's and nofib's with it on).
3. Rounds: nofib runs each program once, nofib-run's default; containers'
   and vector's benchmark programs run 5 times and megaparsec's 10,
   pkgcmp.py reading their spread; A2T counts each cell once, by
   perf-per-call.py at A2T_CALLS calls and twice as many, with no run again
   of a cell that moved, its bytes allocated a call from the RTS's statistics
   of the same runs (--alloc), which left the instructions as they were.
4. The fifteen compilations are counted by tools/compile-cost.py with its
   own defaults: its cells, its rounds and its RTS options, -A3G -V0 after
   GHC's own; `compile-cost.py compare` compares two labels' .runs files.
5. nofib's compiler wrapper passes +RTS -A3G -V0 -RTS before nofib-run's
   arguments, for the reason compile-cost.py runs under them: under GHC's
   own options (-H) the collections fall elsewhere from one run to the next
   at byte-equal allocation, and the compiler's instructions spread by 0.3%
   to 0.65%. A module whose compile allocates more than 3 GB collects again,
   which nbcmp.py's compiler collections show.
6. nofib-run at -j5 and cabal at -j8, the lanes sharing CPUS, as Mikolaj ruled
   on 2026-11-03 for the series' full rebuild: "run containers, vector
   and megaparsec each on its own lane in parallel and at the same time run
   nofib at -j5"; "give -O2 and -O1 of containers their own lanes"; "if you
   build packages when nothing runs except probes, then do `cabal -j8`". Labels
   before then ran nofib-run at -j3 and cabal at -j2, the packages in one lane.
   A2T's dependencies build at -j8 too, and A2T itself, beside the packages'
   builds, at -j4 with --semaphore, setting 11.
7. nofib and the packages are built by the stage-2 compiler with the
   libraries the stage-1 compiler built, the bootstrapped GHC (Mikolaj,
   2026-11-03), so that the compiler's figures beside the programs' are those
   of a GHC the series compiled; earlier labels' are the stage-1 compiler's.
   comp1 alone runs the stage-1 compiler, which GHC 9.12.4 compiled.
8. The perf tests run by hadrian/build -jN --freeze1 test --only-perf, N being
   how many CPUS are given, one round: the figures GHC's CI judges, under
   the RTS options the testsuite driver gives, counting allocation and residency
   and no instructions. A table at -j10 under load differed from one at -j1
   by no more than a second -j1 run did. They run after the lanes, so that they
   do not contend with the programs the lanes count.
   --only-perf leaves out the size tests of testsuite/tests/perf/size, which
   count bytes on disk, so a second such run names that directory and adds its
   rows to the same table; those needing a dynamically linked compiler are
   skipped under the flavour of setting 10. Hadrian tests the stage-2 compiler
   and rebuilds it where the tree's sources changed, so the part fails unless
   the compiler is still the copy ghc-LABEL.
9. The probes run under tools/NCG-scale/run.sh's own settings.
10. A tree is measured only in hadrian's flavour
    perf+no_profiled_libs+no_dynamic_libs, that of the trees the battery's
    results compare across, so nothing runs if its _build/flavour names another
    or none.
11. A2T is orthotope's benchmark specialisation at bcbba7e959
    of its toVectorListT checkout, archived into vpapi/a2t from the local
    checkout until the code is on a stable branch upstream, and built
    under the project file of the full A2T runs, tests and benchmarks enabled,
    into the label's store. Its dependencies build first, alone, so
    that the packages' builds find those they share, such as primitive,
    installed and build none twice (Mikolaj, 2026-11-05: "duplicate build still
    wastes time"); then A2T itself, at -j4 with cabal's --semaphore, as the full
    runs were, so that GHC compiles the benchmark's modules side by side:
    without the semaphore its three largest took 9.5 minutes one after another,
    of a build of 11.7, and with it orthotope took 5.3 at -j4, after 0.7
    for the dependencies into an empty store. Its sample, vpapi/a2t-cells.txt,
    is forced cells of small arrays whose call took 100 ns or less when the full
    runs were sized, so that each takes A2T_CALLS calls, in the full runs'
    order: the first of each view, operation and kind, then the second of each,
    to 1000 cells, which count in ten minutes on an idle CPU. Summed cells,
    which need a wrapper adding --summed, and cells sized by the full runs'
    table are left out. The lane, one count at a time, ends about when
    containers' do (Mikolaj, 2026-11-05: "a single thread, so that it ends when
    the longest of the other package benchmarks ends").
12. The packages and A2T build with -ddump-timings -ddump-to-file on the
    packages under test, a ghc-options in each one's stanza, cabal 3.18
    applying a top-level one to none of the local packages; the flags left
    vector's objects and benchmark program byte-identical (2026-11-07). They
    build by ghcw-LABEL beside ghc-LABEL, which runs each --make run, those in
    cabal's response files included, under perf stat -e instructions:u with
    the RTS's statistics (-t --machine-readable) and GHC's own RTS options
    (WRAP_RTS): under nofib's -A3G -V0 each of vector's processes took 3.1
    to 3.3 GB of heap where GHC's own options took 22 to 320 MB, too much
    for eight jobs a lane beside A2T's build, and under GHC's own two builds
    of vector differed by at most 0.46% in a process's instructions.
13. Under --a2t-lock FILE each of A2T's deps and build steps takes flock
    on FILE and then, holding it, waits until MemAvailable reaches A2T_MEM GiB
    (its kB over 1048576, read every 30 seconds), so that one A2T build, about
    25 GB, runs at a time on the machine, and never without the memory; the run
    step counts outside the lock. In the whole battery A2T's dependencies
    and its build take the lock each in its own lane.
"""

import contextlib
import fcntl
import filecmp
import glob
import io
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = '/home/mikolaj/slop/dist-ghcho'
COMPILE_COST = os.path.join(os.path.dirname(HERE), 'compile-cost.py')
SCALE_RUN = os.path.join(os.path.dirname(HERE), 'NCG-scale', 'run.sh')
PER_CALL = os.path.join(os.path.dirname(HERE), 'perf-per-call.py')
TICKETS = os.path.join(HERE, 'tickets.py')

# The settings of the docstring, by number.
ROUNDS = {'containers': 5, 'vector': 5, 'megaparsec': 10}  # 3
A2T_CALLS = 200000  # 3, 11
NOFIB_RTS = '+RTS -A3G -V0 -RTS'  # 5
# the packages' and A2T's compiler wrapper's; every module's passes timed
WRAP_RTS = ''  # 12
DUMP_FLAGS = '-ddump-timings -ddump-to-file'  # 12
NOFIB_J, CABAL_J, A2T_J = 5, 8, 4  # 6, 11
FLAVOUR = 'perf+no_profiled_libs+no_dynamic_libs'  # 10
A2T_MEM, A2T_POLL = 30, 30  # 13: GiB, seconds
MEMINFO = '/proc/meminfo'

# Under the work directory.
NOFIB_RUN = ('nofib-r/nofib/dist-newstyle/build/x86_64-linux/ghc-9.12.4/'
             'nofib-0.1.0.0/x/nofib-run/build/nofib-run/nofib-run')
PAPIPKG = 'vpapi/tasty-papi-settle2'
PERF_TESTS = 'ghc-g/testsuite/tests/perf/compiler'
SIZE_TESTS = 'testsuite/tests/perf/size'
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
A2T_SRC = 'vpapi/a2t'
A2T_CELLS = 'vpapi/a2t-cells.txt'
A2T_TARGET = 'orthotope:bench:specialisation'
# whose dependencies are the benchmark's but orthotope itself, which none
# of the packages' builds share
A2T_LIB = 'orthotope:lib:orthotope'
PARTS = ('nofib-O2', 'nofib-O1', 'nofib-O0', 'containers-O2', 'vector-O2',
         'megaparsec-O2', 'containers-O1', 'vector-O1', 'megaparsec-O1',
         'a2t', 'comp1', 'comp2', 'perf', 'scale', 'tickets')
PKG_PARTS = PARTS[3:9]
A2T_STEPS = ('deps', 'build', 'run')
# the steps a PART may name, in the order they run
STEPS = {**{x: ('build', 'run') for x in PKG_PARTS}, 'a2t': A2T_STEPS}
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


def ghcw(tree, label, ghc):
    """The packages' and A2T's compiler: ghc, each --make run under perf stat
    with the RTS's statistics where GHCW_STATS names a directory, its
    arguments, those of cabal's response files written out, beside them."""
    rts = f'+RTS {WRAP_RTS + " " if WRAP_RTS else ""}-t"$GHCW_STATS/$id.rts" --machine-readable -RTS'
    return ('#!/bin/sh\n'
            f'# ghc-{tree}\'s ghc-{label}, each --make run counted into $GHCW_STATS\n'
            'm=; for a in "$@"; do case $a in --make) m=1;;'
            ' @*) grep -qx -e --make "${a#@}" 2>/dev/null && m=1;; esac; done\n'
            f'[ -n "$m" ] && [ -n "${{GHCW_STATS:-}}" ] || exec {ghc} "$@"\n'
            'id=$$.$(date +%s%N)\n'
            '{ printf \'%s\\n\' "$PWD"; for a in "$@"; do case $a in @*) cat "${a#@}";;'
            ' *) printf \'%s\\n\' "$a";; esac; done; } > "$GHCW_STATS/$id.args"\n'
            'exec perf stat -x, -e instructions:u -o "$GHCW_STATS/$id.csv" -- '
            f'{ghc} {rts} "$@"\n')


def nofib_part(work, tree, label, level):
    n = f'{work}/nofib-r'
    f = f'{work}/ghc-{tree}/_build/stage1/bin'
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
        '# 1 with every failed target under real/eff is no failure: GHC rejects'
        ' some of its programs',
        f'd=$(grep -a "^\\* Depends on: " {q(log)})',
        '[ $e = 0 ] || { [ $e = 1 ] &&'
        ' ! printf \'%s\\n\' "$d" | grep -qv /real/eff/; } || exit 2'])


def project(work, tree, label, pkg, level):
    p = PKGS[pkg]
    g = f'{work}/ghc-{tree}/_build/stage1/bin'
    ci = '' if tree == 'f' else p.get('unless_f', '')
    head = [f'packages: {p["packages"]}{ci} {work}/{PAPIPKG}',
            f'with-compiler: {g}/ghcw-{label}',
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
        # cabal 3.18 applied a top-level ghc-options to none of the local packages
        s.append(f'  ghc-options: {f"-O{level} " if level != 2 else ""}{DUMP_FLAGS}')
        stanzas.append('\n'.join(s) + '\n')
    return '\n'.join(head) + '\n' + ''.join('\n' + s for s in stanzas)


def pkg_part(work, tree, label, pkg, level, steps=('build', 'run')):
    p = PKGS[pkg]
    v = f'{work}/vpapi'
    ghc = f'{work}/ghc-{tree}/_build/stage1/bin/ghc-{label}'
    lab = f'c{tree}-{label}' if level == 2 else f'c{tree}-o{level}-{label}'
    # the -O1 builds share the -O2 store: the dependencies are built as there
    cabal = 'cabal --store-dir=' + q(f'{v}/store-c{tree}-{label}')
    opts = (f'--project-file=cabal.project.{lab} --builddir='
            + q(f'{v}/{p["builddir"]}-{lab}'))
    progs = p.get('progs') or containers_progs(work)
    stats = q(f'{v}/wstats-{p["builddir"]}-{lab}')
    out = [f'# {pkg} at -O{level}, label {lab}',
           ('exec > ' if 'build' in steps else 'exec >> ')
           + q(f'{v}/{p["log"]}-{lab}.log') + ' 2>&1',
           'echo "start $(date +%T)"',
           f'[ -x {q(ghc)} ] || {{ echo "no compiler {ghc}"; exit 2; }}',
           'cd ' + q(f'{v}/{p["src"]}') + ' || exit 2']
    if 'build' in steps:
        out += [heredoc(f'cabal.project.{lab}', project(work, tree, label, pkg, level)),
                f'rm -rf {stats}; mkdir -p {stats}',
                f'GHCW_STATS={stats} {cabal} build -j{CABAL_J} {p["build"]} {opts}'
                f' || {{ echo "{p["log"]} {lab} build failed"; exit 2; }}',
                'echo "built $(date +%T)"']
    if 'run' not in steps:
        return '\n'.join(out)
    out.append('f=0')
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


def a2t_project(work, tree, label):
    """The full A2T runs' project file, with the battery's compiler."""
    g = f'{work}/ghc-{tree}/_build/stage1/bin'
    return '\n'.join([
        'packages: .', f'with-compiler: {g}/ghcw-{label}', f'with-hc-pkg: {g}/ghc-pkg',
        f'index-state: {INDEX_STATE}',
        'allow-newer: base, ghc-prim, ghc-bignum, template-haskell, containers',
        'constraints: hashable ==1.5.0.0', 'tests: True', 'benchmarks: True', '',
        'package data-default-class', '  ghc-options: -frebindable-known-names', '',
        'package orthotope', f'  ghc-options: {DUMP_FLAGS}', ''])


def a2t_part(work, tree, label, outdir, steps=('deps', 'build', 'run'), pc=PER_CALL):
    v = f'{work}/vpapi'
    ghc = f'{work}/ghc-{tree}/_build/stage1/bin/ghc-{label}'
    lab = f'c{tree}-{label}'
    tsv = q(f'{outdir}/a2t-{label}.tsv')
    cabal = 'cabal --store-dir=' + q(f'{v}/store-{lab}')
    opts = f'--project-file=cabal.project.{lab} --builddir=' + q(f'{v}/adist-{lab}')
    stats = q(f'{v}/wstats-adist-{lab}')
    out = [f'# A2T, label {lab}',
           ('exec > ' if 'deps' in steps else 'exec >> ') + q(f'{v}/ab-{lab}.log') + ' 2>&1',
           'echo "start $(date +%T)"',
           f'[ -x {q(ghc)} ] || {{ echo "no compiler {ghc}"; exit 2; }}',
           'cd ' + q(f'{work}/{A2T_SRC}') + ' || exit 2']
    if 'deps' in steps:
        out += [heredoc(f'cabal.project.{lab}', a2t_project(work, tree, label)),
                f'rm -rf {stats}; mkdir -p {stats}',
                f'GHCW_STATS={stats} {cabal} build -j{CABAL_J} --only-dependencies {A2T_LIB} {opts}'
                f' || {{ echo "ab {lab} dependencies failed"; exit 2; }}',
                'echo "dependencies built $(date +%T)"']
    if 'build' in steps:
        out += [f'mkdir -p {stats}',
                f'GHCW_STATS={stats} {cabal} build -j{A2T_J} --semaphore {A2T_TARGET} {opts}'
                f' || {{ echo "ab {lab} build failed"; exit 2; }}',
                'echo "built $(date +%T)"']
    if 'run' not in steps:
        return '\n'.join(out)
    return '\n'.join(out + [
        f'[ -e {tsv} ] && {{ echo "a2t {label}: {outdir}/a2t-{label}.tsv exists"; exit 2; }}',
        f'mkdir -p {q(outdir)}',
        f'B=$({cabal} list-bin {A2T_TARGET} {opts})',
        'f=0',
        'while read -r c; do',
        f'  r=$(setarch -R python3 {q(pc)} --reps 1 --alloc "$B" "$c" {A2T_CALLS} < /dev/null 2>&1);'  # 2
        ' e=$?',
        "  n=$(printf '%s\\n' \"$r\" | sed -n 's/^A instructions \\([0-9.]*\\) .*/\\1/p')",
        "  a=$(printf '%s\\n' \"$r\" | sed -n 's/^A .*  alloc \\([0-9.]*\\) .*/\\1/p')",
        f"  printf '%s\\t%s\\t%s\\t%s\\n' \"$c\" \"${{n:--}}\" $e \"${{a:--}}\" >> {tsv}",
        '  [ $e = 0 ] && [ -n "$n" ] || { echo "$c: exit $e: $r"; f=2; }',
        f'done < {q(f"{work}/{A2T_CELLS}")}',
        f'echo "ab {lab} DONE $(date +%T)"', 'exit $f'])


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


def perf_part(work, tree, label, jobs, outdir):
    t = f'{work}/ghc-{tree}'
    ghc = '_build/stage1/bin/ghc'
    base = f'{outdir}/perf-{label}'
    tsv = q(base + '.tsv')
    hadrian = (f'timeout 14400 hadrian/build -j{jobs} --flavour={FLAVOUR}'
               ' --docs=none --freeze1 test')
    return '\n'.join([
        "# GHC's perf tests by the stage-2 compiler",
        f'cd {q(t)} || exit 2',
        f'[ -x {q(f"{ghc}-{label}")} ] || {{ echo "perf {label}: no {t}/{ghc}-{label}"; exit 2; }}',
        f'[ -e {q(base + ".tsv")} ] && {{ echo "perf {label}: {base}.tsv exists"; exit 2; }}',
        f'mkdir -p {q(outdir)}',
        f'{hadrian} --only-perf'
        f' --summary={q(base + "-summary.txt")} --summary-metrics={tsv}'
        f' > {q(base + ".log")} 2>&1; e=$?',
        f'echo "perf {label} exit $e $(date +%T):'
        f' $(grep -E \'unexpected failures|expected passes\' {q(base + "-summary.txt")}'
        ' | tr -s \' \' | tr \'\\n\' \';\')"',
        '# the size tests, which --only-perf leaves out; the driver appends to the table',
        f'{hadrian} --test-root-dirs={SIZE_TESTS}'
        f' --summary={q(base + "-size-summary.txt")} --summary-metrics={tsv}'
        f' > {q(base + "-size.log")} 2>&1; e2=$?',
        f'echo "perf {label} size exit $e2 $(date +%T):'
        f' $(grep -E \'unexpected failures|expected passes\' {q(base + "-size-summary.txt")}'
        ' | tr -s \' \' | tr \'\\n\' \';\')"',
        f'cmp -s {ghc} {q(f"{ghc}-{label}")}'
        f' || {{ echo "perf {label}: hadrian rebuilt {ghc}"; exit 2; }}',
        '[ $e = 0 ] && [ $e2 = 0 ] || exit 2'])


def scale_part(work, tree, label, cpu, outdir, sc=SCALE_RUN):
    ghc = f'{work}/ghc-{tree}/_build/stage1/bin/ghc-{label}'
    out = f'{outdir}/scale-{label}.txt'
    return '\n'.join([
        '# the scaling probes by the stage-2 compiler',
        f'[ -x {q(ghc)} ] || {{ echo "scale {label}: no {ghc}"; exit 2; }}',
        f'[ -e {q(out)} ] && {{ echo "scale {label}: {out} exists"; exit 2; }}',
        f'mkdir -p {q(outdir)}',
        f'SCALECPU={cpu} bash {q(sc)} {q(out)} {q(f"{label}={ghc}")}',
        f'n=$(grep -c \'^FAILED\' {q(out)})',
        f'echo "scale {label} $(date +%T): $n failed"',
        f'[ "$n" = 0 ] && grep -q \'^scale DONE\' {q(out)} || exit 2'])


def tickets_part(work, tree, label, cpu, outdir, tk=TICKETS):
    ghc = f'{work}/ghc-{tree}/_build/stage1/bin/ghc-{label}'
    tsv = f'{outdir}/tix-{label}.tsv'
    return '\n'.join([
        "# the tickets' reproducers by the stage-2 compiler",
        f'[ -x {q(ghc)} ] || {{ echo "tickets {label}: no {ghc}"; exit 2; }}',
        f'[ -e {q(tsv)} ] && {{ echo "tickets {label}: {tsv} exists"; exit 2; }}',
        f'mkdir -p {q(outdir)}',
        f'python3 {q(tk)} run {q(ghc)} {q(tsv)} {cpu}; e=$?',
        f'echo "tickets {label} exit $e $(date +%T)"',
        '# 1 is a case failing, its row saying so, 2 nothing measured',
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


def part(name, work, tree, label, cpus, outdir, cc, sc, pc, steps=None, tk=TICKETS):
    body = part_body(name, work, tree, label, cpus, outdir, cc, sc, pc, steps, tk)
    return f'(\n{body}\n) || f=2'


def part_body(name, work, tree, label, cpus, outdir, cc, sc, pc, steps=None, tk=TICKETS):
    fam, _, lev = name.partition('-O')
    if fam == 'nofib':
        body = nofib_part(work, tree, label, int(lev))
    elif fam in PKGS:
        body = pkg_part(work, tree, label, fam, int(lev), steps or ('build', 'run'))
    elif name == 'a2t':
        body = a2t_part(work, tree, label, outdir, steps or ('deps', 'build', 'run'), pc)
    elif name == 'perf':
        body = perf_part(work, tree, label, len(cpus), outdir)
    elif name == 'scale':
        body = scale_part(work, tree, label, cpus[0], outdir, sc)
    elif name == 'tickets':
        body = tickets_part(work, tree, label, cpus[0], outdir, tk)
    else:
        stage = int(name[-1])
        body = comp_part(work, tree, label, stage, cpus[stage], outdir, cc)
    return body


def a2t_held(body, label, lock, meminfo, poll):
    """A2T's building steps holding flock on lock, the memory waited for
    with the lock held (setting 13)."""
    mem = f'awk \'/MemAvailable/{{print int($2/1048576)}}\' {q(meminfo)}'
    return '\n'.join([
        f'echo "a2t {label}: waiting for {lock} and {A2T_MEM} GiB $(date +%T)"',
        f'exec 9>> {q(lock)} && flock 9 || {{ echo "a2t {label}: no lock {lock}"; exit 2; }}',
        f'until [ "$({mem})" -ge {A2T_MEM} ]; do sleep {poll}; done',
        f'echo "a2t {label}: {lock} held, {A2T_MEM} GiB available $(date +%T)"',
        body])


def compilers(work, tree, label, ghc0):
    """--compilers: the label's two compilers put in place, the tree's own
    (full) or GHC0's, the docstring's."""
    g = f'{work}/ghc-{tree}/_build'
    c0, c1 = f'{g}/stage0/bin/ghc-{label}', f'{g}/stage1/bin/ghc-{label}'
    stop = '{ echo "battery STOP, copies failed"; exit 2; }'
    if ghc0 == 'full':
        out = [f'cmp -s {q(f"{g}/{s}/bin/ghc")} {q(c)} || cp {q(f"{g}/{s}/bin/ghc")} {q(c)}'
               f' || {stop}' for s, c in (('stage0', c0), ('stage1', c1))]
    else:
        lib = f'{g}/stage0/lib'
        out = [f'[ -x {q(ghc0)} ] || {{ echo "battery STOP, no {ghc0}"; exit 2; }}',
               f'[ -d {q(lib)} ] || {{ echo "battery STOP, no {lib}"; exit 2; }}',
               heredoc(c1 + '.new', f'#!/bin/sh\nexec {q(ghc0)} -B{q(lib)} "$@"\n'),
               f'chmod +x {q(c1 + ".new")}',
               f'if cmp -s {q(c1 + ".new")} {q(c1)}; then rm {q(c1 + ".new")};'
               f' else mv {q(c1 + ".new")} {q(c1)} || {stop}; fi',
               f'cmp -s {q(ghc0)} {q(c0)} || cp {q(ghc0)} {q(c0)} || {stop}']
    return out + [f'{q(c1)} --info | grep -E \'"Global Package DB"|"Project version"\'']


def parse_parts(parts):
    """Each PART's name and steps, None where it names none."""
    bad = [x for x in parts if x.partition(':')[0] not in PARTS]
    if bad:
        raise ValueError(f'no such part: {" ".join(bad)}; the parts are'
                         f' {" ".join(PARTS)}')
    out = []
    for x in parts:
        name, colon, rest = x.partition(':')
        steps = tuple(rest.split(',')) if colon else None
        have = STEPS.get(name, ())
        if steps is not None and (len(set(steps)) != len(steps)
                                  or any(s not in have for s in steps)):
            raise ValueError(f'{x}: ' + (f'the steps of {name} are {",".join(have)}'
                                         if have else f'{name} has no steps'))
        out.append((name, steps))
    return out


def script(work, tree, label, cpus_spec, outdir, parts=(), cc=COMPILE_COST,
           sc=SCALE_RUN, pc=PER_CALL, tk=TICKETS, ghc0=None, a2t_lock=None,
           meminfo=MEMINFO, poll=A2T_POLL):
    """The bash script of the battery, or of the parts named; ghc0 is
    --compilers', a2t_lock --a2t-lock's."""
    for x in (tree, label):
        if not re.fullmatch(r'[A-Za-z0-9_.]+', x):
            raise ValueError(f'a tree or label is letters, digits, _ and .: {x!r}')
    named = parse_parts(parts)
    if ghc0 is not None and ghc0 != 'full':
        if not os.path.isabs(ghc0):
            raise ValueError(f'--compilers is full or a path: {ghc0!r}')
        if not parts or 'perf' in [n for n, _ in named]:
            raise ValueError('--compilers GHC0 is refused with perf, which tests'
                             " the tree's own stage-2 compiler, and so with the whole battery")
    if a2t_lock is not None and not os.path.isabs(a2t_lock):
        raise ValueError(f'--a2t-lock is a path: {a2t_lock!r}')
    cpus = cpu_list(cpus_spec)
    pin = f'taskset -cp {q(cpus_spec)} $BASHPID > /dev/null || exit 2'
    flavour = f'{work}/ghc-{tree}/_build/flavour'
    flavour_ok = (f'[ "$(cat {q(flavour)} 2>/dev/null)" = {q(FLAVOUR)} ]'
                  f' || {{ echo "battery STOP, {flavour} does not name {FLAVOUR}"; exit 2; }}')

    def p(name, steps=None):
        if name != 'a2t' or a2t_lock is None:
            return part(name, work, tree, label, cpus, outdir, cc, sc, pc, steps, tk)
        steps = steps or A2T_STEPS
        held = tuple(x for x in A2T_STEPS[:2] if x in steps)
        pieces = []
        if held:
            pieces.append(a2t_held(part_body(name, work, tree, label, cpus, outdir, cc, sc, pc,
                                             held, tk), label, a2t_lock, meminfo, poll))
        if 'run' in steps:
            pieces.append(part_body(name, work, tree, label, cpus, outdir, cc, sc, pc,
                                    ('run',), tk))
        return ' && '.join(f'(\n{x}\n)' for x in pieces) + ' || f=2'
    g = f'{work}/ghc-{tree}/_build'
    wrap = [heredoc(f'{g}/stage1/bin/ghcw-{label}',
                    ghcw(tree, label, f'{g}/stage1/bin/ghc-{label}')),
            f'chmod +x {q(f"{g}/stage1/bin/ghcw-{label}")}']

    def lane(pid, done, *ps):
        return ['(', pin, 'f=0', *ps, f'echo "{done} DONE {label} $(date +%T)"',
                'exit $f', f') & {pid}=$!']
    head = ['#!/bin/bash',
            f'# NCG-battery: tree {tree}, label {label}, CPUs {cpus_spec},'
            f' work {work}, out {outdir}', 'set -u']
    if parts:
        built = [n for n, _ in named if n in PKG_PARTS or n == 'a2t']
        setup = compilers(work, tree, label, ghc0) if ghc0 is not None else []
        return '\n'.join(head + [flavour_ok] + setup + (wrap if built else [])
                         + ['(', pin, 'f=0'] + [p(n, s) for n, s in named]
                         + ['exit $f', ')']) + '\n'
    n, v = f'{work}/nofib-r', f'{work}/vpapi'
    stop = [f'{n}/nofib/_make/c{tree}-{label}', f'{n}/nofib/_make/o1-{label}',
            f'{n}/nofib/_make/o0-{label}', f'{v}/cres/c{tree}-{label}',
            f'{v}/mres/c{tree}-{label}', f'{v}/store-c{tree}-{label}',
            f'{outdir}/comp1-{label}.txt', f'{outdir}/comp1-{label}.runs',
            f'{outdir}/comp2-{label}.runs', f'{outdir}/perf-{label}.tsv',
            f'{outdir}/scale-{label}.txt', f'{outdir}/a2t-{label}.tsv',
            f'{outdir}/tix-{label}.tsv']
    logs = ' '.join([q(f'{v}/{PKGS[k]["log"]}-c{tree}{o}-{label}.log')
                     for k in PKGS for o in ('', '-o1')] + [q(f'{v}/ab-c{tree}-{label}.log')])
    build, run = ('build',), ('run',)
    body = [
        f'mkdir -p {q(outdir)} || exit 2',
        f'exec >> {q(f"{outdir}/meas-{label}.log")} 2>&1',
        f'echo "== measure {label} (tree {tree}) $(date +%T)"',
        flavour_ok,
        f'for p in {" ".join(q(x) for x in stop)}; do',
        '  [ -e "$p" ] && { echo "meas STOP, $p exists"; exit 2; }',
        'done',
        f'cp {q(g + "/stage0/bin/ghc")} {q(f"{g}/stage0/bin/ghc-{label}")}'
        f' && cp {q(g + "/stage1/bin/ghc")} {q(f"{g}/stage1/bin/ghc-{label}")}'
        ' || { echo "meas STOP, copies failed"; exit 2; }',
        *wrap,
        's=0',
        *lane('probes', 'probes', p('scale'), p('tickets')),
        *lane('a2td', "A2T's dependencies built", p('a2t', ('deps',))),
        'wait $a2td || s=2',
        *lane('built', 'packages built', *[p(x, build) for x in PKG_PARTS]),
        *lane('a2tb', 'A2T built', p('a2t', build)),
        'wait $probes || s=2; wait $built || s=2; wait $a2tb || s=2',
        *lane('c2', 'containers -O2', p('containers-O2', run)),
        *lane('c1', 'containers -O1', p('containers-O1', run)),
        *lane('vec', 'vector', p('vector-O2', run), p('vector-O1', run)),
        *lane('mega', 'megaparsec', p('megaparsec-O2', run), p('megaparsec-O1', run)),
        *lane('a2t', 'A2T', p('a2t', run)),
        *lane('nb', 'nofib', p('nofib-O2'), p('nofib-O1'), p('nofib-O0')),
        'wait $c2 || s=2; wait $c1 || s=2; wait $vec || s=2; wait $mega || s=2;'
        ' wait $a2t || s=2; wait $nb || s=2',
        '(', pin, 'f=0',
        '(', p('comp1'), 'exit $f', ') & q1=$!',
        '(', p('comp2'), 'exit $f', ') & q2=$!',
        'wait $q1 || f=2; wait $q2 || f=2',
        f'echo "comp DONE {label} $(date +%T)"', 'exit $f', ') || s=2',
        '(', pin, 'f=0', p('perf'),
        f'echo "perf DONE {label} $(date +%T)"', 'exit $f', ') || s=2',
        f'grep -h "^nbf {label} exit" {q(n + "/nbf.log")} | tail -1',
        f'grep -h -E "^nbo [01] {label} exit" {q(n + "/nbo.log")} | tail -2',
        f'for f in {logs}; do tail -1 "$f"; done',
        f'echo "measured {label} $(date +%T)"',
        '[ $s = 0 ] || { echo "a part failed"; exit 2; }']
    return '\n'.join(head + body) + '\n'


def main(argv):
    if argv == ['--self-test']:
        return run_self_test('battery.py', self_test)
    dry, work, outdir, ghc0, lock = False, WORK, None, None, None
    while argv[:1] and argv[0] in ('--dry', '--work', '--out', '--compilers', '--a2t-lock'):
        if argv[0] == '--dry':
            dry, argv = True, argv[1:]
        elif len(argv) < 2:
            print(f'{argv[0]} needs a value', file=sys.stderr)
            return 2
        else:
            if argv[0] == '--work':
                work = argv[1]
            elif argv[0] == '--out':
                outdir = argv[1]
            elif argv[0] == '--compilers':
                ghc0 = argv[1] if argv[1] == 'full' else os.path.abspath(argv[1])
            else:
                lock = os.path.abspath(argv[1])
            argv = argv[2:]
    if len(argv) < 3:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    work = os.path.abspath(work)
    outdir = os.path.abspath(outdir or os.path.join(work, 'battery'))
    try:
        text = script(work, argv[0], argv[1], argv[2], outdir, argv[3:],
                      ghc0=ghc0, a2t_lock=lock)
    except ValueError as e:
        print(f'{e}; nothing run', file=sys.stderr)
        return 2
    if dry:
        sys.stdout.write(text)
        return 0
    return subprocess.run(['bash', '-c', text, 'NCG-battery']).returncode


# --- self-test: the script run in a planted work directory, every program it
# names faked by one that records its arguments.

class Failures(list):
    """A self-test's failures, rebuild.py's too. Under SELFTEST_FIRST_FAILURE,
    which mutants.py sets for every judge, the first one ends the self-test:
    a mutant is caught by the exit alone, and the checks after it cost time."""

    class Stop(BaseException):  # past any `except Exception` of a test
        pass

    def append(self, x):
        super().append(x)
        if os.environ.get('SELFTEST_FIRST_FAILURE'):
            raise Failures.Stop(x)


def run_self_test(name, test):
    """main's --self-test: test's status, and 1 where Failures stopped it."""
    try:
        return test()
    except Failures.Stop as e:
        print('FAIL', e.args[0])
        print(f'{name} self-test stopped at its first failure')
        return 1


FAKE = r'''#!/bin/bash
me=$(basename "$0")
case $me in
  nofib-run) echo "nofib-run|$PWD|$NB_STATS|$*" >> "$FAKELOG"
             for d in ${FAKEDEPENDS:-}; do echo "* Depends on: _make/x/$d"; done
             exit "${FAKENOFIB:-0}";;
  cabal) echo "cabal|$PWD|$*" >> "$FAKELOG"
         [ -z "${FAKELOCK:-}" ] || echo "cabal-lock|$2|$(flock -n "$FAKELOCK" true && echo free || echo held)" >> "$FAKELOG"
         case " $* " in *" build "*) echo "cabal-stats|${GHCW_STATS:-}|$([ -d "${GHCW_STATS:-/nonexistent}" ] && echo dir)" >> "$FAKELOG";; esac
         case " $* " in
           *" list-bin "*) echo "$FAKEBIN/bench";;
           *" build "*) sleep "${FAKESLEEP:-0}"
                        echo "cabal-end|$PWD|$*" >> "$FAKELOG"
                        case "$*" in *only-dependencies*) exit "${FAKEA2TDEPS:-0}";;
                                     *adist-*) exit "${FAKEA2TBUILD:-0}";; esac
                        exit "${FAKECABAL:-0}";;
         esac;;
  bench) echo "bench|$*" >> "$FAKELOG"; sleep "${FAKESLEEP:-0}"
         case "$*" in *"${FAKEBENCH:-no such benchmark}"*) exit 3;; esac
         exit "${FAKEFAIL:-0}";;
  setarch) echo "setarch|$*" >> "$FAKELOG"; shift; exec "$@";;
  build) echo "build|$PWD|$*" >> "$FAKELOG"
         for a in "$@"; do case $a in
           --summary=*) echo "  1 expected passes" > "${a#*=}";;
           --summary-metrics=*) : >> "${a#*=}";;
         esac; done
         [ -z "${FAKEREBUILD:-}" ] || echo rebuilt >> _build/stage1/bin/ghc
         case " $* " in *" --test-root-dirs="*) exit "${FAKESIZE:-0}";; esac
         exit "${FAKEPERF:-0}";;
  taskset) echo "taskset|$1 $2" >> "$FAKELOG"; [ "$1" = -cp ] && exit 0
           shift 2; exec "$@";;
  *) echo "$me|$*" >> "$FAKELOG"; exit "${FAKEFAIL:-0}";;
esac
'''
FAKE_CC = ('import os, sys\nopen(os.environ["FAKELOG"], "a").write('
           '"compile-cost|" + " ".join(sys.argv[1:]) + "\\n")\n')
FAKE_SCALE = ('echo "scale|$SCALECPU|$*" >> "$FAKELOG"\n'
              '[ -z "${FAKESCALE:-}" ] || echo "FAILED x" >> "$1"\n'
              'echo "scale DONE" >> "$1"\n')
FAKE_PC = ('import os, sys, time\nopen(os.environ["FAKELOG"], "a").write('
           '"perf-per-call|" + " ".join(sys.argv[1:]) + "\\n")\n'
           'time.sleep(float(os.environ.get("FAKESLEEP", "0")))\n'
           'if os.environ.get("FAKELOCK"):\n    import fcntl\n'
           '    fh, s = open(os.environ["FAKELOCK"], "a"), "free"\n'
           '    try:\n        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)\n'
           '    except OSError:\n        s = "held"\n'
           '    open(os.environ["FAKELOG"], "a").write("pc-lock|" + s + "\\n")\n'
           'if os.environ.get("FAKEPCFAIL"):\n    sys.exit("no count")\n'
           'print(sys.argv[-2] + ", per call:")\n'
           'print("A instructions 5.0 [5.0..5.0]  cycles 3.0 [3.0..3.0]  "'
           ' + ("alloc 8.0 [8.0..8.0]  " if "--alloc" in sys.argv else "") + sys.argv[-3])\n')
FAKE_TK = ('import os, sys\nopen(os.environ["FAKELOG"], "a").write('
           '"tickets|" + " ".join(sys.argv[1:]) + "\\n")\n'
           'open(sys.argv[3], "w").write("27799 -O2\\tinner\\tsplit\\n")\n'
           'sys.exit(int(os.environ.get("FAKETK", "0")))\n')
A2T_SAMPLE = ('Dynamic/size/small/dense/boxed', 'Ranked/<*>/small/runs/Unboxed')
MAKEFILE = 'TOP = ..\nSUBDIRS = ansi \\\n  minimax \\\n  fish\n\ninclude x\n'
CABAL = 'name: c\nbenchmark map-benchmarks\n  x\nbenchmark set-benchmarks\n'


def plant(d):
    w, fb = os.path.join(d, 'w'), os.path.join(d, 'bin')
    for x in (fb, f'{w}/nofib-r/nofib/spectral', f'{w}/vpapi/ctr',
              f'{w}/vpapi/src', f'{w}/vpapi/mtr', f'{w}/{A2T_SRC}',
              f'{w}/ghc-t/_build/stage0/bin', f'{w}/ghc-t/_build/stage1/bin',
              f'{w}/ghc-t/hadrian',
              os.path.dirname(f'{w}/{NOFIB_RUN}'),
              os.path.dirname(f'{w}/{CONTAINERS_CABAL}')):
        os.makedirs(x, exist_ok=True)
    for name in ('nofib-run', 'cabal', 'setarch', 'taskset', 'bench', 'ghc', 'build', 'perf'):
        path = (f'{w}/{NOFIB_RUN}' if name == 'nofib-run'
                else f'{w}/ghc-t/hadrian/build' if name == 'build'
                else f'{fb}/{name}')
        with open(path, 'w') as fh:
            fh.write(FAKE)
        os.chmod(path, 0o755)
    for s in ('stage0', 'stage1'):
        shutil.copy(f'{fb}/ghc', f'{w}/ghc-t/_build/{s}/bin/ghc')
    for rel, text in ((SPECTRAL_MAKEFILE, MAKEFILE), (CONTAINERS_CABAL, CABAL),
                      (A2T_CELLS, ''.join(c + '\n' for c in A2T_SAMPLE))):
        with open(f'{w}/{rel}', 'w') as fh:
            fh.write(text)
    with open(f'{d}/cc.py', 'w') as fh:
        fh.write(FAKE_CC)
    with open(f'{d}/pc.py', 'w') as fh:
        fh.write(FAKE_PC)
    with open(f'{d}/tk.py', 'w') as fh:
        fh.write(FAKE_TK)
    with open(f'{d}/scale.sh', 'w') as fh:
        fh.write(FAKE_SCALE)
    with open(f'{w}/ghc-t/_build/flavour', 'w') as fh:
        fh.write(FLAVOUR + '\n')
    return w, fb


def self_test():
    bad = Failures()
    with tempfile.TemporaryDirectory(prefix='ncg-battery-') as d:
        w, fb = plant(d)
        o, log = f'{d}/out', f'{d}/fake.log'
        env = dict(os.environ, PATH=fb + os.pathsep + os.environ['PATH'],
                   FAKELOG=log, FAKEBIN=fb)
        pc, tk = f'{d}/pc.py', f'{d}/tk.py'
        text = script(w, 't', 'x', '4-6', o, cc=f'{d}/cc.py', sc=f'{d}/scale.sh', pc=pc, tk=tk)
        open(log, 'w').close()

        def run():
            return subprocess.run(['bash', '-c', text, 'test'],
                                  env=dict(env, FAKESLEEP='0.05'),
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
        want = [f'{nb}/nofib|{nb}/stats/ct-x|-j5 -w {nb}/ct/x/w/ghc -o ct-x {perf}',
                f'{nb}/nofib|{nb}/stats/o1-x|-j5 -w {nb}/co/x/w/ghc -o o1-x'
                f' --compiler-arg -O1 {perf}',
                f'{nb}/nofib|{nb}/stats/o0-x|imaginary real shootout'
                f' spectral/ansi spectral/fish -j5 -w {nb}/co/x/w/ghc -o o0-x'
                f' --compiler-arg -O0 {perf}']
        if of('nofib-run') != want:
            bad.append(f'nofib-run ran {of("nofib-run")}')
        if sum(1 for x in got if x.startswith(f'setarch|-R {w}/{NOFIB_RUN} '))\
                != 3:
            bad.append('nofib-run not under setarch -R')
        line = (f'exec perf stat -x, -e instructions:u -o "$NB_STATS/$id.csv"'
                f' -- {w}/ghc-t/_build/stage1/bin/ghc-x +RTS -A3G -V0 -RTS "$@"')
        for wr in (f'{nb}/ct/x/w/ghc', f'{nb}/co/x/w/ghc'):
            if not os.path.isfile(wr) or line not in open(wr).read().split('\n'):
                bad.append(f'{wr} lacks the line {line!r}')
        builds = [x for x in of('cabal') if ' build ' in x]
        s = f'--store-dir={w}/vpapi/store-ct-x'
        want = [f'{w}/vpapi/{src}|{s} build -j8 {t} --project-file=cabal.project.{lab}'
                f' --builddir={w}/vpapi/{bd}-{lab}'
                for o1 in ('', 'o1-')
                for src, t, bd in (('ctr', 'containers-tests:benchmarks', 'cdist'),
                                   ('src', 'vector-bench-papi:bench:algorithms-papi', 'dist'),
                                   ('mtr', 'megaparsec:bench:bench-speed', 'mdist'))
                for lab in [f'ct-{o1}x']]
        a2t_opts = f'--project-file=cabal.project.ct-x --builddir={w}/vpapi/adist-ct-x'
        a2td = f'{w}/{A2T_SRC}|{s} build -j8 --only-dependencies {A2T_LIB} {a2t_opts}'
        a2tb = f'{w}/{A2T_SRC}|{s} build -j4 --semaphore {A2T_TARGET} {a2t_opts}'
        if ([x for x in builds if x not in (a2td, a2tb)] != want or builds[:1] != [a2td]
                or builds.count(a2td) != 1 or builds.count(a2tb) != 1):
            bad.append(f'cabal built {builds}')
        want = [f'--reps 1 --alloc {fb}/bench {c} {A2T_CALLS}' for c in A2T_SAMPLE]
        if of('perf-per-call') != want or of('setarch').count(f'-R python3 {pc} {want[0]}') != 1:
            bad.append(f'A2T counted {of("perf-per-call")}')
        tsv = f'{o}/a2t-x.tsv'
        have = open(tsv).read() if os.path.isfile(tsv) else ''
        if have != ''.join(f'{c}\t5.0\t0\t8.0\n' for c in A2T_SAMPLE):
            bad.append(f'a2t-x.tsv is {have!r}')
        runs = [x for x in got if x.startswith(('setarch|', 'bench|'))
                and NOFIB_RUN not in x and pc not in x]
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
        if sorted(runs) != sorted(want):
            extra = [x for x in runs if x not in want][:2]
            bad.append(f'benchmark runs: {len(runs)}, not {len(want)}; first'
                       f' unexpected {extra}')
        want = [f'--cpu {c} --tests {w}/{PERF_TESTS} --cmm {w}/{MBB}'
                f' --keep-s {o}/px{k} --out {o}/comp{s}-x.runs'
                f' x={w}/ghc-t/_build/stage{s - 1}/bin/ghc-x'
                for s, c, k in ((1, 5, ''), (2, 6, '-2'))]
        if sorted(of('compile-cost')) != want:
            bad.append(f'compile-cost ran {of("compile-cost")}')
        if of('taskset') != ['-cp 4-6'] * 12:
            bad.append(f'taskset ran {of("taskset")}')
        for k, lv in (('vb', ''), ('vb', 'o1-'), ('mb', ''), ('mb', 'o1-'),
                      ('cb', ''), ('cb', 'o1-'), ('ab', '')):
            t = open(f'{w}/vpapi/{k}-ct-{lv}x.log').read()
            if 'built' not in t or 'DONE' not in t or (k == 'ab' and 'dependencies built' not in t):
                bad.append(f'the log {k}-ct-{lv}x.log is {t!r}')
        hadrian = f'{w}/ghc-t|-j3 --flavour={FLAVOUR} --docs=none --freeze1 test'
        want = [f'{hadrian} --only-perf --summary={o}/perf-x-summary.txt'
                f' --summary-metrics={o}/perf-x.tsv',
                f'{hadrian} --test-root-dirs={SIZE_TESTS}'
                f' --summary={o}/perf-x-size-summary.txt'
                f' --summary-metrics={o}/perf-x.tsv']
        if of('build') != want:
            bad.append(f'hadrian ran {of("build")}')
        want = [f'4|{o}/scale-x.txt x={w}/ghc-t/_build/stage1/bin/ghc-x']
        if of('scale') != want:
            bad.append(f'the probes ran {of("scale")}')
        g1 = f'{w}/ghc-t/_build/stage1/bin'
        if of('tickets') != [f'run {g1}/ghc-x {o}/tix-x.tsv 4']:
            bad.append(f'the tickets ran {of("tickets")}')
        # Every build counted by the wrapper into a directory of its own.
        want = sorted({f'{w}/vpapi/wstats-{bd}-{lab}|dir' for bd in ('cdist', 'dist', 'mdist')
                       for lab in ('ct-x', 'ct-o1-x')} | {f'{w}/vpapi/wstats-adist-ct-x|dir'})
        if sorted(set(of('cabal-stats'))) != want or len(of('cabal-stats')) != 8:
            bad.append(f'the builds counted into {sorted(set(of("cabal-stats")))}')
        line = (f'exec perf stat -x, -e instructions:u -o "$GHCW_STATS/$id.csv" -- {g1}/ghc-x'
                ' +RTS -t"$GHCW_STATS/$id.rts" --machine-readable -RTS "$@"')
        wr = f'{g1}/ghcw-x'
        if not os.access(wr, os.X_OK) or line not in open(wr).read().split('\n'):
            bad.append(f'{wr} lacks the line {line!r}')
        else:
            # A --make run is counted, any other runs the compiler alone.
            sd = f'{d}/ws'
            os.makedirs(sd)
            rsp = f'{d}/a.rsp'
            with open(rsp, 'w') as fh:
                fh.write('-O\n--make\n-this-unit-id\nu-1\n')
            for argv, want in ((['--make', '-c', 'M.hs'], f'perf|stat -x, -e instructions:u -o {sd}/'),
                               ([f'@{rsp}'], f'perf|stat -x, -e instructions:u -o {sd}/'),
                               (['--info'], 'ghc-x|--info')):
                wlog = f'{d}/wrapper.log'
                open(wlog, 'w').close()
                subprocess.run([wr] + argv, env=dict(env, GHCW_STATS=sd, FAKELOG=wlog),
                               capture_output=True)
                had = open(wlog).read()
                args = sorted(glob.glob(f'{sd}/*.args'))
                if not had.startswith(want) or (argv[0] == '--make' and (
                        '-RTS --make -c M.hs' not in had or len(args) != 1)) or (
                        argv[0].startswith('@') and (len(args) != 2 or sorted(
                            open(a).read() for a in args)[-1]
                            != f'{os.getcwd()}\n-O\n--make\n-this-unit-id\nu-1\n')):
                    bad.append(f'the wrapper on {argv}: {had!r}')
        # A whole file, an -O1 file's stanzas and megaparsec's packages.
        g = f'{w}/ghc-t/_build/stage1/bin'
        want = [('ctr/cabal.project.ct-x', str.__eq__,
                 'packages: containers/containers-tests tasty-bench-papi'
                 f' {w}/vpapi/tasty-papi-settle2\nwith-compiler: {g}/ghcw-x\n'
                 f'with-hc-pkg: {g}/ghc-pkg\n'
                 'index-state: hackage.haskell.org 2026-09-19T16:13:55Z\n'
                 'allow-newer: base, ghc-prim, ghc-bignum, template-haskell,'
                 ' containers, deepseq\ntests: False\nbenchmarks: True\n\n'
                 'package containers-tests\n  ghc-options: -ddump-timings -ddump-to-file\n'),
                ('src/cabal.project.ct-o1-x', str.endswith,
                 'benchmarks: True\n\npackage vector\n  ghc-options: -O1 -ddump-timings'
                 ' -ddump-to-file\n\npackage vector-stream\n  ghc-options: -O1 -ddump-timings'
                 ' -ddump-to-file\n\npackage vector-bench-papi\n  flags: +BenchPAPI\n'
                 '  ghc-options: -O1 -ddump-timings -ddump-to-file\n'),
                ('mtr/cabal.project.ct-x', str.startswith,
                 'packages: megaparsec-9.8.1 criterion-papi'
                 f' case-insensitive-1.2.1.0 {w}/vpapi/tasty-papi-settle2\n'),
                ('a2t/cabal.project.ct-x', str.startswith,
                 f'packages: .\nwith-compiler: {g}/ghcw-x\nwith-hc-pkg: {g}/ghc-pkg\n'),
                ('a2t/cabal.project.ct-x', str.endswith,
                 '\npackage orthotope\n  ghc-options: -ddump-timings -ddump-to-file\n')]
        for rel, how, piece in want:
            path = f'{w}/vpapi/{rel}'
            have = open(path).read() if os.path.isfile(path) else ''
            if not how(have, piece):
                bad.append(f'{rel} is {have!r}')
        for d2 in ('ctr', 'src', 'mtr', 'a2t'):
            for f in os.listdir(f'{w}/vpapi/{d2}'):
                if not f.startswith('cabal.project.'):
                    continue
                t = open(f'{w}/vpapi/{d2}/{f}').read()
                if 'V0' in t or 'rtsopts' in t:
                    bad.append(f'{d2}/{f} sets RTS options')
        for s in ('stage0', 'stage1'):
            if not os.path.isfile(f'{w}/ghc-t/_build/{s}/bin/ghc-x'):
                bad.append(f'no copy of the {s} compiler')
        log0 = f'{d}/fake-first.log'
        shutil.copy(log, log0)
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
        # A2T alone over its earlier results refuses, after building.
        p = subprocess.run(['bash', '-c', script(w, 't', 'x', '4-6', o, ('a2t',), pc=pc), 'test'],
                           env=env, capture_output=True, text=True)
        if (p.returncode != 2 or 'a2t-x.tsv exists'
                not in open(f'{w}/vpapi/ab-ct-x.log').read()):
            bad.append(f'A2T over its results exited {p.returncode}, not 2')
        # A perf test failing, a size test failing, a compiler rebuilt, a probe
        # failing and earlier results each fail their part.
        for name, extra, word in (('perf', {'FAKEPERF': '1'}, 'perf x exit 1'),
                                  ('perf', {'FAKESIZE': '1'}, 'perf x size exit 1'),
                                  ('perf', {'FAKEREBUILD': '1'}, 'hadrian rebuilt'),
                                  ('perf', {}, 'perf-x.tsv exists'),
                                  ('scale', {'FAKESCALE': '1'}, 'scale x'),
                                  ('scale', {}, 'scale-x.txt exists')):
            o2 = f'{d}/out-{name}-{"-".join(extra) or "again"}'
            os.makedirs(o2)
            for f in ('perf-x.tsv', 'scale-x.txt'):
                if not extra:
                    shutil.copy(f'{o}/{f}', f'{o2}/{f}')
            p = subprocess.run(['bash', '-c', script(w, 't', 'x', '4-6', o2, (name,),
                                                     sc=f'{d}/scale.sh'), 'test'],
                               env=dict(env, **extra), capture_output=True, text=True)
            if p.returncode != 2 or word not in p.stdout:
                bad.append(f'{name} under {extra}: exited {p.returncode}:'
                           f' {p.stdout[-200:]}')
            shutil.copy(f'{w}/ghc-t/_build/stage1/bin/ghc-x',
                        f'{w}/ghc-t/_build/stage1/bin/ghc')
        # A tree in another flavour, or naming none, measures nothing, whether
        # by the whole battery or by a part.
        flav = f'{w}/ghc-t/_build/flavour'
        for content in ('perf\n', FLAVOUR + '+x\n', None):
            if content is None:
                os.unlink(flav)
            else:
                with open(flav, 'w') as fh:
                    fh.write(content)
            for parts in ((), ('nofib-O2',), ('perf',), ('scale',)):
                o4 = f'{d}/out-flavour'
                shutil.rmtree(o4, ignore_errors=True)
                open(log, 'w').close()
                p = subprocess.run(['bash', '-c', script(w, 't', 'z', '4-6', o4, parts,
                                                         cc=f'{d}/cc.py', sc=f'{d}/scale.sh'),
                                    'test'], env=env, capture_output=True, text=True)
                meas = f'{o4}/meas-z.log'
                said = p.stdout + (open(meas).read() if os.path.isfile(meas) else '')
                if (p.returncode != 2 or open(log).read() or 'battery STOP' not in said
                        or os.path.exists(f'{w}/ghc-t/_build/stage1/bin/ghc-z')):
                    bad.append(f'flavour {content!r}, parts {parts}: exited'
                               f' {p.returncode}, ran {open(log).read()[:80]!r}')
        with open(flav, 'w') as fh:
            fh.write(FLAVOUR + '\n')
        # The perf tests start when the lanes have ended.
        lines = open(log0).read().split('\n')
        last = max(i for i, x in enumerate(lines)
                   if x and not x.startswith(('build|', 'taskset|')))
        if not any(x.startswith('build|') for x in lines[last:]) or any(
                x.startswith('build|') for x in lines[:last]):
            bad.append('the perf tests overlap the lanes')

        # A2T's dependencies are built first, then the packages and A2T beside
        # each other, the probes alone beside the builds; the six lanes overlap,
        # a lane's levels go in order, and the compilations follow the lanes.
        def at(*pieces):
            return [i for i, x in enumerate(lines)
                    if all(piece in x for piece in pieces)]
        built, rounds = at('cabal|', ' build '), at('bench|') + at('perf-per-call|')
        nofib, comp, scale = at('nofib-run|'), at('compile-cost|'), at('scale|')
        a2t = at('perf-per-call|')
        c2, c1 = at('bench|', 'cres/ct-x/'), at('bench|', 'cres/ct-o1-x/')
        v2, v1 = at('bench|', 'res-ct-x-'), at('bench|', 'res-ct-o1-x-')
        m2, m1 = at('bench|', 'mres/ct-x/'), at('bench|', 'mres/ct-o1-x/')
        if not max(built) < min(rounds + nofib):
            bad.append('a lane started before the packages were built')
        if not max(scale) < max(built):
            bad.append('the probes did not run beside the builds')
        ad = at('cabal-end|', '--only-dependencies')
        ab = [i for i in built if '--semaphore' in lines[i]]
        pk = [i for i in built if '--semaphore' not in lines[i]
              and '--only-dependencies' not in lines[i]]
        if not ad or not ad[-1] < min(pk + ab):
            bad.append("A2T's dependencies were not built before the other builds")
        if not ab or not ab[0] < max(pk):
            bad.append("A2T's build did not run beside the packages'")
        for name, begin, end in (('containers -O1', c1, c2), ('containers -O2', c2, c1),
                                 ('vector', v2, c2), ('megaparsec', m2, c2),
                                 ('A2T', a2t, c2), ('nofib', nofib, c2)):
            if not min(begin) < max(end):
                bad.append(f'{name} does not overlap the containers lane beside it')
        if not (max(v2) < min(v1) and max(m2) < min(m1)):
            bad.append("vector's or megaparsec's levels out of order")
        if not max(rounds + nofib) < min(comp):
            bad.append('the compilations overlap the lanes')
        # A failure in any lane or the perf tests fails the whole battery.
        for lab, what, value in (('y', 'FAKEPERF', '1'), ('z', 'FAKESCALE', '1'),
                                 ('u', 'FAKECABAL', '1'), ('v', 'FAKENOFIB', '3'),
                                 ('a', 'FAKEBENCH', 'cres/ct-a/'),
                                 ('b', 'FAKEBENCH', 'cres/ct-o1-b/'),
                                 ('c', 'FAKEBENCH', 'res-ct-o1-c-'),
                                 ('e', 'FAKEBENCH', 'mres/ct-o1-e/'),
                                 ('g', 'FAKEPCFAIL', '1'), ('h', 'FAKEA2TBUILD', '1'),
                                 ('i', 'FAKEA2TDEPS', '1'), ('j', 'FAKETK', '2')):
            o3 = f'{d}/out-whole-{lab}'
            p = subprocess.run(['bash', '-c', script(w, 't', lab, '4-6', o3, cc=f'{d}/cc.py',
                                                     sc=f'{d}/scale.sh', pc=pc, tk=tk), 'test'],
                               env=dict(env, **{what: value}), capture_output=True, text=True)
            if p.returncode != 2 or 'a part failed' not in open(f'{o3}/meas-{lab}.log').read():
                bad.append(f'{what}={value} in the whole battery: {p.returncode}')
        # nofib-run's exit 1 over real/eff alone is no failure, and any other is.
        for code, deps, want in (('1', 'real/eff/FS/EffBench.o', 0),
                                 ('1', 'real/eff/FS/Main spectral/simple/Main', 2),
                                 ('1', 'spectral/simple/Main', 2),
                                 ('1', '', 2),
                                 ('3', 'real/eff/FS/Main', 2)):
            p = subprocess.run(['bash', '-c', script(w, 't', 'x', '4-6', o, ('nofib-O1',)),
                                'test'], env=dict(env, FAKENOFIB=code, FAKEDEPENDS=deps),
                               capture_output=True, text=True)
            if p.returncode != want:
                bad.append(f'nofib-run exit {code} over {deps!r}: exited'
                           f' {p.returncode}, not {want}')

        def ran(prog):
            with open(log) as fh:
                return [x.split('|', 1)[1] for x in fh.read().split('\n')
                        if x.startswith(prog + '|')]

        def go(lab, out, parts, extra=None, **kw):
            open(log, 'w').close()
            return subprocess.run(['bash', '-c', script(w, 't', lab, '4-6', out, parts,
                                                        sc=f'{d}/scale.sh', pc=pc, **kw), 'test'],
                                  env=dict(env, **(extra or {})), capture_output=True, text=True)
        # A part's steps: only those named run, in the part's order.
        for k, (parts, want) in enumerate(((('containers-O2:build',), (1, 0, 0)),
                                           (('vector-O1:run',), (0, 5, 0)),
                                           (('a2t:build,deps',), (2, 0, 0)),
                                           (('a2t:run',), (0, 0, 2)))):
            p = go('x', f'{d}/out-steps-{k}', parts)
            builds = [x for x in ran('cabal') if ' build ' in x]
            have = (len(builds), len(ran('bench')), len(ran('perf-per-call')))
            if p.returncode or have != want or (k == 2 and '--only-dependencies' not in builds[0]):
                bad.append(f'{parts}: exited {p.returncode}, builds, runs and counts {have}')
        # --compilers GHC0: stage 1 a copy, stage 2 a wrapper running it with -B,
        # each written only where it differs; a missing GHC0 or library stops.
        g0, g1 = f'{w}/ghc-t/_build/stage0/bin', f'{w}/ghc-t/_build/stage1/bin'
        ghc0, lib = f'{d}/ghc0', f'{w}/ghc-t/_build/stage0/lib'
        shutil.copy(f'{fb}/ghc', ghc0)
        for ghc, why in ((f'{d}/nonexistent', 'no ' + f'{d}/nonexistent'), (ghc0, 'no ' + lib)):
            p = go('k', f'{d}/out-k0', ('scale',), ghc0=ghc)
            if p.returncode != 2 or why not in p.stdout or ran('scale'):
                bad.append(f'--compilers {ghc} without {why[3:]}: exited {p.returncode}')
        os.makedirs(lib)
        for k in (1, 2):
            p = go('k', f'{d}/out-k{k}', ('scale',), ghc0=ghc0)
            c0, c1 = f'{g0}/ghc-k', f'{g1}/ghc-k'
            have = open(c1).read() if os.path.isfile(c1) else ''
            if (p.returncode or have != f'#!/bin/sh\nexec {ghc0} -B{lib} "$@"\n'
                    or not os.access(c1, os.X_OK) or not filecmp.cmp(ghc0, c0, shallow=False)
                    or ran('ghc0') != [f'-B{lib} --info']
                    or ran('scale') != [f'4|{d}/out-k{k}/scale-k.txt k={c1}']
                    or (k == 2 and {os.stat(c).st_mtime for c in (c0, c1)} != {1e9})):
                bad.append(f'--compilers GHC0, run {k}: exited {p.returncode}, wrapper {have!r},'
                           f' ran {ran("ghc0")} {ran("scale")}')
            for c in (c0, c1):
                os.utime(c, (1e9, 1e9))
        # --compilers full: the tree's own, copied where they differ.
        for k in (1, 2):
            p = go('m', f'{d}/out-m{k}', ('scale',), ghc0='full')
            cs = [(f'{g}/ghc', f'{g}/ghc-m') for g in (g0, g1)]
            if (p.returncode or not all(os.path.isfile(c) and filecmp.cmp(a, c, shallow=False)
                                        for a, c in cs)
                    or (k == 2 and {os.stat(c).st_mtime for _, c in cs} != {1e9})):
                bad.append(f'--compilers full, run {k}: exited {p.returncode}')
            for _, c in cs:
                if os.path.isfile(c):
                    os.utime(c, (1e9, 1e9))
        if script(w, 't', 'x', '4-6', o, ghc0='full') != script(w, 't', 'x', '4-6', o):
            bad.append('--compilers full changes the whole battery')
        # --a2t-lock: A2T's builds hold the lock and its count does not;
        # the builds wait for the memory with the lock held.
        lock, mi = f'{d}/a2t.lock', f'{d}/meminfo'

        def mem(kb):
            with open(mi, 'w') as fh:
                fh.write(f'MemTotal: 1 kB\nMemAvailable: {kb} kB\n')
        mem(A2T_MEM * 1048576)
        locked = dict(ghc0='full', a2t_lock=lock, meminfo=mi, poll=0.05)
        p = go('l', f'{d}/out-l', ('a2t',), {'FAKELOCK': lock}, **locked)
        if (p.returncode or ran('cabal-lock') != ['build|held', 'build|held', 'list-bin|free']
                or ran('pc-lock') != ['free', 'free']):
            bad.append(f'--a2t-lock: exited {p.returncode}, cabal {ran("cabal-lock")},'
                       f' counts {ran("pc-lock")}')
        mem(A2T_MEM * 1048576 - 1)
        open(log, 'w').close()
        bg = subprocess.Popen(['bash', '-c', script(w, 't', 'l2', '4-6', f'{d}/out-l2', ('a2t',),
                                                    pc=pc, **locked), 'test'],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=True)
        held, t0 = False, time.time()
        while not held and time.time() < t0 + 5:
            with open(lock, 'a') as fh:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    held = True
            time.sleep(0.05)
        time.sleep(0.3)
        early = [x for x in ran('cabal') if ' build ' in x]
        mem(A2T_MEM * 1048576)
        try:
            bg.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(bg.pid, signal.SIGKILL)
            bg.wait()
        if (not held or early or bg.returncode
                or len([x for x in ran('cabal') if ' build ' in x]) != 2):
            bad.append(f'--a2t-lock short of memory: lock held {held}, built early {early[:1]},'
                       f' exited {bg.returncode}')
        if script(w, 't', 'x', '4-6', o, a2t_lock=lock).count(f'exec 9>> {lock} && flock 9') != 2:
            bad.append('--a2t-lock not over both of the whole battery\'s A2T builds')
        open(log, 'w').close()
        p = subprocess.run([sys.executable, os.path.abspath(__file__), '--dry',
                            '--work', w, '--out', o, 't', 'x', '4-6',
                            'nofib-O1', 'comp2'], capture_output=True, text=True)
        if (p.returncode or open(log).read()
                or '--compiler-arg -O1' not in p.stdout
                or f'{o}/comp2-x.runs' not in p.stdout or '-o ct-x' in p.stdout):
            bad.append(f'--dry of two parts: {p.returncode} {p.stderr[-200:]}')
        # Relative paths made absolute.
        here = os.getcwd()
        try:
            os.chdir(d)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = main(['--dry', '--work', w, '--compilers', 'ghc0', '--a2t-lock', 'a2t.lock',
                           't', 'x', '4-6', 'a2t:deps'])
        finally:
            os.chdir(here)
        if rc or f'exec {ghc0} -B' not in out.getvalue() or f'9>> {lock} ' not in out.getvalue():
            bad.append(f'--dry with relative --compilers and --a2t-lock: {rc}')
        for args in (['t', 'x', '4-5'], ['t', 'x', '4-6', 'nofib-O3'],
                     ['t', 'x/y', '4-6'], ['t', 'x', '4-6', 'nofib-O2:build'],
                     ['t', 'x', '4-6', 'a2t:count'], ['t', 'x', '4-6', 'a2t:'],
                     ['t', 'x', '4-6', 'containers-O2:deps'], ['t', 'x', '4-6', 'a2t:run,run'],
                     ['--compilers', ghc0, 't', 'x', '4-6', 'comp1', 'perf'],
                     ['--compilers', ghc0, 't', 'x', '4-6']):
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
