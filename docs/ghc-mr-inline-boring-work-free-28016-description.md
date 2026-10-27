# GHC merge request description: an experiment floating out before each simplifier phase, for #28016

Staged 2026-10-27 as the new title and description of GHC [!16870](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16870), after its branch `wip/T28016-inline-boring-work-free` was reset to two commits on master at `a4a3a964b0`, `8301a6d60e` (the test) and `92b13ca7ef` (the change), for GHC [#28016](https://gitlab.haskell.org/ghc/ghc/-/work_items/28016); the title is **Draft: Experiment: float out before each simplifier phase (#28016)**, and the text from "Not for merging" down is the body. It replaces the description posted on 2026-10-26 for commit `06d164e6ca`. Posted 2026-10-27.

Not for merging: an experiment for #28016.

The first commit adds T15519, the example of Note [Honour INLINE on 0-ary bindings] from #15519, which no test covered: the INLINE binding `x = case g a0 b0 of I# r -> T r` is inlined into `f`, and `g a0 b0` must still be computed once, not at every call of `f`. It passes on master.

The second commit changes `GHC.Core.Opt.Pipeline` only. Before each phase of the main simplifier, it runs one simplifier iteration in that phase with case-of-case off, and then a float-out to top level only. A constant that an unfolding first active in that phase exposes when it is inlined, such as the `INLINE [1]` constant `emptyArr` of #28016, is then floated before case-of-case and the `runRW#` rule move the caller's continuation into it, as the gentle run does for the first float-out (Note [Case-of-case and full laziness]). `emptyArr` is still inlined into `f`, as its pragma asks, and that float-out then shares the array.

Until now this MR held another experiment, commit 06d164e6ca: an INLINE binding with no arguments was inlined where `-dinline-check` reports no benefit only if its template is work-free. That fixed `f` of #28016 only because `f`'s use of `emptyArr` has no benefit: in `fc n = case emptyArr of Arr a -> R n (Arr a)` the array was still built at every call, and T15519 fails with it, printing `g` once for each of the three calls of `f`.

Measured locally, with compilers built from master at a4a3a964b0 (flavour `default+no_profiled_libs+no_dynamic_libs`); the rows for #28016 are per call, as in its description, and T15578 is compiled at `-O2`:

```
                                    master   06d164e6ca      this MR
#28016 f, bytes a call                64.0         40.0         40.0
#28016 fc, bytes a call                 64           64           40
#28016 pad, instructions a call      162.0        162.0         93.0
T15519, runs of g                        1            3            1
T15578, bytes allocated        400,040,464  400,040,464  400,040,464
```

In nofib's Fast mode, against master, over the 109 benchmarks with results under both, `instructions:u` changes by a geomean of -0.54%, allocation by -0.40%, object size by +0.03% and the compiler's allocation by +5.4%. `gc/hash` runs 36% fewer instructions, `real/mkhprog` allocates 9.5% less and `real/infer` 7.3% less; no benchmark rises by more than 2.1% in instructions or 0.2% in allocation. In `perf/compiler`, the compiler's bytes allocated rise by a geomean of 4.2%, up to 30% for T24471.

Nine tests fail locally, on output they pin: T11068 (the same lines in another order), T27296b and rule2 (the dump of every float-out, and the count of simplifier runs), T15445, T21286, T25703a and inline-check (the count or order of rule firings and inlining traces), T26903 (`op` still inlined into `test` and its constant still shared, the floated chain renumbered) and T18401 (one more top-level function); LinearLetRec passes unexpectedly.

In CI ([pipeline 132877][pipeline]), every job that ran the testsuite fails on the same nine tests, and in each LinearLetRec passes unexpectedly; the compiler's allocation rises by a geomean of 3.5% to 3.7%, up to 29% for T24471, and code size changes by a geomean of -0.1% to +0.0%.

[pipeline]: https://gitlab.haskell.org/ghc/ghc/-/pipelines/132877

Generated with [Claude Code](https://claude.com/claude-code)
