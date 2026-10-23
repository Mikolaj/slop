#!/usr/bin/env python3
"""Check orthotope's HasCallStack constraints against the rule they keep to.

Usage: python3 tools/hascallstack.py ROOT [--fix] [--list]
       python3 tools/hascallstack.py --self-test

ROOT is an orthotope checkout, of which Data.Array.Internal, the modules
under it and Data.Array.Convert are read. The rule, ruled 2026-10-23 in place
of that of 2026-10-08, rests on the error policy that orthotope's README
states. An argument error names an exported operation whose documentation
says when it fails: its own function, or, in a helper checking an operation's
argument, that operation, the one name the helper serves or a name its caller
passes; never a function its module does not export. A contract check names
the function whose contract it is and says "violated contract". An error
reflecting a type's numbers names the class, Shape. A function takes
HasCallStack exactly when an argument error naming it, or naming the function
of the same name in another module that it wraps, can be raised in its code
or in a function it calls, which takes one too, so that the error shows
the line the operation was called from: a callee's argument errors count
as a caller's where their message opens with the caller's name, or with
a name passed in and the call passes the caller's name as a literal. A contract
check guards against a bug in orthotope and adds no stack, nor does an assert,
and class methods take none, a stack on one binding every instance.

An error's message is every string literal on its line from `error` on,
and its name the word before the first literal's colon, or the name its
message opens with where that is passed in. The rule reads the wording, so
the wording is checked too: an error in Data.Array.Internal that does not say
"violated contract", and one anywhere that says "impossible" or "shouldn't
happen", are findings. So are an error naming neither its function nor
a caller of it, an argument error naming its own function where its module
does not export it, a call of a function whose errors open with a name passed
in that passes neither the caller's name nor a name of the caller's own,
and a stack-taking function that calls itself, each level of which would push
a frame of its own where a stack-free local worker pushes none.

Reports each signature the rule would change and each module whose
GHC.Stack import does not match its uses; `--fix` rewrites both and reports
what remains, and `--list` prints the verdict. Exit 0 when the tree keeps
the rule, 1 with the findings listed, 2 when the run did not happen:
a module missing under ROOT.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hssource import strip_comments  # noqa: E402

MODS = ['Internal', 'DynamicG', 'RankedG', 'ShapedG', 'Dynamic', 'DynamicS',
        'DynamicU', 'Ranked', 'RankedS', 'RankedU', 'Shaped', 'ShapedS',
        'ShapedU', 'Shape', 'Convert']
ORTHOTOPE = dict(
    own='Data.Array',
    mods=MODS,
    path={m: 'Data/Array/%s.hs' % m if m in ('Internal', 'Convert')
          else 'Data/Array/Internal/%s.hs' % m for m in MODS},
    # Whose every error checks a contract.
    internal='Internal',
    # A module whose errors may name a class rather than a function.
    classes={'Shape': 'Shape'})

SIG = re.compile(r"^([a-z][\w']*) ::(.*)$")
END = re.compile(r"^([a-z][\w']* ::|[a-z][\w']*\s*$|-- \||\{-#|"
                 r"(instance|class|data|newtype|type|deriving)\b)")
MESSAGE = re.compile(r'\berror\b\s*\$?\s*\(?\s*("[^"]*"|[a-zA-Z_][\w.]*)')
LEAD = re.compile(r"\s*([A-Za-z_][\w']*)\s*:")
CONTRACT = 'violated contract'
UNWORDED = re.compile(r'"[^"]*(impossible|shouldn.t happen)')


def unquote(line):
    """The line with its string literals emptied."""
    out, q = [], False
    for i, c in enumerate(line):
        if c == '"' and (i == 0 or line[i - 1] != '\\'):
            q = not q
        elif not q:
            out.append(c)
    return ''.join(out)


def parse(cfg, texts):
    """{(module, name): sig, body, hcs, errors, occ}, and each module's
    imports of the others: {qualifier: module} and 'unqual': [modules].
    errors lists each `error` call in the body as its line's index, its
    message, every literal on the line from `error` on, and its name: the
    word before the first literal's colon, a pair ('passed', NAME) where the
    message opens with a name, or None."""
    own = re.escape(cfg['own'])
    funs, imports = {}, {}
    for m in cfg['mods']:
        lines = texts[m].split('\n')
        code = [unquote(l) for l in strip_comments(texts[m]).split('\n')]
        imp = {'unqual': []}
        for l in lines:
            a = re.match(r'import\s+qualified\s+(%s(?:\.\w+)*)\s+as\s+(\w+)'
                         % own, l)
            if a and a.group(1).split('.')[-1] in cfg['mods']:
                imp[a.group(2)] = a.group(1).split('.')[-1]
            b = re.match(r'import\s+(%s(?:\.\w+)*)\s*(\(|$)' % own, l)
            if b and b.group(1).split('.')[-1] in cfg['mods']:
                imp['unqual'].append(b.group(1).split('.')[-1])
        imports[m] = imp
        k = 0
        while k < len(lines):
            mm = SIG.match(lines[k])
            if (not mm and k + 1 < len(lines)
                    and re.match(r"^[a-z][\w']*\s*$", lines[k])
                    and re.match(r'^\s+::', lines[k + 1])):
                mm = re.match(r"^([a-z][\w']*)", lines[k])
            if not mm:
                k += 1
                continue
            name, j = mm.group(1), k + 1
            while j < len(lines) and lines[j].startswith(' '):
                j += 1
            sig_end = j
            while j < len(lines) and not END.match(lines[j]):
                j += 1
            occ, errors = {}, []
            for i in range(sig_end, j):
                # The name heading its own equation is no call. A name's
                # end is no \b, which backtracks past a prime and read go'
                # as go (hascallstack-02).
                l = re.sub(r"^%s(?![\w'])" % re.escape(name), ' ' * len(name),
                           code[i])
                for q, f in re.findall(r"(?<![\w'])(?:([A-Z]\w*)\.)?"
                                       r"([a-z_][\w']*)(?![\w'])", l):
                    occ.setdefault((q, f), []).append(i)
                if re.search(r'\berror\b', l):
                    errors.append((i,) + message(lines[i]))
            funs[(m, name)] = dict(
                sig=(k, sig_end), body=(sig_end, j),
                hcs='HasCallStack' in ' '.join(lines[k:sig_end]),
                errors=errors, occ=occ)
            k = j
    return funs, imports


def graph(funs, imports):
    """{(caller, callee): [lines of the calls]}."""
    defs = {}
    for m, n in funs:
        defs.setdefault(m, set()).add(n)
    edges = {}
    for (m, name), d in funs.items():
        for (q, f), lns in d['occ'].items():
            if q:
                tm = imports[m].get(q)
                tgts = [(tm, f)] if tm and f in defs.get(tm, ()) else []
            elif f in defs[m]:
                tgts = [(m, f)]
            else:
                tgts = [(u, f) for u in imports[m]['unqual']
                        if f in defs.get(u, ())]
            for t in tgts:
                edges.setdefault(((m, name), t), []).extend(lns)
    return edges


def message(line):
    """(message, name) of the `error` call on the line."""
    tail = line[line.index('error') if 'error' in line else 0:]
    lits = re.findall(r'"((?:[^"\\]|\\.)*)"', tail)
    e = MESSAGE.search(line)
    if e and not e.group(1).startswith('"'):
        name = ('passed', e.group(1))
    else:
        lead = LEAD.match(lits[0]) if lits else None
        name = lead.group(1) if lead else None
    return ' '.join(lits), name


def passes(texts, g, lns):
    """Whether g's calls on lns pass g's own name as a literal."""
    lines = texts[g[0]].split('\n')
    return any('"%s"' % g[1] in lines[i] for i in lns)


def argument_errors(d):
    return [e for e in d['errors'] if CONTRACT not in e[1]]


def verdict(cfg, texts):
    """The functions the rule gives HasCallStack, with the parse and the
    call graph."""
    funs, imports = parse(cfg, texts)
    edges = graph(funs, imports)
    v = {k for k, d in funs.items() if argument_errors(d)}

    def serves(g, f, lns):
        """Whether f's argument errors are g's to show: f is the function
        of g's name that g wraps, or an error of f names g."""
        if f[1] == g[1] and f[0] != g[0]:
            return True
        names = [n for _, _, n in argument_errors(funs[f])]
        return (g[1] in names
                or any(isinstance(n, tuple) for n in names)
                and passes(texts, g, lns))
    while True:
        new = {g for (g, f), lns in edges.items()
               if g not in v and f in v and serves(g, f, lns)}
        if not new:
            return v, funs, edges
        v |= new


