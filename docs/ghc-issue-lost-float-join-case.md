# GHC issue: at -O2 master takes `k` apart twice in `$wstep` of S.hs, in the exit join point and in the scope of the join points; floating that case above the join points, as !16600 does, fixes it, and holding the floating back in the Gentle phase keeps the full-laziness float of R.hs that note 705378 on !16600 reports lost

Filed as GHC [#28164](https://gitlab.haskell.org/ghc/ghc/-/work_items/28164) on 2026-11-21. The text from "## Summary" down is the body as drafted for filing, in the tracker's bug template; it is a defect report against master about `S.hs`, and names !16600 only by the link to note 705378, before `R.hs`'s code block; it names !16600's head 17df08ba52 once, in Environment, and no fork, branch or commit of the fix, and gives the fix in three short sentences. Title: **-O2: after liberate-case, a value is taken apart both in an exit join point and in the scope of the join points, where once suffices (6.48% more instructions)**. `S.hs` (-O2, Core and `perf stat -e instructions:u -r 5` on `S 10000000`) and `R.hs` (-O1, `R 200 +RTS -s`) on 2026-11-21: master 83038fbee5 and !16600's head 17df08ba52 as quick-flavour builds; master 37ad471050 as a perf-flavour build; the fix (17df08ba52 with the floating held back in the Gentle phase) as a stage-1 compiler of the 17df08ba52 tree run with `-B` over that tree's libraries, beside the tree's unpatched stage-1 compiler. The S.hs counts were taken by one agent and not re-run. The simplification of `z` the body describes, the pass-by-pass comparison of S.hs, k-nucleotide's Core and the nofib figures were taken on builds of the default GHC's tree (!16600 with other patches), which the body calls builds carrying the floating with other patches. `R.hs` is verbatim the reproducer of [note 705378](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600#note_705378) on !16600 (2026-10-20). Tracker search 2026-11-21 for `simplJoinPointBind`, `simplWrapFloats`, `rebuildSingleAltCase`, `FloatCase`, `Floating single-alternative cases`, `sm_case_case`, `liberate-case`, `full laziness`, `float-out`, `join point` and `16600`: no report; closest GHC [#28016](https://gitlab.haskell.org/ghc/ghc/-/work_items/28016) (a constant exposed by inlining after the first float-out is computed at every call) and [#27894](https://gitlab.haskell.org/ghc/ghc/-/work_items/27894) (float-out floats a would-be join point out of a specialisation), neither about !16600 or case-floats.

## Summary

At -O2, master's final Core of `$wstep` for `S.hs` below takes `k` apart twice, once in the exit join point and once in the scope of the join points, where once suffices. Liberate-case peels the first iteration of `hash`, which leaves a single-alternative `case k` at the head of the scope of the join points `$wgo` and `exit`. Master leaves it there, below the join points, and the body of `exit` takes `k` apart again (`-ddump-simpl -dsuppress-all -dsuppress-uniques`, abridged at `...`):

```
join { exit ww1 = case k of { I# y -> *# ww1 y } } in
joinrec { $wgo ww1 = ... jump exit ww1 ... } in
case k of { I# y ->
case y of wild { ...
```

Floating that case above the join points lets the `case k` in `exit` meet a known constructor:

```
case k of { I# y ->
join { exit ww1 = *# ww1 y } in
joinrec { $wgo ww1 = ... jump exit ww1 ... } in
case y of wild { ...
```

With master's shape, `S 10000000` runs 6.48% more instructions than with the floated one, 8 a call. At -O1, and at -O2 with `-fno-liberate-case`, the floating leaves `$wstep` as on master. The same pattern is in nofib's k-nucleotide at -O2 (`$slinks`, SpecConstr's specialisation in `checkGrow`); on builds carrying the floating with other patches, putting such cases back below the join points in every phase cost k-nucleotide 1.78% more instructions at -O2 and mate 0.78%.

A fix must not regress `R.hs` below, which [note 705378](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600#note_705378) reports: floating such cases above the join points loses a full-laziness float there, and it is the floating in the Gentle phase that loses it. The desugarer gives `z`:

```
z = \ sh ds ds1 ->
      join fail _ = ... expensive sh ds ... expensive sh ds1
      in case ds of T ss _ bx -> case ds1 of T _ _ bx' -> ...
```

In that phase the cases on `ds` and `ds1` in the desugared `z` move above its join point `fail`, and case-of-known-constructor rewrites the calls of `work` in `fail` onto their fields. Once `z` is inlined into `f` with the constant `c`, the call of `work` on the fields of `c` sits under `case c of T ...`, which full laziness does not float, `c` being an unevaluated CAF. So at -O1 `R 200` allocates 2,246,895,616 bytes with the floating in every phase, against 15,854,104 on master 83038fbee5.

A proposed potential fix: float the single-alternative case at the head of a join binding's scope above the join binding, as `S.hs` needs. Do not float it while case-of-case (`sm_case_case`) is off, in the Gentle phase before the first float-out. That keeps `R.hs`'s float.

## Steps to reproduce

`S.hs`:

```haskell
{-# LANGUAGE BangPatterns #-}
module Main (main) where

import System.Environment (getArgs)

-- step is lazy in k (the x < 0 branch), so its worker takes k boxed.
-- At -O2 liberate-case peels hash's first iteration, which puts a
-- `case k of I# y` in the body of go's join points; go's exit also takes
-- k apart.
{-# NOINLINE step #-}
step :: Int -> Int -> Int
step k x
  | x < 0 = 0
  | otherwise = go (hash 0 0)
  where
    hash !i !acc | i == k = acc
                 | otherwise = hash (i + 1) (acc * 131 + x + i)
    go !j | j < 1000 = j * k
          | otherwise = go (j `quot` 7)

main :: IO ()
main = do
  [n] <- map read <$> getArgs
  let k = n `rem` 2 + 2
  print (sum [ step k x | x <- [1 .. n] ])
```

`ghc -O2 -rtsopts -ddump-simpl -dsuppress-all -dsuppress-uniques S.hs && perf stat -e instructions:u -r 5 ./S 10000000`

`R.hs`:

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

`ghc -O1 -rtsopts R.hs && ./R 200 +RTS -s`

### Results

`S 10000000` prints `8518716244` and `R 200` prints `13142050000` on every compiler below.

| compiler | `S.hs`: `case k` in `$wstep` | `S.hs`: instructions | `R.hs`: bytes allocated |
|---|---|---|---|
| master 37ad471050 | twice | 1,315,157,535 | 15,853,944 |
| master 83038fbee5 | twice | 1,315,163,207 | 15,854,104 |
| floating in every phase | once | 1,235,160,175 | 2,246,895,616 |
| floating held back in the Gentle phase | once | 1,235,160,229 | 15,854,112 |

Neither form of the floating changes the allocation of `S.hs`.

## Expected behavior

`$wstep` takes `k` apart once, in a single `case k` above the join points, and `R.hs` allocates as on master.

## Environment

* GHC version used: master 37ad471050, master 83038fbee5 and a change that floats the single-alternative cases of a join binding's scope above the join binding (commit 17df08ba52), measured as it is and with the floating held back in the Gentle phase.

Optional:

* Operating System: Linux
* System Architecture: x86_64

/label ~"T::bug"
/label ~"runtime perf"
/label ~"needs triage"
