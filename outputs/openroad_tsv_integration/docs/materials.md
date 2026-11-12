# Tungsten and copper TSV configurations

Both tungsten and copper are valid TSV conductor choices. The original tungsten
configuration is retained, with its numerical equations and model constants
unchanged in `tsv_models.py`. Adding copper does not supersede that configuration.
No OpenROAD C++ rebuild is needed for this Python/Tcl material extension.

| Case | Conductor diameter | Length | Pitch | Liner | Electrical model |
| --- | --- | --- | --- | --- | --- |
| Original tungsten | 20 µm | 60 µm | 40 µm | 1 µm | Original TED/MATLAB reproduction conventions |
| Copper engineering benchmark | 5 µm | 50 µm | 20 µm | 0.2 µm | Bulk DC R; externally supplied C when available |

The copper case assumes 5.8e7 S/m at its declared 300 K. This is an explicit
engineering assumption, not measured process data or a fitted temperature model.
It yields 0.0439048 ohm for the uniform cylindrical conductor alone. Contacts,
barriers, taper, grain structure, and AC resistance are not included. The
metal diameter is independent of the terminal-marker LEF size used to transport
geometry. The oxide and silicon dielectric constants are recorded as 3.9 and
11.7 in the reference context, used by the separate Palace electrostatic model when extracting capacitance.

The substrate acceptor density is explicitly 1e15 cm^-3; an independent substrate
resistivity is not assigned. This avoids claiming that two uncalibrated substrate
properties describe the same process. The marker fixture has no drawn ground
plane, substrate contacts, or return TSVs. Its recorded substrate-reference and
bias assumptions must become explicit geometry/boundary conditions in a field model.
The Palace example uses an explicit grounded enclosure and treats silicon as a
linear dielectric; it does not use doping or bias to predict depletion.
The legacy `ground_spacing_m` metadata is not used in the new bulk DC model.

## Run both material examples

Use the schema-143 executable from `repos/OpenROAD-pr-ready`. The example
runner creates fresh input databases, so archived private-schema-142 ODBs are
not reused. From the workspace root, using a new output directory:

```sh
python3 outputs/openroad_tsv_integration/run_material_examples.py --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --output-dir work/tsv_material_examples_schema143
```

The tungsten case exports its existing native RC/SPEF network. The copper case
calculates R, stores the result in ODB properties, and records capacitances as
JSON `null` with status `resistance_only_capacitance_pending`. The copper case
therefore does not emit a physical RC/SPEF network before capacitance is supplied.
Changing an already marked copper endpoint to tungsten in config is rejected as
a metadata conflict. The original tungsten resistance and capacitance regressions
are included in the native adapter tests documented in [native_rc.md](native_rc.md).

To create just the copper input database:

```sh
python3 outputs/openroad_tsv_integration/make_native_fixture.py --profile copper --openroad repos/OpenROAD-pr-ready/bazel-bin/openroad --output-odb work/copper_schema143_input.odb
```

Then use `run_native.py` with `examples/copper_config.json` to produce a property
report. Supply `--native-rc` and the actual design's `--liberty` files only after
adding reference capacitance. `examples/copper_fixture/landing.lib` is a passive
pad interface for this synthetic fixture; it has no timing arcs.

## Supply copper capacitance

The separate model family is `material_dc_reference_c`. It supports explicit
conductivity for tungsten or copper, and requires `frequency_hz=0`. It never
applies the tungsten-calibrated AC or inductance fits to copper.

After running the property report, copy its `geometry_sha256` into a
`reference_capacitance` object in the configuration. Provide:

- `kind`: `q3d_extraction`, `measurement`, or `palace_electrostatic`. The Palace
  kind requires evidence hashes and the explicit benchmark validity label.
- `source`: an identifiable reference, including extraction file/version or
  measurement identifier, with its geometry and operating-point records.
- `geometry_sha256`: the report fingerprint.
- `unit`: `F`; `frequency_hz`: `0` for the supported quasi-static RC case.
- `ground_farad`: a map from every TSV id to its ground capacitance in farads.
- `pair_farad`: a map from compact JSON pair keys such as `["TSV_0","TSV_1"]`
  to mutual branch capacitance in farads, covering all modeled neighbor pairs.

The fingerprint covers the modeled TSV dimensions, positions, material,
conductivity, doping, temperature, net identities and the configuration's
`electrostatic_context`. Storage provenance is excluded; numeric values are
canonicalized to 12 significant digits for consistent native/offline reads.
It protects against accidental reuse of a reference after those fields change.
It does not verify an external solver's geometry, settings, or physical accuracy.
Update the context with actual bias, substrate contacts, and return geometry
before producing the reference data.

Provide circuit branch ground capacitance separately from mutual coupling.
For a Maxwell capacitance matrix, under its usual sign convention,
`C_pair(i,j) = -C_matrix(i,j)` and `C_ground(i) = sum_j C_matrix(i,j)` when the
complete modeled conductor set and reference are retained. The diagonal alone
is not the branch ground capacitance. Any eliminated/grounded return conductors
must be handled consistently before assigning the network entries. Do not add
mutual capacitance twice or treat capacitance to a floating substrate as VSS C.

`test_vector` references require `allow_test_capacitance=true`. The native tests
use deliberately artificial 50 fF ground and 5 fF pair values to check transport,
serialization, and repeat insertion. They are never presented as Q3D results or
predicted copper capacitance. The separate Palace benchmark has now completed
extraction and native RC/SPEF validation; see [copper_palace.md](copper_palace.md).

The Maxwell-to-SPICE convention above follows the [Ansys Q3D documentation](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v261/en/Subsystems/Q3DExtractor/Content/Q3D/RelationshipbetweenMaxwellMatrixandSpiceMatrix.htm).

## Verification

The current suite passes 49 tests and skips the optional direct Python `odb`
test. It includes the unchanged tungsten numerical checks, actual copper geometry
and conductivity extraction, independent DC resistance checks, rejection of
missing/reference-mismatched capacitance, and real copper ODB/SPEF roundtrips with
explicitly artificial test capacitors. The two-material example runner also
completed using the rebuilt macOS OpenROAD executable. The eight compiled Bazel
targets were already confirmed passing in the user's latest validation run.

## Scope

The copper geometry is an engineering benchmark, not a foundry-qualified stack.
The original tungsten benchmark remains valid for its stated material and
reproduction purpose. Its unresolved capacitance discrepancy is retained as a
separate issue. Physical validation of either process requires reference data.

Future work can add temperature-dependent conductivity, AC R/L models, explicit
G–S–S–G returns, substrate conductance, and process-qualified semiconductor capacitance. These are
not silently approximated by the current copper option.
