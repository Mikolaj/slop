#!/usr/bin/env python3
"""Check that the code citations and permalinks in a document still resolve.

Usage: python3 ~/slop/tools/check-plan-citations.py [DOC ...]
DOC defaults to CLAUDE.md. The repository checked is the one holding the
documents, else the working directory's; runs from anywhere.

A citation names a text anchor: `File.hs:some text`, in backticks or between
`@` signs (haddock's code markup, for a document that drafts a module),
where what follows the colon starts with neither a digit nor a space and
runs to the closing delimiter. The file may be a .hs, .ts, .py, .c, .h,
.cabal, .mjs, .html, .md, .txt, .yaml/.yml, .json or .sh file, or the
Makefile --- documents cite each other and the tools. The anchor is a fixed
string that exactly one line of the file must contain, runs of whitespace
on either side counting as one space, since the formatter collapses them in
prose; the script prints that line with its number, so a human can compare
it against what the surrounding sentence claims, and fails ANCHOR-MISSING
when no line carries it and ANCHOR-AMBIGUOUS when several do, listing
them. An anchor also carries no word that would open a heading, a quote, a
table row or a list item were a wrap to put it first on a line (`#ifdef`,
`>=`, `|`, a bare `-` or `*`), because the formatter breaks inside backticks
and such a paragraph does not survive its round trip; cite the words
beside such a token instead. A slid line therefore never goes stale, and a
rewritten one fails loudly. An anchor can contain neither a backtick nor
an `@`, whichever delimits it, so a line whose only unique text has one in
it is cited by the text beside it. Into a `.md` file an anchor is matched
against paragraphs rather than lines --- the file read through `wrap80
--unwrap`, as check-doc-refs.py reads its spans --- because a wrap can fall
inside any phrase and moves whenever a paragraph above is edited; the report
then names the paragraph, and a run that finds no wrap80 to unwrap with
stops at 2 rather than reporting every such anchor missing.

A citation by line number --- `File.hs:12`, a range `File.hs:12-34` or
a list `File.hs:12,34` --- fails as LINE-NUMBER whether or not the line
exists: a commit above it slides it onto other text while it still resolves,
and nothing then says so. Cite a text anchor instead, or, where the sentence
describes a past tree, a permalink pinned to it. Line numbers are refused
since 2026-10-21, by when citations had slid in both repositories that used
them with every pass green.

A `/.../` component in a cited path is treated as a wildcard (the document
uses it to abbreviate long paths).

Exit status is nonzero if any citation is UNRESOLVED (no such file),
AMBIGUOUS (a bare basename matching several files --- qualify it in the
document), LINE-NUMBER, ANCHOR-MISSING or ANCHOR-AMBIGUOUS, or if a
permalink or a link fails as below. It is 2 where the run did not happen: a
usage error, a document that cannot be read or no repository to run in.

Pinned GitHub permalinks (`https://github.com/.../blob/<commit>/<path>#L12`
or `#L12-L34`) are also checked, against the pinned commit via
`git show <commit>:<path>` --- they never drift, so this catches typos,
wrong ranges and links whose commit or path is not in this repository.
This repository is the GitHub one that PUBLISHED_REF's remote names, and
with no GitHub remote every link is taken for this repository's; a link into
another is listed as not checked unless FOREIGN names a clone of it.

`git show` proves only that the commit is in *this* clone's object
database, which an unpushed or squashed-away commit is too --- such a link
resolves for one person on one machine and 404s everywhere else. So a
resolved permalink is then required to be an ancestor of PUBLISHED_REF,
and one that is not fails as UNPUBLISHED; if that ref is absent the
document is BLOCKED (exit 2, unless another document of the run failed)
rather than degraded to the weaker check, as check-doc-refs.py does for
an unmounted sibling.

FOREIGN, one of the repository's settings in its
`tools/check-plan-citations.config.py` over the defaults in the block at the
top, maps the URL prefix of another repository's permalinks to a local clone
of it, GHC's GitLab to `ghc` in ~/slop's, and such a
link is checked in the clone the same way: a GitLab range reads `#L12-34`, a
link with no line names the whole file, and published means that one of the
clone's remote-tracking refs holds the commit. A clone or a commit missing
here makes the document BLOCKED (exit 2, unless something failed), stderr
saying which is missing. `--foreign=PREFIX=CLONE` adds a mapping for one
run.

A document's links are checked for their own claims too. A `[text][label]`
with no definition renders as plain text and fails, but for two bracketed
numbers in a document defining no numeric label, which are sources cited
footnote-style against a numbered list. A permalink's link text
shaped like a path must be the end of its URL, and a `#L` one must continue
the file the paragraph's last path-shaped one named. And of the names written
beside a permalink in its clause --- backticked code, a `Note [...]`, a
quotation of twelve characters or more, the link text included --- the
cited file's own path and those the file does not hold as a whole word are
dropped, and one of the rest must occur within NAME_WINDOW lines of the
cited ones or in a definition or Note enclosing them. The drop is what lets
a clause name the program a draft is about, while a link whose lines moved
still fails.

Non-vacuity: run `python3 ~/slop/tools/check-plan-citations.py
--self-test`. It builds a scratch git repository -- files, commits, an
origin/master ref, an unpublished commit -- and a control document holding
every failing kind beside its passing controls, and asserts each verdict
and the exact failure count. A second scratch repository stands in for a
foreign clone, a published commit and an unpublished one in it, for the
FOREIGN and link rows, both BLOCKED stops and, its origin/HEAD then set, the
ancestry test that decides before the remote refs are scanned. The AMBIGUOUS
kind gets its first live control there too: two files of one basename under
different search roots, with no copy at the repo root to shadow them. Its
second-document row was added for a defect found by review, and the
subdirectory row for another, the search roots being root-relative and the
script now moving there itself. When running any of this by hand instead,
check the exit status without a pipe: `tail` swallows it. That the self-test
bites is mutants.py's to show.

One design point the self-test encodes: UNPUBLISHED takes a commit the
scratch repository mints fresh, since the branch is reached only after `git
show` succeeds, and a real hash's resolvability rests on a branch or the
reflog and expires with them --- the hand-run control this replaces, a row
pinned at a commit that a backup branch alone kept resolvable, died that
way.

The PUBLISHED_REF-absent stop is exercised before the ref is created:
the same permalink document must exit 2 there, a failing document named
after it in the same run must still be checked with the run at 1, and
the permalink must pass once the ref exists. The stop sits inside the
permalink loop, so in a repo whose
documents pin no permalink of its own a bogus PUBLISHED_REF stays silent --
true of this repo's tracked documents, whose pinned links all point into
other repositories, the README's whole-file pointers being deliberately
`blob/master`.

Scope limits, deliberate: a line number written in prose ("config.ui.default
line 67") is not refused, nor one left dangling from its filename (`:1581`),
which is indistinguishable from an X display such as `:99`. And the *claims*
around citations are not checked --- in particular, universally-quantified
claims ("only X does Y", "exactly two", "never") must be re-verified by
repo-wide grep, not by re-reading the cited file; that asymmetry is how a
real error slipped in once.

The permalink rows depend on the order the checks run in, which is worth
knowing before either is edited: OUT-OF-RANGE is tested before
publication, so a range row fails as a range even when its commit is also
unpublished. Give the range row a commit that happens to be unpublished
and the two rows still report distinctly; swap the two checks and the
range row silently starts proving the publication branch instead, with
nothing in the output to say so.

AMBIGUOUS (a bare basename matching several files) needs the scratch
repository, and deliberately: in horde-ad `test/CLAUDE.md` and
`bench/CLAUDE.md` share the only duplicated basename under the search roots,
and `resolve` returns at its `os.path.exists` check before reaching the
ambiguity branch, so the root `CLAUDE.md` shadows the pair and an anchor
into `CLAUDE.md` resolves -- a live row needs a basename duplicated under
the search roots with no copy at the repo root, which the self-test builds.
"""

