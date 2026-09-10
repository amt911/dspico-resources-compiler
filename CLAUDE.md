# DSpico Resources Compiler — Claude Guide

Docker-based build orchestrator for the DSpico flashcart: it clones and compiles every DSpico
component (DLDI driver, bootloader, ROM encryptor, Pico firmware, loader, launcher) inside one
reproducible container and assembles a ready-to-copy SD card layout in `outputs/`.

## Start here

- **This repo has no source of its own.** All logic lives in two scripts (`build_resources.sh` host
  launcher, `compile_resources.sh` in-container pipeline) plus the `Dockerfile`. Everything else is
  cloned at build time from upstream repos. Read **Build pipeline** below before touching either script.
- **Run `/graphify` before each session.** The persistent graph at `graphify-out/graph.json`
  summarizes architecture, dependencies and cross-cutting concepts without re-reading the repo.
- **Read `docs/FINDINGS.md` before debugging or touching the build** — non-obvious gotchas.
  **Convention:** when you discover something non-obvious that cost time and isn't deducible from the
  code, add a short entry to `docs/FINDINGS.md` (create it if missing). The **Known gotchas** section
  below is the current seed list.
- **Never commit copyrighted binaries.** Blowfish tables, BIOS dumps, WRFU and ntrboot ROMs are
  user-supplied from hardware they own. `inputs/**` is git-ignored except `.gitkeep` placeholders;
  `outputs/` is git-ignored entirely. Keep it that way.

## ⚡ graphify — use every session

```text
/graphify            # first run (builds graph from scratch)
/graphify --update   # incremental update (only re-extracts changed files)
/graphify query "<question>"    # architecture questions instead of opening multiple files
/graphify explain "<name>"      # locate a concept or symbol
/graphify path "A" "B"          # dependency path between two modules
```

Outputs in `graphify-out/`: `graph.json` (source of truth), `GRAPH_REPORT.md` (god nodes,
communities, surprising connections), `graph.html` (interactive view).

Run `/graphify --update` at end of session if you touched docs or images (code changes rebuild via
hook if installed).

## ⚡ superpowers — use whenever applicable

Always prefer **superpowers** skills over ad-hoc approaches. If there's even a small chance a skill
applies to the task, invoke it via the `Skill` tool before acting (including before clarifying
questions).

- **Process skills first** — `brainstorming` before creative/feature work, `systematic-debugging`
  before fixing bugs, `test-driven-development` before writing implementation.
- **Then implementation skills** — domain-specific skills guide execution.
- **Verify before claiming done** — `verification-before-completion` / `requesting-code-review`
  before merging.

Flow: `brainstorming → spec (you approve) → writing-plans → plan (you approve) →
subagent-driven-development → finishing-a-development-branch`. **Nothing is implemented without an
approved spec.**

User instructions always take precedence over skills; skills override default behavior. **Skills
refine *how* the work is done; they never override the rules in this file. When a skill and this
`CLAUDE.md` conflict, this file wins.**

### Mode switch

- **"lite mode"** — fully disables superpowers: no skill is invoked, not even the applicability
  check, until **"normal mode"** is said.
- **"normal mode"** (default) — standard superpowers behavior, plus: when delegating coding work,
  dispatch at most 1 **implementation** agent at a time (a read-only review agent runs alongside it — see **Agent orchestration**), and never use a model above Sonnet (no Opus).
- **"modo desatendido"** (unattended mode) — the user is away and delegates autonomy: work without
  waiting for confirmations and make reasonable decisions yourself instead of asking. In this mode you
  MAY **`git push` the feature branches you create** and **open PRs via `gh`** on your own, so the
  work is ready for review when the user returns. The hard limits still hold and are NOT lifted:
  **never merge anything** (no `git merge`, no fast-forward integration, no `gh pr merge`), **never
  push to `main`** or any protected/default branch directly, and **never** `git push --force` /
  `--force-with-lease`. Deliver everything as pushed branches + PRs for the user to merge. Reverts to
  defaults on **"normal mode"**.

Confirm the switch briefly when it happens.

