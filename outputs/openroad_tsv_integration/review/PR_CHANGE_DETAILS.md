# OpenROAD PR changes and additions

## High-level summary

- Add native chip-level coupling-capacitor storage through a new `dbChipCCSeg` object.
- Preserve coupling data and attached properties across OpenDB save/reload, and remove incident couplings when their endpoint nodes are deleted.
- Advance the database schema to **143**, retaining upstream's schema-142 feature and existing object-type ordinals.
- Extend the OpenDB generator and type registries so the new persistent object is reproducible and existing type IDs remain stable.
- Export ground and inter-net coupling capacitance in assembly SPEF, with matching net capacitance totals and unit conversion.
- Add `write_spef -assembly_only` to export bond parasitics without requiring per-die extraction.
- Extend C++ and Tcl/Python-facing bindings for chip-level RC objects and the new export option.
- Prevent the capacitance-only export crash by reporting **RCX-6102** when a node lacks the bump reference needed to name its SPEF terminal.
- Add and register database, SPEF, API, compatibility, and cross-die timing regressions, including positive and negative capacitance-only cases.
- Document validation on macOS ARM64 and Linux x86-64 in Docker/Rosetta; keep the TSV equations and Palace/Gmsh extraction workflow in a separate companion bundle.

## 1. Scope and reviewed baseline

This document describes the proposed **OpenROAD core PR** and identifies related
companion work separately. The core patch contains **39 files: 31 modified and
8 added**. It has not been committed, pushed, or submitted as a PR.

| Item | Value |
| --- | --- |
| Proposed target | `The-OpenROAD-Project/OpenROAD:master` |
| Reviewed upstream base | `b56f3a6a26fcab9c6f86604358ae5ac0a9a28ce1` |
| Prepared checkout | `repos/OpenROAD-pr-ready` |
| Local branch | `tsv/native-rc-coupling-upstream` |
| Database schema | 143 |
| Core patch | `patches/native_rc_coupling.patch` in the companion bundle |
| Final review | `review/FINAL_REVIEW.md` |

The purpose is to let assembly-level capacitance be stored as native circuit
elements and exported for downstream SPEF consumers. The core PR does not add a
TSV field solver or automatically derive physical TSV capacitance.

## 2. Native database representation

### Existing elements reused

`dbChipRSeg` already stores chip-level series resistance, and `dbChipCapNode`
already stores ground capacitance at a circuit node. These classes are reused;
the PR does not introduce replacement resistor or ground-capacitor classes.
Their units are documented more clearly.

| Electrical quantity | Native object | Storage unit | Change |
| --- | --- | --- | --- |
| Series resistance | `dbChipRSeg` | ohm | Existing storage reused; unit comments and collection bindings extended |
| Ground capacitance | `dbChipCapNode` | fF | Existing storage reused; export and deletion cleanup extended |
| Inter-net coupling capacitance | `dbChipCCSeg` | fF | New chip-owned persistent object |

### New coupling object

Each `dbChipCCSeg` stores two cap-node references and one scalar floating-point
capacitance. Both endpoints must belong to different nets of the same chip.
The chip owns the coupling table, so a capacitor between two nets has one native
owner. Public methods support creation, deletion, capacitance access/update,
endpoint access, owner access, and iteration through `dbChip::getChipCCSegs()`.

Creation rejects same-net endpoints, endpoints from different chips, and an
existing endpoint pair in either order. A null endpoint returns no object.
The capacitance setter rejects negative values, NaN, and infinity.

Deletion removes coupling properties before deleting the object. Deleting a
cap node first removes its incident couplings and its node properties. Net
cleanup uses cap-node destruction, so those couplings are removed as well.
Chip construction/destruction, comparison, table lookup, and memory accounting
include the new table.

These elements remain single scalar values. This change does not create a
frequency-dependent or multi-corner chip-parasitic representation.

## 3. Serialization and compatibility

The PR uses database revision **143**, with `kSchemaChipCoupling` guarding reads
of the added table. New writes include the coupling table. Upstream revision 142
already belongs to the cut-enclosure-table feature and is retained unchanged.

The coupling object type is appended after the existing type sequence. The
reviewed upstream sequence of 121 existing object types is preserved. This
matters because some database structures persist object-type ordinals, including
property ownership and references; preserving only type hashes would not suffice.

Generator snapshots pin that sequence and check that enum entries, name tables,
and hash mappings stay aligned. A schema-141 binary fixture checks legacy chip-net
property ownership when read by the updated database implementation. New-object
roundtrip tests check capacitance, endpoints, and coupling-property ownership.

The original research prototype privately used revision 142 for coupling storage.
Those historical ODB artifacts have a different layout from upstream schema 142.
Keep them with their original binary and regenerate fixture databases for the
schema-143 checkout. They are retained as historical research evidence, not as
input databases for the new build.

