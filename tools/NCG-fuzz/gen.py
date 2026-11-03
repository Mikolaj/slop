#!/usr/bin/env python3
"""A random Haskell program on stdout, for tools/NCG-fuzz/run.py's differential
test of code generation: functions over Int#, Word#, Double# and Float# with
many live values across branches (join points), loops, unsafe and safe C calls,
unknown calls, allocation (so heap-check failures under a small -A), byte
arrays (inline memset and memcpy), fixed-register instructions (quot, rem,
shifts, timesInt2#, popCnt, clz), narrowing, SSE vectors and more arguments
than registers. Every operation is defined on all inputs: no shift past the
width, no division by zero or minBound/-1, no out-of-range double2Int#; so all
compilers and flags must print the same.

Usage: python3 tools/NCG-fuzz/gen.py SEED [--size N]
       python3 tools/NCG-fuzz/gen.py --self-test

One seed names one program, so a seed that fails can be compiled again by hand."""
import random
import re
import sys

HTY = {'I': 'Int#', 'W': 'Word#', 'D': 'Double#', 'F': 'Float#'}

class G:
    def __init__(self, seed, size):
        self.r = random.Random(seed)
        self.size = size
        self.n = 0
        self.funcs = []  # (name, argtypes, restypes)

    def fresh(self, p='v'):
        self.n += 1
        return f'{p}{self.n}'

    def lit(self, t):
        r = self.r
        if t == 'I':
            return r.choice(['0#', '1#', '-1#', '7#', '63#', '64#', '255#',
                             '-128#', '65536#', '2147483648#',
                             '9223372036854775807#', '-9223372036854775808#',
                             f'{r.randint(-1000, 1000)}#'.replace('#', '#')])
        if t == 'W':
            return r.choice(['0##', '1##', '255##', '65535##',
                             '4294967296##', '18446744073709551615##',
                             f'{r.randint(0, 100000)}##'])
        if t == 'D':
            return r.choice(['0.0##', '1.0##', '-1.5##', '3.25##', '1.0e10##',
                             '-2.5e-3##', f'{r.randint(-99, 99)}.5##'])
        return r.choice(['0.0#', '1.0#', '-1.5#', '3.25#', '1.0e10#',
                         f'{r.randint(-99, 99)}.5#'])

    def atom(self, env, t):
        vs = [v for v, ty in env if ty == t]
        if vs and self.r.random() < 0.85:
            return self.r.choice(vs)
        l = self.lit(t)
        return f'({l})' if l.startswith('-') else l

    def expr(self, env, t, d=0):
        """A pure expression of type t over env."""
        r = self.r
        a = lambda ty=t: self.atom(env, ty)
        if d > 2 or r.random() < 0.15:
            return a()
        e = lambda ty=t: self.expr(env, ty, d + 1)
        if t == 'I':
            return r.choice([
                lambda: f'({e()} +# {e()})',
                lambda: f'({e()} -# {e()})',
                lambda: f'({e()} *# {e()})',
                lambda: f'(andI# {e()} {e()})',
                lambda: f'(orI# {e()} {e()})',
                lambda: f'(xorI# {e()} {e()})',
                lambda: f'(notI# {e()})',
                lambda: f'(negateInt# {e()})',
                lambda: f'(uncheckedIShiftL# {e()} (andI# {e()} 63#))',
                lambda: f'(uncheckedIShiftRA# {e()} (andI# {e()} 63#))',
                lambda: f'(uncheckedIShiftRL# {e()} (andI# {e()} 63#))',
                lambda: f'(quotInt# {e()} (orI# (andI# {e()} 65535#) 1#))',
                lambda: f'(remInt# {e()} (orI# (andI# {e()} 65535#) 1#))',
                lambda: f'(narrow8Int# {e()})',
                lambda: f'(narrow16Int# {e()})',
                lambda: f'(narrow32Int# {e()})',
                lambda: f'(word2Int# {e("W")})',
                lambda: f'({e()} ==# {e()})',
                lambda: f'({e()} <# {e()})',
                lambda: f'({e("D")} >## {e("D")})',
                lambda: f'({e("D")} ==## {e("D")})',
                lambda: f'(gtFloat# {e("F")} {e("F")})',
                lambda: f'(ltWord# {e("W")} {e("W")})',
                lambda: f'(int8ToInt# (intToInt8# {e()}))',
                lambda: f'(int32ToInt# (plusInt32# (intToInt32# {e()}) (intToInt32# {e()})))',
                lambda: f'(word2Int# (word8ToWord# (wordToWord8# {e("W")})))',
                lambda: f'(ord# (indexCharOffAddr# "quick brown fox"# (andI# {e()} 7#)))',
            ])()
        if t == 'W':
            return r.choice([
                lambda: f'(plusWord# {e()} {e()})',
                lambda: f'(minusWord# {e()} {e()})',
                lambda: f'(timesWord# {e()} {e()})',
                lambda: f'(and# {e()} {e()})',
                lambda: f'(or# {e()} {e()})',
                lambda: f'(xor# {e()} {e()})',
                lambda: f'(not# {e()})',
                lambda: f'(uncheckedShiftL# {e()} (andI# {e("I")} 63#))',
                lambda: f'(uncheckedShiftRL# {e()} (andI# {e("I")} 63#))',
                lambda: f'(quotWord# {e()} (or# {e()} 1##))',
                lambda: f'(remWord# {e()} (or# {e()} 1##))',
                lambda: f'(popCnt# {e()})',
                lambda: f'(popCnt8# {e()})',
                lambda: f'(clz# {e()})',
                lambda: f'(ctz# {e()})',
                lambda: f'(clz32# {e()})',
                lambda: f'(ctz16# {e()})',
                lambda: f'(byteSwap# {e()})',
                lambda: f'(byteSwap32# {e()})',
                lambda: f'(bitReverse8# {e()})',
                lambda: f'(pdep# {e()} {e()})',
                lambda: f'(pext# {e()} {e()})',
                lambda: f'(narrow8Word# {e()})',
                lambda: f'(narrow32Word# {e()})',
                lambda: f'(int2Word# {e("I")})',
            ])()
        if t == 'D':
            return r.choice([
                lambda: f'({e()} +## {e()})',
                lambda: f'({e()} -## {e()})',
                lambda: f'({e()} *## {e()})',
                lambda: f'({e()} /## {e()})',
                lambda: f'(negateDouble# {e()})',
                lambda: f'(fabsDouble# {e()})',
                lambda: f'(sqrtDouble# {e()})',
                lambda: f'(int2Double# {e("I")})',
                lambda: f'(word2Double# {e("W")})',
                lambda: f'(float2Double# {e("F")})',
                lambda: f'(fmaddDouble# {e()} {e()} {e()})',
            ])()
        return r.choice([
            lambda: f'(plusFloat# {e()} {e()})',
            lambda: f'(minusFloat# {e()} {e()})',
            lambda: f'(timesFloat# {e()} {e()})',
            lambda: f'(divideFloat# {e()} {e()})',
            lambda: f'(negateFloat# {e()})',
            lambda: f'(sqrtFloat# {e()})',
            lambda: f'(int2Float# {e("I")})',
            lambda: f'(double2Float# {e("D")})',
        ])()

    def mix(self, env):
        e = '0#'
        for v, t in env:
            if t == 'I':
                e = f'(xorI# {v} ({e} *# 31#))'
            elif t == 'W':
                e = f'(xorI# (word2Int# {v}) ({e} *# 33#))'
            elif t == 'D':
                e = f'(({v} >## 0.5##) +# ({e} *# 3#))'
            else:
                e = f'((gtFloat# {v} 0.5#) +# ({e} *# 5#))'
        return e

    def types(self, k):
        return [self.r.choice('IIIIWWDDF') for _ in range(k)]

    def stmts(self, env, depth, n, ind, in_io=False):
        """Lines binding new variables; extends env in place."""
        out = []
        r = self.r
        p = ' ' * ind
        for _ in range(n):
            kind = r.choices(
                ['let', 'branch', 'loop', 'ccall', 'qr', 'wide', 'call',
                 'unknown', 'alloc', 'bytes', 'simd', 'many'],
                [8, 6 if depth < 3 else 1, 4 if depth < 2 else 0, 3, 2, 2,
                 3 if self.funcs else 0, 2, 3, 2, 1, 1])[0]
            if out:
                out.append(f'{p}in')
            if kind == 'let':
                t = r.choice('IIIWWDF')
                v = self.fresh()
                out.append(f'{p}let !{v} = {self.expr(env, t)}')
                env.append((v, t))
            elif kind == 'many':
                vs = []
                for j in range(r.randint(6, 16)):
                    t = r.choice('IIIWWD')
                    v = self.fresh()
                    if j:
                        out.append(f'{p}in')
                    out.append(f'{p}let !{v} = {self.expr(env, t, 2)}')
                    vs.append((v, t))
                env.extend(vs)
            elif kind == 'branch':
                # A case whose arms define the same variables: a join point
                k = r.randint(1, 7)
                ts = self.types(k)
                vs = [self.fresh() for _ in ts]
                cond = self.expr(env, 'I', 1)
                arm = lambda: self.arm(list(env), depth + 1, ts, ind + 8)
                if r.random() < 0.3:
                    out.append(f'{p}let !(# {", ".join(vs)} #) = case {cond} of')
                    for a in range(r.randint(1, 4)):
                        out.append(f'{p}      {a}# ->')
                        out.extend(arm())
                    out.append(f'{p}      _ ->')
                    out.extend(arm())
                else:
                    out.append(f'{p}let !(# {", ".join(vs)} #) = case {cond} of')
                    out.append(f'{p}      0# ->')
                    out.extend(arm())
                    out.append(f'{p}      _ ->')
                    out.extend(arm())
                env.extend(zip(vs, ts))
            elif kind == 'loop':
                k = r.randint(1, 8)
                ts = self.types(k)
                vs = [self.fresh() for _ in ts]
                go = self.fresh('go')
                i = self.fresh('i')
                ps = [self.fresh('p') for _ in ts]
                bound = r.choice(['3#', '8#', '17#', f'(andI# {self.atom(env, "I")} 15#)'])
                inits = ' '.join(f'({self.expr(env, t, 2)})' for t in ts)
                out.append(f'{p}let !(# {", ".join(vs)} #) =')
                sig = ' -> '.join(HTY[t] for t in ['I'] + ts)
                res = ', '.join(HTY[t] for t in ts)
                out.append(f'{p}      let {go} :: {sig} -> (# {res} #)')
                out.append(f'{p}          {go} {i} {" ".join(ps)}')
                out.append(f'{p}            | isTrue# ({i} >=# {bound}) = (# {", ".join(ps)} #)')
                out.append(f'{p}            | otherwise =')
                lenv = list(env) + [(i, 'I')] + list(zip(ps, ts))
                body = self.stmts(lenv, depth + 1, r.randint(1, 4), ind + 14)
                out.extend(body)
                # Often the loop's parameters come back permuted: a parallel
                # move, with cycles, on the back edge
                def nxt(t, q):
                    same = [x for x, ty in zip(ps, ts) if ty == t]
                    return r.choice(same) if r.random() < 0.5 else self.expr(lenv, t, 2)
                nexts = ' '.join(f'({nxt(t, q)})' for t, q in zip(ts, ps))
                out.append(f'{p}              {go} ({i} +# 1#) {nexts}')
                out.append(f'{p}      in {go} 0# {inits}')
                env.extend(zip(vs, ts))
            elif kind == 'ccall':
                v = self.fresh()
                c = r.choice(['I', 'Is', 'D', 'Dm', 'F'])
                if c == 'I':
                    out.append(f'{p}let !(I# {v}) = c_labs (I# {self.atom(env, "I")})')
                    env.append((v, 'I'))
                elif c == 'Is':
                    out.append(f'{p}let !(I# {v}) = c_labs_safe (I# {self.atom(env, "I")})')
                    env.append((v, 'I'))
                elif c == 'D':
                    out.append(f'{p}let !(D# {v}) = c_fabs (D# {self.atom(env, "D")})')
                    env.append((v, 'D'))
                elif c == 'Dm':
                    out.append(f'{p}let !(D# {v}) = c_ldexp (D# {self.atom(env, "D")}) (fromIntegral (I# (andI# {self.atom(env, "I")} 7#)))')
                    env.append((v, 'D'))
                else:
                    out.append(f'{p}let !(F# {v}) = c_fabsf (F# {self.atom(env, "F")})')
                    env.append((v, 'F'))
            elif kind == 'qr':
                a, b = self.fresh(), self.fresh()
                if r.random() < 0.5:
                    out.append(f'{p}let !(# {a}, {b} #) = quotRemInt# {self.expr(env, "I", 2)} (orI# (andI# {self.atom(env, "I")} 4095#) 1#)')
                    env += [(a, 'I'), (b, 'I')]
                else:
                    out.append(f'{p}let !(# {a}, {b} #) = quotRemWord# {self.expr(env, "W", 2)} (or# {self.atom(env, "W")} 1##)')
                    env += [(a, 'W'), (b, 'W')]
            elif kind == 'wide':
                a, b, c = self.fresh(), self.fresh(), self.fresh()
                w = r.randint(0, 3)
                if w == 0:
                    out.append(f'{p}let !(# {c}, {a}, {b} #) = timesInt2# {self.atom(env, "I")} {self.atom(env, "I")}')
                    env += [(c, 'I'), (a, 'I'), (b, 'I')]
                elif w == 1:
                    out.append(f'{p}let !(# {a}, {b} #) = timesWord2# {self.atom(env, "W")} {self.atom(env, "W")}')
                    env += [(a, 'W'), (b, 'W')]
                elif w == 2:
                    out.append(f'{p}let !(# {a}, {b} #) = addIntC# {self.atom(env, "I")} {self.atom(env, "I")}')
                    env += [(a, 'I'), (b, 'I')]
                else:
                    out.append(f'{p}let !(# {a}, {b} #) = subWordC# {self.atom(env, "W")} {self.atom(env, "W")}')
                    env += [(a, 'W'), (b, 'I')]
            elif kind == 'call':
                f, ats, rts = r.choice(self.funcs)
                args = ' '.join(self.atom(env, t) for t in ats)
                vs = [self.fresh() for _ in rts]
                out.append(f'{p}let !(# {", ".join(vs)} #) = {f} {args}')
                env.extend(zip(vs, rts))
            elif kind == 'unknown':
                v = self.fresh()
                f = r.choice(['ukA', 'ukB', 'ukC'])
                out.append(f'{p}let !{v} = pick (I# (andI# {self.atom(env, "I")} 2#)) {f} {self.atom(env, "I")}')
                env.append((v, 'I'))
            elif kind == 'alloc':
                v = self.fresh()
                a = [self.atom(env, 'I') for _ in range(r.randint(1, 6))]
                bx = ', '.join(f'I# {x}' for x in a)
                n = r.choice(['2#', '9#', '40#'])
                out.append(f'{p}let !(I# {v}) = sumL (rep (I# {n}) [{bx}]) -- allocates')
                env.append((v, 'I'))
            elif kind == 'bytes':
                v = self.fresh()
                size = r.choice([1, 2, 7, 8, 16, 24, 31, 32, 64, 128])
                out.append(f'{p}let !{v} = bytes{size} {self.atom(env, "I")} {self.atom(env, "I")}')
                env.append((v, 'I'))
            elif kind == 'simd':
                a, b = self.fresh(), self.fresh()
                x = [self.atom(env, 'D') for _ in range(3)]
                out.append(f'{p}let !(# {a}, {b} #) = unpackDoubleX2# (plusDoubleX2# (packDoubleX2# (# {x[0]}, {x[1]} #)) (broadcastDoubleX2# {x[2]}))')
                env += [(a, 'D'), (b, 'D')]
        if out:
            out.append(f'{p}in')
        return out

    def arm(self, env, depth, ts, ind):
        p = ' ' * ind
        body = self.stmts(env, depth, self.r.randint(0, 3), ind)
        res = ', '.join(self.expr(env, t, 2) for t in ts)
        return body + [f'{p}(# {res} #)']

    def function(self, i):
        r = self.r
        name = f'f{i}'
        ats = self.types(r.choice([1, 2, 3, 4, 6, 8, 10, 12, 16]))
        rts = self.types(r.choice([1, 1, 2, 3, 5, 8])) + ['I']
        ps = [self.fresh('a') for _ in ats]
        env = list(zip(ps, ats))
        sig = ' -> '.join(HTY[t] for t in ats)
        res = ', '.join(HTY[t] for t in rts)
        lines = []
        if r.random() < 0.7:
            lines.append(f'{{-# NOINLINE {name} #-}}')
        lines.append(f'{name} :: {sig} -> (# {res} #)')
        lines.append(f'{name} {" ".join(ps)} =')
        lines.extend(self.stmts(env, 0, r.randint(2, self.size), 2))
        # The last result mixes every value bound, so all of them stay live to
        # the end: the allocator spills, reloads and fixes up joins
        res = [self.expr(env, t, 2) for t in rts[:-1]] + [self.mix(env)]
        lines.append(f'  (# {", ".join(res)} #)')
        self.funcs.append((name, ats, rts))
        return lines

    def main_lines(self):
        # Arguments out of NOINLINE opaque values, so nothing folds them away
        out = ['main :: IO ()', 'main = do']
        hidden = {'I': 'oi', 'W': 'ow', 'D': 'od', 'F': 'of1'}
        box = {'I': 'I#', 'W': 'W#', 'D': 'D#', 'F': 'F#'}
        for f, ats, rts in self.funcs:
            for k in range(3):
                vs = [self.fresh('r') for _ in rts]
                args = ' '.join(
                    f'({hidden[t]} {self.r.randint(0, 15)})' for t in ats)
                shows = ' ++ " " ++ '.join(f'show ({box[t]} {v})'
                                           for v, t in zip(vs, rts))
                out.append(f'  case {f} {args} of')
                out.append(f'    (# {", ".join(vs)} #) -> putStrLn ("{f} " ++ {shows})')
        return out

