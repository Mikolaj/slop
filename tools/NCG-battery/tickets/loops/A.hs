{-# LANGUAGE BangPatterns, MagicHash, UnboxedTuples #-}
module A (rnfArr, Array(..)) where
import GHC.Exts
import Control.DeepSeq (NFData, rnf)
-- h30/A.hs with Data.Primitive.Array's Array and indexArray written out
data Array a = Array (Array# a)
indexArray :: Array a -> Int -> a
indexArray (Array a) (I# i) = case indexArray# a i of (# x #) -> x
{-# INLINE indexArray #-}
-- orthotope's rnfArrayFrom (RA), specialised as OpsShaped's copy is
{-# INLINABLE rnfArrayFrom #-}
rnfArrayFrom :: NFData a => Int -> Int -> Array a -> ()
rnfArrayFrom !i !hi !arr
  | i >= hi = ()
  | otherwise = rnf (indexArray arr i) `seq` rnfArrayFrom (i + 1) hi arr
rnfArr :: Int -> Int -> Array Double -> ()
rnfArr = rnfArrayFrom