def split_ctx(sig):
    """The signature up to `::` and an optional forall, the context before
    the first top-level `=>` or None, and the rest."""
    i = j = sig.index('::') + 2
    fa = re.match(r'\s*forall\s[^.]*\.', sig[i:])
    if fa:
        j = i + fa.end()
    depth = 0
    for p in range(j, len(sig) - 1):
        c = sig[p]
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        elif depth == 0 and sig.startswith('=>', p):
            return sig[:j], sig[j:p], sig[p:]
        elif depth == 0 and sig.startswith('->', p):
            break
    return sig[:j], None, sig[j:]


def add_hcs(sig):
    head, ctx, rest = split_ctx(sig)
    if ctx is None:
        lead = re.match(r'\s*', rest).group(0)
        return head + lead + '(HasCallStack) => ' + rest[len(lead):]
    c = ctx.strip()
    if c.startswith('(') and c.endswith(')'):
        i = ctx.index('(')
        return head + ctx[:i + 1] + 'HasCallStack, ' + ctx[i + 1:] + rest
    lead = re.match(r'\s*', ctx).group(0)
    return head + lead + '(HasCallStack, ' + c + ') ' + rest


def drop_hcs(sig):
    head, ctx, rest = split_ctx(sig)
    c = ctx.strip()
    if c in ('HasCallStack', '(HasCallStack)'):
        return (head + re.match(r'\s*', ctx).group(0)
                + re.sub(r'^=>\s*', '', rest, count=1))
    new = re.sub(r'HasCallStack\s*,\s*', '', ctx, count=1)
    if new == ctx:
        new = re.sub(r',\s*HasCallStack', '', ctx, count=1)
    return head + new + rest


