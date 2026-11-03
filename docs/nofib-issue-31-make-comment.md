# nofib issue comment: what the make build needs today, for nofib's #31

Staged 2026-11-01 as a comment on nofib's [#31](https://gitlab.haskell.org/ghc/nofib/-/issues/31), "Make build is broken", and posted the same day as [note 708235](https://gitlab.haskell.org/ghc/nofib/-/work_items/31#note_708235), the body below under a preface of Mikolaj's; this file stays as the record of the staged text. The fixes it offers are the branch `make-build-fixes` of Mikolaj/nofib, three commits on `d4750745` ending at `b064249`, pushed 2026-11-01. The six programs GHC master's non-canonical `return` error breaks under either build are nofib [!85](https://gitlab.haskell.org/ghc/nofib/-/merge_requests/85), staged in `nofib-mr-noncanonical-return-description.md`, which the comment cites. The body, as it would be posted, follows.

What the make build needs today beyond the explicit `-package` flags this issue is about, checked with GHC master (ghc/ghc@5308737363) and the recipe of GHC's `nofib` CI job ([.gitlab-ci.yml#L1018][ci], disabled there), with `random-1.3.1` in place of its `random-1.2.1` and the boot packages added to its package environment:

1. NofibUtils: `mk/boilerplate.mk` adds `nofib-common/NofibUtils.hs` to every program's sources (ae985b5) but not its directory to the search path, so every program importing `NofibUtils` fails to find it. `SRC_HC_OPTS += -i$(TOP)/nofib-common` beside it fixes that.
2. real/smallpt: `smallpt.stdout` ends in a newline that the program, printing with `hPutStr`, does not write, so runstdtest reports a mismatch whatever it computes; nofib-run compares without newlines. Dropping the newline from the file fixes it.
3. real/ben-raytrace: make compiles every module under `Random/` and `SamplerMonad/`, including those only a CPP flag selects. `Random/Wyhash64.hs` passes `Word64#` where `timesWord2#` takes `Word#`, and under random 1.3 the `StatefulGen` instances in `Random/Lehmer64Mut.hs` and `SamplerMonad/Unboxed.hs` meet the ambiguous default of `uniformByteArrayM`, which !77 stubbed out in `SamplerMonad/Naive.hs` alone. Converting with `word64ToWord#` and `wordToWord64#`, and the same stub in both instances, fix it.
4. random: since !77, ben-raytrace needs random 1.3 or later, while GHC's CI job installs `random-1.2.1`, which no longer compiles against master's `base` either (`replicateM` not in scope). That pin is in GHC's repository.
5. gc/happy has no `FAST_OPTS`, so in fast mode make runs it with no arguments and it prints its usage; nofib-run falls back to `NORM_OPTS`.

With 1 to 3, imaginary/bernouilli, real/smallpt and real/ben-raytrace build and match their expected output under make in fast mode, and none of them does without. The fixes for 1 to 3, a commit each, are on [a branch of my fork][br]; I can open a merge request from it if the make build is worth keeping working.

Separately, !85 fixes the six programs that GHC master's error on a non-canonical `return` (ghc/ghc!15795) breaks under either build.

[ci]: https://gitlab.haskell.org/ghc/ghc/-/blob/5308737363/.gitlab-ci.yml#L1018
[br]: https://gitlab.haskell.org/Mikolaj/nofib/-/compare/master...make-build-fixes
