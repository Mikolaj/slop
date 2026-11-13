# Session facts of the dev machine: the record

How the facts of the dev machine that `CLAUDE.md` at the root of `~/slop` states
were measured. That file keeps, for each, the symptom and what to do; this one
keeps each bullet as it stood on 2026-11-13, with its mechanism,
its measurements and their dates, under the lead words the bullet has now. Read
an entry when what you meet differs from what the bullet says, and before
changing or removing the bullet; add a new measurement here.

### The two sandboxes

Claude Code sessions on Mikolaj's machine run inside an outer bwrap sandbox
wrapper (PID 1 is `bwrap`), beyond Claude Code's own (inner) sandbox. Sessions
start in `~/slop`, which holds the repositories worked on but `~/.claude`,
so a sandboxed write lands anywhere in them; what follows about writing outside
the working directory and about sibling checkouts bites on an edit
to `~/.claude`, on a repository outside `~/slop` and on the read-only paths
the first bullet names, every repository's `.git/config` among them (measured
2026-10-19), and the inner sandbox's placeholders land in `~/slop`'s own root
rather than a repository's. Current state and its implications:

### Run `git` writes, `gpg` and SSH pushes unsandboxed

- Run `git` writes and `gpg` unsandboxed --- the inner sandbox mounts
  `.git/config` and `~/.gnupg` read-only. A sandboxed command may write
  `~/.cabal`, which `sandbox.filesystem.allowWrite` in `~/.claude/settings.json`
  has named since 2026-10-19. The inner sandbox's network filter refuses every
  host no settings source allows, and the same file's
  `sandbox.network.allowedDomains` allows only GitHub's hosts, GHC's GitLab
  and Hackage (measured 2026-10-19): a call needing any other host lists
  it in the Bash call's `allowed_domains` or runs unsandboxed. `git checkout -b`
  / `branch -f` fail to lock the config, though the ref often moves anyway ---
  verify refs afterwards. GPG signing (`commit.gpgsign` is on) fails sandboxed
  and works unsandboxed, so never fall back to `--no-gpg-sign`; SSH pushes
  likewise work only unsandboxed.

### Anything outside the working directory refuses a *sandboxed* Bash write and accepts an unsandboxed one

- **Anything outside the working directory refuses a *sandboxed* Bash write
  and accepts an unsandboxed one**, the read-only HOME mounts and the sibling
  checkouts alike: `~/.claude/projects` and, from a session started in horde-ad,
  `../orthotope` were measured in all four cells and do not differ, whatever
  a mechanism story suggests. The Write and Edit tools reach both regardless.
  So there are always two routes, and the choice is worth real tokens: Edit
  for a few lines, an unsandboxed `python3` splice for anything structural,
  a move otherwise shipping the block twice through Edit and costing tens
  of thousands of tokens where a script costs hundreds. Expect the wrong half
  to be learned by accident --- a session meeting `Read-only file system`
  from a *sandboxed* script concludes Bash cannot write there at all and reaches
  for Edit ever after. **And it misreports MOUNT FLAGS and not only what a write
  gets**: a path the inner sandbox will not let you write is reported `ro`
  by a sandboxed `mount` or `findmnt` and `rw` by an unsandboxed one, and what
  it presents is a read-only view with a writable one STACKED where it permits
  writes, so `findmnt -T` names the target TWICE for a path you may write
  and ONCE, `ro`, for one you may not --- which is the cheapest sandboxed test
  of whether a write will land, but for a checkout inside `~/slop`, shown ONCE,
  `ro`, and taking the write all the same (2026-10-20). `findmnt` reports
  a sibling checkout as `ro,nosuid,nodev,relatime` sandboxed where the real
  mount is `rw`. So a verdict about what any mount permits is the sandbox's
  unless it was taken unsandboxed; met 2026-09-21 on a tmpfs
  at `micro-regime3/hugebin`, where the sandboxed reading would have indicated
  a run could not launch from a mount that was in fact writable.

### A blocked write runs nothing at all, and under a typed `&` leaves the command's fate unreadable, which is why a session does not type one

- **A blocked write runs nothing at all, and under a typed `&` --- which is why
  a session does not type one --- leaves the command's fate unreadable.**
  Measured both ways: a simple command's redirections are checked before exec,
  so `cmd > blocked.log` and `nohup cmd > blocked.log` report the failure
  and run nothing at all, the command's own side effects included; while
  a pipeline fails only at its consumer --- `tee` opens its file itself, after
  the shell has forked --- so `cmd | tee blocked.log` reports the error
  and `cmd` keeps going. Backgrounded with a bare `&` that survivor is detached
  and invisible, and the launch looks as if it never happened --- two copies
  of a benchmark once ran side by side, contending, because one was read
  that way. The harness's own background mode reports the job's exit whatever
  the redirect did, and a pipeline whose consumer died still shows as running.