import collections
import functools
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Beside this file, which a path import (a defect case's unit) leaves off
# sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# --- per-repo configuration -----------------------------------------
# The defaults, which the root's tools/check-plan-citations.config.py
# assigns over (common.repo_config, run by configure() below).
# The directories a cited file is looked for under, the root included.
SEARCH_ROOTS = ["."]
# The ref a pinned commit has to be reachable from to count as published.
# `git show` is an object-database lookup with no reachability requirement,
# so without this a link naming an unpushed or squashed-away commit resolves
# here and nowhere else.
PUBLISHED_REF = "origin/master"
# Permalinks into another repository that a local clone can check, keyed by
# the URL up to the commit: the clone's path from the root. A commit there
# counts as published when one of the clone's remote-tracking refs holds it.
FOREIGN = {}
# --- end per-repo configuration --------------------------------------
SETTINGS = ("SEARCH_ROOTS", "PUBLISHED_REF", "FOREIGN")
# FOREIGN with this run's --foreign= additions, which main() sets.
FOREIGN_RUN = dict(FOREIGN)

# The extensions are check-doc-refs.py's PATH_EXT: that pass skips every
# backticked `path:NN` token as this one's, so an extension missing here
# lets a line number into such a file pass unrefused, and an anchor into it
# go unchecked. Two files, so the list is written twice and each names the
# other.
CITED_FILE = (r"(\.?[A-Za-z][A-Za-z0-9_./-]*"
              r"\.(?:hs|ts|py|c|h|cabal|mjs|html|md|txt|yaml|yml|json|sh)|Makefile)")
CITE_RE = re.compile(
    r"`?" + CITED_FILE + r":(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)")
# The anchor form. The first character after the colon excludes a digit, so
# the numeric form above, which is refused, keeps every match it had, and
# a space, so a shell command's `file.hs: ` cannot start one; the closing
# delimiter must repeat the opening one.
ANCHOR_RE = re.compile(r"([`@])" + CITED_FILE + r":([^0-9\s`@][^`@\n]*)\1")
URL_RE = re.compile(
    r"https://github\.com/([\w.-]+/[\w.-]+)/blob/([0-9a-f]{7,40})/"
    r"([A-Za-z0-9_./-]+)#L(\d+)(?:-L(\d+))?")
# A reference definition, `[g1]: URL`, a title after it allowed, and a link
# written either way, `[text][label]` or `[text](URL)`, one level of
# brackets allowed inside the text; code spans are blanked before the links
# are looked for.
DEF_RE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*<?([^\s>]+)>?"
                    r"""(?:[ \t]+(?:"[^"]*"|'[^']*'|\([^)]*\)))?[ \t]*$""")
LINK_RE = re.compile(r"\[((?:[^\[\]\n]|\[[^\[\]\n]*\])*)\]"
                     r"(?:\[([^\[\]\n]*)\]|\(([^()\s]+)\))")
CODE_RE = re.compile(r"(`+)(.+?)\1", re.S)
# Link text that names a file and line rather than saying something:
# `compiler/GHC/X.hs#L12`, `X.hs`, `#L40`.
PATHISH_RE = re.compile(r"[A-Za-z0-9_./+-]*(?:#L\d+(?:-L?\d+)?)?")
# The names beside a link that say what its line holds: code, a Note, or a
# quotation of the source.
NAME_RE = re.compile(r"`([^`\n]+)`|Note \[([^\]\n]+)\]|\"([^\"\n]{12,})\"")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_']{2,}")
# How far from the cited lines a name beside the link may sit.
NAME_WINDOW = 15
# Words of Haskell's own that a code span beside a link holds and that say
# nothing about which line it cites.
KEYWORDS = frozenset(
    "case class data default deriving else forall foreign import infix"
    " infixl infixr instance let module newtype qualified then type where"
    .split())


def reachable_from(sha, ref):
    """Is sha an ancestor of ref? None if ref does not exist here."""
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                       f"{ref}^{{commit}}"], capture_output=True).returncode:
        return None
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref],
                          capture_output=True).returncode == 0