---

## Build pipeline (source of truth — don't deviate)

`build_resources.sh` (host) builds the image, then runs `compile_resources.sh` inside it with three
mounts: `inputs/` → `/inputs` **read-only**, `outputs/` → `/outputs`, and the script itself →
`/dspico/compile_resources.sh` read-only. Entrypoint is `bash -lc` so `/etc/profile.d/wonderful.sh`
sources `wf-env` and the toolchain is on `PATH`.

`compile_resources.sh` is a set of `step_*` functions run in fixed order by `main`:

| # | Step | Produces | Notes |
| --- | --- | --- | --- |
| 1 | `step_dldi` | `dldi/DSpico.dldi` | sets `DLDI_FILE` |
| 2 | `step_bootloader` | `bootloader/BOOTLOADER.nds` | DLDI-patched with `dlditool`; sets `BOOTLOADER_NDS` |
| 3 | `step_encryptor` | `encryptor/default.nds` | .NET build; sets `ENCRYPTOR_BIN`, `ENCRYPTED_NDS` |
| 4 | `step_wrfuxxed` | `wrfuxxed/uartBufv060.bin` | only if `ENABLE_WRFUXXED=1`; also DLDI-patched |
| 5 | `step_firmware` | `firmware/*.uf2` | injects ROMs into `roms/`, runs upstream `./compile.sh` |
| 6 | `step_pico_loader` | `pico-loader/picoLoader{7,9*}.bin`, `aplist/savelist/patchlist.bin` | |
| 7 | `step_pico_launcher` | `pico-launcher/LAUNCHER.nds`, `_pico/` themes | |
| 8 | `step_assemble_sd` | `sd_card/_picoboot.nds` + `sd_card/_pico/` | the actual deliverable |
| 9 | `step_firmware_ntrboot` | `firmware/DSpico_ntrboot_{3ds,dsi}.uf2` | only `ENABLE_NTRBOOT=1` **and not** `USE_EDO_FIRMWARE=1` |

**Rules that follow from this:**

1. **Steps share global state** — `DLDI_FILE`, `BOOTLOADER_NDS`, `ENCRYPTED_NDS`, `ENCRYPTOR_BIN` are
   set by earlier steps and consumed by later ones. Reordering, skipping or extracting a step breaks
   the ones downstream. Read the whole affected function before editing.
2. **`clone_repo` `cd`s into the repo and stays there.** Every step after a `clone_repo` call uses
   paths relative to that clone (`chmod +x compile.sh`, `git submodule update --init`,
   `(cd pico-sdk && …)`). Don't add a step that assumes a fixed cwd.
3. **Keep failures loud** — `error_exit` after every clone/build/copy that must succeed, and
   `find_artifact` / `[ -f … ]` before consuming an artifact. These guards *are* the pipeline's tests.
   `|| true` is only for genuinely optional copies (`copy_if_exists`, `copy_glob`).
4. **New optional feature → new env flag**, and update `compute_steps` (step count) and `setup_dirs`
   (output dirs) in the same change.
5. **Never write to `/inputs`** — it's mounted read-only. Copy into `/tmp` or the clone dir instead
   (as `step_encryptor` does when it copies Blowfish tables into the DSRomEncryptor bin dir).
6. **Each component writes `BUILD_INFO.txt`** (`write_build_info`) with the upstream commit hash,
   date and subject. Upstream clones float to their default branch, so this is the only traceability
   a build has — always write it for a new component.

### Firmware ROM slots (why there are two ntrboot paths)

- **LNH-team firmware** (default) has **2 ROM slots**: `roms/default.nds` (encrypted bootloader) and
  `roms/dsimode.nds` (WRFUxxed). ntrboot therefore needs its **own separate builds** → step 9 rebuilds
  the firmware once per variant into `DSpico_ntrboot_3ds.uf2` / `DSpico_ntrboot_dsi.uf2`.
- **edo9300 fork** (`USE_EDO_FIRMWARE=1`) has **4 slots**, adding `ntrboot.nds` + `ntrbootdsi.nds`, so
  ntrboot is embedded in the single `DSpico.uf2` and **step 9 is skipped**.