def exported(s):
    """The names a module's export list gives, or None where it exports
    all of itself."""
    m = re.search(r'^module\s+([\w.]+)\s*(\(.*?\))?\s*where',
                  strip_comments(s), re.S | re.M)
    if not m or m.group(2) is None or re.search(
            r'\bmodule\s+%s\b' % re.escape(m.group(1)), m.group(2)):
        return None
    return set(re.findall(r"(?<![\w'.])([a-z_][\w']*)", m.group(2)))


def stack_import(s):
    """(the GHC.Stack import line or None, whether the code names
    HasCallStack)."""
    has = re.search(r'^import\s+GHC\.Stack\b.*$', s, re.M)
    code = '\n'.join(l for l in strip_comments(s).split('\n')
                     if not l.startswith('import'))
    return has, re.search(r'\bHasCallStack\b', code) is not None


def fix_import(cfg, s):
    has, uses = stack_import(s)
    if uses and not has:
        lines = s.split('\n')
        imps = [i for i, l in enumerate(lines) if l.startswith('import ')]
        own = re.compile(r'import\s+(qualified\s+)?%s\b' % re.escape(cfg['own']))
        # In order among the unqualified imports of other packages, which
        # come first, else before the module's own.
        pos = next((i for i in imps
                    if not lines[i].startswith('import qualified')
                    and not own.match(lines[i])
                    and lines[i][len('import '):].lstrip() > 'GHC.Stack'),
                   None)
        if pos is None:
            pos = next((i for i in imps if own.match(lines[i])),
                       imps[-1] + 1 if imps else 1)
        lines.insert(pos, 'import GHC.Stack(HasCallStack)')
        s = '\n'.join(lines)
    elif has and not uses:
        s = s.replace(has.group(0) + '\n', '', 1)
    return s


