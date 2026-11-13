# The incidents behind the rules of `~/slop/CLAUDE.md`

Not loaded. The dated incidents and measurements behind the bullets of `CLAUDE.md` beside this file, moved out of them on 2026-11-13, one entry per bullet under its lead words, in the bullets' order; a bullet with no entry had none. Those of the sandbox, `gh`, `pkill` and `grep` bullets are in `docs/session-machine-facts.md`, and the default GHC's fixes in `docs/default-ghc.md`. Read a bullet's entry before changing or removing the bullet. A new incident is added here, under the bullet it bears on. A refused design stays in the bullet itself, with its date and finding.

### Verify before claiming done: "uniform", "correct" or "passes" must rest on an actual line-by-line cross-check or a test run, not on the fact that it compiled, and an only, every or never claim on a repo-wide grep

One run shipped 'the first arms whose two statistics part in sign' --- no checker ranks a population, so it passed them all --- where two other pairs did it and ranking every pair took one command.

That is not hypothetical: in horde-ad it cost `tools/check-doc-refs.py` two of README's backticked references, which is why that checker now processes the unwrapped form too.

### Classify by the property you need, not by the proxy that greps easily

Building LambdaHack's leader-conversion inventory, functions were bucketed by whether their *own* body performs an interactive wait --- mechanical, and wrong for the one whose wait sits in a helper it calls (`closeDirHuman`, whose `pickPoint` waits for it), which landed in the "harmless" bucket until re-read.

the same way misreading a three-disjunct predicate as two produced a fixture whose code path never fired.

### A citation that resolves can still lie: cite code by a text anchor, or by a permalink pinned to the tree a sentence describes

(in LambdaHack, a `CliMock` citation came to name a comment two hundred lines away)

horde-ad's CREDITS.md's MNIST provenance link now serves an empty directory index, all four named files gone, at the same 200 it always gave

### Prove a check non-vacuous before trusting its silence: an assertion, a checker, a search

one session verified twenty-five fixes that way, reported them all applied, and had left two sites standing that differed from the checked wording by two words

a failed `python3 -m pyflakes` once reported pyflakes missing while a `pyflakes` script on PATH would have run, and the checks went unrun for a day; today the script is gone and the module runs, so `command -v pyflakes` reports missing a tool that is there.

Two wrong answers in one session came of skipping that (in LambdaHack: `grep '^??'` over colourised `git status` output, the git notes below, and concluding a note was absent from every document after grepping one of its phrasings).

this is how the orthotope version pin in `horde-ad/.claude/rules/performance-model.md` was established rather than guessed.

### Links that cite source code, in GitHub-bound texts and the reference documents, must be GitHub permalinks pinned to a commit hash that is on `master`

GitLab served `6913545fd3` with no branch holding it (2026-10-19)

### A tracked file or a commit message cites no untracked file for what it says, unless Mikolaj approves the mention

*Why:* on 2026-10-18 a defect record cited a handoff and its scratch copy of a tool, as records written days before cited the untracked plan and scratch scripts, and two commits were rewritten when Mikolaj came to delete the files.

### Commits should be clean and logical, not a diary of the work

Removed on 2026-11-13 as stated by the Bash tool's own description:

Interactive git is unavailable (tool commands run without a TTY, so editor and prompt loops hang): no `rebase -i`, no `add -i`.

### Name the paths on every `git add`, and read the diffstat of the commit you just made

one `git add -A` in orthotope's micro-regime3 committed 79 scratch files, 176632 insertions and five 32 MB binaries, and `git status` then reported CLEAN, the files having been absorbed. It was found three hours later in the same session, by a review of the diff's SHAPE noticing 83 changed files where four were expected; no pass between saw it.

### The GHC to use by default is no released version but `~/slop/ghc/_build/stage1/bin/ghc`, built from the branch `for-review` of `ghc/`

on 2026-10-30 it named the old `for-review`, `201f499705`, for a build of `da35817d62`.

### `hlint` and `stylish-haskell` are on PATH (via `~/.cabal/bin`) and work in-session, sandboxed included

The bullet as it stood until 2026-11-13, when the history of the mount was removed from it:

- Commands managed by `update-alternatives` --- `awk`, `cc`, `which`, `vi`, `pager` and the rest --- resolve in sessions since the wrapper began mounting `/etc/alternatives` (2026-08-10); before that every `/usr/bin` symlink pointing there dangled. The fix is that one mount and not a shim per command: the `~/.local/bin/awk -> mawk` link that had stood in for one of them is removed, and a retargeted alternative now reaches a session on its own. `hlint` and `stylish-haskell` are on PATH (via `~/.cabal/bin`) and work in-session, sandboxed included.

### A verification command must not be piped, and must not sit behind `&&` either: redirect to a file and echo `$?`, or put the check in its own call

`tools/check-plan-citations.py`'s non-vacuity recipe already tells its own reader to check the status without a pipe, having once read five successes that were four refusals.

printed *(tree clean)* on 2026-09-03 with the commit refused and three files still staged.

### A comment line that begins with the word `shellcheck` (bullet removed on 2026-11-13)

Removed because the failure names itself at once (SC1072); what is lost is one wasted call when it next happens. The bullet as it stood:

- **A comment line that begins with the word `shellcheck` is read as one of shellcheck's own directives**, so a note *about* the tool fails the whole file at SC1072/SC1073 ("Couldn't parse this shellcheck directive") rather than being ignored --- rephrase so the word does not start the line.

### `-keep-s-files` keeps nothing under a build that names `-pgma`

a fresh `--builddir` of orthotope's `micro-regime3` under GHC HEAD `10.1.20260918` held no `.s` at all after one (2026-09-22)

### `-dumpdir` and `-outputdir` are ignored for a source given by an absolute path, or found through an absolute `-i`: its dumps land beside it

*Why:* on 2026-11-06 two compilers' dumps of one module, compiled by its absolute path each with its own `-dumpdir`, landed beside the source, the second over the first.

(measured on 9.6.7, 9.12.4, 9.14.1 and master, 2026-11-06)

### A binary under `dist-newstyle` can silently predate the tree, so check before measuring it

Reverting an edit without rebuilding cost two wrong conclusions in one session: the binary still carried the reverted code, and the extra startup work it did was read as a property of the suite, contradicting an earlier measurement that had been right all along.

### The `/tmp` scratchpad is wiped by every machine restart, and a restart can come unannounced, so put there only what can be regenerated and nothing cites

*Why:* a GHC investigation met two restarts in two days that nobody announced to it, on 2026-11-11 in the middle of a measuring step and on 2026-11-12, and lost two scripts an agent's notes cited, written to `/tmp/claude-1000` after the copy made before an earlier, planned restart.

### `.github/workflows/haskell-ci.yml` is generated by `haskell-ci` from the `.cabal` file: regenerate it (`haskell-ci regenerate`) rather than hand-editing

which is what a rewritten `tests` step and a whole `benchmarks` step in horde-ad were exposed to, a plain regenerate dropping both without a word, until the first moved into the patch and the second into a hand-written workflow of its own.

(In LambdaHack the same role is played by an `apt:` entry, `libsdl2-ttf-dev`, which that repo nearly lost the same way.)
