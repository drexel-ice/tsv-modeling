# Preparing the OpenROAD submission

> Research-workspace record: some commands and evidence paths below refer to
> internal tools or archived results not distributed in this repository. For
> supported publication-checkout commands, use the
> [repository quick start](../../../README.md).


Latest status: the capacitor-node crash is fixed and verified on macOS ARM64
and emulated Linux x86-64. The corrected patch passed the CLI builds, full lint,
eight registered targets and 49 enabled companion tests. The original reproducer
now returns RCX-6102 without a crash. No blocking finding remains in the reviewed
scope. See `review/FINAL_REVIEW.md` and the `p1_fix_*_pass/` evidence folders.
Earlier paragraphs below retain the preparation history. No PR was submitted.

The fixed schema-143 patch passed the current checks. Evidence is in
`review/p1_fix_macos_pass/` and `review/p1_fix_linux_pass/`. One optional
direct-Python ODB test remains skipped. The initial review is preserved in
`review/FINAL_REVIEW_INITIAL.md`; the current final review is
`review/FINAL_REVIEW.md`. Submission requires the user's approval.

The proposed upstream target is `The-OpenROAD-Project/OpenROAD:master`.
The core source for submission lives in `repos/OpenROAD-pr-ready` on branch
`tsv/native-rc-coupling-upstream`, based on fetched upstream
`b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1`. The original working baseline is
preserved in `repos/OpenROAD` on `tsv/native-rc-coupling`. No commit, push, or PR
has been made.
The core patch is `patches/native_rc_coupling.patch`; its scope is OpenDB coupling,
persistence/bindings, and assembly SPEF support. Python models, Palace extraction,
macOS setup and benchmark artifacts remain a companion bundle outside that repo.

The draft description is `review/OPENROAD_PR.md`, and the status/evidence index is
`review/pr_readiness.json`. The patch includes new source/test files and the binary
schema-141 fixture. Its reverse applicability against the local working tree was
checked. Do not apply it again to the already-modified checkout.

## Reproducing completed macOS checks

From the workspace root:

```bash
python3 outputs/openroad_tsv_integration/prepare_pr_checks.py --fetch --format
```

The helper selects `repos/OpenROAD-pr-ready` when present and prints the selected
path. Use `--repo` to select explicitly. It initializes submodules, runs the
repository C++ formatter and lint fixes, checks whitespace, builds
the CLI, runs full lint, the eight targeted Bazel regressions and the companion
suite, and exports a fresh patch. It fetches `origin/master` and checks whether
the patch applies in a temporary detached worktree. It removes that temporary
worktree afterward. It never rebases the working branch, commits, pushes or opens
a PR. Formatting can change source files; review the final diff before committing.
It also formats/lints new, untracked Python, Tcl and C++ source files explicitly.
Each run writes logs, a patch and `report.json` under a new `work/pr_checks_*`
directory. Failed checks are retained and produce a nonzero exit code.

The previous Terminal run passed build, eight targets and adapter tests on the
original baseline. Both lint failures came from one fixed constant-glob warning.
The original upstream patch failed because schema 142 was taken upstream. The
new worktree retains that upstream feature and assigns coupling revision 143.
Its patch passes against a clean index of the fetched upstream commit.
The assistant cannot write Bazel caches or clone the new OpenSTA submodule, so
the fresh build/test was run successfully in the user Terminal; its logs are archived.
The cached compiler-independent generator test and compiled unit tests were run
with their existing binaries; they do not substitute for a fresh build of a
future source revision. ODB regeneration used cached Jinja2 and pinned
clang-format 23.1.2 and produced no changes. The optional direct Python ODB test
is outside the supported Tcl transport path and remains skipped.

The following procedure describes the completed Linux portability check. Once a Linux checkout is
available, apply the patch to the reconciled target and run the CLI build, eight
registered targets, lint and companion suite. Palace is not required for the
OpenROAD core build or its registered tests. This bundle contains macOS and emulated Linux x86-64 core-runtime evidence.
The Palace numerical extraction evidence is from macOS only.

The successful Terminal report and exact exported patch have been archived,
and the PR draft is updated. Linux validation is now archived too. Review the final scoped diff and
description before submission. A clean patch application checks textual compatibility; it does not
replace a build/test of the updated upstream checkout. No PR action is automated.

## Schema and test-data boundary

Keep the original prototype's private schema-142 ODBs with its original binary.
Upstream schema 142 has a different meaning; the port uses 143 and preserves all
121 upstream object-type ordinals. Do not reuse those prototype ODBs with the new
binary. Adapter tests create fresh fixtures with the executable under test.
For a new copper workflow run, regenerate its input ODB using the new executable.
The archived numerical field-solver evidence remains valid for its recorded
benchmark and original executable. Reimporting scalar reference capacitances
into a freshly generated ODB does not require repeating the EM solve.

The primary patch targets b56f3a6a26. The separate
`patches/native_rc_coupling_baseline_08a3714.patch` retains the original-baseline
variant. These variants must not be applied on top of each other.

For the independent Linux pass, see [linux_validation.md](linux_validation.md).
The isolated container run completed successfully; Docker must be running to reproduce it.