def published(sha):
    """Is sha reachable from PUBLISHED_REF? None if that ref is absent."""
    return reachable_from(sha, PUBLISHED_REF)


def foreign_res(foreign):
    """One URL pattern per foreign repository: commit, path, and a line or
    range in either host's spelling, GitLab's `#L12-34` or GitHub's
    `#L12-L34`; a link with no line names the whole file, and a path ends
    in no sentence's punctuation."""
    return [(clone, re.compile(re.escape(prefix)
                               + r"([0-9a-f]{7,40})/"
                               r"([^\s#)>\]]*[^\s#)>\].,;:!?])"
                               r"(?:#L(\d+)(?:-L?(\d+))?)?"))
            for prefix, clone in sorted(foreign.items())]


# The calls into a clone, here and in blob_lines and foreign_published,
# clear git's location variables: an inherited GIT_DIR, which -C does not
# override, sent them to the document's repository
# (check-plan-citations-18).
@functools.lru_cache(maxsize=None)
def is_clone(clone):
    """Is CLONE a git repository here?"""
    return subprocess.run(["git", "-C", clone, "rev-parse", "--git-dir"],
                          capture_output=True,
                          env=common.git_env()).returncode == 0


@functools.lru_cache(maxsize=None)
def blob_lines(clone, sha, path):
    """PATH's lines at SHA in CLONE: None when the commit is not there,
    False when the path is not."""
    if subprocess.run(["git", "-C", clone, "cat-file", "-e",
                       f"{sha}^{{commit}}"], capture_output=True,
                      env=common.git_env()).returncode:
        return None
    p = subprocess.run(["git", "-C", clone, "show", f"{sha}:{path}"],
                       capture_output=True, text=True, errors="replace",
                       env=common.git_env())
    return p.stdout.splitlines() if p.returncode == 0 else False


Body = collections.namedtuple("Body", "text squashed flat words")
WORD_RE = re.compile(r"[\w']+")


@functools.lru_cache(maxsize=None)
def blob_body(clone, sha, path):
    """PATH's text at SHA in CLONE but its imports: as it is, squashed to
    lower-case letters and digits, with its runs of white space single
    spaces, and as the set of its words. Read once a file, however many
    links cite it."""
    text = "\n".join(ln for ln in blob_lines(clone, sha, path)
                     if not ln.startswith("import "))
    return Body(text, re.sub(r"[^a-z0-9]", "", text.lower()),
                " ".join(text.split()), frozenset(WORD_RE.findall(text)))


@functools.lru_cache(maxsize=None)
def foreign_published(clone, sha):
    """Does one of CLONE's remote-tracking refs hold SHA?"""
    # origin's default branch first: one ancestry test, where the scan below
    # walks every remote ref, which in a GHC clone is seconds a commit.
    if subprocess.run(["git", "-C", clone, "merge-base", "--is-ancestor",
                       sha, "refs/remotes/origin/HEAD"], env=common.git_env(),
                      capture_output=True).returncode == 0:
        return True
    p = subprocess.run(["git", "-C", clone, "for-each-ref", "--count=1",
                        "--contains", sha, "refs/remotes"],
                       capture_output=True, text=True, env=common.git_env())
    return p.returncode == 0 and bool(p.stdout.strip())


def permalink(url, own, foreign):
    """(clone, sha, path, lo, hi) of a permalink this run checks, "." being
    this repository and lo None for a whole file; None for any other URL."""
    m = URL_RE.match(url)
    if m and (own is None or m.group(1).lower() == own):
        return (".", m.group(2), m.group(3), int(m.group(4)),
                int(m.group(5) or m.group(4)))
    for clone, rx in foreign_res(foreign):
        m = rx.match(url)
        if m:
            lo = int(m.group(3)) if m.group(3) else None
            return (clone, m.group(1), m.group(2), lo,
                    int(m.group(4) or m.group(3)) if lo is not None else None)
    return None


def paragraphs(text):
    """The document's paragraphs outside fenced code."""
    out, cur = [], []
    for line, kind, _info in common.fence_scan(text.split("\n")):
        if kind is None and line.strip():
            cur.append(line)
            continue
        if cur:
            out.append("\n".join(cur))
        cur = []
    if cur:
        out.append("\n".join(cur))
    return out


def norm_label(label):
    """A reference label as Markdown matches it: case and spacing folded."""
    return " ".join(label.split()).lower()


def trailing_end(masked, end, stop):
    """Where the words after a link that are about it end: a parenthesis
    opening right after it, else the clause it closes, up to a `;`, `:` or
    `. `, a parenthesis the link sits in closing, or STOP, the next link."""
    j = end
    while j < stop and masked[j] == " ":
        j += 1
    depth = 0
    for k in range(j, stop):
        ch = masked[k]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return k
            if depth == 0 and k > j and masked[j] == "(":
                return k + 1
        elif depth == 0 and (ch in ";:" or masked[k:k + 2] == ". "):
            return k
    return stop


def described(par, masked, uses, i):
    """The text that says what link I points at: its clause before it, back
    to the last `;`, `:` or `. ` since the previous link, and the words after
    it up to trailing_end. Words between two links count for both, the any
    of the check being lenient; a separator keeps a neighbour's clause out."""
    start, end = uses[i][0], uses[i][1]
    nxt = uses[i + 1][0] if i + 1 < len(uses) else len(masked)
    lo = uses[i - 1][1] if i else 0
    cuts = [m.end() for m in re.finditer(r"[;:] |\. ", masked[lo:start])]
    left = lo + (cuts[-1] if cuts else 0)
    return par[left:end] + " " + par[end:trailing_end(masked, end, nxt)]


def indent(ln):
    return len(ln) - len(ln.lstrip(" "))


