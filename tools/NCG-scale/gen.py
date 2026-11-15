#!/usr/bin/env python3
"""Sources for scaling probes of GHC's native code generator: shapes in which
one structure the code generator walks grows with N, so that a compiler whose
cost grows faster than its base's shows it, run.sh compiling them and report.py
flagging the rows.

Usage: python3 tools/NCG-scale/gen.py N...      (into the current directory)
       python3 tools/NCG-scale/gen.py --shapes  (the shapes in run order)
       python3 tools/NCG-scale/gen.py --shapes L  (those compiled at -OL)
       python3 tools/NCG-scale/gen.py --levels  (the levels, ascending)
       python3 tools/NCG-scale/gen.py --self-test

chainN.hs, T3294 with N strict unpacked Double fields; loopsN.hs, one function
running N loops in sequence, each calling an unknown function, so that each loop
holds a call returning into it; ccallsN.hs, one block of N unsafe C calls in
sequence, each taking the last's result, each result live to its end; callsN.hs,
N calls in sequence in one procedure, each value live to the end, so N return
continuations outside any loop; allocsN.hs, the same with an allocation before
each call, so N heap checks and N blocks the garbage collector returns to;
listsN.hs, N loops in sequence over a lazy list, each evaluating its cells
and their elements, so tag tests and evaluations returning into each loop;
casesN.hs, an N-way case whose alternatives jump to one join point, kept by
NOINLINE; deadchainN.cmm, N loops in sequence, the k-th copying t(k-1) to
tk, nothing reading tN: sinking moves each copy to its loop's exit and drops
only the last, and each liveness pass of the NCG series' dropDeadAssignments
drops one more; nestN.cmm, N loops nested in one procedure; carryN.cmm, one
loop carrying N variables, each updated from its neighbour at every iteration;
rotateN.cmm, one loop rotating N variables at its back edge, so a cyclic join
fixup of N registers and slots; diamondsN.cmm, one loop whose body is N if-else
diamonds in sequence, each arm updating another variable, so N joins in one
cyclic SCC; claimsN.cmm, one loop whose body is one block of N steps, each
writing t afresh and reading it twice, t's last value returned in R1, so that
each allocation of t, a vreg with no preference but R1's register as its wide
destination, reaches the linear allocator's scan of the vregs the block reads
or writes with a first-used register (claims); joinN.hs, a case whose two arms
jump to one join point with N Int#s, loaded last, and seventeen Doubles, one arm
broadcasting a Double that the other reads again, so that the join's target
expects it both in a register and in a slot other than its own
(https://gitlab.haskell.org/ghc/ghc/-/work_items/27638), the Int#s leaving no
register spare there: a compiler that panics on it fails the compile.

Every shape is compiled at -O1 and -O2, and claims at -O0 too: at -O1 and -O2
the base's own cost on claims is superlinear as well, hiding the scan's.

chain, loops, ccalls and claims are kept byte for byte as first written, so that
their figures stay comparable with the runs that found a quadratic compile cost
on loops and on claims and a superlinear one on ccalls; the self-test checks
their hashes at N = 50, and of every shape that the item it grows occurs N
times."""
import hashlib
import os
import sys
import tempfile


def chain(n):
    return ('module Main where\n\ndata X = X\n'
            + ''.join('  {-# UNPACK #-} !Double\n' for _ in range(n))
            + '  deriving (Show)\n\nmain = print $ X' + ' 1' * n + '\n')


def loops(n):
    s = ('module Loops (g) where\n\ng :: (Int -> Int) -> Int -> Int\n'
         'g h n = loop1 0 0\n  where\n')
    for k in range(1, n + 1):
        nxt = f'loop{k + 1} 0 acc' if k < n else 'acc'
        s += (f'    loop{k} !i !acc | i == n = {nxt}\n'
              f'                  | otherwise = loop{k} (i + 1) (acc + h (i + {k}))\n')
    return s


