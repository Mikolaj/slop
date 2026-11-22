-- | criterion's API, as far as megaparsec's bench-speed uses it, measured by
-- tasty-papi: each benchmark's allocation and instruction counts over one run;
-- env as tasty-bench's, its value forced before any benchmark runs.
module Criterion.Main (module Test.Tasty.PAPI, env) where

import Control.DeepSeq (NFData, force)
import Control.Exception (evaluate)
import System.IO.Unsafe (unsafePerformIO)
import Test.Tasty (withResource)
import Test.Tasty.PAPI

env :: NFData e => IO e -> (e -> Benchmark) -> Benchmark
env res f = withResource (res >>= evaluate . force) (const (pure ())) (f . unsafePerformIO)
