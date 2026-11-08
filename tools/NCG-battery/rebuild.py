#!/usr/bin/env python3
"""The NCG series' full rebuild: the base and each commit above it, one after
another, each built from nothing in a tree of its own and then measured by
battery.py with the machine to itself (Mikolaj, 2026-11-03: "you sequentially
build and benchmark each commit in turn").

Usage: python3 tools/NCG-battery/rebuild.py [--dry] [--pair] [--work DIR] BASE TIP CPUS
       python3 tools/NCG-battery/rebuild.py --build [--patch P]... [--target T]
           [--setting L]... [--logs DIR] [--max-wait S] [--work DIR] TREE COMMIT CPUS
       python3 tools/NCG-battery/rebuild.py --self-test

BASE and TIP name commits of ~/slop/ghc and CPUS is a taskset list, to which
the whole run is pinned, hadrian's -j being how many CPUs it names. The base is
label fr00, the Nth commit above it frNN, tree and label alike: `nbcmp.py
cfr00-fr00 cfr01-fr01`, `o1-fr00 o1-fr01` at -O1. A step:

1. The tree ghc-frNN from nothing: a clone of the work directory's ghc-g, the
   commit fetched from ~/slop/ghc, the submodules from ghc-g's, nofib left out,
   ./boot, ./configure, hadrian's default target in battery.py's flavour with
   --docs=none and -V, which logs every compiler command, under perf stat,
   with HADRIAN_SETTINGS in _build/hadrian.settings, which every hadrian run
   in the tree loads; then bstats.py's table of the build, WORK/battery/
   ghcb-frNN.tsv: each module's compile time, allocation and object size,
   both stages, and the build's wall time and instructions:u. The flags
   changed no object: against a tree of the same sources built without them,
   only GHC.Version's commit id differed, and the tree's path in the RTS's C
   objects of the debug ways, which ghc.hs.opts does not reach (2026-11-07).
2. battery.py frNN frNN CPUS, the whole battery; then bstats.py's table of
   the packages' and A2T's builds, WORK/battery/pkgb-frNN.tsv.
3. What the comparison tools read kept and the rest deleted: the tree,
   the packages' and A2T's build directories, stores, project files and
   wrapper records, and every file but the tables in nofib's runs. A step
   that failed keeps all of them, to read.

The run exits once, 0 with every step measured and 2 otherwise, so a session
waiting on it in the harness's background mode wakes at its end. A failed
step is recorded and the next one starts. It stops early, with 2, only under
MIN_FREE GB free before a step or after MAX_FAILED steps failing in a row, which
no one commit explains. A build and a battery are each killed after TIMEOUT
seconds, which fails the step. Run again, it takes up from the steps not
measured, each begun again from nothing: a step counts as measured when its
LABEL.done stands and every record of 2026-11-07 exists (ghcb, pkgb and tix,
and A2T's table with its bytes allocated), so steps measured before then are
measured again; and a label whose commit is not the one steps.txt names is
measured again, its old results deleted. It refuses a base other than
steps.txt's, or a run while another holds the lock; a first run refuses if any
step's results exist. --pair builds and measures the base and the tip alone,
under the labels the chain gives them, steps.txt naming the whole chain, so
that a later run of the chain takes them up where their commits are the same.
At the end, when the base and the last label are measured, runreport.py's
report of the last label against fr00, LOGS/report-fr00-frNN.txt, which
the run's last line names. --dry prints the steps and the first step's
commands, and runs nothing. Run it unsandboxed.

WORK/battery/rebuild (LOGS) holds rebuild.log, the lines it prints; steps.txt;
for each step build-LABEL.log, boot-LABEL.log, configure-LABEL.log,
hadrian-LABEL.log.gz, hperf-LABEL.csv (perf stat's) and battery-LABEL.log;
LABEL.done or LABEL.failed, holding what the log's line says; the report.
--repo, --battery, --timeout and --min-free are the self-test's.

--build builds the one tree WORK/ghc-TREE at COMMIT by step 1's script
and measures nothing. Each P is applied by patch -p1, in the order given,
after the check that the tree is clean at COMMIT and before ./boot; T is
a hadrian target in place of the default one, such as _build/stage0/bin/ghc
for a stage-1 tree; each L is a line appended to _build/hadrian.settings
after HADRIAN_SETTINGS. It first waits until MemAvailable reaches MIN_MEM GB,
for at most S seconds where --max-wait is given, and then refuses under
MIN_FREE GB free on the work directory's disk, both exiting 9 with nothing
built; GB is 10^9 bytes in both. The build runs under taskset over CPUS,
hadrian at -j their count, with ulimit -v ULIMIT_V, its lines in
LOGS/build-TREE.log beside the script's other logs, LOGS the current
directory unless --logs names one; it prints the log's last line and exits
with the script's status. A tree named frNN, a label of the rebuild's, is
refused. --build's --repo, --min-free, --min-mem, --meminfo and --poll are
the self-test's.
"""

import fcntl
import glob
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
sys.path.insert(0, HERE)
from battery import (A2T_CELLS, A2T_SRC, CONTAINERS_CABAL, FLAVOUR, MBB,  # noqa: E402
                     NOFIB_RUN, PAPIPKG, PERF_TESTS, PKGS, SPECTRAL_MAKEFILE, WORK,
                     Failures, cpu_list, q, run_self_test)
import bstats  # noqa: E402
import runreport  # noqa: E402

REPO = os.path.join(os.path.dirname(WORK), 'ghc')
BATTERY = os.path.join(HERE, 'battery.py')
MIN_FREE = 30  # GB
MAX_FAILED = 3
TIMEOUT = 7200  # s; each takes under half an hour
# every module's passes timed, a dump a module and GHC way tag under its build
# directory, the RTS's four ways writing two (bstats.py)
HADRIAN_SETTINGS = '*.*.ghc.hs.opts += -ddump-timings -ddump-to-file'
# --build's gate and limit, common.md's
MIN_MEM = 12  # GB
ULIMIT_V = 40000000  # kB
MEMINFO = '/proc/meminfo'
POLL = 20  # s between readings of MEMINFO


def git(repo, *args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True)


def steps_of(repo, base, tip):
    """The labels and full hashes, the base's first, resolved now."""
    def rev(x):
        p = git(repo, 'rev-parse', '--verify', x + '^{commit}')
        if p.returncode:
            raise ValueError(f'no commit {x} in {repo}')
        return p.stdout.strip()
    b, t = rev(base), rev(tip)
    if git(repo, 'merge-base', '--is-ancestor', b, t).returncode:
        raise ValueError(f'{base} is not an ancestor of {tip}')
    ups = git(repo, 'rev-list', '--reverse', f'{b}..{t}').stdout.split()
    if not ups:
        raise ValueError(f'no commit between {base} and {tip}')
    return [(f'fr{i:02d}', h) for i, h in enumerate([b] + ups)]


