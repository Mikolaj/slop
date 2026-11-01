# nofib merge request description: build six programs with GHC master, which rejects a non-canonical return

Staged 2026-11-01 as the description of a merge request into nofib's master, from the branch `noncanonical-return` of Mikolaj/nofib, one commit on `d4750745`, `3e47a18`, pushed 2026-11-01; opened 2026-11-01 as nofib [!85](https://gitlab.haskell.org/ghc/nofib/-/merge_requests/85), the body below under a preface of Mikolaj's, this file staying as the record of the staged text. The title is the commit's subject, **Build with GHC master: drop non-canonical return definitions**, and its message:

    Build with GHC master: drop non-canonical return definitions

    ghc/ghc!15795 (CLC proposal 328) makes a definition of return other
    than pure, or of pure as return, an error (GHC-22705), so real/eff's CS,
    FS, VS and VSM, gc/happy and parallel/gray no longer compile with GHC
    master. Each removed return is the same as its instance's pure,
    and gc/happy's becomes pure's definition.

    Assisted-by: Claude Opus 5.5

The body, as it would be posted, follows.

Since ghc/ghc!15795 (CLC proposal [328][clc328]), GHC master rejects a definition of `return` other than `return = pure`, and a definition of `pure` as `return`, with error GHC-22705. Six programs have one and no longer compile: real/eff's CS, FS, VS and VSM, gc/happy and parallel/gray.

This removes each such `return`, with its `INLINE` pragma where it has one, so that `return` takes the class default, `pure`; in gc/happy, `return`'s definition becomes `pure`'s. Each removed `return` is the same as its instance's `pure`, so no program's behaviour changes.

Checked with GHC master at ghc/ghc@5308737363 under the make build: all six fail to compile before and build after, and real/eff's programs, parallel/gray and gc/happy, at its Norm size, match their expected output. The canonical definitions left, `return = pure` (spectral/dom-lt, parallel/gray, ben-raytrace's `SamplerMonad.Unboxed`) and `mappend = (<>)` (shootout/fannkuch-redux), are only warnings under that change.

[clc328]: https://github.com/haskell/core-libraries-committee/issues/328
