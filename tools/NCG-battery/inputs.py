#!/usr/bin/env python3
"""The inputs battery.py's parts read under the work directory, each from
a pin (Mikolaj's rulings 456 and 457, 2026-11-22): a commit of the canonical
upstream repository, a Hackage tarball by version and sha256, a path tracked
under tools/NCG-battery/pins or the output of a generator tracked there, with
our change to upstream's code a patch tracked in pins, applied by patch -p1.
WORK keeps only copies, which this script makes again where they are absent.
A GHC's perf tests are no input: battery.py takes them from the source tree
of the GHC under test.

Usage: python3 tools/NCG-battery/inputs.py [--work DIR] [--cache DIR] ensure [NAME...]
       python3 tools/NCG-battery/inputs.py [--work DIR] [--cache DIR] check [NAME...]
       python3 tools/NCG-battery/inputs.py [--cache DIR] materialize NAME DIR
       python3 tools/NCG-battery/inputs.py list
       python3 tools/NCG-battery/inputs.py generated SCRIPT
       python3 tools/NCG-battery/inputs.py --self-test

ensure, for each NAME or every input, puts an absent destination in place:
the pin's tree, fetched into the cache (--cache, WORK/battery-inputs/cache
by default) where it is not there yet, the patch applied, the row's files
tracked in pins added, then the stamp WORK/battery-inputs/stamps/NAME naming
the pin; nofib's then builds nofib-run in it, by GHC 9.12.4, where its binary
is absent. nofib's added files are pins/nofib-run.project as the project file
cabal.project.nofib-run, which nofib-run's build names and which imports
nofib's cabal.project, and pins/nofib-run.freeze beside it as
cabal.project.nofib-run.freeze: nofib-run's dependencies, their flags and the
index-state, as its build plan resolved them on 2026-11-22. The freeze is not
cabal.project.freeze, which nofib-run's own runs would read when they install
the benchmarks' dependencies through cabal.project by the compiler under test,
whose base it does not admit. A destination present with its stamp is taken
as it is. One present without it, such as the copies made before this script,
is checked against the pin, as check does, the row's added files put in place
first where absent, and stamped once it passes; one stamped with another pin,
a patch or a tracked file having changed since, is checked the same way, and
moving it aside is left to whoever reads the failure. check compares each present
destination with its pin, stamp or none: every file of the pin's tree there
and equal, and no other file but the row's build products, and writes
nothing under WORK but the cache. materialize puts NAME's pin at DIR, which must not
exist, and runs nothing of it but a generate row's script. generated runs
SCRIPT, the generator a row names, into a scratch file and checks the
output's sha256 against the row's pin. ensure, check and generated exit 0
when every input named passed, 1 when one failed and 2 on bad usage.
--self-test runs ensure and check over planted rows of each kind, with no
network, a row's added files as nofib's freeze among them, and checks that
the table's pins exist and that nofib-run's build names nofib's added project
file.
"""

import collections
import contextlib
import fcntl
import fnmatch
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PINS = os.path.join(HERE, 'pins')
WORK = '/home/mikolaj/slop/dist-ghcho'  # battery.py's
HACKAGE = 'https://hackage.haskell.org/package'
STORE = 'battery-inputs'  # under WORK: cache/, stamps/ and lock
# what nofib's row builds in its destination by NOFIB_RUN_BUILD, battery.py's NOFIB_RUN
NOFIB_RUN = ('dist-newstyle/build/x86_64-linux/ghc-9.12.4/nofib-0.1.0.0/x/nofib-run/build/'
             'nofib-run/nofib-run')
# nofib-run's dependencies frozen (chat item 7968.3, Mikolaj's ruling 458): its
# own project file, cabal reading PROJECT.freeze beside it, and not nofib's
# cabal.project.freeze, which nofib-run's runs would read too, installing the
# benchmarks' dependencies by the compiler under test through cabal.project
NOFIB_PROJECT = 'cabal.project.nofib-run'
NOFIB_RUN_BUILD = ['cabal', 'build', '-w', 'ghc-9.12.4', '--project-file=' + NOFIB_PROJECT,
                   'nofib-run']
# the placeholders the sessions' sandboxes leave in a destination, every row's
PRODUCTS = ('.claude/*',)