def rewrite(cfg, texts, v):
    """The texts with HasCallStack on exactly the functions of v, and
    GHC.Stack imported where it is used."""
    funs, _ = parse(cfg, texts)
    out = {}
    for m in cfg['mods']:
        lines = texts[m].split('\n')
        for k, d in sorted(funs.items(), key=lambda x: -x[1]['sig'][0]):
            if k[0] != m or (k in v) == d['hcs']:
                continue
            b, e = d['sig']
            sig = '\n'.join(lines[b:e])
            new = add_hcs(sig) if k in v else drop_hcs(sig)
            lines[b:e] = new.split('\n')
        out[m] = fix_import(cfg, '\n'.join(lines))
    return out


def name(k):
    return '%s.%s' % k


def check(cfg, texts):
    """The findings, one line each, and the verdict."""
    v, funs, edges = verdict(cfg, texts)
    exports = {m: exported(texts[m]) for m in cfg['mods']}
    out = []
    for k, d in sorted(funs.items()):
        where = '%s:%d' % (cfg['path'][k[0]], d['sig'][0] + 1)
        if (k in v) != d['hcs']:
            out.append('%s HasCallStack: %s (%s)'
                       % ('add' if k in v else 'drop', name(k), where))
        if k in v and (k, k) in edges:
            out.append('calls itself with a stack: %s (%s)' % (name(k), where))
        lines = texts[k[0]].split('\n')
        callers = {g: lns for (g, f), lns in edges.items() if f == k}
        for i, msg, n in d['errors']:
            line = lines[i]
            at = '%s (%s:%d): %s' % (name(k), cfg['path'][k[0]], i + 1,
                                     line.strip()[:60])
            if UNWORDED.search(line) or (k[0] == cfg['internal']
                                         and CONTRACT not in msg):
                out.append('error worded as neither: ' + at)
            if isinstance(n, tuple):
                for g, lns in sorted(callers.items()):
                    if not (passes(texts, g, lns) or any(
                            isinstance(m, tuple)
                            for _, _, m in funs[g]['errors'])):
                        out.append('a call passes no name of its caller: %s'
                                   ' calls %s' % (name(g), at))
            elif n is not None and n != k[1] and n != cfg.get(
                    'classes', {}).get(k[0]) and n not in {
                        g[1] for g in callers}:
                out.append('error names %s, neither its function nor a'
                           ' caller: %s' % (n, at))
            elif (n == k[1] and CONTRACT not in msg
                  and exports[k[0]] is not None
                  and k[1] not in exports[k[0]]):
                out.append('error names an unexported function: ' + at)
    for m in cfg['mods']:
        has, uses = stack_import(texts[m])
        if bool(has) != uses:
            out.append('GHC.Stack import %s: %s'
                       % ('missing' if uses else 'unused', cfg['path'][m]))
    return out, v