def enclosing(lines, lo):
    """What names the cited line from above: the header of each definition
    it sits in, local ones included, and the title of the Note it sits in."""
    out = []
    level = indent(lines[lo - 1]) if lines[lo - 1].strip() else 10 ** 6
    for j in range(lo - 2, max(-1, lo - 2 - 400), -1):
        ln = lines[j]
        if ln.strip() and indent(ln) < level and not ln.lstrip().startswith(
                ("--", "{-", "-}", "#", ")", "]", "}", ",", "|", "~")):
            out.append(ln)
            level = indent(ln)
            if level == 0:
                break
    for j in range(lo, min(len(lines), lo + 200)):
        if re.match(r"[a-z_][\w']*\b[^=]*(?:::|=)", lines[j]):
            out.append(lines[j])        # the definition a comment documents
            break
    for j in range(lo - 1, -1, -1):
        if (re.match(r"\s*(?:\{-\s*)?Note \[[^\]]+\]\s*$", lines[j])
                and j + 1 < len(lines)
                and lines[j + 1].strip().startswith("~~~")):
            out.append(lines[j])
            break
    return out


def name_keys(code, note, quote):
    """What to look for in the source for one name beside a link: its
    identifiers of three letters or more, a flag also as the `Opt_` constant
    it sets, a Note's title, a quotation's words; nothing for a name too
    short to tell anything apart."""
    if note:
        return [note]
    if quote:
        return [" ".join(quote.split())]
    m = re.fullmatch(r"-[fdW](?:no-)?([a-z][a-z0-9-]*)(?:=.*)?", code)
    if m:
        return ["flag:" + m.group(1).replace("-", "")]
    return [k for k in IDENT_RE.findall(code) if k not in KEYWORDS]


def word_in(key, body):
    """Is KEY in BODY: as a whole identifier where it opens like one, and
    anywhere where it is a phrase or opens otherwise?"""
    if " " in key:
        return key in body.flat
    if not key[0].isalpha() and key[0] != "_":
        return key in body.text
    if WORD_RE.fullmatch(key):
        return key in body.words
    return re.search(r"(?<![\w'])" + re.escape(key) + r"(?![\w'])",
                     body.text) is not None


def names_path(code, path):
    """Is CODE the cited PATH, or its end after a slash? Such a name says
    which file a link cites, not which of its lines."""
    return bool(code) and ("/" + path).endswith("/" + code)


def check_links(text, own, foreign):
    """The links' own claims, apart from where their targets are: every
    label used is defined; a path-like link text is the end of its
    permalink; a `#L` continuation stays in the file its paragraph last
    named; and at least one name beside a permalink occurs near the line it
    cites. Returns the failures."""
    defs = {}
    for line, kind, _info in common.fence_scan(text.split("\n")):
        m = DEF_RE.match(line) if kind is None else None
        if m:
            defs.setdefault(norm_label(m.group(1)), m.group(2))
    failures = 0
    for par in paragraphs(text):
        masked = CODE_RE.sub(lambda m: " " * len(m.group(0)), par)
        uses = []
        for m in LINK_RE.finditer(masked):
            shown = par[m.start(1):m.end(1)]
            url = m.group(3)
            if url is None:
                label = m.group(2) or shown
                url = defs.get(norm_label(label))
                if url is None and shown.isdigit() \
                        and (m.group(2) or "").isdigit() \
                        and not any(k.isdigit() for k in defs):
                    # Sources cited footnote-style, `[7][9]` against a
                    # numbered list, in a document defining no numeric
                    # label: they render as written, as LambdaHack's wasm
                    # plan means them to.
                    continue
                if url is None:
                    print(f"FAIL [{shown}][{m.group(2)}] --- no definition"
                          f" of [{label}], so it renders as plain text")
                    failures += 1
                    continue
            uses.append((m.start(), m.end(), shown, url))
        last = None
        for i, (start, end, shown, url) in enumerate(uses):
            t = permalink(url, own, foreign)
            if t is None:
                continue
            clone, sha, path, lo, hi = t
            if PATHISH_RE.fullmatch(shown) and ("#" in shown or "/" in shown
                                                or "." in shown):
                cut = len(url) - len(shown)
                if not url.endswith(shown) or not (
                        shown.startswith("#") or url[cut - 1] == "/"):
                    print(f"FAIL [{shown}] --- the link text is not the end"
                          f" of its URL, {url}")
                    failures += 1
                if shown.startswith("#"):
                    if last is not None and path != last:
                        print(f"FAIL [{shown}] --- a continuation into {path},"
                              f" where its paragraph last named {last}")
                        failures += 1
                else:
                    last = path
            if lo is None:
                continue
            lines = blob_lines(clone, sha, path)
            if not lines or not 1 <= lo <= hi <= len(lines):
                continue                  # reported where the URL is checked
            names = [(name, name_keys(*name)) for name in
                     NAME_RE.findall(described(par, masked, uses, i))
                     if not names_path(name[0], path)]
            # A name the file does not hold, or holds in its imports alone,
            # is about something else, the program a draft describes most
            # often, and says nothing about the line.
            body = blob_body(clone, sha, path)
            names = [(name, [k for k in keys if (
                k[5:] in body.squashed if k.startswith("flag:")
                else word_in(k, body))]) for name, keys in names]
            names = [(name, keys) for name, keys in names if keys]
            if not names:
                continue
            near = "\n".join(lines[max(0, lo - 1 - NAME_WINDOW):
                                   hi + NAME_WINDOW]
                             + enclosing(lines, lo))
            flat = " ".join(near.split())
            squashed = re.sub(r"[^a-z0-9]", "", near.lower())
            # Near is a substring, case folded, where in the file is a whole
            # word: a name passes by sitting anywhere near the line, and
            # leniency there costs only a missed catch.
            folded = flat.lower()
            if not any(k[5:] in squashed if k.startswith("flag:") else
                       k.lower() in folded
                       for _name, keys in names for k in keys):
                said = ", ".join(f"`{c}`" if c else
                                 f"Note [{n}]" if n else f'"{q}"'
                                 for (c, n, q), _keys in names)
                span = f"L{lo}" if lo == hi else f"L{lo}-L{hi}"
                print(f"FAIL {path}#{span} @ {sha[:9]} --- none of {said}"
                      f" beside the link is within {NAME_WINDOW} lines of"
                      f" it")
                failures += 1
    return failures


