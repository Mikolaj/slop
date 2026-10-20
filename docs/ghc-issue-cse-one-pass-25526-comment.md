# GHC issue comment: CSE's one pass over the top-level bindings compiles two copies of the same code differently

Staged and posted 2026-10-20 as [a comment](https://gitlab.haskell.org/ghc/ghc/-/work_items/25526#note_705423) on GHC [#25526](https://gitlab.haskell.org/ghc/ghc/-/work_items/25526) ("Order-dependent interaction between SPECIALISE and CSE", open), opening with the sentence Mikolaj gave and following up with GHC [#23925](https://gitlab.haskell.org/ghc/ghc/-/work_items/23925), which GHC [!11236](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/11236) closed by adding `-fno-cse` to the perf tests T15426 and T18964 (98e7c1cff8), changing no compiler code; this file stays as the record of the comment, the text from "There is also" down being the body as drafted. Every command in it was run as printed, with GHC HEAD 10.1.20261019 (`merged-mrs`: master 3d326d7d28 with MRs and fixes, the fix of GHC [#27974](https://gitlab.haskell.org/ghc/ghc/-/work_items/27974) in `GHC.Core.Opt.CSE` among them, which keeps INLINE and INLINABLE unfoldings); its module, which has no pragma, compiles the same way with 9.6.7, 9.8.4, 9.10.3, 9.12.4 and 9.14.1. Found in orthotope's specialisation benchmark, where a change filling `fromList`'s vector by one `foldr` cost Dynamic's Storable and Unboxed and Ranked's Storable `fromVector` rows 4 instructions a call by this mechanism, while the boxed rows escaped it. Code read at master 3d326d7d28; #25526's description and its one comment read 2026-10-20.

There is also an order-dependent interaction between CSE and CSE itself.

Top-level CSE is a single pass over the bindings in order ([`cseProgram`][cseprogram]), so it can rewrite a binding in terms of an earlier binding but not of a later one. In the module below, `f1` and `f2` have the same text, and only `f2` comes after `g`, whose `case` scrutinee `strides [3, 3]` full laziness floats to top level as a binding of its own. It floats each copy's pair `(n, st)` to top level too. CSE rewrites `f2`'s pair into a `case` of `g`'s binding, which makes it work-free (Note [Case expressions are work-free] in [`GHC.Core.Utils`][workfree]), so the simplifier inlines it into `f2`, which then tests the list's constructor on every call. `f1`'s pair comes before `g`'s binding and keeps its call, and `f1` reads the evaluated pair.

```haskell
module T (f1, g, f2) where

strides :: [Int] -> [Int]
strides [] = [1]
strides (s : ss) = case strides ss of
  r@(m : _) -> s * m : r
  [] -> []

noStrides :: a
noStrides = error "no strides"
{-# NOINLINE noStrides #-}

f1 :: Int -> Int
f1 v = n + v + length st
  where (n, st) = case strides [3, 3] of { n : st -> (n, st); [] -> noStrides }

g :: Int -> Int
g v = case strides [3, 3] of { n : st -> n * v + length st; [] -> noStrides }

f2 :: Int -> Int
f2 v = n + v + length st
  where (n, st) = case strides [3, 3] of { n : st -> (n, st); [] -> noStrides }
```

`ghc -O -ddump-simpl -dsuppress-all -dsuppress-uniques -ddump-to-file T.hs`, in `T.dump-simpl` (excerpt):

```
f5
  = case strides f6 of {
      [] -> noStrides;
      : n st -> (n, st)
    }

f1
  = \ v ->
      case f5 of { (n, st) ->
      case n of { I# x ->
      case v of { I# y -> case f4 of { I# y1 -> I# (+# (+# x y) y1) } }
      }
      }

f10 = strides f6

f2
  = \ v ->
      case f10 of {
        [] -> case noStrides of {};
        : n st ->
          case n of { I# x ->
          case v of { I# y -> case f9 of { I# y1 -> I# (+# (+# x y) y1) } }
          }
      }
```

`ghc -O -fforce-recomp -ddump-cse -dsuppress-all -ddump-to-file T.hs` shows the step, in `T.dump-cse` (excerpt; the uniques vary):

```
ds_sUj
  = case strides lvl_sVL of wild_XKv {
      [] -> noStrides;
      : n_aA8 st_aA9 -> (n_aA8, st_aA9)
    }

lvl_sUq = strides lvl_sVL

ds_sUy
  = case lvl_sUq of wild_XKG {
      [] -> noStrides;
      : n_aGJ st_aGK -> (n_aGJ, st_aGK)
    }
```

With `g` moved above `f1`, or below `f2`, the two copies compile alike (and CSE then makes `f2 = f1`); `-fno-cse` gives both of them the pair. GHC 9.6.7, 9.8.4, 9.10.3, 9.12.4, 9.14.1 and a HEAD build (master 3d326d7d28 with some MRs) all do the same. Called through an unknown function by `Main.hs` below (`ghc -O Main.hs`), `f2` runs 4 instructions a call more than `f1`: `perf stat -e instructions:u ./Main 1 10000000` and `./Main 1 20000000` count 894115693 and 1780557579 instructions, 88.6 a call by their difference, and `./Main 2 ...` 934116387 and 1860558381, 92.6 a call.

```haskell
{-# LANGUAGE BangPatterns #-}
import System.Environment (getArgs)
import T (f1, f2)

go :: (Int -> Int) -> Int -> Int -> Int
go f = loop
  where loop 0 !acc = acc
        loop k !acc = loop (k - 1) (acc + f k)
{-# NOINLINE go #-}

main :: IO ()
main = do
  [w, n] <- getArgs
  print (go (if w == "1" then f1 else f2) (read n) 0)
```

It is well known that this makes benchmarks fragile: #23925 was fixed by adding `-fno-cse` to two perf tests so that the independent tests in each module would not interact, and this is one concrete reproducer of such an interaction. I met it in a benchmark module of many independent rows, where whether a row compiled to the pair or to the list, 4 instructions a call apart, depended on which other rows the module held and on the order in which GHC placed two floated bindings, not on the row's own code.

[cseprogram]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Opt/CSE.hs#L382-384
[workfree]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Utils.hs#L1818-1830
