# GHC issue: NCG: much of what working on the native code generator takes is not written down where the code is

Filed as GHC [#28128](https://gitlab.haskell.org/ghc/ghc/-/work_items/28128) on 2026-11-14; the text from "## Summary" down is the filed body. Title: **NCG: much of what working on the native code generator takes is not written down where the code is**. Each "Partly" and "No" rests on a search of master 37ad471050; `#28127` is the issue recorded in `ghc-issue-ncg-stale-comments.md`. Tracker search 2026-11-14, issues, for "NCG documentation", "native code generator README", "CmmToAsm README", "NCG overview", "NCG Notes", "native code generator Notes", "register allocator documentation", "code generator documentation", "NCG onboarding", "NCG maintainer", "native code generator maintainer", "NCG maintenance" and "NCG invariants": no report of this; #19914 (closed) asked for the documentation of four `NcgImpl` functions.

## Summary

Location of documentation issue: the comments and Notes of the native code generator (`compiler/GHC/CmmToAsm.hs`, `compiler/GHC/CmmToAsm/`) and the users' guide.

The list below is what whoever works with the native code generator (NCG) needs to find in the code base: someone reading its output and dumps, a reviewer of a change (human or LLM), a contributor making one, or an owner maintaining it. Each of them needs a part of the list, and an owner the whole of it. After each point is what master (37ad471050) provides of it, as a search of master for that point found it: **Partly**, with a place that provides some of it, or **No**. This issue asks that what master lacks be written down where the code is; !16996 provides part of the list. The issue stays open until each point is provided or declined.

## What an owner of the NCG needs

- Comments and Notes that are true of the code they describe. **No:** #28127 lists comments that the code contradicts, and Note [Native code generator] names `cmmCodeGen`, which nothing defines.
- Which targets go through the NCG, which of its parts each target uses, and what the NCG takes from the Cmm pipeline, StgToCmm and the RTS. **Partly:** `nativeCodeGen`'s case over `platformArch` in `GHC.CmmToAsm`.
- The NCG's passes in the order they run, and what each requires of the one before. **Partly:** Note [Native code generator] in `GHC.CmmToAsm` names instruction selection, register allocation and the ordering of the blocks.
- An order in which to read the NCG's Notes. **No.**
- One place where the terms the NCG's comments use are defined. **No.**
- One small function followed through the NCG's dumps, in the order of its passes. **No.**
- The paper or earlier design each part of the NCG is based on, where there is one, and which code is no longer used and since which change. **Partly:** Note [Static Branch Prediction] in `GHC.CmmToAsm.CFG` cites Wu and Larus's paper.
- The kind of each statement in the NCG's comments, shown at the statement: a bug, half-done work, a likely change or code meant to stay. **Partly:** comments that begin with `TODO`, with no stated meaning, such as "TODO: We shouldn't need to go through a list here." in `GHC.CmmToAsm.Reg.Liveness`.
- What a comment that does not show the kind of its statements does and does not claim. **No.**
- How the statements on bugs, half-done work and likely changes are kept true as the code changes. **No.**
- Which parts of the NCG were examined for bugs, half-done work and likely changes, and which were not. **No.**
- The invariants the code depends on. **Partly:** the comment on the `CFG` type in `GHC.CmmToAsm.CFG`, "We must uphold the invariant that for each edge A -> B".
- Where the code does something other than what reading it suggests. **Partly:** Note [Sub-word subtlety during jump-table indexing] in `GHC.CmmToAsm.X86.CodeGen`.
- Where the code is known to behave wrongly or is half done. **Partly:** "TODO: make sure this still works, it might be bitrotted" in the header of `GHC.CmmToAsm.PIC`.
- What each known bug leads to, such as wrong code, a compiler panic or only slower code, and under which flags and on which targets it is reached. **Partly:** the users' guide's entry for `-fregs-graph`, off by default because of a performance regression (#7679).
- Where the code is likely to change, and how. **Partly:** "TODO: Do a better job of the overloading, and eliminate this module." in the header of `GHC.CmmToAsm.Reg.Target`.
- Which of the code's likely changes depend on which redesign, and so in what order they can be made. **Partly:** the TODO of Note [Static Branch Prediction] in `GHC.CmmToAsm.CFG`, "Requires refactoring of all the code relying on the binary nature of likelihood."
- The norms and principles that apply to the NCG, whether each is agreed or only proposed, and which trade-offs are acceptable. **Partly:** Note [Object determinism] in `GHC.StgToCmm`.
- How to find the pass at fault for a miscompilation or a compiler panic, and how to reduce the case to a Cmm test. **Partly:** the users' guide's entries for `-dasm-lint` and `-dcmm-lint`.
- What else must change when a MachOp, an instruction, a register or a relocation is added or changed. **Partly:** Note [Register mapping on WebAssembly] in `GHC.CmmToAsm.Wasm.FromCmm`, for wasm32's global registers.
- What the tests cover and what they do not: which targets CI runs natively, which paths have few or no tests, and which performance test exercises which pass. **Partly:** `.gitlab/jobs.yaml`, whose jobs build GHC and run its testsuite on x86-64, AArch64 and i386; for RISC-V and LoongArch they build a cross-compiler and run one program under qemu (`.gitlab/ci.sh`); no job targets PowerPC.
- The NCG's own compile-time cost: which passes are expected to be linear in the size of their input, and where they are not. **Partly:** Note [Combining neighborhood chains] in `GHC.CmmToAsm.BlockLayout`, on a heuristic kept for compile time.
- The support status of each part of the NCG, such as the graph register allocator and the code for 32-bit targets. **Partly:** `backendMaintainsCfg` in `GHC.CmmToAsm.BlockLayout`, on i386: "Should work but not tested so disabled currently."
- Which open merge requests change code that the NCG's comments say behaves wrongly, is half done or is likely to change. **No.**

/label ~"T::task"
/label ~"documentation"
/label ~"NCG backend"
/label ~"llm-derived::unverified"
/label ~"needs triage"