@functools.lru_cache(maxsize=None)
def all_files_named(basename):
    # One find per basename: per citation it was one per `/.../` or bare
    # name, most of a run's time on a long document (check-plan-citations-08).
    # answered dropped-status: the find's failure is an empty listing, and
    # an empty listing is what the caller reports
    out = subprocess.run(
        ["bash", "-c",
         "find " + " ".join(SEARCH_ROOTS[:-1])
         + f" -name {basename} 2>/dev/null; ls {basename} 2>/dev/null"],
        capture_output=True, text=True).stdout.split()
    return sorted(set(out))


def resolve(name):
    """Return (path, error) --- exactly one of the two is None."""
    if "/.../" in name:
        prefix, suffix = name.split("/.../", 1)
        hits = [h for h in all_files_named(os.path.basename(name))
                if h.startswith(prefix) and h.endswith("/" + suffix)]
        if len(hits) == 1:
            return hits[0], None
        return None, f"wildcard resolves to {hits or 'nothing'}"
    if os.path.exists(name):
        return name, None
    hits = [h for h in all_files_named(os.path.basename(name))
            if h.endswith("/" + name)]
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, "UNRESOLVED"
    return None, f"AMBIGUOUS: {hits} --- qualify the citation"


def self_test():
    """Scratch-repository controls for every failing kind. Subprocess-driven:
    each case runs this script itself from the scratch repo, so extraction, resolution, git and the exit status are
    all the real thing. The module docstring records what each case
    proves."""
    if not shutil.which("git"):
        print("BLOCKED: git not on PATH, self-test did not run")
        return 2
    # The scratch repository is found by the cwd, by every git call here and
    # every run of this script: an inherited GIT_DIR took the commits to the
    # caller's repository (check-plan-citations-14).
    for k in common.GIT_LOCATION:
        os.environ.pop(k, None)
    script = os.path.abspath(__file__)
    prev = os.getcwd()
    bad = []

    def expect(case, got, want):
        if got != want:
            bad.append(f"{case}: got {got!r}, expected {want!r}")

    def contains(case, out, *needles):
        for n in needles:
            if n not in out:
                bad.append(f"{case}: output lacks {n!r}")

    def run(*argv, cwd=None, env=None):
        return subprocess.run([sys.executable, script] + list(argv),
                              capture_output=True, text=True, cwd=cwd,
                              env=env)

    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            def git(*a):
                subprocess.run(["git"] + list(a), check=True,
                               capture_output=True)

            def head(*a):
                return subprocess.run(["git", *a, "rev-parse", "HEAD"],
                                      capture_output=True, text=True,
                                      check=True).stdout.strip()
            common.scratch_repo()
            git("remote", "add", "origin", "https://github.com/x/y.git")
            open("a.hs", "w").write("line one\nline two\nline three\n")
            os.makedirs("sub")
            open("sub/b.py", "w").write("print(1)\n")
            open("note.md", "w").write("prose that\nwraps here\n")
            open(".dot.yaml", "w").write("key: value\n")
            os.makedirs("test")
            os.makedirs("tools")
            open("test/Dup.hs", "w").write("dup\n")
            open("tools/Dup.hs", "w").write("dup\n")
            open("d.json", "w").write("{}\n")
            open("s.sh", "w").write("true\n")
            open("sp.hs", "w").write("double  spaced   words\n")
            git("add", "-A")
            git("commit", "-qm", "c1")
            c1 = head()
            url = "https://github.com/x/y/blob/%s/a.hs"

            open("stop.md", "w").write("Link %s#L1 pinned.\n" % (url % c1))
            p = run("stop.md")
            expect("PUBLISHED_REF absent stops", p.returncode, 2)
            open("bad.md", "w").write("`a.hs:999999` not.\n")
            p = run("stop.md", "bad.md")
            expect("a failure outranks the stop", p.returncode, 1)
            contains("a failure outranks the stop", p.stdout + p.stderr,
                     "LINE-NUMBER", "does not exist here")

            git("update-ref", "refs/remotes/origin/master", c1)
            open("a.hs", "a").write("line four\n")
            git("commit", "-aqm", "c2")
            c2 = head()
            p = run("stop.md")
            expect("same link passes once the ref exists", p.returncode, 0)
            open("ok.md", "w").write("`a.hs:line one` fine.\n")
            open("bad.md", "w").write("`a.hs:999999` not.\n")
            p = run("ok.md", "bad.md")
            expect("every named document is checked", p.returncode, 1)
            contains("every named document", p.stdout, "=== bad.md ===",
                     "LINE-NUMBER")
            # The root is the repository holding the document, the cwd
            # outside every repository: these tools serve ~/slop's
            # repositories from ~/slop/tools.
            p = run(os.path.abspath("ok.md"), cwd=os.path.dirname(td))
            expect("the document names the root", p.returncode, 0)
            # The repository's settings file is read, and a name the
            # checker lacks stops the run rather than going unread.
            cfg = os.path.join("tools", "check-plan-citations.config.py")
            open(cfg, "w").write('PUBLISHED_REF = "origin/nosuch"\n')
            p = run("stop.md")
            expect("a setting from the file is taken", p.returncode, 2)
            open(cfg, "w").write("NOSUCH = 1\n")
            p = run("ok.md")
            expect("an unknown setting stops", p.returncode, 2)
            contains("an unknown setting stops", p.stderr, "NOSUCH")
            os.unlink(cfg)

            open("doc.md", "w").write(
                "# control\n\n"
                "`a.hs:1` line number, `a.hs:3-2` range and `a.hs:1,999999`\n"
                "list, refused alike, as is `note.md:1`.\n"
                "`NoSuchFile.hs:no such` unresolved, `Dup.hs:dup` ambiguous.\n"
                "`sub/b.py:print(1)` extracted too. `.dot.yaml:key: value`\n"
                "dotfile control. `d.json:{}` and `s.sh:true` are extensions\n"
                "beside it.\n"
                "`a.hs:line two` anchor control, @a.hs:line three@ its"
                " haddock twin, `a.hs:no such text` missing,\n"
                "`a.hs:line` ambiguous. `a.hs: line one` is a shell\n"
                "command and not a citation. `sp.hs:double spaced words`\n"
                "matches across a run of spaces. `note.md:that wraps`\n"
                "spans a wrap and matches the paragraph.\n"
                "%s#L1 pinned ok. %s#L99999 pinned range.\n"
                "%s#L0 pinned zero. %s#L3-L1 pinned backwards.\n"
                "https://github.com/ghc/ghc/blob/0123456789abcdef01234567"
                "89abcdef01234567/x.hs#L1 foreign.\n"
                "https://github.com/x/y/blob/0123456789abcdef01234567"
                "89abcdef01234567/a.hs#L1 own, commit missing.\n"
                "%s#L1-L3 unpublished.\n"
                % (url % c1, url % c1, url % c1, url % c1, url % c2))
            p = run("doc.md")
            expect("kitchen-sink document fails", p.returncode, 1)
            contains("kitchen-sink document", p.stdout,
                     "UNRESOLVED", "AMBIGUOUS", "UNPUBLISHED",
                     "not in this repository",
                     "in ghc/ghc, another repository, not checked",
                     "a.hs:1 --- LINE-NUMBER", "a.hs:3-2 --- LINE-NUMBER",
                     "a.hs:1,999999 --- LINE-NUMBER",
                     "note.md:1 --- LINE-NUMBER",
                     "ok   sub/b.py:1 <- 'print(1)'",
                     "ok   .dot.yaml:1 <- 'key: value'",
                     "ok   d.json:1 <- '{}'", "ok   s.sh:1 <- 'true'",
                     "ok   a.hs:2 <- 'line two'", "ok   a.hs:3 <- 'line three'",
                     "ok   sp.hs:1 <- 'double spaced words'",
                     "ok   note.md:paragraph 1 <- 'that wraps'",
                     "ANCHOR-MISSING", "ANCHOR-AMBIGUOUS (lines 1, 2, 3, 4",
                     "a.hs#L1 @", "13 failed", "#L0-L0 @", "#L3-L1 @")
            expect("a shell command's colon-space is not an anchor",
                   "' line one'" in p.stdout, False)
            p = run("../doc.md", cwd="sub")
            expect("same verdict from a subdirectory", p.returncode, 1)
            contains("same verdict from a subdirectory", p.stdout,
                     "13 failed")

            # A foreign repository checked through a local clone, mapped by
            # --foreign= so that these rows run whatever FOREIGN configures:
            # a published commit and a local-only one, one document holding
            # every failing kind beside its passing controls, and the two
            # stops, a commit and a clone missing here.
            src = (["module M where", "", "-- | foo's comment",
                    "foo :: Int", "foo = 1", ""]
                   + ["filler %d" % k for k in range(14)]
                   + ["bar :: Int -> Int", "bar x ="]
                   + ["    + %d" % k for k in range(20)]
                   + ["", "{- Note [Some note]", "~~~~~~~~~~~~~~~~~~",
                      "The note body says hello there."]
                   + ["more note %d" % k for k in range(20)]
                   + ["-}", "", "baz :: Int", "baz = 2"])

            def at(text):
                return src.index(text) + 1

            os.makedirs("fx/src")
            open("fx/src/M.hs", "w").write("\n".join(src) + "\n")
            open("fx/src/N.hs", "w").write("module N where\n")
            open("fx/src/Words.hs", "w").write(
                "alpha = 1\n" + "filler\n" * 19 + "-- Words here\n")

            def fgit(*a):
                git("-C", "fx", *a)
            common.scratch_repo("fx")
            fgit("add", "-A")
            fgit("commit", "-qm", "f1")
            fa = head("-C", "fx")
            fgit("update-ref", "refs/remotes/origin/main", fa)
            open("fx/src/N.hs", "a").write("-- local\n")
            fgit("commit", "-aqm", "f2")
            fb = head("-C", "fx")
            pre = "https://example.org/fx/-/blob/"
            fmap = "--foreign=" + pre + "=fx"
            deep = at("    + 19")
            note = at("more note 19")
            hello = at("The note body says hello there.")
            defs = {"f1": f"{fa}/src/M.hs#L{at('foo :: Int')}",
                    "f2": f"{fa}/src/M.hs",
                    "f3": f"{fa}/src/Nope.hs#L1",
                    "f4": f"{fa}/src/M.hs#L99999",
                    "f5": f"{fb}/src/N.hs#L1",
                    "f6": f"{fa}/src/M.hs#L4-5",
                    "f7": f"{fa}/src/N.hs#L1",
                    "f8": f"{fa}/src/M.hs#L{deep}",
                    "f9": f"{fa}/src/M.hs#L{note}",
                    "fa": f"{fa}/src/M.hs#L{hello}",
                    "fw": f"{fa}/src/Words.hs#L1"}
            open("f.md", "w").write(
                "Ok, `foo` at [src/M.hs#L4][f1]; the file, [src/M.hs][f2];"
                " a GitLab range, [src/M.hs#L4-5][f6] (`foo`).\n\n"
                "A missing path [src/Nope.hs#L1][f3], a range [x][f4],"
                " an unpublished commit [src/N.hs#L1][f5].\n\n"
                "Sources [7][9], footnote-style.\n\n"
                "An undefined label [y][nosuch]. Text naming another line,"
                " [src/M.hs#L5][f1].\n\n"
                "[src/M.hs#L4][f1] and then [#L1][f7], into another file.\n\n"
                "A far name: [src/M.hs#L4][f1] (`baz`). A name the file does"
                " not hold says nothing: [src/M.hs#L4][f1] (`Repro`).\n\n"
                "Inside `bar`, [src/M.hs#L%d][f8]; inside Note [Some note],"
                " [src/M.hs#L%d][f9]; quoted, \"says hello there\""
                " [src/M.hs#L%d][fa].\n\n" % (deep, note, hello)
                + "The file's own name, [`src/Words.hs`, line 1][fw].\n\n"
                + "".join(f"[{k}]: {pre}{v}\n" for k, v in defs.items()))
            p = run("f.md", fmap)
            expect("foreign kitchen sink fails", p.returncode, 1)
            contains("foreign kitchen sink", p.stdout,
                     "ok   src/M.hs#L4 @", "ok   src/M.hs @",
                     "ok   src/M.hs#L4-L5 @",
                     "no such path in fx", "OUT-OF-RANGE", "UNPUBLISHED",
                     "no definition of [nosuch]",
                     "[src/M.hs#L5] --- the link text is not the end",
                     "[#L1] --- a continuation into src/N.hs",
                     "none of `baz`", "7 failed")
            for quiet in ("`Repro`", "none of `src/Words.hs`",
                          "no definition of [9]",
                          f"#L{deep} @ {fa[:9]} --- none",
                          f"#L{note} @ {fa[:9]} --- none",
                          f"#L{hello} @ {fa[:9]} --- none"):
                if quiet in p.stdout:
                    bad.append(f"foreign kitchen sink: {quiet!r} reported")
            open("nd.md", "w").write(
                "Sources [7][9], beside a numeric label.\n\n"
                "[1]: https://example.com/\n")
            p = run("nd.md")
            expect("a numeric label defined makes [7][9] a link",
                   p.returncode, 1)
            contains("a numeric label defined makes [7][9] a link",
                     p.stdout, "no definition of [9]")
            open("fb.md", "w").write(
                f"[src/M.hs#L1][z]\n\n[z]: {pre}{'0' * 40}/src/M.hs#L1\n")
            p = run("fb.md", fmap)
            expect("a commit missing from the clone blocks", p.returncode, 2)
            contains("a commit missing from the clone blocks", p.stderr,
                     "is not in fx")
            p = run("fb.md", "--foreign=" + pre + "=nowhere")
            expect("a clone missing here blocks", p.returncode, 2)
            contains("a clone missing here blocks", p.stderr,
                     "nowhere is not a git repository")
            # With origin/HEAD set, the ancestry test alone says a commit on
            # it is published, the scan of the remote refs never reached.
            fgit("symbolic-ref", "refs/remotes/origin/HEAD",
                 "refs/remotes/origin/main")
            open("fh.md", "w").write(
                f"[src/N.hs#L1][h]\n\n[h]: {pre}{fa}/src/N.hs#L1\n")
            p = run("fh.md", fmap)
            expect("a commit on origin/HEAD is published", p.returncode, 0)
            contains("a commit on origin/HEAD is published", p.stdout,
                     "ok   src/N.hs#L1 @")
        finally:
            os.chdir(prev)
    for b in bad:
        print(f"FAIL: {b}")
    if not bad:
        print("ok:   every self-test case behaved as expected")
    return 1 if bad else 0


