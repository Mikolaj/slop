# GHC issue: i386 NCG: a SIMD operation whose two operands each contain a 64-bit shift puts the CFG out of step with the code and panics; and three sentences of Note [Updating the CFG during CodeGen] that the code contradicts

Filed as GHC [#28179](https://gitlab.haskell.org/ghc/ghc/-/work_items/28179) on 2026-11-24. The text from "## Summary" down is the body as drafted for filing, in the tracker's bug template, under a preface of Mikolaj's naming Claude as its author, which is not carried here. Title as drafted, its length and the labels left to him: **i386 NCG: a SIMD operation whose two operands each contain a 64-bit shift puts the CFG out of step with the code and panics; and three sentences of Note [Updating the CFG during CodeGen] that the code contradicts**. The body rests on a reading of master 56bb91d95f's code (2026-11-24) and on runs on 2026-11-24 of a stage-1 compiler built from master 56bb91d95f plus commits that change only comments (its code, Haskell comments stripped, identical to 56bb91d95f's), given an i386 target description through `-B` as the Environment section says; no i386 compiler was run, nothing was assembled, linked or run, and `T_vecorder.hs` as an i386 user would write it was never compiled. The reproducers in the body are the files run, less their comment lines. The fix the body suggests was not built or tested. The links pin 56bb91d95f. Tracker search 2026-11-24, issues and merge requests, all states, for `vector_op_sse_reg`, "cfg nodes don't match", "Can't find weight for edge", "i386 CFG", "Updating the CFG during CodeGen", `sanityCheckCfg`, "lockstep", `addCondBlock`, "i386 SIMD", "i386 vector", `getNonClobberedAmode` and "unreachable blocks CFG", and the comments of #28127, #28088, #27915, !16535, !16996 and !16891: no report of either part; #28088 is about the unreachable blocks themselves and predates the Note on master.

## Summary

On i386, `vector_op_sse_reg` in `GHC.CmmToAsm.X86.CodeGen` ([lines 1928-1942][opsse]) generates the code of its first operand (`exp1_code <- getAnyReg expr1`) before that of its second (`(reg2, exp2_code) <- getSomeReg expr2`), but emits `exp2_code` first, in both of its cases. Note [Updating the CFG during CodeGen] in `GHC.CmmToAsm.Monad` ([lines 272-321][note]), added by !16535, rules this out: "The order of these monadic actions must match the order of the generated instructions: the CFG updates assume that the instructions of a child expression are placed before the instructions of its parent. Code that emits the instructions of two children in the reverse order of their generation breaks this assumption."

The order matters where an operand's code splits the current block. On i386, which keeps a CFG since f59fb957e3 ("x86 ncg: Maintain the CFG on i386", from !16535), a 64-bit shift does: the `MO_Shl`, `MO_S_Shr` and `MO_U_Shr` cases of `iselExpr64` end the current block with a conditional jump and call `addCondBlock` ([lines 703-727][shl] for `MO_Shl`), and a 32-bit expression reaches them through a narrowing `MO_SS_Conv W64 W32` or `MO_UU_Conv W64 W32` of a shift ([lines 877-885][narrow]), as in the operand of a broadcast ([lines 1405-1411][bcast]). If one operand splits, the splits stay in order; if both do, the CFG records the first operand's split before the second's and the code has them the other way round. Then `sanityCheckCfg` panics ("Block list and cfg nodes don't match") under `-dasm-lint` or in a DEBUG compiler, and otherwise `addNodesBetween` can panic ("Can't find weight for edge that should have one", the message of #27915) where the linear allocator puts a fixup block on an edge of the code that the CFG lacks. Every 128-bit integer vector addition goes through `vector_op_sse_reg` ([line 1558][vadd], with no AVX case), as do the other operations that `vector_op_sse` serves ([line 1921][vecsse]) and the `MOVLHPS`/`MOVHLPS` cases of `vector_shuffle_floatx4_sse` ([lines 2251-2254][movlhps]). On x86-64 only code generated for statements splits a block (`genAtomicRMW`, `genWordToFloat`; `iselExpr64` is i386's), so the reversal is harmless there.

The same reversal, read in the code and not run, is in the second PALIGNR fallback of `vector_shuffle_int128_common` ([lines 2609-2618][palignr]), taken by the 128-bit integer shuffles without SSSE3: it generates `exp1 <- getAnyReg v1` before `exp2 <- getAnyReg v2` and emits `exp2 tmp` first.

A suggestion, not built or tested: swap the two bindings, generating the second operand's code first, in `vector_op_sse_reg` and in that fallback, so that generation follows the order of emission.

Note [Updating the CFG during CodeGen] has three sentences that master's code contradicts (comments of the NCG that the code contradicts are collected in #28127):

