# tasty-papi PR comment: whether running other threads before counting fixes a real problem

Posted 2026-11-02 on [Shimuuar/tasty-papi#7](https://github.com/Shimuuar/tasty-papi/pull/7) ("Run other Haskell threads before counting starts", staged as docs/tasty-papi-pr-settle.md), in reply to [the maintainer's comment](https://github.com/Shimuuar/tasty-papi/pull/7#issuecomment-6571948146) of the same day, which asked whether the change fixes a problem or is overly defensive; this file stays as the record of the comment, the text from "A fair question." down being the body staged for it, one paragraph per line for GitHub. Its figures are those measured for the PR.

A fair question. Measured on containers' benchmarks (14 suites, 1224 benchmarks, five runs each) with GHC master's build and the default RTS options, so neither `-V0` nor GHC #28060's fix is involved:

| | tasty-papi 0.1.2.0 | this change |
|---|---|---|
| benchmarks whose five runs agree within 0.05% | 631 | 1119 |
| a benchmark's highest count minus its lowest, median over the benchmarks | 5511 instructions | 4 instructions |

So under the default options about half of the benchmarks count, in some runs and not in others, work done by other Haskell threads: what the major GC before counting makes runnable, finalizers among it, and tasty's own threads, which run whenever a timer context switch falls inside the counted window. Under `-V0`, where the scheduler switches at every block boundary, that work is most of the count: `union-block_nn` counts 994596 instructions against 142124.

On the parts that may look defensive:

- Collecting again after the yields is needed. A first version that yielded after the GC and then started counting left a spread of about a hundred instructions in most benchmarks (median 87); ending on a GC brought it to 4.
- Looping while `listThreads` and `threadStatus` report a runnable thread, rather than yielding once, was not compared on its own: the loop is what was measured. If a smaller change is preferred, `performMajorGC >> yield >> performMajorGC`, which the PR already uses for base older than 4.18, could be measured the same way.
- The cap of 1000 yields only bounds the wait where some other thread never blocks, which would otherwise keep the benchmark from starting.