def main(argv, cfg=ORTHOTOPE):
    if argv == ['--self-test']:
        return self_test()
    flags = [a for a in argv if a.startswith('--')]
    args = [a for a in argv if not a.startswith('--')]
    if len(args) != 1 or set(flags) - {'--fix', '--list'}:
        print(__doc__.split('\n\n')[1])
        return 2
    root, texts = args[0], {}
    for m in cfg['mods']:
        p = os.path.join(root, cfg['path'][m])
        if not os.path.isfile(p):
            print('no %s under %s: nothing checked' % (cfg['path'][m], root))
            return 2
        with open(p) as fh:
            texts[m] = fh.read()
    if '--fix' in flags:
        v = verdict(cfg, texts)[0]
        new = rewrite(cfg, texts, v)
        for m in cfg['mods']:
            if new[m] != texts[m]:
                with open(os.path.join(root, cfg['path'][m]), 'w') as fh:
                    fh.write(new[m])
                print('rewrote', cfg['path'][m])
        texts = new
    out, v = check(cfg, texts)
    if '--list' in flags:
        for m in cfg['mods']:
            print('%s: %s' % (m, ' '.join(sorted(n for mm, n in v
                                                 if mm == m))))
    for o in out:
        print(o)
    print('%d functions take HasCallStack by the rule; %d findings'
          % (len(v), len(out)))
    return 1 if out else 0


FIXTURE = {
    'A': '''module Lib.A where

import GHC.Stack(HasCallStack)
import qualified Lib.C as C

build :: Int -> [Int]
build n | n < 0 = error "build: negative size"
        | otherwise = [0 .. n]

total :: (HasCallStack) => [Int] -> Int
total = sum

twice :: Int -> [Int]
twice n = build n ++ build n

view :: Int -> Int
view i = C.at i

grow :: Int -> [Int]
grow k | k < 0 = error "grow: negative size"
       | k == 0 = []
       | otherwise = k : grow (k - 1)

long
  :: Int -> Int
long n = if n < 0 then error "long: negative" else n
''',
    'B': '''module Lib.B where

import qualified Lib.A as A
import qualified Lib.D as D

build :: Int -> [Int]
build = A.build

twice :: Int -> [Int]
twice = A.twice

size :: Int -> Int
size n = length (A.build n)

op :: [Int] -> [Int]
op = D.op
''',
    'C': '''module Lib.C where

import GHC.Stack(HasCallStack)

-- | Indexes, with no use for HasCallStack.
at :: (HasCallStack) => Int -> Int
at i | i < 0 = error "at: violated contract: negative index"
     | otherwise = i

bad :: Int -> Int
bad i = if i < 0 then error "impossible" else i

half :: Int -> Int
half i = if odd i then error "half: odd" else i `div` 2
''',
    'D': '''module Lib.D(op, op2, op3, wrap, maxi, stray, refl) where

import GHC.Stack(HasCallStack)

op :: (HasCallStack) => [Int] -> [Int]
op xs = checked xs

checked :: (HasCallStack) => [Int] -> [Int]
checked xs = if any (< 0) xs then error "op: negative" else xs

op2 :: (HasCallStack) => Int -> [Int]
op2 n = outer "op2" n

op3 :: Int -> [Int]
op3 n = outer "op2" n

outer :: (HasCallStack) => String -> Int -> [Int]
outer name n | n < 0 = error $ name ++ ": negative"
             | otherwise = inner name n

inner :: (HasCallStack) => String -> Int -> [Int]
inner name n = if n > 9 then error $ name ++ ": too big" else [n]

hidden :: Int -> Int
hidden n = if n < 0 then error "hidden: negative" else n

wrap :: Int -> Int
wrap = hidden

maxi :: [Int] -> Int
maxi = extreme "maxi"

extreme :: String -> [Int] -> Int
extreme name [] = error $ name ++ ": violated contract: empty"
extreme _ xs = maximum xs

stray :: (HasCallStack) => Int -> Int
stray n = if n < 0 then error "elsewhere: negative" else n

refl :: (HasCallStack) => Int -> Int
refl n = if n < 0 then error "Klass: negative" else n
'''}


