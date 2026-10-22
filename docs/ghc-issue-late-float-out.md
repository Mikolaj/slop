# GHC issue: a constant exposed by inlining after the first float-out is not floated, because the simplifier first moves the caller's continuation into it

Staged and filed 2026-10-22 as [GHC work item 28016](https://gitlab.haskell.org/ghc/ghc/-/work_items/28016); this file stays as the filed record, the text from "## Summary" down being the filed body, in the tracker's bug template. Title: **A constant exposed by inlining after the first float-out is computed at every call: case-of-case and the `runRW#` rule move the caller's continuation into it before the second float-out**. Every command in it was run as printed on 2026-10-22 with GHC HEAD 10.1.20261019 (`merged-mrs`: master 3d326d7d28 with MRs and fixes); `Repro.hs` gives the same Core shapes with 9.6.7, 9.8.4, 9.10.3, 9.12.4 and 9.14.1. Found in orthotope's specialisation benchmark, twice: the boxed vector instance's empty vector, `VG.empty` inlined into callers and built at every call, 24 bytes a call for each array at the empty size; and a test for no padding, `all (== (0, 0))` over a constant list in an INLINE function, run at every call of `pad`. The tracker search of 2026-10-22 ("runRW# float", "runRW# full laziness", "runRW# floated", "full laziness case-of-case", "float out join point", "full laziness join point", "case-of-case full laziness", "constant not floated", "floated to top level join", "empty vector allocated") found no report; GHC [#13236](https://gitlab.haskell.org/ghc/ghc/-/work_items/13236), [#25906](https://gitlab.haskell.org/ghc/ghc/-/work_items/25906), [#15560](https://gitlab.haskell.org/ghc/ghc/-/work_items/15560) and [#13104](https://gitlab.haskell.org/ghc/ghc/-/work_items/13104) are about other interactions of floating with join points and `runRW#`; GHC [#27962](https://gitlab.haskell.org/ghc/ghc/-/work_items/27962) is a Core Lint failure from a cast that the same `runRW#` rule drops, and its fix, GHC [!16829](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16829) (open), still pushes the continuation into `runRW#` in both of the rule's cases (read in its diff on 2026-10-22, not built). Code read at master 3d326d7d28.

## Summary

The first float-out runs after the gentle Simplifier and the specialiser, before any other Simplifier run ([`GHC.Core.Opt.Pipeline`][pipeline]). A computation of constants that appears later, when a function is inlined after the first float-out, can meet case-of-case or the `runRW#` rule (Note [Simplification of runRW#], [GHC.CoreToStg.Prep][runrw]) in the Simplifier runs before the second float-out, and they move the caller's strict continuation into it. When the second float-out runs, no closed expression is left to float, and the computation runs at every call.

Note [Inlining in gentle mode] ([GHC.Core.Opt.Simplify.Utils][gentle]) describes this hazard for the first float-out: "Before full laziness we must be careful not to inline wrappers, because doing so inhibits floating [...] and now the redex (f x) isn't floatable any more."

## Steps to reproduce

`Repro.hs` has two examples, each with a control that is the same code seen by the first float-out:

```haskell
{-# LANGUAGE MagicHash, UnboxedTuples #-}
module Repro (R (..), f, f0, pad, pad0) where

import GHC.Exts
import GHC.ST (ST (..), runST)

data Arr = Arr (Array# Int)
data R = R !Int !Arr

new :: State# s -> (# State# s, Arr #)
new s = case newArray# 0# 0 s of
  (# s1, ma #) -> case unsafeFreezeArray# ma s1 of
    (# s2, a #) -> (# s2, Arr a #)
{-# INLINE new #-}

-- An empty array inlined in phase 1, as vector's INLINE_FUSED functions are.
emptyArr :: Arr
emptyArr = runST (ST new)
{-# INLINE [1] emptyArr #-}

-- The same, inlined before the first float-out.
emptyArr0 :: Arr
emptyArr0 = runST (ST new)
{-# INLINE emptyArr0 #-}

f, f0 :: Int -> R
f n = R n emptyArr
f0 n = R n emptyArr0

padT :: [Int] -> [Int] -> [Int]
padT ps xs = if all (== 0) ps then xs else zipWith (+) ps xs
{-# INLINE padT #-}

zeros :: [Int]
zeros = [0, 0, 0]
{-# NOINLINE zeros #-}

-- The same test, in pad0's own body.
pad, pad0 :: [Int] -> [Int]
pad xs = padT zeros xs
pad0 xs = if all (== 0) zeros then xs else zipWith (+) zeros xs
```

`ghc -O -ddump-simpl -dsuppress-all -dsuppress-uniques -ddump-to-file -c Repro.hs`, in `Repro.dump-simpl` (excerpt): `f0` uses the array `f1`, built once, and `f` builds an array at every call, the construction of its result inside `runRW#`:

```
f1
  = runRW#
      (\ s ->
         case newArray# 0# f2 s of { (# ipv, ipv1 #) ->
         case unsafeFreezeArray# ipv1 ipv of { (# _, ipv3 #) -> Arr ipv3 }
         })

f = \ n ->
      runRW#
        (\ s ->
           case newArray# 0# f2 s of { (# ipv, ipv1 #) ->
           case unsafeFreezeArray# ipv1 ipv of { (# _, ipv3 #) ->
           case n of { I# unbx -> R unbx ipv3 }
           }
           })

f0 = \ n -> $WR n f1
```

`pad0` tests the constant `pad3`, computed once; `pad` runs the test at every call, as a loop whose exits jump to the branches of the `if`:

```
pad3 = pad0_go1 zeros

pad
  = \ xs ->
      join { $j = pad_go zeros xs } in
      joinrec {
        go1 ds
          = case ds of {
              [] -> xs;
              : y ys ->
                case y `cast` <Co:1> of {
                  False -> jump $j;
                  True -> jump go1 ys
                }
            }; } in
      jump go1 pad1

pad0
  = \ xs ->
      case pad3 `cast` <Co:1> of {
        False -> pad_go zeros xs;
        True -> xs
      }
```

With `-dverbose-core2core`, the Core that the first float-out receives has `f = \ n -> $WR n emptyArr` and `pad = \ xs -> padT zeros xs`. The second Simplifier run after it inlines `emptyArr` and `padT`, and `f` becomes `\ n -> runRW# (\ s -> ... $WR n (Arr ipv))`; in that run and the next ones, all before the second float-out, `padT`'s `all` is fused into a loop, and case-of-case gives the loop the `if`'s branches.

The cost, with `Main.hs`:

```haskell
{-# LANGUAGE BangPatterns #-}
import System.Environment (getArgs)
import Repro (R (..), f, f0, pad, pad0)

goF :: (Int -> R) -> Int -> Int -> Int
goF g = go
  where go 0 !acc = acc
        go k !acc = case g k of R m _ -> go (k - 1) (acc + m)
{-# NOINLINE goF #-}

goP :: ([Int] -> [Int]) -> Int -> Int -> Int
goP p = go
  where go 0 !acc = acc
        go k !acc = case p [k, k, k] of
          x : _ -> go (k - 1) (acc + x)
          [] -> go (k - 1) acc
{-# NOINLINE goP #-}

main :: IO ()
main = do
  [w, n] <- getArgs
  let k = read n
  print $ case w of
    "f" -> goF f k 0
    "f0" -> goF f0 k 0
    "pad" -> goP pad k 0
    _ -> goP pad0 k 0
```

`ghc -O -rtsopts Main.hs -o main`; `./main W N +RTS -s` for the bytes allocated and `perf stat -e instructions:u ./main W N` for the instructions, at N = 1000000 and 2000000, the difference divided by 1000000:

```
        bytes a call   instructions a call
f           64.0             60.3
f0          40.0             68.8
pad         88.0            162.0
pad0        88.0             93.0
```

`f` allocates the 24 bytes of the empty array at every call, though it runs fewer instructions than `f0`; `pad` runs 69 instructions a call more than `pad0`.

## Expected behavior

`f` and `pad` compute the array and the test once, as `f0` and `pad0` do.

## Environment

- GHC 9.6.7, 9.8.4, 9.10.3, 9.12.4, 9.14.1 and a HEAD build (master 3d326d7d28 with some MRs), at `-O`.
- x86-64 Linux.

[pipeline]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Opt/Pipeline.hs#L203-216
[runrw]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/CoreToStg/Prep.hs#L1379-1395
[gentle]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Opt/Simplify/Utils.hs#L1322-1351

/label ~"T::bug"

/label ~"needs triage"
