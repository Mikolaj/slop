module Main (main) where

import GHC.Arr (Array (..), listArray)
import Lib
import System.Environment (getArgs)

{-# OPAQUE force #-}
force :: Int -> V -> ()
force r v = nf (pass r v)

{-# OPAQUE pass #-}
pass :: Int -> a -> a
pass _ x = x

mk :: Int -> V
mk k = case listArray (0, k - 1) [fromIntegral i | i <- [0 .. k - 1]] of
  Array _ _ _ a -> V [k] k () a

main :: IO ()
main = do
  [k, reps] <- map read <$> getArgs
  let flat = mk k
      loop :: Int -> ()
      loop 0 = ()
      loop r = case force r flat of () -> loop (r - 1)
  print (loop reps)