# kind git: source the repository's URL, ref the commit; hackage: source
# PACKAGE-VERSION, ref the tarball's sha256; tracked: source a path under
# pins; generate: source a script under pins run with the output's path,
# ref the output's sha256. dest is under WORK, extra the globs of build
# products a check passes over there; add the files tracked under pins
# put into the tree after the patch, each (source, path in the tree).
Input = collections.namedtuple('Input', 'name kind source ref patch dest extra add',
                               defaults=((),))
INPUTS = (
    # A2T, battery.py's setting 11: the branch ncg-benchmark-a2t-cells of the fork
    Input('a2t', 'git', 'https://github.com/Mikolaj/orthotope.git',
          'b96e3f0c59c2734e693ac340867cbc21fae7352d', None, 'vpapi/a2t',
          ('cabal.project.*',)),
    Input('a2t-cells', 'tracked', 'a2t-cells.txt', None, None, 'vpapi/a2t-cells.txt', ()),
    # the two tables p103's A2T binary printed, battery.py's setting 17,
    # from which a2t-full and a2t-groups size every label's N alike
    Input('a2t-tables', 'tracked', 'a2t-tables', None, None, 'vpapi/a2t-tables', ()),
    # !16269's genManyBasicBlocks, as compile-cost.py's cell MBB
    Input('mbb', 'generate', 'gen-ManyBasicBlocks.py',
          '442291b8e445cdff326238a7d45a275e637ae412fd147a75afbe7c2239091bab', None,
          'battery-inputs/ManyBasicBlocks.cmm', ()),
    # the nofib ~/slop/ghc's gitlink names; the make build's leftovers and
    # the outputs runs write beside the programs are products
    Input('nofib', 'git', 'https://gitlab.haskell.org/ghc/nofib.git',
          'd4750745a96ee293612cef0fedd8ed2c9ae8d1a0', None, 'nofib-r/nofib',
          ('_make/*', 'dist-newstyle/*', '.git', '*.depend', '*.depend.bak', 'local.env',
           'runstdtest/runstdtest', '*.stdout', '*.stdin', '*.faststdin', '*.faststdout',
           'real/ben-raytrace/out.ppm', 'real/maillist/runtime_files/*.tex'),
          (('nofib-run.project', NOFIB_PROJECT), ('nofib-run.freeze', NOFIB_PROJECT + '.freeze'))),
    # GHC's submodule at the series' base
    Input('containers', 'git', 'https://github.com/haskell/containers.git',
          '953428ad079d5708df696442f9bdeaccd1acfc6c', None, 'vpapi/ctr/containers', ()),
    Input('tasty-bench-papi', 'tracked', 'tasty-bench-papi', None, None,
          'vpapi/ctr/tasty-bench-papi', ()),
    # vector-bench-papi is upstream's
    Input('vector', 'git', 'https://github.com/haskell/vector.git',
          'd0f42e056202fa24b479833dbc21222c1964d096', None, 'vpapi/src',
          ('.git/*', 'cabal.project.*')),
    # bench-memory deleted, so that cabal does not solve its weigh dependency,
    # nor the compiler under test build it: the battery runs bench-speed alone
    Input('megaparsec', 'hackage', 'megaparsec-9.8.1',
          'e05c71a12a085b8e87f156dfee4a9a7c8cbd483a3abe9c779f921d0563b97aa8',
          'megaparsec-9.8.1.patch', 'vpapi/mtr/megaparsec-9.8.1', ()),
    # 1.2.2.0, its mappend the default, where 1.2.1.0's noncanonical one,
    # which GHC's master rejects, took a patch (Mikolaj's ruling 465)
    Input('case-insensitive', 'hackage', 'case-insensitive-1.2.2.0',
          '54125d4bfa3199730787e050dde8ee5e0e2e28a07f67adcae89f72f3f5d132cc', None,
          'vpapi/mtr/case-insensitive-1.2.2.0', ()),
    Input('criterion-papi', 'tracked', 'criterion-papi', None, None,
          'vpapi/mtr/criterion-papi', ()),
    # settle2, findings 499 to 501: Shimuuar/tasty-papi#7 in an earlier form,
    # the PR open and unreleased on 2026-11-22
    Input('tasty-papi', 'hackage', 'tasty-papi-0.1.2.0',
          'ca6702f376411b1620c7df65d27d9e32111c0b4317abb38ffc72307f55f7c715',
          'tasty-papi-settle2.patch', 'vpapi/tasty-papi-settle2', ()),
)
BY_NAME = {x.name: x for x in INPUTS}
# the inputs each of battery.py's part families reads
NEEDS = {'nofib': ('nofib',),
         'containers': ('containers', 'tasty-bench-papi', 'tasty-papi'),
         'vector': ('vector', 'tasty-papi'),
         'megaparsec': ('megaparsec', 'case-insensitive', 'criterion-papi', 'tasty-papi'),
         'a2t': ('a2t', 'a2t-cells'), 'a2t-full': ('a2t', 'a2t-tables'),
         'a2t-groups': ('a2t', 'a2t-tables'),
         'comp1': ('mbb',), 'comp2': ('mbb',)}


