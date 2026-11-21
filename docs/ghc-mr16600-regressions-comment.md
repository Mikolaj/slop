# GHC merge request comment: !16600's tip f4e950c720 against its base 83038fbee5, six regressions traced to c38f35da9b and f4e950c720 with a reproducer each, and a laziness bug on master that c38f35da9b fixes

Staged and posted 2026-11-21 as a comment on GHC [!16600](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600), "Don't push `case` inside `let` in Gentle simplification" (open, by simonpj, head f4e950c720 when read at 20:5x), answering simonpj's [note 713327](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600#note_713327) and reporting what [note 713315](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600#note_713315) offered to run; this file stays as the record of the comment. The text from "Measured as offered above" down is the body. A fresh agent wrote it from the session's collected facts, with no variant of the tip carrying another fix named in it; the session then made five small edits: the attribution sentence's quantifier, the permutation benchmarks' exact names, joinlost-vector's allocation by compiler and level, an unlocated call-site count dropped, and R.hs dropped from what the tip fixes of #28164 (master keeps R.hs's float); later its shorthand "Gentle pass" became the commit title's "Gentle simplification". Posted as [note 713357](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600#note_713357), which Mikolaj edited on 2026-11-22: in "Not traced", "code layout not ruled out" became "the generated code was not compared"; and, at the session's request after its checks, in section 4 "which SetLevels never floats" became the rule SetLevels applies, that a bottoming binding goes to the top only if it is not a join point; in section 5 the clause saying master duplicates partition's per-element step was confined to the three places where master's Core does so, master otherwise building the same join points; and in section 6 "final loop" became "final `isWideChar`", the binding the sizes are of. The body here is the note's as read at 13:5x on 2026-11-22, without the preface he wrote above it. Measured 2026-11-21 on perf-flavour builds of master 83038fbee5 and of the tip, and on stage-1 builds of e9551156d0, c38f35da9b and the tip without f4e950c720, run with -B over the tip's libraries; every reproducer re-run by the session; the pasted sources byte-identical to the reproducers' files; every figure of the prose found in the measurements by script.

Measured as offered above, on !16600 itself: its tip f4e950c720 against its base, master 83038fbee5, both perf flavour built from nothing, x86_64 Linux. "The tip without f4e950c720" is a compiler of the tip with only that commit's compiler change reverted, run over the tip's libraries (the tip's own compiler run the same way gives the tip's figures). Instructions are user-space instructions (`perf stat -e instructions:u`), allocation the RTS's.

**Summary.** Against master, the geomeans of nofib, containers and megaparsec move by -0.21% to +0.52%, vector's by +1.68% (-O2) and +2.48% (-O1); GHC's perf tests improve (compile-time allocation -0.70%, no row above its window). Six regressions are traced to a mechanism, each with a reproducer below; two of the reproducers are not minimized. containers' sequence replicateA/State rise is not a regression: it is the price of a laziness bug on master that c38f35da9b fixes (section 7). Figures of c38f35da9b's regressions are of the tip without f4e950c720 against master; the tip has them too.

| | Benchmark | Against master | Commit | What changes | Reproducer |
|---|---|---|---|---|---|
| 1 | nofib shootout/reverse-complement, -O1 | x2.03 instructions | f4e950c720 | a case binder without an unfolding in Gentle lets float-out's reverse binder swap turn a loop into a top-level function over the CAF | caf |
| 2 | vector Applicative.generateState | +44.35% instructions, +24.65% allocation (-O2) | c38f35da9b, `bindingOk` | makeTrivial refuses a `let` argument of `W64#`, so a box per element survives | boxarg |
| 3 | vector next/prevPermutation (small vector, until end) | +18.0%/+16.2% (-O2), +29.6% (-O1) | c38f35da9b, Gentle simplification | `K[let binds in e]` no longer becomes `let binds in K[e]`; the inner loop stops being a join point | joinlost-vector, not minimized |
| 4 | containers intmap index | +2.60% | c38f35da9b, Gentle simplification | an argument pushed into a `case` makes `not_found` a join point that float-out never floats; `$w!` outgrows the inlining threshold | notfound |
| 5 | containers sequence partition | +1.04% to +1.14% | c38f35da9b, Gentle simplification | an argument pushed into a `case` makes `f` inlined at every site; join points re-evaluate the strict pair's fields | strictpair |
| 6 | megaparsec reachOffsetNoLine, -O1 | +1.47% | c38f35da9b | a binary search reads the array element directly and duplicates a join point into the branches | mpreach, not minimized |

