"""Settings for ~/slop/tools/check-plan-citations.py in ~/slop itself, read by
its common.repo_config.
"""

# The directories a cited file is looked for under, the root included.
SEARCH_ROOTS = ["tools", "docs",
                # The filed issue bodies cite horde-ad's files by their path
                # in horde-ad, and stay as filed.
                "horde-ad/src", "horde-ad/test", "horde-ad/bench",
                "horde-ad/example", "horde-ad/docs", "horde-ad/.claude", "."]
PUBLISHED_REF = "origin/master"
# GHC's permalinks are checked in horde-ad's GHC clone, the one holding every
# commit the filed issues pin: ghc/, the GHC to build with, lacks 6913545fd3,
# a commit of wip/T27737 that no remote holds, until that branch is fetched
# into it. horde-ad's own permalinks are checked in its checkout.
FOREIGN = {"https://gitlab.haskell.org/ghc/ghc/-/blob/": "horde-ad/ghc",
           "https://github.com/Mikolaj/horde-ad/blob/": "horde-ad"}
