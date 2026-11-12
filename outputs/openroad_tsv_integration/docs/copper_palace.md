# Copper TSV capacitance extraction

## Run with the schema-143 PR checkout

From the project root, first create a fresh copper input using the same
executable that will perform insertion. Choose unused input/output paths:

```bash
python3 outputs/openroad_tsv_integration/make_native_fixture.py --profile copper --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --output-odb work/copper_schema143_input.odb
OPENROAD_BIN="$PWD/repos/OpenROAD-pr-ready/bazel-bin/openroad" TSV_ODB_INPUT="$PWD/work/copper_schema143_input.odb" bash outputs/openroad_tsv_integration/run_copper_palace.sh work/copper_palace_schema143
```

This explicitly overrides the shell wrapper's retained original-prototype
defaults (`repos/OpenROAD` and `work/tsv_material_examples/copper_input.odb`).
Do not use the wrapper's bare command for a schema-143 run. It uses the shared
Palace/Gmsh installation. Existing output directories are preserved; choose a
new directory for another run. An alternative fresh input is
`work/tsv_material_examples_schema143/copper_input.odb` after running both
material examples as described in [materials.md](materials.md).

The original prototype uses a private schema-142 layout. Its archived ODBs
cannot be reused with the PR-ready binary, which uses schema 143 and retains
upstream's different schema-142 feature. Regenerate the input database.
The recorded Palace matrices and scalar capacitance reference remain evidence
for their original benchmark. Reimporting a reference does not require another
EM solve when geometry, material, net/context fingerprints and evidence remain
valid; the command above intentionally runs extraction and validation afresh.

The runner exports actual TSV positions and process properties from OpenDB,
meshes two uniform TSVs, runs coarse and fine electrostatic solves, and requires
less than 1% change in every ground and pair branch capacitance. It converts the
Maxwell matrix using Cground_i = sum_j Cij and Cpair_ij = -Cij, checks reciprocity
and signs, and binds the reference to the geometry/material/net/context hash.
Input meshes, configurations, solver logs and matrix outputs receive SHA256
provenance. It then uses the existing native RC insertion, ODB persistence,
SPEF export and OpenSTA SPEF import checks. Tungsten equations remain unchanged.

## Explicit physical assumptions

The default copper fixture has diameter 5 um, length 50 um, pitch 20 um and
oxide liner thickness 0.2 um. Liner and silicon relative permittivities come from
the config (3.9 and 11.7 in the example). Silicon is modeled as a linear,
lossless dielectric. Four enclosure sidewalls are grounded, with the outer
rectangle extending 10 um beyond the liner bounds in each transverse direction.
The axial ends have zero normal displacement. The geometry is uniform along Z,
with no pads, end fringing, depletion, substrate leakage or contact resistance.
Copper conductivity enters the separate bulk DC resistance calculation.

This is a reproducible dielectric-enclosure benchmark, not a process-qualified
semiconductor TSV model. The enclosure is a physical reference for this model;
changing its dimensions changes the modeled device. The old fixture ground
metadata does not determine this enclosure. The actual boundary convention is
recorded in the reference's electrostatic context and fingerprint.

## Recorded original-prototype verification

Palace 0.16.0 and Gmsh 4.15.2 passed the native Apple Silicon analytical coax
smoke test. Fine-mesh error was 0.0201%, and mesh change was 0.0719%.
Both TSV meshes were generated (46,629 and 110,869 nodes), with positive minimum
Jacobian checks. Both field solves and the native OpenDB/SPEF pipeline completed.
The fine-mesh ground capacitances are 15.6188146997 and 15.6188237872 fF, and the
coupling branch is 1.3401850716 fF. DC resistance is 0.0439048119 ohm per TSV.
The largest coarse/fine branch change is 0.0157943%, below the 1% threshold.
The native graph contains two R segments, four ground-cap nodes and two coupling
segments (one half of each total at each axial end). SPEF values/totals and
OpenSTA import with capacitive coupling retained pass.

These results were produced with the original prototype executable and its
private schema-142 databases. They are not a recorded physical solver/insertion
run on the schema-143 PR checkout. The schema-143 implementation has separate
fresh-fixture native regression evidence, described in [native_rc.md](native_rc.md).

The completed run and original solver evidence are saved under
`results/copper_palace/`. Recorded configuration paths refer to the original
workspace. Use the runner to regenerate inputs for a different directory.
`results/copper_palace_preparation.json` records the earlier preparation stage;
`results/em_installation_verified.json` records the analytical installation test.

## Outputs after a successful run

The command above writes under `work/copper_palace_schema143` (the wrapper default remains `work/copper_palace_extraction`):

- `extraction_report.json`: convergence, matrices, branch capacitances and status.
- `copper_palace_config.json`: geometry-bound Palace reference capacitance.
- `copper_palace.odb`: native R, ground C and coupling C plus research provenance.
- `copper_palace.bonds.spef`: assembly parasitics for downstream analysis.
- `native_result.json` and related graph/log files: persistence and SPEF checks.

Success requires status `extracted_and_native_rc_spef_verified`. A failed run
retains its report and logs. If convergence exceeds 1%, refine the mesh before
importing. No values are substituted automatically.