def self_test():
    """The fixture above: the verdict, the wording, name and recursion
    findings, the rewrite and its fixed point, and the exit codes."""
    import tempfile
    cfg = dict(own='Lib', mods=['A', 'B', 'C', 'D'],
               path={m: 'Lib/%s.hs' % m for m in 'ABCD'}, internal='C',
               classes={'D': 'Klass'})
    bad = []

    def kinds(out, kind):
        return sorted(o.split(': ')[1].split(' ')[0] for o in out
                      if o.startswith(kind))
    out, v = check(cfg, FIXTURE)
    if kinds(out, 'add') != ['A.build', 'A.grow', 'A.long', 'B.build',
                             'B.op', 'C.bad', 'C.half', 'D.hidden']:
        bad.append('adds %s' % kinds(out, 'add'))
    if kinds(out, 'drop') != ['A.total', 'C.at']:
        bad.append('drops %s' % kinds(out, 'drop'))
    if kinds(out, 'calls itself') != ['A.grow']:
        bad.append('recursion %s' % kinds(out, 'calls itself'))
    if kinds(out, 'error worded') != ['C.bad', 'C.half']:
        bad.append('wording %s' % kinds(out, 'error worded'))
    if kinds(out, 'error names') != ['D.hidden', 'D.stray']:
        bad.append('names %s' % kinds(out, 'error names'))
    if kinds(out, 'error names an unexported') != ['D.hidden']:
        bad.append('unexported %s' % kinds(out, 'error names an unexported'))
    if kinds(out, 'a call passes') != ['D.op3']:
        bad.append('passed names %s' % kinds(out, 'a call passes'))
    if sorted(n for m, n in v if m == 'D') != [
            'checked', 'hidden', 'inner', 'op', 'op2', 'outer', 'refl',
            'stray']:
        bad.append("D's stacks %s" % sorted(n for m, n in v if m == 'D'))
    new = rewrite(cfg, FIXTURE, v)
    want = ['build :: (HasCallStack) => Int -> [Int]',
            'total :: [Int] -> Int', 'twice :: Int -> [Int]',
            'view :: Int -> Int', 'long\n  :: (HasCallStack) => Int -> Int',
            'size :: Int -> Int',
            'import GHC.Stack(HasCallStack)\nimport qualified Lib.A as A\n',
            'at :: Int -> Int']
    text = '\n'.join(new[m] for m in 'ABCD')
    bad += ['rewrite lacks %r' % w for w in want if w not in text]
    if new['C'].count('import GHC.Stack') != 1:
        bad.append('C keeps one import, bad taking the stack')
    out, _ = check(cfg, new)
    rest = sorted(o.split(':')[0] for o in out)
    if rest != ['a call passes no name of its caller',
                'calls itself with a stack',
                'error names an unexported function',
                'error names elsewhere, neither its function nor a caller',
                'error worded as neither', 'error worded as neither']:
        bad.append('after the rewrite: %s' % out)
    clean = dict(FIXTURE)
    clean['A'] = re.sub(r'grow ::.*?\n\n', '', clean['A'], flags=re.S)
    clean['C'] = clean['C'][:clean['C'].index('bad ::')]
    for f in ('op3', 'hidden', 'wrap', 'stray'):
        clean['D'] = re.sub(r'\n%s ::.*?\n\n' % f, '\n', clean['D'],
                            flags=re.S)
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, 'Lib'))
        for m in 'ABCD':
            with open(os.path.join(td, 'Lib', m + '.hs'), 'w') as fh:
                fh.write(clean[m])
        if main([td], cfg) != 1:
            bad.append('findings did not exit 1')
        if main([td, '--fix'], cfg) != 0:
            bad.append('--fix did not exit 0')
        with open(os.path.join(td, 'Lib', 'C.hs')) as fh:
            if 'GHC.Stack' in fh.read():
                bad.append("--fix kept C's unused import")
        if main([td], cfg) != 0:
            bad.append('a fixed tree did not exit 0')
        os.remove(os.path.join(td, 'Lib', 'C.hs'))
        if main([td], cfg) != 2:
            bad.append('a missing module did not exit 2')
    for b in bad:
        print('FAIL', b)
    print('self-test', 'FAILED' if bad else 'passed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