## 4. Generator and binding changes

The schema model gains `object_type_order`, defaulting to zero for the existing
alphabetically generated group. Positive ranks append persistent types;
`dbChipCCSeg` uses rank 1. The generator rejects negative/non-integer ranks and
duplicate positive ranks. Templates generate the appropriate enum, name, and
hash-table sections, and the generator documentation explains the rule for future
persistent types.

Regenerated OpenDB headers and sources accompany the schema/template changes.
Full regeneration was checked for idempotence. The schema/generator tests are
registered under `//src/odb:code_generator_test` with declared inputs.

SWIG collection wrappers now cover `dbChipCapNode`, `dbChipRSeg`, and
`dbChipCCSeg`. Tcl API tests exercise the compiled collection path. The Python-
facing declarations are updated too, but the optional direct Python `odb`
runtime test remains skipped; the verified companion workflow uses OpenROAD's
Tcl interface from an ordinary Python process.

## 5. Assembly SPEF behavior

The assembly writer previously emitted connections and resistors but no `*CAP`
records. Ground values stored on chip cap nodes therefore lacked corresponding
explicit capacitor records in the exported network.

The writer now emits:

- Ground `*CAP` records for nonzero cap-node capacitance.
- Inter-net `*CAP` records for incident `dbChipCCSeg` objects.
- `*D_NET` totals equal to ground capacitance plus incident coupling capacitance.
- Existing `*RES` records and terminal connections.

Each net section lists its incident coupling at the full element value, following
the per-net SPEF convention. The two incident net sections do not represent two
separate physical coupling objects. Summing those repeated records globally as
independent capacitors would double-count them.

Output values use the existing SPEF unit-scaling mechanism. C++ tests cover
PF/FF capacitance and OHM/KOHM resistance combinations, net totals, and record
counts/values. Numeric output precision is increased for the assembly records.
Networks containing capacitance without R segments are now exportable when their
terminal references are valid; this behavior is tested directly.

### Assembly-only command

```tcl
write_spef -assembly_only design.spef
```

This writes `design.bonds.spef` and bypasses per-die SPEF extraction. The option
requires a hierarchical 3D assembly and rejects simultaneous net-ID, net-name,
or coordinate filters. The internal options structure defaults `assembly_only`
to false, and the binding argument is optional to preserve existing callers.

The feature exports stored parasitics. It does not calculate missing values,
create a full extraction flow, or add full crosstalk/signal-integrity timing.

## 6. Capacitance-only crash correction

Final review found that a cap node created without a bump reference could reach
the terminal-name lookup and cause a null-pointer dereference. The writer now
checks that optional reference before using it and raises **RCX-6102**, identifying
the net and node. It retains the stored capacitance and fails explicitly.

This keeps the terminal-based export contract clear: a node needs a valid bump
reference to produce its terminal name. The fix does not invent an internal-node
name or silently discard a capacitor. Valid capacitor-only networks still export.

New C++ cases check valid capacitor-only export and the exact unbound-node
exception. The Tcl regression checks the same diagnostic through `write_spef`
and confirms the value is unchanged. The original minimal crash reproducer now
returns exit code 1 with RCX-6102 instead of a segmentation fault. The fix and
both updated RCX test targets passed on macOS and Linux.

## 7. Tests and completed validation

The eight registered targets used for the core validation are:

1. `//src/odb:code_generator_test`
2. `//src/odb/test/cpp:TestChips`
3. `//src/odb/test/cpp:TestObjectType`
4. `//src/rcx/test:rcx_unittest`
5. `//src/rcx/test:chip_caps_api-tcl_test`
6. `//src/dbSta/test:3dic_native_caps-tcl_test`
7. `//src/dbSta/test:3dic_spef-tcl_test`
8. `//src/dbSta/test:3dic_read_db-tcl_test`

| Check | macOS ARM64 | Linux x86-64, Docker/Rosetta |
| --- | --- | --- |
| CLI build | Passed | Passed |
| Seven repository lint targets | Passed | Passed |
| Explicit new-file formatting/lint | Passed | Passed |
| Eight registered test targets | Passed | Passed |
| Companion suite | 49 passed; 1 optional skip | 49 passed; 1 optional skip |
| Corrected RCX tests | Executed and passed | Executed and passed |
| Source/patch identity | Matched the saved patch | 39 changed files checked before/after; matched current source |

The OpenRCX unit binary now has six cases, including the two new capacitor-only
cases. The generator/schema suite has 34 tests. Database tests cover endpoint
validation, duplicate rejection, invalid capacitance, deletion cleanup, new
serialization/property ownership, and legacy readback.

The cross-die timing regression uses controlled capacitance values and fresh
OpenSTA sessions to check that increasing native ground capacitance increases
path delay after SPEF export/import. This verifies the electrical integration
behavior without asserting physical TSV accuracy from the test vectors.

