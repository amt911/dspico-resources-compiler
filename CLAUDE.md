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
- **"modo desatendido"** (unattended mode) — the user is away and delegates autonomy: work without waiting for confirmations and make reasonable decisions yourself instead of asking. In this mode you MAY **`git push` the feature branches you create** and **open PRs via `gh`** on your own, so the work is ready for review when the user returns. The hard limits still hold and are NOT lifted: **never merge anything** (no `git merge`, no fast-forward integration, no `gh pr merge`), **never push to `main`** or any protected/default branch directly, and **never** `git push --force` / `--force-with-lease`. Deliver everything as pushed branches + PRs for the user to merge. Reverts to defaults on **"normal mode"**.

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

## Real-hardware verification — what no green build can prove

`## Quality beyond coverage` already names the trap ("it ran on my machine") and the answer for the
scripts (ShellCheck, `set -eu`, `error_exit`, SHA-1 at the boundary). This section names the trap one
level further out: **a pipeline that exits 0 and writes files is not a bootloader that boots.**

`docker build` succeeding, ShellCheck clean and every `find_artifact` guard passing tell you a file of
the right name exists at the right path. They tell you nothing about what is *in* it. The artifacts
here are firmware — a `.nds` bootloader, a `.dldi` driver, a `.uf2` for the Pico. Firmware is verified
by running it, and nothing in this repo can do that.

**The final gate is a human with hardware.** Write the steps down as a checklist, commit it, and name
it here. Because the real run needs the user's own copyrighted Blowfish tables and BIOS dumps, the run
is *handed over*, never claimed.

What "real environment" means here, concretely:

- **A real DS (or DSi/3DS) with the flashcart**, or an emulator that models the hardware — melonDS,
  no$gba, DeSmuME. An emulator proves the ROM header, the encrypted secure area and the entry point
  are sane; only the real cart proves DLDI, SD timing and the actual boot chain.
- **A real Pico**, flashed with the `.uf2`, enumerating over USB and talking to the DS side.
- **The ntrboot path on real hardware** if it was touched — the `firm-to-nds` conversion produces
  something the target's boot ROM either accepts or does not. There is no partial credit.
- **A clean build environment.** `docker build` with a warm layer cache is not a from-scratch build,
  and the toolchain install steps are exactly where a floating upstream breaks. Prune the cache before
  believing a green build.

### The names, so you can ask for them by name

| Name | What it means here |
| --- | --- |
| **E2E / on-hardware acceptance test** | Flash the produced artifacts and assert on observable behaviour — the DS boots to the launcher, `outputs/dspico/sd_card/` is actually read, the Pico enumerates — never on the build log. The log says a file was written; it says nothing about what is in it. |
| **Contract test** | Checks that assumptions about things you do not control still hold — and this pipeline is built almost entirely out of them. **Cloned component repos float to their default branch**, so every build depends on someone else's `HEAD`; `DSRomEncryptor` decides where the Blowfish tables and the secure area land; the wonderful/BlocksDS, .NET and Pico SDK layouts move under `wf-pacman`. The `BUILD_INFO.txt` the script already writes per component **is** a contract artifact — it is the first thing to read when a build that used to work stops working. |
| **Mutation testing** (here: by hand) | Revert the fix, rebuild, confirm the check goes red, restore. There is no unit suite to automate it against, so this is manual — feed a deliberately wrong input and watch the guard fire. **A check that has never failed has not been tested**, and an `error_exit` nobody has seen trigger is decoration, not an assertion. |
| **State-invariant test** | Asserts a relationship **between two things** no single check owns: the SD layout against the filenames the bootloader actually looks for (`_picoboot.nds` + `_pico/` must be where the boot chain expects them, not merely present); the `BUILD_INFO.txt` commits against the artifacts sitting next to them; a step's globals (`DLDI_FILE`, `BOOTLOADER_NDS`, `ENCRYPTED_NDS`) against what the later step consumes. Each side can be individually fine while the pair is wrong. |
| **Test pollution / isolation leak** | State that outlives a run and quietly changes the next one: a warm Docker layer cache hiding a broken toolchain step; stale artifacts left in `outputs/` making a skipped step look successful; and above all **the user's copyrighted inputs** — `/inputs` is untrusted, holds BIOS dumps and Blowfish tables, and must never end up in a commit, a log, an image layer or a CI artifact. |

### Rules that came out of real bugs, not theory

- **Prove every guard can fail before you trust it green.** Remove or corrupt an expected input and
  watch `find_artifact` / `error_exit` fire, then restore. A pipeline exits 0 just as happily when a
  step was silently skipped as when it succeeded; the guards are the only difference, and an
  unexercised guard is not one.
- **Never assert on a count or a size you cannot predict.** "The `.nds` is about 4 MB", "there are 7
  files under `outputs/`" — both report success against a genuinely broken build as soon as an
  upstream default branch moves, because the magnitude depends on someone else's repository, not on
  your bug. Assert the **invariant**: the SD tree contains `_picoboot.nds` and `_pico/` at the paths
  the boot chain reads; every input matches its known-good SHA-1; a second run over identical inputs
  produces the same tree; every `BUILD_INFO.txt` names a commit you can look up.