The reproducers but joinlost-vector were also compiled by compilers built at e9551156d0 and at c38f35da9b, run the same way: each but caf gives master's figure at e9551156d0 and its regressed figure at c38f35da9b, unchanged by ffc053c4e5 and f4e950c720 (except notfound, which f4e950c720 brings down 0.5%); caf changes only at f4e950c720. joinlost-vector's attribution to c38f35da9b rests on its Core after the Gentle Simplifier run and c38f35da9b's message, not on such a build. e9551156d0's compiler, run over the tip's libraries, matches master within 25,000 instructions on every reproducer, so the libraries do not matter.

## Overall

Geomeans against master 83038fbee5 (instructions; method at the end):

```
                       tip       tip without f4e950c720
nofib instr -O2        -0.21%    -0.22%
nofib instr -O1        +0.52%    -0.11%
nofib instr -O0        -0.01%    -0.01%
containers -O2         -0.13%    -0.04%
containers -O1         -0.06%    +0.04%
megaparsec -O2         -0.20%    -0.20%
megaparsec -O1         +0.05%    +0.05%
vector -O2             +1.68%    +2.23%
vector -O1             +2.48%    +2.87%
```

nofib, tip against master: program allocation geomean -0.35%, -0.18%, +0.03% at -O2, -O1, -O0; compiler allocation -0.31%, -0.38%, -0.20%; compiler instructions +0.035%, -0.031%, -0.024%. Largest program falls: spectral/ansi -10.2% (-O2), shootout/k-nucleotide -3.3% (-O2).

GHC's perf tests, tip against master (326 rows): compile-time bytes allocated geomean -0.70%; no row above its CI acceptance window; four below, each named under Metric Decrease in an MR commit message: T26989 -52.7%, T26425 -5.6%, CoOpt_Read -5.5%, T18730 -2.4%. Runtime allocation geomean -0.002%.

Gains of f4e950c720: containers IntMap symmetricDifference rows -4% to -6%, intmap lookup_mixed -4.1%; vector's six *Bijective permutations -2.0% to -3.0%; nofib real/smallpt allocation -1.5%. Gains of the rest of the MR: containers graph bcc.rand -24.5%, -17.4%, -7.6%, bcc.line,n=100 -3.2% (-O2); nofib spectral/ansi -10%, k-nucleotide -3.3%.

## 1. nofib shootout/reverse-complement at -O1: f4e950c720

nofib's shootout/reverse-complement at -O1 runs 8,652,909,372 instructions on master and 17,533,349,222 on the tip (x2.03). Without f4e950c720 the -O1 Core is identical to master's. At -O2 both are at about 8.55e9 (master 8,567,947,781, tip 8,552,768,425).

Mechanism (`-dverbose-core2core`, -O1). `revcomp` forces the CAF `ca` (``ca `seq` ...``), and the loop rc/rc1/rc2 bound inside reads the table through `comp = peekElemOff ca . fromIntegral`. After the first (Gentle) Simplifier run, master has resolved the loop's `ca` to the field of the outer `case ca of Ptr ipv`; the tip leaves `case wild of { Ptr a -> ... }` in the loop, `wild` being the case binder of the outer case, which under f4e950c720 has no unfolding in the Gentle phase (Ptr's alternative has a field, so the `null bndrs` exemption does not apply). The first float-out then floats rc and rc1 to top level: SetLevels' reverse binder swap (`extendCaseBndrEnv`) replaces `wild` by the global `ca`, leaving no free local variable. Final Core: top-level `$wrc`/`$wrc1`, called functions doing `case ca of { Ptr a -> ... }` on every iteration, where master has join points reading the field. At -O2, liberate-case peels `$wrc1`'s first iteration, so the inner loop reads the field and the count is master's.

Reproducer **caf**, one module, base only: the same shape, a top-level table `tbl` forced by `seq` and a loop bound inside it whose only free variable is `tbl`. `ghc -O1 -rtsopts Main.hs -o caf && ./caf 1000000 200`, output 127493856 on all three compilers: master 1,677,665,848 instructions, tip 6,677,640,108 (x3.98), tip without f4e950c720 1,677,656,525; allocation 56,707,456 bytes on master, 56,707,392 on the tip.

<details><summary>caf: Main.hs</summary>

