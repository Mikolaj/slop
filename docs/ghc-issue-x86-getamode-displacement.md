# GHC issue: x86-64 NCG `getAmode` emits address displacements outside the signed 32-bit range, which the assembler rejects

Filed as GHC [#28105](https://gitlab.haskell.org/ghc/ghc/-/work_items/28105) on 2026-11-09; the text from "## Summary" down is the filed body, in the tracker's bug template. Title: **x86-64 NCG: three clauses of `getAmode` emit a displacement outside the signed 32-bit range, which the assembler rejects**. Verified on 2026-11-09 with a stage-1 build of master 37ad471050 (10.1.20261103), with ghc-9.14.1 and with ghc-9.6.7, from the files and commands as shown here, the output being master's with GHC's temporary directory written as `/tmp/`; the links pin 37ad471050. One issue and not one per clause, because the clauses are in one function and give one symptom, and one file reproduces all three. The `x + ((y << shift) + offset)` and `x - lit` clauses were found while testing changes to x86's `add_int` and `getAmode`, and the `CmmRegOff` clause by reading the clauses beside them. Tracker search 2026-11-09, issues and merge requests, for `getAmode`, `is32BitInteger`, `is32BitLit`, `x86_complex_amode`, `mangleIndexTree`, "displacement", "32bit displacement", "out of range" and "relocation out of range": no issue or MR about these clauses.

## Summary

Three clauses of `getAmode` in `GHC.CmmToAsm.X86.CodeGen` can build an address whose displacement is outside the signed 32-bit range, which an x86-64 address with a base register cannot encode, so the assembler rejects the module. Haskell source reaches two of them at `-O`.

1. `x + ((y << shift) + offset)` ([CodeGen.hs, lines 3513-3517][guard]): the guard `shift == 0 || shift == 1 || shift == 2 || shift == 3 && is32BitInteger offset` parses as `... || (shift == 3 && is32BitInteger offset)`, because `&&` binds tighter than `||`, so the offset is checked only at shift 3. Suggested fix: parenthesise the disjunction.
2. `CmmRegOff x offset + (y << shift)` ([CodeGen.hs, lines 3504-3507][regoff]): `offset` goes to `x86_complex_amode` with no check. Suggested fix: add `is32BitInteger (fromIntegral offset)` to the guard.
3. `x - lit` ([CodeGen.hs, lines 3483-3489][sub]): the guard checks that `lit` fits and the clause then emits `-lit`, which does not fit for `lit = -2^31`. Suggested fix: check `-lit` rather than `lit`, or reject `lit = -2^31`.

`is32BitLit` checks label offsets for the same reason, citing #15570.

## Steps to reproduce

`amode.cmm`, one procedure per clause:

```
#include "Cmm.h"

shifted (W_ p, W_ i) {
    return (I64[((p - 4294967296) + (i << 2)) + 4294967296]);
}

regoff (W_ p, W_ i) {
    return (I64[(p + 4294967296) + (i << 2)]);
}

subneg (W_ p) {
    return (I64[I64[p] - (-2147483648)]);
}
```

`ghc -c amode.cmm` prints

```
/tmp/ghc12_tmp_0/ghc_tmp_4.s: Assembler messages:
/tmp/ghc12_tmp_0/ghc_tmp_4.s:9:0: error:
     Error: 0x100000000 out of range of signed 32bit displacement
  |
9 |         movq 4294967296(%rbx,%r14,4),%rbx
  | ^

/tmp/ghc12_tmp_0/ghc_tmp_4.s:18:0: error:
     Error: 0x100000000 out of range of signed 32bit displacement
   |
18 |         movq 4294967296(%rbx,%r14,4),%rbx
   | ^

/tmp/ghc12_tmp_0/ghc_tmp_4.s:28:0: error:
     Error: 0x80000000 out of range of signed 32bit displacement
   |
28 |         movq 2147483648(%rax),%rbx
   | ^

`gcc' failed in phase `Assembler'. (Exit code: 1)
```

Lines 9, 18 and 28 of the assembly are in `shifted`, `regoff` and `subneg`, and `-O` gives the same errors. In `shifted` the two constants cancel: the base register holds `p - 4294967296`, so the address is `p + 4*i`.

`Amode.hs`, for the first two clauses:

```
{-# LANGUAGE MagicHash #-}
module Amode where

import GHC.Exts

f :: Addr# -> Int# -> Word8#
f a i = indexWord8OffAddr# a (i *# 4# +# 4294967296#)

g :: Addr# -> Int# -> Word8#
g a i = indexWord8OffAddr# (plusAddr# a 4294967296#) (i *# 4#)
```

`ghc -c -O Amode.hs` prints

```
/tmp/ghc22_tmp_0/ghc_tmp_1.s: Assembler messages:
/tmp/ghc22_tmp_0/ghc_tmp_1.s:14:0: error:
     Error: 0x100000000 out of range of signed 32bit displacement
   |
14 |         movb 4294967296(%r14,%rsi,4),%al
   | ^

/tmp/ghc22_tmp_0/ghc_tmp_1.s:38:0: error:
     Error: 0x100000000 out of range of signed 32bit displacement
   |
38 |         movb 4294967296(%r14,%rsi,4),%al
   | ^

`gcc' failed in phase `Assembler'. (Exit code: 1)
```

the first error in `f` and the second in `g`, whose addresses in `-ddump-opt-cmm` are `I8[R2 + ((R3 << 2) + 4294967296)]` and `I8[(R2 + 4294967296) + (R3 << 2)]`. At `-O0` the module compiles.

## Expected behavior

Both files compile, the constant added in a register where it does not fit in a displacement, as for `x + lit` when `is32BitLit` fails.

## Environment

* GHC version used: master at 37ad471050 (10.1.20261103), 9.14.1 and 9.6.7

Optional:

* Operating System: Linux
* System Architecture: x86_64

[guard]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L3513-3517
[regoff]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L3504-3507
[sub]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L3483-3489

/label ~"T::bug"
/label ~"NCG backend"
/label ~"llm-derived::reproducer"
/label ~"needs triage"