- 3DS ntrboot input is a raw `boot9strap_ntr.firm`, converted to NDS at build time by
  [`amt911/firm-to-nds`](https://github.com/amt911/firm-to-nds). DSi ntrboot input `default.gcd` is
  copied as-is.
- `ENABLE_WRFUXXED=1` also `sed`s `CMakeLists.txt` to uncomment `DSPICO_ENABLE_WRFUXXED`. If upstream
  renames or reformats that line, the `sed` silently no-ops (`|| true`) and the exploit is quietly
  missing from the build — verify the flag actually took effect.

---

## Stack

- **POSIX sh / bash** — the entire pipeline. `build_resources.sh` is `sh`; `compile_resources.sh` is
  bash (`local`, arrays-free but bash-isms present). Both use `set -eu`.
- **Docker** (`debian:bookworm`) — reproducible build environment; the only supported way to build.
- **Wonderful toolchain + BlocksDS** at `/opt/wonderful` — `wf-pacman`, `male` (falls back to `make`),
  `dlditool`. Builds the `.nds` / `.dldi` artifacts.
- **ARM GCC + CMake + Pico SDK** — builds the Raspberry Pi Pico `.uf2` firmware via the upstream
  repo's own `compile.sh`.
- **.NET 9 SDK** — builds `Gericom/DSRomEncryptor`, which inserts the Blowfish tables and encrypts the
  bootloader's secure area.
- **Python 3** — `firm-to-nds` conversion on the 3DS ntrboot path.

Upstream components cloned at build time: `LNH-team/{dspico-dldi,dspico-bootloader,dspico-wrfuxxed,
dspico-firmware,pico-loader,pico-launcher}`, `Gericom/DSRomEncryptor`, `edo9300/dspico-firmware`
(optional), `amt911/firm-to-nds` (optional). This repo orchestrates; it vendors nothing.

## Commands

```bash
# Portable launcher (Linux/macOS/Windows). Runs the same compile_resources.sh.
# Needs Python 3.11+ on the host; flags instead of env vars so PowerShell works.
python -m dspico build --wrfuxxed --ntrboot --edo-firmware
python -m dspico build --dry-run     # print the docker commands, run nothing

# Second engine, INCOMPLETE and unvalidated — see "Two engines" below.
python -m dspico build --engine-kind=python

# Full build: builds the Docker image, then runs the in-container pipeline.
# Requires Blowfish tables in inputs/blowfish/ (see README).
./build_resources.sh

# Feature flags (env vars, additive — combine freely):
ENABLE_WRFUXXED=1 ./build_resources.sh          # DSi/3DS exploit ROM (needs inputs/wrfuxxed/dsimode.nds)
ENABLE_NTRBOOT=1  ./build_resources.sh          # ntrboot variants   (needs inputs/ntrboot/)
USE_EDO_FIRMWARE=1 ./build_resources.sh         # edo9300 fork: ntrboot embedded in DSpico.uf2

# Recommended full build:
USE_EDO_FIRMWARE=1 ENABLE_WRFUXXED=1 ENABLE_NTRBOOT=1 ./build_resources.sh

# Custom inputs/outputs dirs and image name:
IMAGE_NAME=my-dspico:latest ./build_resources.sh /path/to/inputs /path/to/outputs

# Build only the image:
docker build -t dspico-compiler:latest .

# Local checks (what CI runs — see below):
shellcheck --severity=warning build_resources.sh compile_resources.sh
bash -n compile_resources.sh && sh -n build_resources.sh
docker run --rm -i hadolint/hadolint < Dockerfile
```

**Fast iteration:** `compile_resources.sh` is **bind-mounted** into the container, so editing it and
re-running `./build_resources.sh` picks the change up without rebuilding the image (the `docker build`
is a cache hit). Only `Dockerfile` changes cost a real rebuild.

## Two engines

The pipeline is mid-migration from shell to Python. `--engine-kind` picks which one runs **inside**
the container; the host launcher is the same either way.

- **`bash` (default)** — `compile_resources.sh`, unchanged and complete. This is the engine to use.
- **`python`** — `dspico.pipeline.run`, imported over `PYTHONPATH` (never installed; the container
  ships Python 3.11.2). **Six of nine steps are ported**: dldi, bootloader, wrfuxxed, pico_loader,
  pico_launcher, sd_card. `encryptor`, `firmware` and `ntrboot_variants` **raise** rather than
  no-op, so a partial run aborts instead of producing a plausible-looking wrong build.

**The Python engine has never completed a real build.** Do not describe it as working. When it is
finished, the two engines are compared on: identical relative file tree under `outputs/dspico/`,
identical file sizes, and identical upstream commit in every `BUILD_INFO.txt` — the artifacts
themselves are not bit-reproducible, because upstream clones float to their default branch and
builds carry timestamps.

## Tests and quality

The deliverable is the build itself, so the pipeline's fail-fast guards remain part of its test
story — but the decision logic now lives in `dspico/`, which has a real suite.

- **`python -m pytest`** — unit tests for the pure modules. Runs on Linux, macOS and Windows,
  Python 3.11-3.14, and needs no Docker, network or toolchain.
- **`mypy --strict` and `ruff`** — blocking in CI. For typed Python these play the role ShellCheck
  plays for the shell scripts.
- **`scripts/mutation-gate.sh`** — mutation testing, gated at **100% killed** on `config.py`,
  `hostenv.py`, `pipeline/plan.py` and `pipeline/rom.py`. **mutmut exits 0 even with survivors**, so
  the verdict comes from `mutmut results`, not from its exit code — see `docs/MUTATION_TESTING.md`.
  The same script is what `pre-push` and the CI `mutation` job run, so the two cannot drift apart.
  **The floor the template sets is 60%**; this repo sits at 100% because the four modules are pure
  decision logic and ~130 mutants take a couple of seconds. That is a ratchet, not a headroom
  allowance: it goes up or stays, never down to 60 to let a push through.

The shell pipeline is still the only executable build path and is still covered by ShellCheck; it
has no unit tests by design, and is deleted rather than tested once the Python engine is validated.

- **ShellCheck** *(primary gate, blocking in CI)* — `shellcheck --severity=warning build_resources.sh
  compile_resources.sh`. Fix everything at that level before committing. The scripts lean on `set -eu`,
  globbing and `find`/`sed` pipelines that break silently; ShellCheck catches quoting, word-splitting
  and unset-variable bugs that would otherwise surface mid-build.
- **Syntax check** — `bash -n` / `sh -n` on any edited script.
- **`hadolint Dockerfile`** — advisory; it currently reports pre-existing style findings (unpinned apt
  versions, final `USER` is root, consecutive `RUN`s). Don't regress it further.
- **Build smoke test** — after any pipeline change, `docker build -t dspico-compiler:latest .` at
  minimum.
- **Artifact guards are the assertions** — preserve and extend `find_artifact` / `error_exit` /
  `[ -f … ]` rather than removing them to make a run pass.
- **Input validation** — `/inputs` is untrusted. SHA-1s for every expected input are documented in the
  README; ROMs under 32 KB are padded to `0x8000` before encryption because DSRomEncryptor writes test
  patterns at `0x3000-0x3FFF` and processes the secure area at `0x4000-0x8000`. Keep those checks.

### What to check per area

| Area | What | How |
| --- | --- | --- |
| `build_resources.sh` | arg parsing, env passthrough, volume mounts | ShellCheck + `sh -n`; re-read the `docker run` invocation |
| `compile_resources.sh` | `step_*` functions, artifact discovery, encryption, SD assembly | ShellCheck; trace each step's globals in/out; keep `error_exit` guards |
| `Dockerfile` | toolchain install (wonderful/BlocksDS, .NET 9, ARM GCC), non-root `builder` user | `docker build`; hadolint |
| `inputs/` layout | `blowfish/`, `wrfuxxed/`, `ntrboot/` | keep `.gitkeep`; never commit binaries |
| `README.md` | user-facing input requirements, SHA-1s, flags | must stay in sync with the flags the scripts actually read |

### You cannot run the real build

A full `./build_resources.sh` needs the user's copyrighted Blowfish tables / BIOS dumps, which you do
not have and must never require. **Claim exactly what you verified** (ShellCheck clean, `docker build`
succeeds, syntax parses, guards fire on stub inputs) and hand the user a precise manual test plan for
the real run. Evidence before assertions — never say "the pipeline works".

## Quality beyond coverage

**"It ran on my machine" is the trap here, not misleading coverage.** A shell pipeline can exit 0
while having silently skipped a step, copied a stale artifact, or produced a subtly wrong SD layout.

- **Static analysis first** *(highest priority)* — ShellCheck on every script, hadolint on the
  Dockerfile. For shell, static analysis catches the majority of real bugs (unquoted expansions, `cd`
  failures, `set -e` interactions) before anything runs. This is the shell analogue of "strict types +
  SAST".
- **Fail-fast, assert-everything scripting** — `set -eu` plus explicit `error_exit` and existence
  checks. Never weaken a guard to make a run go green.
- **Stub-input testing** — exercise a changed `step_*` with same-size dummy blobs instead of the real
  copyrighted inputs, and confirm the guards still fire on missing/invalid input.
- **Reproducibility** — the build must work from a clean `docker build` with no host state. Prefer
  non-interactive installs, pin sources where practical, and keep `BUILD_INFO.txt` accurate: upstream
  clones float to their default branch, so the recorded commit is the only thing making a build
  traceable.
- **Supply-chain awareness** — this repo clones third-party repos and installs a whole toolchain at
  build time. Every new `git clone` URL or package install is a new supply-chain surface; verify the
  upstream URL is the real one and ask before adding.
- **Idempotence** — steps `rm -rf` their clone dir and `rm -rf build` before rebuilding. A change that
  leaves stale state behind produces a "successful" build of the previous artifact.

**Process rule: don't let the AI define the acceptance criteria.** The user decides what a correct
artifact set looks like; the agent implements against it.

## CI & hooks

**Policy — cheap, mostly-static checks in CI; the real end-to-end run is the user's local build.**

- **Git hooks** (`.githooks/`) — install once per clone: `git config core.hooksPath .githooks`.
  - **pre-push** — `pytest`, then `scripts/mutation-gate.sh` (the slow step goes last, and mutating
    over a red suite tells you nothing). Only the Python side: the shell pipeline has no unit tests
    by design and its gate is ShellCheck, which CI already runs. Bypass: `git push --no-verify`, and
    then the breakage is yours.

`.github/workflows/ci.yml` (on push to `main` and on every PR):

- **`shellcheck` — BLOCKING.** `--severity=warning` on both scripts. Verified 0 findings at that
  level; the only default-level finding is an info-level `SC1091` for a file sourced inside the
  container. Fix findings, don't raise the severity threshold.
- **`hadolint` — advisory** (`continue-on-error`), pre-existing style findings.
- **SAST (Semgrep) — advisory** (`continue-on-error`), `--config r/bash`. Note: the `p/bash` registry
  shorthand 404s; `r/bash` is the ruleset that resolves.
- **`mutation` (mutmut) — BLOCKING**, and unchanged in strictness: `scripts/mutation-gate.sh`, zero
  survivors on the four pure modules. It is the same command the pre-push hook runs.

Don't grow this into a build pipeline (a real DSpico build needs copyrighted inputs CI can't have)
without asking.

