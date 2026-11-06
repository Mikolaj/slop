# GHC issue: `-dumpdir` is ignored when the source file is given by an absolute path

Filed as GHC [#28096](https://gitlab.haskell.org/ghc/ghc/-/work_items/28096) on 2026-11-06. This file stays as the filed record, the text from "## Summary" down being the body staged for it, in the tracker's bug template. Title: **`-dumpdir` is ignored when the source file is given by an absolute path**. Verified on 2026-11-06 with ghc-9.14.1 and a build of master 37ad471050 (10.1.20261103), from the commands as shown here, and with 9.12.4 and 9.6.7 for a source given by an absolute path with `-c`; the links pin 3d326d7d28, whose code there is the same as 37ad471050's. Met when two compilers compiled one module by its absolute path, each with its own `-dumpdir`, and the second's dumps overwrote the first's beside the source. The cause was named on GHC [#26968](https://gitlab.haskell.org/ghc/ghc/-/work_items/26968) in [note 660944](https://gitlab.haskell.org/ghc/ghc/-/work_items/26968#note_660944) of 2026-03-02; a tracker search for "dumpdir" finds no issue or MR about it since.

## Summary

The user's guide says `-dumpdir` "Redirects all dump files into" its directory ([separate_compilation.rst, lines 342-348][doc]). But `chooseDumpFile` names a dump file `setDir (prefix ++ suffix)` ([Logger.hs, lines 532-535][choose]), `setDir f` being `d </> f` for `-dumpdir d` ([Logger.hs, lines 571-573][setdir]), and for a source file the prefix is the source's path without its extension, directories kept ([Pipeline.hs, line 779][split], [Pipeline.hs, lines 789-791][setprefix]). `</>` returns an absolute right operand unchanged and keeps a relative one's directories, so:

- a source given by an absolute path, or found through an absolute `-i`, gets its dumps beside it;
- `src/M.hs` gets them in `d/src/`, and `../src/M.hs` in `d/../src/`, beside it again;
- only a source in the current directory gets them in `d`.

`-odir` and `-hidir` in the same command put the object and interface files in their directory by the module's name, as `dd/M.o` or `dd/A/B.o` below. `-outputdir` sets the dump directory with the same effect, and `-c` and `--make` behave alike. So two builds of one module given by its absolute path, each with its own `-dumpdir`, write the same dump files, the second over the first.

[#26968](https://gitlab.haskell.org/ghc/ghc/-/work_items/26968#note_660944) named the `</>` in a note: "the `setDir f` code path in `GHC.Utils.Logger` uses `</>` and doesn't work when the right operand is absolute path".

## Steps to reproduce

```
mkdir -p src dd
printf 'module M where\nf :: Int -> Int\nf x = x + 1\n' > src/M.hs
ghc -c "$PWD/src/M.hs" -odir dd -hidir dd -dumpdir dd -ddump-simpl -ddump-to-file
ls dd src
```

prints

```
dd:
M.hi
M.o

src:
M.dump-simpl
M.hs
```

With `src/M.hs` in place of `"$PWD/src/M.hs"`, the dump goes to `dd/src/M.dump-simpl`. For a module `A.B` in `src/A/B.hs`, compiled the same way with `src/A/B.hs`, `-odir dd` gives `dd/A/B.o` and the dump goes to `dd/src/A/B.dump-simpl`.

## Expected behavior

The dump in `dd`, beside the object and interface files. Naming the dump by the module's name under the dump directory, as `-odir` names `dd/A/B.o`, would keep apart the dumps of modules whose files share a name. Until then, `-ddump-file-prefix=M` puts the dump at `dd/M.dump-simpl`.

## Environment

* GHC version used: 9.14.1, and master at 37ad471050 (10.1.20261103)

Optional:

* Operating System: Linux
* System Architecture: x86_64

[doc]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/docs/users_guide/separate_compilation.rst#L342-348
[choose]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Utils/Logger.hs#L532-535
[setdir]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Utils/Logger.hs#L571-573
[split]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Driver/Pipeline.hs#L779
[setprefix]: https://gitlab.haskell.org/ghc/ghc/-/blob/3d326d7d28ee5d51c9ae42ae1baf1c5a4500d185/compiler/GHC/Driver/Pipeline.hs#L789-791

/label ~"T::bug"
/label ~"driver"
/label ~"llm-derived::reproducer"
/label ~"needs triage"
