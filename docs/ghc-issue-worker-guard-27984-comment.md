# GHC work item comment: a guard that never inlines a worker from its INLINABLE unfolding, measured against the example of #27984, the testsuite and nofib

Staged 2026-10-26 as a comment on GHC [#27984](https://gitlab.haskell.org/ghc/ghc/-/work_items/27984); posted that day as note 706582, without the text in square brackets. The text from "I tried" down is the body. The measurements were taken on 2026-10-26 with two compilers built from master at `a4a3a964b0`, one of them with the diff below, which is not committed.

I tried a broader form of the fix that the description of this ticket suggests: `callSiteInline` never inlines a worker from its INLINABLE unfolding, in its own wrapper or anywhere else. The unfolding stays, so a client can still specialise the worker. I built two compilers from master at [a4a3a964b0][base], with and without this diff (flavour `default+no_profiled_libs+no_dynamic_libs`), and compared them; all numbers are local.

```diff
--- a/compiler/GHC/Core/Opt/Simplify/Inline.hs
+++ b/compiler/GHC/Core/Opt/Simplify/Inline.hs
@@ -104,9 +104,14 @@ callSiteInline env logger id lone_variable arg_infos cont_info
       -- idUnfolding checks for loop-breakers, returning NoUnfolding
       -- Things with an INLINE pragma may have an unfolding *and*
       -- be a loop breaker  (maybe the knot is not yet untied)
-        CoreUnfolding { uf_tmpl = unf_template
-                      , uf_cache = unf_cache
-                      , uf_guidance = guidance }
+        unf@CoreUnfolding { uf_tmpl = unf_template
+                          , uf_cache = unf_cache
+                          , uf_guidance = guidance }
+          -- EXPERIMENT (#27984): never inline a worker from its INLINABLE
+          -- unfolding, which is the source form that worker/wrapper split;
+          -- the unfolding stays for specialisation.
+          | isWorkerLikeId id, isStableUserUnfolding unf
+          -> traceInline logger uf_opts id "Worker with INLINABLE unfolding:" (ppr id) Nothing
           | active_unf -> tryUnfolding env logger id lone_variable
                                     arg_infos cont_info unf_template
                                     unf_cache guidance
```

**The example of this ticket is fixed.** For one run with argument 10000000:

```
                     bytes allocated   instructions:u
master      plain             58,176      160,666,639
master      inlb         640,058,184      375,032,223
with guard  plain             58,176      160,666,638
with guard  inlb              57,880       80,666,011
```

With `-dinline-check '$wmkInlb'`, the guard refuses `$wmkInlb` 12 times, and `mkInlb` stays a wrapper of `$wmkInlb`, whose loop takes `Int#` arguments. `inlb` now runs half the instructions of `plain`: the two loops are the same in Core, but the loop of `mkPlain` checks the heap at each iteration for the `A` and `T` that its exit allocates, while `$wmkInlb` returns an unboxed tuple and checks the heap nowhere.

**Testsuite.** `hadrian/build test` with the guard (the flavour skips the profiled and dynamic ways) gives 11,846 expected passes, 127 expected failures and one unexpected failure, T27626 in the `optasm` way, which is an artifact of an artificial way in which an unrelated property is tested. [T27626 prints 28.0 instead of 38.0. That test makes the two forms of its function disagree on purpose: the rule `"mk" [~1] forall t. mk t = mkFast t` rewrites the right-hand side of the INLINABLE `f` but not its stable unfolding, so 38.0 is what `f 19 12` gives through the unfolding and 28.0 what it gives through the right-hand side. The test raises `-funfolding-use-threshold` to inline the worker's stable unfolding; with the guard the worker is called instead, so the test no longer checks what it was written for in #27626.]

**Compile time and code size**, against master's own run: in `perf/compiler`, the compiler's bytes allocated change by a geomean of -0.01% over 101 metrics, none by 1% or more; in `perf/size`, 38 metrics change by a geomean of +0.00%, none by 1% or more. Residency moves by 1% or more in five metrics, the largest decrease being the `max_bytes_used` of T3064, -5.9%, and the largest increase the `peak_megabytes_allocated` of T10370, from 58 to 60 MB.

**nofib**, in Fast mode, has results under both compilers for 109 benchmarks; `spectral/secretary`, `real/ben-raytrace`, `real/eff`, `real/smallpt`, `gc/gc_bench` and `gc/happy` fail under both. No benchmark changes by 1% or more in allocation, `instructions:u`, object size or the compiler's allocation; the geomeans are +0.00%, -0.01%, +0.00% and -0.01%, and every benchmark's object code has the same total size under both.

[base]: https://gitlab.haskell.org/ghc/ghc/-/commit/a4a3a964b00f2e73b71592161fe7e2a1043d0ed3
