# Native TSV RC implementation

## Current checkout and database compatibility

The supported PR checkout is `repos/OpenROAD-pr-ready`, on branch
`tsv/native-rc-coupling-upstream`, based on upstream
`b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1`. It uses **schema 143**.
The corrected implementation passed CLI builds, seven lint targets, eight
registered test targets, and 49 enabled companion tests on macOS ARM64 and
Linux x86-64 in Docker/Rosetta. One optional direct-Python `odb` test is skipped.
The detailed validation evidence remains in the separate research archive.

The retained `repos/OpenROAD` prototype uses a **private schema-142 layout**.
Upstream schema 142 denotes a different feature. Keep its archived ODB files,
including `results/synthetic_tsv_input.odb` and `results/copper_palace/*.odb`,
with the original executable. Do not load those files into the schema-143 build.
Regenerate inputs from 3Dblox/LEF and process metadata with the executable used
for the new run; changing a schema number in a binary file is not a migration.

## Build and validate the current PR checkout

Follow the [repository quick start](../../../README.md#openroad-dependency) to
prepare and build the patched OpenROAD executable. Run native adapter tests with:

```sh
OPENROAD_BIN="$PWD/repos/OpenROAD-pr-ready/bazel-bin/openroad" TSV_RUN_NATIVE_RC=1 python3 -m unittest discover -s outputs/openroad_tsv_integration/tests -v
```

The internal `prepare_pr_checks.py` and `validate_native_rc.py` helpers are
retained in the research archive, not this publication checkout.

## Create a fresh input and insert RC

From the workspace root, choose unused input/output filenames:

```sh
python3 outputs/openroad_tsv_integration/make_native_fixture.py --profile tungsten --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --output-odb work/tsv_schema143_input.odb
python3 outputs/openroad_tsv_integration/run_native.py --native-rc --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --input-odb work/tsv_schema143_input.odb --output-odb work/tsv_schema143_native_rc.odb --config outputs/openroad_tsv_integration/examples/native_config.json --report work/tsv_schema143_native_rc.json --liberty outputs/openroad_tsv_integration/examples/native_fixture/landing.lib
```

This is an explicitly invoked companion workflow, not an automatic reaction to
finding two die SPEF files. Geometry and process parameters come from OpenDB and
the configuration; the assembly SPEF is an output of the workflow.

Use a new output filename each time. Supply the actual design Liberty libraries using repeated `--liberty` arguments.
The supplied `landing.lib` is only a passive pad interface for the synthetic
fixture, with no timing arcs; it does not model TSV electrical behavior.
The command emits an ODB, a `.bonds.spef`,
and JSON/log reports. A new OpenROAD process reloads the database to check native
values and topology. Python independently checks SPEF units, entries and totals.
Another process imports SPEF with `read_spef -keep_capacitive_coupling` and checks
for unresolved-node warnings.

## Database and circuit mapping

| Python quantity | Native storage | Unit |
| --- | --- | --- |
| TSV series resistance | existing `dbChipRSeg` between two endpoint nodes | ohm |
| Total TSV ground capacitance | existing `dbChipCapNode`, half at each endpoint | fF |
| Total pair coupling capacitance | new `dbChipCCSeg`, half between each corresponding pair of endpoints | fF |
| Inductance and model provenance | research JSON properties | SI units documented in JSON |

This is an explicit lumped pi approximation for two-terminal, parallel, equal
TSVs. The adapter requires direct children of the top assembly and one TSV per
two-bump chip net. Pair geometry is checked by the existing equation adapter.
Ownership properties distinguish these elements from other extracted RC. A repeat
run updates owned R/ground C and recreates owned coupling contributions. Conflicting
or unowned RC is rejected. Removing a previously owned TSV from the batch requires
explicit cleanup. Run this pass before an extractor that would append different
RC to the same assembly nets.

The new chip-owned coupling table supports serialization, SWIG collections,
validated endpoints and nonnegative finite capacitance. Deleting a cap node
removes incident couplings. Duplicate endpoint pairs are rejected. This initial
implementation scans the coupling table, so indexing is a future scalability
improvement. Chip parasitics currently store a single scalar value per element,
not frequency-dependent or multicorner models.

The current ODB schema advances upstream revision 142 to **143** for chip
coupling storage. Upstream's schema-142 feature is retained. The coupling object
type is appended after all 121 existing upstream types, preserving their ordinals.
A schema-141 fixture checks legacy property ownership. This compatibility test
applies to the upstream layout, not to the private prototype's schema-142 ODBs.
Use the schema-143 executable to read its new outputs; no backward-reader or
prototype-binary migration support is claimed.

## SPEF and downstream analysis

The assembly writer now emits ground and inter-net coupling `*CAP` records,
correct `*D_NET` capacitance totals, and existing `*RES` records. Each net lists
its incident coupling with the full element value, following the per-net SPEF
convention. Do not sum duplicate records across net sections as distinct physical
capacitors. `write_spef -assembly_only filename.spef` writes
`filename.bonds.spef` without requiring per-die extraction.

For a real stitched timing design, load libraries/constraints first, read bond
SPEF at the top scope, then read each die SPEF with `-path`. A top-scope read
replaces a network, while die-path reads merge their contributions. Grounded
coupling is the default OpenSTA behavior. Keeping coupling through the import
option does not establish full signal-integrity or crosstalk timing support.
The new dbSta regression checks that increasing native ground C increases
cross-die path delay after exported SPEF is read back. It uses controlled test
values rather than asserting that the still-unresolved research model is accurate.

## Current runtime validation

The corrected schema-143 patch passed on both platforms. Evidence is saved in
`review/p1_fix_macos_pass/` and `review/p1_fix_linux_pass/`; see also
`review/FINAL_REVIEW.md`. Tests cover native persistence, SPEF units and totals,
repeat insertion, valid capacitance-only networks, and cross-die timing response
to controlled ground-C values. An unbound cap node now reports RCX-6102 rather
than dereferencing a missing bump reference. The optional direct Python `odb`
test remains skipped; the supported runtime path uses the compiled Tcl interface.

Earlier prototype results remain under `results/` and in historical review
folders. They describe their recorded original executable, not a fresh physical
Palace extraction on the schema-143 checkout.

The 2009 capacitance equation/unit discrepancy remains unresolved. This work
preserves the explicit research convention selections; it does not validate a
physical TSV model or reproduce the ICCAD paper's design results. The synthetic
fixture does not contain a drawn ground plane or EM-qualified routed geometry.
