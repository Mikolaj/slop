#!/usr/bin/env python3
"""One label of the NCG series measured from a commit: its tree built,
the whole battery run on it and its report written against each base, each
step's outcome a line in a chain log that a later launch or a waiter reads.

Usage: python3 tools/NCG-battery/label.py [--dry] [--work DIR] [--logs DIR]
           [--a2t-lock FILE] [--after STEP] [--steps STEP,...]
           LABEL COMMIT CPUS [BASE...]
       python3 tools/NCG-battery/label.py [--work DIR] [--logs DIR] --cmp A B
       python3 tools/NCG-battery/label.py --self-test

LABEL names the tree and the label alike, as rebuild.py's do, COMMIT is a
commit of ~/slop/ghc and CPUS a taskset list of three CPUs or more. The
steps, in this order, the ones --steps names (build, battery, report) or all:

  build    rebuild.py --build LABEL COMMIT CPUS, the work directory's ghc-LABEL
           from nothing, its lines in LOGS/rebuild-build-LABEL.out, the
           build's in LOGS/build-LABEL.log; then hadrian's log gzipped and
           bstats.py ghc's table of the build, WORK/battery/ghcb-LABEL.tsv
  battery  battery.py LABEL LABEL CPUS, the whole battery, its lines in
           LOGS/battery-LABEL.log, every A2T build under --a2t-lock FILE,
           WORK/battery-inputs/a2t.lock by default; then bstats.py pkgs's
           table of the packages' builds, WORK/battery/pkgb-LABEL.tsv
  report   runreport.py BASE LABEL for each BASE, LOGS/report-BASE-LABEL.txt

Each runs from the work directory, battery.py's (--work, dist-ghcho by default),
and LOGS is --logs or WORK/battery/label. LOGS/chain.log gets, before each
step, the work directory's free space and MemAvailable and `LABEL-STEP start`;
after it `LABEL-STEP OK` or `LABEL-STEP FAILED`, the report step's after a line
`runreport BASE LABEL exit N` for each BASE; and at the end `LABEL ALL DONE`,
or `LABEL ALL FAILED at STEP` where a step failed and the rest did not run,
each line ending in the time. --after STEP, a step of another launch named as
its chain line names it (`s2a-battery`), first waits until the chain log has
that step's OK or FAILED, reading it every POLL seconds, and runs nothing after
a FAILED. COMMIT is read by build alone and may be `-` where --steps leaves it
out. --dry prints each command and the wait and runs nothing.

A launch other than --dry is refused, exit 2 with nothing run, from inside
the inner sandbox (SANDBOX_RUNTIME set) or with TMPDIR set: the sandbox sets
TMPDIR and more variables, which move compile allocation and short programs'
instruction counts against labels launched outside it. Run it unsandboxed, with
TMPDIR unset. It exits 0 when every step it ran succeeded, 1 when one failed, 2
when refused, on a usage error or after --after's step failed.

--cmp A B compares the objects of labels A and B, each measured on the tree
named as the label, as this launcher measures them, into LOGS/cmp-A-B/:
obj-diff.py --all over nofib's _make directories at -O2, -O1 and -O0, and over
each package's build directory at -O2 and -O1, below its ghc-VERSION directory,
whose name moves with the commit's date; and each benchmark executable in those,
`binaries identical` or obj-diff.py's verdict over the two files. It prints a
line for each and exits 0, or 2 on a usage error. runreport.py compares the
labels' figures and the compilations' assembly, and none of these objects.
"""

import fnmatch
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from battery import PKGS, WORK, Failures, cpu_list, run_self_test  # noqa: E402

TOOLS = {'rebuild': os.path.join(HERE, 'rebuild.py'), 'battery': os.path.join(HERE, 'battery.py'),
         'bstats': os.path.join(HERE, 'bstats.py'), 'runreport': os.path.join(HERE, 'runreport.py'),
         'obj-diff': os.path.join(os.path.dirname(HERE), 'obj-diff.py')}
