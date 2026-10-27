# GHC work item comment: draft !16870 floats out before each simplifier phase, fixing `f`, `pad` and `fc` of #28016, with its CI and nofib results

Staged 2026-10-27 as a comment on GHC [#28016](https://gitlab.haskell.org/ghc/ghc/-/work_items/28016), following note 706541, which reported the effect of GHC [!16866](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16866) on its repro; posted that day. The text from "Per" down is the body. The local measurements were taken on 2026-10-26 and 2026-10-27 with compilers built from master at `a4a3a964b0`, and the CI results are those of pipeline 132877 of GHC [!16870](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16870) at `92b13ca7ef`.

Per [note 706421][n706421], there is no evident way to float out every constant sub-expression as soon as some inlining exposes it. Draft [!16870][mr] tries doing so once per simplifier phase. Before each phase of the main simplifier, it runs one simplifier iteration in that phase with case-of-case off, and then a float-out to top level only; the change is to `GHC.Core.Opt.Pipeline` alone. A constant that an unfolding first active in that phase exposes, such as the array of `emptyArr`, whose `INLINE [1]` makes it active in phase 1, is then floated before case-of-case and the `runRW#` rule move the caller's continuation into it, as the gentle run does for the first float-out (Note [Case-of-case and full laziness]). `emptyArr` is still inlined into `f`, as its pragma asks, and the float-out then shares the array.

Measured as in the description, with compilers built from master at [a4a3a964b0][base], with `fc n = case emptyArr of Arr a -> R n (Arr a)` added to the repro, and with T15578, the test that Note [Honour INLINE on 0-ary bindings] cites, compiled at `-O2`:

```
                                  master       !16870
f, bytes a call                     64.0         40.0
fc, bytes a call                      64           40
pad, instructions a call           162.0         93.0
T15519, runs of g                      1            1
T15578, bytes allocated      400,040,464  400,040,464
```

So `f` and `fc` allocate as `f0` does, and `pad` runs as `pad0` does, without !16866. T15519 is the example of that Note, from #15519, which the first commit of !16870 adds as a test, since none covered it: the INLINE binding `x = case g a0 b0 of I# r -> T r` is inlined into `f`, called three times, and `g` prints `g` with `trace` each time it runs.

!16870 first held another attempt, commit 06d164e6ca: an INLINE binding with no arguments was inlined where `-dinline-check` reports no benefit only if its template is work-free. That fixed `f` only because `f`'s use of `emptyArr` has no benefit: `fc` still built the array at every call, and T15519 printed `g` three times, `x` being refused twice in a boring context and inlined later as a case scrutinee, so that the final `f` called `$wg` at every call, where master shares that call as a top-level constant. T15519 passes on master and could be merged on its own, whatever becomes of the rest of !16870.

**CI** ([pipeline 132877][pipeline]): each job that ran the testsuite fails on the same nine tests, all on output they pin: T11068 (the same lines in another order), T27296b and rule2 (the dump of every float-out, and the count of simplifier runs), T15445, T21286, T25703a and inline-check (the count or order of rule firings and inlining traces), T26903 (a renumbered chain of floated constants) and T18401 (one more top-level function); and LinearLetRec, marked broken for #18694, passes. `aarch64-darwin-validate` failed fetching the repository, before building. In each job that measures it, the compiler's allocation rises by a geomean of 3.5% to 3.7%, every change of 1% or more being an increase: by 26% to 29% for T24471, and by 19% to 22% for WWRec, T9961, T9675 and `info_table_map_perf`. Code size changes by a geomean of -0.1% to +0.0%, and run-time allocation by a geomean of -0.1% to -0.0%.

**nofib**, in Fast mode, locally, over the 109 benchmarks with results under both compilers: `instructions:u` changes by a geomean of -0.54%, allocation by -0.40%, object size by +0.03% and the compiler's allocation by +5.4%. `gc/hash` runs 36% fewer instructions and allocates 10.3% less, `real/mkhprog` allocates 9.5% less and `real/infer` 7.3% less; no benchmark rises by more than 2.1% in instructions or 0.2% in allocation.

**The compile-time cost** is mostly that of the three extra simplifier iterations, one before each phase; the rest is the three extra float-outs, which dominate in T24471, at 55 MB allocated each against 10 MB for the first float-out. Three ways of cutting it while keeping a float-out before each phase did not pay, measured locally in `perf/compiler`, where !16870 costs 4.2%: making the first float-out also top level only cost 4.16% and moved nofib's allocation by up to 22%; turning off eta-expansion, eta-reduction and let-floating in the extra iterations cost 4.33%; and making the first float-out the one before phase 2 cost 3.64% but made `spectral/mate` allocate 47% more.

[mr]: https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16870
[n706421]: https://gitlab.haskell.org/ghc/ghc/-/work_items/28016#note_706421
[base]: https://gitlab.haskell.org/ghc/ghc/-/commit/a4a3a964b00f2e73b71592161fe7e2a1043d0ed3
[pipeline]: https://gitlab.haskell.org/ghc/ghc/-/pipelines/132877