## Agentic PR verification (MANDATORY on every PR)

**Every PR MUST be verified before merge and the verdict MUST be posted as a PR comment**
(`gh pr comment`). Running the pass and posting the verdict is **not optional**. A headless agent
(`claude -p`, local) produces it and then **waits for you** — it never merges.

- **Engine.** No app or browser to drive — this is a build orchestrator. The pass means:
  `docker build -t dspico-compiler:latest .` to confirm the image still builds, then run
  `compile_resources.sh` in the container against **non-copyrighted stub inputs** (dummy same-size
  blobs standing in for the Blowfish tables / BIOS dumps) far enough to exercise the changed `step_*`
  function(s), and confirm the loud-failure guards (`error_exit`, `find_artifact`) still fire on
  missing or invalid input. **Never** require or use the user's real copyrighted inputs — the full
  genuine run stays the user's own manual verification step.
- **Two layers.** Deterministic checks (ShellCheck, `bash -n`, `docker build`) are the hard merge
  gate; the agentic pass is advisory and never vetoes a merge on its own — but running it and posting
  the comment is mandatory.
- **Hard limits.** The verdict awaits your close; the agent never merges (see **Git & GitHub**).

## Known gotchas

- **The README is partly stale.** It documents `verify_blowfish.sh`, `extract_blowfish.sh` and
  `find_blowfish.sh`, which were removed in `c5b4abe "Deleted unused files"` and no longer exist on
  `main`. They still live on the old `edo` branch. Don't cite them as runnable; either restore them
  deliberately or fix the README.
