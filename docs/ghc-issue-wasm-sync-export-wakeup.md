# GHC issue: a wasm JSFFI sync export does not run the threads it wakes

Filed as GHC [#28010](https://gitlab.haskell.org/ghc/ghc/-/work_items/28010) on 2026-10-21; the text from "## Summary" down is the filed body, in the tracker's bug template. Title: **wasm: a JSFFI sync export does not run the threads it wakes, so they wait for an unrelated event**. Verified on 2026-10-21 with ghc-wasm-meta's 9.12 toolchain, GHC 9.12.4.20260402, under Node.js 26.4.0; the cited wasm code --- JSFFI.c, scheduler.cmm, Exports.hs and the export desugaring in Wasm.hs --- is the same on master `3d326d7d28` as on the `ghc-9.12` branch up to imports, the text type of the export label and the `ByteArray#` import types. That a later sync export runs queued threads only until its own thread finishes, and that an async export called at once runs them all, were measured the same day with a `noop sync` export added to the reproducer. Found in LambdaHack's browser frontend, whose sync `lhKey` export calls `rts_scheduleWork` for this reason. A tracker search of 2026-10-21 found no report. The proposed fix is not tested. The prose is ASD-STE100 Simplified Technical English.

## Summary

A JSFFI sync export can wake other Haskell threads, for example with `putMVar`. These threads do not run when the export returns. They wait until a later event enters the RTS scheduler, for example a call to an async export or a settled Promise of an async import. If no such event comes, they do not run. In a browser, this occurs when a sync `keydown` handler gives a key to an idle application: the handler wakes the application's thread, and that thread does not run until the next unrelated event. A sync export is necessary there, because only a sync handler can call `preventDefault` in time.

An async export does not have this problem. The JavaScript backend does not have it either.

The cause: a sync export uses the C FFI top handler. Its stub calls `rts_inCall` ([Wasm.hs, lines 741-759](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/HsToCore/Foreign/Wasm.hs#L741-759)), and the scheduler returns when the export's own thread finishes ([Schedule.c, line 590](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/Schedule.c#L590)). A thread that the export woke stays in the run queue. In a reactor, nothing runs it until JavaScript calls into the RTS again. A later sync export runs the queued threads only until its own thread finishes. The following calls run the scheduler loop, which runs threads until the run queue is empty:

- an async export, whose `runIO` runs `stg_scheduler_loop#` after it forks the work ([Exports.hs, lines 63-80](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/libraries/ghc-internal/src/GHC/Internal/Wasm/Prim/Exports.hs#L63-80));
- a Promise callback, which calls `rts_schedulerLoop` ([JSFFI.c, lines 254-259](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/wasm/JSFFI.c#L254-259)), and the `throwTo` of an async export's Promise, which calls it too ([JSFFI.c, line 314](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/wasm/JSFFI.c#L314));
- the `setImmediate` that the scheduler loop requests with `rts_scheduleWork` when it stops after 15 ms ([scheduler.cmm, line 176](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/wasm/scheduler.cmm#L176)).

Note [Async JSFFI scheduler] says that the loop is "idempotent, it's safe to run it multiple times, now or later, though it's not safe to forget to run it when there's still thread that needs to make progress" ([scheduler.cmm, lines 72-74](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/wasm/scheduler.cmm#L72-74)). The sync export path does not run it.

In the JavaScript backend, `h$wakeupThread` puts the thread in the run queue and calls `h$startMainLoop()`, which schedules the main loop with `setImmediate` ([thread.js, lines 393-404](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/js/thread.js#L393-404)). Thus a thread that a synchronous callback wakes runs soon.

A `yield` at the end of the sync export is not a fix. The export's thread goes to the end of the run queue, and the woken thread runs. But when the woken thread wakes a third thread, that thread goes to the end of the queue, after the export's thread. The export's thread then finishes, the scheduler returns, and the third thread stays in the queue. `pokeYield` below shows this.

### Proposed fix

When a sync export returns and threads are in the run queue, request a scheduler run. For example, add this after `rts_scheduleWork` ([JSFFI.c, lines 238-241](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/rts/wasm/JSFFI.c#L238-241)):

```c
void rts_inCallSync(Capability **cap, HaskellObj p, HaskellObj *ret) {
  rts_inCall(cap, p, ret);
  if (!emptyRunQueue(*cap)) {
    rts_scheduleWork();
  }
}
```

Then make the sync export stub call `rts_inCallSync` instead of `rts_inCall`. This also covers `"wrapper sync"`, which uses the same stub. The scheduler loop is idempotent, thus an extra run is safe. I did not test this fix. An alternative is the design of the JavaScript backend: request a scheduler run when a thread becomes runnable outside the scheduler loop.

The section on sync exports in the user's guide ([wasm.rst, lines 508-512](https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/docs/users_guide/wasm.rst#L508-512)) does not mention this behaviour. Until a fix is available, a sentence there can tell users to use a workaround below.

## Steps to reproduce

`Repro.hs`:

```haskell
module Repro where

import Control.Concurrent
import Control.Monad
import System.IO.Unsafe

-- Two waiters in a chain: the first wakes on 'box', reports 1 and wakes
-- the second through 'relay', which reports 2.
{-# NOINLINE box #-}
box :: MVar ()
box = unsafePerformIO newEmptyMVar

{-# NOINLINE relay #-}
relay :: MVar ()
relay = unsafePerformIO newEmptyMVar

foreign import javascript unsafe "globalThis.woken($1)"
  js_woken :: Int -> IO ()

start :: IO ()
start = do
  _ <- forkIO $ forever $ takeMVar box >> js_woken 1 >> putMVar relay ()
  _ <- forkIO $ forever $ takeMVar relay >> js_woken 2
  pure ()

foreign export javascript "start" start :: IO ()

-- Wake the first waiter from a sync export.
poke :: IO ()
poke = putMVar box ()

foreign export javascript "poke sync" poke :: IO ()

-- The same, then yield.
pokeYield :: IO ()
pokeYield = putMVar box () >> yield

foreign export javascript "pokeYield sync" pokeYield :: IO ()

-- The same, then ask for a scheduler run.
foreign import ccall unsafe "rts_scheduleWork" rts_scheduleWork :: IO ()

pokeSchedule :: IO ()
pokeSchedule = putMVar box () >> rts_scheduleWork

foreign export javascript "pokeSchedule sync" pokeSchedule :: IO ()

-- An async export that does nothing.
nudge :: IO ()
nudge = pure ()

foreign export javascript "nudge" nudge :: IO ()
```

`run.mjs`:

```js
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { WASI } from 'node:wasi';

const [, , wasmPath, jsffiPath] = process.argv;
const woken = [];
globalThis.woken = (n) => woken.push(n);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const wasi = new WASI({ version: 'preview1', args: ['repro'], env: {}, returnOnExit: true });
const exports = {};
const { default: mkImports } = await import(pathToFileURL(resolve(jsffiPath)).href);
const { instance } = await WebAssembly.instantiate(readFileSync(wasmPath), {
  wasi_snapshot_preview1: wasi.wasiImport,
  ghc_wasm_jsffi: mkImports(exports),
});
Object.assign(exports, instance.exports);
wasi.initialize(instance);
await exports.start();

for (const name of ['poke', 'pokeYield', 'pokeSchedule']) {
  woken.length = 0;
  exports[name]();
  await sleep(1000);
  console.log(`${name}: woken ${JSON.stringify(woken)} 1 s later`);
  await exports.nudge();
  console.log(`${name}: woken ${JSON.stringify(woken)} after nudge()`);
}
```

Build and run:

```
wasm32-wasi-ghc Repro.hs -o repro.wasm -no-hs-main -optl-mexec-model=reactor \
  '-optl-Wl,--export=start,--export=poke,--export=pokeYield,--export=pokeSchedule,--export=nudge'
"$(wasm32-wasi-ghc --print-libdir)"/post-link.mjs -i repro.wasm -o repro.js
node --no-warnings run.mjs repro.wasm repro.js
```

Output:

```
poke: woken [] 1 s later
poke: woken [1,2] after nudge()
pokeYield: woken [1] 1 s later
pokeYield: woken [1,2] after nudge()
pokeSchedule: woken [1,2] 1 s later
pokeSchedule: woken [1,2] after nudge()
```

After `poke`, neither waiter runs for 1 s. They run only when the unrelated `nudge()` enters the scheduler. After `pokeYield`, only the first waiter runs.

## Expected behavior

After `poke` and `pokeYield`, both waiters run soon, without another event: `woken [1,2] 1 s later`, as after `pokeSchedule`.

### Workarounds

- At the end of the sync export, call `rts_scheduleWork`, as `pokeSchedule` does. No public header declares `rts_scheduleWork`, thus a later GHC can remove or change it without notice.
- After the sync export, call any async export, for example an empty one, as `nudge` does.

## Environment

* GHC version used: 9.12.4.20260402 (ghc-wasm-meta, `wasm32-wasi-ghc`), with Node.js 26.4.0

Optional:

* Operating System: Linux
* System Architecture: x86_64

/label ~"T::bug"
/label ~"wasm"
/label ~"FFI"
/label ~"needs triage"
