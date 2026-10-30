# tasty-papi PR: run other Haskell threads before counting starts

Filed as [Shimuuar/tasty-papi#7](https://github.com/Shimuuar/tasty-papi/pull/7) on 2026-10-30, against its master c13ea0c (0.1.2.0); the change is the diff at the end, committed as 2838ef4 on the branch `settle-before-counting` of the fork Mikolaj/tasty-papi. The text from "## Problem" down to the reference links is the filed body, posted under a preface, which is not carried here. Title: **Run other Haskell threads before counting starts**. Its branch for base 4.18 and later is the code measured below (builds of GHC's master and of GHC !16891 on x86-64 Linux, containers-tests at 953428ad07); the branch for older base was not compiled here, no GHC older than 9.6 being installed. With GHC 9.6.7 and 9.14.1 the package builds with no warning in its own module and its tests pass; `cabal check` warns only about the `.cabal` file, which the change does not touch.

## Problem

In the non-threaded RTS every Haskell thread runs on one OS thread, and PAPI counts that thread's instructions between `PAPI_start` and `PAPI_stop`, so a benchmark's count includes the work of any other Haskell thread the scheduler runs in that window. Two cases make one run there:

- The `performMajorGC` before the measurement can find finalizers to run. Their thread then waits in the run queue for the next context switch: under the RTS timer usually after the measured call, but with a GHC that requests a context switch when it schedules finalizers, as the fix of GHC [#28060][28060] does, at the first block boundary inside the window.
- Under `+RTS -V0` the scheduler switches at every block boundary while another thread is runnable, so the work tasty's own threads have pending runs inside the window too.

## Example

containers' `set-operations-intset` benchmark `union-block_nn`, which allocates 79392 bytes in every run; instructions, the lowest of three or five runs, the whole suite in one process or the benchmark alone:

| GHC | RTS options | tasty-papi | in the suite | alone |
|---|---|---|---|---|
| master | default | 0.1.2.0 | 142124 | 142124 |
| master | `-V0` | 0.1.2.0 | 994596 | |
| with GHC #28060's fix | default | 0.1.2.0 | 145087 .. 151337 | 140582 |
| master | default | this change | 142079 | |
| master | `-V0` | this change | 142912 | |
| with GHC #28060's fix | default | this change | 140537 | |

Over the suite's 88 benchmarks, the build with the fix counts 1.98% fewer instructions than master's in geometric mean with tasty-papi 0.1.2.0 and 2.01% fewer with this change, `union-block_nn`'s rise of up to 6.5% gone. Over containers' 14 benchmark suites, 1224 benchmarks run five times each, the benchmarks whose runs agree within 0.05% are 631 with tasty-papi 0.1.2.0 and 1119 with this change, for master's build.

## The change

In place of the `performMajorGC` before counting, `settle` runs the major GC, and while another thread is runnable, as `listThreads` and `threadStatus` report, yields until none is and runs the GC again, at most 1000 yields in all. Counting still starts right after a GC: yielding after the GC instead left counts varying by about a hundred instructions from run to run. With base older than 4.18, which has no `listThreads`, `settle` collects, yields once and collects again. Under `-V0` some benchmarks still count more than under the default options, which this change does not address: in `set-operations-intset`, master's build counts more in four of the 88 by more than 1%, by 4.3% at most.

[28060]: https://gitlab.haskell.org/ghc/ghc/-/work_items/28060

## The diff (not part of the body)

```diff
diff --git a/Changelog.md b/Changelog.md
index c4b954c..7427906 100644
--- a/Changelog.md
+++ b/Changelog.md
@@ -1,3 +1,10 @@
+* Unreleased
+
+  - Other Haskell threads, such as the finalizers that the major GC before
+    a measurement schedules, run before counting starts rather than inside
+    the counted region, where PAPI counted their work as the benchmark's.
+
+
 * Changes in 0.1.2.0
 
   - `benchIngredients`, `consoleBenchReporter`, `csvReporter` are exported.
diff --git a/Test/Tasty/PAPI.hs b/Test/Tasty/PAPI.hs
index a172b81..c03a65f 100644
--- a/Test/Tasty/PAPI.hs
+++ b/Test/Tasty/PAPI.hs
@@ -1,4 +1,5 @@
 {-# LANGUAGE CApiFFI                    #-}
+{-# LANGUAGE CPP                        #-}
 {-# LANGUAGE FlexibleInstances          #-}
 {-# LANGUAGE ForeignFunctionInterface   #-}
 {-# LANGUAGE GeneralizedNewtypeDeriving #-}
@@ -94,6 +95,12 @@ import Control.Exception
 import Control.Monad
 import Control.DeepSeq
 import Control.Concurrent.STM
+import Control.Concurrent (yield)
+#if MIN_VERSION_base(4,18,0)
+import Control.Concurrent (myThreadId)
+import GHC.Conc (ThreadStatus(..), threadStatus)
+import GHC.Conc.Sync (listThreads)
+#endif
 import Data.List       (nub, intercalate)
 import Data.Proxy
 import Data.Foldable
@@ -569,7 +576,12 @@ instance IsTest Benchmarkable where
             -- just because previous benchmarks allocated enough to
             -- trigger it. This could bias measurement a lot since we
             -- run bencmark only once
-            performMajorGC
+            --
+            -- In the non-threaded RTS every Haskell thread runs on this OS
+            -- thread, so PAPI counts whatever runs between start and stop:
+            -- let the finalizers the GC schedules, and any other thread
+            -- with work pending, run before counting.
+            settle
             n1 <- getAllocationCounter
             -- Perform measurement
             call "Failed to start measurements" $ papi_start evt
@@ -593,6 +605,32 @@ instance IsTest Benchmarkable where
       n_threads = getNumThreads $ lookupOption opts
       counters  = getCounterSet $ lookupOption opts
 
+-- | Run a major GC, and while another Haskell thread is runnable, yield until
+--   none is and run the GC again, yielding at most 1000 times in all, so
+--   that counting starts right after a GC, whatever ran before it.  Before
+--   base 4.18, which has no 'listThreads': collect, yield once and collect.
+settle :: IO ()
+#if MIN_VERSION_base(4,18,0)
+settle = do
+  me <- myThreadId
+  let busy = do
+        ts <- listThreads
+        st <- mapM threadStatus (filter (/= me) ts)
+        pure (ThreadRunning `elem` st)
+      drain :: Int -> IO Int
+      drain k = do
+        b <- busy
+        if b && k > 0 then yield >> drain (k - 1) else pure k
+      loop :: Int -> IO ()
+      loop k = do
+        performMajorGC
+        b <- busy
+        when (b && k > 0) $ yield >> drain (k - 1) >>= loop
+  loop 1000
+#else
+settle = performMajorGC >> yield >> performMajorGC
+#endif
+
 showN :: CLLong -> String
 showN n
   | x < 1e4 = show n
```