- **Step labels are hardcoded.** `step "5/$TOTAL_STEPS"` etc. — `compute_steps` only bumps
  `TOTAL_STEPS` to 10 for the non-edo ntrboot path, so the printed numerators never change. Cosmetic,
  but don't assume the label reflects real ordering after an edit.
- **`ENABLE_WRFUXXED` depends on a `sed` against upstream `CMakeLists.txt`** — it ends in `|| true`,
  so an upstream rename fails silently (see **Firmware ROM slots**).
- **DSi ntrboot needs USB power** on the hardware side — the firmware must boot before the DSi starts
  its ntrboot sequence. This is a runtime constraint, not a build one; it shows up as "ntrboot doesn't
  work" bug reports.
- **`outputs/` accumulates.** Only `sd_card/` is rebuilt from scratch (`rm -rf`); per-component dirs
  are overwritten in place, so a stale artifact from a previous flag combination can survive. Wipe
  `outputs/dspico/` when comparing builds.

## Debugging — keep the loop from running away

What a bug costs is not the fix. It is how many times you go around
`build → deploy → reach the state → observe` before you know what to fix, times what one lap costs.
Every rule below carries the number it came from; the ones this repo has not measured are marked
`<!-- pendiente de medir -->` until someone does.

- **Measure before you ablate.** Ablation costs one lap per hypothesis and answers yes/no;
  instrumentation costs one lap total and answers *what is actually happening*. **Measured: 28
  ablations over 1 h 42 min moved nothing; one 13-min batch of probes changed the question and the
  bug fell on the next round.** The rule that came out of it: **if a pipeline completes every phase
  with non-empty output, the output exists** — stop asking "why doesn't it appear" and ask "where
  does it appear". Here that pipeline is `load/parse → validation → transform → write the result`.
