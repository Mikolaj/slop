# GHC work item comment: INLINE functions inlined in boring contexts too, measured against the example of #27984 and in the testsuite and nofib

Staged 2026-10-26 as a comment on GHC [#27984](https://gitlab.haskell.org/ghc/ghc/-/work_items/27984), answering Simon Peyton Jones's notes 705599 and 706429; posted that day as note 706529. The text from "I tried" down is the body. The measurements were taken on 2026-10-26 with two compilers built from master at `a4a3a964b0`, one of them with the change, and in CI on the draft merge request GHC [!16866](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16866).

I tried your suggestion, `boring_ok = True` in [`mkInlineUnfoldingWithArity`][make], on master at [a4a3a964b0][base]. I built two compilers from that commit, with and without the change (flavour `default+no_profiled_libs+no_dynamic_libs`), and compared them. The numbers before the CI section are local, each comparing the two compilers directly.

**The example of this ticket does not change.** `./Repro inlb 10000000` allocates 640,058,184 bytes with both compilers. The only INLINE function in it is `sumFromTo`, and its calls inline without the change too: `-dinline-check sumFromTo` gives `some_benefit True` and `ANSWER = YES` for each of its three decisions, because the arguments are not trivial. The boxed loop comes from the inlining of `$wmkInlb` into its wrapper from its INLINABLE unfolding, whose guidance is `UnfIfGoodArgs` and not `UnfWhen`, so `boring_ok` does not apply to it.

**Your example in [this note][n704906] is fixed.** I used `{-# INLINE f #-}` (the note has `{- # INLINE f #-}`, which is a comment), and called `h` through a NOINLINE alias, so that the code compiled for `h` runs. Without the change, `-dinline-check f` gives six refusals in a `BoringCtxt`, `f` is inlined only after worker/wrapper, and `t` takes a boxed `Int`. With the change, `f` is inlined at its first decision, in a `BoringCtxt`, and the loop is `$wt :: Int# -> Int#`. For `h 10000000`:

```
                bytes allocated   instructions:u
without change      160,056,440      105,698,517
with change              56,424       30,663,147
```

**Compile time.** In `perf/compiler`, the compiler's bytes allocated over 101 metrics change by a geomean of +0.12%. The compiler under test is itself built with the change. The changes of 1% or more:

```
T9630 (normal)         716,052,792 ->  785,657,160   +9.7%
T12425 (optasm)         76,039,248 ->   81,064,984   +6.6%
LargeRecord (normal)   910,911,440 ->  943,804,256   +3.6%
T13056 (optasm)        257,316,896 ->  253,623,288   -1.4%
```

Residency changes little: `max_bytes_used` by a geomean of -0.02%, and `peak_megabytes_allocated` by +0.09%, the largest change being T3064's peak, from 36 to 38 MB.

**Code size.** In `perf/size`, 38 tests change by a geomean of -1.4%; the `_so` tests need a dynamically linked GHC, which these builds are not. The changes of 1% or more:

```
parsec_dir       2,288,659 -> 1,429,256   -37.5%
ghc_boot_dir     1,322,948 -> 1,271,682    -3.9%
binary_dir       1,428,200 -> 1,383,512    -3.1%
containers_dir   7,531,658 -> 7,383,018    -2.0%
bytestring_dir   3,359,145 -> 3,395,973    +1.1%
array_dir        1,221,660 -> 1,258,594    +3.0%
```

The stage-2 `ghc` executable goes from 136,714,400 to 136,356,448 bytes (-0.26%).

Local **nofib**, in Fast mode, has results under both compilers for 109 benchmarks; `spectral/secretary`, `real/ben-raytrace`, `real/smallpt`, `gc/gc_bench`, `gc/happy` and `real/eff`'s `CS`, `FS`, `VS` and `VSM` fail under both. The geomeans: `instructions:u` -0.13%, bytes allocated +0.41%, object code size -0.49%, the compiler's bytes allocated -0.41%, and executable size +0.04%, no executable changing by 1% or more. The benchmarks that change by 1% or more in one of the first four:

```
                          allocation  instructions  object size  compiler alloc
gc/constraints                 +0.0%         +0.0%        +1.1%           +0.8%
imaginary/digits-of-e2         +0.0%         -0.3%        +2.4%           +2.5%
imaginary/wheel-sieve2         +0.0%         -0.1%        +2.4%           +1.4%
real/hidden                    +0.0%         -0.0%        +0.1%           -1.1%
real/mkhprog                   -9.5%         -3.8%        -2.2%           +1.5%
real/reptile                   +0.0%         +0.0%        -6.3%           -5.7%
real/scs                       +0.0%         -0.1%        +0.6%           +1.2%
shootout/fasta                 -0.0%         -0.1%        -3.9%           -0.2%
shootout/k-nucleotide          +0.0%         -0.0%        +0.0%           +1.4%
shootout/pidigits              +0.0%         +0.0%        +0.0%           -1.2%
spectral/constraints           +0.0%         +0.0%        +1.1%           +0.8%
spectral/expert                +0.3%         +0.1%        -1.6%           -0.4%
spectral/mandel2               +0.0%         -1.2%        +1.3%           +0.5%
spectral/pretty                +0.0%         +0.3%        +3.3%           +1.7%
spectral/puzzle               +71.1%         -8.3%       -41.5%          -33.2%
```

`spectral/puzzle` has no pragmas and imports only from `base`, so its changes come from INLINE functions in `base`.

**CI**, in the pipeline of !16866, compares with the measurements of a4a3a964b0 itself. The four jobs that collect metrics agree with each other and with the local numbers. The x86_64 Linux column is `x86_64-linux-fedora43-release`, as the default pipeline's other x86_64 Linux job builds a compiler with assertions, for which the testsuite skips the perf tests in this table; Windows runs no `_so` size tests.

```
                               x86_64 Linux  aarch64 Linux  aarch64 macOS x86_64 Windows
compiler alloc, geomean              +0.12%         +0.12%         +0.14%         +0.17%
  T9630                               +9.7%          +9.2%          +9.2%         +10.1%
  T12425                              +6.6%          +6.6%          +6.5%          +6.1%
  LargeRecord                         +3.6%          +3.7%          +3.6%          +3.6%
  T10858                              +1.7%          +1.5%          +1.6%          +1.8%
  T13056                              -1.4%          -1.5%          -1.5%          -1.5%
size, geomean                        -1.70%         -1.89%         -1.78%         -1.28%
  parsec_so                          -46.3%         -42.7%         -44.2%        not run
  parsec_dir                         -31.5%         -36.9%         -33.5%         -32.4%
  array_dir                           +2.3%          +3.9%          +3.0%          +2.6%
haddock.Cabal allocation              +4.5%          +4.8%          +4.8%          +4.9%
haddock.base allocation               +2.1%          +2.4%          +2.4%          +2.4%
haddock.compiler allocation           +0.9%          +1.1%          +1.1%          +1.1%
```

Each of these jobs fails on the same five tests: the stat failures T9630 and T12425, and three changed outputs. T22375 and T22375DataFamily dump an unfolding whose guidance now says `boring_ok=True`, and T12603's dump names a binder `ww2` where it said `v`, the constant still floated to top level. The job with assertions fails on the same three outputs only.

[make]: https://gitlab.haskell.org/ghc/ghc/-/blob/a4a3a964b00f2e73b71592161fe7e2a1043d0ed3/compiler/GHC/Core/Unfold/Make.hs#L157-170
[base]: https://gitlab.haskell.org/ghc/ghc/-/commit/a4a3a964b00f2e73b71592161fe7e2a1043d0ed3
[n704906]: https://gitlab.haskell.org/ghc/ghc/-/work_items/27984#note_704906
