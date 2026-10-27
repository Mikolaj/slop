# GHC merge request description: an experiment inlining INLINE functions in boring contexts too, for #27984

Staged 2026-10-26 as the description of a draft merge request from `wip/T27984-inline-boring` (commit `43e49b6001`, on master at `a4a3a964b0`) into GHC's master, for GHC [#27984](https://gitlab.haskell.org/ghc/ghc/-/work_items/27984); the title is **Experiment: inline INLINE functions in boring contexts too (#27984)**, and the text from "Not for merging" down is the body.

Not for merging: an experiment for #27984, as Simon suggested in [this note][n706429], following [this one][n705599].

`mkInlineUnfoldingWithArity` gives every INLINE unfolding `ug_boring_ok = True`, so an INLINE function is inlined even at a call whose arguments and context carry no information. The same function also builds the unfoldings of the foreign-call wrappers in `GHC.HsToCore.Foreign.C` and `GHC.HsToCore.Foreign.JavaScript`, so the change reaches those too.

The aim is to see the effect on compile time (`perf/compiler`) and on code size (`perf/size`) in CI.

Generated with [Claude Code](https://claude.com/claude-code)

[n705599]: https://gitlab.haskell.org/ghc/ghc/-/work_items/27984#note_705599
[n706429]: https://gitlab.haskell.org/ghc/ghc/-/work_items/27984#note_706429
