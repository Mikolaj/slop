{-# LANGUAGE BangPatterns #-}
-- C23's price: a scan shaped like megaparsec's decimal over Text (the
-- digits taken by a predicate, then their value folded), on K digits of
-- UTF-8 width W (1: '7', 2: U+0667, 3: U+0967, 4: U+1D7D5), N times.
-- Usage: Main N K W; prints the sum so that nothing is dropped.
module Main (main) where
import qualified Data.Text as T
import Data.Bits ((.&.))
import Data.Char (isNumber, ord)
import System.Environment (getArgs)

scan :: Int -> T.Text -> Int
scan i t = T.foldl' (\a c -> a * 10 + (ord c .&. 15)) 0
                    (T.takeWhile isNumber (T.drop (i .&. 1) t))
{-# NOINLINE scan #-}

main :: IO ()
main = do
  [n, k, w] <- map read <$> getArgs
  let ch = case w of { 1 -> '7'; 2 -> '\x0667'; 3 -> '\x0967'; _ -> '\x1D7D5' }
      !input = T.replicate k (T.singleton ch) <> T.pack " end"
      go :: Int -> Int -> Int
      go !i !acc | i == 0    = acc
                 | otherwise = go (i - 1) (acc + scan i input)
  print (go n 0)
