{-# LANGUAGE MagicHash, UnboxedTuples, BangPatterns #-}
module S3 (sumFrom, A(..)) where

import GHC.Exts

data A = A (Array# Double)

-- A loop's bound known on the path into the loop, after a call, and
-- a variable inside it: the loop's head gets the shallower stack.
sumFrom :: A -> Double -> Int -> Double
sumFrom (A arr) d off = case d of
  D# _ -> go off 0 (off + 500)
  where
    go !i !acc !n
      | i >= n = acc
      | otherwise = case indexArray# arr (unI i) of
          (# x #) -> go (i + 1) (acc + x) n
    unI (I# x) = x
{-# NOINLINE sumFrom #-}
