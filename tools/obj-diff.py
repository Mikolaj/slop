#!/usr/bin/env python3
"""The object and assembly files of two builds by two compilers, compared
with what the compiler's identity puts into them masked.

Usage: python3 tools/obj-diff.py [--all] DIR_A DIR_B
       python3 tools/obj-diff.py --self-test

Every file ending in `.o`, `.dyn_o`, `.p_o` or `.s` under DIR_A is compared
with the file at the same relative path under DIR_B. Masked first, in both:
a GHC version whose third component is a date, as `10.1.20261030`, which
a development GHC takes from its commit's date and writes into an assembly
file's `.ident` and an object's `.comment`; and every run of 64 hex digits,
a cabal unit id's hash, which covers that version and stands in the symbols
of the packages a program links. So builds by compilers from commits
of different dates that generate the same code compare equal, where without
the masks every file differs. Prints the counts, identical, equal once
masked, differing, and the files one side has alone; then the differing
files and those, the first 20 of each, or with --all every one.

Exit 0 when no file differs beyond the masks and both sides hold the same
files, 1 when one differs or one side holds a file the other lacks, 2 when
the run did not happen: a missing directory, or no such file under DIR_A.
"""

import os
import re
import sys
import tempfile

EXTS = ('.o', '.dyn_o', '.p_o', '.s')
MASK = re.compile(rb'(?<![0-9.])[0-9]+\.[0-9]+\.20[0-9]{6}(?![0-9])'
                  rb'|[0-9a-f]{64}')


def files(d):
    """The relative paths of the files under d with one of EXTS."""
    out = set()
    for root, _, fs in os.walk(d):
        out |= {os.path.relpath(os.path.join(root, f), d) for f in fs
                if f.endswith(EXTS)}
    return out


def masked(path):
    with open(path, 'rb') as fh:
        return MASK.sub(b'V', fh.read())


def compare(a, b):
    """(identical, masked-equal, differing, only in a, only in b), each a
    sorted list of relative paths."""
    fa, fb = files(a), files(b)
    same, eq, diff = [], [], []
    for p in sorted(fa & fb):
        x, y = os.path.join(a, p), os.path.join(b, p)
        with open(x, 'rb') as hx, open(y, 'rb') as hy:
            if hx.read() == hy.read():
                same.append(p)
                continue
        (eq if masked(x) == masked(y) else diff).append(p)
    return same, eq, diff, sorted(fa - fb), sorted(fb - fa)


def run(argv):
    """The lines to print and the exit status."""
    every = '--all' in argv
    argv = [x for x in argv if x != '--all']
    if len(argv) != 2:
        return [__doc__.split('\n\n')[1]], 2
    a, b = argv
    for d in (a, b):
        if not os.path.isdir(d):
            return [f'obj-diff: {d}: no such directory'], 2
    same, eq, diff, oa, ob = compare(a, b)
    if not (same or eq or diff or oa):
        return [f'obj-diff: no {"/".join(EXTS)} file under {a}'], 2
    out = [f'compared {len(same) + len(eq) + len(diff)}: identical'
           f' {len(same)}, equal once masked {len(eq)}, differing'
           f' {len(diff)}; only in A {len(oa)}, only in B {len(ob)}']
    for what, ps in (('differs', diff), ('only in A', oa), ('only in B', ob)):
        out += [f'{what}: {p}' for p in (ps if every else ps[:20])]
        if not every and len(ps) > 20:
            out.append(f'{what}: ... {len(ps) - 20} more')
    return out, 1 if diff or oa or ob else 0


def self_test():
    """Two scratch builds: a file equal, one differing in the version
    alone, one in a unit id's hash alone, one in its code, one of another
    kind that differs and is not compared, one under a subdirectory, and
    one only A has; then the two without the differing one, and then
    without the one only A has."""
    bad = []
    h1, h2 = b'a' * 64, b'b' * 64
    tree = {'same.o': (b'\x7fELF code', b'\x7fELF code'),
            'ver.s': (b'mov\n.ident "GHC 10.1.20261028"\n',
                      b'mov\n.ident "GHC 10.1.20261030"\n'),
            'hash.o': (b'pkg-1.0-' + h1 + b'_M_f_info',
                       b'pkg-1.0-' + h2 + b'_M_f_info'),
            'code.dyn_o': (b'add $1', b'add $2'),
            'notes.txt': (b'x', b'y'),
            'sub/deep.p_o': (b'z', b'z'),
            'onlya.s': (b'only', None)}
    with tempfile.TemporaryDirectory() as td:
        a, b = os.path.join(td, 'a'), os.path.join(td, 'b')
        for p, (x, y) in tree.items():
            for d, v in ((a, x), (b, y)):
                if v is not None:
                    os.makedirs(os.path.dirname(os.path.join(d, p)),
                                exist_ok=True)
                    with open(os.path.join(d, p), 'wb') as fh:
                        fh.write(v)
        out, rc = run([a, b])
        want = ['compared 5: identical 2, equal once masked 2, differing 1;'
                ' only in A 1, only in B 0',
                'differs: code.dyn_o', 'only in A: onlya.s']
        if (out, rc) != (want, 1):
            bad.append(f'a differing build: {rc} {out}')
        os.remove(os.path.join(a, 'code.dyn_o'))
        os.remove(os.path.join(b, 'code.dyn_o'))
        out, rc = run([a, b])
        if rc != 1 or out[-1] != 'only in A: onlya.s':
            bad.append(f'a file one side lacks, nothing differing: {rc}'
                       f' {out}')
        os.remove(os.path.join(a, 'onlya.s'))
        out, rc = run([a, b])
        if (out, rc) != (['compared 4: identical 2, equal once masked 2,'
                          ' differing 0; only in A 0, only in B 0'], 0):
            bad.append(f'builds differing in the masked strings alone: {rc}'
                       f' {out}')
        out, rc = run([a, os.path.join(td, 'none')])
        if rc != 2:
            bad.append(f'a missing directory: {rc} {out}')
    for x in bad:
        print('FAIL', x)
    print('self-test', 'FAILED' if bad else 'passed')
    return 1 if bad else 0


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    out, rc = run(argv)
    for line in out:
        print(line, file=sys.stderr if rc == 2 else sys.stdout)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