- **Budget the lap, then attack the dominant term.** Time the four phases once and write the real
  seconds in; one dominates and the rest are noise. **If a bug needs more than three reproductions,
  write the shortcut before the fourth** — here that means
  a fixture that lands the tree/state already built, a VM snapshot, or a dev subcommand that skips
  the earlier steps.
  Commit it as `<scripts/repro-<bug>.sh>` and name it in `docs/FINDINGS.md`.

  | Lap phase | Command here | Measured |
  | --- | --- | --- |
  | build / install | `<pip install -e . · none>` | `<n s>` |
  | deploy | `<copy to the VM · none>` | `<n s>` |
  | reach the state | `<sample config · VM at the starting state>` | `<n s>` |
  | observe | `<stdout · resulting files · journalctl>` | `<n s>` |

- **A review finding is not a reproduction.** Whoever reviewed read the code; they did not run it.
  Reproduce it yourself before sending anyone to fix it, and **if the implementer says they cannot
  reproduce it, believe the implementer** — one of them has the thing running. **Measured: 1 h 25 min
  chasing a bug that did not exist.**
- **A test that refuses to go red is data, not a failure.** The fourth failed attempt to pin down
  that non-existent bug is what uncovered the real one, pointing the opposite way. "I cannot make
  this fail" is a result and it gets reported; a green test papered over it throws the signal away.