A2T_LOCK = 'battery-inputs/a2t.lock'  # under WORK, inputs.py's directory
LOGS = 'battery/label'  # under WORK
STEPS = ('build', 'battery', 'report')
POLL = 30  # s between readings of the chain log
MEMINFO = '/proc/meminfo'


def refused(env):
    """Why a launch in env is refused, or None."""
    if env.get('SANDBOX_RUNTIME') or env.get('TMPDIR'):
        return 'launch unsandboxed, TMPDIR unset: the sandbox moves compile allocation'
    return None


class Launch:
    def __init__(self, work, logs, lock, dry):
        self.work, self.logs, self.lock, self.dry = work, logs, lock, dry
        self.poll, self.meminfo, self.tools = POLL, MEMINFO, TOOLS
        self.chain = os.path.join(logs, 'chain.log')

    def say(self, line):
        if not self.dry:
            with open(self.chain, 'a') as fh:
                fh.write(f'{line} {time.strftime("%T")}\n')

    def run(self, argv, out):
        """argv's status, its output in out, from the work directory."""
        if self.dry:
            print(f'{shlex.join(argv)} > {shlex.quote(out)} 2>&1')
            return 0
        with open(out, 'w') as fh:
            return subprocess.run(argv, cwd=self.work, stdout=fh, stderr=subprocess.STDOUT).returncode

    def py(self, tool, *args):
        return [sys.executable, self.tools[tool], *args]

    def wait(self, after):
        """Whether step after of the chain ended OK, once it has ended."""
        if self.dry:
            print(f'# waits for "{after} OK" or "{after} FAILED" in {self.chain}')
            return True
        pat = re.compile(rf'{re.escape(after)} (OK|FAILED)( |$)')
        while True:
            if os.path.exists(self.chain):
                with open(self.chain) as fh:
                    for line in fh:
                        m = pat.match(line)
                        if m:
                            return m.group(1) == 'OK'
            time.sleep(self.poll)

    def state(self):
        """The free space and the memory, as the chain log records them."""
        free = shutil.disk_usage(self.work).free / 2 ** 30
        with open(self.meminfo) as fh:
            mem = next((x.strip() for x in fh if x.startswith('MemAvailable:')), 'no MemAvailable')
        return [f'{free:.0f} GiB free on {self.work}', mem]

    def build(self, label, commit, cpus):
        L = self.logs
        st = self.run(self.py('rebuild', '--build', '--work', self.work, '--logs', L,
                              label, commit, cpus), f'{L}/rebuild-build-{label}.out')
        if not self.dry:
            with open(f'{L}/rebuild-build-{label}.out') as fh:
                self.say((fh.read().strip().splitlines() or ['(no output)'])[-1])
        if st:
            return st
        hlog, wall = f'{L}/hadrian-{label}.log', 'WALL'
        if self.dry:
            print(f'gzip -f {shlex.quote(hlog)}')
        else:
            if os.path.exists(hlog) and subprocess.run(['gzip', '-f', hlog]).returncode:
                self.say(f'gzip -f {hlog} failed')
            with open(f'{L}/build-{label}.log') as fh:
                m = re.findall(r'; wall (\d+) s;', fh.read())
            wall = m[-1] if m else '0'
            self.say(f'wall {wall}')
        st = self.run(self.py('bstats', 'ghc', f'{self.work}/ghc-{label}',
                              f'{self.work}/battery/ghcb-{label}.tsv', f'{L}/hperf-{label}.csv', wall),
                      f'{L}/bstats-ghc-{label}.out')
        self.say(f'bstats ghc exit {st}')
        return st

    def battery(self, label, cpus):
        L = self.logs
        st = self.run(self.py('battery', '--work', self.work, '--a2t-lock', self.lock,
                              label, label, cpus), f'{L}/battery-{label}.log')
        if not self.dry:
            meas = f'{self.work}/battery/meas-{label}.log'
            with open(meas) if os.path.exists(meas) else open(os.devnull) as fh:
                last = (fh.read().strip().splitlines() or [f'no {meas}'])[-1]
            self.say(f'battery exit {st}; last: {last}')
        if st:
            return st
        st = self.run(self.py('bstats', 'pkgs', self.work, label, label,
                              f'{self.work}/battery/pkgb-{label}.tsv'), f'{L}/bstats-pkgs-{label}.out')
        self.say(f'bstats pkgs exit {st}')
        return st

    def report(self, label, bases):
        bad = 0
        for b in bases:
            st = self.run(self.py('runreport', '--work', self.work, b, label,
                                  f'{self.logs}/report-{b}-{label}.txt'),
                          f'{self.logs}/runreport-{b}-{label}.out')
            self.say(f'runreport {b} {label} exit {st}')
            bad = bad or st
        return bad

    def label(self, label, commit, cpus, bases, steps, after):
        if not self.dry:
            os.makedirs(self.logs, exist_ok=True)
        if after and not self.wait(after):
            self.say(f'{label}-{steps[0]} FAILED (skipped: {after} failed)')
            self.say(f'{label} ALL FAILED at {steps[0]}')
            return 2
        for s in steps:
            if not self.dry:
                for line in self.state():
                    self.say(line)
            self.say(f'{label}-{s} start')
            st = (self.build(label, commit, cpus) if s == 'build' else
                  self.battery(label, cpus) if s == 'battery' else self.report(label, bases))
            self.say(f'{label}-{s} {"FAILED" if st else "OK"}')
            if st:
                self.say(f'{label} ALL FAILED at {s}')
                return 1
        self.say(f'{label} ALL DONE')
        return 0