def needs(parts):
    """The inputs of battery.py's parts, every input's for the whole battery."""
    if not parts:
        return [x.name for x in INPUTS]
    want = {n for p in parts for n in NEEDS.get(p.partition(':')[0].partition('-O')[0], ())}
    return [x.name for x in INPUTS if x.name in want]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def files(top):
    """{relative path: absolute path} of the files and symlinks under top,
    or of top itself where it is a file."""
    if not os.path.isdir(top):
        return {'': top}
    out = {}
    for r, ds, fs in os.walk(top):
        for f in fs + [d for d in ds if os.path.islink(os.path.join(r, d))]:
            p = os.path.join(r, f)
            out[os.path.relpath(p, top)] = p
    return out


def tree_digest(top):
    h = hashlib.sha256()
    for rel, p in sorted(files(top).items()):
        h.update(f'{rel}\0{sha256(p)}\0'.encode())
    return h.hexdigest()


def pin_id(x):
    """The stamp's text: the pin, its patch's, a tracked source's and the added
    files' digests."""
    src = os.path.join(PINS, x.source)
    ref = tree_digest(src) if x.kind == 'tracked' else x.ref
    if x.kind == 'generate':
        ref += ' ' + sha256(src)
    patch = sha256(os.path.join(PINS, x.patch)) if x.patch else '-'
    add = ''.join(f' add {d} {sha256(os.path.join(PINS, s))}' for s, d in x.add)
    return f'{x.name} {x.kind} {x.source} {ref} patch {patch}{add}\n'


def run(argv, **kw):
    p = subprocess.run(argv, capture_output=True, text=True, **kw)
    if p.returncode:
        raise RuntimeError(f'{" ".join(argv)}: exit {p.returncode}: {p.stderr.strip()[-300:]}')
    return p.stdout


def fetch_git(x, cache):
    repo = os.path.join(cache, x.name + '.git')
    if not os.path.isdir(repo):
        run(['git', 'init', '-q', '--bare', repo])
    if subprocess.run(['git', '-C', repo, 'cat-file', '-e', x.ref + '^{commit}'],
                      capture_output=True).returncode:
        run(['git', '-C', repo, 'fetch', '-q', '--depth', '1', x.source, x.ref])
    return repo


def fetch_hackage(x, cache, hackage):
    path = os.path.join(cache, 'hackage', x.source + '.tar.gz')
    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with urllib.request.urlopen(f'{hackage}/{x.source}/{x.source}.tar.gz') as r, \
                open(path + '.part', 'wb') as fh:
            shutil.copyfileobj(r, fh)
        os.replace(path + '.part', path)
    if sha256(path) != x.ref:
        raise RuntimeError(f'{path}: sha256 {sha256(path)}, not {x.ref}')
    return path