def build_script(work, repo, logs, tree, commit, jobs, patches=(), target=None, settings=()):
    """The build of ghc-TREE at COMMIT, step 1; the patches, the target and
    the settings lines are --build's."""
    t, g = f'{work}/ghc-{tree}', f'{work}/ghc-g'
    tgt = f' {q(target)}' if target else ''
    stamp, hlog = f'{logs}/stamp-{tree}', f'{logs}/hadrian-{tree}.log'
    hperf = f'{logs}/hperf-{tree}.csv'
    return '\n'.join([
        'set -u',
        f'echo "start {tree} $(date +%T)"',
        f'[ -e {q(t)} ] && {{ echo "tree STOP {tree}, {t} exists"; exit 1; }}',
        f'git clone -q --no-checkout {q(g)} {q(t)}'
        f' || {{ echo "tree STOP {tree}, clone failed"; exit 2; }}',
        f'cd {q(t)} || exit 2',
        f'git fetch -q {q(repo)} {commit} && git checkout -q --detach {commit}'
        f' || {{ echo "tree STOP {tree}, checkout failed"; exit 2; }}',
        "git config -f .gitmodules --get-regexp '^submodule\\..*\\.path$' | while read -r k p; do",
        '  n=${k#submodule.}; n=${n%.path}',
        '  [ "$p" = nofib ] && continue',
        f'  git config submodule.$n.url {q(g)}/.git/modules/$n',
        '  git -c protocol.file.allow=always submodule update -q --init -- "$p" 2>/dev/null'
        ' || echo "submodule $p failed"',
        'done',
        'git update-index -q --refresh',
        f'[ "$(git rev-parse HEAD)" = {commit} ]'
        ' && [ -z "$(git status --porcelain -uno | grep -v \' nofib$\')" ]'
        f' || {{ echo "tree STOP {tree}, not at {commit}"; exit 2; }}',
        f'echo "ghc-{tree} at $(git log -1 --format=\'%h %s\')"',
        *[f'patch -p1 --forward --batch < {q(p)}'
          f' || {{ echo {q(f"tree STOP {tree}, patch {p} failed")}; exit 2; }}' for p in patches],
        *(['echo "changed: $(git status --porcelain | grep -v \' nofib$\' | tr \'\\n\' \' \')"']
          if patches else []),
        f'./boot > {q(f"{logs}/boot-{tree}.log")} 2>&1'
        f' && ./configure > {q(f"{logs}/configure-{tree}.log")} 2>&1'
        f' || {{ echo "tree STOP {tree}, boot or configure failed"; exit 3; }}',
        # loaded by every hadrian run in the tree, the perf part's included,
        # which given other arguments would build the compiler again
        f'mkdir -p _build && echo {q(HADRIAN_SETTINGS)} > _build/hadrian.settings',
        *[f'echo {q(s)} >> _build/hadrian.settings' for s in settings],
        # mtimes on ~/slop step by 1 ms, so every object is newer than the stamp
        f'touch {q(stamp)}; sleep 0.01',
        's0=$(date +%s)',
        f'perf stat -x, -e instructions:u -o {q(hperf)} --'
        f' hadrian/build -j{jobs} -V --flavour={FLAVOUR} --docs=none{tgt} > {q(hlog)} 2>&1',
        'e=$?; s=$(( $(date +%s) - s0 ))',
        f'old=$(find _build -name \'*.o\' ! -newer {q(stamp)} | wc -l); rm -f {q(stamp)}',
        f'i=$(sed -n \'s/^\\([0-9]*\\),.*,instructions:u,.*/\\1/p\' {q(hperf)} 2>/dev/null)',
        f'echo "hadrian {tree} exit $e $(date +%T): warnings'
        f' $(grep -c \'warning:\' {q(hlog)}); objects older than the build: $old;'
        ' wall ${s} s; instructions:u ${i:--}"',
        '[ $e = 0 ] || exit 4',
        '[ "$old" = 0 ] || exit 5'])


def label_paths(work, label):
    """Every path a step of this label makes, but its lines in logs other runs share."""
    v, n, out = f'{work}/vpapi', f'{work}/nofib-r', f'{work}/battery'
    c, o1 = f'c{label}-{label}', f'c{label}-o1-{label}'
    ps = [f'{work}/ghc-{label}', f'{n}/c{label}', f'{n}/co/{label}',
          f'{n}/nbf-{label}.log', f'{n}/nbo1-{label}.log', f'{n}/nbo0-{label}.log',
          f'{v}/store-{c}', f'{v}/cres/{c}', f'{v}/cres/{o1}', f'{v}/mres/{c}', f'{v}/mres/{o1}']
    for r in (c, f'o1-{label}', f'o0-{label}'):
        ps += [f'{n}/nofib/_make/{r}', f'{n}/stats/{r}']
    for lab in (c, o1):
        for p in PKGS.values():
            ps += [f'{v}/{p["builddir"]}-{lab}', f'{v}/{p["src"]}/cabal.project.{lab}',
                   f'{v}/{p["log"]}-{lab}.log']
        ps += sorted(glob.glob(f'{v}/res-{glob.escape(lab)}-*.csv'))
    ps += [f'{v}/adist-{c}', f'{work}/{A2T_SRC}/cabal.project.{c}', f'{v}/ab-{c}.log']
    ps += [sdir for _, _, sdir in bstats.builds(work, label, label)]
    for s in (f'a2t-{label}.tsv', f'tix-{label}.tsv', f'ghcb-{label}.tsv', f'pkgb-{label}.tsv',
              f'comp1-{label}.txt', f'comp1-{label}.runs', f'comp2-{label}.txt',
              f'comp2-{label}.runs', f'perf-{label}.tsv', f'perf-{label}.log',
              f'perf-{label}-summary.txt', f'perf-{label}-size.log',
              f'perf-{label}-size-summary.txt', f'scale-{label}.txt', f'meas-{label}.log',
              f'p{label}', f'p{label}-2'):
        ps.append(f'{out}/{s}')
    return ps


def remove(p):
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p)
    elif os.path.lexists(p):
        os.unlink(p)


