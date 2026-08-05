# Design: Cross-platform Python pipeline for dspico-resources-compiler

Date: 2026-08-05
Status: Approved (design), pending implementation plan

## Problem

The build orchestrator works, but two properties it needs are missing:

1. **It only runs on Linux hosts.** `build_resources.sh` is POSIX `sh`, the Docker image bootstraps an
   x86_64-only toolchain, and the container's build user is hardcoded to UID/GID 1000.
2. **Nothing is tested.** 776 lines of shell across two scripts, with all decision logic (which steps
   run, which ROM goes in which firmware slot, whether a ROM needs padding) inlined among the I/O.
   Shell has no viable mutation-testing tooling, so the current structure cannot reach the quality bar
   the project asks for.

The work inside the container is already OS-independent by construction — it runs in a Linux
container regardless of host. What is Linux-bound is the *shell*: the host launcher, the image's
architecture assumption, and file ownership of the outputs.

## Goals

- `dspico build` runs on Windows (native PowerShell/CMD, no WSL), macOS on Apple Silicon, Linux with
  any UID, and WSL2/Git Bash.
- All decision logic is pure, unit-tested via TDD, and gated at a 100% mutation score.
- Migration carries zero regression risk: the shell pipeline stays as a reference implementation
  until the user validates the Python one against a real build.

## Non-goals

- **Podman support.** Runtime detection is centralized in `hostenv.py` so it can be added later, but
  v1 assumes `docker`. Doing podman properly requires `--userns=keep-id` and different UID semantics.
- **Running a real end-to-end build in CI.** It needs the user's copyrighted Blowfish tables and BIOS
  dumps. CI verifies the image builds and the logic is correct; the genuine build stays a manual step.
- **Backwards compatibility of the CLI.** Env-var flags are replaced by CLI flags outright.

## Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+, stdlib-only at runtime | Only option that gives native Windows, arm64 handling, UID mapping *and* real mutation tooling. `python3` is already in the image. |
| Host requirement | Python 3.11+ installed | Single documented prerequisite. No `pip install` for normal use. |
| CLI | Flags only (`--wrfuxxed`, `--ntrboot`, `--edo-firmware`) | `ENABLE_X=1 ./script` is not valid PowerShell syntax. Env vars are dropped, not kept as fallback. |
| Migration | Parallel — shell survives until user validates | The user is the only one who can run a real build. A reference implementation makes divergence debuggable. |
| Mutation tool | `mutmut` | Faster than cosmic-ray, direct pytest integration. |

## Architecture

The organizing principle is **separate decision from effect**. Everything that decides is pure and
fully testable; everything that executes goes through one injectable seam.

```text
dspico/                    # stdlib-only at runtime
  __main__.py              # python -m dspico
  cli.py                   # argparse -> BuildConfig
  config.py                # BuildConfig (frozen dataclass) + validation   <- PURE
  hostenv.py               # host arch, uid/gid, container runtime, paths  <- PURE
  runtime.py               # the ONLY module importing subprocess
  host/
    image.py               # docker build: --platform, --build-arg UID/GID
    launcher.py            # docker run: mounts, env, entrypoint
  pipeline/
    plan.py                # which steps, what order, real numbering       <- PURE
    rom.py                 # padding decisions, ntrboot 3DS/DSi slotting   <- PURE
    artifacts.py           # find_artifact, copy_glob, write_build_info
    upstream.py            # upstream.lock.json read/write, clone pinning
    steps/
      dldi.py  bootloader.py  encryptor.py  wrfuxxed.py  firmware.py
      pico_loader.py  pico_launcher.py  sd_card.py  ntrboot.py
```

Every step takes `(config, runner, paths)` and returns its produced artifacts explicitly. This kills
the shell version's shared-global contract (`DLDI_FILE`, `BOOTLOADER_NDS`, `ENCRYPTED_NDS`,
`ENCRYPTOR_BIN` set by one step and read by another) — the dependency becomes a function signature
the type checker enforces.

With `runtime.run()` as the single subprocess seam, tests inject a `FakeRunner` that records `argv`.
No Docker, no network, no toolchain needed to test the pipeline.

### Why this shape enables mutation testing

Mutants in `plan.py` / `rom.py` / `config.py` / `hostenv.py` are killed by fast pure unit tests.
Mutants in `steps/` and `host/` are killed by asserting the exact command the step would emit. Without
the decision/effect split, most mutants would be unreachable without a real build, and the score would
be meaningless.

## Defects the migration fixes

Found by reading the current pipeline. Each becomes a regression test.

| Location | Defect |
| --- | --- |
| `compile_resources.sh:131` | `compute_steps` computes `TOTAL_STEPS`, but step labels are hardcoded (`step "5/$TOTAL_STEPS"`). The numbering lies. |
| `compile_resources.sh:300` | `sed ... \|\| true` against upstream `CMakeLists.txt`. If upstream renames `DSPICO_ENABLE_WRFUXXED`, the exploit is silently dropped from the build. Must assert the substitution applied. |
| `compile_resources.sh:74` | `find ... \| head -n 1` picks an arbitrary match when several exist, silently. |
| `compile_resources.sh:329-341` | `has_3ds`/`has_dsi` slot matrix, four branches, no tests. |
| `compile_resources.sh:518` | `. wf-env \|\| true` — a failed source lets the build continue with a broken toolchain. |
| `compile_resources.sh:93` | `copy_glob` uses `[ -e "$f" ] && cp` under `set -e`, and does not fail when the glob matches nothing. |
| `compile_resources.sh:119` | `truncate -s 32768` would truncate, not pad, if the size guard were ever wrong. Covered by a property test. |

## Portability