def benchmarks(d):
    """The executables of a package's build directory d, relative to it,
    its objects and libraries apart."""
    out = []
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            if (os.access(p, os.X_OK) and fnmatch.fnmatch(p, '*/build/*/build/*')
                    and not f.endswith(('.o', '.so'))):
                out.append(os.path.relpath(p, d))
    return sorted(out)


def compare(work, logs, a, b, say=print):
    """--cmp's comparisons of labels a and b, a line each said."""
    out = os.path.join(logs, f'cmp-{a}-{b}')
    os.makedirs(out, exist_ok=True)
    od = [sys.executable, TOOLS['obj-diff']]

    def obj_diff(args, path):
        with open(path, 'w') as fh:
            rc = subprocess.run(od + args, stdout=fh, stderr=subprocess.STDOUT).returncode
        with open(path) as fh:
            return (fh.read().splitlines() or [''])[0] + (f' (exit {rc})' if rc not in (0, 1) else '')
    n = os.path.join(work, 'nofib-r', 'nofib', '_make')
    for ra, rb, lev in ((f'c{a}-{a}', f'c{b}-{b}', 'O2'), (f'o1-{a}', f'o1-{b}', 'O1'),
                        (f'o0-{a}', f'o0-{b}', 'O0')):
        say(f'nofib {lev}: {obj_diff(["--all", f"{n}/{ra}", f"{n}/{rb}"], f"{out}/nofib-{lev}.txt")}')
    v = os.path.join(work, 'vpapi')
    for d in [p['builddir'] for p in PKGS.values()] + ['adist']:  # A2T's, -O2 alone
        for lv in ('', '-o1'):
            da, db = f'{v}/{d}-c{a}{lv}-{a}', f'{v}/{d}-c{b}{lv}-{b}'
            if not os.path.isdir(da):
                continue
            ga, gb = (sorted(x for x in os.listdir(f'{y}/build/x86_64-linux') if x.startswith('ghc-'))
                      if os.path.isdir(f'{y}/build/x86_64-linux') else [] for y in (da, db))
            if len(ga) != 1 or len(gb) != 1:
                say(f'{d}{lv}: not compared, ghc-VERSION directories {ga} and {gb}')
                continue
            da, db = f'{da}/build/x86_64-linux/{ga[0]}', f'{db}/build/x86_64-linux/{gb[0]}'
            say(f'{d}{lv}: {obj_diff(["--all", da, db], f"{out}/{d}{lv}.txt")}')
            for rel in benchmarks(da):
                ea, eb, name = f'{da}/{rel}', f'{db}/{rel}', os.path.basename(rel)
                if not os.path.exists(eb):
                    say(f'  {name}: only in {a}')
                elif subprocess.run(['cmp', '-s', ea, eb]).returncode == 0:
                    say(f'  {name}: binaries identical')
                else:
                    say(f'  {name}: {obj_diff([ea, eb], f"{out}/bin-{d}{lv}-{name}.txt")}')
    return 0


