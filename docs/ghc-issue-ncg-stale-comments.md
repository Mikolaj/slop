# GHC issue: NCG: comments and a users' guide paragraph that the code on master contradicts

Filed as GHC [#28127](https://gitlab.haskell.org/ghc/ghc/-/work_items/28127) on 2026-11-14; the text from "## Summary" down is the filed body. Title: **NCG: comments and a users' guide paragraph that the code on master contradicts**. Drawn from the message and diff of the commit that fixes them, the one commit of the branch `wip/ncg-comment-fixes`, on master 37ad471050. Tracker search 2026-11-14, issues, for "NCG comments", "stale comment", "outdated comment", "native code generator documentation", "CmmToAsm Note" and "NCG README": no report of these; #27973 lists documentation slips outside the NCG.

## Summary

Location of documentation issue: comments and Notes of the native code generator (`compiler/GHC/CmmToAsm.hs`, `compiler/GHC/CmmToAsm/`), comments in `GHC.Cmm.Node`, `GHC.Cmm.Reg`, `GHC.Platform.Reg`, `GHC.Platform.Reg.Class` and `GHC.StgToCmm.Monad`, and one paragraph of the users' guide.

The comments below were found while the NCG's machine-independent passes, and the x86, i386 and AArch64 code generators where those passes depend on them, were examined, not by a sweep of every comment, and !16995 corrects them. Each says something that the code on master (37ad471050) does not do:

- `GHC.CmmToAsm`, above `genMachCode`: names stix code and `UniqSM`; the code is Cmm, and switches from `UniqDSM` to `NatM`.
- `NcgImpl`'s `extractUnwindPoints`: places Note [Unwinding information in the NCG] in `GHC.CmmToAsm.Monad`; it is in `GHC.CmmToAsm`.
- `GHC.CmmToAsm.PIC`, header: names the modules `CLabel`, `Cmm`, `AsmCodeGen` and `MachCodeGen` for what other modules and functions do.
- `GHC.CmmToAsm.Reg.Target`, header: says that the module keeps the NCG to the host's architecture; each of its functions dispatches on the target's.
- Note [CFG based code layout]: runs `optimizeCFG` right after instruction selection; `cmmNativeGen` runs it after register allocation and shortcutting.
- Note [CFG Edge Weights]: a default weight of 20k (`defaultWeights` has 1000); likely and unlikely branches taken more than 80% and less than 20% of the time (the weights give 75% and 25%); the false side of a regular branch preferred (`getCfg` gives both sides the same weight, and on x86-64 the instruction selector adds 3 to the false side of a floating-point comparison); calls ignored completely (their edges are left out only while chains are built, and divided by 64 when chains are merged).
- Note [Layout relevant edge weights]: edges constituted by a call are ignored; they are left out only while chains are built, and divided by 64 when chains are merged.
- Note [Static Branch Prediction]: names two heuristics; `staticBranchPrediction` applies three, `ohPredicts` being the third.
- `staticBranchPrediction`: `s1` is the branch in the true case (it is the successor with the smaller label); the guard commented "Only backedges" is also reached by a back edge beside a heap or stack check's edge.
- `findBackEdges` in `GHC.CmmToAsm.CFG`: its comment says that it finds back edges by BFS; it finds them by a depth-first search (`classifyEdges`).
- The `Instruction` class: asks `regUsageOfInstr` to state precisely what an instruction reads and writes; x86's states it as the register allocators are to see it.
- x86's `regUsageOfInstr`, its `MOV` case in `GHC.CmmToAsm.X86.Instr`: its comment says that the MOVs reaching its last arm zero any remaining upper part of the destination; some keep it, such as a MOV between registers at `FF32` or `FF64` (`movss`, `movsd`) and an 8-bit or 16-bit MOV into a general register.
- The liveness pass, both register allocators, and the `Ord` instances of `CmmTickScope`, `LocalReg` and `VirtualReg`: comments say that deterministic code generation is not supported, which `-fobject-determinism` provides.
- `GHC.CmmToAsm.Reg.Graph.SpillCost`: says that there are no loops, so that the block frequencies can be 1; given a CFG, `slurpSpillCostInfo` scales the uses and definitions it counts by the CFG's block frequencies.
- `linearRegAlloc` and `process`: a block of an SCC is allocated before a jump into it only if it is the procedure's first block (any entry block is); `process` would loop on a block whose assignment never gets set (it drops it).
- `findPrefRealReg`: the preferred register is the first one assigned; it is the variable's register in the first block entry assignment, in allocation order, that maps it to a register.
- `GHC.CmmToAsm.Reg.Graph`: two comments name `-fasm-lint`, which is `-dasm-lint`.
- `GHC.CmmToAsm.Reg.Linear.Base`: two comments name `-ddrop-asm-stats`, which is `-ddump-asm-stats`.
- `FreeRegs`' executable specification: gives a list's `noFreeRegs` as `0` and hands out the most recently released register first; each instance has a fixed order.
- `StackMap`'s header: a slot stays with its register to the end of the procedure; a register that outgrows its slot moves to new ones.
- `handleComponent` in `GHC.CmmToAsm.Reg.Linear.JoinToTargets`, a cycle of moves: spills all the cycle's source registers; it spills one.
- AArch64's `getFreeRegs`: scans the integer registers from 28 down; it starts from x18.
- `classOfRealReg` (`GHC.CmmToAsm.X86.Regs`): says "On x86" of what holds on i386 alone, and numbers the registers with 8-bit versions 1-4 and the allocatable ones 1, 3 and 4; they are 0-3, and 0, 2 and 3.
- `RegArch`'s `Separate` (`GHC.Platform.Reg.Class`): gives RISC-V as an example; `registerArch` gives RISC-V `NoVectors`, and no architecture `Separate`.
- X86's `stmtToInstrs`: takes a branch's condition as likely false, `GHC.Cmm.ContFlowOpt` putting the likely side on the fall-through; `ContFlowOpt` also inverts where the false target has more than one predecessor, and `genCondBranch` does not read the likelihood.
- `mkCmmIfThenElse'` in `GHC.StgToCmm.Monad`: says that the NCG does not know about likely annotations; PowerPC's code generator prints them as branch hints, and `getCfg` weights the CFG's edges by them, which the block layout follows on x86-64. Its clause on a fallthrough leaves out that the swapped test, where it can be inverted, is a likely-true test of the inverse, and that `GHC.Cmm.ContFlowOpt` swaps the branches back where the true target, after shortcutting, has one predecessor.
- Users' guide, `-fcmm-static-pred`: the prediction is used by register allocation and layout; it is made only by the x86-64 NCG and used for the layout, after allocation and not under `-finfo-table-map`.

/label ~"T::bug"
/label ~"documentation"
/label ~"NCG backend"
/label ~"llm-derived::unverified"
/label ~"needs triage"
