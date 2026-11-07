{-# LANGUAGE BangPatterns, MagicHash, CPP #-}
{-# OPTIONS_GHC -O2 -funbox-strict-fields #-}
module HashStr where

import Foreign.C
import GHC.Exts
import Data.Word
import GHC.Ptr (Ptr (..))

#define hASH_TBL_SIZE          4091

hashStr  :: Ptr Word8 -> Int -> Int
 -- use the Addr to produce a hash value between 0 & m (inclusive)
hashStr (Ptr a#) (I# len#) = loop 0# 0#
   where
    loop h n | isTrue# (n GHC.Exts.==# len#) = I# h
             | otherwise  = loop h2 (n GHC.Exts.+# 1#)
          where !c = ord# (indexCharOffAddr# a# n)
                !h2 = (c GHC.Exts.+# (h GHC.Exts.*# 128#)) `remInt#`
                      hASH_TBL_SIZE#