def main(argv, env=None):
    env = os.environ if env is None else env
    if argv == ['--self-test']:
        return run_self_test('label.py', self_test)
    o = {'work': WORK, 'logs': None, 'a2t_lock': None, 'after': None, 'steps': ','.join(STEPS)}
    dry, cmp = False, False
    while argv[:1] and argv[0].startswith('--'):
        name = argv[0][2:].replace('-', '_')
        if name in ('dry', 'cmp'):
            dry, cmp = dry or name == 'dry', cmp or name == 'cmp'
            argv = argv[1:]
        elif name in o and len(argv) >= 2:
            o[name], argv = argv[1], argv[2:]
        else:
            print(f'{argv[0]}: no such option, or it needs a value', file=sys.stderr)
            return 2
    work = os.path.abspath(o['work'])
    logs = os.path.abspath(o['logs'] or os.path.join(work, LOGS))
    steps = o['steps'].split(',')
    why = [f'no such step: {s}' for s in steps if s not in STEPS]
    why += (['steps out of order or repeated'] if not why
            and steps != sorted(set(steps), key=STEPS.index) else [])
    if cmp:
        if len(argv) != 2 or dry:
            print(__doc__.split('\n\n')[1], file=sys.stderr)
            return 2
        return compare(work, logs, *argv)
    if len(argv) < 3:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    label, commit, cpus, bases = argv[0], argv[1], argv[2], argv[3:]
    try:
        cpu_list(cpus)
    except ValueError as e:
        why.append(str(e))
    why += ['no BASE to report against'] if 'report' in steps and not bases else []
    why += [f'COMMIT {commit!r} with build'] if 'build' in steps and commit == '-' else []
    if why:
        print(f'label.py: {"; ".join(why)}; nothing run', file=sys.stderr)
        return 2
    if not dry and refused(env):
        print(f'label.py: {refused(env)}; nothing run', file=sys.stderr)
        return 2
    lock = os.path.abspath(o['a2t_lock'] or os.path.join(work, A2T_LOCK))
    return Launch(work, logs, lock, dry).label(label, commit, cpus, bases, steps, o['after'])


# --- self-test: fakes of the four tools recording their arguments and
# writing what the steps read, the launches run through main.

FAKE = r'''
import os, sys
tool, args = os.path.basename(sys.argv[0])[:-3], sys.argv[1:]
open(os.environ['FAKELOG'], 'a').write('|'.join([tool, os.getcwd()] + args) + '\n')
fail = os.environ.get('FAKEFAIL', '')
if tool == 'rebuild':
    logs, label = args[args.index('--logs') + 1], args[-3]
    open(f'{logs}/hadrian-{label}.log', 'w').write('hadrian\n')
    open(f'{logs}/build-{label}.log', 'w').write('x\nbuild done; wall 1197 s; instructions:u 9\n')
    print(f'{label} exit 0 in 20 min: done')
elif tool == 'battery':
    w, label = args[1], args[-2]
    os.makedirs(f'{w}/battery', exist_ok=True)
    open(f'{w}/battery/meas-{label}.log', 'a').write(f'== {label} all parts ran\n')
elif tool == 'obj-diff':
    print('compared:', ' '.join(os.path.basename(x) for x in args))
sys.exit(1 if tool == fail else 0)
'''