The latest evidence is in `review/p1_fix_macos_pass/`,
`review/p1_fix_linux_pass/`, `review/rcx_unit_fixed.log`,
`review/rcx_tcl_fixed.log`, and `review/cap_only_fixed.log`.
Linux execution used x86-64 emulation on an Apple Silicon host. It is a Linux
platform correctness check, not a native x86 performance benchmark. The completed
checks are the scoped checks above, not a claim that every upstream flow or
maintainer CI configuration has been run locally.

## 8. Related companion additions outside the core PR

The companion bundle contains the work that supplies and validates TSV values.
It does not add Palace/Gmsh or the research models as dependencies of OpenROAD.

| Companion component | Purpose |
| --- | --- |
| Original tungsten equations | Preserve the TED/MATLAB reproduction conventions and tungsten support |
| Copper material model | Compute uniform-cylinder bulk DC resistance from explicit conductivity; require a supplied capacitance reference |
| OpenDB/Tcl/Python bridge | Extract unfolded endpoint positions, read explicit process metadata, evaluate models, store research provenance, and insert owned native RC |
| Native network mapping | Split total ground C between TSV ends and pair coupling between corresponding endpoint pairs in a lumped pi approximation |
| Palace/Gmsh runner | Build two-TSV dielectric/liner/enclosure geometry, extract its Maxwell matrix, convert it to branch C, check mesh convergence, and import a geometry-bound reference |
| Reference provenance | Bind values to geometry/material/net/context fingerprints and record solver-input/output SHA256 hashes |
| Installation and validation tools | Set up shared macOS tools, check the analytical coax problem, and run isolated exact-source Linux validation |
| Example collateral | Provide synthetic terminal markers, minimal LEF/Liberty data, configs, ODB/SPEF results, and validation logs |

The copper example uses a 5 um conductor diameter, 50 um length, 20 um pitch,
0.2 um oxide liner, and assumed conductivity of 5.8e7 S/m at 300 K. Its original
recorded field-solver run used liner/silicon relative permittivities of 3.9/11.7,
grounded enclosure sidewalls, and insulated axial ends. Fine-mesh results were
approximately 15.619 fF ground capacitance per TSV and 1.3402 fF pair coupling,
with a largest mesh-refinement change of 0.0158%. Bulk DC resistance was
0.0439048 ohm per TSV.

That is a linear, lossless dielectric-enclosure benchmark. It excludes substrate
depletion/conduction, contacts, and end fringing, and is not process-qualified.
Its Palace and native insertion evidence belongs to its recorded original binary;
the schema-143 core has independent regenerated-fixture regressions. Doping and
bias metadata are not interpreted as a semiconductor depletion solution.
The original tungsten equations remain unchanged, and the 2009 capacitance
subscript/unit discrepancy remains unresolved.

## 9. Limits and follow-up work

Coupling insertion checks scan the chip coupling table, and export scans that
table for each net. Creating M couplings is O(M^2); export is O(N*M) for N nets.
Per-net adjacency/indexing or measured size limits are follow-up work before
claiming large-assembly scalability.

The PR stores scalar R/C. It does not add native inductance, AC resistance,
frequency-dependent RC, multi-corner chip RC, automatic TSV classification, or a
process-qualified semiconductor extraction model. No OpenSTA source files are
changed. There are no remaining blocking findings in the reviewed scope after
the verified capacitor fix. Submission still requires the user's approval.

## 10. Complete core file inventory

All paths below are relative to the OpenROAD repository. Generated files are
included deliberately so that the committed schema/templates reproduce the
checked source. The eight added files are already present locally but remain
untracked until staging; they are included in the saved patch.

