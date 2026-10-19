"""Settings for ~/slop/tools/check-doc-refs.py in ~/slop itself, read by its
common.repo_config. ~/slop's documents name its own `tools/` and `docs/`, and
a repository inside it by its path from here, `horde-ad/src/...`, which
resolves as it stands.
"""

SEARCH_ROOTS = ["tools", "docs",
                # The filed issue bodies name horde-ad's files by their path
                # in horde-ad, and stay as filed: resolved there, by suffix.
                # No search walks a whole repository, ghc/ among them.
                "horde-ad/src", "horde-ad/test", "horde-ad/bench",
                "horde-ad/example", "horde-ad/docs", "horde-ad/.claude",
                "horde-ad/.github"]
# orthotope's and ox-arrays' files, which the issues name by their path in
# those checkouts, resolved for real as horde-ad's documents resolved them.
SIBLING_ROOTS = ["orthotope", "ox-arrays"]
ALLOW_FILE = "tools/doc-refs-allow.txt"
