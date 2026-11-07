{-# LANGUAGE BangPatterns #-}

module Sink2 where

data S = S !Int !Int !Int !Int !Int !Int !Int !Int !Int

spill :: S -> S -> S -> S
spill (S !a !b !c !d !e !f !g !h !i) (S !j !k !l !m !n !o !p !q !r) (S !s !t !u !v !w !x !y !z _)
 = S (a + j + s) (b + c) (k + r) (a + b + c + d + e + f + g + h + i) (j + k + l + m + n + o + p + q + r) (s + t + u + v + w + x + y + z) (a + b + c) (j + k + l) (s + t + u)