HEADER = r'''{-# LANGUAGE MagicHash, UnboxedTuples, BangPatterns, ExtendedLiterals #-}
{-# OPTIONS_GHC -Wno-all #-}
module Main (main) where
import GHC.Exts
import GHC.IO (IO (..))
import Foreign.C.Types

foreign import ccall unsafe "labs" c_labs :: Int -> Int
foreign import ccall safe "labs" c_labs_safe :: Int -> Int
foreign import ccall unsafe "fabs" c_fabs :: Double -> Double
foreign import ccall unsafe "fabsf" c_fabsf :: Float -> Float
foreign import ccall unsafe "ldexp" c_ldexp :: Double -> CInt -> Double

{-# NOINLINE ukA #-}
ukA, ukB, ukC :: Int# -> Int#
ukA x = x +# 1#
{-# NOINLINE ukB #-}
ukB x = x *# 3#
ukC x = notI# x

{-# NOINLINE pick #-}
pick :: Int -> (Int# -> Int#) -> Int# -> Int#
pick 0 _ x = ukB x
pick 2 _ x = ukC x
pick _ f x = f x

{-# NOINLINE rep #-}
rep :: Int -> [Int] -> [Int]
rep 0 _ = []
rep n xs = xs ++ rep (n - 1) (map (+ n) xs)

sumL :: [Int] -> Int
sumL = go 0 where
  go !a [] = a
  go !a (x : xs) = go (a + x) xs

ints :: [Int]
ints = [0, 1, -1, 2, 63, 64, 255, -128, 65535, 2147483648, maxBound, minBound, 12345, -987654321, 7, 42]
words' :: [Word]
words' = [0, 1, 2, 255, 256, 65535, 4294967295, 4294967296, maxBound, 12345, 987654321, 7, 42, 3, 8, 1024]
doubles :: [Double]
doubles = [0, 1, -1, 0.5, -0.25, 3.25, 1.0e10, -1.0e-3, 1.5, 2.5, 1024, 7, 42, -3.75, 1.0e300, 9.5]
floats :: [Float]
floats = [0, 1, -1, 0.5, -0.25, 3.25, 1.0e10, -1.0e-3, 1.5, 2.5, 1024, 7, 42, -3.75, 1.0e30, 9.5]
{-# NOINLINE oi #-}
oi :: Int -> Int#
oi k = case ints !! k of I# x -> x
{-# NOINLINE ow #-}
ow :: Int -> Word#
ow k = case words' !! k of W# x -> x
{-# NOINLINE od #-}
od :: Int -> Double#
od k = case doubles !! k of D# x -> x
{-# NOINLINE of1 #-}
of1 :: Int -> Float#
of1 k = case floats !! k of F# x -> x
'''

