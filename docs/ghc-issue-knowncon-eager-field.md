# GHC issue: on HEAD, case-of-known-constructor evaluates a lazy field whose unlifted argument can fail, so a program that never forces the field can raise its exception

Filed as GHC [#28163](https://gitlab.haskell.org/ghc/ghc/-/work_items/28163) on 2026-11-21, as Simon Peyton Jones asked on GHC [!16600](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600) ([note 713218](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600#note_713218): "Could you open a ticket for this, please, with a repo case? Then I can add the repro case to the tests in !16600."); staged 2026-10-20. The text from "## Summary" down is the body as drafted for filing, in the tracker's bug template. Title: **HEAD regression: case-of-known-constructor evaluates a lazy field: `x = D# e` is ANF-ised and `e` floated out of the lazy binding**. `Repro.hs` below at -O1, run as `Repro 0` and `Repro 2`, on 2026-11-21: master 83038fbee5 and !16600's head 17df08ba52 (three commits, 3378d5aa47, 73a2f04a11 and 17df08ba52, on master 5308737363) as quick-flavour builds, master 37ad471050 as a perf-flavour build, and ghc-9.14.1, 9.12.4 and 9.10.3; on 2026-10-20 with quick-flavour builds of master 3d326d7d28 and of 15b311be10. The bisection, the dumps, the code reading and the `fromIntegral` variant date from 2026-10-20, on 3d326d7d28 and 9.14.1, and were not redone on 83038fbee5 or 17df08ba52; the body keeps them tied to those commits and does not say which commit of !16600 cures it. Found in orthotope's boxed `generate` on the strided view, which allocated less with GHC HEAD 10.1.20260918 (master e2d5702699 with !16600's first three commits and local patches) than with `merged-mrs` (master 3d326d7d28 with !16600 and other MRs): the former computes each element before the write, where `Data.Vector.generate` leaves it lazy. Tracker search 2026-11-21 for `simplAuxBind`, `prepareRhs`, `knownCon`, `FltCareful`, `case-of-known-constructor`, `ok-for-speculation`, `lazy field`, `divide by zero`, `evaluated eagerly`, `ANF` and `Improve typechecking of data constructors`: no report; GHC [#27910](https://gitlab.haskell.org/ghc/ghc/-/work_items/27910) (closed), about `simplAuxBind` rebuilding as a `case` a binding that is ok-for-speculation, is near and not the same.

## Summary

On master the Simplifier can evaluate a lazy constructor field before the field is demanded, so a program that never forces a failing field can raise its exception: `Repro.hs` below dies with `divide by zero` on master 83038fbee5 and 37ad471050. GHC 9.10.3, 9.12.4 and 9.14.1 print `3`, and so does !16600 at its head 17df08ba52.

In `case Just (D# e) of Just x -> ...`, case-of-known-constructor binds `x` with [`simplAuxBind`][simplauxbind], whose `prepareRhs` ANF-ises `x = D# e` into `a = e; x = D# a` (code as of master 3d326d7d28). `a` is unlifted and `e` is not ok-for-speculation, so the float is `FltCareful`; [`prepareBinding`][preparebinding] would keep such a float in a lazy binding's right-hand side ([`doFloatFromRhs`][dofloat]: `FltCareful -> ... && strict_bind`), but `simplAuxBind` returns `prepareRhs`'s floats unconditionally, and the careful float becomes a `case` around the binding. 9.14.1's `simplAuxBind` also returns `prepareRhs`'s floats unconditionally, but there the field is not a constructor application, so `prepareRhs` finds nothing to ANF-ise.

The change comes from b33284c7db ("Improve typechecking of data constructors"), the first bad commit of a bisection on `Repro.hs` below; its parent 15b311be10 prints `3`. It changes what the desugarer gives the Simplifier. `-ddump-ds -dsuppress-all -dsuppress-uniques` of `mk`, at 15b311be10 and with 9.14.1:

```
mk
  = \ a b ->
      Just
        (case int2Double# (unI (div $fIntegralInt a b)) of ds
         { __DEFAULT ->
         D# ds
         })
```

on master 3d326d7d28:

```
mk = \ a b -> Just (D# (int2Double# (unI (div $fIntegralInt a b))))
```

So the Simplifier code above is not new; since b33284c7db it is handed a constructor application in a lazy field whose unlifted argument is not ok-for-speculation.

## Steps to reproduce

`Repro.hs`:

```haskell
{-# LANGUAGE MagicHash #-}
module Main (main) where

import GHC.Exts
import System.Environment (getArgs)

{-# NOINLINE k #-}
k :: Double -> Double -> Int
k _ _ = 3

unI :: Int -> Int#
unI (I# x) = x

{-# INLINE [0] mk #-}
mk :: Int -> Int -> Maybe Double
mk a b = Just (D# (int2Double# (unI (a `div` b))))

{-# NOINLINE f #-}
f :: Int -> Int -> Int
f a b = case mk a b of
  Just x -> k x x
  Nothing -> 0

main :: IO ()
main = do
  [b] <- map read <$> getArgs
  print (f 1 b)
```

`ghc -O1 Repro.hs && ./Repro 0; ./Repro 2`. With ``fromIntegral (a `div` b) :: Double`` in place of the explicit `D#` the same happened on master 3d326d7d28 and not on 9.14.1, since base on that master gives `fromIntegral @Int @Double` the same `D# (...)` shape; that is how it was met, in `Data.Vector.generate` (vector 0.13.2.0), whose elements stay lazy on 9.14.1 and are computed before each write on master 3d326d7d28.

### Results

With 9.10.3, 9.12.4, 9.14.1 and !16600's head 17df08ba52, `./Repro 0` and `./Repro 2` both print `3`. With master 83038fbee5 and 37ad471050, `./Repro 2` prints `3` and `./Repro 0` dies:

```
Repro: Uncaught exception ghc-internal:GHC.Internal.Exception.Type.ArithException:

divide by zero
```

`-ddump-simpl-iterations -dsuppress-all -dsuppress-uniques`, first iteration of the phase-0 Simplifier, after `mk` inlines (both excerpts abridged at `...`). 9.14.1 keeps a lazy binding:

```
f = \ a b ->
      let {
        x = case b of { I# x ->
            join { $j x = D# (int2Double# x) } in
            case x of wild { ... quotInt# ... ; 0# -> case divZeroError of {} } } } in
      k x x
```

master 3d326d7d28 evaluates the division first:

```
f = \ a b ->
      case case b of { I# x ->
           case x of wild { ... int2Double# wild ...; 0# -> case divZeroError of {} } }
      of x
      { __DEFAULT ->
      let { x = D# x } in k x x
      }
```

The final Core on master 3d326d7d28 drops the division and keeps its checks:

```
$wf
  = \ ww ww1 ->
      case ww1 of {
        __DEFAULT -> case lvl of { BoxInt v1 -> v1 };
        -1# ->
          case ww of {
            __DEFAULT -> case lvl of { BoxInt v1 -> v1 };
            -9223372036854775808# -> case overflowError of {}
          };
        0# -> case divZeroError of {}
      }
```

## Expected behavior

`./Repro 0` prints `3`, as with 9.14.1: `k` never forces its arguments, so the division is never evaluated.

## Environment

* GHC version used: master 83038fbee5 (a quick-flavour build) and 37ad471050 (a perf-flavour build) show it; 9.14.1, 9.12.4, 9.10.3 and !16600's head 17df08ba52 (a quick-flavour build) do not.

Optional:

* Operating System: Linux
* System Architecture: x86_64

[simplauxbind]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Opt/Simplify/Iteration.hs#L392-437
[preparebinding]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Opt/Simplify/Iteration.hs#L717-757
[dofloat]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Opt/Simplify/Env.hs#L806-820

/label ~"T::bug"
/label ~"regression"
/label ~"needs triage"
