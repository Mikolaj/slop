# GHC issue: AArch64 NCG: a label at an offset from -2048 to -1 stops the compilation in check_off ("is out of 12 bit")

Filed as GHC [#28126](https://gitlab.haskell.org/ghc/ghc/-/work_items/28126) on 2026-11-14; the text from "## Summary" down is the filed body, in the tracker's bug template. Title: **AArch64 NCG: a label at an offset from -2048 to -1 stops the compilation in check_off ("is out of 12 bit")**. Established by reading master 37ad471050, which the links pin, by compiling the inputs with master's x86-64 compiler to see their Cmm, and on 2026-11-14 by compiling them with master's stage-1 compiler, built for x86-64, given a target description naming AArch64 (Steps to reproduce): `lbloff.cmm` at `-O0` and `-O1` and `Neg.hs` at `-O1` stop with `check_off`'s error, and both compile at `-O1` under the unchanged x86-64 description. No compiler built for AArch64 was at hand and nothing ran on AArch64 hardware; the label is `llm-derived::reproducer`, described on the tracker as for content that "comes with a reproducer showcasing that this issue deserves attention", rather than `llm-derived::unverified`. Tracker search 2026-11-14, issues and merge requests, titles and descriptions, for `check_off`, "out of 12 bit", `ImmIndex`, `isNbitEncodeable`, "AArch64 label offset", "aarch64 CmmLabelOff", "AArch64.Ppr", "AArch64 offset", "AArch64 label", "aarch64 out of 12", "aarch64 pgmError" and "AArch64 negative offset": no report of this; the one hit is !16891, whose branch guards the clause.

## Summary

On AArch64, the NCG stops the compilation of the address of a label at an offset from -2048 to -1 with `check_off`'s error. This is read from master's code and reproduced with master's compiler given an AArch64 target description (Steps to reproduce), not with a compiler built for AArch64. For an offset of -8, the message that `check_off` gives `pgmError`, as the compiler prints it, is:

```
GHC.CmmToAsm.AArch64.Ppr.check_off : -8 is out of 12 bit
```

The instruction selector and the printer disagree on the offsets an immediate can take:

* `getRegister'` handles `CmmLit (CmmLabelOff lbl off)` by the clause [`CmmLabelOff _lbl off | isNbitEncodeable 12 (fromIntegral off)`][clause]. Its test, [`isNbitEncodeable`][enc], is signed and admits `off` from -2048 to 2047. The clause emits an `LDR` of `ImmIndex lbl off` ([`litToImm'`][lti], [`litToImm`][lit]).
* The printer prints each of the three `LDR` cases with an `ImmIndex` operand ([`Ppr.hs`][ldr]) ending in an `add` of the offset through [`check_off`][chk], which accepts 0 to 4095 and otherwise calls `pgmError`.

So an offset from -2048 to -1 passes the guard and fails in `check_off`. An offset below -2048 fails the guard and takes the clause below, which adds the offset from a register, and so does an offset from 2048 to 4095, which `check_off` would accept.

`check_off` came with 9995c2b70f ([Support for ARM64 Windows][9995]), first in 9.14.1. Before it, the printer emitted `add xN, xN, #off` unchecked, under a TODO, and LLVM's assembler (`llvm-mc` 15 and 18) assembles `add x0, x0, #-8` as `sub x0, x0, #8`; GNU as was not tried.

Master's Cmm folds make such offsets. `cmmMachOpFoldM` folds a label less a literal into a `CmmLabelOff` ([`GHC.Cmm.Opt`][fold]). `cmmExprNative` ([`GHC.Cmm.GenericOpt`][native]) rebuilds a `CmmLabelOff` as the sum of the label's reference and the offset; where that reference is the `CmmLabel` itself, as on AArch64 for these inputs, the fold's `MO_Add` clause ([`GHC.Cmm.Opt`][add]) turns the sum into the `CmmLabelOff` again. Whether StgToCmm or the RTS's `.cmm` files produce one was not established. !16891 met the error with its own folds, which gather a sum's literals into a label's offset, and adds `off >= 0` to the guard.

## Steps to reproduce

The two inputs below were compiled on x86-64 Linux by master's stage-1 compiler at 37ad471050, built for x86-64, with `-B` pointing at a copy of its `lib` directory in which `targets/default.target` has `archOS_arch = ArchAArch64` in place of `archOS_arch = ArchX86_64`, so that `ghc --info` reports `("target arch","ArchAArch64")` and `-S` runs the AArch64 code generator and its printer. This is neither a compiler built for AArch64 nor a run on AArch64: the compiler binary and the interface files `Neg.hs` loads are x86-64's, only the target description differs, and no assembler ran. Below, `ghc` is that compiler and `lib` the copy.

`lbloff.cmm`:

```
section "data" {
  tbl: bits64 1; bits64 2;
}

lbloff (gcptr p)
{
  bits64[p] = bits64[tbl - 8];
  return ();
}
```

`ghc -Blib -S -O0 -dcmm-lint lbloff.cmm` exits with 1 and prints only this, and so does the same at `-O1`:

```
GHC.CmmToAsm.AArch64.Ppr.check_off : -8 is out of 12 bit
```

`-ddump-opt-cmm` shows `I64[_c1::P64] = I64[tbl-8];` at `-O0` and `I64[R1] = I64[tbl-8];` at `-O1`, with the AArch64 target description as with master's x86-64 compiler, `tbl-8` being the folded `CmmLabelOff`. On AArch64 the load's address goes through `getAmode`'s generic case to the clause. Under the unchanged target description `lbloff.cmm` compiles at `-O1`.

With `tbl - 8` changed in `lbloff.cmm`, at `-O1`, the cases follow the guard and `check_off`: the offsets -2048 and -1 stop likewise, with `-2048 is out of 12 bit` and `-1 is out of 12 bit`; 8 and 2047 compile to an `add` of the offset as an immediate; and -4096, -2056, 2048 and 4095 compile to an `add` of the offset from a register.

From Haskell, `Neg.hs` at `-O1`; at `-O0` the subtraction stays on a local and is not folded:

```haskell
{-# LANGUAGE MagicHash #-}
module Neg (f) where
import GHC.Exts

f :: Int -> Addr#
{-# NOINLINE f #-}
f _ = plusAddr# "hello"# (-1#)
```

`ghc -Blib -S -O1 Neg.hs` exits with 1 and prints only this:

```
GHC.CmmToAsm.AArch64.Ppr.check_off : -1 is out of 12 bit
```

`-ddump-opt-cmm` shows `R1 = lvl_rx6_bytes-1;`, with the AArch64 target description as with master's x86-64 compiler. At `-O0` it compiles, to a `sub x18, x18, #1` after the string's address; under the unchanged target description it compiles at `-O1`.

## Expected behavior

Both inputs compile. Either of two changes suffices: narrow the clause's guard to what the printer accepts (`off >= 0`, or an unsigned test of 0 to 4095), so that a negative offset takes the clause below; or let the printer take a negative offset, as a `sub` of its negation.

## Environment

* GHC version used: master at 37ad471050, run as in the Steps, and 9.14.1, read and not run, have the clause and `check_off`; 9.12 has the clause without `check_off`

Optional:

* System Architecture: AArch64, any OS (each of the three `LDR` cases calls `check_off`)

[clause]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/AArch64/CodeGen.hs#L907-911
[enc]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/AArch64/CodeGen.hs#L1791-1792
[lti]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/AArch64/CodeGen.hs#L639-640
[lit]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/AArch64/Regs.hs#L87
[ldr]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/AArch64/Ppr.hs#L575-598
[chk]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/AArch64/Ppr.hs#L690-691
[9995]: https://gitlab.haskell.org/ghc/ghc/-/commit/9995c2b70f1e94ca4a97c7c585c7472cd5b2b456
[fold]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Cmm/Opt.hs#L300-302
[native]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Cmm/GenericOpt.hs#L187-193
[add]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Cmm/Opt.hs#L294-296

/label ~"T::bug"
/label ~"NCG backend"
/label ~aarch64
/label ~"llm-derived::reproducer"
/label ~"needs triage"