- **Before demanding a red, ask whether the mechanism can produce one.** If another layer masks the
  effect there will be no red however hard you push, and the time goes into the test instead of the
  bug. **Measured: over 1 h on two structurally impossible reds.**
- **Assertions that are inert by construction** — none of these shows up as a failure, a warning or
  a coverage drop. **Every assertion is watched failing once**, and expected values are written by
  hand:

  | Inert by | What it looks like here |
  | --- | --- |
  | `assert` under `-O` | `python -O` / `PYTHONOPTIMIZE` strips them from the bytecode: the test passes checking nothing |
  | an unawaited coroutine | leaves a `RuntimeWarning: coroutine was never awaited` and the test stays green |
  | snapshots with `--snapshot-update` | `syrupy` / `pytest-snapshot` record the current output as the reference |
  | `MagicMock` | returns another `MagicMock` for any attribute: everything is truthy and everything looks called |
  | expectation computed alike | the expected value is recomputed with the same function under test |

- **Verify the resource limit reaches the process doing the work.** A job wrapped in a memory scope
  can hand the work to a daemon or worker pool living outside it, and the tool still reports the
  limit as applied — over a process that is idle. Check the **worker's** cgroup
  (`cat /proc/<worker-pid>/cgroup`), not the scope's.
- **Environment claims get measured or they don't get made.** "That heap sounds low" produced a
  recommendation that was simply wrong; measuring it — three runs per setting, not one — gave a
  **0.4% difference, below the run-to-run variance**. No performance tuning lands without a
  before/after over more than one run.
- **Locate which layer owns a rule before deciding which side gives.** A rule that lives in one
  layer and isn't shared by the others fails where the assumption breaks, not where it is written,
  which is why the fix keeps landing in the innocent layer.
- **Replacing a component can remove capabilities in silence.** When you swap one API for another,
  enumerate what the old one did that the new one does not, and say it in the PR — nothing will fail
  to compile. An optional parameter that defaults to off is a capability that only exists if the
  caller remembers it.

## Agent orchestration — parallel where it's free, batched where it's yours

Delegating to agents moves the bottleneck to **scheduling**: what waits on what, what each agent
re-derives, and which decisions quietly stop being yours. Same convention — every rule carries its
measured number.

- **Review is not on the critical path.** Reviewing task N and starting N+1 are independent when
  they touch different files. Serialized, review is **10-15% of the wall clock** and blocks
  everything behind it; in parallel it is free. **On receiving an implementation report, dispatch
  its review and the next implementation in the same turn.** This is the one exception to
  *"at most 1 agent at a time"*: the cap counts **implementation** agents — a review agent reads and
  reports, it writes nothing, so it cannot race the implementer. **The exclusive resource here is:**
  the VM or target directory, and any real database or block device
  — at most one agent touching it.
- **Keep one shared facts file.** Every fresh agent re-derives the same things: the real selector,
  which fake exists, what that helper accepts. Keep `docs/FACTS.md`, have each agent append to it
  when it finishes, and hand it to the next one in its dispatch. Only **facts verified against the
  repo or the running system**, with how they were verified. It is not the gotchas log: that holds
  what is *not* deducible from the code and outlives the branch; this holds what is perfectly
  deducible and merely expensive to look up, and it may die with the branch.
- **Plans carry contracts, not literal code.** The agent **trusts** the code in the plan; code you
  never compiled is an error wearing authority. **Measured: 4 wrong blocks, 15-40 min of detour
  each.** Write exact names, exact signatures and "mirror the shape of `<X>`" — claims the agent can
  check against the repo — and reserve literal code for what you have run.
- **Batch the discretionary decisions.** Work that appears along the way — a capability being
  dropped, a missing script, an adjacent bug — added **5-6 h of 15**. Each was justified; deciding
  them on the fly is what takes them away from you. Accumulate and ask **once per batch, with the
  estimated cost**. In **"modo desatendido"** the batch goes in the PR body instead, with its costs.
