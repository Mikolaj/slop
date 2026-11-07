#!/usr/bin/env python3
"""The object and assembly files of two builds by two compilers, compared
with what the compiler's identity puts into them masked.

Usage: python3 tools/obj-diff.py [--all] [--ext EXT]... [--procs] [--show REGEX]
           DIR_A DIR_B
       python3 tools/obj-diff.py [--all] [--procs] [--show REGEX] FILE_A FILE_B
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

Two files are compared alone, under FILE_A's name. --ext EXT, repeatable,
compares the files ending in EXT in place of those four, as --ext .dump-asm
the assembly GHC writes under -ddump-asm -ddump-to-file, whose timestamp lines,
as `2026-11-07 19:16:49.189756588 UTC`, are masked too.

--procs follows each differing assembly file, one holding no NUL byte, with
its procedures that differ. The file, masked, is split at every line starting
`.section`; a unit is named by its first label, a line `NAME:` at column 0,
or else by its first line, a later unit of the same name primed; blank lines,
the dump's `====` headers and timestamps are dropped; and the labels a unit
defines, its name apart, are renumbered L0, L1, ... by first appearance,
so that a unit equal but for its own labels' uniques compares equal, while
a reference to a label defined in another unit is compared as written. Under
the file's line, each unit that differs is printed `  differs: NAME a -> b`,
a and b its instruction counts (the lines starting with a tab and no `.`),
one only a side holds `  only in A: NAME a` or `  only in B: NAME b`, the first
20 unless --all; where no unit differs, `  no procedure differs once local
labels are renumbered`. --show REGEX, implying --procs, keeps the units whose
name REGEX matches (re.search) and prints each one's unified diff of the units
as compared, A's normalised text against B's.

Exit 0 when no file differs beyond the masks and both sides hold the same
files, 1 when one differs or one side holds a file the other lacks, 2 when
the run did not happen: a missing directory, a bad option, or no such file
under DIR_A.
"""

import difflib
import os
import re
import sys
import tempfile

EXTS = ('.o', '.dyn_o', '.p_o', '.s')
MASK = re.compile(rb'(?<![0-9.])[0-9]+\.[0-9]+\.20[0-9]{6}(?![0-9])'
                  rb'|[0-9a-f]{64}')
STAMP = re.compile(rb'(?m)^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}'
                   rb'(\.[0-9]+)? UTC$')
LIMIT = 20
LABEL = re.compile(r'([\w.$]+):')
TOKEN = re.compile(r'[\w.$]+')


def files(d, exts=EXTS):
    """The relative paths of the files under d with one of exts, each
    mapped to its path."""
    out = {}
    for root, _, fs in os.walk(d):
        for f in fs:
            if f.endswith(exts):
                out[os.path.relpath(os.path.join(root, f), d)] = os.path.join(root, f)
    return out


def masked(path):
    with open(path, 'rb') as fh:
        return STAMP.sub(b'T', MASK.sub(b'V', fh.read()))


def compare(fa, fb):
    """(identical, masked-equal, differing, only in a, only in b), each a
    sorted list of the relative paths of fa and fb, files' maps."""
    same, eq, diff = [], [], []
    for p in sorted(fa.keys() & fb.keys()):
        x, y = fa[p], fb[p]
        with open(x, 'rb') as hx, open(y, 'rb') as hy:
            if hx.read() == hy.read():
                same.append(p)
                continue
        (eq if masked(x) == masked(y) else diff).append(p)
    return same, eq, diff, sorted(fa.keys() - fb.keys()), sorted(fb.keys() - fa.keys())


