# Mutation testing

## What is gated

`mutmut` runs against the four pure decision modules only, configured under
`[tool.mutmut]` in `pyproject.toml`:

- `dspico/config.py`
- `dspico/hostenv.py`
- `dspico/pipeline/plan.py`
- `dspico/pipeline/rom.py`

The threshold is **100% of mutants killed**, blocking in CI.

## Why only those

These modules hold every branch that decides what the build does: which steps
run, whether a ROM is padded, which ntrboot source lands in which slot, what
`--platform` and UID the container gets. They are pure, so every mutant is
reachable from a fast unit test. A surviving mutant is a missing test.

`dspico/host/` and `dspico/pipeline/steps/` are deliberately **not** gated. They
assemble command lines, where mutating a string literal often produces an
equivalent mutant no honest test can kill. Gating them would produce tests that
assert the implementation back at itself. They target 80% informally instead.

## Running it

```bash
mutmut run       # run the mutants
mutmut results   # list survivors — empty output means all were killed
```

## mutmut exits 0 even when mutants survive

Verified on mutmut 3.7.0 by deliberately adding an untested branch: `mutmut run`
still returned exit code `0` while `mutmut results` listed two survivors. The CI
job therefore greps `mutmut results` rather than trusting the exit status. If you
add a local pre-commit check, do the same.

## Fixing a survivor

Add the missing test. Never exclude the mutant.

Two traps account for most survivors here:

1. **Comparing a value to the constant it came from.** `assert cfg.image_name ==
   DEFAULT_IMAGE_NAME` mutates on both sides at once and can never fail. Every
   module therefore has one test pinning its constants against literals.

2. **Genuinely equivalent mutants, which signal duplicated logic.** `pad_rom`
   originally repeated the `>= SECURE_AREA_END` threshold that `needs_padding`
   already owned. Mutating `>=` to `>` there was unkillable: at exactly
   `SECURE_AREA_END` the mutated branch falls through to `data + bytes(0)`, and
   CPython returns the original object for a concatenation with empty bytes — so
   even an identity assertion passes. The fix was to delete the duplicate
   comparison and call `needs_padding`, leaving the threshold in one place. If a
   mutant looks equivalent, the code is usually saying something.