def prune(work, label):
    """A measured step's files that no comparison tool reads."""
    n, v = f'{work}/nofib-r', f'{work}/vpapi'
    c, o1 = f'c{label}-{label}', f'c{label}-o1-{label}'
    for r in (c, f'o1-{label}', f'o0-{label}'):
        for root, _, fs in os.walk(f'{n}/nofib/_make/{r}'):
            for f in fs:
                p = os.path.join(root, f)
                if not f.endswith('.tsv') and os.path.isfile(p) and not os.path.islink(p):
                    os.unlink(p)
    gone = [f'{work}/ghc-{label}', f'{n}/c{label}', f'{n}/co/{label}', f'{v}/store-{c}']
    for lab in (c, o1):
        for p in PKGS.values():
            gone += [f'{v}/{p["builddir"]}-{lab}', f'{v}/{p["src"]}/cabal.project.{lab}']
    gone += [f'{v}/adist-{c}', f'{work}/{A2T_SRC}/cabal.project.{c}']
    gone += [sdir for _, _, sdir in bstats.builds(work, label, label)]
    for p in gone:
        remove(p)


def unrecorded(work, label):
    """The records a measured step of this label lacks: those added on
    2026-11-07, which steps measured before then lack."""
    out = f'{work}/battery'
    miss = [f'{out}/{s}-{label}.tsv' for s in ('ghcb', 'pkgb', 'tix')
            if not os.path.exists(f'{out}/{s}-{label}.tsv')]
    a2t = f'{out}/a2t-{label}.tsv'
    with open(a2t) if os.path.exists(a2t) else open(os.devnull) as fh:
        first = fh.readline()
    if len(first.rstrip('\n').split('\t')) != 4:
        miss.append(f'{a2t}, its bytes allocated')
    return miss


def free_gb(work):
    s = os.statvfs(work)
    return s.f_bavail * s.f_frsize / 1e9


