# Linux validation runner

> Research-workspace record: some commands and evidence paths below refer to
> internal tools or archived results not distributed in this repository. For
> supported publication-checkout commands, use the
> [repository quick start](../../../README.md).


Run from the workspace root with Docker Desktop's Linux engine already running:

```bash
python3 outputs/openroad_tsv_integration/run_linux_validation.py
```

The default target is Linux x86-64 (`linux/amd64`). On Apple Silicon Docker may
execute this using CPU emulation. This validates Linux x86-64 build/test behavior,
not native x86 hardware performance. Use `--platform linux/arm64` for a separate
Linux ARM64 check, and report its architecture separately.

The runner snapshots the exact current core patch and hashes every changed/new
source file. It builds the upstream Dockerfile's development stage using the
checkout's dependency installer, adding Python 3 for the test harness. All
package installation is inside that image. It records the resulting image ID.
The container fetches the exact base commit, applies the patch, and checks file
hashes before and after validation. It initializes the pinned submodules, builds
the CLI, checks full lint plus new-file styles, and runs the eight registered
regressions and companion tests. Two concurrent Bazel jobs limit memory pressure.
It does not format the test source, commit, push or create a PR.

A read-only input mount carries the patch and companion scripts. The macOS
checkout is not mounted. Output logs/report are written to a new
`work/linux_validation_*` directory. A named Docker volume retains Bazel cache
per architecture. Host Docker images and cache remain available for reuse.
Palace/Gmsh are not required for these core tests.

Success requires a Linux test report with the expected architecture and
`checks_passed`, and an outer report with `linux_validation_passed`. All check
logs and exact source identity are retained. A failed Docker preflight reports
`not_started`; it is not a completed Linux test or a source-code failure.

The completed run has status `linux_validation_passed`. Its inner report records
Linux x86_64 and `checks_passed`. The CLI build, seven lint targets, eight
registered regressions and 49 enabled companion tests pass; the optional direct
Python ODB test remains skipped. Exact changed-source identity is verified before
and after the checks. The current primary patch matches the tested patch.

Evidence is preserved in `review/linux_presubmit_pass/`. The initial blocked
Docker preflight is retained separately as historical troubleshooting evidence;
it is superseded by this successful run. The Linux core tests did not repeat
the Palace field-solver calculation.
