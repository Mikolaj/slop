# vector issue: `fromListN` takes its list apart by `case`, so a list producer cannot fuse with it

Filed 2026-10-24 as [vector issue 578][578]; this file stays as the filed record, the text from "## Summary" down being the body as last drafted here, in the tracker's bug template. Title: **`fromListN` does not fuse with a list producer, so `fromListN n (iterate f x)` builds each cons cell and boxed element of the list**. The prose is ASD-STE100 Simplified Technical English. The reproducer is a cabal script and needs only `vector`. The problem was found while auditing the `Vector` methods of orthotope's `pr-mikolaj-toVectorListT` branch, whose `iterateN` gives `fromListN` a list from `build`; orthotope writes its `vFromListN` as one `foldr` into a new vector, with a comment that names this problem. A search on 2026-10-24 of the vector issues and pull requests, open and closed, for `fromListN`, `fromList`, `list fusion`, `foldr/build`, `foldr`, `build`, `good consumer`, `iterate`, `unfoldrN`, `enumFromTo fusion` and `Bundle.fromList` found nothing about this: [#439][439] is about the spare capacity of `fromList`, [#388][388] about allocation strategies, [#565][565] about the documentation of `fromListN`, [#301][301] about the memory that a large size hint allocates, and [#229][229] about a test suite for fusion. The figures below are from GHC 9.12.4, run on 2026-10-24 on a machine busy with other work; GHC 9.14.1 prints the same bytes and runs within 3% of the table's instructions, and the rules' figures are the same on it.

## Summary

`fromListN n xs` reads `xs` through a stream whose step function takes the list apart by `case`. GHC's `foldr/build` rule fuses a list producer only with a consumer that is a `foldr`. Thus, when `xs` comes from a producer such as `iterate`, `map`, `take`, an enumeration or a list comprehension, the program builds each cons cell and each boxed element of the list, and then it copies the elements into the vector. A `fromListN` that consumes its list with `foldr` fuses with the producer, and the program does not build the list.

The table gives the bytes allocated and the instructions executed for each element, for `fromListN n (take n (iterate (+ 1) x))` with `x :: Double` and `n = 200000`, on GHC 9.12.4 with `-O2`. "`foldr` writer" is the function in "Proposed fix". With `-O1` and with `-O1 -fspec-constr`, the bytes are the same, and the instructions are the same or 1 more. A build of GHC HEAD 10.1.20261019 with patches not yet merged allocates less with `-O2`: `fromListN` 80 bytes for each element at the three kinds, and the `foldr` writer 8, 8 and 24.

| | Unboxed | Storable | boxed |
|---|---|---|---|
| `fromListN`, bytes | 104 | 104 | 129 |
| `foldr` writer, bytes | 8 | 8 | 73 |
| `fromListN`, instructions | 133 | 137 | 250 |
| `foldr` writer, instructions | 9 | 9 | 156 |

For a short list the difference is the same: at `n = 9`, Unboxed `fromListN` allocates 1072 bytes for each call and the `foldr` writer 136.

The generic `fromListN` ([lines 2418 to 2420][gfromlistn]) is `unstream . Bundle.fromListN n`. `Bundle.fromListN` ([lines 988 to 990][bfromlistn]) is `fromStream (S.fromListN n xs)`. `S.fromListN` in vector-stream ([lines 1457 to 1464][sfromlistn]) is:

```haskell
fromListN m zs = Stream step (zs,m)
  where
    {-# INLINE_INNER step #-}
    step (_, n) | n <= 0 = return Done
    step (x:xs,n)        = return (Yield x (xs,n-1))
    step ([],_)          = return Done
```

The step function takes the list apart by `case`, so no rule can fuse the list's producer into it.

## Proposed fix

Write `fromListN` as one `foldr` that writes each element into a new mutable vector of `n` elements, and stops after `n` elements. This is the function that orthotope uses:

```haskell
fromListN :: Vector v a => Int -> [a] -> v a
{-# INLINE fromListN #-}
fromListN n xs = create (do
    out <- M.unsafeNew (max 0 n)
    let {-# INLINE step #-}
        step x k = \ !i -> do
          M.unsafeWrite out i x
          if i + 1 < n then k (i + 1) else return out
    if n <= 0 then return out
    else foldr step (\ !i -> return (M.unsafeSlice 0 i out)) xs 0)
```

It reads no list cell after the `n`th element, as `take n` reads none. If the list is shorter than `n`, the result has the elements of the list.

This change has a cost. The current `fromListN` is a stream, so a consumer such as `sum (fromListN n xs)` can fuse with it through `stream/unstream`, and the program does not build the vector. The `foldr` writer always builds the vector. Two rewrite rules can keep both fusions. The first rule replaces `fromListN n (build g)` with the `foldr` writer, and must fire before GHC inlines `build`. The second rule replaces `stream (fromListN n xs)` with the stream of the list, which `stream/unstream` gives when GHC has inlined `fromListN`, so that a stream consumer fuses with `fromListN` when the first rule does not fire. To test the rules, we put them on a wrapper of `Data.Vector.Unboxed.fromListN` that GHC inlines in phase 1 and after, and made both rules active before phase 1. `foldrFromListN` is the `foldr` writer above:

```haskell
{-# INLINE [1] wrappedFromListN #-}
wrappedFromListN :: Int -> [Double] -> Data.Vector.Unboxed.Vector Double
wrappedFromListN = Data.Vector.Unboxed.fromListN
{-# RULES
"wrappedFromListN/build" [~1]
      forall n (g :: forall b. (Double -> b -> b) -> b -> b).
      wrappedFromListN n (build g) = foldrFromListN n (build g)
"wrappedFromListN/stream" [~1]
      forall n xs. Data.Vector.Generic.stream (wrappedFromListN n xs)
                     = Data.Vector.Fusion.Bundle.fromListN n xs
  #-}
```

With `-O2` on GHC 9.12.4 and `n = 200000`, the Core and the counts show these results for `sum (wrappedFromListN n xs)`:

* When `xs` comes from `build`, as `take n (iterate (+ 1) x)` does, the first rule fires. The program does not build the list, and it builds the vector. It executes 13 instructions and allocates 8 bytes for each element.
* When `xs` does not come from `build`, the second rule fires, and `sum` reads the list directly. The program builds the list, and it does not build the vector. It executes 125 instructions and allocates 96 bytes for each element. These are the values of the current `fromListN` on the same list.
* For comparison, the current `fromListN` on the list from `build`: `stream/unstream` fires, and `sum` reads the list directly. The program does not build the vector, but it builds the list. It executes 125 instructions and allocates 96 bytes for each element.

GHC 9.14.1 gives the same values. With `-O1` and with `-O1 -fspec-constr`, the bytes are the same, and the instructions are the same or 1 more. Without the second rule, the wrapper prevents `stream/unstream`: when `xs` does not come from `build`, the program builds the list and the vector, and it executes 137 instructions and allocates 104 bytes for each element.

## Steps to reproduce

1. Save the program below as `Repro.hs`.

2. Run it. To select a compiler, add `-w ghc-VERSION`.

```
cabal run -v0 Repro.hs
```

3. On GHC 9.12.4, the output is:

```
n =      9  Unboxed fromListN            1072.0 bytes      0.185 us
n =      9  Unboxed foldr writer          136.0 bytes      0.015 us
n =      9  Storable fromListN           1032.0 bytes      0.114 us
n =      9  Storable foldr writer         152.0 bytes      0.020 us
n =      9  boxed fromListN              1000.0 bytes      0.105 us
n =      9  boxed foldr writer            496.0 bytes      0.064 us
n = 200000  Unboxed fromListN        20800136.2 bytes   3366.599 us
n = 200000  Unboxed foldr writer      1600064.0 bytes    145.237 us
n = 200000  Storable fromListN       20800096.0 bytes   3277.683 us
n = 200000  Storable foldr writer     1600080.0 bytes    161.982 us
n = 200000  boxed fromListN          25782360.0 bytes  15781.821 us
n = 200000  boxed foldr writer       14582360.0 bytes   6771.055 us
```

```haskell
{- cabal:
build-depends: base, vector ==0.13.2.0
ghc-options: -O2
-}
{-# LANGUAGE BangPatterns #-}
-- Reproducer: fromListN of a list that a producer builds allocates each cons
-- cell and boxed element of the list, where a foldr consumer fuses with the
-- producer and allocates only the vector.
--
-- Run: cabal run -v0 Repro.hs
module Main (main) where

import Control.Exception (evaluate)
import Control.Monad (forM_)
import qualified Data.Vector as VB
import qualified Data.Vector.Generic as VG
import qualified Data.Vector.Generic.Mutable as VGM
import qualified Data.Vector.Storable as VS
import qualified Data.Vector.Unboxed as VU
import GHC.Clock (getMonotonicTime)
import System.Mem (getAllocationCounter)
import Text.Printf (printf)

-- fromListN as one foldr that writes into a new vector.
{-# INLINE foldrFromListN #-}
foldrFromListN :: VG.Vector v a => Int -> [a] -> v a
foldrFromListN n xs = VG.create (do
    out <- VGM.unsafeNew (max 0 n)
    let {-# INLINE step #-}
        step x k = \ !i -> do
          VGM.unsafeWrite out i x
          if i + 1 < n then k (i + 1) else return out
    if n <= 0 then return out
    else foldr step (\ !i -> return (VGM.unsafeSlice 0 i out)) xs 0)

{-# INLINE from #-}
from :: Int -> Int -> [Double]
from n i = take n (iterate (+ 1) (fromIntegral i))

{-# NOINLINE flU #-}
flU, flUf :: Int -> Int -> VU.Vector Double
flU n i = VU.fromListN n (from n i)
{-# NOINLINE flUf #-}
flUf n i = foldrFromListN n (from n i)
{-# NOINLINE flS #-}
flS, flSf :: Int -> Int -> VS.Vector Double
flS n i = VS.fromListN n (from n i)
{-# NOINLINE flSf #-}
flSf n i = foldrFromListN n (from n i)
{-# NOINLINE flB #-}
flB, flBf :: Int -> Int -> VB.Vector Double
flB n i = VB.fromListN n (from n i)
{-# NOINLINE flBf #-}
flBf n i = foldrFromListN n (from n i)

-- Bytes and microseconds for each call, the mean of reps calls, each
-- result evaluated and its last element read.
measure :: Int -> (Int -> IO ()) -> IO (Double, Double)
measure reps run = do
  run 0
  a0 <- getAllocationCounter
  t0 <- getMonotonicTime
  forM_ [1 .. reps] run
  t1 <- getMonotonicTime
  a1 <- getAllocationCounter
  return ( fromIntegral (a0 - a1) / fromIntegral reps
         , (t1 - t0) / fromIntegral reps * 1e6 )

main :: IO ()
main = forM_ [9, 200000] $ \ n -> do
  let reps = max 10 (20000000 `div` n)
      u f i = evaluate (f n i) >>= evaluate . VU.last >> return ()
      s f i = evaluate (f n i) >>= evaluate . VS.last >> return ()
      b f i = evaluate (f n i) >>= evaluate . VB.last >> return ()
      cases = [ ("Unboxed fromListN", u flU), ("Unboxed foldr writer", u flUf)
              , ("Storable fromListN", s flS), ("Storable foldr writer", s flSf)
              , ("boxed fromListN", b flB), ("boxed foldr writer", b flBf) ]
  forM_ cases $ \ (name, run) -> do
    (bytes, us) <- measure reps run
    printf "n = %6d  %-22s %12.1f bytes %10.3f us\n" n name bytes us
```

## Expected behavior

`fromListN n xs` fuses with a list producer, as a `foldr` consumer does, and allocates only the vector.

## Environment

* vector-0.13.2.0, from Hackage. On master at [d0f42e0562][master], the generic `fromListN`, `Bundle.fromListN` and vector-stream's `fromListN` have the same code.
* GHC 9.12.4 and 9.14.1; cabal-install 3.18.2.0.
* Linux (kernel 7.0.0-38-generic), x86_64 (AMD Ryzen 7 5800X).

[439]: https://github.com/haskell/vector/issues/439
[388]: https://github.com/haskell/vector/issues/388
[565]: https://github.com/haskell/vector/issues/565
[301]: https://github.com/haskell/vector/issues/301
[229]: https://github.com/haskell/vector/issues/229
[gfromlistn]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector/src/Data/Vector/Generic.hs#L2418-L2420
[bfromlistn]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector/src/Data/Vector/Fusion/Bundle/Monadic.hs#L988-L990
[sfromlistn]: https://github.com/haskell/vector/blob/d0f42e056202fa24b479833dbc21222c1964d096/vector-stream/src/Data/Stream/Monadic.hs#L1457-L1464
[master]: https://github.com/haskell/vector/tree/d0f42e056202fa24b479833dbc21222c1964d096
[578]: https://github.com/haskell/vector/issues/578
