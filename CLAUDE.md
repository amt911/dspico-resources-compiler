# DSpico Resources Compiler — Claude Guide

## Start here

Run `/graphify` before each session. The persistent graph at `graphify-out/graph.json` summarizes architecture, dependencies, and cross-cutting concepts without re-reading the repo each time.

This repo is a **Docker-based build orchestrator**, not an application. It clones and compiles all the separate DSpico components (DLDI driver, bootloader, ROM encryptor, firmware, loader, launcher) inside a reproducible container and assembles a ready-to-copy SD card layout in `outputs/`. Almost all the logic lives in two POSIX/bash scripts and a `Dockerfile` — there is no compiled source of its own.

## ⚡ graphify — use every session

```
/graphify            # first run (builds graph from scratch)
/graphify --update   # incremental update (only re-extracts changed files)
/graphify query "<question>"    # architecture questions instead of opening multiple files
/graphify explain "<name>"      # locate a concept or symbol
/graphify path "A" "B"          # dependency path between two modules
```

Outputs in `graphify-out/`: `graph.json` (source of truth), `GRAPH_REPORT.md` (god nodes, communities, surprising connections), `graph.html` (interactive view).

Run `/graphify --update` at end of session if you touched docs or images (code changes rebuild via hook if installed).

## ⚡ superpowers — use whenever applicable

Always prefer **superpowers** skills over ad-hoc approaches. If there's even a small chance a skill applies to the task, invoke it via the `Skill` tool before acting (including before clarifying questions).

- **Process skills first** — `brainstorming` before creative/feature work, `systematic-debugging` before fixing bugs, `test-driven-development` before writing implementation.
- **Then implementation skills** — domain-specific skills guide execution.
- **Verify before claiming done** — `verification-before-completion` / `requesting-code-review` before merging.

User instructions always take precedence over skills; skills override default behavior.

### Mode switch

- **"lite mode"** — fully disables superpowers: no skill is invoked, not even the applicability check, until **"normal mode"** is said.
- **"normal mode"** (default) — standard superpowers behavior, plus: when delegating coding work, dispatch at most 1 agent at a time, and never use a model above Sonnet (no Opus).

Confirm the switch briefly when it happens.

## Stack

- **POSIX sh / bash** — the whole build pipeline. `build_resources.sh` is the host launcher; `compile_resources.sh` is the in-container build script (structured into `step_*` functions + a `main`).
- **Docker** (`debian:bookworm` base image) — reproducible build environment. Inputs are mounted read-only at `/inputs`, artifacts written to `/outputs`.
- **Wonderful toolchain + BlocksDS** — Nintendo DS homebrew toolchain (`wf-pacman`, `male`/`make`, `dlditool`) installed at `/opt/wonderful`, used to build the `.nds` / `.dldi` artifacts.
- **ARM GCC + Pico SDK (CMake)** — `gcc-arm-none-eabi` and `cmake` build the Raspberry Pi Pico `.uf2` firmware.
- **.NET 9 SDK** — builds `DSRomEncryptor` (Gericom) which inserts Blowfish tables and encrypts the bootloader ROM.
- **Python 3** — used for the optional `firm-to-nds` conversion in the ntrboot path.

Components are cloned at build time from external repos (`LNH-team/*`, `Gericom/DSRomEncryptor`), so this repo orchestrates rather than vendors them.

## Commands

```bash
# Full build (host): builds the Docker image, then runs the in-container pipeline.
# Requires Blowfish tables in inputs/blowfish/ (see README).
./build_resources.sh

# Optional feature flags (env vars):
ENABLE_WRFUXXED=1 ./build_resources.sh      # DSi/3DS exploit variant
ENABLE_NTRBOOT=1  ./build_resources.sh      # ntrboot firmware variants (needs inputs/ntrboot/)

# Custom inputs/outputs dirs and image name:
IMAGE_NAME=my-dspico:latest ./build_resources.sh /path/to/inputs /path/to/outputs

# Build only the Docker image:
docker build -t dspico-compiler:latest .

# Lint the shell scripts (see "Tests and quality"):
shellcheck build_resources.sh compile_resources.sh
```

