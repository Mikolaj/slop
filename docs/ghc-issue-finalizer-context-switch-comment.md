# GHC issue comment: why the fix for #28060 requests a context switch rather than putting the finalizer thread at the front of the run queue

Posted on 2026-11-16 as the answer to Duncan Coutts's [note 712168](https://gitlab.haskell.org/ghc/ghc/-/work_items/28060#note_712168) on GHC [#28060](https://gitlab.haskell.org/ghc/ghc/-/work_items/28060), under a preface naming Claude as its author; the text from "The front of the run queue" down is the body. Its claims are read from the RTS at master 13408a2b59, which its links pin; the front-of-queue form it discusses was measured on maillist and after a `performMajorGC` on 2026-11-16, in the non-threaded RTS only.

The front of the run queue was not weighed when the issue was written: the flag was copied from [the mechanism `-V0` uses][c0], where the effect was found. Weighed now, the flag does work the front form does not.

On the scheduler's own path, a GC on heap overflow, the front form is the narrower change, master's own [`scheduleThreadNow`][now] in place of `scheduleThread(cap,t)` in [`scheduleFinalizers`][fin], with no flag. The finalizer thread then runs first after the GC, and no other thread yields or loses its place. The flag instead makes the running thread yield at its next block boundary ([heap check][yield]), and [`scheduleHandleYield`][append] then appends it behind every runnable thread. On `maillist` both forms give 1.65 MB peak residency and 324 major GCs, the front form 0.03% fewer instructions.

After an explicit GC from `System.Mem`, in the non-threaded RTS, the front form is as late as no fix. Its [`performGC`, `performMajorGC` and `performMinorGC`][mem] are safe foreign calls: [`performGC_`][pgc] runs the GC and releases the capability, and [`resumeThread`][resume] puts the caller straight back on it, bypassing the run queue. A finalizer thread at the front then waits for the next context switch the timer requests: until then, each heap overflow of the caller puts it back in front. Counting allocating loop iterations from a `performMajorGC` that finds one dead weak pointer to the run of its finalizer gives 129 every time with the flag, 3.7M to 8.6M with the front form and 4.1M to 8.5M with no fix. Harnesses that call `performGC` before measuring take this path.

As to the second question: the flag was copied, not chosen, and it happens to cover the case the front form misses.

Not measured: the threaded RTS, programs with other runnable threads, and the front form on nofib beyond `maillist`.

[c0]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/rts/Schedule.c#L419-423
[now]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/rts/Schedule.c#L2633-2639
[fin]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/rts/Weak.c#L179
[yield]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/rts/HeapStackCheck.cmm#L135-144
[append]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/rts/Schedule.c#L1218-1252
[mem]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/libraries/ghc-internal/src/GHC/Internal/System/Mem.hs#L36-54
[pgc]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/rts/Schedule.c#L2850-2867
[resume]: https://gitlab.haskell.org/ghc/ghc/-/blob/13408a2b593d9c1831ea82faf2f5321d4b7215d8/rts/Schedule.c#L2539-2613