def self_test():
    bad = Failures()
    with tempfile.TemporaryDirectory(prefix='label-') as d:
        tools = {}
        for t in TOOLS:
            tools[t] = f'{d}/{t}.py'
            with open(tools[t], 'w') as fh:
                fh.write(FAKE)
        w, fakelog = f'{d}/w', f'{d}/fake.log'
        os.makedirs(w)
        mi = f'{d}/meminfo'
        with open(mi, 'w') as fh:
            fh.write('MemTotal: 1 kB\nMemAvailable:   52000000 kB\n')
        os.environ['FAKELOG'] = fakelog
        saved = dict(TOOLS), globals()['POLL'], globals()['MEMINFO']
        TOOLS.update(tools)
        globals().update(POLL=0.05, MEMINFO=mi)

        def launch(args, env=None, fail='', out=None):
            for p in (fakelog,):
                if os.path.exists(p):
                    os.unlink(p)
            os.environ['FAKEFAIL'] = fail
            buf = out if out is not None else open(os.devnull, 'w')
            old, sys.stdout, olderr, sys.stderr = sys.stdout, buf, sys.stderr, io.StringIO()
            try:
                rc = main(['--work', w] + args, env if env is not None else {})
            finally:
                sys.stdout, sys.stderr = old, olderr
            ran = open(fakelog).read().splitlines() if os.path.exists(fakelog) else []
            return rc, ran

        def chain(logs=f'{w}/battery/label'):
            p = f'{logs}/chain.log'
            return [re.sub(r' \d\d:\d\d:\d\d$', '', x) for x in open(p).read().splitlines()] \
                if os.path.exists(p) else []
        try:
            # The whole launch: each tool's arguments, from the work directory,
            # the lock under the work directory, and the chain's lines.
            rc, ran = launch(['L', 'abc123', '4-6', 'B1', 'B2'])
            lg, sh = f'{w}/battery/label', sys.executable
            want = [f'rebuild|{w}|--build|--work|{w}|--logs|{lg}|L|abc123|4-6',
                    f'bstats|{w}|ghc|{w}/ghc-L|{w}/battery/ghcb-L.tsv|{lg}/hperf-L.csv|1197',
                    f'battery|{w}|--work|{w}|--a2t-lock|{w}/battery-inputs/a2t.lock|L|L|4-6',
                    f'bstats|{w}|pkgs|{w}|L|L|{w}/battery/pkgb-L.tsv',
                    f'runreport|{w}|--work|{w}|B1|L|{lg}/report-B1-L.txt',
                    f'runreport|{w}|--work|{w}|B2|L|{lg}/report-B2-L.txt']
            if rc != 0 or ran != want:
                bad.append(f'the whole launch: {rc}, ran {ran}')
            c = chain()
            cw = ['L-build start', 'L exit 0 in 20 min: done', 'wall 1197', 'bstats ghc exit 0',
                  'L-build OK', 'L-battery start', 'battery exit 0; last: == L all parts ran',
                  'bstats pkgs exit 0', 'L-battery OK', 'L-report start', 'runreport B1 L exit 0',
                  'runreport B2 L exit 0', 'L-report OK', 'L ALL DONE']
            if [x for x in c if 'GiB free' not in x and not x.startswith('MemAvailable')] != cw \
                    or c.count('MemAvailable:   52000000 kB') != 3 \
                    or sum(x.endswith(f'GiB free on {w}') for x in c) != 3:
                bad.append(f'the whole launch\'s chain: {c}')
            if not os.path.exists(f'{lg}/hadrian-L.log.gz') or os.path.exists(f'{lg}/hadrian-L.log'):
                bad.append('hadrian\'s log not gzipped')
            # The sandbox refused, before anything runs.
            for env in ({'TMPDIR': '/tmp/claude-1000'}, {'SANDBOX_RUNTIME': '1'}):
                rc, ran = launch(['M', 'abc123', '4-6', 'B1'], env)
                if rc != 2 or ran or os.path.exists(f'{w}/battery/label/rebuild-build-M.out'):
                    bad.append(f'a launch under {env}: {rc}, ran {ran}')
            # A failed build stops the launch; --a2t-lock and --logs move.
            rc, ran = launch(['--logs', f'{d}/lg2', 'N', 'abc123', '4-6', 'B1'], fail='rebuild')
            if rc != 1 or len(ran) != 1 or chain(f'{d}/lg2')[-2:] != ['N-build FAILED',
                                                                     'N ALL FAILED at build']:
                bad.append(f'a failed build: {rc}, ran {ran}, chain {chain(f"{d}/lg2")}')
            rc, ran = launch(['--a2t-lock', f'{d}/x.lock', '--steps', 'battery', 'P', '-', '4-6'],
                             fail='battery')
            if rc != 1 or ran != [f'battery|{w}|--work|{w}|--a2t-lock|{d}/x.lock|P|P|4-6'] \
                    or chain()[-3:] != ['battery exit 1; last: == P all parts ran',
                                        'P-battery FAILED', 'P ALL FAILED at battery']:
                bad.append(f'a failed battery alone: {rc}, ran {ran}, chain {chain()[-3:]}')
            rc, ran = launch(['--steps', 'report', 'Q', '-', '4-6', 'B1'], fail='runreport')
            if rc != 1 or chain()[-3:] != ['runreport B1 Q exit 1', 'Q-report FAILED',
                                           'Q ALL FAILED at report']:
                bad.append(f'a failed report: {rc}, chain {chain()[-3:]}')
            # --after: a step failed skips the launch; one ended OK, or ending
            # OK while the launch waits, lets it run.
            with open(f'{lg}/chain.log', 'a') as fh:
                fh.write('X-battery FAILED 01:00:00\nXX-build OK 01:00:00\n')
            rc, ran = launch(['--after', 'X-battery', 'R', 'abc123', '4-6', 'B1'])
            if rc != 2 or ran or chain()[-2:] != ['R-build FAILED (skipped: X-battery failed)',
                                                  'R ALL FAILED at build']:
                bad.append(f'--after a failed step: {rc}, ran {ran}, chain {chain()[-2:]}')
            rc, ran = launch(['--after', 'XX-build', '--steps', 'report', 'S', '-', '4-6', 'B1'])
            if rc != 0 or len(ran) != 1:
                bad.append(f'--after a step ended OK: {rc}, ran {ran}')
            later = threading.Timer(0.3, lambda: open(f'{lg}/chain.log', 'a').write('Y-build OK 01:00:01\n'))
            later.start()
            t0 = time.time()
            rc, ran = launch(['--after', 'Y-build', '--steps', 'report', 'T', '-', '4-6', 'B1'])
            later.join()
            if rc != 0 or len(ran) != 1 or time.time() - t0 < 0.3:
                bad.append(f'--after a step ending later: {rc}, ran {ran}, {time.time() - t0:.2f} s')
            # --dry: the commands printed, nothing run or written, the sandbox
            # no bar.
            buf = io.StringIO()
            rc, ran = launch(['--dry', '--logs', f'{d}/lg3', '--after', 'Z-battery', 'U', 'abc123',
                              '4-6', 'B1'], {'TMPDIR': '/tmp/claude-1000'}, out=buf)
            text = buf.getvalue()
            for piece in (f'# waits for "Z-battery OK" or "Z-battery FAILED" in {d}/lg3/chain.log\n',
                          f'{sh} {tools["rebuild"]} --build --work {w} --logs {d}/lg3 U abc123 4-6'
                          f' > {d}/lg3/rebuild-build-U.out 2>&1\n',
                          f'gzip -f {d}/lg3/hadrian-U.log\n',
                          f'{w}/battery/ghcb-U.tsv {d}/lg3/hperf-U.csv WALL > ',
                          f'--a2t-lock {w}/battery-inputs/a2t.lock U U 4-6 > {d}/lg3/battery-U.log',
                          f'{tools["runreport"]} --work {w} B1 U {d}/lg3/report-B1-U.txt'):
                if piece not in text:
                    bad.append(f'--dry lacks {piece!r}')
            if rc != 0 or ran or os.path.exists(f'{d}/lg3'):
                bad.append(f'--dry: {rc}, ran {ran}, {d}/lg3 made: {os.path.exists(f"{d}/lg3")}')
            # Usage errors run nothing.
            for args in (['V', 'abc123', '4-5', 'B1'], ['V', 'abc123', '4-6'],
                         ['--steps', 'report,build', 'V', 'abc123', '4-6', 'B1'],
                         ['--steps', 'bat', 'V', 'abc123', '4-6', 'B1'], ['V', '-', '4-6', 'B1'],
                         ['--cmp', 'A'], ['--frob', 'V', 'abc123', '4-6', 'B1']):
                rc, ran = launch(args)
                if rc != 2 or ran:
                    bad.append(f'{args}: {rc}, ran {ran}')
            # --cmp: nofib's runs at each level, a package's build directory
            # below its ghc-VERSION, its executables, the -O1 directory absent.
            n, v = f'{w}/nofib-r/nofib/_make', f'{w}/vpapi'
            for lab, ver in (('A', 'ghc-10.1.20261101'), ('B', 'ghc-10.1.20261102')):
                for r in (f'c{lab}-{lab}', f'o1-{lab}', f'o0-{lab}'):
                    os.makedirs(f'{n}/{r}')
                e = f'{v}/cdist-c{lab}-{lab}/build/x86_64-linux/{ver}/x-1/b/bench/build/bench'
                os.makedirs(e)
                for f, s in (('bench', 'same'), ('other', lab), ('Main.o', '')):
                    with open(f'{e}/{f}', 'w') as fh:
                        fh.write(s)
                    os.chmod(f'{e}/{f}', 0o755)
            lines = []
            rc = compare(w, f'{d}/lg4', 'A', 'B', say=lines.append)
            cv = f'{v}/cdist-c%s-%s/build/x86_64-linux/ghc-10.1.2026110%d'
            wl = ['nofib O2: compared: --all cA-A cB-B', 'nofib O1: compared: --all o1-A o1-B',
                  'nofib O0: compared: --all o0-A o0-B', 'cdist: compared: --all ghc-10.1.20261101 ghc-10.1.20261102',
                  '  bench: binaries identical', '  other: compared: other other']
            if rc != 0 or lines != wl:
                bad.append(f'--cmp: {rc}, {lines}')
            got = open(fakelog).read().splitlines()
            if f'obj-diff|{os.getcwd()}|--all|{cv % ("A", "A", 1)}|{cv % ("B", "B", 2)}' not in got:
                bad.append(f'--cmp of cdist: {got}')
            if sorted(os.listdir(f'{d}/lg4/cmp-A-B')) != ['bin-cdist-other.txt', 'cdist.txt',
                                                         'nofib-O0.txt', 'nofib-O1.txt', 'nofib-O2.txt']:
                bad.append(f'--cmp\'s files: {sorted(os.listdir(f"{d}/lg4/cmp-A-B"))}')
        finally:
            for k in ('FAKELOG', 'FAKEFAIL'):
                os.environ.pop(k, None)
            TOOLS.clear()
            TOOLS.update(saved[0])
            globals().update(POLL=saved[1], MEMINFO=saved[2])
    for x in bad:
        print('FAIL', x)
    print('ok   label.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
