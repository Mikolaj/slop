# GHC issue: following -Wredundant-bang-patterns can change the result of a function, if an earlier equation matches a pattern synonym that does not force its argument

Staged and filed 2026-10-22 as [GHC work item 28014](https://gitlab.haskell.org/ghc/ghc/-/work_items/28014); this file stays as the filed record, the text from "## Summary" down being the filed body, in the tracker's bug template. It makes a ticket of its own of the comment posted on GHC [#27862](https://gitlab.haskell.org/ghc/ghc/-/work_items/27862) on 2026-09-29 ([note 701165](https://gitlab.haskell.org/ghc/ghc/-/work_items/27862#note_701165), record [ghc-issue-redundant-bang-pattern-synonym-comment.md](ghc-issue-redundant-bang-pattern-synonym-comment.md)), to which simonpj answered "This seems like an entirely separate issue." and "Make a new ticket!" ([note 701222](https://gitlab.haskell.org/ghc/ghc/-/work_items/27862#note_701222)), and AndreasK agreed on 2026-10-22 ([note 705616](https://gitlab.haskell.org/ghc/ghc/-/work_items/27862#note_705616)). Title: **Following `-Wredundant-bang-patterns` can change the result of a function, if an earlier equation matches a pattern synonym that does not force its argument**. The prose is ASD-STE100 Simplified Technical English. The search of 2026-10-22 of the tracker's issues and merge requests for "redundant bang", "Wredundant-bang", "pattern synonym bang", "pattern synonym strict" and "isPmAltConMatchStrict", and of the issues opened since 2026-09-28 for "pattern synonym", "PatternSynonyms" and "pattern match checker", found no report since the comment; it found GHC [#27323](https://gitlab.haskell.org/ghc/ghc/-/work_items/27323) and GHC [!16395](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16395), open, which are about the bangs that `-XStrict` adds, not this. Verified 2026-10-22 from `Repro.hs` as shown here, the warning quoted from HEAD under `LC_ALL=C`; code read at master 3d326d7d28, the pattern-synonym equation of `isPmAltConMatchStrict` unchanged at master 593f5f5bbe.

## Summary

`-Wredundant-bang-patterns` reports a bang on an argument as redundant when an earlier equation matches that argument against a pattern synonym. If the matcher of the synonym does not force its argument, the bang is not redundant. The defect affects semantics: if you follow the warning and remove the bang, the function can give a different result. In the reproducer below, `withBang undefined` is bottom, and `withoutBang undefined`, the same function without the bang, is `2`. GHC compiles both functions correctly; the defect is in the advice of the warning.

The pattern-match checker uses a strictness assumption: it treats each match on a pattern synonym as one that forces its argument. [`isPmAltConMatchStrict`][strict] in `GHC.HsToCore.Pmc.Solver.Types` returns `True` for a pattern synonym, with a reference to #17357. Thus, after an equation with a pattern synonym fails, the checker excludes bottom as a value of the argument, and it reports a bang on that argument in a later equation as dead (Note [Dead bang patterns] in [`GHC.HsToCore.Pmc.Check`][dead]).

The decision in #17357 (2019-10-18) was not to bother about pattern synonyms that can fail to match and do not force their argument, as degenerate, and to keep the assumption. Its description already shows that, for its function `f`, the deletion of a clause that GHC reports as redundant is unsound. The bang warning (731c8d3bc5, first in 9.2.1) came later and adds a second warning with the same risk. The discussion of #17340, where the warning was designed, expected this risk for a bang directly on a lazy pattern synonym, `f !(Con _)` with `pattern Con x <- ~[x]`: "a good example where we'd give unsound advice (see #17357 for why)". The implemented warning reports only dead bangs, and it does not report that bang. But it reports a bang in a later equation, where the same assumption applies.

This was first a comment on #27862, which is about a different effect of the same warning.

## Steps to reproduce

`Repro.hs`, where `F` is the synonym `F` of #17357:

```haskell
{-# LANGUAGE BangPatterns, PatternSynonyms, ViewPatterns #-}
module Main (main) where

import Control.Exception (ErrorCall, evaluate, try)

-- Never matches, and does not force its argument.
pattern F :: Bool
pattern F <- (const False -> True)

withBang :: Bool -> Int
withBang F = 1
withBang !_ = 2

-- The same function, with the warning followed.
withoutBang :: Bool -> Int
withoutBang F = 1
withoutBang _ = 2

run :: Int -> IO String
run v = either (\e -> const "bottom" (e :: ErrorCall)) show <$> try (evaluate v)

main :: IO ()
main = do
  a <- run (withBang undefined)
  b <- run (withoutBang undefined)
  print (a, b)
```

`ghc -Wredundant-bang-patterns Repro.hs` reports:

```
Repro.hs:12:11: warning: [GHC-38520] [-Wredundant-bang-patterns]
    Pattern match has redundant bang
    In an equation for `withBang': withBang _ = ...
   |
12 | withBang !_ = 2
   |           ^
```

Then `./Repro` prints `("bottom","2")`, the results of `withBang undefined` and `withoutBang undefined`. When the view pattern `(const False -> True)` is written directly in the first equation of `withBang`, GHC gives no warning.

## Expected behavior

GHC does not report the bang in `withBang`, because the bang is not redundant.

Two possible changes. The check for dead bangs can ignore the strictness assumption for pattern synonyms, and the coverage checks can keep it. Then the warning does not report some redundant bangs, but it does not give unsound advice. Or, if the assumption stays for all checks, the documentation of `-Wredundant-bang-patterns` can tell that the warning treats each match on a pattern synonym as one that forces its argument.

## Environment

- GHC 9.6.7, 9.8.4, 9.10.3, 9.12.4, 9.14.1 and a HEAD build (master 3d326d7d28 with some MRs), at `-O0` and `-O`, all with the same result.
- x86-64 Linux.

[strict]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/HsToCore/Pmc/Solver/Types.hs#L589-595
[dead]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/HsToCore/Pmc/Check.hs#L250-281

/label ~"T::bug"

/label ~"needs triage"