def materialize(x, cache, dest, hackage=HACKAGE):
    """x's pin put at dest, which must not exist; nothing of it run."""
    if os.path.lexists(dest):
        raise RuntimeError(f'{dest} exists')
    parent = os.path.dirname(os.path.abspath(dest))
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=f'.{x.name}-', dir=parent)
    try:
        new = os.path.join(tmp, 'new')
        if x.kind == 'git':
            repo = fetch_git(x, cache)
            os.makedirs(new)
            arch = subprocess.Popen(['git', '-C', repo, 'archive', x.ref], stdout=subprocess.PIPE)
            tar = subprocess.run(['tar', '-x', '-C', new], stdin=arch.stdout, capture_output=True)
            arch.stdout.close()
            if arch.wait() or tar.returncode:
                raise RuntimeError(f'git archive {x.ref} of {repo} failed')
        elif x.kind == 'hackage':
            with tarfile.open(fetch_hackage(x, cache, hackage)) as t:
                t.extractall(tmp, filter='data')
            os.rename(os.path.join(tmp, x.source), new)
        elif x.kind == 'tracked':
            src = os.path.join(PINS, x.source)
            if os.path.isdir(src):
                shutil.copytree(src, new)
            else:
                shutil.copy2(src, new)
        else:
            run([sys.executable, '-I', os.path.join(PINS, x.source), new])
            if sha256(new) != x.ref:
                raise RuntimeError(f'{x.source} wrote sha256 {sha256(new)}, not {x.ref}')
        if x.patch:
            with open(os.path.join(PINS, x.patch)) as fh:
                run(['patch', '-p1', '-s', '--forward', '--batch', '-d', new], stdin=fh)
        put_added(x, new)
        os.rename(new, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def put_added(x, top):
    """x's added files put under top where absent; the paths put."""
    out = []
    for s, d in x.add:
        if not os.path.lexists(os.path.join(top, d)):
            shutil.copy2(os.path.join(PINS, s), os.path.join(top, d))
            out.append(d)
    return out


def compare(x, pin, dest):
    """What differs between pin, x materialized, and dest: a file of the pin
    missing or other at dest, or a file at dest neither the pin's nor
    a product."""
    a, b = files(pin), files(dest)
    bad = []
    for rel, p in sorted(a.items()):
        q = b.get(rel)
        if q is None:
            bad.append(f'missing {rel or dest}')
        elif os.path.islink(p) or os.path.islink(q):
            if not (os.path.islink(p) and os.path.islink(q) and os.readlink(p) == os.readlink(q)):
                bad.append(f'other {rel}')
        elif sha256(p) != sha256(q):
            bad.append(f'other {rel or dest}')
    globs = PRODUCTS + x.extra
    bad += [f'extra {rel}' for rel in sorted(b) if rel not in a
            and not any(fnmatch.fnmatchcase(rel, g) for g in globs)]
    return bad


def check_one(x, work, cache, hackage=HACKAGE):
    """dest against the pin materialized beside the cache: the differences."""
    dest = os.path.join(work, x.dest)
    os.makedirs(cache, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f'check-{x.name}-', dir=cache) as d:
        materialize(x, cache, os.path.join(d, 'pin'), hackage)
        return compare(x, os.path.join(d, 'pin'), dest)


@contextlib.contextmanager
def locked(work):
    os.makedirs(os.path.join(work, STORE), exist_ok=True)
    with open(os.path.join(work, STORE, 'lock'), 'a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def ensure(work, names, cache=None, hackage=HACKAGE, say=print, build=NOFIB_RUN_BUILD):
    """ensure's: each input in place and stamped; the failures."""
    cache = cache or os.path.join(work, STORE, 'cache')
    stamps = os.path.join(work, STORE, 'stamps')
    bad = []
    with locked(work):
        os.makedirs(stamps, exist_ok=True)
        for name in names:
            x = BY_NAME[name]
            dest, stamp = os.path.join(work, x.dest), os.path.join(stamps, name)
            pid = pin_id(x)
            try:
                have = open(stamp).read() if os.path.isfile(stamp) else None
                if not os.path.lexists(dest):
                    materialize(x, cache, dest, hackage)
                    say(f'inputs: {name} put at {dest}')
                elif have != pid:
                    for d in put_added(x, dest):
                        say(f'inputs: {name}: {d} put in {dest}')
                    diff = check_one(x, work, cache, hackage)
                    if diff:
                        bad.append(f'{name}: {dest} is not its pin: {"; ".join(diff[:5])}'
                                   + (f'; {len(diff) - 5} more' if len(diff) > 5 else ''))
                        continue
                    say(f'inputs: {name} at {dest} checked against its pin')
                with open(stamp, 'w') as fh:
                    fh.write(pid)
                if name == 'nofib' and not os.path.isfile(os.path.join(dest, NOFIB_RUN)):
                    say(f'inputs: building nofib-run in {dest}')
                    with open(os.path.join(dest, '..', 'build-nofib-run.log'), 'a') as log:
                        if subprocess.run(build, cwd=dest, stdout=log, stderr=log).returncode \
                                or not os.path.isfile(os.path.join(dest, NOFIB_RUN)):
                            bad.append(f'nofib: {" ".join(build)} in {dest} built no {NOFIB_RUN}')
            except (OSError, RuntimeError, tarfile.TarError) as e:
                bad.append(f'{name}: {e}')
    return bad


def absent(work, names):
    """The inputs whose destinations are absent, which ensure would put in place."""
    return [n for n in names if not os.path.lexists(os.path.join(work, BY_NAME[n].dest))]


def check(work, names, cache=None, hackage=HACKAGE):
    """check's: each present input against its pin, stamp or none; the failures."""
    cache = cache or os.path.join(work, STORE, 'cache')
    bad = []
    for name in names:
        x = BY_NAME[name]
        dest = os.path.join(work, x.dest)
        try:
            diff = check_one(x, work, cache, hackage) if os.path.lexists(dest) else ['absent']
        except (OSError, RuntimeError, tarfile.TarError) as e:
            diff = [str(e)]
        bad += [f'{name}: {d}' for d in diff]
        print(f'{name}: {"ok" if not diff else f"{len(diff)} differences"}')
    return bad


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    work, cache = WORK, None
    while argv[:1] and argv[0] in ('--work', '--cache') and len(argv) > 1:
        work, cache = (argv[1], cache) if argv[0] == '--work' else (work, argv[1])
        argv = argv[2:]
    work = os.path.abspath(work)
    cache = cache and os.path.abspath(cache)
    cmd, names = (argv[0], argv[1:]) if argv else (None, [])
    if cmd == 'list' and not names:
        for x in INPUTS:
            print('\t'.join([x.name, x.kind, x.source, x.ref or '-', x.patch or '-', x.dest]))
        return 0
    if cmd == 'materialize' and len(names) == 2 and names[0] in BY_NAME:
        try:
            materialize(BY_NAME[names[0]], cache or os.path.join(work, STORE, 'cache'),
                        os.path.abspath(names[1]))
        except (OSError, RuntimeError, tarfile.TarError) as e:
            print(e, file=sys.stderr)
            return 1
        return 0
    if cmd == 'generated' and len(names) == 1:
        rows = [x for x in INPUTS if x.kind == 'generate' and os.path.realpath(
            os.path.join(PINS, x.source)) == os.path.realpath(names[0])]
        if not rows:
            print(f'no generate row names {names[0]}', file=sys.stderr)
            return 2
        with tempfile.TemporaryDirectory(prefix='ncg-generated-') as d:
            try:
                materialize(rows[0], os.path.join(d, 'cache'), os.path.join(d, 'out'))
            except (OSError, RuntimeError) as e:
                print(f'{rows[0].name}: {e}', file=sys.stderr)
                return 1
        print(f'{rows[0].name}: {names[0]} writes its pin')
        return 0
    if cmd not in ('ensure', 'check') or [n for n in names if n not in BY_NAME]:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    names = names or [x.name for x in INPUTS]
    bad = ensure(work, names, cache) if cmd == 'ensure' else check(work, names, cache)
    for x in bad:
        print('FAIL', x)
    return 1 if bad else 0


# --- self-test: rows over a local repository, a tarball in the cache, files
# tracked in a planted pins, one of them added to a row, and a generator,
# no network.

def self_test():
    global PINS
    bad = []
    with tempfile.TemporaryDirectory(prefix='ncg-inputs-') as d:
        pins, up, w, cache = (os.path.join(d, x) for x in ('pins', 'up', 'w', 'cache'))
        for x in (pins + '/pk', up, w):
            os.makedirs(x)

        def put(path, text):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as fh:
                fh.write(text)
        put(f'{up}/a.txt', 'one\n')
        put(f'{up}/sub/b.txt', 'two\n')
        ident = ['-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        for args in (['init', '-q'], ['add', '.'], [*ident, 'commit', '-qm', 'x']):
            run(['git', '-C', up, *args])
        head = run(['git', '-C', up, 'rev-parse', 'HEAD']).strip()
        put(f'{d}/p-1/x.cabal', 'name: p\n')
        os.makedirs(f'{cache}/hackage')
        with tarfile.open(f'{cache}/hackage/p-1.tar.gz', 'w:gz') as t:
            t.add(f'{d}/p-1', 'p-1')
        tsha = sha256(f'{cache}/hackage/p-1.tar.gz')
        put(f'{pins}/p.patch', '--- a/x.cabal\n+++ b/x.cabal\n@@ -1 +1 @@\n-name: p\n+name: q\n')
        put(f'{pins}/pk/m.hs', 'module M where\n')
        put(f'{pins}/fz', 'constraints: any.a ==1\n')
        put(f'{pins}/gen.py', 'import sys\nopen(sys.argv[1], "w").write("cmm\\n")\n')
        gsha = hashlib.sha256(b'cmm\n').hexdigest()
        rows = (Input('g', 'git', up, head, None, 'r/g', ('*.o',)),
                Input('h', 'hackage', 'p-1', tsha, 'p.patch', 'r/h', ()),
                Input('t', 'tracked', 'pk', None, None, 'r/t', ()),
                Input('m', 'generate', 'gen.py', gsha, None, 'r/m.cmm', ()),
                Input('nofib', 'tracked', 'pk', None, None, 'r/n', ('dist-newstyle/*',),
                      (('fz', 'p.freeze'),)))
        saved = dict(BY_NAME), PINS
        BY_NAME.clear()
        BY_NAME.update({x.name: x for x in rows})
        PINS = pins
        said = []
        fake = [sys.executable, '-c', 'import os; p = "' + NOFIB_RUN + '";'
                ' os.makedirs(os.path.dirname(p)); open(p, "w").close()']
        try:
            def go(names=('g', 'h', 't', 'm'), build=fake):
                said.clear()
                return ensure(w, names, cache, 'http://nowhere.invalid', said.append, build)
            # Absent: each materialized, patched and stamped; nofib-run built.
            r = go(('g', 'h', 't', 'm', 'nofib'))
            want = {'r/g/a.txt': 'one\n', 'r/g/sub/b.txt': 'two\n', 'r/h/x.cabal': 'name: q\n',
                    'r/t/m.hs': 'module M where\n', 'r/m.cmm': 'cmm\n',
                    'r/n/p.freeze': 'constraints: any.a ==1\n'}
            have = {k: open(f'{w}/{k}').read() for k in want if os.path.isfile(f'{w}/{k}')}
            stamped = sorted(os.listdir(f'{w}/{STORE}/stamps'))
            if r or have != want or stamped != ['g', 'h', 'm', 'nofib', 't'] \
                    or not os.path.isfile(f'{w}/r/n/{NOFIB_RUN}'):
                bad.append(f'materialized: {r}, {have}, stamps {stamped}')
            if absent(w, ('g', 'm')) or absent(f'{w}/r', ('g', 'm')) != ['g', 'm']:
                bad.append(f'absent gave {absent(f"{w}/r", ("g", "m"))}')
            # Stamped: taken as they are, even changed, and fetched from nowhere.
            put(f'{w}/r/g/a.txt', 'changed\n')
            if go() or said:
                bad.append(f'stamped inputs checked again: {said}')
            # check sees the change and a stray file, ensure without the stamp
            # refuses it, and a product is passed over.
            put(f'{w}/r/g/x.o', '')
            put(f'{w}/r/g/stray', '')
            with contextlib.redirect_stdout(open(os.devnull, 'w')):
                c = check(w, ['g', 'h'], cache)
            if c != ['g: other a.txt', 'g: extra stray']:
                bad.append(f'check found {c}')
            os.unlink(f'{w}/{STORE}/stamps/g')
            r = go(('g',))
            if len(r) != 1 or 'other a.txt; extra stray' not in r[0] \
                    or os.path.isfile(f'{w}/{STORE}/stamps/g'):
                bad.append(f'a changed copy without its stamp: {r}')
            # Unstamped but equal, the copies made before: checked and stamped.
            put(f'{w}/r/g/a.txt', 'one\n')
            os.unlink(f'{w}/r/g/stray')
            if go(('g',)) or not os.path.isfile(f'{w}/{STORE}/stamps/g') \
                    or said != [f'inputs: g at {w}/r/g checked against its pin']:
                bad.append(f'an equal copy without its stamp: {said}')
            # A patch changed moves the pin: the old copy is checked and refused.
            put(f'{pins}/p.patch', open(f'{pins}/p.patch').read().replace('+name: q', '+name: z'))
            r = go(('h',))
            if len(r) != 1 or 'other x.cabal' not in r[0]:
                bad.append(f'a stale stamp: {r}')
            # A tarball other than its sha256, or a generator's output, fails.
            for rel, row in (('hackage/p-1.tar.gz', 'h'), (None, 'm')):
                if rel:
                    with open(f'{cache}/{rel}', 'ab') as fh:
                        fh.write(b'x')
                else:
                    put(f'{pins}/gen.py', 'import sys\nopen(sys.argv[1], "w").write("c\\n")\n')
                dest = f'{w}/{BY_NAME[row].dest}'
                shutil.rmtree(dest, ignore_errors=True)
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(dest)
                r = go((row,))
                if len(r) != 1 or 'sha256' not in r[0] or os.path.lexists(dest):
                    bad.append(f'{row} with a wrong sha256: {r}')
            # nofib-run's build failing fails nofib.
            shutil.rmtree(f'{w}/r/n/dist-newstyle')
            if len(go(('nofib',), build=['false'])) != 1:
                bad.append('a failed nofib-run build passed')
            # An added file absent from an unstamped copy is put in place
            # before the check; check finds it missing; one of an older pin,
            # the stamp moving with the pin, is refused.
            frz = f'{w}/r/n/p.freeze'
            os.unlink(f'{w}/{STORE}/stamps/nofib')
            with contextlib.suppress(FileNotFoundError):
                os.unlink(frz)
            if go(('nofib',)) or f'inputs: nofib: p.freeze put in {w}/r/n' not in said \
                    or not os.path.isfile(frz) or open(frz).read() != 'constraints: any.a ==1\n':
                bad.append(f'an added file absent: {said}')
            with contextlib.suppress(FileNotFoundError):
                os.unlink(frz)
            with contextlib.redirect_stdout(open(os.devnull, 'w')):
                c = check(w, ['nofib'], cache)
            if c != ['nofib: missing p.freeze']:
                bad.append(f'check of an absent added file found {c}')
            put(frz, 'constraints: any.a ==1\n')
            put(f'{pins}/fz', 'constraints: any.a ==2\n')
            r = go(('nofib',))
            if len(r) != 1 or 'other p.freeze' not in r[0]:
                bad.append(f'an added file of an older pin: {r}')
        finally:
            BY_NAME.clear()
            BY_NAME.update(saved[0])
            PINS = saved[1]
        # The table: every pin under pins, every part family's names rows.
        for x in INPUTS:
            for rel in (x.source if x.kind in ('tracked', 'generate') else None, x.patch,
                        *[s for s, _ in x.add]):
                if rel and not os.path.exists(os.path.join(PINS, rel)):
                    bad.append(f'{x.name}: no {rel} under {PINS}')
        # nofib-run's build names the project file nofib's row adds, beside its
        # freeze, and no other.
        adds = [d for _, d in BY_NAME['nofib'].add]
        if adds != [NOFIB_PROJECT, NOFIB_PROJECT + '.freeze'] \
                or [a for a in NOFIB_RUN_BUILD if a.startswith('--project-file')] \
                != ['--project-file=' + NOFIB_PROJECT]:
            bad.append(f'nofib adds {adds}, its build {NOFIB_RUN_BUILD}')
        if needs(['containers-O1:build', 'comp2']) != ['mbb', 'containers', 'tasty-bench-papi',
                                                         'tasty-papi'] \
                or needs(['perf', 'scale']) != [] or len(needs([])) != len(INPUTS):
            bad.append(f'needs gave {needs(["containers-O1:build", "comp2"])}')
    for x in bad:
        print('FAIL', x)
    print('ok   inputs.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