def bytes_fun(size):
    return f'''
bytes{size} :: Int# -> Int# -> Int#
bytes{size} a b = case runRW# (\\s0 -> case newByteArray# {size * 2}# s0 of
  (# s1, m #) -> case setByteArray# m 0# {size * 2}# (andI# a 255#) s1 of
    s2 -> case writeWord8Array# m (remInt# (andI# b 65535#) {size}#) (wordToWord8# (int2Word# b)) s2 of
      s3 -> case copyMutableByteArrayNonOverlapping# m 0# m {size}# {size}# s3 of
        s4 -> case readWord8Array# m (remInt# (andI# a 65535#) {size}# +# {size}#) s4 of
          (# s5, w #) -> case readWord8Array# m (remInt# (andI# b 65535#) {size}#) s5 of
            (# s6, x #) -> (# s6, I# (word2Int# (word8ToWord# w) +# (256# *# word2Int# (word8ToWord# x))) #)) of
  (# _, I# r #) -> r
'''

def program(seed, size=6):
    g = G(seed, size)
    bodies = []
    for i in range(g.r.randint(3, 6)):
        bodies.extend(g.function(i))
        bodies.append('')
    out = [HEADER]
    out += [bytes_fun(s) for s in [1, 2, 7, 8, 16, 24, 31, 32, 64, 128]]
    out += ['\n'.join(bodies), '\n'.join(g.main_lines())]
    return '\n'.join(out) + '\n'


