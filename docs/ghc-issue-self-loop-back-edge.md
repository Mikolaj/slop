# GHC issue: a self loop counts as a back edge only on a leaf of the dominator tree, so code after an x86 compare-and-swap loop gets frequency 0

Filed as GHC [#28093](https://gitlab.haskell.org/ghc/ghc/-/work_items/28093) on 2026-11-06, at sjakobi's request on GHC [!16269](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16269) ([note 709614](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16269#note_709614)): "IMHO, to make this somewhat traceable and comprehensible, it would be good to have a proper bug report that lays out the problem. Maybe you could file one?!" This file stays as the filed record, the text from "## Summary" down being the filed body, in the tracker's bug template. Title: **NCG: a self loop counts as a back edge only on a leaf of the dominator tree, so code after an x86 compare-and-swap loop gets frequency 0**. Verified 2026-11-06 on x86-64 Linux by `-ddump-cfg-weights`, with stage-1 compilers built from master `37ad471050`, which the links pin, and from the tip `fec02739bf` of GHC [!16891](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16891); the retry loop of GHC [!16535](https://gitlab.haskell.org/ghc/ghc/-/merge_requests/16535) read at its head `7bd9789c46`, and `selfloop_weights.cmm` at !16269's head `036497527e`. A tracker search of 2026-11-05 for "self-loop", "self loop", "selfloop" and "cmpxchg weight" found no report.

## Summary

`loopInfo` takes an edge for a back edge where its target dominates its source, by the sets `mkDomMap` builds ([CFG.hs, lines 852-856][back]). A set holds the block's own label only where the block is a leaf of the dominator tree ([CFG.hs, lines 887-898][dom]), so a self edge is a back edge only on a leaf. On a block that dominates another block, the self edge is no back edge. `calcFreqs` then takes the block for irreducible, the self edge coming from a predecessor that is neither visited nor a back edge, and leaves its frequency at 0 ([CFG.hs, lines 1262-1269][irr]). Every block it dominates, and their edges, get frequency 0 as well, the back edge of a loop around them included.

On x86-64 this happens in ordinary code. `cmpxchg_code` emulates the atomic and, nand, or and xor operations with a compare-and-swap loop, turning A -> B into A -> A' -> A'' -> B with a self loop of weight 0 on A' ([X86/CodeGen.hs, lines 6304-6316][cas]). A' dominates A'', so it is never a leaf, and A'' and every block A' dominates get frequency 0. At -O1 and -O2, `-fcmm-static-pred` replaces the edge weights by these frequencies before block layout, which builds its chains in the order of the weights.

The measured effect on generated code is small. Against its parent on x86-64, the commit of !16891 that fixes this (below) leaves unchanged the assembly of perf/compiler's T3294, T12707, T783 and T9961 at -O0 and -O and the objects of nofib's programs at -O2, changes of containers' objects only graph-benchmarks' Main, and moves no benchmark of containers, vector or megaparsec beyond its noise.

## Steps to reproduce

On x86-64, with `selfloop_weights.cmm` from !16269:

```
#include "Cmm.h"

// S is a self-loop. The entry does work, so it isn't merged into S.
// Expected: the self edge outweighs the exit edge. Without loop detection
// both get weight 0.
stg_self {
  R1 = R1 + 1;
  goto S;
S:
  R1 = R1 - 1;
  if (R1 > 0) { goto S; }
  jump stg_self [R1];
}
```

```
ghc -O -c selfloop_weights.cmm -ddump-cfg-weights
```

The final weights:

```
stg_self:
digraph {
	c1 -> c1[label="0.00000",weight="0.00000"];
	c1 -> c4[label="0.00000",weight="0.00000"];
	c5 -> c1[label="1.00000",weight="1.00000"];
}
```

`c1` is `S`, which dominates `c4`, the block of `jump stg_self`. `c5` enters `S` once per call, and both edges out of `S` weigh 0.

A Haskell loop around `fetchOrIntArray#`, which sums its old values:

```haskell
{-# LANGUAGE MagicHash, UnboxedTuples #-}
module A (orAll) where
import GHC.Exts
import GHC.IO

-- a loop around fetchOrIntArray#, whose old value it sums
orAll :: MutableByteArray# RealWorld -> Int -> IO Int
orAll mba (I# n) = IO (\s -> go 0# 0# s)
  where
    go i acc s
      | isTrue# (i >=# n) = (# s, I# acc #)
      | otherwise = case fetchOrIntArray# mba 0# i s of
          (# s', old #) -> go (i +# 1#) (acc +# old) s'
```

```
ghc -O -c A.hs -ddump-cfg-weights
```

The final weights of `A.orAll1_entry` (block names may differ):

```
A.orAll1_entry:
digraph {
	n4 -> n4[label="0.00000",weight="0.00000"];
	n4 -> n5[label="0.00000",weight="0.00000"];
	n5 -> n9[label="0.00000",weight="0.00000"];
	n9 -> czs[label="0.00000",weight="0.00000"];
	czv -> czD[label="0.18750",weight="0.18750"];
	czj -> czk[label="0.25000",weight="0.25000"];
	czr -> n8[label="0.25000",weight="0.25000"];
	czs -> czw[label="0.25000",weight="0.25000"];
	czw -> czr[label="0.25000",weight="0.25000"];
	n8 -> czs[label="0.25000",weight="0.25000"];
	czl -> czg[label="0.28846",weight="0.28846"];
	czh -> czg[label="0.46154",weight="0.46154"];
	czl -> czh[label="0.46154",weight="0.46154"];
	czv -> czE[label="0.56250",weight="0.56250"];
	czE -> n4[label="0.56250",weight="0.56250"];
	czg -> czs[label="0.75000",weight="0.75000"];
	czj -> czl[label="0.75000",weight="0.75000"];
	czs -> czv[label="0.75000",weight="0.75000"];
}
```

`czs` is the loop head, which holds the heap check; `czv` tests `i < n`; `czE` runs the atomic operation; `n4` is A' and `n5` is A''; `n9`, which the register allocator inserts, jumps from `n5` back to `czs`; and `czw`, `czr` and `n8` are the way back to `czs` through the GC when the heap check fails. `czE` passes 0.5625 per call to `n4`, and `n4` passes on 0. The loop's back edge through the atomic operation, `n9 -> czs`, weighs 0, and the one through the GC, `n8 -> czs`, 0.25.

## Expected behavior

A self edge is a back edge wherever its block is in the dominator tree, so that A' and the blocks it dominates get the frequencies of the code around them: in the second example, `n4 -> n5` carries what `czE -> n4` carries, and the back edge through the atomic operation outweighs the one through the GC.

## Fixes under review

!16269's first commit, "NCG: Rewrite loopInfo.mkDomMap", makes each block's set hold the block's own label and the entry's, which makes every self edge a back edge; the first example is its test `selfloop_weights`. With it, the rule in `staticBranchPrediction` that gives the back edges of a block with other successors a probability of 0.875 between them ([CFG.hs, lines 1042-1052][mix]) predicts the retry to repeat 7 times in 8, overriding the weight 0 that `cmpxchg_code` gives it. That multiplies the frequency of A' alone by 8, its exit edge keeping its frequency, and changes no generated code, block layout skipping self edges.

!16891's "Count self loops as loops in static branch prediction" makes the same change to the sets, leaving the entry out, and gives the retry edge a `TransitionSource` of its own, `AsmCodeGenRetry`, which that rule leaves out, so that the retry keeps weight 0. At !16891's tip, in the second example, the retry edge weighs 0 and the back edge through the atomic operation 3.00075.

!16535 builds the edges of the same compare-and-swap loop with `continueInNewBlock` and a new `addColdSelfLoop`, which keeps the retry at weight 0.

#28083 is the other gap in the same sets: the entry's label is in none of them, so loops headed by the entry are missed.

## Environment

* GHC version used: master at 37ad471050 (10.1.20261103)

Optional:

* Operating System: Linux
* System Architecture: x86_64

[back]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/CFG.hs#L852-856
[dom]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/CFG.hs#L887-898
[irr]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/CFG.hs#L1262-1269
[mix]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/CFG.hs#L1042-1052
[cas]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L6304-6316

/label ~"T::bug"
/label ~"NCG backend"
/label ~"runtime perf"
/label ~"llm-derived::reproducer"
/label ~"needs triage"
