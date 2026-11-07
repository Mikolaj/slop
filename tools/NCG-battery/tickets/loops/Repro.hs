{-# LANGUAGE MagicHash #-}
module Repro (f) where

import GHC.Exts

f :: Int# -> Int# -> Int# -> Int# -> Int# -> Int# -> Int# -> Int#
f a b c d e n i = case i >=# n of
  1# -> a +# b +# c +# d +# e
  _ -> f a b c d e n (i +# 1#)