def run_logged(argv, log, timeout):
    """The status of argv, stdout and stderr in log; on the timeout its whole
    session killed, as `timeout`, which the perf part runs under, leads a group
    of its own."""
    with open(log, 'ab') as fh:
        p = subprocess.Popen(argv, stdout=fh, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            return p.wait(timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['pkill', '-KILL', '-s', str(p.pid)])
            p.send_signal(signal.SIGKILL)
            p.wait()
            return 'killed after the timeout'


def step(o, label, commit, jobs):
    """None and the line for a measured step, or what failed and the line."""
    logs, t0 = o['logs'], time.time()
    build = f'{logs}/build-{label}.log'
    st = run_logged(['bash', '-c', build_script(o['work'], o['repo'], logs, label, commit, jobs)],
                    build, o['timeout'])
    if st != 0:
        return f'build: {st}', ''
    t1 = time.time()
    with open(build) as fh:
        text = fh.read()
    m = re.search(r'warnings (\d+);', text)
    warnings = m.group(1) if m else '?'
    m = re.search(r'; wall (\d+) s;', text)
    os.makedirs(f'{o["work"]}/battery', exist_ok=True)
    bstats.write(f'{o["work"]}/battery/ghcb-{label}.tsv',
                 bstats.ghc_rows(f'{o["work"]}/ghc-{label}', f'{logs}/hperf-{label}.csv',
                                 float(m.group(1)) if m else 0))
    hlog = f'{logs}/hadrian-{label}.log'
    if os.path.exists(hlog):
        subprocess.run(['gzip', '-f', hlog])
    st = run_logged([sys.executable, o['battery'], '--work', o['work'], label, label, o['cpus']],
                    f'{logs}/battery-{label}.log', o['timeout'])
    if st != 0:
        return f'battery: {st}', ''
    t2 = time.time()
    bstats.write(f'{o["work"]}/battery/pkgb-{label}.tsv', bstats.pkg_rows(o['work'], label, label))
    prune(o['work'], label)
    return None, (f'built in {(t1 - t0) / 60:.0f} min with {warnings} warnings,'
                  f' measured in {(t2 - t1) / 60:.0f} min')


def run(o, steps):
    logs, work = o['logs'], o['work']
    os.makedirs(logs, exist_ok=True)
    lock = open(f'{logs}/lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f'rebuild STOP, another run holds {logs}/lock')
        return 2

    def say(line):
        text = f'{time.strftime("%F %T")} {line}\n'
        with open(f'{logs}/rebuild.log', 'a') as fh:
            fh.write(text)
        sys.stdout.write(text)
        sys.stdout.flush()
    listing = ''.join(f'{lab} {h}\n' for lab, h in steps)
    path = f'{logs}/steps.txt'
    changed = []
    if os.path.exists(path):
        with open(path) as fh:
            had = dict(line.split() for line in fh if line.strip())
        if had.get(steps[0][0]) != steps[0][1]:
            say(f'rebuild STOP, {path} names another base, {had.get(steps[0][0], "none")[:10]}')
            return 2
        changed = [lab for lab, h in steps if had.get(lab, h) != h]
    else:
        there = [p for lab, _ in steps for p in label_paths(work, lab) if os.path.lexists(p)]
        if there:
            say(f'rebuild STOP, {len(there)} results exist, the first {there[0]}')
            return 2
    with open(path, 'w') as fh:
        fh.write(listing)
    for lab in changed:  # its commit is another now: its results are stale
        say(f'{lab} names another commit than before, {had[lab][:10]}: measured again')
        for p in label_paths(work, lab) + [f'{logs}/{lab}.done', f'{logs}/{lab}.failed']:
            remove(p)
    os.sched_setaffinity(0, {int(c) for c in cpu_list(o['cpus'])})
    jobs = len(cpu_list(o['cpus']))
    todo = [steps[0], steps[-1]] if o.get('pair') else steps
    done, failed, row = 0, [], 0
    say(f'rebuild start: {len(todo)} of {len(steps)} steps, {steps[0][1][:10]} to {steps[-1][1][:10]},'
        f' CPUs {o["cpus"]}')
    for label, commit in todo:
        mark = f'{logs}/{label}'
        if os.path.exists(mark + '.done'):
            miss = unrecorded(work, label)
            if not miss:
                done += 1
                continue
            say(f'{label} measured without {len(miss)} records, the first {miss[0]}: measured again')
            os.unlink(mark + '.done')
        free = free_gb(work)
        if free < o['min_free']:
            say(f'rebuild STOP, {free:.0f} GB free before {label}, under {o["min_free"]}')
            return 2
        say(f'{label} {commit[:10]} {git(o["repo"], "log", "-1", "--format=%s", commit).stdout.strip()}')
        try:
            for p in label_paths(work, label) + [mark + '.failed']:
                remove(p)
            bad, line = step(o, label, commit, jobs)
        except Exception as e:  # recorded like any failed step
            bad, line = f'{type(e).__name__}: {e}', ''
        line = f'{label} FAILED, {bad}' if bad else f'{label} done, {line}, {free_gb(work):.0f} GB free'
        with open(mark + ('.failed' if bad else '.done'), 'w') as fh:
            fh.write(line + '\n')
        say(line)
        if bad:
            failed.append(label)
            row += 1
            if row >= MAX_FAILED:
                say(f'rebuild STOP, {row} steps failed in a row')
                return 2
        else:
            done += 1
            row = 0
    a, b = steps[0][0], steps[-1][0]
    if all(os.path.exists(f'{logs}/{x}.done') for x in (a, b)):
        try:
            rep = '; report ' + runreport.report(work, a, b, f'{logs}/report-{a}-{b}.txt')
        except Exception as e:  # the run's own figures stand
            rep = f'; no report, {type(e).__name__}: {e}'
    else:
        rep = f'; no report, {a} or {b} not measured'
    say(f'rebuild DONE: {done} of {len(todo)} steps measured,'
        f' failed: {" ".join(failed) or "none"}; {free_gb(work):.0f} GB free{rep}')
    return 2 if failed else 0


def mem_gb(path):
    with open(path) as fh:
        for line in fh:
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) * 1024 / 1e9
    raise ValueError(f'no MemAvailable in {path}')


def build_main(argv):
    """--build: the gate, then build_script under taskset, -j and the ulimit."""
    o = {'work': WORK, 'repo': REPO, 'logs': os.getcwd(), 'target': '', 'max_wait': -1.0,
         'min_free': float(MIN_FREE), 'min_mem': float(MIN_MEM), 'meminfo': MEMINFO,
         'poll': float(POLL)}
    patches, settings = [], []
    while argv[:1] and argv[0].startswith('--'):
        name = argv[0][2:].replace('-', '_')
        if len(argv) < 2 or name not in ('patch', 'setting', *o):
            print(f'{argv[0]}: no such option of --build, or it needs a value', file=sys.stderr)
            return 2
        if name == 'patch':
            patches.append(os.path.abspath(argv[1]))
        elif name == 'setting':
            settings.append(argv[1])
        else:
            o[name] = type(o[name])(argv[1])
        argv = argv[2:]
    if len(argv) != 3:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    tree, commit, cpus = argv
    work, logs = os.path.abspath(o['work']), os.path.abspath(o['logs'])
    p = git(o['repo'], 'rev-parse', '--verify', commit + '^{commit}')
    n = subprocess.run(['taskset', '-c', cpus, 'nproc'], capture_output=True, text=True)
    why = ([f'a tree is letters, digits, _ and .: {tree!r}']
           if not re.fullmatch(r'[A-Za-z0-9_.]+', tree) else [])
    why += [f'ghc-{tree} would be a tree of the rebuild\'s'] if re.fullmatch(r'fr\d+', tree) else []
    why += [f'no commit {commit} in {o["repo"]}'] if p.returncode else []
    why += [f'CPUS is not a taskset list taskset takes: {cpus!r}'] if n.returncode else []
    why += [f'no patch {x}' for x in patches if not os.path.isfile(x)]
    if why:
        print(f'{"; ".join(why)}; nothing built', file=sys.stderr)
        return 2
    jobs = int(n.stdout)
    script = build_script(work, o['repo'], logs, tree, p.stdout.strip(), jobs,
                          patches, o['target'] or None, settings)
    t0 = time.time()
    while mem_gb(o['meminfo']) < o['min_mem']:
        if 0 <= o['max_wait'] <= time.time() - t0:
            print(f'{tree}: {mem_gb(o["meminfo"]):.1f} GB available after {time.time() - t0:.0f} s,'
                  f' under {o["min_mem"]:g}; nothing built', flush=True)
            return 9
        time.sleep(o['poll'])
    free = free_gb(work)
    if free < o['min_free']:
        print(f'{tree}: {free:.0f} GB free on {work}, under {o["min_free"]:g}; nothing built', flush=True)
        return 9
    os.makedirs(logs, exist_ok=True)
    log = f'{logs}/build-{tree}.log'
    open(log, 'w').close()
    print(f'{tree} start {time.strftime("%T")}: {mem_gb(o["meminfo"]):.1f} GB available,'
          f' {free:.0f} GB free, CPUs {cpus} at -j{jobs}', flush=True)
    t1 = time.time()
    st = run_logged(['taskset', '-c', cpus, 'bash', '-c', f'ulimit -v {ULIMIT_V}; {script}'],
                    log, None)
    with open(log) as fh:
        last = (fh.read().strip().splitlines() or [''])[-1]
    print(f'{tree} exit {st} in {(time.time() - t1) / 60:.0f} min: {last}', flush=True)
    return st


def main(argv):
    if argv == ['--self-test']:
        return run_self_test('rebuild.py', self_test)
    if argv[:1] == ['--build']:
        return build_main(argv[1:])
    o = {'work': WORK, 'repo': REPO, 'battery': BATTERY, 'timeout': TIMEOUT, 'min_free': MIN_FREE}
    dry = False
    while argv[:1] and argv[0].startswith('--'):
        name = argv[0][2:].replace('-', '_')
        if name == 'dry':
            dry, argv = True, argv[1:]
        elif name == 'pair':
            o['pair'], argv = True, argv[1:]
        elif name in o and len(argv) >= 2:
            o[name] = type(o[name])(argv[1])
            argv = argv[2:]
        else:
            print(f'{argv[0]}: no such option, or it needs a value', file=sys.stderr)
            return 2
    if len(argv) != 3:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    o['work'] = os.path.abspath(o['work'])
    o['cpus'] = argv[2]
    o['logs'] = f'{o["work"]}/battery/rebuild'
    try:
        jobs = len(cpu_list(argv[2]))
        steps = steps_of(o['repo'], argv[0], argv[1])
    except ValueError as e:
        print(f'{e}; nothing run', file=sys.stderr)
        return 2
    missing = [x for x in (NOFIB_RUN, PAPIPKG, PERF_TESTS, MBB, SPECTRAL_MAKEFILE,
                           CONTAINERS_CABAL, A2T_SRC + '/orthotope.cabal', A2T_CELLS,
                           'ghc-g/.git/modules')
               if not os.path.exists(f'{o["work"]}/{x}')]
    if missing and o['battery'] == BATTERY:
        print(f'no {" ".join(missing)} under {o["work"]}; nothing run', file=sys.stderr)
        return 2
    if dry:
        for label, commit in ([steps[0], steps[-1]] if o.get('pair') else steps):
            print(label, commit)
        print(build_script(o['work'], o['repo'], o['logs'], steps[0][0], steps[0][1], jobs))
        print(shlex.join([sys.executable, o['battery'], '--work', o['work'],
                          steps[0][0], steps[0][0], o['cpus']]))
        return 0
    return run(o, steps)


# --- self-test: a planted repository whose ./boot, ./configure and hadrian/build
# only record what they are given, a battery that plants results, real git.

RECORD = 'echo "$(basename "$0")|$(basename "$PWD")" >> "$FAKELOG"\n'
# perf stat around hadrian, a count of its own
PERF = r'''#!/bin/bash
o=; while [ "$1" != -- ]; do [ "$1" = -o ] && o=$2; shift; done; shift
"$@"; e=$?
echo "123456,,instructions:u,9,100.00,," > "$o"; exit $e
'''
HADRIAN = r'''#!/bin/bash
t=$(basename "$PWD")
echo "hadrian|$t|$(git rev-parse HEAD)|$*|$(taskset -cp $$ | sed 's/.*: //')|$(ls -d ../ghc-fr* | wc -l)|$(cat libs/x/f)|$(paste -sd';' _build/hadrian.settings)|$(ulimit -v)" >> "$FAKELOG"
mkdir -p _build/stage1/compiler/build/compiler/GHC _build/stage1/compiler/build/GHC; touch _build/a.o
printf 'P [GHC.X]: alloc=100 time=2.0\n' > _build/stage1/compiler/build/compiler/GHC/X.dump-timings
echo xx > _build/stage1/compiler/build/GHC/X.o
echo 'x: warning: one'; echo 'y: warning: two'
[ "${FAKEHADRIAN:-}" = "$t" ] && exit 1
exit 0
'''
FAKE_BATTERY = r'''
import os, subprocess, sys
assert sys.argv[1] == '--work'
w, tree, label, cpus = sys.argv[2:6]
open(os.environ['FAKELOG'], 'a').write(f'battery|{tree}|{label}|{cpus}\n')
c, o1 = f'c{tree}-{label}', f'c{tree}-o1-{label}'
n, v, b = f'{w}/nofib-r', f'{w}/vpapi', f'{w}/battery'
def put(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w').write('x')
for r in (c, f'o1-{label}', f'o0-{label}'):
    put(f'{n}/nofib/_make/{r}/x/Main'); put(f'{n}/nofib/_make/{r}/x/Main.perf.results.tsv')
    put(f'{n}/stats/{r}/1.csv')
put(f'{n}/c{tree}/{label}/w/ghc'); put(f'{n}/co/{label}/w/ghc')
put(f'{v}/store-{c}/x'); put(f'{v}/cdist-{c}/x'); put(f'{v}/mdist-{o1}/x'); put(f'{v}/dist-{c}/x')
put(f'{v}/cres/{c}/m-1.csv'); put(f'{v}/mres/{o1}/b-1.csv'); put(f'{v}/res-{c}-1.csv')
put(f'{v}/ctr/cabal.project.{c}'); put(f'{v}/cb-{c}.log')
put(f'{v}/adist-{c}/x'); put(f'{v}/a2t/cabal.project.{c}'); put(f'{v}/ab-{c}.log')
put(f'{b}/perf-{label}.tsv'); put(f'{b}/p{label}/a.s'); put(f'{b}/comp2-{label}.runs')
put(f'{b}/tix-{label}.tsv'); open(f'{b}/a2t-{label}.tsv', 'w').write('c\t1.0\t0\t2.0\n')
os.makedirs(f'{v}/wstats-cdist-{c}', exist_ok=True)
open(f'{v}/wstats-cdist-{c}/1.args', 'w').write('/x\n--make\n-this-unit-id\nu-0\n-no-link\n')
open(f'{v}/wstats-cdist-{c}/1.csv', 'w').write('77,,instructions:u,9,100.00,,\n')
if os.environ.get('FAKEHANG') == label:
    subprocess.Popen(['bash', '-c', 'echo $$ > "$FAKEPID"; exec sleep 4']).wait()
sys.exit(3 if label in os.environ.get('FAKEBATTERY', '').split() else 0)
'''


def plant(d):
    def sh(*args, cwd):
        subprocess.run(args, cwd=cwd, check=True, capture_output=True)
    ident = ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
             '-c', 'protocol.file.allow=always']
    x, r, w = f'{d}/x', f'{d}/repo', f'{d}/w'
    for path in (x, r, w):
        os.makedirs(path)
    sh('git', 'init', '-q', cwd=x)
    with open(f'{x}/f', 'w') as fh:
        fh.write('sub\n')
    sh('git', 'add', 'f', cwd=x)
    sh(*ident, 'commit', '-qm', 'x', cwd=x)
    sh('git', 'init', '-q', cwd=r)
    os.makedirs(f'{r}/hadrian')
    for rel, text in (('boot', '#!/bin/bash\n' + RECORD), ('configure', '#!/bin/bash\n' + RECORD),
                      ('hadrian/build', HADRIAN)):
        with open(f'{r}/{rel}', 'w') as fh:
            fh.write(text)
        os.chmod(f'{r}/{rel}', 0o755)
    sh(*ident, 'submodule', 'add', '-q', x, 'libs/x', cwd=r)
    with open(f'{r}/.gitmodules', 'a') as fh:
        fh.write('[submodule "nofib"]\n\tpath = nofib\n\turl = /nowhere\n')
    sh('git', 'add', '.', cwd=r)
    sh(*ident, 'commit', '-qm', 'base', cwd=r)
    for i in range(1, 5):
        with open(f'{r}/c', 'a') as fh:
            fh.write(f'{i}\n')
        sh('git', 'add', 'c', cwd=r)
        sh(*ident, 'commit', '-qm', f'commit {i}', cwd=r)
    sh(*ident, 'clone', '-q', r, f'{w}/ghc-g', cwd=d)
    sh(*ident, 'submodule', 'update', '-q', '--init', 'libs/x', cwd=f'{w}/ghc-g')
    for rel in ('nofib-r/co', 'vpapi/ctr', 'vpapi/cres', 'vpapi/mres', 'battery'):
        os.makedirs(f'{w}/{rel}', exist_ok=True)
    with open(f'{d}/battery.py', 'w') as fh:
        fh.write(FAKE_BATTERY)
    os.makedirs(f'{d}/bin')
    with open(f'{d}/bin/perf', 'w') as fh:
        fh.write(PERF)
    os.chmod(f'{d}/bin/perf', 0o755)
    return r, w