def ccalls(n):
    L = ['{-# LANGUAGE MagicHash, UnliftedFFITypes #-}', f'module C{n} (f) where',
         'import GHC.Exts',
         'foreign import ccall unsafe "sin" c_sin :: Double# -> Double#',
         'f :: Double -> Double', 'f (D# x0) =']
    for i in range(1, n + 1):
        L.append(f'  let !a{i} = c_sin (a{i-1} +## 1.0##) in' if i > 1
                 else '  let !a1 = c_sin x0 in')
    L.append('  D# (' + ' +## '.join(f'a{i}' for i in range(1, n + 1)) + ')')
    return '\n'.join(L) + '\n'


def calls(n):
    return ('module Calls (g) where\n\ng :: (Int -> IO Int) -> IO Int\n'
            'g h = do\n'
            + ''.join(f'  x{k} <- h {k}\n' for k in range(1, n + 1))
            + '  pure (' + ' + '.join(f'x{k}' for k in range(1, n + 1)) + ')\n')


def allocs(n):
    return ('module Allocs (g) where\n\ng :: ([Int] -> IO Int) -> IO Int\n'
            'g h = do\n  x1 <- h []\n'
            + ''.join(f'  x{k} <- h [x{k - 1}]\n' for k in range(2, n + 1))
            + '  pure (' + ' + '.join(f'x{k}' for k in range(1, n + 1)) + ')\n')


def lists(n):
    s = 'module Lists (g) where\n\ng :: [Int] -> Int\ng xs = loop1 xs 0\n  where\n'
    for k in range(1, n + 1):
        nxt = f'loop{k + 1} xs acc' if k < n else 'acc'
        s += (f'    loop{k} [] !acc = {nxt}\n'
              f'    loop{k} (y : ys) !acc = loop{k} ys (acc + y * {k})\n')
    return s


def cases(n):
    return ('module Cases (f) where\n\nf :: Int -> Int -> Int\n'
            'f x y = case x of\n'
            + ''.join(f'    {k} -> j (y * {2 * k + 1} + {k})\n'
                      for k in range(1, n + 1))
            + '    _ -> j y\n'
            '  where\n'
            '    {-# NOINLINE j #-}\n'
            '    j !r = let !s = r * r + x\n'
            '               !t = s * (r + y) + s `quot` 7\n'
            '           in t * (t + r) + s\n')


def proc(name, decls, body):
    return (f'#include "Cmm.h"\n\n{name} (W_ n)\n{{\n    W_ {", ".join(decls)};\n'
            + body + '}\n')


def deadchain(n):
    body = '    t0 = n;\n    i = 0;\n    goto l1;\n'
    for k in range(1, n + 1):
        nxt = f'i = 0;\n    goto l{k + 1};' if k < n else 'return (i);'
        body += (f'\nl{k}:\n    t{k} = t{k - 1};\n'
                 f'    if (i >= n) {{ goto e{k}; }}\n'
                 f'    i = i + 1;\n    goto l{k};\n'
                 f'\ne{k}:\n    {nxt}\n')
    return proc('deadchain', ['i'] + [f't{k}' for k in range(n + 1)], body)


def nest(n):
    body = '    s = 0;\n    i1 = 0;\n    goto l1;\n'
    for k in range(1, n + 1):
        inner = (f'    i{k + 1} = 0;\n    goto l{k + 1};\n' if k < n else
                 f'    s = s + i{k};\n    i{k} = i{k} + 1;\n    goto l{k};\n')
        body += (f'\nl{k}:\n    if (i{k} >= n) {{ goto x{k - 1}; }}\n' + inner)
    for k in range(n - 1, 0, -1):
        body += f'\nx{k}:\n    i{k} = i{k} + 1;\n    goto l{k};\n'
    body += '\nx0:\n    return (s);\n'
    return proc('nest', ['s'] + [f'i{k}' for k in range(1, n + 1)], body)


def total(n):
    return ' + '.join(f'a{k}' for k in range(1, n + 1))