```haskell
{-# LANGUAGE BangPatterns, MagicHash, UnboxedTuples #-}
module Main (main) where

import Foreign
import GHC.Exts (realWorld#)
import GHC.IO (IO (..))
import System.Environment (getArgs)

{-# INLINE inlinePerformIO #-}
inlinePerformIO :: IO a -> a
inlinePerformIO (IO m) = case m realWorld# of (# _, r #) -> r

-- A table built once, as a top-level value.
tbl :: Ptr Word8
tbl = inlinePerformIO $ do
  a <- mallocBytes 256
  mapM_ (\i -> pokeByteOff a (fromIntegral i) (255 - i)) [0 .. 255 :: Word8]
  return a

-- Forces tbl, then translates buf in place by a loop bound inside the seq,
-- whose only free variable is tbl.
translate :: Ptr Word8 -> Int -> IO ()
translate buf n = tbl `seq`
  let go :: Ptr Word8 -> Ptr Word8 -> IO ()
      go !p !e
        | p < e = do
            x <- peek p
            y <- peekElemOff tbl (fromIntegral x)
            poke p y
            go (p `plusPtr` 1) e
        | otherwise = return ()
  in go buf (buf `plusPtr` n)

main :: IO ()
main = do
  [n, k] <- map read <$> getArgs
  buf <- mallocBytes n
  mapM_ (\i -> pokeElemOff buf i (fromIntegral i :: Word8)) [0 .. n - 1]
  mapM_ (\_ -> translate buf n) [1 .. k :: Int]
  s <- sum <$> mapM (fmap fromIntegral . peekElemOff buf) [0 .. n - 1] :: IO Int
  print s
```

</details>

## 2. vector Applicative.generateState: c38f35da9b, `bindingOk`

vector-0.13.2.0's benchmark `Applicative.generateState` (vector-bench-papi), tip without f4e950c720 against master: +44.35% instructions and +24.65% allocation at -O2, +42.91% and +18.00% at -O1 (tip: +44.3%/+24.7%, +42.9%/+18.0%).

