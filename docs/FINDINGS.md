# Findings

Non-obvious things that cost time and are not deducible from the code. Add an entry when you hit one.

## `male` does not exist in the image — `build()` has always used `make`

`compile_resources.sh`'s `build()` prefers `male` (the Wonderful toolchain's make wrapper) and falls
back to `make -j$(nproc)`. In the actual image there is **no `male` binary anywhere on the
filesystem**, even though `wf-tools 0.2.0-3` is installed:

```console
$ docker run --rm --entrypoint bash dspico-compiler:latest -lc 'find / -name male -type f; wf-pacman -Q | grep wf-tools'
wf-tools 0.2.0-3
wf-tools-lua 0.1.0.r175.8beadd1-1
wf-tools-native 0.1.0.r159.7e47f4c-1
```

So the `male` branch has never executed and every component has been built with plain `make`. Do not
assume `male` semantics when debugging a build. Verified 2026-08-05 against an image built 2026-02.

## The container runs as root, not as `builder`

`Dockerfile` creates a `builder` user and switches to it for the toolchain install, but line 62
switches back to `USER root` for the blocksds symlink and the .NET 9 install and never switches
again. The final `USER` is root, so `builder` never runs a build.

Consequences:

- `--build-arg USER_UID` / `USER_GID` configure an account nothing uses. Passing them does nothing.
- Under rootful Docker every artifact lands root-owned.
- Under **rootless podman** the host user maps to container root, which is why `outputs/` comes out
  correctly owned there — by accident of the mapping, not by design.

This is the "final USER is root" finding hadolint reports, which is easy to dismiss as style.

## Never chown `/outputs` to the host's UID

Following from the above: the correct chown target inside the container is **not** the host UID.
Under rootless podman, chowning to the literal host UID (1000) hands artifacts to an unrelated
subuid (10999) and breaks a case that already worked. `fix_ownership` reads `stat -c %u /outputs`
instead — the host created that mount as the invoking user, so whatever UID the container sees on it
is correct under rootful Docker, rootless podman and Docker Desktop alike.

## mutmut exits 0 even when mutants survive

Verified on mutmut 3.7.0 by deliberately adding an untested branch: `mutmut run` returned exit code
`0` while `mutmut results` listed two survivors. Any mutation gate must parse `mutmut results`;
gating on the exit status is silently useless. See `docs/MUTATION_TESTING.md`.

## `ruff format` rewrites Python inside markdown

Current ruff formats fenced Python blocks in `.md` files, so `ruff format --check .` failed on the
illustrative snippets in `docs/superpowers/`. `[tool.ruff] exclude = ["docs"]` in `pyproject.toml`
keeps the plans and specs readable as written.
