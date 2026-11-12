# OpenROAD / OpenDB TSV integration prototype

## Citation

Please reference the following publications when using these models:

1. I. Savidis and E. G. Friedman, “Closed-form expressions of 3-D via resistance, inductance, and capacitance,” *IEEE Transactions on Electron Devices*, vol. 56, no. 9, pp. 1873–1881, September 2009.
   DOI: [10.1109/TED.2009.2026200](https://doi.org/10.1109/TED.2009.2026200).
2. I. Savidis, S. M. Alam, A. Jain, S. Pozder, R. E. Jones, and R. Chatterjee, “Electrical modeling and characterization of through-silicon vias (TSVs) for 3-D integrated circuits,” *Microelectronics Journal*, vol. 41, no. 1, pp. 9–16, January 2010.
   DOI: [10.1016/j.mejo.2009.10.006](https://doi.org/10.1016/j.mejo.2009.10.006).
3. I. Savidis and E. G. Friedman, “Electrical modeling and characterization of 3-D vias,” *Proceedings of the IEEE International Symposium on Circuits and Systems*, pp. 784–787, May 2008.
   DOI: [10.1109/ISCAS.2008.4541535](https://doi.org/10.1109/ISCAS.2008.4541535).

## Overview

The proposed core PR is described in [PR_CHANGE_DETAILS.md](review/PR_CHANGE_DETAILS.md),
starting with a high-level bulleted summary and followed by detailed changes,
validation, compatibility notes, and the complete file inventory.

The current PR implementation uses `repos/OpenROAD-pr-ready`, based on upstream
`b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1`, with **OpenDB schema 143**.
It passed macOS ARM64 and Linux x86-64 Docker/Rosetta validation. The companion
adapter uses compiled Tcl transport and ordinary Python for the TSV equations;
a separate Python `odb` extension is optional.

The original `repos/OpenROAD` prototype at `08a3714d61` and the archived ODB
examples use a private schema-142 layout. Those databases must stay with their
original executable. Upstream schema 142 has a different meaning. Create fresh
inputs with the schema-143 executable for current runs; see
[native_rc.md](docs/native_rc.md) for the compatibility boundary and validation.

## Open-source capacitance extraction setup

Palace 0.16.0 and Gmsh 4.15.2 passed native Apple Silicon installation and
analytical capacitance verification. The copper TSV extraction runner completed both mesh solves, native RC
insertion, ODB persistence, SPEF export and OpenSTA SPEF import. Ground C is
15.619 fF per TSV and pair C is 1.3402 fF for the dielectric-enclosure benchmark.
See [copper_palace.md](docs/copper_palace.md) for the one-command workflow and
explicit dielectric/enclosure assumptions, and
[palace_gmsh_setup.md](docs/palace_gmsh_setup.md) for installation details.

## Material options

The original tungsten TSV remains supported, with unchanged numerical equations
and default geometry. Copper is added as a separate `material_dc_reference_c`
model family with a 5 µm × 50 µm benchmark, explicit conductivity, and supplied
capacitance support. It does not replace tungsten or reuse its AC calibration.
See [materials.md](docs/materials.md) for commands, reference-data requirements,
and the distinction between extracted benchmark capacitance and test vectors.

## Run the current native path

From the workspace root, using unused output filenames:

```sh
python3 outputs/openroad_tsv_integration/make_native_fixture.py --profile tungsten --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --output-odb work/tsv_schema143_input.odb
python3 outputs/openroad_tsv_integration/run_native.py --native-rc --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --input-odb work/tsv_schema143_input.odb --output-odb work/tsv_schema143_native_rc.odb --config outputs/openroad_tsv_integration/examples/native_config.json --report work/tsv_schema143_native_rc.json --liberty outputs/openroad_tsv_integration/examples/native_fixture/landing.lib
```

The runner refuses to overwrite input or existing output databases. Separate
OpenROAD processes export geometry, insert results, and verify persisted data.
It exports assembly bond SPEF and checks its values and OpenSTA import.
The archived `results/native_demo.json` and its ODB files belong to the original
prototype; the commands above regenerate the input for the current schema.
Extraction is explicitly invoked; finding die SPEFs does not trigger it.

Run the compiled-binary tests from the workspace root:

```sh
OPENROAD_BIN="$PWD/repos/OpenROAD-pr-ready/bazel-bin/openroad" TSV_RUN_NATIVE_RC=1 python3 -m unittest discover -s outputs/openroad_tsv_integration/tests -v
```

The current suite includes real native RC insertion, SPEF import and repeat-run
checks when `TSV_RUN_NATIVE_RC=1` is set. The optional direct-Python `odb` test
remains separate. See the native RC guide for the current validation results. The native test checks length, pitch, process
metadata read from actual OpenDB double properties, model values, persistence in
a new process, repeat-run idempotence, input preservation, and conflicting metadata.
The synthetic fixture is an assembly of terminal markers with explicit TSV process
metadata, not an EM-qualified routed TSV design. Its ground-reference distance is
metadata, not geometry extracted from a drawn ground plane. The 3Dblox checker
reports a floating-chip-set warning because it has no package/physical bond model;
this does not invalidate the transport test or establish physical stack validity.

## Start with the offline example

Run from this directory with Python 3.10 or newer; no additional packages:

```sh
mkdir -p ../../work
python3 run_bridge.py --config examples/config.json --fixture examples/endpoints.json --report ../../work/offline_demo.json
python3 -m unittest discover -s tests -v
```

The example contains two parallel tungsten TSVs, 20 um diameter, 60 um length,
40 um pitch, 1 um liner, and 10 um distance to a common ground reference. Positions
are synthetic, not extracted from an actual OpenDB file. `../../work/offline_demo.json`
records R, ground C, pair C, self L, mutual L, geometry, units, and provenance.
The model settings explicitly select the legacy reproduction conventions; they
are not endorsed corrections to the unresolved capacitance equations.

## Repository setup

Recommended initial API baseline: The-OpenROAD-Project/OpenROAD, which has publicly
documented native 3D objects and chip-level RC objects. The paper and slides also
reference ieee-ceda-datc/OpenROAD-Research and CODA-Team/TaiWei. These repositories
serve different roles; they are not interchangeable version identifiers. We have
not established a paper-specific commit or verified a corresponding research branch.

For a new publication checkout, follow the pinned dependency and build commands
in the [repository quick start](../../README.md#openroad-dependency). They use
upstream `b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1` and the bundled schema-143 patch.
Do not apply the patch twice or substitute an unreviewed current `master`.
Read applicable AGENTS.md files before modifying OpenROAD. The historical
`repository_status.json` belongs to the research archive, not this checkout.
Do not install an unrelated pip package named `odb`; use OpenROAD's compiled
bindings if you choose the optional direct-Python route.

## Native database path after the build is available

The pinned C++ source and compiled Tcl 3D API have been inspected/tested. Python
exposure must still be checked against a compiled Python extension. `bridge.probe`
reports key Python classes and methods; extraction raises on missing requirements.
This section describes the optional direct-Python route, not the verified Tcl transport.

Prepare a config with actual endpoint paths/instance names from the design, and
actual TSV process metadata. Then run using the Python environment that can import
the compiled OpenDB `odb` module:

```sh
mkdir -p ../../work
python3 run_bridge.py --config actual_config.json --input-odb assembly.odb --output-odb assembly_with_tsv_research.odb --report ../../work/assembly_report.json
```

The command constructs the derived unfolded model, reads positions and connectivity,
checks selected endpoints, evaluates the equations, writes a distinct output file,
reopens it, and compares the stored property. It refuses to overwrite the input or
an existing output. This direct-Python route remains unexecuted; use run_native.py
for the tested macOS executable route.

`TSV_ODB_INPUT` and `TSV_ODB_CONFIG` can be set to run the optional native roundtrip
unit test under that same runtime. Without the native module and fixture it is
explicitly skipped, not counted as a successful integration test.

## Data contract

Each modeled conductor selects two endpoints by chip-instance path and pad-instance
name. Selection explicitly confirms `kind=cylindrical_tsv` and that the endpoint
coordinates denote conductor ends. Not every bump pair meets this condition.
Full path arrays distinguish repeated chip-master placements without aliasing.

Global coordinates are obtained from `dbUnfoldedChipBumpInst.getGlobalPosition()`
and converted using the assembly's `dbDatabase.getDbuPerMicron()`. The bridge does
not apply die-local DBU scaling to global coordinates. It uses the database's
unfolded transforms rather than manually combining chip orientations.

Core diameter, liner, ground distance, doping, and temperature are read from double
properties on the selected source pad instance if present. These property names
are a proposed prototype convention, not existing standardized OpenDB attributes:

- `org.drexel.tsv.research.v1.diameter_m`
- `org.drexel.tsv.research.v1.liner_m`
- `org.drexel.tsv.research.v1.ground_spacing_m`
- `org.drexel.tsv.research.v1.acceptors_cm3`
- `org.drexel.tsv.research.v1.intrinsic_cm3`
- `org.drexel.tsv.research.v1.temperature_k`

If a property is absent, an explicit per-TSV config value is required and recorded
as such. Conflicting ODB/config values are rejected. Ground-reference identity,
material, substrate, TSV classification, and endpoint interpretation are explicit
config fields in this prototype. There are no hidden process defaults. Pad dimensions,
chip thickness, and bond-gap thickness are never silently treated as TSV geometry.

The original TED model family supports Z-aligned rods, tungsten, p-type silicon with the original
silicon/oxide constants, bulk TSV diameters 20-60 um, and aspect ratios 0.5-9. This
range is a screening envelope, not blanket validation for every geometry therein.
It is not a calibrated copper/hybrid-bond model. Coupling is evaluated once per
unordered pair within an explicit search radius, only for equal-diameter rods
with identical Z spans, a common reference identity, and matching ground distances.
Unsupported pairs are listed. Pair enumeration is currently quadratic: replace it
with a spatial index before large bump-map runs. This is not a multi-body field solve.
Same-net pair values are flagged and retained for diagnostics; they are not inserted
as inter-net coupling or automatically added to the ground capacitance.

## Storage versus electrical use

`org.drexel.tsv.research.v1.results` is a JSON string property on the folded root
chip. It stores the full occurrence-specific result table and persists through the
ordinary `.odb` mechanism when supported by the compiled runtime. Re-running updates
that property instead of adding duplicate contributions. Results include the model
source hash and the unresolved-capacitance status. No properties are attached to
the temporary unfolded objects, and shared master-level pad instances are not used
to store placement-dependent calculated values.

The default property route remains available. The optional `--native-rc` route
adds a native pi network using `dbChipRSeg` and `dbChipCapNode`, and stores pair
coupling in the new `dbChipCCSeg` table. The patched assembly writer emits ground
and coupling `*CAP` entries with fF/ohm conversion. See
[the native RC guide](docs/native_rc.md) for the rebuild command and verification
status. The corrected timing regression and its Bazel resources passed on macOS
and Linux in the recorded core validation.

See `docs/integration_design.md` for the field mapping, missing-schema proposals,
source URLs, and implementation/validation milestones.

## Submission preparation

See [pr_readiness.md](docs/pr_readiness.md) for the core/companion scope split,
local checks, remaining Terminal/Linux checks, and an unsubmitted PR draft.

## License

Original TSV companion code and documentation use the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International license
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
See the repository's [LICENCE](../../LICENCE) for the full terms and
[THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) for upstream exceptions.
Please reference the publications in the Citation section when using the models.
