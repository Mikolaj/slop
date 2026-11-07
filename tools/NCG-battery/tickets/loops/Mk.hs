{-# LANGUAGE MagicHash, UnboxedTuples, BangPatterns #-}
-- Mk.hs: an array of evaluated Doubles, built at -O2
module Mk (Arr(..), mkArr) where
import GHC.Exts
data Arr = Arr (Array# Double)
mkArr :: Int -> Arr
mkArr (I# n) = runRW# (\s -> case newArray# n (0.0 :: Double) s of
  (# s1, m #) ->
    let go i s' | isTrue# (i >=# n) = s'
                | otherwise = let !x = D# (int2Double# i)
                              in go (i +# 1#) (writeArray# m i x s')
    in case unsafeFreezeArray# m (go 0# s1) of (# _, a #) -> Arr a)
{-# NOINLINE mkArr #-}