def units(text):
    """The procedures of an assembly text, --procs': (name, normalised lines)
    in the text's order."""
    raw, cur = [], []
    for line in text.split('\n'):
        if line.startswith('.section') and cur:
            raw.append(cur)
            cur = []
        if line.strip() and not line.startswith('====') and not STAMP.match(line.encode()):
            cur.append(line)
    if cur:
        raw.append(cur)
    out, seen = [], set()
    for lines in raw:
        defs = [m.group(1) for m in map(LABEL.fullmatch, lines) if m]
        name = defs[0] if defs else lines[0]
        while name in seen:
            name += "'"
        seen.add(name)
        own, num = set(defs[1:]) - set(defs[:1]), {}

        def sub(m):
            t = m.group(0)
            k, pre = (t, '') if t in own or not t.startswith('$') else (t[1:], '$')
            if k not in own:
                return t
            num.setdefault(k, f'L{len(num)}')
            return pre + num[k]
        out.append((name, [TOKEN.sub(sub, x) for x in lines]))
    return out


def instructions(lines):
    return sum(1 for x in lines if x.startswith('\t') and not x.startswith('\t.'))


def procs(x, y, show, every):
    """The lines of --procs (and --show) under a differing file, x and y
    the two paths; none where the file is not an assembly text."""
    with open(x, 'rb') as hx, open(y, 'rb') as hy:
        ta, tb = MASK.sub(b'V', hx.read()), MASK.sub(b'V', hy.read())
    if b'\0' in ta or b'\0' in tb:
        return []
    ua = units(ta.decode('utf-8', 'replace'))
    ub = units(tb.decode('utf-8', 'replace'))
    da, db = dict(ua), dict(ub)
    rows = []
    for name, la in ua:
        if name not in db:
            rows.append((name, f'  only in A: {name} {instructions(la)}', la, []))
        elif la != db[name]:
            rows.append((name, f'  differs: {name} {instructions(la)} ->'
                               f' {instructions(db[name])}', la, db[name]))
    rows += [(name, f'  only in B: {name} {instructions(lb)}', [], lb)
             for name, lb in ub if name not in da]
    if not rows:
        return ['  no procedure differs once local labels are renumbered']
    if show is not None:
        rows = [r for r in rows if show.search(r[0])]
    out = []
    for name, line, la, lb in (rows if every else rows[:LIMIT]):
        out.append(line)
        if show is not None:
            out += ['    ' + d for d in difflib.unified_diff(
                la, lb, f'A {name}', f'B {name}', n=3, lineterm='')]
    if not every and len(rows) > LIMIT:
        out.append(f'  ... {len(rows) - LIMIT} more')
    return out


def run(argv):
    """The lines to print and the exit status."""
    every, exts, by_proc, show, pos = False, [], False, None, []
    usage = [__doc__.split('\n\n')[1]], 2
    while argv:
        x, argv = argv[0], argv[1:]
        if x == '--all':
            every = True
        elif x == '--procs':
            by_proc = True
        elif x in ('--ext', '--show'):
            if not argv:
                return usage
            if x == '--ext':
                exts.append(argv[0])
            else:
                try:
                    show = re.compile(argv[0])
                except re.error as e:
                    return [f'obj-diff: --show {argv[0]!r}: {e}'], 2
                by_proc = True
            argv = argv[1:]
        else:
            pos.append(x)
    if len(pos) != 2:
        return usage
    a, b = pos
    exts = tuple(exts) or EXTS
    if os.path.isfile(a) and os.path.isfile(b):
        fa, fb = {os.path.basename(a): a}, {os.path.basename(a): b}
    else:
        for d in (a, b):
            if not os.path.isdir(d):
                return [f'obj-diff: {d}: no such directory'], 2
        fa, fb = files(a, exts), files(b, exts)
    same, eq, diff, oa, ob = compare(fa, fb)
    if not (same or eq or diff or oa):
        return [f'obj-diff: no {"/".join(exts)} file under {a}'], 2
    out = [f'compared {len(same) + len(eq) + len(diff)}: identical'
           f' {len(same)}, equal once masked {len(eq)}, differing'
           f' {len(diff)}; only in A {len(oa)}, only in B {len(ob)}']
    for what, ps in (('differs', diff), ('only in A', oa), ('only in B', ob)):
        for p in (ps if every else ps[:LIMIT]):
            out.append(f'{what}: {p}')
            if what == 'differs' and by_proc:
                out += procs(fa[p], fb[p], show, every)
        if not every and len(ps) > LIMIT:
            out.append(f'{what}: ... {len(ps) - LIMIT} more')
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
    with tempfile.TemporaryDirectory() as td:
        procs_test(td, bad)
    for x in bad:
        print('FAIL', x)
    print('self-test', 'FAILED' if bad else 'passed')
    return 1 if bad else 0


