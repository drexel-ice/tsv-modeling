# Add native chip coupling capacitors and assembly capacitance SPEF export

For the high-level summary, detailed changes, and complete 39-file inventory,
see [PR_CHANGE_DETAILS.md](PR_CHANGE_DETAILS.md).

Final review follow-up: the missing-bump guard and positive/negative C++/Tcl
regressions passed on both platforms. The reproduced crash blocker is closed;
see `review/FINAL_REVIEW.md`.

Chip-level parasitics currently lack a native coupling-capacitor object, and the
assembly SPEF writer omits ground and coupling capacitance. Add chip-owned
`dbChipCCSeg` objects, their persistent storage and Tcl/Python SWIG collection
bindings, and emit ground/coupling `*CAP` entries with matching `*D_NET` totals.
The `write_spef -assembly_only` option permits bond SPEF export without per-die
extraction. A two-net assembly can now retain its native R/C network through an
ODB roundtrip and export it for downstream SPEF import.

The new ODB schema revision is 143 on upstream b56f3a6a26. Existing object-type
ordinals are preserved, and a schema-141 fixture checks legacy property ownership.
Coupling creation rejects endpoints on the same net or different chips, duplicate
endpoint pairs, and invalid capacitance values. Deleting either endpoint removes
incident coupling objects. New C++ and Tcl regressions cover persistence, units,
SPEF values/totals, and cross-die timing response to added native ground capacitance.

## Validation

On macOS ARM64, the upstream-based schema-143 checkout passed:

- CLI build and all eight targeted Bazel regressions passed.
- All seven repository lint checks and explicit formatting/lint of new files.
- Companion suite: 49 pass; one optional direct-Python ODB test skipped.
- Patch reverse applicability and forward applicability against fetched upstream
  b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1.

Local generator checks also pass all 34 tests; full regeneration is idempotent.
The original companion Palace benchmark passed field extraction, mesh convergence,
native RC insertion, ODB persistence, SPEF export and OpenSTA SPEF import on its
recorded original binary. That numerical solver evidence is preserved separately
from the new core checkout's regression results.

Linux x86-64 validation also passed in Docker under Rosetta emulation on Apple
Silicon: CLI build, all seven lint targets, all eight registered targets, and
49 enabled companion tests (one optional skip). Source identity was checked
before and after the run for all 39 changed files; the current primary patch
matches the validated patch. This is Linux platform validation under emulation,
not native x86 hardware performance testing. Evidence is saved in
`review/macos_presubmit_pass/` and `review/linux_presubmit_pass/` in the companion
bundle.

## Scope and limitations

The core patch contains no Palace/Gmsh dependency and no TSV material equations.
Those remain companion research code. The companion copper result is a linear,
lossless dielectric-enclosure benchmark with insulated axial ends. It does not
establish semiconductor depletion/leakage behavior or process-qualified accuracy.
The original tungsten equations remain unchanged.

This change stores scalar capacitances and resistance. It does not add native
inductance to OpenRoad, frequency/corner models, automatic TSV extraction, or full 
crosstalk STA. For inductance, The companion tungsten models calculate self and 
mutual inductance, but this PR integrates only resistance and capacitance into native 
OpenDB elements and assembly SPEF export. Inductance remains stored as research metadata.  
Coupling-table scans are retained; indexing for large assemblies is follow-up
work. Upstream schema 142 is retained; the coupling feature uses revision 143.

The tested original prototype used a private schema-142 layout. Its ODB artifacts
must not be loaded into the upstream-based build, where 142 denotes a different
upstream feature. Regenerate fixture databases with the schema-143 executable.
The new code preserves the target upstream enum sequence before appending the
coupling type.

Unbound capacitance-only nodes now receive RCX-6102 rather than dereferencing a
missing bump reference. New C++ tests cover rejection and valid capacitor-only
networks, and the Tcl API regression checks the diagnostic. These tests passed on the 
rebuilt macOS and Linux targets. Fixed-patch evidence is saved in `review/p1_fix_macos_pass/` 
and `review/p1_fix_linux_pass/`.