### Paths the wrapper blocks report "No such file or directory", not "Permission denied"

- Paths the wrapper blocks report "No such file or directory", not "Permission
  denied". If a path outside the repo seems missing --- especially one
  documented as expected, like horde-ad's `../ox-arrays` sibling checkout ---
  suspect the wrapper rather than recording the path as absent.
  `dangerouslyDisableSandbox` bypasses only the inner sandbox, never
  the wrapper. `tools/check-doc-refs.py` encodes the same rule: it resolves
  sibling checkouts when present and *stops* (exit 2) when one is not, rather
  than falling back to a weaker check, so a BLOCKED run means the check did
  not happen, not that it passed. **The complement is worse, because
  it is silent: a path CREATED under an unmounted parent succeeds
  and is invisible outside.** `mkdir ~/r/orthotope-pr` works, reads back,
  builds, and does not exist for Mikolaj --- so what looks like a delivered
  directory is a phantom of this session's mount namespace. The trap has teeth
  where a real path and a phantom one are written in the same command:
  `git worktree add ~/r/orthotope-pr BRANCH` puts the worktree registration
  and the commits in the MOUNTED `.git`, so the objects and the ref are real
  and survive, while the working tree is not there at all ---
  and the registration then makes git refuse to check that branch out anywhere,
  for a directory nobody can see. Prefer a path inside a mounted checkout,
  and where one is not available say what was written and where rather
  than reporting a directory delivered (2026-08-30).

### Where a sibling checkout and the released version it tracks disagree, the checkout wins

- **Where a sibling checkout and the released version it tracks disagree,
  the checkout wins.** It is ahead of the release and actively worked on,
  not stale, so read it for what upstream *is*: `orthotope` sat at 0.1.8.0 plus
  unreleased commits rewriting the very strided fallback the gather cost bullet
  in `horde-ad/.claude/rules/performance-model.md` describes, which would have
  been recorded as current had the release been treated as the authority.
  The cabal store provides what the checkout cannot: what to read when
  the wrapper hides the mount, and whether a *version-sensitive name* a document
  pins is really in the release the build plan resolves. A note resting
  on upstream code the checkout has since changed says so, and names what
  to re-measure when that work lands.

### The wrapper mounts a fixed set of HOME paths, curated per path rather than per directory, plus whatever repo checkouts it was launched with, skipping in silence any that do not exist

- The wrapper mounts a fixed set of HOME paths, curated per-path rather
  than per-directory, plus whatever repo checkouts it was launched with,
  skipping in silence any that do not exist --- which is where the previous
  bullet's "No such file or directory" comes from. The fixed part can be relied
  on; the checkouts are what varies from session to session, `~/r` having
  at times held only the current repo, so verify a sibling at the moment
  it matters rather than inferring it from habit. What of HOME it does not mount
  sits on the wrapper's root tmpfs, `/home` itself included, so `df /home`
  reports that tmpfs and not the disk: measure free space on a checkout,
  `df ~/slop` --- on 2026-11-02 a session read 32 GB free off `/home` where
  the disk had 89 GB, and deleted trees for want of space. That an entry
  is visible still says nothing about how much of its contents is: `~/.ssh`
  carries public material only.

### Sandboxed `ls` shows eleven dotfiles in the working directory that are not on the real filesystem: ignore them, and verify with an unsandboxed command before deleting any