- "Thus 'cmmNativeGen' removes the unreachable blocks before it builds the CFG and generates code." It does not (#28088): `cmmToCmm` keeps every block ([GenericOpt.hs, lines 58-62][cmmtocmm]), `getCfg` builds the CFG of the blocks `revPostorder` reaches ([CFG.hs, line 732][getcfg]), `cmmTopCodeGen` generates code for every block ([CodeGen.hs, lines 112-113][topcg]), and only the liveness pass drops the unreachable ones ([Liveness.hs, lines 739-756][liveness]), after instruction selection.
- "A store emits the code of its address before the code of its value, so it takes the address from 'getNonClobberedAmode' (see the Rule of the Game (tm) for Amodes in GHC.CmmToAsm.X86.CodeGen), which stays valid across the value code." `assignMem_IntCode` in its general case ([lines 4059-4076][memint]), `assignMem_FltCode` ([lines 4101-4109][memflt]), `assignMem_VecCode` ([lines 4118-4126][memvec]) and `assignMem_I64Code` ([lines 487-500][mem64]) generate and emit the code of the value first and take the address from `getAmode`, as the Rule of the Game itself says ([lines 397-417][rule]: "The assignMem_* stores do this."); the users of `getNonClobberedAmode` are `getNonClobberedOperand`, `getSimpleAmode` and `genAtomicRMW`.
- "The CFG is checked against the final instruction stream by 'sanityCheckCfg' when assembly linting (-dasm-lint) is enabled." `cmmNativeGen` runs it where `ncgEnableDeadCodeElimination` holds and either `-dasm-lint` is on or the compiler is a DEBUG one ([CmmToAsm.hs, lines 638-643][sanity]), so also in a DEBUG compiler without `-dasm-lint`, and never where the CFG is not kept: `ncgEnableDeadCodeElimination` is false under `-finfo-table-map` and on targets other than x86 and x86-64 ([Config/CmmToAsm.hs, lines 54-57][dce], [BlockLayout.hs, lines 924-928][maintains]).

## Steps to reproduce

As an i386 user would write it, for an i386 compiler at `-O -dasm-lint` (`T_vecorder.hs`, not compiled: no i386 compiler was available):

```haskell
{-# LANGUAGE MagicHash #-}
module T_vecorder (f) where

import GHC.Exts

f :: Int64# -> Int64# -> Int# -> Int# -> Int32X4#
f x y n m =
  plusInt32X4#
    (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftL64# x n))))
    (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftL64# y m))))
```

What was run, through the `-B` route of the Environment section, which can import only `GHC.Prim`: `T_vecorderP.hs`, the same function.

```haskell
{-# LANGUAGE MagicHash, NoImplicitPrelude #-}
module T_vecorderP (f) where

import GHC.Prim

f :: Int64# -> Int64# -> Int# -> Int# -> Int32X4#
f x y n m =
  plusInt32X4#
    (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftL64# x n))))
    (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftL64# y m))))
```

At `-O` both shifts stay inside the operands (`-ddump-opt-cmm`):

```
XMM1 = %MO_V_Add_4_W32(%MO_V_Broadcast_4_W32(%MO_SS_Conv_W64_W32(I64[Sp] << I32[Sp + 16])),
                       %MO_V_Broadcast_4_W32(%MO_SS_Conv_W64_W32(I64[Sp + 8] << I32[Sp + 20])));
```

`ghc -B<lib> -frebindable-known-names -S -O -dasm-lint T_vecorderP.hs` exits 1 with (call stack omitted):

```
ghc: panic! (the 'impossible' happened)
  GHC version 10.1.20261124:
	Block list and cfg nodes don't match
  difference: []
  missing edges: [(cY, n7), (cY, n6), (n7, n3), (n7, n2)]
  stale edges: [(n3, n7), (n3, n6), (cY, n3), (cY, n2)]
  blocks: [cY, n2, n3, n6, n7, na, nb]
  cfg: digraph {
	cY -> n2[label="0.25000",weight="0.25000"];
	n2 -> nb[label="0.25000",weight="0.25000"];
	n3 -> n6[label="0.25000",weight="0.25000"];
	n6 -> na[label="0.25000",weight="0.25000"];
	na -> n7[label="0.25000",weight="0.25000"];
	nb -> n3[label="0.25000",weight="0.25000"];
	cY -> n3[label="0.75000",weight="0.75000"];
	n3 -> n7[label="0.75000",weight="0.75000"];
}

  cfg not in lockstep
```

The CFG has the first operand's shift splitting `cY` into `n2` and `n3`, and the second's splitting `n3` into `n6` and `n7`; the code has the second operand's shift in `cY`, jumping to `n6` and `n7`, and the first's in `n7`, jumping to `n2` and `n3` (`na` and `nb` are fixup blocks of the register allocator). `-O2` and `-O -fregs-graph` give the same missing and stale edges, the entry block being `c10` at `-O2`. These compile: `-O` without `-dasm-lint` (the compiler is not a DEBUG one, so nothing checks the CFG); `-O0 -dasm-lint`, where the shifts stay in local variables; `-O -dasm-lint` with only the first operand shifted (the second `broadcastInt32X4# (intToInt32# (int64ToInt# y))`); and `-O -dasm-lint` for x86-64.

Without `-dasm-lint`, `T_vecloop.hs`, the same addition inside a loop:

```haskell
{-# LANGUAGE MagicHash, NoImplicitPrelude #-}
module T_vecloop (g, h) where

import GHC.Prim

g :: Int# -> Int64# -> Int64# -> Int# -> Int# -> Int32X4# -> Int32X4#
g k x y n m acc = case k of
  0# -> acc
  _  -> g (k -# 1#) (plusInt64# x y) (timesInt64# y x) (n +# 1#) (m -# 1#)
          (plusInt32X4# acc
            (plusInt32X4#
              (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftL64# x n))))
              (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftL64# y m))))))

h :: Int# -> Int64# -> Int64# -> Int64# -> Int# -> Int# -> Int# -> Int32X4# -> Int32X4#
h k x y z n m p acc = case k of
  0# -> acc
  _  -> h (k -# 1#) (plusInt64# x z) (timesInt64# y x) (subInt64# z y) (n +# p) (m -# 1#) (p *# 3#)
          (plusInt32X4# acc
            (plusInt32X4#
              (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftRA64# (plusInt64# x z) n))))
              (broadcastInt32X4# (intToInt32# (int64ToInt# (uncheckedIShiftL64# (subInt64# y z) m))))))
```

`ghc -B<lib> -frebindable-known-names -S -O T_vecloop.hs` exits 1 with (call stack omitted):

```
ghc: panic! (the 'impossible' happened)
  GHC version 10.1.20261124:
	Can't find weight for edge that should have one
  triple (n7, nj, c2z)
  updates [(n7, nj, c2z), (n6, ni, n7), (n9, nh, na)]
  cfg: digraph {
	c2F -> n6[label="300.00000",weight="300.00000"];
	n7 -> n9[label="300.00000",weight="300.00000"];
	c2z -> c2E[label="800.00000",weight="800.00000"];
	c2z -> c2F[label="800.00000",weight="800.00000"];
	c2F -> n7[label="900.00000",weight="900.00000"];
	n7 -> na[label="900.00000",weight="900.00000"];
	c2G -> c2z[label="1000.00000",weight="1000.00000"];
	n6 -> n7[label="1000.00000",weight="1000.00000"];
	n9 -> na[label="1000.00000",weight="1000.00000"];
	na -> c2z[label="1000.00000",weight="1000.00000"];
}
```

The linear allocator put the fixup block `nj` on the loop's back edge, which the code takes from `n7` to the loop head `c2z` and the CFG has from `na`. `-O2` panics the same way; `-O -fregs-graph` compiles.

## Expected behavior

Both files compile at `-O` with `-dasm-lint`, the CFG matching the code; and the Note says what the code does.

## Environment

* GHC version used: master 56bb91d95f's code (built from a branch on it whose commits change only comments), as an x86-64 stage-1 compiler (10.1.20261124) run with `-B<lib>`, `<lib>` a copy of its `lib` directory (symlinks to its entries) whose `targets/default.target` names `ArchX86`, word size 4 and the LLVM target `i386-unknown-linux` (`ghc --info`: target arch ArchX86, word size 4, platform i386-unknown-linux). An x86-64 interface file has another magic number than such a compiler expects, and even `import GHC.Prim` reads ghc-internal's `GHC/Internal/Prim.hi` first, so the copy holds a 32-bit one, compiled from ghc-internal's own source of `GHC.Internal.Prim` with `-this-unit-id ghc-internal` under the i386 description; `-frebindable-known-names` keeps the modules from importing `GHC.Essentials` from base. The compiler binary and its RTS constants stay x86-64's, so code importing base could not be tried and nothing was assembled, linked or run. The failures are in the NCG's CFG handling, which reads the target description, so an i386 compiler is expected to fail the same way.

Optional:

* Operating System: Linux
* System Architecture: x86_64 host, i386 target description

[opsse]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L1928-1942
[note]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/Monad.hs#L272-321
[shl]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L703-727
[narrow]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L877-885
[bcast]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L1405-1411
[vadd]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L1558
[vecsse]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L1921
[movlhps]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L2251-2254
[palignr]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L2609-2618
[cmmtocmm]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/Cmm/GenericOpt.hs#L58-62
[getcfg]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/CFG.hs#L732
[topcg]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L112-113
[liveness]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/Reg/Liveness.hs#L739-756
[memint]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L4059-4076
[memflt]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L4101-4109
[memvec]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L4118-4126
[mem64]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L487-500
[rule]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L397-417
[sanity]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm.hs#L638-643
[dce]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/Driver/Config/CmmToAsm.hs#L54-57
[maintains]: https://gitlab.haskell.org/ghc/ghc/-/blob/56bb91d95f89509cb351a5eb4a7406825675866c/compiler/GHC/CmmToAsm/BlockLayout.hs#L924-928

/label ~"T::bug"
/label ~"NCG backend"
/label ~"i386"
/label ~"llm-derived::reproducer"
/label ~"needs triage"