def main():
    global FOREIGN_RUN
    extra = {}
    for a in sys.argv[1:]:
        if a.startswith("--foreign="):
            prefix, _, clone = a[len("--foreign="):].partition("=")
            if not prefix or not clone:
                print("--foreign takes PREFIX=CLONE", file=sys.stderr)
                sys.exit(2)
            extra[prefix] = clone
    flags = {a for a in sys.argv[1:]
             if a.startswith("--") and not a.startswith("--foreign=")}
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    unknown = flags - {"--self-test"}
    if unknown:
        print(f"unknown flag(s): {' '.join(sorted(unknown))};"
              f" only --self-test and --foreign= are understood",
              file=sys.stderr)
        sys.exit(2)
    # From the root before anything, the self-test included, as every
    # checker here does: this one's self-test names no root-relative path,
    # but two siblings' did and reported wrongly from a subdirectory.
    docs = common.chdir_root(args)
    globals().update(common.repo_config(
        "check-plan-citations", {k: globals()[k] for k in SETTINGS}))
    FOREIGN_RUN = {**FOREIGN, **extra}
    if "--self-test" in flags:
        return self_test()
    docs = docs or ["CLAUDE.md"]
    common.require_readable(docs)
    # Every document named is checked. Until 2026-08-28 only the first was,
    # and the rest reported nothing while the run exited 0.
    results = []
    for doc in docs:
        if len(docs) > 1:
            print(f"=== {doc} ===")
        results.append(check(doc))
    # A failure outranks a document that could not be checked, as
    # check-all aggregates its steps.
    return 1 if 1 in results else (2 if 2 in results else 0)


