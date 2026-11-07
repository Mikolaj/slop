{-# LANGUAGE MagicHash, UnboxedTuples #-}
-- Main.hs W K: K calls of loop W (A: 1000 elements, T8905 and S3: 500,
-- Repro: 1000 iterations); compiled -O0 so that every call runs
import GHC.Exts
import Control.Exception (evaluate)
import Control.Monad (forM_)
import System.Environment (getArgs)
import qualified A
import qualified T8905
import qualified S3
import qualified Repro
import Mk

main :: IO ()
main = do
  [w, ks] <- getArgs
  let k = read ks :: Int
  case mkArr 1000 of
    Arr a -> case w of
      "A"     -> forM_ [1 .. k] $ \_ -> evaluate (A.rnfArr 0 1000 (A.Array a))
      "T8905" -> forM_ [1 .. k] $ \_ -> evaluate (T8905.sumElems (T8905.A a) 0) >> return ()
      "S3"    -> forM_ [1 .. k] $ \_ -> evaluate (S3.sumFrom (S3.A a) 1.0 0) >> return ()
      "Repro" -> forM_ [1 .. k] $ \_ -> evaluate (I# (Repro.f 1# 2# 3# 4# 5# 1000# 0#)) >> return ()
      "none"  -> forM_ [1 .. k] $ \_ -> evaluate () >> return ()
      _       -> error w
