# GHC issue: an instance method defined as another function is not specialised, its unfolding a cast with no binders, so a specialisation calls that function's worker with a dictionary

Staged and filed 2026-11-07 as [GHC work item 28099](https://gitlab.haskell.org/ghc/ghc/-/work_items/28099); this file stays as the filed record, the text from "## Summary" down being the filed body, in the tracker's bug template. Title: **Specialise: an instance method defined as another function, its unfolding a cast with no binders, is not specialised, so a specialisation calls that function's worker with a dictionary**. Every command in it was run as printed on 2026-11-07 with GHC 9.14.1 and a stage-1 build of master at 37ad471050.

## Summary

An instance method defined as another function, `vfill = fillL`, is compiled to a cast of that function with no binders: the dictionary is `$fVecL = C:Vec (fillL |> co)`. A caller specialised at the instance then calls the function's worker unspecialised, with a dictionary, here `$wfillL $fNumInt` in the loop of `Repro.g`, though `fillL` is `INLINABLE`. [`specHeader`][spechdr] in `GHC.Core.Opt.Specialise` stops where a binding has no binders ("If we run out of binders, stop immediately"), so nothing specialises the method at `Num Int`, and the simplifier exposes the call of `fillL` at `Int` only after the specialiser has run.

Writing the method with its arguments, `vfill n v = fillL n v`, changes nothing: GHC eta-reduces the unfolding back to the cast. Banging them, `vfill !n !v = fillL n v`, keeps the binders, and then `Repro` gets `$s$wfillL` and the rule `"SPEC/Repro $wfillL @Int"`, its loop calling `$s$wfillL`.

## Steps to reproduce

`ReproLib.hs`:

```haskell
{-# LANGUAGE TypeFamilies #-}
module ReproLib (Vec (..), L (..), fillL, useFill) where

import Data.Kind (Constraint, Type)

class Vec v where
  type Elem v :: Type -> Constraint
  vfill :: Elem v a => Int -> v a -> v a

newtype L a = L [a]

instance Vec L where
  type Elem L = Num
  {-# INLINE vfill #-}
  vfill = fillL

fillL :: Num a => Int -> L a -> L a
fillL 0 v = v
fillL n (L xs) = fillL (n - 1) (L (map (+ 1) xs))
{-# INLINABLE fillL #-}

useFill :: (Vec v, Elem v a) => Int -> v a -> v a
useFill 0 v = v
useFill n v = useFill (n - 1) (vfill n v)
{-# INLINABLE useFill #-}
```

`Repro.hs`:

```haskell
module Repro (g) where

import ReproLib

g :: Int -> L Int -> L Int
g = useFill
```

Compile with `ghc -O -fforce-recomp -ddump-simpl -dsuppress-all -dsuppress-uniques -ddump-to-file Repro.hs`. `Repro.dump-simpl` shows the loop:

```
        __DEFAULT -> $wg (-# ds2 1#) ($wfillL $fNumInt ds2 v1);
```

## Expected behavior

The specialisation of `useFill` at `L Int` calls a specialisation of `fillL` at `Int`, as it does when the method binds its arguments with bangs:

```
          $wg (-# ds2 1#) ($s$wfillL ds2 (nt `cast` <Co:3> :: ...))
```

## Environment

* GHC version used: 9.14.1, and master at 37ad471050 (10.1.20261103), whose loop makes the same call. GHC 9.6.7 to 9.12.4 differ: the specialisation of `useFill` keeps the method's constraint dictionary as a parameter, and the banged method does not change that.

Optional:
* Operating System: Linux
* System Architecture: x86-64

[spechdr]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Core/Opt/Specialise.hs#L2563-2565

/label ~"T::bug"
/label ~"specialisation"
/label ~"runtime perf"
/label ~"llm-derived::reproducer"
/label ~"needs triage"
