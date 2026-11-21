# The default GHC: what it fixes and carries

What the default GHC of `~/slop`, `~/slop/ghc/_build/stage1/bin/ghc`, carries
beyond GHC master; `CLAUDE.md` at the root of `~/slop` says how it is built.
Read this before deciding whether a workaround for a GHC issue is still needed:
an issue listed here is fixed in the default compiler, whatever released
compilers do.

### The NCG series

The compiler is built from the branch `for-review` of `ghc/`, pushed
as the `master` of
[Mikolaj/vibed-ghc-fixes](https://gitlab.haskell.org/Mikolaj/vibed-ghc-fixes/-/tree/master):
a merge of the NCG series of `for-review-master`, pushed
as `wip/T27981-ncg-mystery-box`, into the branch below, and on it a fix
of a full-laziness float
that [!16600](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600) loses,
a join point's body case-floats kept below it in the Gentle phase, which
with !16600 fixes GHC
[#28164](https://gitlab.haskell.org/ghc/ghc/-/work_items/28164). The series
fixes GHC [#27980](https://gitlab.haskell.org/ghc/ghc/-/work_items/27980),
[#27800](https://gitlab.haskell.org/ghc/ghc/-/work_items/27800),
[#27981](https://gitlab.haskell.org/ghc/ghc/-/work_items/27981),
[#26631](https://gitlab.haskell.org/ghc/ghc/-/work_items/26631),
[#27619](https://gitlab.haskell.org/ghc/ghc/-/work_items/27619),
[#27437](https://gitlab.haskell.org/ghc/ghc/-/work_items/27437),
[#27448](https://gitlab.haskell.org/ghc/ghc/-/work_items/27448),
[#28093](https://gitlab.haskell.org/ghc/ghc/-/work_items/28093),
[#28060](https://gitlab.haskell.org/ghc/ghc/-/work_items/28060),
[#8327](https://gitlab.haskell.org/ghc/ghc/-/work_items/8327),
[#27991](https://gitlab.haskell.org/ghc/ghc/-/work_items/27991),
[#27799](https://gitlab.haskell.org/ghc/ghc/-/work_items/27799),
[#20334](https://gitlab.haskell.org/ghc/ghc/-/work_items/20334)
and [#27638](https://gitlab.haskell.org/ghc/ghc/-/work_items/27638).

### The branch under it

The merge's first parent is the branch `merged-mrs`, also pushed to
[Mikolaj/vibed-ghc-fixes](https://gitlab.haskell.org/Mikolaj/vibed-ghc-fixes/-/tree/merged-mrs):
GHC master at `83038fbee5`, plus MRs
[!16658](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16658),
[!16600](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16600), fixing
[#28163](https://gitlab.haskell.org/ghc/ghc/-/work_items/28163),
[!16675](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16675),
[!16684](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16684),
[!16619](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16619),
[!16899](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16899), fixing GHC
[#27862](https://gitlab.haskell.org/ghc/ghc/-/work_items/27862),
and [!16901](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16901), fixing
[#27973](https://gitlab.haskell.org/ghc/ghc/-/work_items/27973), and fixes
to GHC [#27667](https://gitlab.haskell.org/ghc/ghc/-/work_items/27667),
[#27778](https://gitlab.haskell.org/ghc/ghc/-/work_items/27778),
[#27868](https://gitlab.haskell.org/ghc/ghc/-/work_items/27868),
[#27873](https://gitlab.haskell.org/ghc/ghc/-/work_items/27873),
[#27874](https://gitlab.haskell.org/ghc/ghc/-/work_items/27874),
[#27879](https://gitlab.haskell.org/ghc/ghc/-/work_items/27879),
[#27880](https://gitlab.haskell.org/ghc/ghc/-/work_items/27880),
[#27951](https://gitlab.haskell.org/ghc/ghc/-/work_items/27951),
[#27974](https://gitlab.haskell.org/ghc/ghc/-/work_items/27974),
[#27975](https://gitlab.haskell.org/ghc/ghc/-/work_items/27975),
[#27976](https://gitlab.haskell.org/ghc/ghc/-/work_items/27976)
and [#27990](https://gitlab.haskell.org/ghc/ghc/-/work_items/27990).

### The stale commit id

Its `ghc --info` names as "Project Git commit id" the commit `./configure` last
ran at, so after a switch of branch without it that id is stale: on 2026-10-30
it named the old `for-review`, `201f499705`, for a build of `da35817d62`.