def self_test():
    bad = Failures()
    mine = sorted(os.sched_getaffinity(0))
    if len(mine) < 4:  # a run pinned to three of them tells its CPUs from the test's
        print(f'the self-test needs four CPUs and has {len(mine)}; nothing run')
        return 2
    cpus = mine[:3]
    spec = ','.join(str(c) for c in cpus)
    with tempfile.TemporaryDirectory(prefix='ncg-rebuild-') as d:
        r, w = plant(d)
        log = f'{d}/fake.log'
        tip = git(r, 'rev-parse', 'HEAD').stdout.strip()
        base = git(r, 'rev-list', '--max-parents=0', 'HEAD').stdout.strip()
        hashes = [base] + git(r, 'rev-list', '--reverse', f'{base}..{tip}').stdout.split()
        logs = f'{w}/battery/rebuild'

        def go(args=(base, tip, spec), work=w, opts=(), **extra):
            open(log, 'w').close()
            env = dict(os.environ, FAKELOG=log, FAKEPID=f'{d}/pid',
                       PATH=f'{d}/bin' + os.pathsep + os.environ['PATH'], **extra)
            # the disk's free space no input of the test (NCG-battery-08)
            p = subprocess.run([sys.executable, os.path.abspath(__file__), '--work', work,
                                '--repo', r, '--battery', f'{d}/battery.py', '--min-free', '0',
                                *opts, *args],
                               env=env, capture_output=True, text=True)
            with open(log) as fh:
                return p, fh.read().split('\n')[:-1]

        def measured(lines):
            return [x.split('|')[1] for x in lines if x.startswith('battery|')]
        all_labels = [f'fr{i:02d}' for i in range(5)]
        # Dry, and refusals before anything runs.
        p, lines = go(opts=('--dry',))
        if p.returncode or lines or os.path.exists(logs) or hashes[0] not in p.stdout:
            bad.append(f'--dry: {p.returncode}, ran {lines[:2]}')
        p, lines = go(opts=('--dry', '--pair'))
        if p.returncode or lines or [x.split()[0] for x in p.stdout.split('\n')[:2]] != ['fr00', 'fr04']:
            bad.append(f'--dry --pair: {p.returncode}, {p.stdout[:120]!r}')
        p = subprocess.run([sys.executable, os.path.abspath(__file__), '--work', w, '--repo', r,
                            '--dry', base, tip, spec], capture_output=True, text=True)
        if p.returncode != 2 or NOFIB_RUN not in p.stderr:
            bad.append(f'a work directory lacking what the battery reads: {p.returncode}')
        for args, word in (((tip, base, spec), 'not an ancestor'), ((base, 'nosuch', spec), 'no commit'),
                           ((base, tip, '1'), 'fewer than three'), ((base, base, spec), 'no commit between')):
            p, lines = go(args)
            if p.returncode != 2 or lines or word not in p.stderr:
                bad.append(f'{args}: {p.returncode} {p.stderr[-100:]}')
        p, lines = go(opts=('--min-free', '100000000'))
        if p.returncode != 2 or lines or 'GB free before fr00' not in p.stdout:
            bad.append(f'a full disk: {p.returncode} {p.stdout[-200:]}')
        shutil.rmtree(logs)
        # Results a first run finds stop it.
        os.makedirs(f'{w}/vpapi/cres/cfr02-fr02')
        p, lines = go()
        if p.returncode != 2 or lines or 'results exist' not in p.stdout:
            bad.append(f'earlier results: {p.returncode} {p.stdout[-200:]}')
        os.rmdir(f'{w}/vpapi/cres/cfr02-fr02')
        shutil.rmtree(logs)
        # The whole run: base first, build and battery in turn, one tree at a time.
        p, lines = go()
        if p.returncode != 0 or 'rebuild DONE: 5 of 5' not in p.stdout:
            bad.append(f'the run exited {p.returncode}: {p.stdout[-300:]} {p.stderr[-300:]}')
        want = []
        for lab in all_labels:
            want += [f'boot|ghc-{lab}', f'configure|ghc-{lab}', f'hadrian|ghc-{lab}', f'battery|{lab}']
        got = ['|'.join(x.split('|')[:2]) for x in lines]
        if got != want:
            bad.append(f'the order was {got}')
        for lab, h, x in zip(all_labels, hashes, [y for y in lines if y.startswith('hadrian|')]):
            f = x.split('|')
            if f[2] != h or f[3] != f'-j3 -V --flavour={FLAVOUR} --docs=none':
                bad.append(f'{lab} built {f[2]} with {f[3]}')
            if sorted(int(c) for c in cpu_list(f[4])) != cpus:
                bad.append(f'{lab} built on CPUs {f[4]}, not {spec}')
            if f[5] != '1':
                bad.append(f'{lab} built beside {f[5]} trees')
            if f[6] != 'sub':
                bad.append(f'{lab} without its submodule: {f[6]!r}')
            if f[7] != HADRIAN_SETTINGS:
                bad.append(f'{lab} built under the settings {f[7]!r}')
        for x in [y for y in lines if y.startswith('battery|')]:
            f = x.split('|')
            if f[1] != f[2] or f[3] != spec:
                bad.append(f'battery ran {x}')
        n, v = f'{w}/nofib-r', f'{w}/vpapi'
        for lab in all_labels:
            c, o1 = f'c{lab}-{lab}', f'c{lab}-o1-{lab}'
            for rel in (f'{n}/nofib/_make/{c}/x/Main.perf.results.tsv',
                        f'{n}/nofib/_make/o0-{lab}/x/Main.perf.results.tsv',
                        f'{n}/stats/o1-{lab}/1.csv', f'{v}/cres/{c}/m-1.csv', f'{v}/mres/{o1}/b-1.csv',
                        f'{v}/res-{c}-1.csv', f'{v}/cb-{c}.log', f'{w}/battery/perf-{lab}.tsv',
                        f'{v}/ab-{c}.log', f'{w}/battery/a2t-{lab}.tsv',
                        f'{w}/battery/p{lab}/a.s', f'{w}/battery/comp2-{lab}.runs',
                        f'{logs}/hadrian-{lab}.log.gz', f'{logs}/{lab}.done'):
                if not os.path.exists(rel):
                    bad.append(f'{rel} was not kept')
            for rel in (f'{w}/ghc-{lab}', f'{n}/nofib/_make/{c}/x/Main', f'{n}/c{lab}', f'{n}/co/{lab}',
                        f'{v}/store-{c}', f'{v}/cdist-{c}', f'{v}/mdist-{o1}', f'{v}/dist-{c}',
                        f'{v}/ctr/cabal.project.{c}', f'{v}/adist-{c}', f'{v}/a2t/cabal.project.{c}',
                        f'{v}/wstats-cdist-{c}',
                        f'{logs}/hadrian-{lab}.log'):
                if os.path.exists(rel):
                    bad.append(f'{rel} is still there')
        if 'with 2 warnings' not in open(f'{logs}/fr01.done').read():
            bad.append('the warnings were not counted: ' + open(f'{logs}/fr01.done').read())
        # GHC's build and the packages' recorded before the prune.
        ghcb = open(f'{w}/battery/ghcb-fr01.tsv').read().split('\n')
        pkgb = open(f'{w}/battery/pkgb-fr01.tsv').read().split('\n')
        if 'process\tghc\thadrian\tinstructions\t123456' not in ghcb \
                or 'module\tghc/stage1\tcompiler/build/GHC/X.o\talloc\t100' not in ghcb \
                or not any(x.startswith('process\tghc\thadrian\twall_s\t') for x in ghcb) \
                or 'process\tcontainers-O2\tu-0\tinstructions\t77' not in pkgb \
                or 'instructions:u 123456' not in open(f'{logs}/build-fr01.log').read():
            bad.append(f'the build records: {ghcb} {pkgb}')
        rep = f'{logs}/report-fr00-fr04.txt'
        if not p.stdout.rstrip('\n').endswith(f'; report {rep}') or not os.path.exists(rep) \
                or 'fr04 against fr00' not in open(rep).read():
            bad.append(f'the report: {p.stdout[-200:]}')
        # Measured steps are not done again, and other commits are refused.
        p, lines = go()
        if p.returncode != 0 or lines:
            bad.append(f'a second run: {p.returncode}, ran {lines[:2]}')
        p, lines = go((hashes[1], tip, spec))
        if p.returncode != 2 or lines or 'another base' not in p.stdout:
            bad.append(f'another base: {p.returncode} {p.stdout[-200:]}')
        # Another run holding the lock.
        with open(f'{logs}/lock', 'w') as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            p, lines = go()
            if p.returncode != 2 or lines or 'lock' not in p.stdout:
                bad.append(f'the lock: {p.returncode} {p.stdout[-200:]}')

        # A measured step lacking a record of 2026-11-07 is measured again,
        # and so is one whose commit is another now.
        os.unlink(f'{w}/battery/tix-fr02.tsv')
        with open(f'{w}/battery/a2t-fr03.tsv', 'w') as fh:
            fh.write('c\t1.0\t0\n')
        p, lines = go()
        if p.returncode != 0 or measured(lines) != ['fr02', 'fr03'] or 'measured without' not in p.stdout:
            bad.append(f'steps lacking records: {p.returncode} {measured(lines)} {p.stdout[-300:]}')
        with open(f'{logs}/steps.txt') as fh:
            st = fh.read()
        with open(f'{logs}/steps.txt', 'w') as fh:
            fh.write(st.replace(f'fr01 {hashes[1]}', f'fr01 {hashes[2]}'))
        p, lines = go()
        if p.returncode != 0 or measured(lines) != ['fr01'] or 'names another commit' not in p.stdout \
                or open(f'{logs}/steps.txt').read() != st:
            bad.append(f'a step of another commit: {p.returncode} {measured(lines)} {p.stdout[-300:]}')

        def fresh(name):
            w2 = f'{d}/{name}'
            shutil.copytree(w, w2, symlinks=True)
            shutil.rmtree(f'{w2}/battery/rebuild')
            for lab in all_labels:
                for path in label_paths(w2, lab):
                    remove(path)
            return w2
        # The pair alone, the base and the tip, under the chain's labels, and then
        # the chain taking up the rest.
        w7 = fresh('w7')
        p, lines = go(work=w7, opts=('--pair',))
        if p.returncode != 0 or measured(lines) != ['fr00', 'fr04'] \
                or 'rebuild DONE: 2 of 2' not in p.stdout or 'report-fr00-fr04.txt' not in p.stdout \
                or open(f'{w7}/battery/rebuild/steps.txt').read() != st:
            bad.append(f'--pair: {p.returncode} {measured(lines)} {p.stdout[-300:]}')
        p, lines = go(work=w7)
        if p.returncode != 0 or measured(lines) != ['fr01', 'fr02', 'fr03']:
            bad.append(f'the chain after the pair: {p.returncode} {measured(lines)}')
        # A failed step keeps its files and the next one starts; run again, only it runs.
        w2 = fresh('w2')
        p, lines = go(work=w2, FAKEBATTERY='fr01')
        if p.returncode != 2 or 'fr01 FAILED, battery: 3' not in p.stdout \
                or measured(lines) != all_labels or 'failed: fr01' not in p.stdout:
            bad.append(f'a failed battery: {p.returncode} {measured(lines)} {p.stdout[-300:]}')
        if not os.path.isdir(f'{w2}/ghc-fr01') or not os.path.isdir(f'{w2}/vpapi/store-cfr01-fr01') \
                or os.path.isdir(f'{w2}/ghc-fr02'):
            bad.append('a failed battery: the wrong files kept')
        p, lines = go(work=w2)
        if p.returncode != 0 or measured(lines) != ['fr01'] or os.path.exists(f'{w2}/ghc-fr01') \
                or os.path.exists(f'{w2}/battery/rebuild/fr01.failed'):
            bad.append(f'taking up the failed step: {p.returncode} {measured(lines)}')
        # A failed build runs no battery; three steps failing in a row stop the run.
        w3 = fresh('w3')
        p, lines = go(work=w3, FAKEHADRIAN='ghc-fr02')
        if p.returncode != 2 or 'fr02 FAILED, build: 4' not in p.stdout \
                or measured(lines) != ['fr00', 'fr01', 'fr03', 'fr04']:
            bad.append(f'a failed build: {p.returncode} {measured(lines)}')
        w4 = fresh('w4')
        bin4 = f'{d}/b4.py'
        with open(bin4, 'w') as fh:
            fh.write('import sys\nsys.exit(3)\n')
        p = subprocess.run([sys.executable, os.path.abspath(__file__), '--work', w4, '--repo', r,
                            '--battery', bin4, '--min-free', '0', base, tip, spec],
                           env=dict(os.environ, FAKELOG=log,
                                    PATH=f'{d}/bin' + os.pathsep + os.environ['PATH']),
                           capture_output=True, text=True)
        if p.returncode != 2 or 'rebuild STOP, 3 steps failed in a row' not in p.stdout \
                or 'fr03' in p.stdout or 'rebuild DONE' in p.stdout:
            bad.append(f'failing in a row: {p.returncode} {p.stdout[-300:]}')
        # As many failures with a measured step between them do not stop it.
        w6 = fresh('w6')
        p, lines = go(work=w6, FAKEBATTERY='fr00 fr02 fr04')
        if p.returncode != 2 or 'rebuild DONE: 2 of 5' not in p.stdout or measured(lines) != all_labels:
            bad.append(f'failures apart: {p.returncode} {measured(lines)} {p.stdout[-300:]}')
        # A hung battery is killed with its children, which fails the step alone:
        # the whole run's fr03 and fr04 done again, fr03's battery outliving
        # the timeout by 3 s.
        w5 = f'{d}/w5'
        shutil.copytree(w, w5, symlinks=True)
        for lab in ('fr03', 'fr04'):
            os.unlink(f'{w5}/battery/rebuild/{lab}.done')
        p, lines = go(work=w5, opts=('--timeout', '1'), FAKEHANG='fr03')
        if p.returncode != 2 or 'fr03 FAILED, battery: killed' not in p.stdout \
                or measured(lines) != ['fr03', 'fr04']:
            bad.append(f'a hung battery: {p.returncode} {measured(lines)} {p.stdout[-300:]}')
        with open(f'{d}/pid') as fh:
            pid = fh.read().strip()
        for _ in range(50):  # until the killed child is reaped
            if not os.path.exists(f'/proc/{pid}'):
                break
            time.sleep(0.01)
        else:
            bad.append("a hung battery's child survived it")

        # --build: one tree, at a commit named short, with two patches the
        # second of which needs the first, a target and two settings lines, on
        # two CPUs; and the gate, each way it stops or waits.
        two = mine[:2]
        blogs, meminfo = f'{d}/blogs', f'{d}/meminfo'
        for name, text in (('p1.diff', '--- /dev/null\n+++ b/p1\n@@ -0,0 +1 @@\n+one\n'),
                           ('p2.diff', '--- a/p1\n+++ b/p1\n@@ -1 +1,2 @@\n one\n+two\n'),
                           ('bad.diff', '--- a/c\n+++ b/c\n@@ -1 +1 @@\n-nosuch\n+x\n')):
            with open(f'{d}/{name}', 'w') as fh:
                fh.write(text)

        def avail(gb):
            with open(meminfo, 'w') as fh:
                fh.write(f'MemTotal: 1 kB\nMemAvailable: {int(gb * 1e9 / 1024)} kB\n')

        def cpus_of(s):
            return sorted(c for x in s.split(',')
                          for c in range(int(x.split('-')[0]), int(x.split('-')[-1]) + 1))

        def build(tree, *opts, commit=hashes[2][:10], cpus=','.join(map(str, two)),
                  min_free='0', during=None):
            open(log, 'w').close()
            env = dict(os.environ, FAKELOG=log, PATH=f'{d}/bin' + os.pathsep + os.environ['PATH'])
            p = subprocess.Popen([sys.executable, os.path.abspath(__file__), '--build', '--work', w,
                                  '--repo', r, '--logs', blogs, '--min-free', min_free,
                                  '--meminfo', meminfo, '--poll', '0.05', *opts, tree, commit, cpus],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if during:
                during(p)
            try:
                out, err = p.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
                out, err = p.communicate()
                err += ' (killed after 30 s)'
            with open(log) as fh:
                return p.returncode, out, err, fh.read().split('\n')[:-1]
        avail(20)
        rc, out, err, lines = build('tb1', '--patch', f'{d}/p1.diff', '--patch', f'{d}/p2.diff',
                                    '--target', '_build/stage0/bin/ghc',
                                    '--setting', 'a.b += -x', '--setting', 'c.d += -y')
        h = [x.split('|') for x in lines if x.startswith('hadrian|')]
        if rc != 0 or len(h) != 1 or 'tb1 exit 0 in' not in out or 'hadrian tb1 exit 0' not in out:
            bad.append(f'--build: {rc} {out[-300:]} {err[-300:]}')
        else:
            f = h[0]
            if f[2] != hashes[2]:
                bad.append(f'--build built {f[2]}, not {hashes[2]}')
            if f[3] != f'-j2 -V --flavour={FLAVOUR} --docs=none _build/stage0/bin/ghc':
                bad.append(f'--build ran hadrian with {f[3]!r}')
            if cpus_of(f[4]) != two:
                bad.append(f'--build ran on CPUs {f[4]}, not {two}')
            if f[7] != f'{HADRIAN_SETTINGS};a.b += -x;c.d += -y':
                bad.append(f'--build under the settings {f[7]!r}')
            if f[8] != str(ULIMIT_V):
                bad.append(f'--build under ulimit -v {f[8]}')
            if not os.path.exists(f'{w}/ghc-tb1/p1') or open(f'{w}/ghc-tb1/p1').read() != 'one\ntwo\n':
                bad.append('--build: the patches not applied in order')
            if not os.path.exists(f'{blogs}/build-tb1.log') \
                    or 'changed: ?? p1' not in open(f'{blogs}/build-tb1.log').read():
                bad.append('--build: no log in LOGS naming what the patches changed')
        rc, out, err, lines = build('tb2', '--patch', f'{d}/bad.diff')
        if rc != 2 or lines or f'tree STOP tb2, patch {d}/bad.diff failed' not in out:
            bad.append(f'--build, a patch failing: {rc} {lines[:2]} {out[-200:]}')
        # Too little memory: waited for at most --max-wait, or until there is enough.
        avail(1)
        rc, out, err, lines = build('tb3', '--max-wait', '0.2')
        if rc != 9 or lines or 'GB available after' not in out or os.path.exists(f'{w}/ghc-tb3'):
            bad.append(f'--build, memory short past --max-wait: {rc} {lines[:2]} {out[-200:]} {err[-100:]}')

        def later(p):
            time.sleep(0.5)
            if p.poll() is not None or open(log).read():
                bad.append(f'--build did not wait for memory: {p.poll()}')
            avail(20)
        rc, out, err, lines = build('tb4', during=later)
        if rc != 0 or not [x for x in lines if x.startswith('hadrian|ghc-tb4|')]:
            bad.append(f'--build after waiting for memory: {rc} {out[-200:]} {err[-200:]}')
        rc, out, err, lines = build('tb5', min_free='100000000')
        if rc != 9 or lines or 'GB free on' not in out:
            bad.append(f'--build, a full disk: {rc} {lines[:2]} {out[-200:]}')
        for args, word in ((('fr07',), "a tree of the rebuild's"),
                           (('tb6', '--patch', f'{d}/none.diff'), 'no patch'),
                           (('tb6',), 'no commit'), (('tb6',), 'taskset')):
            kw = {'commit': 'nosuch'} if word == 'no commit' else {'cpus': 'x'} if word == 'taskset' else {}
            rc, out, err, lines = build(args[0], *args[1:], **kw)
            if rc != 2 or lines or word not in err:
                bad.append(f'--build refusing {args} {kw}: {rc} {lines[:2]} {err[-200:]}')
    for x in bad:
        print('FAIL', x)
    print('ok   rebuild.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