Mechanism. In `$wgenerateState`'s inner loop master binds `a1 :: Word64#` to `xor64# ...` and the write closure captures the unboxed word; the tip has `a1 = W64# (let x# = .. in let x#1 = .. in xor64# ..)`, a 16-byte box per element (the whole allocation rise). The compilers first differ in the Phase 1 [main] Simplifier run, where generateA and splitmix's nextWord64 inline (nextWord64's unfolding is identical under both). Case-of-known-constructor binds the pair's field through knownCon -> bind_args -> simplAuxBind -> prepareRhs -> makeTrivialArg -> makeTrivial. c38f35da9b changed `bindingOk` for a non-top-level binder from `True` to `not (needsCaseBinding expr_ty expr)`; `exprOkForSpeculation` is False on any `Let`, so makeTrivial now refuses the argument, `W64#` keeps a non-trivial argument, `a1` gets no constructor-application unfolding, and the box survives. Master let-bound the argument; the binding became a case (wrapFloats, FltCareful, mkCoreLet, bindNonRec), the lets floated out of it and the box cancelled. The new Note [Cannot trivialise] says "we lose nothing" by not trivialising such an expression; that fails when the argument is a let whose body is ok for speculation. A source-level `W64# (let ..)` keeps the box on both compilers: the knownCon path is needed.

Reproducer **boxarg**, base only: Main.hs is a generateA-like lazy state loop building write closures; SM.hs is a copy of splitmix's nextWord64 and mix64, in a second module because the consumer must see the optimised cross-module unfolding. `ghc -O2 -rtsopts Main.hs SM.hs -o boxarg && ./boxarg 2000000 5 +RTS -s`, output 422533413578939533 on both compilers. -O2: 649,130,552 -> 809,130,488 bytes (+24.6%), 5,707,203,870 -> 8,239,847,390 instructions (+44.4%). -O1: 889,130,736 -> 1,049,130,672 bytes (+18.0%), 5,887,456,649 -> 8,321,643,030 instructions (+41.3%). (Master -> tip.)

<details><summary>boxarg: Main.hs</summary>

```haskell
{-# LANGUAGE MagicHash, UnboxedTuples, RankNTypes, BangPatterns #-}
-- | vector's generateA in a lazy state monad over splitmix (the benchmark
-- generateState), cut down to base: each element becomes a write closure
-- capturing the generated Word64, as vector's STA does.
module Main (main) where
import GHC.Exts
import GHC.IO (IO (..))
import GHC.Word
import System.Environment
import SM

newtype Act = Act (forall s. MutableByteArray# s -> State# s -> State# s)

gen :: Int -> SMGen -> (Act, SMGen)
gen n = go 0
  where
    go !i g
      | i >= n = (Act (\_ s -> s), g)
      | otherwise = case nextWord64 g of
          (w, g') -> case go (i + 1) g' of
            (Act rest, g'') ->
              ( Act (\mba s -> case w of
                       W64# x -> case i of
                         I# i# -> rest mba (writeWord64Array# mba i# x s))
              , g'' )

run :: Int -> IO Word
run n@(I# n#) = case gen n (SMGen 9297814886316923340 13679457532755275413) of
  (Act f, _) -> IO (\s -> case newByteArray# (n# *# 8#) s of
    (# s1, mba #) -> case f mba s1 of
      s2 -> let loop i acc s3 | isTrue# (i >=# n#) = (# s3, W# acc #)
                              | otherwise = case readWordArray# mba i s3 of
                                  (# s4, x #) -> loop (i +# 1#) (plusWord# acc x) s4
            in loop 0# 0## s2)

main :: IO ()
main = do
  [ns, rs] <- getArgs
  let n = read ns; reps = read rs :: Int
  let go k !acc | k > reps = return acc
                | otherwise = run (n + k - k) >>= \x -> go (k + 1) (acc + x)
  go 1 0 >>= print
```

</details>

<details><summary>boxarg: SM.hs</summary>

```haskell
-- | splitmix's SMGen and nextWord64 (splitmix-0.1.3.2), inlined here so the
-- reproducer depends on base only.  Compiled separately: the consumer must see
-- nextWord64's optimised unfolding, (W64# (let x# = .. in ..), SMGen ..).
module SM (SMGen (..), nextWord64) where
import Data.Bits
import Data.Word

data SMGen = SMGen !Word64 !Word64

nextWord64 :: SMGen -> (Word64, SMGen)
nextWord64 (SMGen seed gamma) = (mix64 seed', SMGen seed' gamma)
  where seed' = seed + gamma

mix64 :: Word64 -> Word64
mix64 z0 = shiftXor 33 (shiftXorMultiply 33 0xc4ceb9fe1a85ec53 (shiftXorMultiply 33 0xff51afd7ed558ccd z0))

shiftXor :: Int -> Word64 -> Word64
shiftXor n w = w `xor` (w `shiftR` n)

shiftXorMultiply :: Int -> Word64 -> Word64 -> Word64
shiftXorMultiply n k w = shiftXor n w * k
```

</details>

## 3. vector next/prevPermutation: c38f35da9b, Gentle simplification

vector-0.13.2.0's benchmarks `(next|prev)Permutation.nextPermutation (small vector, until end)` and `prevPermutation (small vector, until end)` (vector-bench-papi), tip without f4e950c720 against master: +18.0%/+16.2% instructions at -O2 (allocation unchanged); +29.6% each, allocation +15%, at -O1.

Mechanism. Master's inner loop `$wdecrLoop` is a `joinrec` inside `joinrec loop`; on the tip it is a `letrec` outside `loop`, and `loop` does `case ($wdecrLoop ..) of (# s, b #) -> case b of { False -> ..; True -> jump loop }`: a call and a returned Bool per permutation where master jumps. First difference in the Gentle Simplifier run: master has `letrec loop = \s -> let dim .. in letrec decrLoop .. in K[..]`, the tip `joinrec loop s = case (let dim .. in letrec decrLoop .. in ..) of K`. This is c38f35da9b's change that, with case-of-case off, no longer turns `K[let binds in e]` into `let binds in K[e]` (splitContForNoCaseCase). Which later pass moves decrLoop out of loop is not pinned.

Reproducer **joinlost-vector**, NOT minimized: Perm.hs is vector's benchlib `loopPermutations` verbatim, Main.hs a driver, built against vector-0.13.2.0 compiled by the same compiler. Base-only ports of nextPermutation over `Ptr Int` in IO and in ST did not reproduce. `ghc -O2 -rtsopts -package vector Perm.hs Main.hs -o perm && ./perm 9 200`, output (9,200) on both compilers. Master -> tip: -O2 3,709,867,924 -> 4,759,094,313 instructions (+28.3%); -O1 4,105,914,787 -> 5,319,266,400 (+29.6%); allocation 76,720 bytes on master at both levels, 76,656 (-O2) and 81,456 (-O1) on the tip.

<details><summary>joinlost-vector: Perm.hs and Main.hs</summary>

```haskell
module Perm (loopPermutations) where
import qualified Data.Vector.Unboxed.Mutable as M
-- | Repeat @nextPermutation@ on @[0..n-1]@ until the end (copied from vector's benchlib).
loopPermutations :: Int -> IO ()
loopPermutations n = do
  v <- M.generate n id
  let loop = do
        res <- M.nextPermutation v
        if res then loop else return ()
  loop
```

```haskell
module Main (main) where
import Control.Monad
import System.Environment
import Perm (loopPermutations)
main :: IO ()
main = do
  [ks, rs] <- getArgs
  let k = read ks; reps = read rs :: Int
  replicateM_ reps (loopPermutations k)
  print (k, reps)
```

</details>

## 4. containers IntMap index: c38f35da9b, Gentle simplification

containers-tests 0.8.1 `intmap-benchmarks/All.index`, tip without f4e950c720 against master: +2.60% at -O2 and -O1.

Mechanism. Master inlines the worker `$w!` into the lookup loop (indexMany); the MR calls it once per key: `-dinline-check '$w!'` gives size 112 under master (inlined), 192 under the MR (refused). `$w!` grew because find's `not_found = error ...` stays inline: master's first float-out lifts it to a top-level bottoming function; under the MR it is a join point, and SetLevels sends a bottoming binding to the top, abstracted over its free variables, only if it is not a join point. First divergence in the Gentle Simplifier run: in `(case k of I# ipv -> ... go) m` master keeps the argument `m` outside the case (reallyRebuildCase with case-of-case off simplifies the alternatives against a Stop); the MR pushes `m` inside through splitContForNoCaseCase / splitContArgs in simplExprF1's Case equation, so go and not_found are join points already in the Gentle run.

Reproducer **notfound**, base only: find and (!) are containers' code nearly verbatim, with the map cut to Bin/Tip/Nil; two modules, because the cross-module unfolding of `$w!` is the point. `ghc -O2 -fproc-alignment=64 -rtsopts Main.hs -o nf && ./nf 2000`, output ((),16384) on all three compilers: master 3,101,572,422 instructions, tip without f4e950c720 3,232,822,727 (+4.2%), tip 3,216,430,577 (+3.7%); 1,759,432 vs 1,759,416 bytes.

<details><summary>notfound: IM.hs</summary>

```haskell
{-# LANGUAGE BangPatterns #-}
-- The parts of containers' Data.IntMap.Internal that (!) needs.
module IM (IntMap(..), Prefix(..), fromAscList, (!), size) where

newtype Prefix = Prefix Int

data IntMap a = Bin {-# UNPACK #-} !Prefix !(IntMap a) !(IntMap a)
              | Tip {-# UNPACK #-} !Int a
              | Nil

left :: Int -> Prefix -> Bool
left i (Prefix p) = (fromIntegral i :: Word) < fromIntegral p
{-# INLINE left #-}

(!) :: IntMap a -> Int -> a
(!) m k = find k m

find :: Int -> IntMap a -> a
find !k = go
  where
    go (Bin p l r) | left k p  = go l
                   | otherwise = go r
    go (Tip kx x) | k == kx   = x
                  | otherwise = not_found
    go Nil = not_found

    not_found = error ("IntMap.!: key " ++ show k ++ " is not an element of the map")

size :: IntMap a -> Int
size (Bin _ l r) = size l + size r
size (Tip _ _) = 1
size Nil = 0

-- Balanced map over the keys lo..hi (lo <= hi, hi - lo + 1 a power of two),
-- prefixes as in containers: the midpoint's bit.
fromAscList :: Int -> Int -> IntMap Int
fromAscList lo hi
  | lo == hi = Tip lo lo
  | otherwise = let mid = (lo + hi + 1) `div` 2
                in Bin (Prefix mid) (fromAscList lo (mid - 1)) (fromAscList mid hi)
```

</details>

<details><summary>notfound: Main.hs</summary>

```haskell
{-# LANGUAGE BangPatterns #-}
-- containers intmap-benchmarks "index": 8192 lookups of even keys in a
-- 16384-element map, repeated n times.
module Main (main) where
import IM
import Data.List (foldl')
import Control.Exception (evaluate)
import System.Environment (getArgs)

indexMany :: [Int] -> IntMap a -> ()
indexMany xs !m = foldl' (\_ k -> m ! k `seq` ()) () xs

loop :: Int -> [Int] -> IntMap Int -> IO ()
loop 0 _ _ = pure ()
loop n xs m = evaluate (indexMany xs m) >> loop (n - 1) xs m
{-# NOINLINE loop #-}

main :: IO ()
main = do
  [a] <- getArgs
  let m = fromAscList 0 16383
      evens = [ (k * 2654435761) `mod` 16384 | k <- [0, 2 .. 16382 :: Int] ]
  _ <- evaluate (size m)
  _ <- evaluate (sum evens)
  loop (read a) evens m
  print (indexMany evens m, size m)
```

</details>

## 5. containers Seq partition: c38f35da9b, Gentle simplification

containers-tests 0.8.1 `sequence-benchmarks/All.partition.N`, tip without f4e950c720 against master: +1.04% to +1.14% at -O2 and -O1.

Mechanism. The MR's partition builds join points over the strict pair's fields and evaluates them again (`case xs of nt2 {__DEFAULT -> ..}`); master does the same, except at the last element of a `Node2`, of a `Node3` and of a `Two` prefix digit, where it duplicates the per-element step with the fields known to be evaluated. First divergence in the Gentle run: foldl' over a Digit is written `(f $! ...) b`, i.e. `(case .. of vx -> f vx) b`; master leaves `b` outside and `f` a shared let, the MR pushes `b` inside, so `f` is saturated and inlined at every site and case-of-case later turns the copies into join points.

Reproducer **strictpair**, one module, base only, a minimized analogue; it regresses only with partitionD NOINLINE and the predicate abstract, as in the library. `ghc -O1 -rtsopts Main.hs -o sp && ./sp 2000`, output 0 on all three compilers: master 489,569,201 instructions, tip without f4e950c720 497,582,697 (+1.6%), tip the same; 152,195,192 vs 152,195,160 bytes.

<details><summary>strictpair: Main.hs</summary>

```haskell
{-# LANGUAGE BangPatterns #-}
-- Data.Sequence.partition's shape: a foldl' through a strict pair, over a
-- digit-like node whose foldl' is written with ($!).
module Main (main) where
import System.Environment (getArgs)

data StrictPair a b = !a :*: !b

data T = E | C !Int T
newtype S = S T

snocS :: S -> Int -> S
snocS (S t) x = S (C x t)
{-# NOINLINE snocS #-}

lenS :: S -> Int
lenS (S t) = go 0 t where go !n E = n
                          go !n (C _ r) = go (n + 1) r

data Digit a = One a | Two a a | Three a a a | Four a a a a

-- as Data.Sequence.Internal's Foldable Digit foldl'
foldlD' :: (b -> a -> b) -> b -> Digit a -> b
foldlD' f !z (One a) = f z a
foldlD' f !z (Two a b) = (f $! f z a) b
foldlD' f !z (Three a b c) = (f $! (f $! f z a) b) c
foldlD' f !z (Four a b c d) = (f $! (f $! (f $! f z a) b) c) d
{-# INLINE foldlD' #-}

-- as Data.Sequence.partition
partitionD :: (Int -> Bool) -> StrictPair S S -> Digit Int -> StrictPair S S
partitionD p acc = foldlD' part acc
  where
    part (xs :*: ys) x
      | p x       = (xs `snocS` x) :*: ys
      | otherwise = xs :*: (ys `snocS` x)
{-# NOINLINE partitionD #-}

digits :: [Digit Int]
digits = [ case i `mod` 4 of { 0 -> One i; 1 -> Two i (i+1); 2 -> Three i (i+1) (i+2); _ -> Four i (i+1) (i+2) (i+3) } | i <- [0 .. 999] ]

run :: Int -> Int -> Int
run 0 !acc = acc
run n !acc = case go (S E :*: S E) digits of xs :*: ys -> run (n - 1) (acc + lenS xs - lenS ys)
  where go !z [] = z
        go !z (d : ds) = go (partitionD (\x -> even (x + n)) z d) ds
{-# NOINLINE run #-}

main :: IO ()
main = do
  [a] <- getArgs
  print (run (read a) 0)
```

</details>

## 6. megaparsec reachOffsetNoLine at -O1: c38f35da9b

megaparsec-9.8.1 bench-speed `reachOffsetNoLine-0-1000` and siblings, tip without f4e950c720 against master: +1.47% at -O1. reachOffset and errorBundlePretty (+0.9% to +1.24%) are presumably the same, not checked.

Mechanism. The difference is in megaparsec's Text.Megaparsec.Unicode binary searches isZeroWidthChar and isWideChar, run for every character. The Gentle and float-out outputs are identical; the first divergence is the next Simplifier run on identical input: master keeps the lazy binding `(a,b) = wideCharRanges ! mid` and a join point `$j` sharing it; the MR reads the array element directly, duplicates `$j` into the branches and adds exit join points (final `isWideChar` 151 terms vs 117).

Reproducer **mpreach**, NOT minimized; needs text and array, shipped with GHC. U.hs is megaparsec-9.8.1's Text/Megaparsec/Unicode.hs verbatim, its module renamed to `U` (223 lines, not pasted here); S.hs copies megaparsec's Pos, SourcePos, PosState, charInc and reachOffsetNoLine' nearly verbatim; Main.hs is the driver. `ghc -O1 -fproc-alignment=64 -rtsopts Main.hs -o mp && ./mp 1000 2000`, output 320020000 on all three compilers: master 119,399,709,080 instructions, tip without f4e950c720 121,159,707,181 (+1.47%), tip the same; 7,840,351,592 vs 7,840,351,528 bytes.

<details><summary>mpreach: S.hs</summary>

```haskell
{-# LANGUAGE BangPatterns, MultiWayIf, RecordWildCards #-}
-- megaparsec-9.8.1's Pos, SourcePos, PosState, charInc and reachOffsetNoLine'
-- (Text.Megaparsec.Pos, .State, .Stream), instantiated at Text as its
-- TraversableStream Text instance does.
module S (Pos(..), SourcePos(..), PosState(..), mkPos, reachOffsetNoLineText) where
import Control.Exception (Exception, throw)
import qualified Data.Text as T
import qualified U as Unicode

newtype Pos = Pos Int deriving (Show, Eq, Ord)
data InvalidPosException = InvalidPosException Int deriving Show
instance Exception InvalidPosException

mkPos :: Int -> Pos
mkPos a = if a <= 0 then throw (InvalidPosException a) else Pos a
{-# INLINE mkPos #-}

unPos :: Pos -> Int
unPos (Pos w) = w
{-# INLINE unPos #-}

pos1 :: Pos
pos1 = mkPos 1

instance Semigroup Pos where
  (Pos x) <> (Pos y) = Pos (x + y)
  {-# INLINE (<>) #-}

data SourcePos = SourcePos
  { sourceName :: FilePath, sourceLine :: !Pos, sourceColumn :: !Pos }
  deriving (Show, Eq)

data PosState s = PosState
  { pstateInput :: s, pstateOffset :: !Int, pstateSourcePos :: !SourcePos,
    pstateTabWidth :: Pos, pstateLinePrefix :: String }
  deriving (Show, Eq)

charInc :: Char -> Pos -> Pos
charInc ch c
  | Unicode.isZeroWidthChar ch = c
  | Unicode.isWideChar ch = c <> pos1 <> pos1
  | otherwise = c <> pos1

reachOffsetNoLine' ::
  (Int -> s -> (t, s)) -> (forall b. (b -> Char -> b) -> b -> t -> b) ->
  (Char, Char) -> (Char -> Pos -> Pos) -> Int -> PosState s -> PosState s
reachOffsetNoLine' splitAt' foldl'' (newlineTok, tabTok) columnIncrement o PosState {..} =
    ( PosState
        { pstateInput = post,
          pstateOffset = max pstateOffset o,
          pstateSourcePos = spos,
          pstateTabWidth = pstateTabWidth,
          pstateLinePrefix = pstateLinePrefix
        }
    )
    where
      spos = foldl'' go pstateSourcePos pre
      (pre, post) = splitAt' (o - pstateOffset) pstateInput
      go (SourcePos n l c) ch =
        let c' = unPos c
            w = unPos pstateTabWidth
         in if
              | ch == newlineTok -> SourcePos n (l <> pos1) pos1
              | ch == tabTok -> SourcePos n l (mkPos $ c' + w - ((c' - 1) `rem` w))
              | otherwise -> SourcePos n l (columnIncrement ch c)
{-# INLINE reachOffsetNoLine' #-}

reachOffsetNoLineText :: Int -> PosState T.Text -> PosState T.Text
reachOffsetNoLineText o pst = reachOffsetNoLine' T.splitAt T.foldl' ('\n', '\t') charInc o pst
```

</details>

<details><summary>mpreach: Main.hs</summary>

```haskell
-- megaparsec-9.8.1 bench-speed reachOffsetNoLine-0-N: nf of the PosState
-- reached after o1*80 characters 'a'.
module Main (main) where
import qualified Data.Text as T
import Control.Exception (evaluate)
import System.Environment (getArgs)
import S

f :: (Int, Int) -> PosState T.Text
f (startOffset, targetOffset) =
  reachOffsetNoLineText targetOffset
    PosState { pstateInput = T.replicate (targetOffset - startOffset) (T.pack "a"),
               pstateOffset = startOffset,
               pstateSourcePos = SourcePos "" (mkPos 1) (mkPos 1),
               pstateTabWidth = mkPos 8, pstateLinePrefix = "" }

force :: PosState T.Text -> Int
force (PosState i o (SourcePos n l c) w p) = T.length i + o + length n + unP l + unP c + unP w + length p
  where unP (Pos x) = x

loop :: Int -> Int -> Int -> Int -> IO Int
loop 0 _ _ acc = pure acc
loop n a b acc = do { r <- evaluate (force (f (a, b))); loop (n - 1) a b (acc + r) }
{-# NOINLINE loop #-}

main :: IO ()
main = do
  [o1, n] <- map read <$> getArgs
  loop n 0 (o1 * 80) 0 >>= print
```

</details>

## 7. containers Seq replicateA/State: a laziness bug on master, fixed by c38f35da9b

containers-tests' `sequence-benchmarks/All.replicateA/State.N` rises by +2.75% to +4.19% (tip without f4e950c720 against master, both levels). The benchmark is `stateReplicate n = flip evalState 0 . S.replicateA n $ do old <- get; if old > 10 then put 0 else put (old + 1); return $ toEnum old`. At -O2, n=1000, 20000 calls: master 9,043,133,824 bytes and 21,197,928,370 instructions, tip 9,523,133,760 (+5.3%, 24 bytes an element) and 22,095,761,350 (+4.24%).

The difference is in the action itself: master runs chr's range check before building `(C# (chr# ww), I# ..)`; the tip builds `(C# (case leWord# .. of { __DEFAULT -> chr_error ww; 1# -> chr# ww }), I# ..)`, a thunk for the Char field. Master's eager check is wrong. With the action on its own (`act :: State Int Char`, the same do block) and `print (snd (runState act 2000000))`, which never demands `toEnum old`, master at -O1 and -O2 raises `Data.Char.chr: argument outside Unicode range: 0..1114111: 2000000`; the tip at -O1 and -O2, GHC 9.12.4 and GHC 9.14.1 print 0. The bug is fixed at c38f35da9b (e9551156d0 still raises the error). No GHC issue found for it. In master's pipeline the eager form appears in the first Simplifier run after worker/wrapper, where makeTrivial's let-binding of the unlifted argument becomes a case; that the tip's `bindingOk` refuses there is inferred, not traced. The code is that of section 2, so the rise has no reproducer of its own.

Reproducer **chr** (needs transformers, shipped with GHC): `ghc -O1 Main.hs -o chr && ./chr 2000000`.

<details><summary>chr: Act.hs and Main.hs</summary>

```haskell
-- containers-tests' stateReplicate action (benchmarks/Sequence.hs), as a
-- State action of its own.
module Act (act) where
import Control.Monad.Trans.State.Strict

act :: State Int Char
act = do
  old <- get
  if old > (10 :: Int) then put 0 else put (old + 1)
  return $ toEnum old
```

```haskell
-- Runs act from a state out of Char's range, demanding only the new state:
-- the source never evaluates toEnum old, so chr's range check must not fail.
module Main (main) where
import Control.Monad.Trans.State.Strict
import System.Environment
import Act (act)

main :: IO ()
main = do
  [s] <- getArgs
  print (snd (runState act (read s)))
```

</details>

## Not traced

- containers `set-operations-intmap/All.symmetricDifference-mix_nn` and `_swap` at -O1, +5.4% (tip against tip without f4e950c720), so f4e950c720's: symmetricDifference's Core is identical with and without f4e950c720 but for `$wsymDiffTip` hoisting `int2Word# ww` out of its loop without it, and a driver of it ran 6.3% faster with f4e950c720; not reproduced (the generated code was not compared).
- containers' graph bcc rows: f4e950c720's up to +0.6%, and the rest of the MR's at -O1 (bcc.rand,n=100000,m=1000000 +2.6%, bcc.line,n=1000000 +1.9%).

## The earlier reproducers and the tip's own tests

On the tip against master (R.hs, RB.hs, RX.hs at -O1 run as `200 +RTS -s`; S.hs at -O2):

```
                          master 83038fbee5   tip f4e950c720
R.hs bytes (-O1, R 200)   15,853,944          15,853,912
RB.hs bytes               2,246,895,448       15,853,912
RX.hs bytes               2,246,895,448       2,246,895,416
S.hs case k in $wstep     2                   1
S.hs instructions         1,315,140,023       1,235,138,543
T28163 / K.hs with 0      divide by zero      3
```

RB.hs is R.hs with z's two equations merged into one with nested cases; RX.hs is R.hs with z, T, work and expensive in a second module. So the tip fixes #28164's S.hs, fixes RB.hs (lost on master), and leaves the cross-module RX.hs lost, as on master.

The tip's own tests: T28164R fails when run as the testsuite runs it, with no argument (`[n] <- ...getArgs` fails: "Pattern match failure"), though with 200 it prints its .stdout; T28164S has no .stderr, so the testsuite compares its grep against empty and fails while the tip has the one `case k` the test wants. (Checked by running the tests' commands by hand on each compiler, not by the testsuite driver.) T28163 passes on the tip.

## Method

nofib at -O2, -O1, -O0 (`nofib-run --speed=Norm`, each program once, ASLR off); nofib's real/eff does not build on either compiler (GHC rejects its noncanonical `return`). containers (containers-tests' benchmarks), vector (vector-bench-papi, tasty-papi's TOT_INS) and megaparsec 9.8.1 (bench-speed) at -O2 and -O1, 5 runs each (megaparsec 10). containers and megaparsec: the geomean is of the medians' ratios over every benchmark; a benchmark whose runs agree within 0.05% under both compilers is compared by its minimum and moves if by more than 0.05%, any other moves only where the two compilers' run ranges do not overlap. vector: per benchmark the minimum TOT_INS of each compiler's runs, the geomean of their ratios. GHC's perf and size tests (`hadrian test --only-perf` and testsuite/tests/perf/size), one round.