- Sandboxed `ls` shows phantom dotfiles in the working directory that don't
  exist on the real filesystem, and `~/slop`'s `.gitignore` keeps them,
  with the `.claude/` placeholders, out of `git status`. HOME is *not* remapped
  to the repo root, whatever the names suggest: the inner sandbox bind-mounts
  `/dev/null` over eleven names in the directory it was launched in, once per
  Bash call, and over the `.gitmodules` of a checkout below it, so
  that a sandboxed `rm -rf` of such a checkout stops at that file with *Device
  or resource busy*: remove the file unsandboxed by name, then `rmdir` what
  is left (2026-11-09). So one path stats three ways --- a character device 1,3
  mode 666 from inside the call holding the mount, a regular empty file mode 444
  (the placeholder that mount needs) from any other mount namespace while
  that call is live, whether an unsandboxed command or a second concurrent
  sandboxed one, and absent when no call is running. The form follows vantage
  and timing, not the checkout, and a sibling checkout gets none of them at all
  --- which is the half measured from horde-ad, that repo having
  been the sibling when the three states were established. A session rooted
  in the directory is the one that can confirm the device state; the mode-444
  reading horde-ad's `CLAUDE.md` used to carry is what the account predicts
  a second concurrent call, or an unsandboxed one, would return. Ignore them;
  verify with an unsandboxed command before deleting any. The eleven
  are `.bashrc`, `.gitconfig`, `.gitmodules`, `.mcp.json`, `.profile`,
  `.bash_profile`, `.zshrc`, `.zprofile`, `.ripgreprc`, `.idea`, `.vscode`,
  worth listing because two of them are names a repository could legitimately
  carry and would then appear empty rather than missing. That is enough to move
  a checker's verdict: a backticked `.mcp.json` in this file makes
  `tools/check-doc-refs.py` resolve it from a session rooted here and fail
  it from one rooted elsewhere, or from an unsandboxed run, until an entry
  in `tools/doc-refs-allow.txt` settles the answer everywhere. The same masking
  covers the `.claude/` entries a session must not write, settings.json among
  them though `~/slop` carries none, and there it reaches Claude Code itself:
  its `--debug` log records a *Detected change to* that path and reloads every
  settings source on it --- CA certificates re-read, the sandbox configuration
  re-derived, all permission rules replaced. It has rules to replace: the user
  settings allow `Edit(~/.claude/CLAUDE.md)`,
  and `~/slop/.claude/settings.local.json`, a real file, allows
  `Read(//home/mikolaj/.claude/**)`; whether a reload loses them has
  not been measured (2026-10-19). No project `sandbox` block competes
  with the user-level one carrying `enableWeakerNestedSandbox`; adding one would
  give the reload that to lose as well. The same reload reads `.mcp.json`
  at length zero and logs it as invalid JSON, which costs nothing while no such
  file exists --- but a real one here would load at startup and then be read
  as empty on the first reload after any Bash call, dropping its servers
  mid-session.

### The inner sandbox is in its own PID namespace, so `ps` there lists only the session's own processes and `kill -0 <pid>` is not a liveness test

- The inner sandbox is in its own PID namespace, so `ps` there lists only
  the session's own processes and `kill -0 <pid>` is not a liveness test:
  it fails for a process that is running fine, and an `until ! kill -0 ...`
  waiter therefore returns at once. That reported a still-running build
  as finished once. Poll unsandboxed, or watch the thing's output file rather
  than its pid --- except that a file whose creation the sandbox blocked stays
  absent whether or not the process is running (sandboxing notes above),
  so there its absence proves nothing and only the unsandboxed process list
  settles it.

### System state under wrapper-hidden paths cannot be inspected from inside a session

- System state under wrapper-hidden paths cannot be inspected from inside
  a session; such diagnosis must be done by Mikolaj in a plain terminal. Most
  of `/etc` is in that class, the wrapper carrying `resolv.conf`, `hosts`,
  `ssl`, `passwd`, `group`, `alternatives` and `fonts` and no more,
  so `/etc/apparmor.d` here is an instance of one rule rather than a separate
  surprise, and the next `/etc` path to come back missing is predictable.
  The last two were added on 2026-08-10 after a session traced failures to them,
  `/etc/alternatives` being what the shell-tooling notes below rest on.

### The nested inner sandbox works only because three things hold

- The nested inner sandbox works only because three things hold; if sandboxed
  commands start failing at startup, check these first:
  - the Ubuntu AppArmor userns restriction is off
    (`kernel.apparmor_restrict_unprivileged_userns=0`,
    no `bwrap-userns-restrict` profile);
  - the wrapper mounts the repo read-write;
  - `enableWeakerNestedSandbox: true` is in effect --- inherited
    from the `sandbox` block of the user-level `~/.claude/settings.json`
    (a project `sandbox` block wholesale replaces the user-level one ---
    settings objects don't deep-merge --- so a project that defines one must
    repeat the flag).

### Run `gh` unsandboxed, alongside `git` writes and `gpg`

