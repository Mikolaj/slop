{-# LANGUAGE CPP, MagicHash, UnboxedTuples #-}
module Lib (V (..), nf) where

import GHC.Exts

data V = V [Int] Int () (Array# Double)

{-# NOINLINE ping #-}
ping :: [Int] -> Int
ping = foldr (\_ c -> c + 1) 0

nf :: V -> ()
nf (V sh n e arr) = case ping sh of
  I# 0# -> n `seq` e `seq` ()
  I# _ -> case n of
    I# n# -> e `seq`
      let go i | isTrue# (i >=# n#) = ()
               | otherwise = case indexArray# arr i of
                   (# x #) -> case x of D# _ -> go (i +# 1#)
      in go 0#
#if defined(INL)
{-# INLINE nf #-}
#else
{-# NOINLINE nf #-}
#endif
