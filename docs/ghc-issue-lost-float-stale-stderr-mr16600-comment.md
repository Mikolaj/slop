# GHC merge request comment: two changes in !16600's later commits, work on a constant argument no longer floated out from 44d0fa5d35 and a stale `T26903.stderr` at e8ec242c51

Staged and posted 2026-10-20 as [a comment](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600#note_705378) on GHC [!16600](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600), "Don't push `case` inside `let` in Gentle simplification" (open, by simonpj, head e8ec242c51, whose pipeline 132479 failed); this file stays as the record of the comment, the text from "Two changes in the MR's later commits" down being the body as drafted. Verified on 2026-10-20 with quick-flavour builds of the MR's commits 9d8ef33f65, e0aef7c664, 44d0fa5d35, d10a0fc8b9 and e8ec242c51 and of master 3d326d7d28, from the file as shown here; the T26903 failure is also in job 2677343 of pipeline 132479. Found in orthotope's (0619101e) Shaped `zipWith3A.singleR` with two `constant` arguments, which allocated more with `merged-mrs` than with GHC HEAD 10.1.20260918 (master e2d5702699 with the MR's first three commits and local patches), and in T26903 run by hand on `merged-mrs`. Read on 2026-10-20: all the MR's notes; the one of 2026-10-19 by Mikolaj calls T26903 "possibly benign", and none mentions the lost float.

Two changes in the MR's later commits, measured on quick-flavour builds of single commits of the MR (x86_64 Linux).

**Work on a constant argument is no longer floated out.** `Repro.hs`:

```haskell
module Main (main) where

import System.Environment (getArgs)

data T = T ![Int] !Int !Int

{-# NOINLINE work #-}
work :: [Int] -> [Int] -> Int -> Int -> [Int]
work sh ss o v = [ x * o + v + y | x <- sh, y <- ss ]

{-# INLINE expensive #-}
expensive :: [Int] -> T -> [Int]
expensive sh (T ss o v) = work sh ss o v

{-# INLINE z #-}
z :: [Int] -> T -> T -> Int
z sh (T ss _ v) (T _ _ v')
  | v == 1, v' == 1 = sum ss
z sh t t' = sum (expensive sh t) + sum (expensive sh t')

{-# NOINLINE mkT #-}
mkT :: Int -> T
mkT n = T [1 .. n] 3 5

c :: T
c = mkT 1000

{-# NOINLINE f #-}
f :: T -> Int
f a = z [1 .. 100] a c

main :: IO ()
main = do
  [n] <- map read <$> getArgs
  print (sum [ f (T [k] 0 2) | k <- [1 .. n] ])
```

`ghc -O1 -rtsopts Repro.hs && ./Repro 200 +RTS -s` allocates 15,854,112 bytes at e0aef7c664 (master 3d326d7d28: 15,854,104) and 2,246,895,616 at 44d0fa5d35 and at the tip. At e0aef7c664 `sum (expensive sh c)` is a top-level binding (`-dsuppress-all -dsuppress-uniques`):

```
lvl
  = case c of { T ss bx bx1 ->
    $wgo1 (work sh ss (I# bx) (I# bx1)) 0#
    }
```

At 44d0fa5d35 and at the tip `$wf` takes `c` apart and calls `work` on its fields in the join point `fail`, on every call:

```
$wf
  = \ ww ww1 ww2 ->
      case ww of ww3 { __DEFAULT ->
      case c of { T ds bx bx1 ->
      join {
        fail ds1
          = ...
                  jump $wgo2 (work sh ds (I# bx) (I# bx1)) 0# } in
            ...
```

The difference is already in `z`'s INLINE unfolding (`--show-iface`, with `T`, `work`, `expensive` and `z` in a module of their own): at e0aef7c664 `fail` is bound first and takes each argument apart itself; at 44d0fa5d35 the unfolding takes both arguments apart first and `fail`, below the two `case`s, calls `work` on their fields. Met in orthotope's `zipWith3A` on shaped arrays with two constant arguments: 1,600,326 bytes a call at 9d8ef33f65, 4,800,358 at e8ec242c51.

**`T26903.stderr` is stale.** 883a949d3c changed it to 24 coercions and `$fCInt = C:C $fCInt1`, which d10a0fc8b9, the last compiler change before e8ec242c51, prints. e8ec242c51 prints the earlier shape again (48 coercions, `$dmop` and `$fCInt_$cop` cast as a whole, ``$fCInt = C:C ($fCInt1 `cast` <Co:11>)``), as its message says ("A cast suffix stays outside, so it is not duplicated into every alternative of a multi-way case"): the `stderr mismatch` pipeline 132479 reports for T26903. `op` is still inlined into `test`, so if the 48 is intended, the failure is benign, as the note of 2026-10-19 guessed, and only the expected output needs updating.
