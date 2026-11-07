{-# LANGUAGE BangPatterns #-}
module W (f) where

-- A strict, spine-strict tree: the recursive calls' argument is usually
-- evaluated already, as in #8905's unordered-containers insert.
data T = L | N !Int !T !T

f :: Int -> Int -> T -> Int
f !x !y t = case t of
  L -> x + y
  N k l r -> k + x * y + f x y l + f y x r
