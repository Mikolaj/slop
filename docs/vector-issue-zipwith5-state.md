# vector issue: `zipWith5` and `zipWith6` keep their stream state boxed, so they allocate for each element

Filed 2026-10-24 as [vector issue 579][579]; this file stays as the filed record, the text from "## Summary" down being the body as last drafted here, in the tracker's bug template. Title: **`zipWith5` and `zipWith6` allocate for each element with `-O2`, where `zipWith4` allocates only the result vector**. The prose is ASD-STE100 Simplified Technical English. The reproducer is a cabal script and needs only `vector`. The problem was found while auditing the `Vector` methods of orthotope's `pr-mikolaj-toVectorListT` branch, whose boxed and Unboxed zips write their result over the indices with one counter; the boxed instance's comment names this problem. A search on 2026-10-24 of the vector issues and pull requests, open and closed, for `zipWith5`, `zipWith4`, `zipWith3`, `zip3`, `zipWith`, `zip`, `SpecConstr`, `spec-constr`, `stream state`, `boxed state` and `allocates` found nothing about this: [#446][446] is about `foldl'` over large tuples, which `-fmax-worker-args` settled, and [#244][244] is about `zipWith` with `-O1`, which `-O2` settled. The figures below are from GHC 9.12.4, run on 2026-10-24; GHC 9.14.1 prints the same bytes, runs within 3% of the table's instructions and gives Core of the same shape, and a GHC HEAD 10.1.20261019 with patches not yet merged prints the same bytes.

## Summary

`zipWith5` and `zipWith6` allocate memory for each element, also with `-O2`. `zipWith4` and a loop over the indices allocate only the result vector.

The table gives the bytes allocated and the instructions executed for each element, for `zipWith5 (\ x y z u w -> x + y + z + u + w)` on five vectors of `n = 200000` `Double`s, on GHC 9.12.4 with `-O2`. "Index loop" is a loop over the indices that reads each vector with `unsafeIndexM` and writes each result into a new mutable vector. The values with `-O1 -fspec-constr` are the same.

| | boxed | Unboxed |
|---|---|---|
| `zipWith5`, bytes | 472 | 496 |
| index loop, bytes | 64 | 8 |
| `zipWith5`, instructions | 1619 | 449 |
| index loop, instructions | 149 | 33 |

`zipWith6` allocates 632 bytes for each element of a boxed vector and 664 of an Unboxed vector, where the index loop allocates 72 and 8. At `n = 200000`, `zipWith4` allocates the same bytes as the index loop, and executes 1.28 times its instructions at boxed and 1.75 times at Unboxed. For a short vector the difference is the same: at `n = 9`, Unboxed `zipWith5` allocates 485 bytes for each element and the index loop 15.

The generic `zipWith5` ([lines 1215 to 1225][gzipwith5]) is `unstream` of `Bundle.zipWith5`. `Bundle.zipWith5M` ([lines 364 to 369][bzipwith5m]) and `zipWith5M` in vector-stream ([lines 556 to 576][szipwith5m], with `zipWith4M` and `zipWith6M`) are `zipWithM` of `zip3` and `zip`:

```haskell
zipWith5M f sa sb sc sd se
  = zipWithM (\(a,b,c) (d,e) -> f a b c d e) (zip3 sa sb sc) (zip sd se)
