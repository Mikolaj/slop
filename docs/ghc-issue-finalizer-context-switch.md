# GHC issue: finalizers wait for the next context switch, keeping alive what they would free

Filed as GHC [#28060](https://gitlab.haskell.org/ghc/ghc/-/work_items/28060) on 2026-10-30; this file stays as the filed record, the text from "## Summary" down being the filed body, in the tracker's bug template, posted under a preface, which is not carried here. Title: **Finalizers wait for the next context switch, keeping alive what they would free**. Verified on 2026-10-30 with nofib's `real/maillist` at its Norm input, compiled at `-O2` by a stage-1 compiler built from master `5308737363`, on x86-64 Linux, instructions counted by perf (`instructions:u`); the cited RTS files are the same at `3d326d7d28`, which the links pin, as at `5308737363`. The proposed fix is the commit on the local branch `wip/rts-prompt-finalizers` of `~/slop/ghc`. A tracker search of 2026-10-30 found no report.

## Summary

`scheduleFinalizers` passes the thread that runs a GC's finalizers to `scheduleThread(cap,t)` ([Weak.c, line 179][fin]), which puts it at the end of the run queue with `appendToRunQueue` ([Schedule.c, lines 2626-2631][sched]), and `scheduleHandleHeapOverflow` puts the thread whose heap overflow caused the GC back at its front unless a context switch is pending ([Schedule.c, lines 1132-1144][overflow]). So under the RTS timer the finalizers run only at the next context switch, 20 ms later by default (`-C`), and whatever they would free stays live until then. Under `-V0`, and under `-C0`, the context-switch tick count `ctxtSwitchTicks` is 0 ([RtsFlags.c, lines 1959-1965][ticks]) and the scheduler sets `context_switch` whenever another thread is runnable ([Schedule.c, lines 415-423][c0]), so there the finalizers run at the next block boundary.

A program that opens and closes handles quickly therefore keeps every closed handle's buffers live in the meantime, a `Handle__`'s memory going only when its finalizer runs.

### Proposed fix

Request a context switch when scheduling the finalizers, after `scheduleThread(cap,t)` in `scheduleFinalizers`:

```c
    RELAXED_STORE(&cap->context_switch, 1);
```

With it, `maillist` below keeps 1.65 MB under the default options and runs 13% fewer instructions, its runs agreeing to within 7K instructions. Over the rest of nofib at `-O2`, no program's instructions move by 0.2% but `cacheprof`'s, which rise 1.3%, as they do under `-V0`. GHC's testsuite gives the same results with it as without.

## Steps to reproduce

nofib's `real/maillist` writes its output with `appendFile`, a line at a time. In its directory:

```
ghc -O2 -rtsopts Main.hs -o maillist
perf stat -e instructions:u ./maillist runtime_files/norm +RTS -s -RTS
perf stat -e instructions:u ./maillist runtime_files/norm +RTS -s -V0 -RTS
```

It allocates the same 3.27 GB and runs 648 GCs under the default RTS options and under `-V0`, but:

| RTS options | peak residency | major GCs | instructions |
|---|---|---|---|
| default | 18.1 MB | 84 .. 90 | 2410M .. 2420M |
| `-V0` | 1.65 MB | 324 | 2071M |

At the peak under the default options, `+RTS -hT` shows 16.7 MB of `ARR_WORDS` and 292 KB of `Handle__`, against 1.45 MB and 25 KB under `-V0`. Every tick interval from `-V0.001` to `-V1` gives a peak of 16.6 MB to 19.6 MB; `-V0.01 -C0` gives 1.65 MB, and `-V0.01 -C1` 360 MB with 11 major GCs.

The timing dependence also makes the program's instruction count vary from run to run under the default options, by about 1%, where under `-V0` its runs agree to a thousand instructions.

## Expected behavior

A GC's finalizers run soon after it, whatever the timer settings, so that `maillist` keeps under the default options the 1.65 MB it keeps under `-V0`.

## Environment

* GHC version used: master at 5308737363 (10.1.20261028)

Optional:

* Operating System: Linux
* System Architecture: x86_64

[fin]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/Weak.c#L179
[sched]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/Schedule.c#L2626-2631
[overflow]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/Schedule.c#L1132-1144
[ticks]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/RtsFlags.c#L1959-1965
[c0]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/Schedule.c#L415-423

/label ~"T::bug"
/label ~"RTS"
/label ~"space leak"
/label ~"needs triage"