def carry(n):
    body = (''.join(f'    a{k} = n + {k};\n' for k in range(1, n + 1))
            + '    i = 0;\n    goto head;\n\nhead:\n'
            '    if (i >= n) { goto done; }\n'
            + ''.join(f'    a{k} = a{k} + {"i" if k == 1 else f"a{k - 1}"};\n'
                      for k in range(1, n + 1))
            + f'    i = i + 1;\n    goto head;\n\ndone:\n    return ({total(n)});\n')
    return proc('carry', ['i'] + [f'a{k}' for k in range(1, n + 1)], body)


def rotate(n):
    body = (''.join(f'    a{k} = n + {k};\n' for k in range(1, n + 1))
            + '    i = 0;\n    goto head;\n\nhead:\n'
            '    if (i >= n) { goto done; }\n    t = a1;\n'
            + ''.join(f'    a{k} = a{k + 1};\n' for k in range(1, n))
            + f'    a{n} = t;\n'
            + f'    i = i + 1;\n    goto head;\n\ndone:\n    return ({total(n)});\n')
    return proc('rotate', ['i', 't'] + [f'a{k}' for k in range(1, n + 1)], body)


def diamonds(n):
    body = ('    i = 0;\n    x = n;\n    y = 1;\n    z = 2;\n    goto head;\n'
            '\nhead:\n    if (i >= n) { goto done; }\n    goto d1;\n')
    for k in range(1, n + 1):
        nxt = f'd{k + 1}' if k < n else 'tail'
        body += (f'\nd{k}:\n    if (x > y + {k}) {{ goto da{k}; }} else {{ goto db{k}; }}\n'
                 f'\nda{k}:\n    x = x - z;\n    goto dj{k};\n'
                 f'\ndb{k}:\n    y = y + {k};\n    goto dj{k};\n'
                 f'\ndj{k}:\n    z = z + x;\n    goto {nxt};\n')
    body += ('\ntail:\n    i = i + 1;\n    goto head;\n'
             '\ndone:\n    return (x + y + z);\n')
    return proc('diamonds', ['i', 'x', 'y', 'z'], body)


def claims(n):
    body = ('    x = n + 1;\n    y = n + 2;\n    s = 0;\n    q = 0;\n'
            '    i = 0;\n    goto body;\n\nbody:\n')
    for k in range(1, n + 1):
        body += (f'    t = x * {2 * k + 1} + y + i;\n'
                 '    s = s ^ t;\n    q = q + t;\n')
    body += ('    i = i + 1;\n'
             '    if (i < n) { goto body; } else { goto done; }\n\n'
             'done:\n    return (t, s, q);\n')
    return proc('claims', ['i', 'x', 'y', 's', 'q', 't'], body)


def join(n):
    # A local function both arms tail-call, not the unboxed tuple of the
    # tests T27638b to T27638f: a tuple has at most 64 components, and nested
    # tuples left GHC no join, the continuation copied into each arm. The
    # arguments load last first, so the Int#s after the Doubles.
    iz = [f'i{k}' for k in range(n)]
    ds = [f'd{k}' for k in range(17)]
    loads = ' '.join(f'(indexIntOffAddr# q {k}#)' for k in range(n))
    dl = ' '.join(f'(indexDoubleOffAddr# p {k}#)' for k in range(17))
    return ('{-# LANGUAGE MagicHash, UnboxedTuples, UnliftedFFITypes #-}\n'
            'module Join (f) where\n\nimport GHC.Exts\n\n'
            'foreign import ccall unsafe "fabs" c_fabs :: Double# -> Double#\n\n'
            'f :: Int# -> Addr# -> Addr# -> Double# -> Double#\n'
            'f b p q x =\n'
            '  let !y = c_fabs x\n'
            f'      j r {" ".join(iz)} {" ".join(ds)} =\n'
            f'        (r *## x) +## ({" +## ".join(ds)})'
            f' +## int2Double# (0#{"".join(f" +# {i}" for i in iz)})\n'
            '      {-# NOINLINE j #-}\n'
            '  in case b of\n'
            '       0# -> case unpackDoubleX2# (broadcastDoubleX2# x) of\n'
            f'               (# u, _ #) -> let !z = c_fabs u in j z {loads} {dl}\n'
            f'       _  -> j (y +## x) {loads} {dl}\n'
            '{-# NOINLINE f #-}\n')