There is no separate `dev`, `test`, or `lint` toolchain wired up in the repo — the deliverable is the build itself. Outputs land in `outputs/dspico/` (per-component dirs + a `sd_card/` ready to copy).

## Tests and quality

This project has **no unit/integration test suite** — it is a shell + Docker build orchestrator whose "test" is that the pipeline runs to completion and produces valid artifacts. Quality here is about **script correctness, build reproducibility, and smoke-verifying artifacts**, not code coverage. Adapt accordingly:

- **ShellCheck** *(primary gate)* — run `shellcheck build_resources.sh compile_resources.sh` and fix all warnings before committing. The scripts use `set -eu`, `local`, globbing, and `sed`/`find` pipelines that are easy to break silently; ShellCheck catches quoting, word-splitting, and unset-variable bugs that would otherwise only surface mid-build.
- **`sh -n` / `bash -n` syntax check** — quick parse check on any edited script (`bash -n compile_resources.sh`).
- **`hadolint Dockerfile`** — lint the Dockerfile for pinned-version and layer hygiene issues if you touch it.
- **Build smoke test** — after any change to the pipeline, run `docker build -t dspico-compiler:latest .` at minimum. A full `./build_resources.sh` requires the copyrighted Blowfish tables in `inputs/blowfish/` (which the user supplies from hardware they own — you will not have them), so a complete run is usually the **user's** manual verification step, not something you can do end-to-end.
- **Artifact checks** — the scripts already assert artifacts exist (`find_artifact`, `error_exit` on missing `.nds`/`.uf2`/`.dldi`). Preserve and extend these guards rather than removing them; they are the pipeline's real assertions.
- **SHA-1 verification** — inputs are validated by SHA-1 against known-good hashes (see README). When touching input handling, keep those checks intact.

### What to check per area

| Area | What | How |
| --- | --- | --- |
| `build_resources.sh` | Host launcher: arg parsing, env-var passthrough, volume mounts | ShellCheck + `bash -n`; dry-read the `docker run` invocation |
| `compile_resources.sh` | In-container `step_*` functions, artifact discovery, encryption, SD assembly | ShellCheck; trace each step's inputs/outputs; keep `error_exit` guards |
| `Dockerfile` | Toolchain install (wonderful/BlocksDS, .NET, ARM GCC), non-root `builder` user | `docker build`; hadolint |
| `inputs/` layout | `blowfish/`, `wrfuxxed/`, `ntrboot/` expected files | Keep `.gitkeep` placeholders; never commit copyrighted binaries |

### When changing the pipeline

1. **Read the whole affected `step_*` function** — steps share state via globals (`DLDI_FILE`, `BOOTLOADER_NDS`, `ENCRYPTED_NDS`, `ENCRYPTOR_BIN`) set by earlier steps. Reordering or removing a step can break a later one.
2. **Keep failures loud** — every step should `error_exit` when a required artifact is missing. Silent `|| true` is only for genuinely optional copies.
3. **Guard optional features** behind their env var (`ENABLE_WRFUXXED`, `ENABLE_NTRBOOT`) and update `compute_steps` / `setup_dirs` if you add a step or output dir.

## Quality beyond coverage

**"It ran on my machine" is the trap here, not misleading coverage.** A shell pipeline can exit 0 while having silently skipped a step, copied a stale artifact, or produced a subtly wrong SD layout. These practices attack that blind spot:

