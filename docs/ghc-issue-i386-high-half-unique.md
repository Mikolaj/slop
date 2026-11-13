# GHC issue: i386 NCG: a 64-bit Cmm local and a 64-bit NCG temporary can get the same high-half register, so one overwrites the other's high 32 bits

Filed as GHC [#28125](https://gitlab.haskell.org/ghc/ghc/-/work_items/28125) on 2026-11-13; the text from "## Summary" down is the filed body, in the tracker's bug template. Title: **i386 NCG: a 64-bit Cmm local and a 64-bit NCG temporary can get the same high-half register, so one overwrites the other's high 32 bits**. Measured on 2026-11-13 with a stage-1 build of master 37ad471050 (10.1.20261103), with ghc-9.14.1, ghc-9.12.4 and ghc-9.10.3, each made to target i386 as the Environment section says; the links pin 37ad471050. Tracker search 2026-11-13, issues and merge requests, for `getHiVirtualRegFromLo`, `VirtualRegHi`, `getNewReg64`, `localReg64`, "i386 Int64", "i386 64-bit", "32-bit Int64", "i386 cmm", "i386 miscompil", "i386 wrong result", "x86 32-bit wrong" and "object-determinism i386": no report of this; #25601 is one symptom of it, as the body says.

## Summary

On 32-bit x86 a 64-bit value is held in two virtual registers, and the high half's is made by [`getHiVirtualRegFromLo`][hi], which keeps the number of the low half's unique and replaces its tag by `'H'`. So a 64-bit Cmm local with unique `'c'k` ([`localReg64`][local]) and a 64-bit NCG temporary with unique `'n'k` ([`getNewReg64`][new]) get the same high-half register `'H'k`, and where both are live, writing one overwrites the other's high 32 bits.

Since commit [d62c18d84c][d62c] ("determinism: Sampling uniques in the CG"), first in 9.12.1, the NCG's uniques come from a counter that starts at 0 for each module ([Haskell modules][nsupply], [`.cmm` files][usupply]), while before it they came from the global unique counter. Equal numbers then occur readily:

1. In a `.cmm` file, the parser's locals come from the global counter ([`initC`][initc]), which also starts near 0 in that compilation: the first locals are `'c'1`, `'c'2`, ..., and the first temporaries `'n'0`, `'n'1`, ....
2. In a Haskell module under `-fobject-determinism`, the Cmm locals are renamed to `'Q'54`, `'Q'55`, ... ([`UniqueRenamer`][renamer]), which the temporaries reach in a procedure with a few dozen of them.
3. In a Haskell module without it, the locals' numbers come from the global counter after the front end, in the thousands for small modules; the temporaries reach them in a module with enough 64-bit code.

The fix of #25601 (bfa6b70f27) made `genByteSwap` correct when `dst_hi == rhi` ([`CodeGen.hs`][bswap]). In that issue's test procedure, `T25601a.cmm` with `W_` written as `bits32`, the two are equal because of this numbering: `ret` is `'c'2` and the negation's result temporary is `'n'2`. Elsewhere the clash produces wrong code, as below.

`GHC.CmmToAsm.PPC.CodeGen` uses the same two functions; 32-bit PowerPC was not tried. No other backend uses them or `getHiVirtualRegFromLo`: the wasm32 backend keeps a 64-bit Cmm local in one `i64` local.

## Steps to reproduce

`add64.cmm`:

```
add64 (bits64 a, bits64 b, gcptr p)
{
  bits64 x;
  x = a + b;
  bits64[p] = x;
  return ();
}
```

Compiled for i386 with `ghc -S -O0 -dcmm-lint -ddump-asm-native add64.cmm`, the code before register allocation is

```
add64:
.Lc5:
	movl (%ebp),%vI_n0
	movl 4(%ebp),%vHi_H0
	movl %vI_n0,%vI_c1
	movl %vHi_H0,%vHi_H1
	movl 8(%ebp),%vI_n1
	movl 12(%ebp),%vHi_H1
	movl %vI_n1,%vI_c2
	movl %vHi_H1,%vHi_H2
	movl 16(%ebp),%vI_c3
	movl %vI_c1,%vI_n2
	addl %vI_c2,%vI_n2
	movl %vHi_H1,%vHi_H2
	adcl %vHi_H2,%vHi_H2
	...
```

`a` is `'c'1` and `b` is `'c'2`. Loading `b` into the temporary `'n'1` writes `%vHi_H1`, which is `a`'s high half, and the sum's temporary `'n'2` has `b`'s high half `%vHi_H2`, so the sum's high half is computed as `b.hi + b.hi + carry`. The final assembly:

```
add64:
.Lc5:
	movl (%ebp),%eax
	movl 4(%ebp),%ecx
	movl 8(%ebp),%edx
	movl 12(%ebp),%ecx
	movl %ecx,64(%esp)
	movl 16(%ebp),%ecx
	addl %edx,%eax
	movl 64(%esp),%edx
	adcl %edx,%edx
	movl %eax,(%ecx)
	movl %edx,4(%ecx)
	addl $20,%ebp
	jmp *(%ebp)
```

`harness.s` calls it with `a = 0x0000000100000005` and `b = 0x0000000200000007`:

```
        .section .bss
        .lcomm hsstack, 64
        .lcomm out, 8
        .section .data
msg:    .ascii "a + b = 0x"
hihex:  .ascii "00000000"
lohex:  .ascii "00000000\n"
        .text
        .globl _start
_start:
        subl $4096, %esp
        leal hsstack, %ebp
        movl $5, 0(%ebp)
        movl $1, 4(%ebp)
        movl $7, 8(%ebp)
        movl $2, 12(%ebp)
        movl $out, 16(%ebp)
        movl $back, 20(%ebp)
        jmp add64
back:
        movl out+4, %eax
        leal hihex, %edi
        call hex8
        movl out, %eax
        leal lohex, %edi
        call hex8
        movl $4, %eax
        movl $1, %ebx
        leal msg, %ecx
        movl $27, %edx
        int $0x80
        movl $1, %eax
        xorl %ebx, %ebx
        int $0x80
hex8:
        movl $8, %ecx
1:      roll $4, %eax
        movl %eax, %edx
        andl $15, %edx
        movb digits(%edx), %dl
        movb %dl, (%edi)
        incl %edi
        decl %ecx
        jnz 1b
        ret
digits: .ascii "0123456789abcdef"
        .section .note.GNU-stack,"",@progbits
```

`gcc -m32 -c harness.s && gcc -m32 -c add64.s && ld -m elf_i386 -static -e _start harness.o add64.o -o add64 && ./add64` prints

```
a + b = 0x000000040000000c
```

with master, 9.14.1 and 9.12.4. With 9.10.3, whose temporaries are numbered from `'n'7` on, and with master given `-dinitial-unique=1000`, which moves the locals to `'c'1001` on, it prints `0x000000030000000c`.

A Haskell module under `-fobject-determinism`, `M3.hs`:

```haskell
{-# LANGUAGE MagicHash #-}
module M3 (f) where
import GHC.Exts

f :: Int64# -> Int64# -> Int64# -> Int64#
{-# NOINLINE f #-}
f a b c =
  let !x1 = (c `timesInt64#` intToInt64# 1007#) `plusInt64#` b in
  let !x2 = (x1 `timesInt64#` intToInt64# 1014#) `plusInt64#` a in
  let !x3 = (x2 `timesInt64#` intToInt64# 1021#) `plusInt64#` b in
  let !x4 = (x3 `timesInt64#` intToInt64# 1028#) `plusInt64#` a in
  let !x5 = (x4 `timesInt64#` intToInt64# 1035#) `plusInt64#` b in
  let !x6 = (x5 `timesInt64#` intToInt64# 1042#) `plusInt64#` a in
  let !x7 = (x6 `timesInt64#` intToInt64# 1049#) `plusInt64#` b in
  let !x8 = (x7 `timesInt64#` intToInt64# 1056#) `plusInt64#` a in
  let !x9 = (x8 `timesInt64#` intToInt64# 1063#) `plusInt64#` b in
  let !x10 = (x9 `timesInt64#` intToInt64# 1070#) `plusInt64#` a in
  let !x11 = (x10 `timesInt64#` intToInt64# 1077#) `plusInt64#` b in
  let !x12 = (x11 `timesInt64#` intToInt64# 1084#) `plusInt64#` a in
  let !x13 = (x12 `timesInt64#` intToInt64# 1091#) `plusInt64#` b in
  let !x14 = (x13 `timesInt64#` intToInt64# 1098#) `plusInt64#` a in
  ((x14 `plusInt64#` a) `plusInt64#` b) `plusInt64#` c
```

With master, `ghc -S -O1 -fobject-determinism -ddump-asm-native M3.hs` gives `a`, `b` and `c` the uniques `'Q'56`, `'Q'57` and `'Q'58`, and the temporaries of the multiplication in `x14` reach them:

```
	movl %vHi_H0,%vHi_HU
	...
	movl %vHi_HS,%vHi_HU
	imull %vI_nV,%vHi_HU
	movl %vHi_HT,%vI_nU
	imull %eax,%vI_nU
	addl %vI_nU,%vHi_HU
	mull %vI_nV
	addl %edx,%vHi_HU
	...
	movl %vI_QU,%vI_nX
	...
	movl %vHi_HU,%vHi_HX
```

The product's high half is written to `%vHi_HU`, `a`'s high half, which the code then reads as `a`'s. Called with `a = 0x100000005`, `b = 0x200000007` and `c = 0x300000009` by a harness like the one above, `f` returns `0xf912f204bccee156`; without `-fobject-determinism`, where `a`, `b` and `c` have uniques numbered in the thousands, it returns `0xa85ba607bccee156`, the right value.

Without `-fobject-determinism`, a module of 50 functions like `f`, each with a chain of 40 multiply-adds in one expression (`f0` ... `f49`, the constants differing), compiled with master at `-O1`, gets the same clash in `f38` and `f39`: their arguments' uniques, `'t'6399` to `'t'6401` in `f38`, are numbers the module's temporaries reach there. `f38` returns `0xcc928c5dcd24dea6` for the arguments above, where the right value is `0x281e737acd24dea6`; `f37`, with no clash, returns the right value.

## Expected behavior

`add64` stores `0x000000030000000c`, `f` returns `0xa85ba607bccee156`: no two live 64-bit values share a register. The high half needs a unique that no other virtual register can have, for example one derived from the low half's whole unique, tag included, rather than from its number.

## Environment

* GHC version used: master at 37ad471050 (10.1.20261103), 9.14.1 and 9.12.4 (affected); 9.10.3 (not affected)

Optional:

* Operating System: Linux
* System Architecture: i386, emulated as follows. None of these was an i386 build of GHC: each was an x86-64 build run with `-B` over a copy of its library directory whose target settings say i386 (architecture, word size 4, platform string) and whose `DerivedConstants.h` has i386's `MAX_Real_*_REG`; for `M3.hs`, the x86-64 interface files of `ghc-prim`, `ghc-internal` and `base` with their magic number changed to the 32-bit one. The assembly was assembled with `gcc -m32` and linked with `ld -m elf_i386` into static programs, run on x86-64 Linux.

[hi]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Platform/Reg.hs#L129-134
[local]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/Monad.hs#L327-332
[new]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/Monad.hs#L314-322
[d62c]: https://gitlab.haskell.org/ghc/ghc/-/commit/d62c18d84c23728d258333b049994094c6858bbe
[nsupply]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Driver/Main/Compile.hs#L724
[usupply]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Driver/Main/Compile.hs#L906
[initc]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/StgToCmm/Monad.hs#L174
[renamer]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/Cmm/UniqueRenamer.hs#L72-79
[bswap]: https://gitlab.haskell.org/ghc/ghc/-/blob/37ad47105079d55e0da68f3c660f9bbd2e18047a/compiler/GHC/CmmToAsm/X86/CodeGen.hs#L6681-6692

/label ~"T::bug"
/label ~"NCG backend"
/label ~"llm-derived::reproducer"
/label ~"needs triage"