SHAPES = [('chain', '.hs', chain), ('loops', '.hs', loops),
          ('ccalls', '.hs', ccalls), ('calls', '.hs', calls),
          ('allocs', '.hs', allocs), ('lists', '.hs', lists),
          ('cases', '.hs', cases), ('deadchain', '.cmm', deadchain),
          ('nest', '.cmm', nest), ('carry', '.cmm', carry),
          ('rotate', '.cmm', rotate), ('diamonds', '.cmm', diamonds),
          ('claims', '.cmm', claims), ('join', '.hs', join)]

# The levels a shape is compiled at, where not -O1 and -O2.
LEVELS = {'claims': (0, 1, 2)}


def shapes_at(level):
    return [name for name, _, _ in SHAPES if level in LEVELS.get(name, (1, 2))]

# What each shape grows, one occurrence per unit of N.
MARKS = {'chain': '{-# UNPACK #-} !Double', 'loops': '| otherwise = loop',
         'ccalls': 'let !a', 'calls': ' <- h ', 'allocs': ' <- h ',
         'lists': ' [] !acc = ', 'cases': ' -> j (', 'deadchain': ' = t',
         'nest': 'if (i', 'carry': ' = a', 'rotate': ' = a',
         'diamonds': 'if (x > y + ', 'claims': '    t = x * ',
         'join': ' +# i'}
# The sources kept byte for byte, at N = 50.
PINNED = {
    'chain50.hs': '33c65e1873fe32d41b13c354184f988409387ffa0e21859492064023fd30d0a8',
    'loops50.hs': '40f8fb45f73099954e8d9ef27a16c4a190f93b288e0ddc671ebbc387aeaa3007',
    'ccalls50.hs': '54d4107283c2529375c4e8887a1141ef9cfa2eccd7eb8e491ea5fe153d6ebcd2',
    'claims50.cmm': '2f60d42e34fe3a0e784be8a7217240ec3fcc7744df3708e5c9bb848a361b0312',
}


def write(d, ns):
    for n in ns:
        for name, ext, gen in SHAPES:
            with open(os.path.join(d, f'{name}{n}{ext}'), 'w') as f:
                f.write(gen(n))


def self_test():
    bad = []
    with tempfile.TemporaryDirectory() as d:
        write(d, [3, 50])
        for name, ext, _ in SHAPES:
            for n in (3, 50):
                with open(os.path.join(d, f'{name}{n}{ext}')) as f:
                    c = f.read().count(MARKS[name])
                if c != n:
                    bad.append(f'{name}{n}{ext}: {MARKS[name]!r} {c} times, not {n}')
        for f, want in PINNED.items():
            with open(os.path.join(d, f), 'rb') as h:
                got = hashlib.sha256(h.read()).hexdigest()
            if got != want:
                bad.append(f'{f} changed: sha256 {got}')
    every = [name for name, _, _ in SHAPES]
    if shapes_at(1) != every or shapes_at(2) != every:
        bad.append(f'not every shape at -O1 and -O2: {shapes_at(1)}, {shapes_at(2)}')
    if 'claims' not in shapes_at(0):
        bad.append('claims not at -O0')
    for x in bad:
        print('FAIL', x)
    print('ok   gen.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--shapes']:
        print(' '.join(name for name, _, _ in SHAPES))
    elif sys.argv[1:2] == ['--shapes'] and len(sys.argv) == 3:
        print(' '.join(shapes_at(int(sys.argv[2]))))
    elif sys.argv[1:] == ['--levels']:
        print(' '.join(map(str, sorted({v for name, _, _ in SHAPES
                                        for v in LEVELS.get(name, (1, 2))}))))
    elif sys.argv[1:] == ['--self-test']:
        sys.exit(self_test())
    elif not sys.argv[1:]:
        sys.exit(__doc__)
    else:
        write('.', map(int, sys.argv[1:]))