- **A build stamp must die with the artifacts it describes.** A stale `BUILD_INFO.txt` beside
  regenerated binaries, or a reused `outputs/` from an earlier upstream revision, makes every later
  comparison meaningless — no error, no log, and the result looks plausible.
- **Never let a run leak the user's inputs.** No BIOS dump, Blowfish table or dumped ROM in a commit,
  a log, an image layer or a CI artifact. Keep the SHA-1 checks: they are how you assert on an input
  you must not store.
- **Claim exactly what you verified.** ShellCheck clean, `docker build` succeeds, syntax parses,
  guards fire on stub inputs — that is a real result, and it is *not* "the pipeline works". Hand the
  user a precise manual plan for the hardware run and let them report the verdict.

## Agentic PR verification (MANDATORY on every PR)

**Every PR MUST be verified end-to-end before merge, and the verdict MUST be posted as a PR
comment** via `gh pr comment`. A headless agent (`claude -p`, local) drives the change and posts
the result; it **never merges** — it waits for you. Running the pass and posting the verdict
comment is **not optional**. It catches what ShellCheck and a diff miss: a step that silently
skips, a stale artifact being copied forward, or an SD-card layout that's subtly wrong.

- **Engine.** No browser, no API to smoke-test — this is a build orchestrator. The agentic pass
  means: `docker build -t dspico-compiler:latest .` to confirm the image still builds, then run
  `compile_resources.sh` inside the container against **non-copyrighted stub inputs** (dummy
  same-size byte blobs in place of the real Blowfish tables / BIOS dumps) far enough to exercise
  the changed `step_*` function(s) and confirm the loud-failure guards (`error_exit`,
  `find_artifact`) still fire on missing/invalid input. **Never** require or use the user's real,
  copyrighted Blowfish tables/BIOS dumps to verify — those are user-supplied and out of scope for
  an agent; a full real run with the genuine inputs stays the user's own manual verification step
  (see "Tests and quality" above).
- **Two layers.** Deterministic checks (ShellCheck, `bash -n`, `docker build`) stay the hard merge
  gate; the agentic pass is advisory and never vetoes a merge on its own — but running it and
  posting the verdict comment is mandatory.
- **Hard limits.** The verdict awaits your close; the agent never merges.

## Working rules

- **Use superpowers skills whenever they apply** — invoke via `Skill` before acting; process skills before implementation skills.
- **Don't install packages or add new cloned repos without asking** — the toolchain (wonderful/BlocksDS, .NET 9, ARM GCC) and the set of upstream component repos are intentional. New `apt` packages, `wf-pacman` packages, or `git clone` sources change the supply-chain surface.
- **Lint before committing** — ShellCheck on any edited `.sh`, `bash -n` syntax check, and `docker build` if the Dockerfile or pipeline changed.
- **Never commit copyrighted binaries** — Blowfish tables, BIOS dumps, and WRFU/ntrboot ROMs are user-supplied and must stay out of git. Keep only the `.gitkeep` placeholders under `inputs/*`. `outputs/` is git-ignored — keep it that way.
- **Keep failures loud** — preserve `error_exit`/existence guards; don't paper over a missing artifact with `|| true`.
- **Don't break the step contract** — `step_*` functions in `compile_resources.sh` share global state and run in a fixed order; understand the data flow before editing.
- **Reuse before you write** — grep before adding a function (`grep -n '^[a-z_]*()' *.sh`). The pipeline already owns its primitives — `error_exit`, the existence guards, the clone/build helpers — and a new step composes them instead of pasting its own variant. A copied guard that drifts is how a missing artifact turns into a silent success two steps later. At the third copy, extract it next to the other shared helpers in the same change and migrate the callers.

## Git & GitHub

- **Commits and branches OK** — create commits and new branches whenever it makes sense, without asking first.
- **Never push** *(default)* — no `git push` under any circumstance, and absolutely never `git push --force` / `--force-with-lease`. Leave pushing to the user. **Exception:** when **"modo desatendido"** is active, you may push the feature branches you create (never `main`/protected branches, never force) so PRs are ready for review.
- **Never merge — no permission** — you do NOT have permission to merge anything into any branch, nor to merge any pull request. No `git merge`, no fast-forward integration, no `gh pr merge`. Leave every merge (branches and PRs alike) to the user. This holds in every mode, **including "modo desatendido"**.
- **GitHub via `gh`** — if the `gh` CLI is available, you may open pull requests, issues, and similar (comments, labels, etc.). These don't require pushing on your part beyond what `gh` itself does for an already-pushed branch.
- **Every PR must include a manual test plan** — when opening a PR, add a **How to test manually** section describing the exact steps to exercise the change by hand. For this repo that means: the exact command (`./build_resources.sh`, with any `ENABLE_WRFUXXED=1` / `ENABLE_NTRBOOT=1` flags), what must be present in `inputs/blowfish/` first, and the expected result (build finishes; `outputs/dspico/sd_card/` contains `_picoboot.nds` and `_pico/`). Include any setup (which input files, which feature flags) and the edge/error cases to check (missing Blowfish table, missing optional input).