def check(doc):
    """Check one document; its exit status."""
    text = open(doc, encoding="utf-8").read()
    # Citations, permalinks, links and the names beside them are read off
    # the unwrapped form, a link's text or a code span a line break split
    # having gone unread (check-plan-citations-16, -17).
    flat, ran = common.unwrapped(text)
    if not ran:
        print("NOTE: wrap80 is not on PATH, so a link or a name a line break"
              " splits went unread", file=sys.stderr)
    # A line number is refused wherever it points, resolving or not: a
    # commit above the line slides it onto other text while it still
    # resolves, and into a document the formatter moves it at every reflow.
    numbers = sorted({m.group(1) + ":" + m.group(2)
                      for m in CITE_RE.finditer(flat)})
    failures = 0
    blocked = False
    for cite in numbers:
        print(f"FAIL {cite} --- LINE-NUMBER (cite a text anchor, or a"
              f" permalink pinned to the tree the sentence describes)")
        failures += 1
    anchors = sorted({(m.group(2), m.group(3))
                      for m in ANCHOR_RE.finditer(flat)})
    for name, anchor in anchors:
        path, err = resolve(name)
        if err:
            print(f"FAIL {name}:{anchor} --- {err}")
            failures += 1
            continue
        text_ = open(path, encoding="utf-8", errors="replace").read()
        unit = "line"
        if name.endswith(".md"):
            # Prose is matched per paragraph: a wrap can fall inside any
            # phrase and moves with every edit above it, so the line is
            # not the unit. wrap80 defines the paragraph, as it does for
            # check-doc-refs.py; without it the run did not happen.
            if not shutil.which("wrap80"):
                print("stopping: wrap80 is not on PATH, so an anchor into"
                      f" {name} cannot be matched per paragraph",
                      file=sys.stderr)
                sys.exit(2)
            text_ = subprocess.run(["wrap80", "--unwrap"], input=text_,
                                   text=True, capture_output=True,
                                   check=True).stdout
            unit = "paragraph"
        lines_ = text_.splitlines()
        # Whitespace runs collapse on both sides: the formatter collapses
        # them in the document, and source aligns with them.
        norm = " ".join(anchor.split())
        hits = [i for i, ln in enumerate(lines_, 1)
                if norm in " ".join(ln.split())]
        if not hits:
            print(f"FAIL {name}:{anchor} --- ANCHOR-MISSING (no {unit} of"
                  f" {path} contains it)")
            failures += 1
            continue
        if len(hits) > 1:
            print(f"FAIL {name}:{anchor} --- ANCHOR-AMBIGUOUS ({unit}s"
                  f" {', '.join(map(str, hits))} all contain it; lengthen"
                  f" the anchor)")
            failures += 1
            continue
        where = f"{hits[0]}" if unit == "line" else f"paragraph {hits[0]}"
        print(f"ok   {name}:{where} <- {anchor!r}"
              f" | {lines_[hits[0] - 1].strip()[:80]}")
    urlcites = sorted({(m.group(1).lower(), m.group(2), m.group(3),
                        int(m.group(4)), int(m.group(5) or m.group(4)))
                       for m in URL_RE.finditer(flat)})
    # The repository PUBLISHED_REF's remote names; None, no such remote or
    # not on GitHub, leaves every link checked as this repository's.
    own = common.github_repo(PUBLISHED_REF.split("/", 1)[0])
    for slug, sha, path, lo, hi in urlcites:
        if own is not None and slug != own:
            print(f"note {path}#L{lo}-L{hi} @ {sha[:9]} --- in {slug},"
                  f" another repository, not checked")
            continue
        proc = subprocess.run(["git", "show", f"{sha}:{path}"],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"FAIL {path}#L{lo}-L{hi} @ {sha[:9]} --- commit or path"
                  f" not in this repository")
            failures += 1
            continue
        lines = proc.stdout.splitlines()
        if lo < 1 or lo > hi or hi > len(lines):
            print(f"FAIL {path}#L{lo}-L{hi} @ {sha[:9]} --- OUT-OF-RANGE "
                  f"(file has {len(lines)} lines at that commit)")
            failures += 1
            continue
        pub = published(sha)
        if pub is None:
            # The document's status, not the run's: an exit here folded
            # earlier documents' FAIL verdicts into the stop and left the
            # later ones unchecked (check-plan-citations-09).
            if not blocked:
                print(f"BLOCKED: {PUBLISHED_REF} does not exist here, so"
                      f" whether {sha[:9]} is published cannot be told."
                      f" Fetch it, or set PUBLISHED_REF to the ref this"
                      f" repository publishes from.", file=sys.stderr)
            blocked = True
            continue
        if not pub:
            print(f"FAIL {path}#L{lo}-L{hi} @ {sha[:9]} --- UNPUBLISHED"
                  f" (resolves here but is not an ancestor of"
                  f" {PUBLISHED_REF}, so the link may 404 for everyone else)")
            failures += 1
            continue
        span = f"L{lo}" if lo == hi else f"L{lo}-L{hi}"
        print(f"ok   {path}#{span} @ {sha[:9]}"
              f" | {lines[lo - 1].strip()[:70]}")
    # Permalinks into a repository a local clone here can check, by the same
    # verdicts on that clone. A clone or a commit missing here is no verdict
    # on the document, so it blocks rather than fails.
    foreign = sorted({(clone, m.group(1), m.group(2), m.group(3) or "",
                       m.group(4) or m.group(3) or "")
                      for clone, rx in foreign_res(FOREIGN_RUN)
                      for m in rx.finditer(flat)})
    absent = collections.Counter()
    for clone, sha, path, lo, hi in foreign:
        where = path + (f"#L{lo}" + (f"-L{hi}" if hi != lo else "")
                        if lo else "")
        if not is_clone(clone):
            absent[(clone, None)] += 1
            continue
        lines = blob_lines(clone, sha, path)
        if lines is None:
            absent[(clone, sha)] += 1
            continue
        if lines is False:
            print(f"FAIL {where} @ {sha[:9]} --- no such path in {clone} at"
                  f" that commit")
            failures += 1
            continue
        lo, hi = (int(lo), int(hi)) if lo else (None, None)
        if lo is not None and (lo < 1 or lo > hi or hi > len(lines)):
            print(f"FAIL {where} @ {sha[:9]} --- OUT-OF-RANGE (file has"
                  f" {len(lines)} lines at that commit)")
            failures += 1
            continue
        if not foreign_published(clone, sha):
            print(f"FAIL {where} @ {sha[:9]} --- UNPUBLISHED (in {clone}, but"
                  f" no remote-tracking ref there holds it, so the link"
                  f" may 404 for everyone else)")
            failures += 1
            continue
        print(f"ok   {where} @ {sha[:9]}"
              + (f" | {lines[lo - 1].strip()[:70]}" if lo else
                 f" ({len(lines)} lines)"))
    for (clone, sha), n in sorted(absent.items(), key=str):
        blocked = True
        if sha is None:
            print(f"BLOCKED: {clone} is not a git repository here, so {n}"
                  f" permalink(s) into it were not checked", file=sys.stderr)
        else:
            print(f"BLOCKED: commit {sha[:10]} is not in {clone}, so {n}"
                  f" permalink(s) pinning it were not checked; fetch it,"
                  f" `git -C {clone} fetch origin`, and re-run",
                  file=sys.stderr)
    failures += check_links(flat, own, FOREIGN_RUN)
    print(f"\n{len(numbers) + len(anchors) + len(urlcites) + len(foreign)}"
          f" citations checked,"
          f" {failures} failed"
          f" --- now eyeball the snippets against the document's claims.")
    return 1 if failures else (2 if blocked else 0)


if __name__ == "__main__":
    sys.exit(main())