| File | Change | Purpose |
| --- | --- | --- |
| `src/dbSta/test/3dic_native_caps.tcl` | Added | Check that exported native ground capacitance increases cross-die path delay in fresh timing sessions. |
| `src/dbSta/test/BUILD` | Modified | Register the native-capacitance timing regression and its SPEF fixtures. |
| `src/odb/BUILD` | Modified | Register the schema/generator Python tests with hermetic Jinja2 inputs. |
| `src/odb/include/odb/db.h` | Modified | Declare dbChipCCSeg, chip-level coupling iteration, and ground-C/R unit comments. |
| `src/odb/include/odb/dbCompare.inc` | Modified | Extend the generated pointer-comparison declarations to the coupling type. |
| `src/odb/include/odb/dbObject.h` | Modified | Append the new object type while retaining existing enum ordinals. |
| `src/odb/src/codeGenerator/README.md` | Modified | Document stable object-type ordinal ordering and positive append ranks. |
| `src/odb/src/codeGenerator/gen.py` | Modified | Validate append ranks before deriving generated database code. |
| `src/odb/src/codeGenerator/schema.json` | Modified | Declare the chip-owned coupling-table relationship and schema guard. |
| `src/odb/src/codeGenerator/schema/chip/dbChipCCSeg.json` | Added | Define coupling endpoints, scalar capacitance, ownership-related includes, and append rank. |
| `src/odb/src/codeGenerator/schema/chip/dbChipCapNode.json` | Modified | Record ground-capacitance units and includes required for incident-coupling cleanup. |
| `src/odb/src/codeGenerator/schema/chip/dbChipRSeg.json` | Modified | Document existing resistance units in the generated public API. |
| `src/odb/src/codeGenerator/schema_models.py` | Modified | Represent object_type_order in the generator schema model. |
| `src/odb/src/codeGenerator/templates/dbObject.cpp.jinja` | Modified | Generate aligned name/hash tables for legacy and appended object types. |
| `src/odb/src/codeGenerator/templates/dbObject.h.jinja` | Modified | Generate the appended object-type enum section. |
| `src/odb/src/codeGenerator/test_all.py` | Added | Run the generator/schema test modules through one Bazel test entry point. |
| `src/odb/src/codeGenerator/test_generator_snapshot.py` | Modified | Check enum/name ordering and pin the complete upstream legacy ordinal sequence. |
| `src/odb/src/db/dbChip.cpp` | Modified | Manage coupling-table lifetime, comparison, serialization, iteration, and memory accounting. |
| `src/odb/src/db/dbChip.h` | Modified | Add the private chip-owned coupling table. |
| `src/odb/src/db/dbChipCCSeg.cpp` | Added | Implement coupling creation, validation, accessors, deletion, and generated persistence. |
| `src/odb/src/db/dbChipCCSeg.h` | Added | Define private coupling storage and stream/comparison declarations. |
| `src/odb/src/db/dbChipCapNode.cpp` | Modified | Remove incident coupling objects and node properties before node deletion. |
| `src/odb/src/db/dbChipRSeg.cpp` | Modified | Regenerate the public resistance-unit comment. |
| `src/odb/src/db/dbDatabase.h` | Modified | Introduce schema revision 143 and the chip-coupling feature guard. |
| `src/odb/src/db/dbObject.cpp` | Modified | Register the appended coupling type in object name/hash lookup tables. |
| `src/odb/src/swig/common/containers.i` | Modified | Expose iteration for chip cap nodes, R segments, and coupling segments. |
| `src/odb/test/BUILD` | Modified | Export the legacy binary compatibility fixture as a Bazel resource. |
| `src/odb/test/cpp/BUILD` | Modified | Provide the legacy fixture to TestChips. |
| `src/odb/test/cpp/TestChips.cpp` | Modified | Test coupling validation, persistence, property ownership, cleanup, and legacy readback. |
| `src/odb/test/data/chip_property_v141.odb` | Added | Provide a schema-141 property-owner compatibility fixture. |
| `src/rcx/README.md` | Modified | Document assembly-only SPEF export and its option restrictions. |
| `src/rcx/include/rcx/ext_options.h` | Modified | Carry the assembly_only option with a false default. |
| `src/rcx/src/OpenRCX.tcl` | Modified | Expose -assembly_only on the public Tcl write_spef command. |
| `src/rcx/src/ext-py.i` | Modified | Extend the Python-facing declaration with an optional assembly_only argument. |
| `src/rcx/src/ext.i` | Modified | Forward the option and reject unsupported assembly-only uses. |
| `src/rcx/src/multiChipSpefWriter.cpp` | Modified | Export ground/coupling C and totals, support assembly-only output, and reject unbound cap nodes safely. |
| `src/rcx/test/BUILD` | Modified | Register the coupling API Tcl regression and the C++ SPEF tests. |
| `src/rcx/test/TestMultiChipSpef.cpp` | Added | Check SPEF units/totals, capacitance-only networks, and the unbound-node diagnostic. |
| `src/rcx/test/chip_caps_api.tcl` | Added | Check RC collection bindings, empty export, and RCX-6102 through Tcl. |

## 11. Snapshot and supporting documents

This document describes the tested patch as of 2026-11-12. The current patch
SHA256 is `3bb8fcd11301794f42e05bc07486c9b7eaab6f1fe352145dce9749256eb8da44`. A future source change or rebase requires checking that
this inventory and the validation evidence still match.

- Short proposed PR description: `review/OPENROAD_PR.md`.
- Final review and closed blocker: `review/FINAL_REVIEW.md` and `review/P1_FIX.md`.
- Readiness and evidence index: `review/pr_readiness.json`.
- Core patch: `patches/native_rc_coupling.patch`.
- Earlier baseline variant: `patches/native_rc_coupling_baseline_08a3714.patch`,
  retained separately; do not combine it with the current upstream-based patch.

No commit, push, or PR submission is performed by producing this document.
