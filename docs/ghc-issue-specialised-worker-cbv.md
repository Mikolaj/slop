# GHC issue: the specialisation of an imported worker is not call-by-value, so it evaluates the arguments the worker takes evaluated

Staged and filed 2026-10-22 as [GHC work item 28015](https://gitlab.haskell.org/ghc/ghc/-/work_items/28015); this file stays as the filed record, the text from "## Summary" down being the filed body, in the tracker's bug template. Title: **The specialisation of an imported worker is not call-by-value, so it evaluates the arguments that the worker takes evaluated**. Every command in it was run as printed on 2026-10-22 with GHC HEAD 10.1.20261019 (`merged-mrs`: master 3d326d7d28 with MRs and fixes), and the reproducer gives the same two evaluations with 9.6.7, 9.8.4, 9.10.3, 9.12.4 and 9.14.1. Found in orthotope's specialisation benchmark, where the benchmark's specialisation of Dynamic `rotate`'s worker evaluates three arguments from strict fields at every call and the library's worker evaluates none. The tracker search of 2026-10-22 ("CBV specialis", "call-by-value specialis", "cbv marks", "CbvMark", "StrWork", "specialisation worker evaluated", "specialised worker eval", "tag inference specialis", "strict field argument eval") found no report; GHC [#27874](https://gitlab.haskell.org/ghc/ghc/-/work_items/27874) is a different interaction of a call-by-value worker with the specialiser. Code read at master 3d326d7d28.

## Summary

When worker/wrapper unpacks a constructor with strict fields, it passes the strict fields to the worker and puts an "extra eval" of each one it passes boxed at the top of the worker ([`mkStrictFieldSeqs`][seqs]). The worker is call-by-value in these arguments, so the code generator discards the extra evals (Note [Call-by-value for worker args], [GHC.Core.Utils][cbvnote]).

When another module specialises the imported worker, the specialisation is an ordinary function. Note [Transfer IdDetails during specialisation] ([GHC.Core.Opt.Specialise][transfer]) says: "We must keep them as VanillaIds because WW will detect them as WorkerLikeIds again". Tidy gives call-by-value marks only to worker-like Ids and join points ([`computeCbvInfo`][cbvinfo]). If worker/wrapper does not split the specialisation again, as in the reproducer below, the extra evals stay, and the code generator compiles each one: a return frame, a tag test and a branch, at every call. In the reproducer, the specialisation's only caller takes the arguments out of the strict fields of `A`, so the evaluations always find them evaluated.

## Steps to reproduce

`ReproLib.hs`:

```haskell
module ReproLib (C (..), A (..), f, k) where

class C a where
  m :: a -> Int -> Int

data A a = A ![Int] !a

f :: C a => Int -> A a -> [(Int, a)]
f d (A s x)
  | d >= length s = []
  | otherwise = [ (m x i, x) | i <- [0 .. d] ]
{-# INLINABLE f #-}

k :: C a => Int -> A a -> [(Int, a)]
k d a = f (d + 1) a
```

`Repro.hs`:

```haskell
module Repro (g) where

import ReproLib

instance C Bool where
  m b i = if b then i else 0

g :: Int -> A Bool -> [(Int, Bool)]
g = k
```

`k` is small, so its unfolding is its optimised right-hand side, which calls `f`'s worker `$wf`, and `Repro` specialises `$wf`.

`ghc -O -ddump-simpl -dsuppress-all -dsuppress-uniques -ddump-asm -ddump-to-file Repro.hs` compiles both modules. `ghc --show-iface ReproLib.hi` shows the worker call-by-value in `s` and `x`:

```
  $wf ::
    C a =>
    GHC.Internal.Prim.Int#
    -> [GHC.Internal.Types.Int] -> a -> [(GHC.Internal.Types.Int, a)]
  StrWork([~, ~, !, !])
```

`Repro.dump-simpl` has the rule and the specialisation, with the extra evals of both fields at its top:

```
"SPEC/Repro $wf @Bool" [2] forall $dC. $wf $dC = $s$wf

$s$wf
  = \ ww ww1 ww2 ->
      case ww1 of ww3 { __DEFAULT ->
      case ww2 of ww4 { __DEFAULT ->
      case $wlenAcc ww3 0# of ww7 { __DEFAULT ->
```

In `Repro.dump-asm` (assembler directives dropped), `$s$wf` evaluates both before it calls `$wlenAcc`:

```
$s$wf_info:
.Lc16Q:
	leaq -24(%rbp),%rax
	cmpq %r15,%rax
	jb .Lc16R
.Lc16S:
	movq $.Lblock_info,-24(%rbp)
	movq %rsi,%rbx
	movq %r14,-16(%rbp)
	movq %rdi,-8(%rbp)
	addq $-24,%rbp
	testb $7,%bl
	jne .Lc15G
.Lc15H:
	movq (%rbx),%rax
	jmp *%rax
.Lblock_info:
.Lc15G:
	movq $.Lblock_info,(%rbp)
	movq %rbx,%rax
	movq 16(%rbp),%rbx
	movq %rax,16(%rbp)
	testb $7,%bl
	jne .Lc15L
.Lc15M:
	movq (%rbx),%rax
	jmp *%rax
.Lblock_info:
.Lc15L:
	movq $.Lblock_info,(%rbp)
	xorl %esi,%esi
	movq 16(%rbp),%r14
	movq %rbx,16(%rbp)
	jmp $wlenAcc_info
```

In `ReproLib.dump-asm` (likewise), `$wf` calls `$wlenAcc` with no evaluation:

```
$wf_info:
.Lc123:
	leaq -32(%rbp),%rax
	cmpq %r15,%rax
	jb .Lc124
.Lc125:
	movq $.Lblock_info,-32(%rbp)
	movq %rsi,%rax
	xorl %esi,%esi
	movq %r14,%rbx
	movq %rdi,%r14
	movq %rbx,-24(%rbp)
	movq %rax,-16(%rbp)
	movq %r8,-8(%rbp)
	addq $-32,%rbp
	jmp $wlenAcc_info
```

With both arguments evaluated, `$s$wf` runs 21 instructions to the call and `$wf` 13.

## Expected behavior

The specialisation takes as evaluated the arguments that the worker takes call-by-value, and does not evaluate them.

## Environment

- GHC 9.6.7, 9.8.4, 9.10.3, 9.12.4, 9.14.1 and a HEAD build (master 3d326d7d28 with some MRs), at `-O`.
- x86-64 Linux.

[seqs]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Utils.hs#L3389-3403
[cbvnote]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Utils.hs#L3276-3299
[transfer]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Opt/Specialise.hs#L1843-1868
[cbvinfo]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Core/Tidy.hs#L129-136

/label ~"T::bug"

/label ~"needs triage"