```

`zipWithM` ([lines 502 to 522][szipwithm]) and `zipWith3M` ([lines 528 to 554][szipwith3m]) keep each element that they read in a `Just` in their state, until they read the elements of the other streams. With `-O2`, GHC's SpecConstr makes four specialised copies of the loop of `zipWith5`. In the Core, a specialised copy jumps to the loop that is not specialised, and gives it the state as boxed `Int`s in tuples and the elements in `Just`. The loop of `zipWith4`, which is `zipWithM` of two `zip`s, stays in its four specialised copies and allocates nothing.

## Steps to reproduce

1. Save the program below as `Repro.hs`.

2. Run it. To select a compiler, add `-w ghc-VERSION`.

```
cabal run -v0 Repro.hs
```

3. On GHC 9.12.4, the output is:

```
n =      9  boxed zipWith4             72.9 bytes an element
n =      9  boxed index loop, 4        64.9 bytes an element
n =      9  boxed zipWith5            463.1 bytes an element
n =      9  boxed index loop, 5        72.9 bytes an element
n =      9  boxed zipWith6            624.9 bytes an element
n =      9  boxed index loop, 6        80.9 bytes an element
n =      9  Unboxed zipWith4           15.1 bytes an element
n =      9  Unboxed index loop, 4      15.1 bytes an element
n =      9  Unboxed zipWith5          485.3 bytes an element
n =      9  Unboxed index loop, 5      15.1 bytes an element
n =      9  Unboxed zipWith6          655.1 bytes an element
n =      9  Unboxed index loop, 6      15.1 bytes an element
n = 200000  boxed zipWith4             56.0 bytes an element
n = 200000  boxed index loop, 4        56.0 bytes an element
n = 200000  boxed zipWith5            472.0 bytes an element
n = 200000  boxed index loop, 5        64.0 bytes an element
n = 200000  boxed zipWith6            632.0 bytes an element
n = 200000  boxed index loop, 6        72.0 bytes an element
n = 200000  Unboxed zipWith4            8.0 bytes an element
n = 200000  Unboxed index loop, 4       8.0 bytes an element
n = 200000  Unboxed zipWith5          496.0 bytes an element
n = 200000  Unboxed index loop, 5       8.0 bytes an element
n = 200000  Unboxed zipWith6          664.0 bytes an element
n = 200000  Unboxed index loop, 6       8.0 bytes an element
```

```haskell
{- cabal:
build-depends: base, vector ==0.13.2.0
ghc-options: -O2
-}
{-# LANGUAGE BangPatterns, RankNTypes #-}
-- Reproducer: zipWith5 and zipWith6 allocate for each element, where
-- zipWith4 and a loop over the indices allocate only the result vector.
--
-- Run: cabal run -v0 Repro.hs
module Main (main) where

import Control.Exception (evaluate)
import Control.Monad (forM_)
import Control.Monad.ST (ST)
import qualified Data.Vector as VB
import qualified Data.Vector.Generic as VG
import qualified Data.Vector.Generic.Mutable as VGM
import qualified Data.Vector.Unboxed as VU
import System.Mem (getAllocationCounter)
import Text.Printf (printf)

-- A vector of n elements, the ith what g i returns.
{-# INLINE indexLoop #-}
indexLoop :: VG.Vector v a => Int -> (forall s. Int -> ST s a) -> v a
indexLoop !n g = VG.create $ do
  mv <- VGM.unsafeNew n
  let go !i | i >= n = return mv
            | otherwise = do
                x <- g i
                VGM.unsafeWrite mv i x
                go (i + 1)
  go 0

type V v = v Double

{-# NOINLINE zip4B #-}
{-# NOINLINE loop4B #-}
zip4B, loop4B :: V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector
zip4B a b c d = VB.zipWith4 (\ x y z u -> x + y + z + u) a b c d
loop4B a b c d = indexLoop (VB.length a) $ \ i -> do
  x <- VB.unsafeIndexM a i; y <- VB.unsafeIndexM b i
  z <- VB.unsafeIndexM c i; u <- VB.unsafeIndexM d i
  return (x + y + z + u)
{-# NOINLINE zip5B #-}
{-# NOINLINE loop5B #-}
zip5B, loop5B :: V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector
zip5B a b c d e = VB.zipWith5 (\ x y z u w -> x + y + z + u + w) a b c d e
loop5B a b c d e = indexLoop (VB.length a) $ \ i -> do
  x <- VB.unsafeIndexM a i; y <- VB.unsafeIndexM b i
  z <- VB.unsafeIndexM c i; u <- VB.unsafeIndexM d i
  w <- VB.unsafeIndexM e i
  return (x + y + z + u + w)
{-# NOINLINE zip6B #-}
{-# NOINLINE loop6B #-}
zip6B, loop6B :: V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector -> V VB.Vector
zip6B a b c d e f = VB.zipWith6 (\ x y z u w t -> x + y + z + u + w + t) a b c d e f
loop6B a b c d e f = indexLoop (VB.length a) $ \ i -> do
  x <- VB.unsafeIndexM a i; y <- VB.unsafeIndexM b i
  z <- VB.unsafeIndexM c i; u <- VB.unsafeIndexM d i
  w <- VB.unsafeIndexM e i; t <- VB.unsafeIndexM f i
  return (x + y + z + u + w + t)
{-# NOINLINE zip4U #-}
{-# NOINLINE loop4U #-}
zip4U, loop4U :: V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector
zip4U a b c d = VU.zipWith4 (\ x y z u -> x + y + z + u) a b c d
loop4U a b c d = indexLoop (VU.length a) $ \ i -> do
  x <- VG.unsafeIndexM a i; y <- VG.unsafeIndexM b i
  z <- VG.unsafeIndexM c i; u <- VG.unsafeIndexM d i
  return (x + y + z + u)
{-# NOINLINE zip5U #-}
{-# NOINLINE loop5U #-}
zip5U, loop5U :: V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector
zip5U a b c d e = VU.zipWith5 (\ x y z u w -> x + y + z + u + w) a b c d e
loop5U a b c d e = indexLoop (VU.length a) $ \ i -> do
  x <- VG.unsafeIndexM a i; y <- VG.unsafeIndexM b i
  z <- VG.unsafeIndexM c i; u <- VG.unsafeIndexM d i
  w <- VG.unsafeIndexM e i
  return (x + y + z + u + w)
{-# NOINLINE zip6U #-}
{-# NOINLINE loop6U #-}
zip6U, loop6U :: V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector -> V VU.Vector
zip6U a b c d e f = VU.zipWith6 (\ x y z u w t -> x + y + z + u + w + t) a b c d e f
loop6U a b c d e f = indexLoop (VU.length a) $ \ i -> do
  x <- VG.unsafeIndexM a i; y <- VG.unsafeIndexM b i
  z <- VG.unsafeIndexM c i; u <- VG.unsafeIndexM d i
  w <- VG.unsafeIndexM e i; t <- VG.unsafeIndexM f i
  return (x + y + z + u + w + t)

-- Bytes allocated for each element, the mean of reps calls, each result
-- evaluated and its last element read.
measure :: Int -> Int -> (Int -> IO ()) -> IO Double
measure n reps run = do
  run 0
  a0 <- getAllocationCounter
  forM_ [1 .. reps] run
  a1 <- getAllocationCounter
  return (fromIntegral (a0 - a1) / fromIntegral reps / fromIntegral n)

main :: IO ()
main = forM_ [9, 200000] $ \ n -> do
  let reps = max 10 (20000000 `div` n)
      bs = [VB.generate n (\ j -> fromIntegral (j + k)) | k <- [1 .. 6 :: Int]]
      us = [VU.generate n (\ j -> fromIntegral (j + k)) | k <- [1 .. 6 :: Int]]
      run4B g _ = case bs of [a, b', c, d, _, _] -> evaluate (g a b' c d) >>= evaluate . VB.last >> return (); _ -> return ()
      run5B g _ = case bs of [a, b', c, d, e, _] -> evaluate (g a b' c d e) >>= evaluate . VB.last >> return (); _ -> return ()
      run6B g _ = case bs of [a, b', c, d, e, f] -> evaluate (g a b' c d e f) >>= evaluate . VB.last >> return (); _ -> return ()
      run4U g _ = case us of [a, b', c, d, _, _] -> evaluate (g a b' c d) >>= evaluate . VU.last >> return (); _ -> return ()
      run5U g _ = case us of [a, b', c, d, e, _] -> evaluate (g a b' c d e) >>= evaluate . VU.last >> return (); _ -> return ()
      run6U g _ = case us of [a, b', c, d, e, f] -> evaluate (g a b' c d e f) >>= evaluate . VU.last >> return (); _ -> return ()
      cases = [ ("boxed zipWith4", run4B zip4B), ("boxed index loop, 4", run4B loop4B)
              , ("boxed zipWith5", run5B zip5B), ("boxed index loop, 5", run5B loop5B)
              , ("boxed zipWith6", run6B zip6B), ("boxed index loop, 6", run6B loop6B)
              , ("Unboxed zipWith4", run4U zip4U), ("Unboxed index loop, 4", run4U loop4U)
              , ("Unboxed zipWith5", run5U zip5U), ("Unboxed index loop, 5", run5U loop5U)
              , ("Unboxed zipWith6", run6U zip6U), ("Unboxed index loop, 6", run6U loop6U) ]
  forM_ cases $ \ (name, run) -> do
    bytes <- measure n reps run
    printf "n = %6d  %-22s %8.1f bytes an element\n" n name bytes
```

## Expected behavior

`zipWith5` and `zipWith6` allocate only the result vector, as `zipWith4` does.

## Environment

* vector-0.13.2.0 and vector-stream-0.1.0.1, from Hackage. On master at [d0f42e0562][master], the generic `zipWith5`, `Bundle.zipWith5M` and vector-stream's `zipWithM`, `zipWith3M`, `zipWith4M`, `zipWith5M` and `zipWith6M` have the same code.
* GHC 9.12.4 and 9.14.1; cabal-install 3.18.2.0.
* Linux (kernel 7.0.0-38-generic), x86_64 (AMD Ryzen 7 5800X).

[446]: https://github.com/haskell/vector/issues/446
[244]: https://github.com/haskell/vector/issues/244
[gzipwith5]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector/src/Data/Vector/Generic.hs#L1215-L1225
[bzipwith5m]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector/src/Data/Vector/Fusion/Bundle/Monadic.hs#L364-L369
[szipwith5m]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector-stream/src/Data/Stream/Monadic.hs#L556-L576
[szipwithm]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector-stream/src/Data/Stream/Monadic.hs#L502-L522
[szipwith3m]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector-stream/src/Data/Stream/Monadic.hs#L528-L554
[master]: https://github.com/haskell/vector/tree/d0f42e056202fa24b479833dbc21222c1964d096
[579]: https://github.com/haskell/vector/issues/579