HEAD = '\n==================== Asm code ====================\n{}\n\n'
STR = '.section .rodata.str,"aMS",@progbits,1\n.align 1\n{}:\n\t.string "x"\n'
F = ('.section .text\n.align 8\nM_f_info:\n{0}:\n\tleaq -24(%rbp),%rax\n\tjb {1}\n'
     '\tmovq ${2},(%rbp)\n{1}:\n\tjmp *-8(%r13)\n{2}:\n\tret\n')
E = '.section .text\nM_e_info:\n\tleaq {}(%rip),%rbx\n\tret\n'
G = '.section .text\nM_g_info:\n\tmovq ${},%rax\n\tret\n'


def procs_test(td, bad):
    """--ext, the dump's timestamps, two files, --procs and --show: a module's
    dumps by two compilers, its string and M_f equal but for their stamps and
    M_f's own labels, M_e differing in a reference to a label of another unit,
    M_g in an instruction, M_h only A has, M_k only B has, and the data unit
    M_d_closure differing; a dump differing in its stamps alone; one in its
    local labels alone; and one with more differing procedures than are
    printed."""
    t1, t2 = '2026-11-07 19:16:49.189756588 UTC', '2026-11-08 00:01:02 UTC'
    common = HEAD.format(t1) + STR.format('.Lr1_bytes')
    a = (common + HEAD.format(t1) + F.format('.LQ12', '.LQ16', '.Lblock_Q1e_info')
         + E.format('.Lr1_bytes') + G.format(1) + '.section .text\nM_h_info:\n\tret\n'
         + '.section .data\nM_d_closure:\n\t.quad 1\n')
    b = (common.replace(t1, t2) + HEAD.format(t2)
         + F.format('.LQ99', '.LQ77', '.Lblock_Q2x_info')
         + E.format('.Lr2_bytes') + G.format(2) + '.section .data\nM_d_closure:\n\t.quad 2\n'
         + '.section .text\nM_k_info:\n\tnop\n')
    many = [''.join(G.replace('M_g', f'M_g{i}').format(i + k) for i in range(LIMIT + 2))
            for k in (0, 1)]
    tree = {'m.dump-asm': (a, b), 's.dump-asm': (common, common.replace(t1, t2)),
            'r.dump-asm': (F.format('.LQ1', '.LQ2', '.LQ3'), F.format('.LQ4', '.LQ5', '.LQ6')),
            'n.dump-asm': tuple(many), 'x.o': ('\x7fELF\0a', '\x7fELF\0b')}
    da, db = os.path.join(td, 'a'), os.path.join(td, 'b')
    for d, k in ((da, 0), (db, 1)):
        os.makedirs(d)
        for name, texts in tree.items():
            with open(os.path.join(d, name), 'w') as fh:
                fh.write(texts[k])
    m = ['  differs: M_e_info 2 -> 2', '  differs: M_g_info 2 -> 2',
         '  only in A: M_h_info 1', '  differs: M_d_closure 0 -> 0',
         '  only in B: M_k_info 1']
    rows = [f'  differs: M_g{i}_info 2 -> 2' for i in range(LIMIT + 2)]
    want = ['compared 4: identical 0, equal once masked 1, differing 3;'
            ' only in A 0, only in B 0',
            'differs: m.dump-asm', *m, 'differs: n.dump-asm', *rows[:LIMIT], '  ... 2 more',
            'differs: r.dump-asm', '  no procedure differs once local labels are renumbered']
    got = run(['--ext', '.dump-asm', '--procs', da, db])
    if got != (want, 1):
        bad.append(f'--procs over two directories of dumps: {got}')
    got = run(['--ext', '.dump-asm', da, db, '--all'])
    if got != ([want[0], 'differs: m.dump-asm', 'differs: n.dump-asm', 'differs: r.dump-asm'],
               1):
        bad.append(f'--ext .dump-asm without --procs: {got}')
    nb = os.path.join(td, 'n-b.dump-asm')
    with open(nb, 'w') as fh:
        fh.write(many[1])
    got = run(['--procs', '--all', os.path.join(da, 'n.dump-asm'), nb])
    if got != (['compared 1: identical 0, equal once masked 0, differing 1;'
                ' only in A 0, only in B 0', 'differs: n.dump-asm', *rows], 1):
        bad.append(f'--procs --all over two files: {got}')
    got = run(['--ext', '.o', '--ext', '.dump-asm', '--procs', da, db])
    if got[1] != 1 or got[0][:1] != ['compared 5: identical 0, equal once masked 1, differing 4;'
                                     ' only in A 0, only in B 0'] or 'differs: x.o' not in got[0]:
        bad.append(f'--ext twice: {got}')
    elif got[0][got[0].index('differs: x.o') + 1:][:1] != []:
        bad.append(f'an object followed by procedures: {got[0][-3:]}')
    out, rc = run(['--show', 'M_[ge]_', os.path.join(da, 'm.dump-asm'),
                   os.path.join(db, 'm.dump-asm')])
    heads = [x for x in out if x.startswith('  ') and not x.startswith('    ')]
    body = [x[4:] for x in out if x.startswith('    ')]
    if (rc != 1 or out[:3] != ['compared 1: identical 0, equal once masked 0, differing 1;'
                               ' only in A 0, only in B 0', 'differs: m.dump-asm', m[0]]
            or heads != m[:2] or '-\tleaq .Lr1_bytes(%rip),%rbx' not in body
            or '+\tleaq .Lr2_bytes(%rip),%rbx' not in body or '-\tmovq $1,%rax' not in body
            or '+\tmovq $2,%rax' not in body or '--- A M_e_info' not in body):
        bad.append(f'--show over two files: {rc} {out}')
    # The labels renumbered, a $-prefixed reference among them; another
    # unit's label and the unit's name kept.
    [(name, lines)] = units(F.format('.LQ1', '.LQ2', '.Lb_info').replace(
        'jmp *-8(%r13)', 'jmp .Lother'))
    if name != 'M_f_info' or lines != ['.section .text', '.align 8', 'M_f_info:', 'L0:',
                                       '\tleaq -24(%rbp),%rax', '\tjb L1', '\tmovq $L2,(%rbp)',
                                       'L1:', '\tjmp .Lother', 'L2:', '\tret']:
        bad.append(f'a unit normalised: {name} {lines}')
    names = [n for n, _ in units(G.format(1) + G.format(2) + '.section .bss\n\t.zero 8\n')]
    if names != ['M_g_info', "M_g_info'", '.section .bss']:
        bad.append(f'units named {names}')
    if units(HEAD.format(t1) + G.format(1)) != units(G.format(1)):
        bad.append(f'a dump header kept: {units(HEAD.format(t1) + G.format(1))}')
    for args in (['--ext'], ['--show', '(', da, db], [da, os.path.join(db, 'm.dump-asm')]):
        out, rc = run(args)
        if rc != 2:
            bad.append(f'{args}: {rc} {out}')


def main(argv):
    if argv == ['--self-test']:
        return self_test()
    out, rc = run(argv)
    for line in out:
        print(line, file=sys.stderr if rc == 2 else sys.stdout)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