- **Static analysis first** *(highest priority)* — **ShellCheck** on every script and **hadolint** on the Dockerfile. For shell, static analysis catches the majority of real bugs (unquoted expansions, `cd` failures, `set -e` interactions) before anything runs. This is the direct analogue of "strict types + SAST" for a shell codebase.
- **Fail-fast, assert-everything scripting** — `set -eu` (already used), explicit `error_exit` after every build/clone/copy that must succeed, and existence checks (`find_artifact`, `[ -f ... ]`) before consuming an artifact. These are the pipeline's real "tests" — treat them as such and never weaken them to make a run pass.
- **Input validation at the boundary** — Blowfish tables and BIOS dumps are validated by **SHA-1** against known-good hashes, and ROMs are size-padded before encryption. Anything crossing the `/inputs` boundary is untrusted; validate it explicitly rather than assuming the user supplied the right file.
- **Reproducibility** — the build must be reproducible from a clean `docker build`. Pin toolchain sources where practical, prefer `--noconfirm`/non-interactive installs, and don't rely on host state. Cloned component repos float to their default branch — record commit metadata (the script already writes `BUILD_INFO.txt` per component) so a build is traceable.
- **Smoke test the real thing** — the only meaningful end-to-end check is "does `./build_resources.sh` finish and produce `outputs/dspico/sd_card/` with `_picoboot.nds` + `_pico/`?" Because that requires user-owned copyrighted inputs, it is generally the **user's** manual verification. Make your changes easy for them to verify (clear step logging, loud failures).
- **Dependency/supply-chain awareness** — this repo clones third-party repos and installs a full toolchain at build time. Don't add new `git clone` sources or package installs casually; each is a supply-chain surface. Verify any new upstream URL is the real one.

**Process rule (worth more than any tool): you cannot run the copyrighted-input build yourself, so don't claim the pipeline "works" — claim exactly what you verified** (ShellCheck clean, `docker build` succeeds, syntax parses) and hand the user a precise manual test plan for the full run. Evidence before assertions.

## Working rules

- **Use superpowers skills whenever they apply** — invoke via `Skill` before acting; process skills before implementation skills.
- **Don't install packages or add new cloned repos without asking** — the toolchain (wonderful/BlocksDS, .NET 9, ARM GCC) and the set of upstream component repos are intentional. New `apt` packages, `wf-pacman` packages, or `git clone` sources change the supply-chain surface.
- **Lint before committing** — ShellCheck on any edited `.sh`, `bash -n` syntax check, and `docker build` if the Dockerfile or pipeline changed.
- **Never commit copyrighted binaries** — Blowfish tables, BIOS dumps, and WRFU/ntrboot ROMs are user-supplied and must stay out of git. Keep only the `.gitkeep` placeholders under `inputs/*`. `outputs/` is git-ignored — keep it that way.
- **Keep failures loud** — preserve `error_exit`/existence guards; don't paper over a missing artifact with `|| true`.
- **Don't break the step contract** — `step_*` functions in `compile_resources.sh` share global state and run in a fixed order; understand the data flow before editing.

## Git & GitHub

- **Commits and branches OK** — create commits and new branches whenever it makes sense, without asking first.
- **Never push** — no `git push` under any circumstance, and absolutely never `git push --force` / `--force-with-lease`. Leave pushing to the user.
- **Never merge — no permission** — you do NOT have permission to merge anything into any branch, nor to merge any pull request. No `git merge`, no fast-forward integration, no `gh pr merge`. Leave every merge (branches and PRs alike) to the user.
- **GitHub via `gh`** — if the `gh` CLI is available, you may open pull requests, issues, and similar (comments, labels, etc.). These don't require pushing on your part beyond what `gh` itself does for an already-pushed branch.
- **Every PR must include a manual test plan** — when opening a PR, add a **How to test manually** section describing the exact steps to exercise the change by hand. For this repo that means: the exact command (`./build_resources.sh`, with any `ENABLE_WRFUXXED=1` / `ENABLE_NTRBOOT=1` flags), what must be present in `inputs/blowfish/` first, and the expected result (build finishes; `outputs/dspico/sd_card/` contains `_picoboot.nds` and `_pico/`). Include any setup (which input files, which feature flags) and the edge/error cases to check (missing Blowfish table, missing optional input).