def arguments(text, name):
    """The two arguments of each application of the primop name in text."""
    out = []
    for m in re.finditer(r'\(' + name + ' ', text):
        i, args = m.end(), []
        while len(args) < 2:
            depth, start = 0, i
            while depth or text[i] not in ' )':
                depth += {'(': 1, ')': -1}.get(text[i], 0)
                i += 1
            args.append(text[start:i])
            i += 1
        out.append(args)
    return out


# A mark of each kind of statement and of the primops the docstring names.
MARKS = [r'let !\(# ', ' = case ', r'let go\d+ :: ', r'go\d+ \(i\d+ \+# 1#\)', 'c_labs ',
         'c_labs_safe ', 'c_fabs ', 'c_fabsf ', 'c_ldexp ', 'quotRemInt# ',
         'quotRemWord# ', 'timesInt2# ', 'timesWord2# ', 'addIntC# ', 'subWordC# ',
         ' = pick ', 'sumL \\(rep ', r' = bytes\d+ ', 'plusDoubleX2# ', 'fmaddDouble# ',
         'popCnt# ', 'clz# ', 'narrow8Int# ', 'pdep# ']
# The operands that must keep a primop defined on every input.
GUARDS = {'uncheckedIShiftL#': r'\(andI# .* 63#\)$', 'uncheckedIShiftRA#': r'\(andI# .* 63#\)$',
          'uncheckedIShiftRL#': r'\(andI# .* 63#\)$', 'uncheckedShiftL#': r'\(andI# .* 63#\)$',
          'uncheckedShiftRL#': r'\(andI# .* 63#\)$', 'quotInt#': r'\(orI# .* 1#\)$',
          'remInt#': r'(\(orI# .* 1#\)|[1-9][0-9]*#)$', 'quotWord#': r'\(or# .* 1##\)$',
          'remWord#': r'\(or# .* 1##\)$'}