- **What never gets cut.** Review was **1.5 h of 15** and found a `create()` silently discarding
  fields, a 404 caused by SQL deduplication, a silent merge that corrupted data, a
  delete-and-recreate with no transaction, and several inert assertions. **Cutting review does not
  give time back; it defers it to production.** Cut reproduction (write the shortcut) and
  serialization (dispatch review in parallel) instead.

### Day one — the numbers that fill the blanks

1. **The lap** — time `build → deploy → reach the state → observe` once and write the seconds into
   the table above. The dominant phase gets the shortcut script; the rest stay unoptimized.
2. **The exclusive resource** — confirm the one named above is really the only one.
3. **The inert assertions** — break one assertion on purpose and run the suite; anything still green
   is inert. Then prune the table above to what this stack can actually produce.

## Working rules

- **Use superpowers skills whenever they apply** — invoke via `Skill` before acting; process skills
  before implementation skills.
- **Don't install packages or add cloned repos without asking** — the toolchain (wonderful/BlocksDS,
  .NET 9, ARM GCC, Python 3) and the set of upstream repos are intentional; each addition is
  supply-chain surface.
- **Lint before committing** — ShellCheck on any edited `.sh`, `bash -n`, and `docker build` if the
  Dockerfile or pipeline changed. There are no hooks to catch it for you.
- **Never commit copyrighted binaries** — Blowfish tables, BIOS dumps, WRFU and ntrboot ROMs stay out
  of git. Keep only the `inputs/*/.gitkeep` placeholders; `outputs/` stays ignored.
- **Keep failures loud** — preserve `error_exit` and existence guards; don't paper over a missing
  artifact with `|| true`.
- **Don't break the step contract** — `step_*` functions share globals and run in a fixed order;
  understand the data flow before editing.
- **Keep this file and the README current** — when you add or change a flag, an input file or a
  pipeline step, update the **Build pipeline** table here and the README's input/flag tables in the
  same change. A stale guide misleads the next session.
- **Commits in English**, Conventional Commits. Scope = script or area (`compile`, `docker`, `docs`).
- **Instrument before you ablate, budget the lap, and dispatch review in parallel** — a pipeline that completes with non-empty output produced output; more than three reproductions means you owe a shortcut script; a review finding is not a reproduction; and the review of task N runs alongside the implementation of N+1. See **Debugging** and **Agent orchestration** above.

## Git & GitHub

- **Commits and branches OK** — create commits and new branches whenever it makes sense, without asking first.
- **Never push** *(default)* — no `git push` under any circumstance, and absolutely never
  `git push --force` / `--force-with-lease`. Leave pushing to the user. **Exception:** when
  **"modo desatendido"** is active, you may push the feature branches you create (never `main`/protected
  branches, never force) so PRs are ready for review.
- **Never merge — no permission** — you do NOT have permission to merge anything into any branch, nor to
  merge any pull request. No `git merge`, no fast-forward integration, no `gh pr merge`. This holds in
  every mode, **including "modo desatendido"**. Leave every merge (branches and PRs alike) to the user.
- **GitHub via `gh`** — if the `gh` CLI is available, you may open pull requests, issues, and similar
  (comments, labels, etc.). These don't require pushing on your part beyond what `gh` itself does for an
  already-pushed branch.
- **Branches:** `feat/name`, `fix/description`, `chore/task`.
- **Every PR must include a manual test plan** — add a **How to test manually** section with the exact
  steps: which input files must be in `inputs/blowfish/` (and `inputs/wrfuxxed/`, `inputs/ntrboot/`)
  first, the exact command including flags (e.g.
  `USE_EDO_FIRMWARE=1 ENABLE_WRFUXXED=1 ENABLE_NTRBOOT=1 ./build_resources.sh`), and the expected
  result (build finishes; `outputs/dspico/sd_card/` contains `_picoboot.nds` and `_pico/`; the expected
  `.uf2` files exist in `outputs/dspico/firmware/`). Include the error cases to check — missing
  Blowfish table, missing optional input — and confirm they fail loudly.