- `gh` is authenticated only unsandboxed, and sandboxed it degrades rather
  than fails, which is the trap: its real token is in the keyring, out
  of the inner sandbox's reach, so it falls back to the read-only
  `~/.config/gh/hosts.yml`, whose token is invalid, and proceeds
  unauthenticated. Measured both ways --- 60 requests an hour against 5000,
  and `/actions/jobs/<id>/logs` returning 403 "Must have admin rights
  to Repository" where an unsandboxed run returns the log. The network itself
  is there sandboxed, a plain `curl` to api.github.com giving 200, so what
  is missing is the credential and not the route, and `gh auth status` names
  it outright. Run `gh` unsandboxed, alongside `git` writes and `gpg`. `glab`
  differs on both counts: its token sits in a readable config file, so it works
  sandboxed too, but only for the host named by `GITLAB_HOST`
  (gitlab.haskell.org here) --- `glab auth status` lists gitlab.com alone even
  while the other host's credential is present and working. So GHC's tracker
  is read through `glab` ---
  `glab api 'projects/ghc%2Fghc/issues?search=...&state=all'`,
  `glab issue list -R ghc/ghc --search ...` --- and never through `curl`
  with a pasted token: on 2026-09-06 a session handed a token reached for `curl`
  and an inline one-liner first, lost a round to quoting, and had `glab` logged
  in the whole time.

### `pkill -f PATTERN` and `pgrep -f PATTERN` match the issuing shell's own command line, which contains the pattern: take pids from `ps` and `kill` those instead

- `pkill -f PATTERN` matches the issuing shell's own command line, which
  contains the pattern, so it kills the shell that ran it --- the tool call
  comes back with exit 144 and nothing else, twice mistaken here for the command
  failing. Take pids from `ps` and `kill` those instead. Sandboxed calls
  are spared that, by accident rather than by design: Claude Code's shell
  snapshot shadows `pkill` with a function that refuses any pattern whose
  `pgrep` hit equals `$CLAUDE_PID`, and in the inner sandbox's PID namespace
  the issuing shell is itself PID 2 --- the number the CLI holds
  in the wrapper's namespace --- so what fires is a collision between two
  namespaces rather than recognition of the CLI. Don't lean on it: unsandboxed,
  where the shell carries some other number, the same command still killed
  its own shell at exit 144. **The property belongs to any matcher run over your
  own command line, not to those two commands**, so a waiter hand-rolled out
  of `ps` inherits it whole: `pgrep -f` self-matches identically and, being
  shadowed by nothing, fails more quietly --- an `until ! pgrep -f PATTERN`
  waiter finds its own shell, so the condition never goes false and it waits
  until something kills it, where `pkill` at least ends the call loudly ---
  and `until ! ps -eo args | grep -q PATTERN` is the same waiter
  with the shadowing gone and no name to recognise it by, hung in orthotope
  on 2026-09-01 until it was killed by pid. Wait on a file's contents instead,
  and where the harness wakes you when a job ends, set no waiter at all.
  That is a job the HARNESS backgrounded: a typed `&` detaches just as well,
  registers nothing and wakes nobody (2026-09-04). A pattern the matcher cannot
  match, `'seq 1 [6]0'`, dodges both --- but only its own occurrence:
  a kill-then-relaunch script still dies through the literal name in its later
  launch line, measured in LambdaHack at exit 144 unsandboxed and meeting
  the refusal above when sandboxed, so kill and relaunch go in separate calls.

### `grep` and `find` are bash functions that Claude Code writes into its shell snapshot, routing to an embedded ugrep and bfs; `command grep` is the way back to GNU grep, at `/usr/bin/grep`

- `grep` is not the binary on PATH but a bash function Claude Code writes
  into its shell snapshot, routing to a ugrep (7.5.0) embedded in the `claude`
  executable; `find` is shadowed the same way, by bfs. A function shadows every
  PATH entry and `\grep` does not escape one, backslash suppressing aliases
  rather than functions, so `command grep` --- GNU grep, at `/usr/bin/grep` ---
  is the way back; the shims are not exported, so a Makefile recipe
  or a `python3` subprocess already gets the real thing. Three
  of the differences are silent: a recursive search skips gitignored paths,
  `--ignore-files` being injected, so a walk over the repo passes over `log*`,
  `dist-newstyle` and `*.prof`; binary files are skipped (`-I`), so `-c` prints
  nothing and exits 1 where GNU prints a count and exits 0; and `-r` output
  paths lose their leading `./`. The regex dialect is *not* one of them --- GNU
  BRE's `\|` and its siblings behave identically --- so an alternation
  that matches nothing means `-E`, `-P` or `rg`, where `\|` is a literal pipe
  in any grep; blaming that on ugrep put a fabricated machine fact one approval
  away from this file. What is ugrep's own: `-P` means PCRE2, it can reject
  a regex outright with `exceeds complexity limits` where GNU grep would run it,
  and on the one-line-per-paragraph documents here a bounded-repeat alternation
  can instead run for minutes --- reach for python when a pattern gets involved.
  The checkers under `tools/` are unaffected: they match with Python `re` rather
  than with whatever `grep` resolves to. Only `check-doc-refs.py` shells out
  to `git grep` at all, and only for its flag-usage check.
