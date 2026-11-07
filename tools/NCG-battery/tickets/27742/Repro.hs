-- Reproducer for the order dependence of the linear register allocator.
-- Base only.
--
-- Build:     ghc -O1 -fforce-recomp Repro.hs -o repro
-- Time:      ./repro a 400 ; ./repro b 400        (prints ns per element)
-- Count:     perf stat -e instructions:u ./repro a 40, and again with 20;
--            the difference over 20 * 250357 is the instructions per element
-- Assembly:  ghc -O1 -S -fforce-recomp Repro.hs
--
-- fillA and fillB are one function written twice.  The bodies are
-- character-identical; only the order of the seven arguments differs.
-- Both are exported, so that each keeps its own symbol in the assembly.
-- The loop is a strided gather: for i below l, with q = i `quot` s
-- computed as a multiply-high and a shift,
--
--     out[o0 + i] = v[tab[q] + (i - q * s) * t]
--
-- The mode argument selects the function, and the second argument is the
-- number of calls.  j `quot` k is 0 for every call; it keeps the calls
-- from being combined into one.
{-# LANGUAGE BangPatterns, MagicHash, UnboxedTuples #-}
module Main (main, fillA, fillB) where

import Data.Bits (countLeadingZeros, shiftR)
import Foreign.Marshal.Alloc (mallocBytes)
import Foreign.Ptr (Ptr)
import Foreign.Storable (peekElemOff, pokeElemOff)
import GHC.Clock (getMonotonicTime)
import GHC.Exts (Word (..), timesWord2#)
import System.Environment (getArgs)

{-# INLINE mulhi #-}
mulhi :: Word -> Word -> Word
mulhi (W# a) (W# b) = case timesWord2# a b of (# hi, _ #) -> W# hi

-- Granlund-Montgomery round-up magic: i `quot` d == mulhi m i `shiftR` sh
-- for every non-negative Int i and every d above 1.
{-# INLINE gmMagic #-}
gmMagic :: Int -> (Word, Int)
gmMagic d = let !mg = fromInteger (2 ^ (63 + lg) `div` toInteger d + 1)
                !sh = lg - 1
            in  (mg, sh)
  where !lg = 64 - countLeadingZeros (fromIntegral d - 1 :: Word)

{-# NOINLINE fillA #-}
fillA :: Ptr Double -> Int -> Int -> Ptr Int -> Int -> Int -> Ptr Double -> IO ()
fillA !out !s !t !tab !o0 !l !v = go 0 o0
  where !gm = gmMagic s
        !magic = fst gm
        !gsh = snd gm
        go !i !o
          | i >= l = return ()
          | otherwise = do
              let !q = fromIntegral (mulhi magic (fromIntegral i) `shiftR` gsh)
              b <- peekElemOff tab q
              x <- peekElemOff v (b + (i - q * s) * t)
              pokeElemOff out o x
              go (i + 1) (o + 1)

{-# NOINLINE fillB #-}
fillB :: Int -> Int -> Int -> Ptr Int -> Ptr Double -> Int -> Ptr Double -> IO ()
fillB !s !t !l !tab !out !o0 !v = go 0 o0
  where !gm = gmMagic s
        !magic = fst gm
        !gsh = snd gm
        go !i !o
          | i >= l = return ()
          | otherwise = do
              let !q = fromIntegral (mulhi magic (fromIntegral i) `shiftR` gsh)
              b <- peekElemOff tab q
              x <- peekElemOff v (b + (i - q * s) * t)
              pokeElemOff out o x
              go (i + 1) (o + 1)

main :: IO ()
main = do
  [mode, ks] <- getArgs
  let k = read ks :: Int
      -- a [97, 89, 29] array read as the view [97, 29, 89] with strides
      -- [2581, 1, 29]: 97 * 29 runs of s = 89 elements at stride t = 29
      l = 97 * 89 * 29
      s = 89
      t = 29
  out <- mallocBytes (8 * l)
  v <- mallocBytes (8 * l)
  mapM_ (\i -> pokeElemOff v i (fromIntegral i :: Double)) [0 .. l - 1]
  tab <- mallocBytes (8 * 97 * 29)
  mapM_ (\(i, b) -> pokeElemOff tab i b)
        (zip [0 ..] [a * 2581 + b | a <- [0 .. 96], b <- [0 .. 28]])
  t0 <- getMonotonicTime
  case mode of
    "a" -> mapM_ (\j -> fillA out s t tab (j `quot` k) l v) [0 .. k - 1]
    _   -> mapM_ (\j -> fillB s t l tab out (j `quot` k) v) [0 .. k - 1]
  x <- peekElemOff out (l - 1)
  print (x :: Double)
  t1 <- getMonotonicTime
  putStrLn ("ns/elem: " ++ show ((t1 - t0) * 1e9 / fromIntegral (k * l)))
