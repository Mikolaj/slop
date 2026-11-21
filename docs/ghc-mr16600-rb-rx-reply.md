# GHC merge request comment: the code of RB.hs and RX.hs (with Z.hs), the earlier comment's two variants of GHC #28164's R.hs, for simonpj

Staged and posted 2026-11-21 as a reply on GHC [!16600](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600) to simonpj's "Can you give the code for RB and RX please?", asked of the comment recorded in `docs/ghc-mr16600-regressions-comment.md`; R.hs is the reproducer of GHC [#28164](https://gitlab.haskell.org/ghc/ghc/-/work_items/28164). This file stays as the record of the reply. The text from "The code is below" down is the body. A fresh agent wrote it; its three code blocks are byte-identical to the files compiled and run for it, whose bytes allocated equal the earlier comment's table.

The code is below: RB.hs, RX.hs, and Z.hs, the module RX.hs imports. RB.hs and RX.hs both start from the R.hs of #28164. RB.hs changes only `z`, whose two equations become one with nested cases. Z.hs holds R.hs's `T`, `work`, `expensive` and `z` unchanged, with their pragmas, and RX.hs holds the rest (`mkT`, `c`, `f`, `main`) unchanged and imports `Z`.

Compiled and run in a directory holding the three files with `ghc -O1 -rtsopts RB.hs` and `ghc -O1 -rtsopts RX.hs` (which compiles Z.hs too), then `./RB 200 +RTS -s` and `./RX 200 +RTS -s`; both print 13142050000. A re-run of exactly these files gives the earlier table's bytes allocated (master 83038fbee5 / tip f4e950c720): RB.hs 2,246,895,448 / 15,853,912, RX.hs 2,246,895,448 / 2,246,895,416.

RB.hs:

```haskell
module Main (main) where

import System.Environment (getArgs)

data T = T ![Int] !Int !Int

{-# NOINLINE work #-}
work :: [Int] -> [Int] -> Int -> Int -> [Int]
work sh ss o v = [ x * o + v + y | x <- sh, y <- ss ]

{-# INLINE expensive #-}
expensive :: [Int] -> T -> [Int]
expensive sh (T ss o v) = work sh ss o v

{-# INLINE z #-}
z :: [Int] -> T -> T -> Int
z sh t t' = case t of
  T ss _ v -> case t' of
    T _ _ v' | v == 1, v' == 1 -> sum ss
             | otherwise -> sum (expensive sh t) + sum (expensive sh t')

{-# NOINLINE mkT #-}
mkT :: Int -> T
mkT n = T [1 .. n] 3 5

c :: T
c = mkT 1000

{-# NOINLINE f #-}
f :: T -> Int
f a = z [1 .. 100] a c

main :: IO ()
main = do
  [n] <- map read <$> getArgs
  print (sum [ f (T [k] 0 2) | k <- [1 .. n] ])
```

RX.hs:

```haskell
module Main (main) where

import System.Environment (getArgs)
import Z

{-# NOINLINE mkT #-}
mkT :: Int -> T
mkT n = T [1 .. n] 3 5

c :: T
c = mkT 1000

{-# NOINLINE f #-}
f :: T -> Int
f a = z [1 .. 100] a c

main :: IO ()
main = do
  [n] <- map read <$> getArgs
  print (sum [ f (T [k] 0 2) | k <- [1 .. n] ])
```

Z.hs:

```haskell
module Z (T(..), work, expensive, z) where

data T = T ![Int] !Int !Int

{-# NOINLINE work #-}
work :: [Int] -> [Int] -> Int -> Int -> [Int]
work sh ss o v = [ x * o + v + y | x <- sh, y <- ss ]

{-# INLINE expensive #-}
expensive :: [Int] -> T -> [Int]
expensive sh (T ss o v) = work sh ss o v

{-# INLINE z #-}
z :: [Int] -> T -> T -> Int
z sh (T ss _ v) (T _ _ v')
  | v == 1, v' == 1 = sum ss
z sh t t' = sum (expensive sh t) + sum (expensive sh t')
```