def self_test():
    bad = []
    if program(5) != program(5):
        bad.append('one seed gave two programs')
    if program(5) == program(6):
        bad.append('two seeds gave one program')
    if program(5) == program(5, 12):
        bad.append('--size changed nothing')
    texts = [program(s) for s in range(1, 41)]
    whole = '\n'.join(texts)
    for mark in MARKS:
        if not re.search(mark, whole):
            bad.append(f'no program in 40 has {mark!r}')
    for name, guard in GUARDS.items():
        args = arguments(whole, name)
        if not args:
            bad.append(f'no program in 40 has {name}')
        for a in args:
            if not re.match(guard, a[1]):
                bad.append(f'{name}\'s operand {a[1][:60]} may be out of range')
                break
    g = G(1, 6)
    env = [('x', 'I'), ('y', 'W'), ('z', 'D'), ('u', 'F')]
    if not all(re.search(rf'\b{v}\b', g.mix(env)) for v, _ in env):
        bad.append(f'mix leaves a value out: {g.mix(env)}')
    # Each function is called three times, its results printed.
    g = G(1, 6)
    g.funcs = [('f0', ['I'], ['I'])]
    lines = '\n'.join(g.main_lines())
    if lines.count('case f0 ') != 3 or lines.count('putStrLn') != 3:
        bad.append(f'main: {lines[:200]}')
    for x in bad:
        print('FAIL', x)
    print('ok   gen.py self-test' if not bad else f'{len(bad)} failed')
    return 1 if bad else 0


def main():
    if sys.argv[1:] == ['--self-test']:
        return self_test()
    if len(sys.argv) not in (2, 4) or (len(sys.argv) == 4 and sys.argv[2] != '--size'):
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    size = int(sys.argv[3]) if len(sys.argv) == 4 else 6
    # print's newline and the blank lines between parts are part of the program
    sys.stdout.write(program(int(sys.argv[1]), size))
    return 0


if __name__ == '__main__':
    sys.exit(main())
