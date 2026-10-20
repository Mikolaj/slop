# GHC merge request comment: !16675 also adds 10 to the size of a non-unary class's applied method, which its changelog entry does not mention

Staged and posted 2026-10-20 as [a comment](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16675#note_705379) on GHC [!16675](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16675), "Tweak inlining discout for unary class ops." (open, by AndreasK, head f84c3214bb), the fix for GHC [#27802](https://gitlab.haskell.org/ghc/ghc/-/work_items/27802) and GHC [#27818](https://gitlab.haskell.org/ghc/ghc/-/work_items/27818); this file stays as the record of the comment, the text from "f84c3214bb also adds 10" down being the body as drafted. Verified on 2026-10-20 with quick-flavour builds of master 3d326d7d28 with GHC [!16719](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16719), [!16658](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16658) and [!16600](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600) merged, and of the same with !16675 merged as well, from the file as shown here. Found in the inlining catalogue's E20 (`docs/inlining-catalogue.md`), where a section's `vMap` call sized 10 more with `merged-mrs` than with GHC HEAD 10.1.20260918, past the threshold, so it stayed let-bound where it had been copied. Read on 2026-10-20: all the MR's notes; simonpj's of 2026-10-01 and 2026-10-08 and AndreasK's of 2026-10-07 discuss the extra 10 for a non-unary class, AndreasK counting it as the method's own call after `op d`, and none mentions the changelog.

f84c3214bb also adds 10 to the size of a *non-unary* class's method applied to further arguments, none of them void, which the changelog entry (`changelog.d/T27802-classop-arg-size`, about unary class methods only) does not mention. `classOpSize` for a method applied to n >= 1 further value arguments was `20 + 10 * n` and is now `20 + callSize n voids`, `callSize n v = 10 * (1 + n - v)`, so `30 + 10 * n` when no argument is void.

It can change whether a small function inlines. `Repro.hs`:

```haskell
module Repro (C (..), f, g) where

class C a where
  op1 :: a -> a -> a
  op2 :: a -> a

f :: C a => a -> a -> a
f x y = op1 x y

g :: C a => a -> a
g x = op2 (op1 x x)
```

`ghc -O1 -ddump-simpl -c Repro.hs` on master 3d326d7d28, and with !16719, !16658 and !16600 merged into it, gives `f` `Guidance=ALWAYS_IF(arity=3,unsat_ok=True,boring_ok=True)` and `g` `Guidance=IF_ARGS [180 0] 70 0`; with this MR merged as well, `f` `Guidance=IF_ARGS [90 0 0] 50 0` and `g` `Guidance=IF_ARGS [180 0] 90 0`. So `f`, which calls one method of a two-method class, is no longer inlined unconditionally.

The thread above explains the extra 10 as the method's own call after `op d`; if it stays, the changelog could say that non-unary class methods became dearer too.