| Host | What breaks today | Fix |
| --- | --- | --- |
| Windows native | `build_resources.sh` is `sh` | `py -m dspico build`. `subprocess` without `shell=True` means no path mangling — the Git Bash `/inputs` -> `C:/Program Files/Git/inputs` failure mode disappears. `.gitattributes` forces LF on container-bound files; scripts are invoked as `bash script`, never relying on the `+x` bit. |
| macOS arm64 | `Dockerfile:37` `wf-bootstrap-x86_64.tar.gz` is x86-only | `hostenv.py` detects arch and forces `--platform linux/amd64` on **build and run**, warning that it runs under QEMU emulation. `ARG WF_BOOTSTRAP_ARCH=x86_64` for a future native arm64 bootstrap. |
| Linux UID != 1000 | `Dockerfile:24-25` hardcodes UID/GID 1000; outputs land with the wrong owner | `--build-arg USER_UID=$(id -u) --build-arg USER_GID=$(id -g)`. On Darwin/Windows, pass 1000 (Docker Desktop maps ownership) so the cached image is shared. |
| WSL2 / Git Bash | — | Falls under Linux / Windows respectively. No extra code. |

## Reproducibility: `upstream.lock.json`

Upstream clones currently float to their default branch, so no two builds are the same and comparing
two engines mixes upstream drift into the diff.

- `upstream.lock.json` maps repo URL -> commit SHA.
- `dspico build --pin-upstream` clones at the pinned commits.
- `dspico update-upstream` regenerates the lock.

This makes `BUILD_INFO.txt` a *verification* rather than the only traceability a build has, and it is
a precondition for the engine comparison in phase 3.

## Testing strategy

TDD throughout: a failing test precedes every behavior, no exceptions.

**Three levels:**

1. **Pure unit** — `config`, `plan`, `rom`, `hostenv`. No I/O, no mocks, millisecond runtime.
2. **Command contract** — `FakeRunner` records `argv`; tests assert the *exact* command emitted. This
   is what catches "arm64 lost its `--platform`" or "the inputs mount lost `:ro`".
3. **Disk-level integration** — `tmp_path` plus same-size stub blobs (nothing copyrighted). Asserts
   the guards fire: missing `ntrBlowfish.bin` errors out, a sub-32 KB ROM is padded to `0x8000`,
   `_picoboot.nds` and `_pico/` land in the right place.

**Mutation testing thresholds are per-module, not global** — a global number is satisfied by killing
easy mutants:

- `plan.py`, `rom.py`, `config.py`, `hostenv.py` -> **100% killed, hard CI gate.** A surviving mutant
  in pure decision logic is a missing test, not noise.
- `steps/`, `host/` -> 80% target, **no gate.** String construction generates many equivalent mutants;
  a hard gate there only produces tautological tests.

**Hypothesis** on `rom.py`: for any input size `n`, the result is `>= 0x8000` and never truncates
existing bytes.

The shell scripts get no tests. During the parallel phase they are a frozen reference implementation;
ShellCheck stays in CI until they are deleted.

## CI

| Job | Status | What |
| --- | --- | --- |
| `test` | BLOCKING | pytest on ubuntu x macos x windows, Python 3.11/3.12/3.13. Tests need no Docker, so the matrix is cheap. This is what actually verifies portability. |
| `types` | BLOCKING | `mypy --strict` on `dspico/`. The Python analogue of the project's "static analysis first" rule. |
| `lint` | BLOCKING | `ruff check` + `ruff format --check`. |
| `mutation` | BLOCKING | mutmut on pure modules, 100% threshold, ubuntu only, paths-filtered. |
| `shellcheck` | blocking | Kept while the shell scripts exist; removed with them. |
| `docker-build` | advisory | New. `docker build` filtered on `Dockerfile` changes. Needs no copyrighted inputs. Expensive (~10-15 min), hence advisory. |
| `hadolint`, `sast` | advisory | Semgrep gains `--config r/python` alongside `r/bash`. |

## Migration plan

Four PRs. Each leaves the repo working.

1. **Scaffolding + pure modules.** Package, `pyproject.toml`, CI jobs. TDD on `config`/`plan`/`rom`/
   `hostenv`. Zero behavior change — the shell remains the only executable path. Fully verified by CI
   without the user.
2. **Host launcher.** `py -m dspico build` builds the image and runs the container, still executing
   the existing `compile_resources.sh`. Windows/macOS/UID are solved here with the pipeline untouched.
   **User validation 1:** one real build. Portability is proven without having touched the pipeline.
3. **Python pipeline.** `--engine=python`; default stays `bash`. **User validation 2:** run both
   engines and compare.
4. **Cutover.** `--engine` removed, both `.sh` deleted, shellcheck job removed, README rewritten.

### How the engines are actually compared

`.uf2` and `.nds` artifacts will not be bit-identical even between two runs of the same engine —
upstream clones drift and builds carry timestamps. The comparison is therefore:

- Identical relative file tree under `outputs/dspico/`.
- Identical file sizes.
- Identical upstream commit in every `BUILD_INFO.txt`.

`--pin-upstream` removes upstream drift from the comparison, which is why it is a precondition.

## Error handling

`error_exit` becomes a `BuildError` exception carrying the failing step name and the command that
failed. `cli.py` catches it at the top level, prints the same red message shape users already know,
and exits non-zero. Guards that today are `|| true` become explicit assertions with a named
exception; the only tolerated soft failures are the genuinely optional copies (`copy_if_exists`),
which log a warning.

## Documentation

`CLAUDE.md` and `README.md` are updated in the same PR that changes behavior, per the project's
existing rule. The **Build pipeline** table, the flag tables, and the input/SHA-1 tables must track
the flags the code actually reads. The README's references to the deleted `verify_blowfish.sh`,
`extract_blowfish.sh` and `find_blowfish.sh` are removed in PR 1 as a drive-by fix.
